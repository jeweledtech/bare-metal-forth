"""Single home for kernel `equ` parsing shared by the test suites.

Exists because two suites (test_dict_bounds.py, test_squote_laydown.py)
grew identical regexes over the same two constants -- a second
implementation of the same knowledge, the drift species this arc
kept meeting (Makefile EMBED_VOCABS vs the snapshot script's sed;
a hardcoded 1024 margin going stale against a 2048 kernel).  The
parse lives once, here; suites import values and call the gate.

History that earns the gate (check_backstop_derivation): a
--backstop0 fixture value (`equ 0`) reached commit 9ae68d5 while
the comment three lines above it and the commit message both said
2048 -- third instance of the VBR-TPL species (a fixture standing
where the production value should be, upstream of every assertion
that would catch its absence).  A constant whose only check is a
human reading two adjacent lines is what the gate replaces.

Import is fail-closed: unparseable source stops every suite,
including --backstop0 runs.  Since the %define/%ifndef rework, the
SOURCE always reads the shipping value -- the only override path
is the build line (-DDICT_BACKSTOP=0, make backstop0) -- so the
three-way gate in check_backstop_derivation() holds in every mode,
--backstop0 included.  What the gate cannot see is which IMAGE the
caller booted; that is proven at runtime by the laydown suite's
mode/image probe (a definition parked inside the would-be margin
compiles only if the booted kernel truly has no backstop).
"""
import os
import re
import sys

# Resolved against this file, not the cwd: as a shared import this
# would otherwise quietly make "runs only from the repo root" a
# dependency of every suite, and the failure would be a bare
# FileNotFoundError instead of a named refusal.
ASM = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', 'src', 'kernel', 'forth.asm'))


def _fail(msg):
    print('FAIL: ' + msg)
    sys.exit(1)


try:
    _src = open(ASM).read()
except OSError as e:
    _fail(f'cannot read kernel source {ASM}: {e}')
# %define, not equ: the default lives behind %ifndef so the build
# line (-DDICT_BACKSTOP=0, make backstop0) is the ONLY override
# path -- a hand-edited source value is what reached 9ae68d5.
# Parens are load-bearing in the match: %define is textual
# substitution, so the source must read (2048); a bare value here
# would hide an unparenthesized define.
_def = re.search(r'^%define\s+DICT_BACKSTOP\s+\((\d+)\)\s*$', _src, re.M)
_der = re.search(r'DICT_BACKSTOP-DERIVATION:\s*(\d+)\s*=\s*(\d+)'
                 r'\s*bound\s*\+\s*(\d+)\s*slack', _src)
_blk = re.search(r'^BLOCK_SIZE\s+equ\s+(\d+)', _src, re.M)
if not _def or not _der or not _blk:
    _fail('could not parse the DICT_BACKSTOP %define (parenthesized, '
          'behind %ifndef), the DICT_BACKSTOP-DERIVATION marker line, '
          f'or BLOCK_SIZE equ from {ASM} (the marker phrasing is '
          'load-bearing -- restore it, do not relax this regex)')

DICT_BACKSTOP = int(_def.group(1))
BLOCK_SIZE = int(_blk.group(1))

# Block buffer pool bounds -- load-bearing for STR_SOURCE_CAP since
# the VAR_BLK phase-pun fix (6a2c64d): the macro classifies "block
# source" by VAR_TIB in [BLK_BUF_DATA, BLK_BUF_GUARD).  The macro
# uses the SYMBOLS, so the drift that matters is the allocator's:
# if the pool moves, grows, or gains a fifth buffer and
# BLK_BUF_GUARD is not moved with it, addresses in the new buffers
# classify as interactive -- cap 0x7FFFFFFF, unbounded laydown
# back, suite green.  Parse is fail-closed like everything above.
_pd = re.search(r'^BLK_BUF_DATA\s+equ\s+0x([0-9A-Fa-f]+)', _src, re.M)
_pg = re.search(r'^BLK_BUF_GUARD\s+equ\s+0x([0-9A-Fa-f]+)', _src, re.M)
_pn = re.search(r'^BLK_NUM_BUFFERS\s+equ\s+(\d+)', _src, re.M)
if not _pd or not _pg or not _pn:
    _fail('could not parse BLK_BUF_DATA / BLK_BUF_GUARD / '
          f'BLK_NUM_BUFFERS equs from {ASM}')
BLK_BUF_DATA = int(_pd.group(1), 16)
BLK_BUF_GUARD = int(_pg.group(1), 16)
BLK_NUM_BUFFERS = int(_pn.group(1))
DERIV_TOTAL, DERIV_BOUND, DERIV_SLACK = (int(g) for g in _der.groups())
# Worst single-token laydown, derived the same way the kernel
# comment derives it: BLOCK_SIZE source cap + 4 ((S") XT) + 4
# (length cell) + 3 (align) + 4 (trailing XT).  Spelled out, not
# 15: a literal would be one more number that agrees with nothing.
BOUND = BLOCK_SIZE + 4 + 4 + 3 + 4


def check_backstop_derivation():
    """Three-way gate: the %define value, the marker line's own
    arithmetic, and the bound re-derived from BLOCK_SIZE must all
    agree, and zero is refused by name.  Runs in every mode
    (--backstop0 included): the source always reads the shipping
    value, so a refusal here means the source was hand-edited --
    the exact event this gate exists to catch.  Which IMAGE the
    caller booted is a separate question, proven at runtime by the
    laydown suite's probe."""
    if DERIV_BOUND != BOUND:
        _fail(f'DICT_BACKSTOP bound drift -- comment says '
              f'{DERIV_BOUND}, BLOCK_SIZE + 4+4+3+4 derives {BOUND}')
    if DICT_BACKSTOP == 0:
        # Not drift -- a fixture that reached a commit (see module
        # docstring).  Distinct failure, distinct fix: restore the
        # derived value, never relax this branch.
        _fail('DICT_BACKSTOP is 0 -- the --backstop0 fixture value, '
              'never shippable (throwaway-build state reached the '
              'tree)')
    if not (DICT_BACKSTOP == DERIV_TOTAL == DERIV_BOUND + DERIV_SLACK):
        _fail(f'DICT_BACKSTOP drift -- equ {DICT_BACKSTOP}, comment '
              f'derives {DERIV_TOTAL} = {DERIV_BOUND} + {DERIV_SLACK}')


HARDWARE_FTH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', 'forth', 'dict', 'hardware.fth'))


def _fth_const(src, name):
    """Parse `<hex> CONSTANT <name>` from a .fth source, allowing
    an ordinary trailing `\\ comment`.  The file is HEX from its
    preamble, so the literal is base-16 with no 0x prefix -- a
    decimal int() here would silently misread 300 as three hundred
    instead of 768, the HEX/DECIMAL trap (bug #20) reproduced
    inside the gate built to prevent drift."""
    m = re.search(r'^([0-9A-F]+) CONSTANT ' + re.escape(name)
                  + r'(?:\s+\\.*)?\s*$', src, re.M)
    return int(m.group(1), 16) if m else None


def check_phys_table():
    """Owner-table sizing gate (Task B, 2026-08-31).  Same shape as
    check_backstop_derivation: a derived, load-bearing, invisible-
    if-drifted number, machine-checked against its own derivation
    three ways.  The capacity claim 'hot-plug cannot grow the
    table' holds only if capacity >= max possible live allocations;
    if OWN-CAP were a chosen literal, many small allocations could
    exhaust the table while pages remain free, and table-full would
    stop being a backstop.  NOTE the base: capacity is derived from
    the pool ORIGIN (0x100000), not the post-carve POOL-BASE -- the
    carve leaves fewer allocatable pages, so the spare entries are
    rounding slack on the safe side.

    Also gates: the FORTH-CELL sentinel (unattributed-allocation
    detection) against the kernel's VAR_FORTH_LATEST equ -- identity,
    not coincidence -- and the DMA-ALLOC ISA delegation claim
    PHYS-TOP <= 0x1000000 as arithmetic, not prose."""
    try:
        fsrc = open(HARDWARE_FTH).read()
    except OSError as e:
        _fail(f'cannot read {HARDWARE_FTH}: {e}')
    origin = _fth_const(fsrc, 'POOL-ORIGIN')
    top = _fth_const(fsrc, 'PHYS-TOP')
    cap = _fth_const(fsrc, 'OWN-CAP')
    rec = _fth_const(fsrc, 'OWN-REC')
    tbytes = _fth_const(fsrc, 'OWN-BYTES')
    fcell = _fth_const(fsrc, 'FORTH-CELL')
    if None in (origin, top, cap, rec, tbytes, fcell):
        _fail('could not parse POOL-ORIGIN / PHYS-TOP / OWN-CAP / '
              f'OWN-REC / OWN-BYTES / FORTH-CELL constants from '
              f'{HARDWARE_FTH} (hex literals, optional trailing '
              '\\ comment -- restore the constants, do not relax '
              'this regex)')
    page = 0x1000
    if rec != 3 * 4:
        _fail(f'owner-record shape drift -- OWN-REC 0x{rec:X} != '
              f'3 cells (base, size, tag); if the record grew a '
              f'field, this gate\'s field count must grow with it '
              f'CONSCIOUSLY, not silently validate the old size')
    if cap * page < top - origin:
        _fail(f'owner-table capacity drift -- OWN-CAP 0x{cap:X} * '
              f'page < pool 0x{top - origin:X} from ORIGIN; a full '
              f'pool can outrun the table and table-full stops '
              f'being a backstop')
    if tbytes != ((cap * rec + page - 1) // page) * page:
        _fail(f'owner-table carve drift -- OWN-BYTES 0x{tbytes:X} != '
              f'page-rounded OWN-CAP*OWN-REC = '
              f'0x{((cap * rec + page - 1) // page) * page:X}')
    if not re.search(r'^POOL-ORIGIN OWN-BYTES \+ CONSTANT POOL-BASE'
                     r'(?:\s+\\.*)?\s*$', fsrc, re.M):
        _fail('POOL-BASE is not derived as POOL-ORIGIN OWN-BYTES + '
              '-- a literal or moved base can overlap the first '
              'allocation with the table; derivation by the SYMBOLS '
              'is what makes overlap impossible by identity')
    _fl = re.search(r'^VAR_FORTH_LATEST\s+equ\s+0x([0-9A-Fa-f]+)',
                    _src, re.M)
    if not _fl:
        _fail(f'could not parse VAR_FORTH_LATEST equ from {ASM}')
    if fcell != int(_fl.group(1), 16):
        _fail(f'FORTH-CELL sentinel drift -- hardware.fth says '
              f'0x{fcell:X}, kernel VAR_FORTH_LATEST equ is '
              f'0x{int(_fl.group(1), 16):X}; unattributed detection '
              f'now compares against the wrong cell and every '
              f'run-time allocation reads as attributed')
    if top > 0x1000000:
        _fail(f'DMA-ALLOC delegation broken -- PHYS-TOP 0x{top:X} > '
              f'16MB ISA limit 0x1000000; DMA-ALLOC = PHYS-ALLOC '
              f'only holds below that line (the comment saying so '
              f'is now a lie)')


def check_pool_bounds():
    """STR_SOURCE_CAP pool gate (follow-on named in 6a2c64d).  The
    invariant is the RELATIONSHIP, not the values: BLK_BUF_GUARD ==
    BLK_BUF_DATA + BLK_NUM_BUFFERS * BLOCK_SIZE.  That is what
    breaks when a fifth buffer is added and the guard is not moved
    -- addresses in the new buffers classify as interactive, cap
    0x7FFFFFFF, unbounded laydown back with the suite green.
    Pinned literals would fail on every legitimate pool move and
    teach the next person to update the expected numbers, which is
    how a gate becomes a formality.

    Also asserts the macro side: STR_SOURCE_CAP must compare
    against the SYMBOLS (so its bounds are the allocator's by
    identity, not coincidence) and its no-cap sentinel must be
    0x7FFFFFFF -- the loop compare is signed jl, so an all-ones
    sentinel reads as -1 and stops every non-block parse at
    length 0."""
    if BLK_BUF_GUARD != BLK_BUF_DATA + BLK_NUM_BUFFERS * BLOCK_SIZE:
        _fail(f'pool-bounds drift -- BLK_BUF_GUARD 0x{BLK_BUF_GUARD:X}'
              f' != BLK_BUF_DATA 0x{BLK_BUF_DATA:X} + BLK_NUM_BUFFERS '
              f'{BLK_NUM_BUFFERS} * BLOCK_SIZE {BLOCK_SIZE} = '
              f'0x{BLK_BUF_DATA + BLK_NUM_BUFFERS * BLOCK_SIZE:X}; '
              f'STR_SOURCE_CAP now mis-classifies part of the pool '
              f'as interactive (unbounded laydown)')
    m = re.search(r'^%macro\s+STR_SOURCE_CAP\s+0\s*$(.*?)^%endmacro',
                  _src, re.M | re.S)
    if not m:
        _fail('could not find the STR_SOURCE_CAP %macro block in '
              f'{ASM} (the "%macro STR_SOURCE_CAP 0" header phrasing '
              'is load-bearing, like the DICT_BACKSTOP-DERIVATION '
              'marker -- restore it, do not relax this regex)')
    body = m.group(1)
    if not re.search(r'cmp\s+eax,\s*BLK_BUF_DATA\b', body) or \
       not re.search(r'cmp\s+eax,\s*BLK_BUF_GUARD\b', body):
        _fail('STR_SOURCE_CAP no longer compares against the '
              'BLK_BUF_DATA/BLK_BUF_GUARD symbols -- a literal here '
              'severs the macro from the allocator and this gate '
              'checks the wrong thing')
    if not re.search(r'\[VAR_STR_CAP\],\s*0x7FFFFFFF\b', body):
        _fail('STR_SOURCE_CAP no-cap sentinel is not 0x7FFFFFFF -- '
              'the loop compare is signed jl; -1/0xFFFFFFFF stops '
              'every non-block parse at length 0')
