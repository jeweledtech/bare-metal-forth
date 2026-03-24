#!/usr/bin/env python3
"""
embed-vocabs.py — Strip comments from .fth files and produce a NUL-terminated
binary blob suitable for embedding in the kernel.

Strips:
  - backslash comment lines (to end of line)
  - parenthesized comment blocks (inline stack effects)
  - Newlines → spaces
  - Multiple spaces → single space

The output is a compact Forth token stream that the kernel's INTERPRET
can evaluate directly. No block-format structure needed.

Usage:
    python3 tools/embed-vocabs.py output.bin file1.fth file2.fth ...
"""

import sys
import re


# Standalone init calls to strip from embedded source.
# These are lines that consist of ONLY this word (no colon def).
# CALIBRATE-DELAY hangs on some real hardware; print messages are noise.
STRIP_INIT_CALLS = {'HARDWARE-INIT', 'PM-INFO'}


def strip_comments(source):
    """Strip comments and standalone init calls from Forth source."""
    lines = source.split('\n')
    result_lines = []

    for line in lines:
        stripped = line.strip()

        # Skip standalone auto-init calls (but keep colon defs like ": HARDWARE-INIT")
        if stripped in STRIP_INIT_CALLS:
            continue

        # Skip pure \ comment lines
        stripped = line.lstrip()
        if stripped.startswith('\\'):
            continue

        # Remove trailing \ comments (not inside ." strings)
        # Find \ that isn't inside a string
        out = []
        i = 0
        in_dot_quote = False
        in_s_quote = False
        while i < len(line):
            # Check for ." (dot-quote string start)
            if not in_dot_quote and not in_s_quote:
                if line[i:i+2] == '."':
                    out.append('."')
                    i += 2
                    in_dot_quote = True
                    continue
                if line[i:i+2] == 'S"' or line[i:i+2] == 's"':
                    out.append(line[i:i+2])
                    i += 2
                    in_s_quote = True
                    continue
                # Check for \ comment (must have space before or be at start)
                if line[i] == '\\' and (i == 0 or line[i-1] == ' ' or line[i-1] == '\t'):
                    break  # Rest of line is comment
                # Check for ( comment
                if line[i] == '(' and (i == 0 or line[i-1] == ' ' or line[i-1] == '\t'):
                    # Find matching )
                    j = line.find(')', i + 1)
                    if j >= 0:
                        i = j + 1
                        continue
                    else:
                        break  # Unclosed ( — skip rest of line
            elif in_dot_quote:
                if line[i] == '"':
                    in_dot_quote = False
                out.append(line[i])
                i += 1
                continue
            elif in_s_quote:
                if line[i] == '"':
                    in_s_quote = False
                out.append(line[i])
                i += 1
                continue

            out.append(line[i])
            i += 1

        result = ''.join(out).rstrip()
        if result:
            result_lines.append(result)

    return ' '.join(result_lines)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    output_file = sys.argv[1]
    input_files = sys.argv[2:]

    all_tokens = []
    for fpath in input_files:
        with open(fpath, 'r') as f:
            source = f.read()
        tokens = strip_comments(source)
        if tokens:
            all_tokens.append(tokens)

    combined = ' '.join(all_tokens)

    # Collapse multiple spaces
    combined = re.sub(r'  +', ' ', combined).strip()

    # Write as NUL-terminated binary
    data = combined.encode('ascii') + b'\x00'

    with open(output_file, 'wb') as f:
        f.write(data)

    print(f"Embedded vocab binary: {output_file}")
    print(f"  Input files: {', '.join(input_files)}")
    print(f"  Token stream: {len(combined)} bytes")
    print(f"  Output (with NUL): {len(data)} bytes")


if __name__ == '__main__':
    main()
