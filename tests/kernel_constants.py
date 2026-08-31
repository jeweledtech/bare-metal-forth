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
