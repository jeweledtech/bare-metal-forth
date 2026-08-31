#!/usr/bin/env python3
"""Compile-mode string laydown gate: S" / ." / ABORT" must not walk
the dictionary past DICT_LIMIT, and their source must stop at the
block boundary.

THE DEFECT (finding_squote_laydown_unbounded, found 2026-08-24):
three identical compile-mode copy loops -- S" (forth.asm:2246),
." (:2329), ABORT" (:2427) -- read source bytes from [VAR_TIB+edx]
and stosb them to HERE.  The loop stops only on NUL or '"'.  Two
independent bounds are missing:

  SOURCE: the interpret branch of S" carries the only block-mode
    bound in the family (forth.asm:2290-2293, cmp edx, BLOCK_SIZE);
    the three compile branches have none.  In block mode VAR_TIB is
    a 1KB block buffer, so an unterminated quote reads past it into
    the adjacent buffers.  NOT unbounded: the walk stops at the NUL
    guard byte at BLK_BUF_GUARD 0x29200, so the worst case is ~4KB
    of laydown -- bounded by one byte that nothing protects.
  DEST: stosb advances edi with no DICT_LIMIT comparison.  The
    2026-08-24/25 bounds gate guards ALLOT/comma_/C,/create_ and
    backstops INTERPRET per token, but the backstop checks BEFORE
    the token runs; a single token whose laydown exceeds the
    backstop margin crosses the ceiling with no refusal.

TRIGGER REFINEMENT (found in this suite's investigation, 2026-08-25):
a single LOAD does NOT reproduce the runaway, because LOAD writes a
NUL terminator at buffer+BLOCK_SIZE (forth.asm:3011) -- the first
byte of the ADJACENT buffer -- and the copy loop stops on NUL.  The
defect requires that NUL to have been clobbered after the LOAD set
it, which any subsequent reload of the neighbouring buffer does
(nested LOADs and --> chains, i.e. exactly how every vocabulary
loads).  This suite emulates the clobber with an in-block poke (the
helper BF, first token of the crafted block, re-writes 'X' over the
NUL) rather than orchestrating a nested load; the emulation writes
the same byte the real mechanism overwrites.

WHAT A GREEN RUN DOES NOT COVER (named per gate discipline):
  - The block READ path (ATA/memdisk into the buffer) is never
    exercised: blocks are crafted in RAM via BUFFER, which marks a
    buffer valid WITHOUT a disk read (forth.asm:2691), so LOAD hits
    the cache.  Correct for this defect -- the copy loop reads the
    buffer bytes regardless of how they got there -- but a read-path
    regression would be invisible here.
  - The in-loop DICT_LIMIT guard (fix part c) is defense in depth
    and is NOT observed firing in the green run: after fix part (a)
    the source is capped at BLOCK_SIZE, so the worst laydown (1039
    bytes, derivation below) is smaller than the backstop margin and
    the guard is unreachable by construction.  It is exercised
    exactly once, by a separate throwaway build with DICT_BACKSTOP
    defeated to 0 (--backstop0 mode below;
    docs/evidence/squote-laydown-backstop0-2026-08-28.log), which
    proves the guard alone stops the crossing -- otherwise it would
    be a definition with a comment and no caller.

THE FIX (one commit, three parts):
  a) source stop: the interpret branch's block-mode bound (BLK!=0
     and edx >= BLOCK_SIZE) in all three compile loops -- as a
     NAMED refusal, not a silent truncation: jmp string_unterm_
     ("UNTERMINATED STRING", sharing dict_refuse_'s print+ABORT
     tail), because what a silent stop compiles -- a truncated
     string -- persists into the loaded vocabulary and surfaces
     far from its cause (bug_squote_blk_truncate).  The
     interactive NUL-end stays a silent truncation on purpose: at
     the prompt the operator sees the truncated echo immediately;
     in block source nobody is watching the laydown;
  b) DICT_BACKSTOP re-derivation.  The backstop checks once per
     token, pre-dispatch; between two checks exactly one token
     compiles (word_ for the next token writes only to the static
     32-byte word_buffer, never HERE).  So the bound is the worst
     single-token laydown, post-fix:
         4 ((S") XT) + 4 (length cell) + 1024 (source, capped at
         BLOCK_SIZE by part a) + 3 (align) + 4 (trailing TYPE /
         (ABORT") XT) = 1039 bytes.
     Every other token is smaller: definers are guarded inside
     create_ (72-byte entry margin), literals 8, control-flow
     immediates <= 8, plain compiles 4.  DICT_BACKSTOP becomes
     2048 = 1039 bound + 1009 slack (slack, not derivation).
  c) dest guard: cmp edi, DICT_LIMIT - 8 / jae dict_full_ ahead of
     the stosb in all three loops (DICT_LIMIT is exclusive, so >=
     is the refusal condition -- the jae direction is what the
     --backstop0 run proves).  The -8 reserves the epilogue: after
     the guard refuses, .endcopy still runs -- align advances HERE
     by up to 3 and ." / ABORT" store a trailing XT (4 bytes) with
     no guard of their own, so a bare-LIMIT guard would accept a
     final byte at DICT_LIMIT-1 and then overrun by up to 7.

GEOMETRY (all values derived, not chosen -- the arithmetic is the
pre-registration): leg names are 2 chars (Q1/Q2/Q3) so the create_
header is [LINK:4][FLAGS+LEN:1][NAME:2] = 7 -> align 8, +4 DOCOL
= 12 bytes.  Block text "BF : Q1 .\" " is 11 bytes, and word_
leaves >IN at the delimiter (offset 10, a space) which the laydown
skips, so the copy starts at source offset 11 (15 for ABORT", whose
token is 4 chars longer).  Sentinels: three cells planted at
0x80000/0x80004/0x80008 (value 305419896 = 0x12345678); the X fill
byte is 88 ('X'), so a crossed cell reads 1482184792 = 0x58585858.

T3 RED laydown chain, park P = 0x7F800 (= DICT_LIMIT - 2048), quote
at absolute source offset 2047 (last byte of the adjacent buffer),
NUL planted at 2048:
    header P..P+11, HERE = P+12 = 0x7F80C
    (S") XT @ 0x7F80C, length cell @ 0x7F810 = P+16
    string from S = P+20 = 0x7F814
  Q1 ."     L = 2047-11 = 2036: string 0x7F814..0x80007 (0x7F814 +
            0x7F4 = 0x80008), s0+s1 X-crossed, edi 0x80008 already
            aligned, TYPE XT @ 0x80008 (s2 <- TYPE XT, a kernel
            address: range prediction < DICT_START 0x30000, exact
            value recorded at the red run), HERE = 0x8000C
  Q2 S"     L = 2036: same string span, s0+s1 X-crossed, no
            trailing XT, HERE = 0x80008, s2 UNTOUCHED (this check
            is predicted to PASS in red -- the S" laydown is 4
            bytes shorter than ."'s)
  Q3 ABORT" L = 2047-15 = 2032: string 0x7F814..0x80003, s0
            X-crossed, edi 0x80004 aligned, (ABORT") XT @ 0x80004
            (s1 <- XT, range < 0x30000), HERE = 0x80008, s2
            untouched (predicted PASS in red)
  No refusal message on the LOAD line in red, any leg.

T3 GREEN, same park: BF executes at STATE=0 (backstop is compile
path only), ':' dispatches at HERE = P (not > P, ja) and lays the
12-byte header, then the string word dispatches at HERE = P+12 >
P: backstop refuses.  HERE = 0x7F80C, all three sentinels intact,
DICT FULL on the LOAD line.  Identical for all three legs.

T2 (boundary refusal, normal HERE far from the ceiling), quote at
absolute 1500, NUL at 1501:
  GREEN: "UNTERMINATED STRING" on the LOAD line; STATE=0 (the
  refusal's ABORT); HERE at h+20, the laydown start -- only
  .endcopy moves VAR_HERE and the refusal precedes it.  The
  length cell at h+16 is never patched, so the old h+16 read is
  gone with the silent stop it measured.  ABORT also resets BLK,
  so the rest of the crafted block is never parsed -- the old
  green side-noise (31-char 'XXX...' token -> "?" -> ABORT via
  word_'s own bound, forth.asm cmp ecx, 31) died with it too.
  RED   L = 1500-11 = 1489 (Q1/Q2), 1500-15 = 1485 (Q3) laid
  down, length-patched, HERE moved, no message, STATE left 1 --
  three discriminators per leg.
T2b (pin, green BOTH sides): quote at 1021, ' ;' poked at
1022/1023, prefix ': Q1 ." ' (8 chars, copy from 8, NO BF -- this
leg wants the clean in-block close).  L = 1013; token laydown =
4 + 4 + 1013 + 3 (align) + 4 = 1028 <= 1039; ';' adds EXIT, so
HERE = h+12+1028+4.  Pins the derivation premise the backstop
margin rests on: the worst laydown a block can terminate.

LAYOUT MODEL CORRECTION (for the reader comparing documents): the
pre-read analysis of ABORT" placed the length cell at h+24 after a
compiled LIT 0.  That model was wrong -- the asm (forth.asm:
2407-2411, comment and code) lays [(S") XT][length][string][align]
[(ABORT") XT], identical to ." but for the trailing XT, with NO
LIT.  All three legs therefore read the length cell at h+16, and
this file's T3 geometry (string at P+20, Q3 trailing XT at
0x80004) follows from the same model.  The asm read of 2026-08-25
supersedes the earlier draft wherever they disagree.

T4 (margin, BACKSTOP_MARGIN = 2048): park DICT_LIMIT-2048+8 =
0x7F808 -> body refused, HERE at park+12.  (RED: old 1024 margin
admits the whole definition, HERE at park+24 -- both checks FAIL;
derivation and red re-run below.)  Control park DICT_LIMIT-8192
compiles and runs on both sides.
T4 MODEL CORRECTION (first green run, 2026-08-26): the draft
prediction read "':' itself must be refused, HERE unchanged".
Wrong model -- the backstop is pre-dispatch but STATE=1-only
(forth.asm INTERPRET gate comment: interpret mode is deliberately
ungated so recovery pokes always parse), so ':' executes at
STATE=0, create_'s 72-byte entry margin admits the header 2040
bytes below the ceiling, and the refusal lands on the first BODY
token.  HERE = park+12 by the GEOMETRY section's own header
arithmetic -- [LINK:4][FLAGS+LEN:1][NAME:2] = 7 -> align 8, +4
DOCOL = 12 for the 2-char name M1, the same derivation that sized
the Q-leg names -- and T3 GREEN already predicts the identical
+12 residue at its own park; the dict-bounds suite's test 4
accepts the same class by decision.  The first green run then
confirmed 0x7F814 = park+12.  "Refused with nothing laid" was
the draft's invention, never the kernel's contract.
T4 RED under the renamed check (derived): the old 1024 margin's
threshold is 0x7FC00, park 0x7F808 is below it, so the whole
definition compiles -- header 12 + literal 8 (LIT XT + value 1)
+ EXIT 4 -> HERE = park+24 = 0x7F820, failing park+12 as it
failed the old "unchanged" -- red discriminates under either
model.  The original red run predates the rename, so this is
confirmed by a red RE-RUN of this suite against 9ae68d5's parent
(17c7e89), not inherited from the 2026-08-25 log.

EXPECTED RED (against the unfixed kernel) -- two vintages, both
observed against the byte-identical image (sha256 964674c7...,
rebuilt from 9ae68d5's parent 17c7e89 for the re-run and equal to
the original red log's input hash):
  2026-08-25 original red (pre-rework suite, 51 checks, 18
  FAILs; docs/evidence/squote-laydown-red-2026-08-25.log):
  T2 'source stopped at block boundary' x3 (lengths
  1489/1489/1485 for 1013/1013/1009), T3 5+4+4, T4 2.
  2026-08-26 red RE-RUN (this suite as shipped, 63 checks, 24
  FAILs; docs/evidence/squote-laydown-red-rerun-2026-08-26.log)
  -- owed because T2's discriminators and T4's HERE check were
  reworked/renamed after the original red, and a check whose
  assertion changed after red has not demonstrated red until
  re-run:
  T2: refusal-named / STATE-cleared / HERE-at-laydown-start x3
      legs (9); the runaway lengths 1489/1489/1485 reappear in
      the FAIL diagnostics
  T3: Q1: refused / s0 / s1 / s2 / HERE-at-park+12  (5)
      Q2: refused / s0 / s1 / HERE                  (4; s2 passes)
      Q3: refused / s0 / s1 / HERE                  (4; s2 passes)
      (XT range predictions held: Q1 s2 0x88F0, Q3 s1 0x98C8,
      both < DICT_START)
  T4: 'margin park refused' + the renamed HERE check (2);
      observed HERE 0x7F820 = park+24, exactly as derived in the
      T4 MODEL CORRECTION -- red discriminates under either model
All instrument checks (T1), craft-stability checks, T2b,
aliveness, and T5 recovery are green BOTH sides (observed in both
red vintages and the green run).

Check-count lineage (the design sketch said ~34 -- an estimate,
not a count): as first written the suite was 51 = 15 (T1) + 9
(T2) + 21 (T3) + 3 (T4) + 3 (T5); the T2 rework (named refusal)
and the T2b pin brought it to 63 = 15 + 15 (T2: per leg craft /
refusal-named / STATE-cleared / HERE-at-start / alive) + 6 (T2b)
+ 21 + 3 + 3, the total both 2026-08-26 runs print.  Growth is
additions, not splits: T1
gained the STATE-probe pair, mutate-detect, buffer-address,
BF-poke, craft-readback, and current-vocab-cell instruments; T2
and T3 each gained per-leg craft-stability and aliveness (+2 per
leg).  One merge the other way: T4's control-park 'compiles' and
'runs' collapsed into the single M2=2 check (a successful run
proves the compile).
The --backstop0 mode is a separate run with its own total, not
part of the 63: 23 = 15 (T1, shared) + 2 (mode/image probe pair,
added when the INVALID first run showed the mode can be handed
the wrong image) + 6 (craft-stability, refusal, sentinels, STATE
cleared by the in-loop refusal, HERE, aliveness) -- a PREDICTED
total: no valid backstop0 run exists yet (the 2026-08-25 attempt
is INVALID -- stale image, dead interpreter).
OBSERVED: the 2026-08-28 run prints exactly 23 (evidence log
above).

STUB RESIDUE AND UNWIND: every leg leaves a LATEST-reachable stub
(same residue class the dict-bounds suite accepts once, test 4
there).  This suite parks at the SAME address repeatedly, and a
second header over a stub that LATEST points at would self-link
the chain -- so unlike the bounds suite, every leg is unwound: HERE
is re-poked and LATEST plus the current vocab's latest cell
([VAR_CURRENT 0x28044]) are restored to the post-helper baseline.
This is instrument hygiene for reuse of one park address, not a
position on unwind-on-abort (Bug #31 owns that).

Typed-numeral invariant: every line that pokes memory carries its
own DECIMAL.  Parsing discipline per tests/test_abort.py: exact
integers, echo line stripped before substring checks.

Result carries input hash: the booted image path arrives from the
caller (Makefile passes $(ACTIVE_IMAGE)) and is hashed unwrapped.

--backstop0 mode (mentor condition, 2026-08-25): run against a
throwaway build with DICT_BACKSTOP defeated from the build line
(-DDICT_BACKSTOP=0, make backstop0 -- never a source edit).  Park
0x7FE00; backstop threshold is then DICT_LIMIT itself (fires only
above 0x80000, ja) and create_'s 72-byte margin also passes, so
ONLY the in-loop guard stands between the laydown and the ceiling.
Predicted (re-registered 2026-08-26 for the DICT_LIMIT-8 guard;
the original 0x80000/492 prediction predates the -8 epilogue
reservation and was never run): guard is 'jae DICT_LIMIT-8', so
it fires when edi reaches 0x7FFF8 after 484 of the available 2036
source bytes (string start 0x7FE14; 0x7FFF8 - 0x7FE14 = 0x1E4 =
484); DICT FULL on the LOAD line (this is the DESTINATION guard's
dict_full_ exit -- UNTERMINATED STRING is the separate source-
exhaustion leg and must NOT appear here); all sentinels intact;
HERE still 0x7FE14 (the copy loop updates VAR_HERE only at
endcopy).
OBSERVED (2026-08-28, image a8879882..., 23/23;
docs/evidence/squote-laydown-backstop0-2026-08-28.log): every
half of the prediction confirmed -- DICT FULL with UNTERMINATED
STRING absent (machine-checked in the same assertion; the
destination guard fires at edx=495 vs the source cap's 1024, a
>500-byte win), sentinels intact, HERE 0x7FE14, STATE cleared,
interpreter alive.  First run of 2026-08-28 (same image, same
23/23) predates the strengthened assertion and is superseded by
this one, not captured.
"""
import hashlib
import re
import socket
import sys
import time

args = [a for a in sys.argv[1:] if a != '--backstop0']
BACKSTOP0 = '--backstop0' in sys.argv

PORT = int(args[0]) if len(args) > 0 else 4598
IMG = args[1] if len(args) > 1 else 'build/bmforth.img'

CEILING = 0x80000
DICT_START = 0x30000
# Parsed from the kernel source via the shared module (one home for
# the equ regexes; see kernel_constants.py's docstring for the
# history that earned it).  The three-way gate runs in EVERY mode,
# --backstop0 included: since the %define/%ifndef rework the source
# always reads the shipping value (the only override is the build
# line, -DDICT_BACKSTOP=0), so a gate refusal in backstop0 mode
# means the source itself is wrong -- exactly the hand-edit the
# rework forbids.  What the gate cannot see is which IMAGE the
# caller booted; that is proven at RUNTIME instead: a probe
# definition parked inside the would-be margin compiles only if the
# BOOTED kernel truly has no backstop (see the backstop0 branch
# below).  Source-side parsing alone cannot give that proof: the
# image the caller passes and the source on disk are separate
# artifacts.
import kernel_constants
kernel_constants.check_backstop_derivation()
# In backstop0 mode this is the WOULD-BE margin (geometry for the
# probe placement), not the booted kernel's margin -- that is 0 by
# construction and proven by the runtime probe.
BACKSTOP_MARGIN = kernel_constants.DICT_BACKSTOP
# The bound T2b pins: worst single-token laydown, derived once in
# the shared module (BLOCK_SIZE + 4 + 4 + 3 + 4).
BOUND = kernel_constants.BOUND
VAR_CURRENT = 0x28044           # forth.asm equ: addr of current vocab's
                                # LATEST cell (no word exposes it)
SENTINEL = 305419896            # 0x12345678
XFILL_CELL = 1482184792         # 0x58585858 -- four 'X' bytes
S0, S1, S2 = 0x80000, 0x80004, 0x80008

with open(IMG, 'rb') as f:
    print(f'input sha256 {hashlib.sha256(f.read()).hexdigest()}  {IMG}')
if BACKSTOP0:
    print('MODE: --backstop0 (DICT_BACKSTOP defeated to 0; this run '
          'exists to observe the in-loop guard firing)')

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
for attempt in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print("FAIL: connect")
    sys.exit(1)

time.sleep(2)
try:
    while True:
        s.recv(4096)
except Exception:
    pass


def send(cmd, wait=1.0):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(2)
    resp = b''
    while True:
        try:
            d = s.recv(4096)
            if not d:
                break
            resp += d
        except Exception:
            break
    return resp.decode('ascii', errors='replace')


def body_of(raw):
    """Drop the echoed input line (the echo contains the command's
    own characters, which would satisfy substring checks)."""
    return raw.split('\n', 1)[1] if '\n' in raw else raw


def val(expr, wait=1.5):
    raw = send(f'DECIMAL {expr} .', wait)
    body = body_of(raw)
    if '?' in body:
        return None, raw
    nums = re.findall(r'-?\d+', body)
    return (int(nums[-1]) if nums else None), raw


def poke_here(n):
    return send(f'DECIMAL {n} HERE !', 1.0)


def hx(v):
    return f'0x{v:X}' if isinstance(v, int) else repr(v)


PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- {detail}' if detail else
              f'  FAIL: {name}')


def alive():
    v, _ = val('7 6 *')
    return v == 42


def here():
    v, raw = val('HERE @')
    return v, raw


def plant_sentinels():
    send(f'DECIMAL {SENTINEL} {S0} !', 0.8)
    send(f'DECIMAL {SENTINEL} {S1} !', 0.8)
    send(f'DECIMAL {SENTINEL} {S2} !', 0.8)


def craft(prefix, quote_abs):
    """Fill blocks 100 (prefix + X) and 101 (X), plant '"' at
    absolute source offset quote_abs and NUL right after.  Returns
    False if the buffer moved (cache instability = instrument
    failure)."""
    v, _ = val('100 BUFFER')
    if v != b100:
        return False
    send('DECIMAL 100 BUFFER 1024 88 FILL', 1.0)
    send('DECIMAL 101 BUFFER 1024 88 FILL', 1.0)
    codes = [ord(c) for c in prefix]
    line = 'DECIMAL ' + ' '.join(
        f'{c} {b100 + i} C!' for i, c in enumerate(codes[:8]))
    send(line, 1.0)
    line = 'DECIMAL ' + ' '.join(
        f'{c} {b100 + 8 + i} C!' for i, c in enumerate(codes[8:]))
    send(line, 1.0)
    send(f'DECIMAL 34 {b100 + quote_abs} C! 0 {b100 + quote_abs + 1} C!',
         1.0)
    return True


def unwind():
    """Restore HERE/LATEST/current-vocab-latest to the post-helper
    baseline (see docstring: park-address reuse forbids leaving
    stubs that LATEST reaches).  Note it restores ALL THREE: A8
    established that ABORT unwinds neither HERE nor LATEST and the
    kernel's own recovery touches only global VAR_LATEST -- so
    after T2's refusal legs (which ABORT mid-definition, leaving a
    smudged header at LATEST), this poke of the per-vocab cell is
    what keeps T2b's h_base arithmetic honest."""
    poke_here(h_base)
    send(f'DECIMAL {l_base} LATEST !', 0.8)
    send(f'DECIMAL {l_base} {cur_cell} !', 0.8)


def recover_state():
    """If a leg left STATE=1 (unterminated definition), close it.
    BT-STATE? is IMMEDIATE so it executes -- and therefore reads --
    in either mode; ';' is only sent when needed because in
    interpret mode it would be a stray.  Returns the STATE it read
    (None if unreadable) so callers can assert on it."""
    r = send('BT-STATE?', 1.0)
    nums = re.findall(r'-?\d+', body_of(r))
    sv = int(nums[-1]) if nums else None
    if sv == 1:
        send(';', 1.5)
    return sv


# ---------------------------------------------------------------
print("\nTest 1: instruments")
send('DECIMAL', 0.5)
check('interpreter alive at start', alive())

# STATE probe (IMMEDIATE, same instrument the bounds suite proved)
send(': BT-STATE? STATE @ . ; IMMEDIATE', 1.0)
r = send('BT-STATE?', 1.0)
nums = re.findall(r'-?\d+', body_of(r))
check('STATE probe reads 0 in interpret mode',
      bool(nums) and int(nums[-1]) == 0, repr(body_of(r).strip()[-60:]))
# The probe must be proven in BOTH directions: recover_state()
# sends ';' only when the probe reads 1, so a stuck-at-0 probe
# would silently skip recovery in the red T2 legs and wedge the
# following leg in compile mode.
r = send(': BT-PROBE BT-STATE? ;', 1.0)
nums = re.findall(r'-?\d+', body_of(r))
check('STATE probe reads 1 in compile mode',
      bool(nums) and int(nums[-1]) == 1, repr(body_of(r).strip()[-60:]))

# Sentinel plant / readback / mutate-detect
plant_sentinels()
v0, _ = val(f'{S0} @')
v1, _ = val(f'{S1} @')
v2, _ = val(f'{S2} @')
check('sentinels planted and read back',
      (v0, v1, v2) == (SENTINEL,) * 3,
      f's0={v0!r} s1={v1!r} s2={v2!r}')
send(f'DECIMAL 7 {S0} !', 0.8)
vm, _ = val(f'{S0} @')
check('sentinel readback detects mutation', vm == 7, f'got {vm!r}')
send(f'DECIMAL {SENTINEL} {S0} !', 0.8)

# Block buffers: address, adjacency, LOAD's neighbour-NUL
b100, raw = val('100 BUFFER')
b101, _ = val('101 BUFFER')
check('100 BUFFER returns an address', b100 is not None,
      repr(raw.strip()[-60:]))
check('block buffers adjacent (101 = 100 + 1024)',
      b100 is not None and b101 == b100 + 1024,
      f'b100={hx(b100)} b101={hx(b101)}')
if b100 is None or b101 != b100 + 1024:
    print('\nPassed: cannot continue without adjacent buffers')
    sys.exit(1)

# BF: the neighbour-NUL clobber emulation (see docstring TRIGGER
# REFINEMENT).  Re-writes 'X' over the NUL that LOAD places at
# buffer+1024, standing in for a reload of the neighbour buffer.
send(f'DECIMAL : BF 88 {b100 + 1024} C! ;', 1.0)
r = send('BF', 1.0)
vb, _ = val(f'{b100 + 1024} C@')
check('BF pokes X over the neighbour byte', vb == 88, f'got {vb!r}')

# Craft readback: prove the prefix and quote land where the
# arithmetic says (this is the check that would catch a word_ /
# >IN off-by-one before it silently shifted every length below)
ok = craft('BF : Q1 ." ', 1500)
check('craft: buffer stable', ok)
p10, _ = val(f'{b100 + 10} C@')
p11, _ = val(f'{b100 + 11} C@')
pq, _ = val(f'{b100 + 1500} C@')
pn, _ = val(f'{b100 + 1501} C@')
check('craft readback: delimiter space at 10, X at 11, quote at '
      '1500, NUL at 1501',
      (p10, p11, pq, pn) == (32, 88, 34, 0),
      f'got {p10!r},{p11!r},{pq!r},{pn!r}')

# Interactive round trips: the three words still work at all
# (positive controls; also prove the interactive NUL stop is not
# disturbed by the fix)
send(': BT-R1 S" AB" ;', 1.0)
v, raw = val('BT-R1 SWAP DROP')
check('interactive S" round trip (len 2)', v == 2,
      repr(raw.strip()[-60:]))
r = send(': BT-R2 ." HI" ; BT-R2', 1.5)
check('interactive ." round trip prints', 'HI' in body_of(r),
      repr(body_of(r).strip()[-60:]))
send(': BT-R3 0 ABORT" NO" 77 ;', 1.0)
v, raw = val('BT-R3')
check('interactive ABORT" false-flag round trip (77)', v == 77,
      repr(raw.strip()[-60:]))

cur_cell, raw = val(f'{VAR_CURRENT} @')
check('current-vocab latest cell readable', cur_cell is not None,
      repr(raw.strip()[-60:]))
h_base, raw = here()
l_base, _ = val('LATEST @')
check('baseline HERE plausible',
      h_base is not None and DICT_START <= h_base < CEILING,
      f'got {h_base!r}')
if None in (h_base, l_base, cur_cell):
    print('\nPassed: cannot continue without baseline')
    sys.exit(1)

LEGS = [('Q1', '."',     'BF : Q1 ." ',     11),
        ('Q2', 'S"',     'BF : Q2 S" ',     11),
        ('Q3', 'ABORT"', 'BF : Q3 ABORT" ', 15)]

# ---------------------------------------------------------------
if BACKSTOP0:
    # Single leg proving the in-loop guard: see docstring tail.
    print("\nBackstop0: in-loop guard alone must stop the crossing")
    # Mode/image agreement probe, BEFORE any zero-reserve leg: this
    # mode's legs are meaningless against a normally-built image
    # (the backstop fires first and every check passes or fails for
    # reasons unrelated to what it asserts).  Source-side parsing
    # cannot prove which kernel BOOTED, so ask the kernel: a
    # definition parked inside the would-be margin (CEILING-256,
    # comfortably above create_'s 72-byte entry margin) compiles
    # only if the backstop is truly absent.  Refusal here is a
    # harness error, not a kernel finding -- stop the run.
    # Park offset derived from the margin, not hardcoded (the same
    # reasoning that moved 2048 and 1024 out of these files): it
    # must sit inside the would-be margin for ANY permitted
    # backstop, with a floor of 128 clearing create_'s 72-byte
    # entry margin plus the ~24-byte probe body.  A margin too
    # small to host the probe cannot be discriminated -- refuse
    # loudly rather than compile-under-both-modes silently.
    probe_off = max(BACKSTOP_MARGIN // 8, 128)
    if probe_off >= BACKSTOP_MARGIN:
        print('ABORTED: backstop margin too small to host the '
              'mode/image probe -- probe cannot discriminate')
        s.close()
        sys.exit(1)
    poke_here(CEILING - probe_off)
    r = send(': BT-M0 5 ;', 1.5)
    b = body_of(r)
    check('mode/image probe: definition inside the would-be margin '
          'compiles (backstop truly absent in the booted image)',
          'DICT FULL' not in b, repr(b.strip()[-90:]))
    if 'DICT FULL' in b:
        recover_state()
        unwind()
        # 'ABORTED', deliberately not 'Passed': the aggregate greps
        # ^Passed: for suite counts, and a mismatch must not land
        # in that count as anything -- the nonzero exit is the
        # signal, this line is for the human reading the log.
        print('\nABORTED: mode/image mismatch -- --backstop0 given a '
              'kernel whose backstop is live; run it against the '
              'make backstop0 build (-DDICT_BACKSTOP=0)')
        s.close()
        sys.exit(1)
    v, raw = val('BT-M0')
    check('mode/image probe runs (BT-M0 = 5)', v == 5,
          repr(raw.strip()[-60:]))
    unwind()
    plant_sentinels()
    park = 0x7FE00
    ok = craft('BF : Q1 ." ', 2047)
    check('craft: buffer stable', ok)
    poke_here(park)
    r = send('DECIMAL 100 LOAD', 3.0)
    b = body_of(r)
    # Both halves of the pre-registration in one check: DICT FULL
    # present (destination guard's dict_full_ exit) AND UNTERMINATED
    # STRING absent -- the destination guard fires at edx=495 (11 +
    # 484), the source cap at edx=1024, so the source-exhaustion leg
    # must lose the race by >500 bytes.  UNTERMINATED here would
    # mean the guard arithmetic is wrong, not just a different
    # refusal.
    check('in-loop guard refused with DICT FULL '
          '(and not UNTERMINATED STRING -- destination guard won)',
          'DICT FULL' in b and 'UNTERMINATED' not in b,
          repr(b.strip()[-90:]))
    # Probe-order discipline as in T2/T3, but promoted from silent
    # no-op to assertion: the in-loop guard ends in dict_full_ ->
    # ABORT, which must clear STATE.  If this ever fires, the guard
    # refused without aborting -- a refusal that leaves the machine
    # wedged in compile mode, worth knowing loudly.  (dict_bounds
    # asserts the same invariant for the backstop's refusal; this
    # is the only run where the IN-LOOP guard's refusal exists to
    # be asserted on.)
    sv = recover_state()
    check('STATE cleared by in-loop refusal (escape hatch open)',
          sv == 0, f'STATE={sv!r}')
    v0, _ = val(f'{S0} @')
    v1, _ = val(f'{S1} @')
    v2, _ = val(f'{S2} @')
    check('sentinels intact (guard stopped the walk)',
          (v0, v1, v2) == (SENTINEL,) * 3,
          f's0={hx(v0)} s1={hx(v1)} s2={hx(v2)}')
    hb, _ = here()
    check('HERE still at string start 0x7FE14 (VAR_HERE only moves '
          'at endcopy)', hb == park + 20, f'HERE={hx(hb)}')
    recover_state()
    unwind()
    check('interpreter alive after in-loop refusal', alive())
    print(f'\nPassed: {PASS}/{PASS + FAIL}')
    s.close()
    sys.exit(0 if FAIL == 0 else 1)

# ---------------------------------------------------------------
print("\nTest 2: block-boundary exhaustion is a NAMED refusal "
      "(x3 words)")
# GREEN: the copy loop hits BLOCK_SIZE with no closing quote and
# jumps string_unterm_ -- "UNTERMINATED STRING" on the LOAD line,
# ABORT clears STATE, and VAR_HERE never advances past the laydown
# start (only .endcopy moves it, and the refusal precedes
# .endcopy; the length cell at h+16 is likewise never patched, so
# this suite no longer reads it here).  RED (pre-fix kernel): no
# message exists, the runaway lays RED_LEN bytes, .endcopy patches
# the length and moves HERE, and STATE is left at 1 because the
# quote swallowed the rest of the line -- three discriminators per
# leg.
RED_LEN = {'Q1': 1489, 'Q2': 1489, 'Q3': 1485}
for name, word, prefix, start in LEGS:
    ok = craft(prefix, 1500)
    check(f'{name} craft: buffer stable', ok)
    r = send('DECIMAL 100 LOAD', 3.0)
    b = body_of(r)
    check(f'{name} boundary refusal named (UNTERMINATED STRING)',
          'UNTERMINATED STRING' in b, repr(b.strip()[-90:]))
    # recover_state BEFORE any val(): in red the leg leaves
    # STATE=1 and a probe sent in compile mode COMPILES its tokens
    # (run 1 of 2026-08-25 read None on every leg for exactly this
    # reason).  In green the refusal's ABORT already cleared it,
    # which is itself the second discriminator.
    sv = recover_state()
    check(f'{name} STATE cleared by the refusal (ABORT ran)',
          sv == 0, f'STATE={sv!r} (red: 1, the runaway swallowed '
          f'the closing quote)')
    hb, _ = here()
    check(f'{name} HERE at laydown start (refusal precedes '
          f'endcopy)', hb == h_base + 20,
          f'HERE={hx(hb)} want {hx(h_base + 20)} (red: endcopy '
          f'ran, len {RED_LEN[name]} laid down)')
    unwind()
    check(f'{name} alive after boundary-refusal leg', alive())

# ---------------------------------------------------------------
print("\nTest 2b: derivation premise -- the worst laydown a block "
      "can TERMINATE fits the derived bound")
# The DICT_BACKSTOP derivation rests on one premise: a single
# token's laydown is bounded by BLOCK_SIZE + 15.  This leg pins it
# with the largest string a block can close: prefix ': Q1 ." '
# (8 chars, copy starts at 8), quote at 1021, then ' ;' poked at
# 1022/1023 so the definition closes IN the block and the reads
# below run at STATE=0.  Length 1013; laydown = 4 + 4 + 1013 +
# 3 (align: h+1033 -> h+1036) + 4 = 1028 <= 1039; ';'
# then compiles EXIT (+4).  No BF in the prefix, deliberately:
# this leg WANTS the clean in-block stop, not the clobber.  A PIN,
# not a discriminator -- it passes on both sides; it exists so the
# 1039 in the kernel comment stays an observed ceiling, not a
# believed one (internal agreement isn't proof).
ok = craft(': Q1 ." ', 1021)
send(f'DECIMAL 32 {b100 + 1022} C! 59 {b100 + 1023} C!', 1.0)
p22, _ = val(f'{b100 + 1022} C@')
p23, _ = val(f'{b100 + 1023} C@')
check('T2b craft: buffer stable, space/semicolon at 1022/1023',
      ok and (p22, p23) == (32, 59), f'got {p22!r},{p23!r}')
r = send('DECIMAL 100 LOAD', 3.0)
b = body_of(r)
check('T2b terminated worst-case string loads without refusal',
      'UNTERMINATED' not in b and 'DICT FULL' not in b,
      repr(b.strip()[-90:]))
sv = recover_state()
check('T2b definition closed in-block (STATE 0)', sv == 0,
      f'STATE={sv!r}')
ln, _ = val(f'{h_base + 16} @')
check('T2b length cell 1013 (quote at 1021, copy from 8)',
      ln == 1013, f'len={ln!r}')
hb, _ = here()
laydown = None if hb is None else hb - h_base - 12 - 4  # -header -EXIT
check(f'T2b laydown 1028 <= derived bound {BOUND}',
      laydown == 1028 and laydown <= BOUND,
      f'laydown={laydown!r} (HERE={hx(hb)})')
unwind()
check('T2b alive', alive())

# ---------------------------------------------------------------
print("\nTest 3: ceiling composite -- laydown must not cross "
      "DICT_LIMIT (x3 words)")
PARK = CEILING - BACKSTOP_MARGIN          # 0x7F800
# Per-leg predictions from the docstring chain.  s2 legend: Q1
# red overwrites it with the TYPE XT; Q2/Q3 red leave it alone
# (their laydowns end 4 bytes shorter), so their s2 checks are
# predicted PASS even in red.  They are NOT dead weight despite
# never failing on either side: they are precision checks on the
# length model -- if Q2's s2 ever came back X-filled, the laydown
# would be longer than derived and the arithmetic above would be
# falsified.  Do not delete them for never having fired.
for name, word, prefix, start in LEGS:
    plant_sentinels()
    ok = craft(prefix, 2047)
    check(f'{name} craft: buffer stable', ok)
    poke_here(PARK)
    r = send('DECIMAL 100 LOAD', 3.0)
    b = body_of(r)
    check(f'{name} ceiling composite refused', 'DICT FULL' in b,
          repr(b.strip()[-90:]))
    # Recovery before the reads (same reason as T2 -- run 1's red
    # read s0=None because the probe compiled into the open stub;
    # at HERE above the ceiling that compile even tripped comma_'s
    # DICT FULL, which is what re-armed the later reads).  In red
    # the ';' lands above the ceiling and is itself refused by
    # comma_'s guard; that refusal ends in ABORT with STATE=0,
    # which is the recovery this probe needs.
    recover_state()
    v0, _ = val(f'{S0} @')
    v1, _ = val(f'{S1} @')
    v2, _ = val(f'{S2} @')
    check(f'{name} sentinel 0x80000 intact', v0 == SENTINEL,
          f'got {hx(v0)} (red predicts {hx(XFILL_CELL)})')
    check(f'{name} sentinel 0x80004 intact', v1 == SENTINEL,
          f'got {hx(v1)} (red: Q1/Q2 {hx(XFILL_CELL)}, Q3 the '
          f'(ABORT") XT < {hx(DICT_START)})')
    check(f'{name} sentinel 0x80008 intact', v2 == SENTINEL,
          f'got {hx(v2)} (red: Q1 the TYPE XT < {hx(DICT_START)}; '
          f'Q2/Q3 predicted intact even in red)')
    hb, _ = here()
    check(f'{name} HERE at park+12 (header laid, body refused)',
          hb == PARK + 12,
          f'HERE={hx(hb)} (red predicts Q1 0x8000C, Q2/Q3 0x80008)')
    recover_state()
    unwind()
    check(f'{name} alive after ceiling leg', alive())

# ---------------------------------------------------------------
print("\nTest 4: backstop margin covers the worst laydown")
# Park inside the margin.  The gate is STATE=1-only, so ':' (at
# STATE=0) lays its 12-byte header ungated -- create_'s 72-byte
# entry margin passes 2040 bytes below the ceiling -- and the
# refusal lands pre-dispatch on the first BODY token.  Red (1024
# margin) admits the whole definition.  See T4 MODEL CORRECTION
# in the docstring.
park = CEILING - BACKSTOP_MARGIN + 8
poke_here(park)
r = send(': M1 1 ;', 2.0)
b = body_of(r)
check('margin park refused', 'DICT FULL' in b,
      repr(b.strip()[-90:]))
hb, _ = here()
check('margin park: header laid, body refused (HERE at park+12)',
      hb == park + 12,
      f'HERE={hx(hb)} want {hx(park + 12)}')
recover_state()
unwind()
# Control: well below the margin, definitions still compile and run
park = CEILING - 8192
poke_here(park)
r = send(': M2 2 ;', 1.5)
v, raw = val('M2')
check('control park compiles and runs (M2 = 2)', v == 2,
      f'got {v!r} from {raw.strip()[-60:]!r}')
unwind()

# ---------------------------------------------------------------
print("\nTest 5: recovered -- definitions work again")
r = send(': BT-REC 6 7 * ;', 1.5)
check('post-suite definition compiles',
      '?' not in body_of(r) and 'DICT FULL' not in body_of(r),
      repr(body_of(r).strip()[-90:]))
v, raw = val('BT-REC')
check('post-suite definition runs (BT-REC = 42)', v == 42,
      f'got {v!r} from {raw.strip()[-60:]!r}')
check('interpreter alive at end', alive())

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
