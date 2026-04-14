#!/usr/bin/env python3
"""
lint-forth.py — Unified Forth source validator.

Catches five silent-failure constraints at build time:

  Vocabulary mode (.fth files):
    1. Line length — errors on lines > 64 chars (block truncation)
    2. BASE tracking — warns on suspicious literals in colon defs after HEX

  Assembly mode (--asm forth.asm):
    3. DTC threading — flags code_* refs in DEFWORD bodies (should be XT)
    4. CREATE CFA — verifies CREATE writes code_DOCREATE
    5. Branch offsets — validates DOLOOP/BRANCH offsets in hand-written DEFWORDs

Usage:
    python3 tools/lint-forth.py forth/dict/*.fth
    python3 tools/lint-forth.py --asm src/kernel/forth.asm
    python3 tools/lint-forth.py --verbose forth/dict/*.fth  # show BASE details
    python3 tools/lint-forth.py --strict forth/dict/*.fth   # warnings are errors

Exit codes:
    0 — no errors (warnings may be present)
    1 — errors found (or warnings with --strict)
"""

import sys
import os
import re

SCREEN_COLS = 64


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def strip_comments(line):
    """Remove Forth comments from a line for analysis.

    Handles:
      - Backslash comments: \\ rest of line
      - Parenthesized comments: ( ... )

    Returns the line with comment content removed.
    """
    result = []
    pos = 0
    while pos < len(line):
        # Skip whitespace
        if line[pos] in (' ', '\t'):
            result.append(line[pos])
            pos += 1
            continue
        # Find end of token
        end = pos
        while end < len(line) and line[end] not in (' ', '\t'):
            end += 1
        token = line[pos:end]

        if token == '\\':
            break
        elif token == '(':
            close = line.find(')', end)
            if close >= 0:
                pos = close + 1
            else:
                break
            continue
        else:
            result.append(token)
            if end < len(line):
                result.append(' ')
            pos = end
            continue

    return ''.join(result).rstrip()


def is_comment_line(line):
    """Check if a line is entirely a comment."""
    return line.lstrip().startswith('\\')


def is_decimal_only_digits(token):
    """Check if token contains only decimal digits (0-9), possibly with leading minus."""
    t = token.lstrip('-')
    return bool(t) and t.isdigit()


def extract_tokens(line):
    """Extract whitespace-delimited tokens from a line, skipping comments."""
    return strip_comments(line).split()


# ---------------------------------------------------------------------------
# Check 1: Line Length
# ---------------------------------------------------------------------------

def check_line_lengths(lines, filepath):
    """Check all lines are <= 64 characters."""
    errors = []
    for i, line in enumerate(lines):
        if len(line) > SCREEN_COLS:
            errors.append({
                'file': filepath,
                'line': i + 1,
                'level': 'ERROR',
                'check': 'line-length',
                'msg': f'line is {len(line)} chars (max {SCREEN_COLS})',
                'context': line,
                'col': SCREEN_COLS,
            })
    return errors


# ---------------------------------------------------------------------------
# Check 2: BASE Tracking
# ---------------------------------------------------------------------------

def check_base_tracking(lines, filepath):
    """Track BASE state and flag suspicious literals in colon definitions.

    Only top-level HEX/DECIMAL changes are tracked. HEX/DECIMAL inside
    colon definitions are compiled (runtime), not executed (compile-time).

    Flags numeric literals inside colon defs that contain only decimal
    digits (0-9) and are > 9 when the compile-time BASE is HEX. These
    are ambiguous — the author may have intended decimal but the outer
    interpreter parses them as hex.
    """
    warnings = []
    base = 10
    in_colon = False
    colon_name = ''

    for i, line in enumerate(lines):
        if is_comment_line(line):
            continue

        tokens = extract_tokens(line)

        for j, token in enumerate(tokens):
            tok_upper = token.upper()

            if tok_upper == ':' and not in_colon:
                in_colon = True
                if j + 1 < len(tokens):
                    colon_name = tokens[j + 1]
                continue

            if tok_upper == ';' and in_colon:
                in_colon = False
                colon_name = ''
                continue

            # Only track BASE changes at top level (outside colon defs)
            if not in_colon:
                if tok_upper == 'HEX':
                    base = 16
                    continue
                if tok_upper == 'DECIMAL':
                    base = 10
                    continue

            # Inside colon def with BASE=16: flag decimal-only literals > 9
            if in_colon and base == 16:
                if is_decimal_only_digits(token):
                    val = int(token.lstrip('-'))
                    if val > 9:
                        hex_val = int(token, 16)
                        warnings.append({
                            'file': filepath,
                            'line': i + 1,
                            'level': 'WARN',
                            'check': 'base-tracking',
                            'msg': (f"literal '{token}' in :{colon_name} "
                                    f"while BASE=HEX (0x{token}={hex_val})"),
                        })

    return warnings


# ---------------------------------------------------------------------------
# Check 3: DTC Threading
# ---------------------------------------------------------------------------

def check_dtc_threading(asm_text, filepath):
    """Flag code_* references in DEFWORD bodies (should use XT/name_*)."""
    errors = []
    in_defword = False
    defword_name = ''

    for i, line in enumerate(asm_text):
        stripped = line.strip()

        m = re.match(r'^DEFWORD\s+"([^"]+)"', stripped)
        if m:
            in_defword = True
            defword_name = m.group(1)
            continue

        if in_defword and re.match(r'^(DEFCODE|DEFWORD|DEFVAR|DEFCONST)\s', stripped):
            in_defword = False
            continue

        if not in_defword:
            continue

        m = re.match(r'^\s*dd\s+(code_\w+)', stripped)
        if m:
            symbol = m.group(1)
            errors.append({
                'file': filepath,
                'line': i + 1,
                'level': 'ERROR',
                'check': 'dtc-threading',
                'msg': (f"DEFWORD '{defword_name}' uses 'dd {symbol}' "
                        f"— should use XT (dd {symbol.replace('code_', '')})"),
            })

    return errors


# ---------------------------------------------------------------------------
# Check 4: CREATE CFA
# ---------------------------------------------------------------------------

def check_create_cfa(asm_text, filepath):
    """Verify CREATE writes code_DOCREATE."""
    results = []
    in_create = False
    found_docreate = False
    create_line = 0

    for i, line in enumerate(asm_text):
        stripped = line.strip()

        if re.match(r'^DEFCODE\s+"CREATE"', stripped):
            in_create = True
            create_line = i + 1
            continue

        if in_create and re.match(r'^(DEFCODE|DEFWORD|DEFVAR|DEFCONST)\s', stripped):
            if not found_docreate:
                results.append({
                    'file': filepath,
                    'line': create_line,
                    'level': 'ERROR',
                    'check': 'create-cfa',
                    'msg': 'CREATE does not write code_DOCREATE — '
                           "variables and CREATE'd words will crash",
                })
            in_create = False
            continue

        if in_create and 'code_DOCREATE' in stripped:
            found_docreate = True

    if in_create and not found_docreate:
        results.append({
            'file': filepath,
            'line': create_line,
            'level': 'ERROR',
            'check': 'create-cfa',
            'msg': 'CREATE does not write code_DOCREATE',
        })

    return results


# ---------------------------------------------------------------------------
# Check 5: Branch Offset Validation
# ---------------------------------------------------------------------------

def check_branch_offsets(asm_text, filepath):
    """Validate hand-written DOLOOP/BRANCH offsets in DEFWORD bodies."""
    results = []
    in_defword = False
    defword_name = ''
    body = []

    DOLOOP_WORDS = {'DOLOOP', 'DOPLOOP'}
    BRANCH_WORDS = {'BRANCH', 'ZBRANCH'}

    def validate_body():
        if not body:
            return
        for idx, (line_num, sym) in enumerate(body):
            sym_upper = sym.upper() if isinstance(sym, str) else ''
            is_loop = sym_upper in DOLOOP_WORDS
            is_branch = sym_upper in BRANCH_WORDS

            if not is_loop and not is_branch:
                continue

            if idx + 1 >= len(body):
                continue
            offset_line, offset_val = body[idx + 1]
            try:
                actual_offset = int(offset_val)
            except (ValueError, TypeError):
                continue

            if actual_offset >= 0:
                continue

            if is_loop:
                target_idx = (idx + 1) + 1 + (actual_offset // 4)
            else:
                target_idx = (idx + 1) + (actual_offset // 4)

            if target_idx < 0 or target_idx >= len(body):
                results.append({
                    'file': filepath,
                    'line': offset_line,
                    'level': 'ERROR',
                    'check': 'branch-offset',
                    'msg': (f"DEFWORD '{defword_name}': {sym} offset {actual_offset} "
                            f"lands outside body (index {target_idx}, "
                            f"body has {len(body)} cells)"),
                })

    for i, line in enumerate(asm_text):
        stripped = line.strip()

        m = re.match(r'^DEFWORD\s+"([^"]+)"', stripped)
        if m:
            if in_defword:
                validate_body()
            in_defword = True
            defword_name = m.group(1)
            body = []
            continue

        if in_defword and re.match(r'^(DEFCODE|DEFWORD|DEFVAR|DEFCONST)\s', stripped):
            validate_body()
            in_defword = False
            m2 = re.match(r'^DEFWORD\s+"([^"]+)"', stripped)
            if m2:
                in_defword = True
                defword_name = m2.group(1)
                body = []
            continue

        if in_defword and re.match(r'^[A-Za-z_]\w*:', stripped):
            validate_body()
            in_defword = False
            continue

        if not in_defword:
            continue

        m = re.match(r'^\s*dd\s+(\S+)', stripped)
        if m:
            body.append((i + 1, m.group(1).rstrip(',')))

    if in_defword:
        validate_body()

    return results


# ---------------------------------------------------------------------------
# Top-level lint functions
# ---------------------------------------------------------------------------

def lint_fth_file(filepath):
    """Run vocabulary checks on a .fth file."""
    with open(filepath, 'r') as f:
        lines = f.read().splitlines()
    issues = []
    issues.extend(check_line_lengths(lines, filepath))
    issues.extend(check_base_tracking(lines, filepath))
    return issues


def lint_asm_file(filepath):
    """Run assembly checks on forth.asm."""
    with open(filepath, 'r') as f:
        lines = f.read().splitlines()
    issues = []
    issues.extend(check_dtc_threading(lines, filepath))
    issues.extend(check_create_cfa(lines, filepath))
    issues.extend(check_branch_offsets(lines, filepath))
    return issues


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def format_issue(issue):
    """Format a single issue for display."""
    parts = [f"{issue['file']}:{issue['line']}: {issue['level']} "
             f"[{issue['check']}] {issue['msg']}"]
    if 'context' in issue:
        parts.append(f"  | {issue['context']}")
        if 'col' in issue:
            parts.append(f"  | {' ' * issue['col']}^ truncated here")
    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        sys.exit(1)

    args = sys.argv[1:]
    asm_mode = False
    strict = False
    verbose = False
    files = []

    for arg in args:
        if arg == '--asm':
            asm_mode = True
        elif arg == '--strict':
            strict = True
        elif arg == '--verbose':
            verbose = True
        elif arg.startswith('-'):
            print(f"Unknown option: {arg}", file=sys.stderr)
            sys.exit(1)
        else:
            files.append(arg)

    if not files:
        print("No files specified.", file=sys.stderr)
        sys.exit(1)

    total_errors = 0
    total_warns = 0
    files_checked = 0

    for filepath in files:
        if not os.path.isfile(filepath):
            print(f"Warning: {filepath} not found, skipping", file=sys.stderr)
            continue

        issues = lint_asm_file(filepath) if asm_mode else lint_fth_file(filepath)
        files_checked += 1

        basename = os.path.basename(filepath)
        errors = [i for i in issues if i['level'] == 'ERROR']
        warns = [i for i in issues if i['level'] == 'WARN']
        total_errors += len(errors)
        total_warns += len(warns)

        # Errors always print in full
        for e in errors:
            print(format_issue(e))

        # Warnings: summary by default, detail with --verbose
        if warns and verbose:
            for w in warns:
                print(format_issue(w))

        # Status line per file
        if errors and warns:
            print(f"{basename}: {len(errors)} error(s), "
                  f"{len(warns)} BASE note(s)")
        elif errors:
            print(f"{basename}: {len(errors)} error(s)")
        elif warns:
            print(f"{basename}: OK ({len(warns)} BASE note(s)"
                  f"{'' if not verbose else ', shown above'})")
        else:
            print(f"{basename}: OK")

    # Final summary
    if total_errors or total_warns:
        print(f"\n{files_checked} files: {total_errors} error(s), "
              f"{total_warns} warning(s)")
        if total_warns and not verbose:
            print("Run with --verbose to see BASE tracking details.")

    if total_errors:
        sys.exit(1)
    if strict and total_warns:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
