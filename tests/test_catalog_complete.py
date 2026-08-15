#!/usr/bin/env python3
"""Catalog completeness gate: EVERY entry in the catalog resolves.

This is the class-closing gate for the 2026-08-13 defect where
`catalog-resolver.fth` scanned `4 CONSTANT CAT-NBLKS` catalog
blocks while `write-catalog.py` emitted `ceil(entries/15)`, by then
5.  Four vocabs -- X86-ASM, VIDEO, VGA-GRAPHICS, ZIP-READER, all
of them on catalog block 5 -- were unloadable, and the failure
presented as **"not found", not as an error**.  Nothing in the
tree asserted the invariant the bug violated, so it shipped.

Deriving the scan width from the header (the fix) closes THAT
instance.  This closes the CLASS: the next time reader and writer
disagree for some other reason, it fails here instead of silently.

DE-ALIASING -- why the name list comes from the HOST.
The enumeration is parsed out of `build/blocks.img` by
tools/catalog_layout.py; only the LOOKUP runs in Forth.  That
split is the whole point.  A Forth word that walked the catalog
itself and resolved each name it saw would be self-referential and
BLIND to exactly this bug: a reader that stops at block 4 never
sees block 5's names, so it would report all-pass while four
vocabs were unreachable.  Independent authority for the list,
code-under-test for the resolution.

FAIL-CLOSED.  An empty or unreadable catalog must not pass
vacuously -- "0 of 0 entries resolved" is literally true and
worthless.  Hence the entry-count floor, and hence the negative
control: a name that is NOT in the catalog must NOT resolve.
Without it, a CATALOG-FIND stubbed to return true always would
score a clean sweep.
"""
import hashlib
import importlib.util
import os
import socket
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

CATALOG_PY = 'tools/catalog_layout.py'
RESOLVER_FTH = 'forth/dict/catalog-resolver.fth'
BLOCKS_IMG = 'build/blocks.img'
COMBINED_IMG = 'build/combined.img'

# Floor on catalog size.  Not a pin on the exact count (that would
# fail on every vocab added); a guard against a parse that silently
# returns almost nothing and sweeps clean.  65 entries at the time
# of writing.
MIN_ENTRIES = 40

# Floor on how many entries must resolve through the BLOCK SCAN
# rather than the in-memory registry.  See the fail-closed check at
# the bottom of the sweep for why this exists.  62 of 65 at the
# time of writing (3 are CATALOG-REGISTER'd form vocabs).
MIN_BLOCK_ENTRIES = 40

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4790

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''))


# ---- self-describing log: hash the inputs BEFORE running them ----
# Any transcript quoting "Passed: N/N" must carry proof of WHICH
# bytes produced it; see tests/test_g6_chain.py for the long-form
# rationale.  Duplicated rather than factored into a shared helper
# on purpose: a suite's provenance must not depend on another file
# being importable, or the one failure mode it exists to survive
# (wrong/missing code) is the one that suppresses it.
#
# blocks.img is a declared INPUT here, not an output, because this
# suite PARSES it for the authoritative name list -- the log has to
# name the bytes that produced the enumeration, not just the ones
# that produced the answer.
_unreadable = []
for _label, _p in (('harness', os.path.abspath(__file__)),
                   ('catalog-layout', CATALOG_PY),
                   ('catalog-resolver.fth', RESOLVER_FTH),
                   ('blocks.img', BLOCKS_IMG),
                   ('combined.img', COMBINED_IMG)):
    try:
        with open(_p, 'rb') as _f:
            _h = hashlib.sha256(_f.read()).hexdigest()
    except OSError as _e:
        _h = '<UNREADABLE>'
        _unreadable.append(f'{_label} ({_p}): {_e}')
    print(f'input sha256 {_h}  {_label}')
# COUNTED (+1 to N), not a bare raise: an unreadable input must
# produce a parseable FAIL plus a "Passed: N/M" line.  A traceback
# gives a scraper nothing, which is indistinguishable from
# "never ran".
check('all declared inputs readable', not _unreadable,
      '; '.join(_unreadable))

# Hashed path and loaded path are the SAME constant, so a rename
# cannot hash one file while importing another off sys.path.
_spec = importlib.util.spec_from_file_location('catalog_layout',
                                               CATALOG_PY)
catalog_layout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(catalog_layout)

print('\nHost-side enumeration (independent authority)')
try:
    detail = catalog_layout.read_catalog_detail(BLOCKS_IMG)
    entries = catalog_layout.read_catalog(BLOCKS_IMG)
    parse_err = ''
except (OSError, ValueError) as e:
    detail = {}
    entries = {}
    parse_err = str(e)
check('catalog parses from the built image', not parse_err, parse_err)
check(f'catalog has >= {MIN_ENTRIES} entries (no vacuous sweep)',
      len(entries) >= MIN_ENTRIES, f'got {len(entries)}')
print(f'  {len(entries)} entries enumerated from {BLOCKS_IMG}')

if not entries:
    print(f'\nPassed: {PASS}/{PASS + FAIL}')
    sys.exit(1)

# ---- serial ----
s = socket.socket()
s.settimeout(10)
for _ in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except OSError:
        time.sleep(0.5)
else:
    check('serial connect', False, f'port {PORT}')
    print(f'\nPassed: {PASS}/{PASS + FAIL}')
    sys.exit(1)
time.sleep(2)
s.settimeout(2)


def drain():
    r = b''
    while True:
        try:
            d = s.recv(4096)
            if not d:
                break
            r += d
        except Exception:
            break
    return r.decode('ascii', errors='replace')


drain()


def send(cmd, wait=0.4):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    return drain()


check('system alive before sweep', '3' in send('1 2 + .', 1))
send('ALSO CATALOG-RESOLVER', 1)

# CATALOG-FIND is asymmetric TWICE OVER, and the probe has to
# model both or it reports nonsense (it did, on first run):
#
#   miss           -> ( false )              -- ONE cell, not three
#   block hit      -> ( start end true  ), CATALOG-MEM = 0
#   registry hit   -> ( addr  nblks true ), CATALOG-MEM = 1
#
# The second shape is documented at catalog-resolver.fth:244-245.
# Embedded form vocabs (NOTEPAD-FORM, HELLO-FORM,
# FILE-BROWSER-FORM) CATALOG-REGISTER their data at load time and
# resolve out of the in-memory registry, so their "block numbers"
# are a dictionary ADDRESS and a length.  Comparing those against
# the catalogued range is a category error.
#
# A probe that blindly printed three cells would also underflow on
# every miss and desynchronise the sweep, turning one real failure
# into garbage for all 65 names.  So: always three numbers, with
# -1 -1 -1 reserved for the miss (no block number is negative).
send(': CF? CATALOG-FIND IF SWAP . . CATALOG-MEM @ . '
     'ELSE -1 . -1 . -1 . THEN ;', 1)


def resolve(name):
    """( first, last, from_memory ) as the MACHINE resolves it.

    Returns None for an unresolvable name.
    """
    raw = send(f'S" {name}" CF?', 0.35)
    nums = []
    for tok in raw.replace('\r', ' ').replace('\n', ' ').split():
        try:
            nums.append(int(tok))
        except ValueError:
            pass
    # The echo contains the name, not digits, but a vocab name can
    # contain them (X86-ASM, RTL8168) -- so take the LAST three
    # integers, which are CF?'s output, never the echo's.
    if len(nums) < 3:
        return None
    a, b, mem = nums[-3], nums[-2], nums[-1]
    return None if (a, b, mem) == (-1, -1, -1) else (a, b, bool(mem))


print('\nNegative control (CATALOG-FIND must be able to say no)')
bogus = 'ZZ-NO-SUCH-VOCAB'
check(f'absent name does not resolve ({bogus})',
      resolve(bogus) is None,
      'CATALOG-FIND resolved a name that is not in the catalog -- '
      'a clean sweep below would prove nothing')

print(f'\nSweep: CATALOG-FIND every one of {len(entries)} entries')
missing = []
mismatched = []
via_blocks = 0
for name, (first, last, catblk) in sorted(detail.items()):
    got = resolve(name)
    if got is None:
        missing.append(f'{name} (catalog block {catblk})')
        continue
    a, b, from_mem = got
    if from_mem:
        continue            # registry hit: addr/len, not a range
    via_blocks += 1
    if (a, b) != (first, last):
        mismatched.append(f'{name}: catalog {first} {last}, '
                          f'machine {a} {b}')

# THE invariant the CAT-NBLKS bug violated.  One assertion, because
# it is one property; the detail names the offenders AND the
# catalog block they sit on, so a red run points at the truncation
# point rather than just at a count.
check('every catalog entry resolves', not missing,
      f'{len(missing)} unresolvable: {", ".join(missing[:8])}'
      + (' ...' if len(missing) > 8 else ''))
check('every block-resolved entry matches the catalogued range',
      not mismatched, '; '.join(mismatched[:4]))

# FAIL-CLOSED against this gate rotting into vacuity.  The in-memory
# registry is searched FIRST, so a registry hit never exercises the
# block scan at all -- the thing that broke.  If enough entries
# migrated to CATALOG-REGISTER, "every entry resolves" could go
# green with the scan-width defect fully intact.  Assert that the
# block path is still carrying the sweep.
check(f'block scan still exercised (>= {MIN_BLOCK_ENTRIES} entries '
      f'resolved via blocks, not the registry)',
      via_blocks >= MIN_BLOCK_ENTRIES,
      f'only {via_blocks} of {len(detail)} came from catalog blocks')

# The scan-width bug made the TAIL of the catalog unreachable, so
# reaching the last block is the specific property that regressed.
# Stated separately from "every entry resolves" because it is the
# one that localises a future failure to the same cause.
last_blk = max(v[2] for v in detail.values())
tail = sorted(n for n, v in detail.items() if v[2] == last_blk)
tail_missing = [n for n in tail
                if any(m.startswith(n + ' ') for m in missing)]
check(f'entries on the LAST catalog block ({last_blk}) resolve '
      f'-- {len(tail)} entries, incl. {tail[-1]}',
      not tail_missing, ', '.join(tail_missing))

check('system alive after sweep', '3' in send('1 2 + .', 1))
check('stack clean after sweep', '<>' in send('.S', 1))

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(1 if FAIL else 0)
