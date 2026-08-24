#!/usr/bin/env python3
"""Doc drift gate — documents someone TYPES FROM must match the artifact.

DRAFT 2026-08-19. Two gates, both born from real defects:

  Gate A (grub.cfg transcription).  On 2026-08-19 a correction to
  docs/TASK_INSTALL_BOOT_ENTRY.md replaced a stale chainload menuentry
  with a HAND-RETYPED copy of the shipped one that differed in three
  ways -- missing `insmod regexp`, `sleep 10` vs `sleep 5`, and most
  seriously an INVERTED guard: `if [ -z "$found" ]; then echo...; fi`
  followed by an UNCONDITIONAL `chainloader +1`, where the shipped entry
  chainloads only inside the found-branch.  The shipped form fails
  closed on a miss; the retyped form prints the error and then chainloads
  whatever `root` happens to be.  tests/test_grub_cfg.py already gates
  "chainloader only inside found-guard" -- on the GENERATED file.  Nothing
  gated the copy in the doc.

  Gate B (runbook typed sequence).  Finding F1: RUNBOOK-G6.md's section
  3e -- the operator's literal keystrokes -- had drifted from the green
  harness in stack discipline and word order.  Every other typed block
  in that runbook cites its source line range; that convention is only a
  defense if something checks it.

Design rules, following the project's existing gate idiom:

  * FAIL CLOSED on ambiguity.  Zero matches is a failure, not a pass --
    the same rule gen-grub-cfg.py's install.fth scan uses (fatal on 0
    hits AND on >1 hits).  A gate that silently finds nothing to check
    reads as green forever.
  * ATTRIBUTE, don't just detect.  Each failure names which store
    disagreed with which authority.
  * ANCHOR EXPLICITLY.  Gate B needs two marker comments added to
    tests/test_g6_chain.py (see RUNBOOK_3E_BEGIN/END below).  A
    heuristic that guesses the region would eventually guess wrong and
    compare the runbook against the wrong lines -- worse than no gate.

Run: python3 tests/test_doc_drift.py    (prints the standard Passed: n/n)
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return f.read()


# ===================================================================
# Gate A -- no doc may carry an unmarked copy of the chainload entry
# ===================================================================
#
# Marker convention, required on every doc copy:
#
#   SHIPPED-VERBATIM  -> the block MUST be byte-equal (after unquoting
#                        and whitespace normalisation) to the menuentry
#                        in tools/pxe/grub.cfg
#   SUPERSEDED        -> the block MUST NOT be equal; it is preserved
#                        history and a marker that has become true is a
#                        marker that is now lying
#
# A block with neither marker fails.  That is the point: the failure
# mode being gated is someone pasting a menuentry into prose without
# saying which kind it is.

GRUB_CFG = 'tools/pxe/grub.cfg'
DOCS_TO_SCAN = [
    'tools/pxe/RUNBOOK-G6.md',
    'docs/TASK_INSTALL_BOOT_ENTRY.md',
    'docs/superpowers/specs/2026-08-05-g6-chain-design.md',
    'README.md',
]

MENUENTRY_RE = re.compile(
    r'menuentry\s+"ForthOS \(installed to disk\)"\s*\{.*?\n[>\s~]*\}',
    re.DOTALL)


def normalise(block):
    """Strip markdown quoting and collapse whitespace, so a block
    indented into a blockquote still compares equal to the artifact."""
    out = []
    for line in block.splitlines():
        line = re.sub(r'^\s*>\s?', '', line)      # blockquote prefix
        line = line.replace('~~', '')             # strikethrough
        line = ' '.join(line.split())             # collapse runs
        if line:
            out.append(line)
    return '\n'.join(out)


def gate_a():
    print('Gate A: chainload menuentry copies in prose')
    cfg = read(GRUB_CFG)
    shipped = MENUENTRY_RE.search(cfg)
    if not shipped:
        check('authority: menuentry found in tools/pxe/grub.cfg', False,
              'regenerate with `make grub-net` or fix this gate')
        return
    check('authority: menuentry found in tools/pxe/grub.cfg', True)
    shipped_n = normalise(shipped.group(0))

    total = 0
    for rel in DOCS_TO_SCAN:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            # Tier/gitignore reality: some of these live only in the
            # private tree.  Absent is fine; SILENTLY absent is not.
            print(f'  note: {rel} not present in this checkout (tier)')
            continue
        text = read(rel)
        for m in MENUENTRY_RE.finditer(text):
            total += 1
            block = m.group(0)
            # Look back up to 6 lines for the marker.
            head = text[:m.start()].splitlines()[-6:]
            context = '\n'.join(head)
            verbatim = 'SHIPPED-VERBATIM' in context
            superseded = 'SUPERSEDED' in context
            where = f'{rel}:{text[:m.start()].count(chr(10)) + 1}'

            check(f'{where} carries exactly one marker',
                  verbatim ^ superseded,
                  'need SHIPPED-VERBATIM or SUPERSEDED (not both, not '
                  'neither) within 6 lines above the block')
            if verbatim:
                check(f'{where} SHIPPED-VERBATIM matches grub.cfg',
                      normalise(block) == shipped_n,
                      'doc copy differs from the generated artifact')
            elif superseded:
                check(f'{where} SUPERSEDED really differs',
                      normalise(block) != shipped_n,
                      'marked superseded but identical to shipped -- '
                      'the marker is now false')

    # Fail closed: finding nothing means the regex rotted, not that
    # every doc is clean.
    check('gate A found at least one doc copy to check', total > 0,
          'zero menuentry blocks found in any scanned doc -- the '
          'MENUENTRY_RE or DOCS_TO_SCAN list has gone stale')

    # Counting assertion: a block matcher that swallows two entries as
    # one match passes all marker checks but silently drops coverage.
    # Count raw declarations independently of the block matcher.
    DECL_RE = re.compile(
        r'menuentry\s+"ForthOS \(installed to disk\)"')
    for rel in DOCS_TO_SCAN:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        text = read(rel)
        declared = len(DECL_RE.findall(text))
        matched = len(MENUENTRY_RE.findall(text))
        if declared > 0:
            check(f'{rel}: every menuentry block terminated',
                  declared == matched,
                  f'{declared} declared vs {matched} matched -- a block '
                  'ran past its closing brace and swallowed the next')


# ===================================================================
# Gate B -- RUNBOOK-G6.md 3e must equal what the harness types
# ===================================================================
#
# REQUIRES two marker comments in tests/test_g6_chain.py bracketing the
# stage-2 install sequence:
#
#     # --8<-- RUNBOOK-3E-BEGIN
#     ...expect(...)/send(...) calls...
#     # --8<-- RUNBOOK-3E-END
#
# Add them at the flag-checked LBA 0 probe and after the DEPTH check.

HARNESS = 'tests/test_g6_chain.py'
RUNBOOK = 'tools/pxe/RUNBOOK-G6.md'

BEGIN = '# --8<-- RUNBOOK-3E-BEGIN'
END = '# --8<-- RUNBOOK-3E-END'
BEGIN_3A = '# --8<-- RUNBOOK-3A-BEGIN'
END_3A = '# --8<-- RUNBOOK-3A-END'

# expect(name, expr, want, ...) -> expr is the typed expression.
EXPECT_RE = re.compile(r"expect\(\s*'[^']*'\s*,\s*'([^']*)'")
# val('expr') -> wraps as 'DECIMAL expr .', so the typed expression
# is the argument; it appears on the stack as a consumed value.
VAL_RE = re.compile(r"val\(\s*'([^']*)'")
# send('CMD', wait) -> typed verbatim, no trailing '.'
SEND_RE = re.compile(r"send\(\s*'([^']*)'")
# send(f'CMD {a} ...', wait) -> typed verbatim with Python-derived
# fields.  Gate B (3e) deliberately EXCLUDES f-sends (the ESP pokes
# are fixture-derived and the runbook derives them differently);
# gate B-3a must PARSE them, because its one f-send -- the catalog
# range THRU -- is exactly the line being gated.  The counting
# backstop forces this: an unparsed f-send is a raw-count mismatch.
FSEND_RE = re.compile(r"send\(\s*f'([^']*)'")


# Independent call-site counter for the gate B counting backstop.
# Must NOT share machinery with the per-line parser — the whole point
# is to catch cases where the joiner or per-line parse drops a call.
# Counts expect/val/send — the three forms that produce typed Forth.
# Does NOT count fatal/print/close_ch/qemu_kill — those are harness
# scaffolding the operator never types.
CALL_SITE_RE = re.compile(r'\b(?:expect|val|send)\(')


def harness_sequence(begin=BEGIN, end=END, fstrings=False):
    text = read(HARNESS)
    if begin not in text or end not in text:
        return None
    region = text.split(begin, 1)[1].split(end, 1)[0]

    # Count raw call sites BEFORE any joining or parsing, so the
    # counting assertion is independent of the joiner.
    raw_call_count = len(CALL_SITE_RE.findall(region))

    # Join continuation lines: Python calls can span multiple lines.
    # Collapse lines that start with whitespace (continuation) into
    # the preceding line so the regex sees the full call.
    raw_lines = region.splitlines()
    joined = []
    for line in raw_lines:
        if joined and line and line[0] in ' \t' and not line.lstrip().startswith('#'):
            joined[-1] += ' ' + line.strip()
        else:
            joined.append(line)
    seq = []
    for line in joined:
        # Lines with '# runbook-exempt:' are harness scaffolding the
        # operator never types (liveness probes, Python-side extractions).
        # The reason after the colon is mandatory — a bare exempt is a
        # gate someone turned off without saying why.
        if '# runbook-exempt:' in line:
            reason = line.split('# runbook-exempt:', 1)[1].strip()
            check('exemption states a reason', bool(reason),
                  f'bare exemption on: {line.strip()[:70]}')
            n = len(CALL_SITE_RE.findall(line))
            check('exempt line carries exactly one call', n == 1,
                  f'{n} call sites on one exempt line -- split them')
            raw_call_count -= n
            continue
        m = EXPECT_RE.search(line)
        if m:
            seq.append(('expr', m.group(1).strip()))
            continue
        m = VAL_RE.search(line)
        if m:
            # val() sends 'DECIMAL <expr> .' — same as a consumed expr
            seq.append(('expr', m.group(1).strip()))
            continue
        if fstrings:
            m = FSEND_RE.search(line)
            if m:
                seq.append(('bare', m.group(1).strip()))
                continue
        m = SEND_RE.search(line)
        if m and not m.group(1).startswith(':'):
            # f-strings (ESP pokes) and colon definitions are excluded
            # unless fstrings=True: in 3e they are fixture-derived; in
            # 3a the f-send IS the gated line.  Colon definitions are
            # helper defs either way.
            seq.append(('bare', m.group(1).strip()))
    return seq, raw_call_count


def runbook_sequence():
    text = read(RUNBOOK)
    m = re.search(r'^### 3e\..*?^```forth\n(.*?)^```',
                  text, re.DOTALL | re.MULTILINE)
    if not m:
        return None
    seq = []
    for line in m.group(1).splitlines():
        line = re.sub(r'\\.*$', '', line).strip()   # drop \ comments
        # Standalone DECIMAL KEPT as of 2026-08-23. The skip was
        # 3e-specific -- the 3a parser keeps every non-empty line,
        # and gate B-3a has been green comparing 3a's two DECIMAL
        # tokens all along -- so the two parsers were silently
        # divergent, and 3e's opening DECIMAL (a typed operator
        # step) was invisible to the gate protecting typed steps.
        # This ends the inconsistency; the harness types both 3e
        # DECIMALs non-exempt so the sides stay symmetric.
        if not line:
            continue
        if line.endswith(' .'):
            seq.append(('expr', line[:-2].strip()))
        else:
            seq.append(('bare', line))
    return seq


def gate_b():
    print('Gate B: RUNBOOK-G6.md 3e vs the green harness')
    result = harness_sequence()
    rs = runbook_sequence()

    if result is None:
        check('harness carries RUNBOOK-3E markers', False,
              f'add {BEGIN} / {END} around the stage-2 install calls in '
              f'{HARNESS}')
        return
    hs, raw_call_count = result
    check('harness carries RUNBOOK-3E markers', True)

    if rs is None:
        check('runbook 3e forth block located', False,
              'no ```forth block under "### 3e." -- section renamed?')
        return
    check('runbook 3e forth block located', True)

    check('gate B has a non-empty sequence to compare',
          len(hs) > 0 and len(rs) > 0, f'harness={len(hs)} runbook={len(rs)}')

    # Counting backstop: the continuation-line joiner and per-line
    # parser can silently drop calls (two calls glued onto one line,
    # unrecognised call form).  Count raw call sites independently.
    check('gate B parsed every call in the region',
          raw_call_count == len(hs),
          f'{raw_call_count} call sites vs {len(hs)} parsed -- the '
          'continuation joiner collapsed two calls onto one line, or '
          'a call form is unrecognised')

    # Compare pairwise so the FIRST divergence is named, rather than
    # dumping two lists and making a human diff them at 1am.
    for i in range(max(len(hs), len(rs))):
        h = hs[i] if i < len(hs) else None
        r = rs[i] if i < len(rs) else None
        if h == r:
            continue
        check(f'step {i + 1} agrees', False,
              f'harness={h!r} runbook={r!r}')
        return
    check(f'all {len(rs)} typed steps agree, in order', True)

    # The specific F1 invariants, asserted by name so a regression is
    # attributable rather than just "step 9 differs".
    words = [e for _, e in rs]
    try:
        i_arm = next(i for i, w in enumerate(words) if w == 'GPT-ARM')
        i_moe = next(i for i, w in enumerate(words)
                     if w.startswith('MAKE-OWN-ENT'))
        check('F1: GPT-ARM precedes MAKE-OWN-ENT', i_arm < i_moe,
              'the old order hands GPT-ARM\'s flag to ADD-PARTITION '
              'as its entry pointer')
    except StopIteration:
        check('F1: both GPT-ARM and MAKE-OWN-ENT present', False)

    check('F1: MAKE-OWN-ENT probes a COPY of its flag',
          any(w.startswith('MAKE-OWN-ENT') and 'DUP 0= 0=' in w
              for w in words),
          'bare "MAKE-OWN-ENT ." consumes the entry address')

    check('F1: no bare -1 sanity line',
          not any(w.strip() == '-1' for w in words),
          'prints a literal and proves nothing; ADD-BOOT-ENTRY . belongs '
          'in that slot')


# ===================================================================
# Gate B-3a -- RUNBOOK-G6.md 3a must equal what the harness types
# ===================================================================
#
# Born 2026-08-20, the day the THRU-before-AHCI-INIT mechanism was
# confirmed as BASE stickiness: 3a became the second typed block with
# a cited source, its first line grew a load-bearing DECIMAL, and
# nothing gated it.  A marker that promises a gate with no gate behind
# it is FREE-SLOT's shape (comments asserting callers it didn't have),
# so the 3A markers and this gate land in the same commit.
#
# NOT a copy of gate B: the harness sends 'DECIMAL 575 653 THRU' with
# session-derived numbers; the runbook necessarily writes
# 'DECIMAL <first> <last> THRU' because the numbers come off the desk
# generator against THAT session's blocks.img.  A literal compare
# fails on a correct doc.  Normalisation rule: collapse ONLY tokens
# that are f-string fields ({a}), doc placeholders (<first>), or bare
# integers to '#'.  Word tokens still compare exactly -- the rule must
# not be able to bless 'USING AHCI' vs 'USING INSTALL'.

PLACEHOLDER_RE = re.compile(r'\{[^}]*\}|<[^>]*>|^\d+$')


def norm_3a(typed):
    return ' '.join('#' if PLACEHOLDER_RE.fullmatch(t) else t
                    for t in typed.split())


def runbook_3a_sequence():
    text = read(RUNBOOK)
    m = re.search(r'^### 3a\..*?^```forth\n(.*?)^```',
                  text, re.DOTALL | re.MULTILINE)
    if not m:
        return None
    seq = []
    for line in m.group(1).splitlines():
        line = re.sub(r'\\.*$', '', line).strip()   # drop \ comments
        # A standalone or leading DECIMAL is KEPT: the DECIMAL is
        # payload this gate exists to protect. (The 3e parser
        # dropped bare DECIMAL until 2026-08-23; both now agree.)
        if not line:
            continue
        seq.append(('bare', line))
    return seq


def gate_b_3a():
    print('Gate B-3a: RUNBOOK-G6.md 3a vs the green harness')
    result = harness_sequence(BEGIN_3A, END_3A, fstrings=True)
    rs = runbook_3a_sequence()

    if result is None:
        check('harness carries RUNBOOK-3A markers', False,
              f'add {BEGIN_3A} / {END_3A} around the load-and-init '
              f'sends in {HARNESS}')
        return
    hs, raw_call_count = result
    check('harness carries RUNBOOK-3A markers', True)

    if rs is None:
        check('runbook 3a forth block located', False,
              'no ```forth block under "### 3a." -- section renamed?')
        return
    check('runbook 3a forth block located', True)

    check('gate B-3a has a non-empty sequence to compare',
          len(hs) > 0 and len(rs) > 0,
          f'harness={len(hs)} runbook={len(rs)}')

    check('gate B-3a parsed every call in the region',
          raw_call_count == len(hs),
          f'{raw_call_count} call sites vs {len(hs)} parsed -- the '
          'continuation joiner collapsed two calls onto one line, or '
          'a call form is unrecognised')

    hn = [(k, norm_3a(e)) for k, e in hs]
    rn = [(k, norm_3a(e)) for k, e in rs]
    for i in range(max(len(hn), len(rn))):
        h = hn[i] if i < len(hn) else None
        r = rn[i] if i < len(rn) else None
        if h == r:
            continue
        check(f'step {i + 1} agrees', False,
              f'harness={h!r} runbook={r!r}')
        return
    check(f'all {len(rn)} typed steps agree, in order', True)

    # The specific invariants, asserted by name so a regression is
    # attributable rather than just "step N differs".
    words = [e for _, e in rn]
    first = words[0] if words else ''
    check('BASE: first typed line is DECIMAL-prefixed THRU',
          first.startswith('DECIMAL ') and first.endswith(' THRU'),
          'confirmed 2026-08-20: AHCI-INIT leaves BASE=16 and boot '
          'base on the GRUB-memdisk path is HEX; a bare range '
          'misparses into the metacompiler TARGET blocks')
    try:
        i_thru = next(i for i, w in enumerate(words)
                      if w.endswith('THRU'))
        i_init = next(i for i, w in enumerate(words)
                      if w == 'AHCI-INIT')
        check('THRU precedes AHCI-INIT (order kept as typed)',
              i_thru < i_init,
              'ordering is retired as MECHANISM, kept as the typed '
              'sequence; the doc has no authority to differ from the '
              'harness')
    except StopIteration:
        check('both THRU and AHCI-INIT present', False)
    try:
        i_also = next(i for i, w in enumerate(words)
                      if w == 'ALSO SURVEYOR')
        i_using = next(i for i, w in enumerate(words)
                       if w == 'USING INSTALL')
        check('DOVOC trap: ALSO SURVEYOR precedes USING INSTALL',
              i_also < i_using,
              'USING replaces the top of the search order; an ALSO '
              'issued after it is lost')
    except StopIteration:
        check('both ALSO SURVEYOR and USING INSTALL present', False)


if __name__ == '__main__':
    gate_a()
    print()
    gate_b()
    print()
    gate_b_3a()
    print(f'\nPassed: {PASS}/{PASS + FAIL}')
    sys.exit(0 if FAIL == 0 else 1)
