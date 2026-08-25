#!/usr/bin/env python3
"""Dictionary bounds gate: HERE must never silently cross the ceiling.

DICT_START (0x30000) + DICT_SIZE (0x50000) = 0x80000 is the ceiling
(forth.asm).  Until 2026-08-24 no VAR_HERE mutation site checked it:
~60 bare adds, so a full dictionary wrote on into whatever lives
above and APPEARED to work.  This is a live defect, not a latent
one: at bare boot HERE is already 0x5E1F0 (57.6% of the region
gone, 138,768 bytes free; measured 2026-08-24), and after the G6
harness's full load 0x6221C (122,340 free).  The fix (G6 closeout
follow-on, the highest-severity open item on the docket) is one
shared refusal routine guarding four choke points:

  - ALLOT        refuse-before-mutate (the only unbounded path)
  - create_      entry check BEFORE the header stosb sequence --
                 create_ writes at HERE first and moves the pointer
                 second, so a check after the add is a check after
                 the corruption
  - comma_ / C,  check before the store
  - INTERPRET    compile-path backstop (STATE=1 only), covering the
                 ~40 inline 'add [VAR_HERE], 4' sites in compilation
                 words without editing them.  Interpret mode is NOT
                 backstopped, deliberately: that is the escape hatch
                 -- a full dictionary must still accept the recovery
                 pokes (HERE !, interpret-mode words), or the refusal
                 wedges the machine it is protecting.

Margins, derived not asserted:
  - backstop reserve 1KB: the worst single-token compilation is a
    string laydown bounded by one input line (TIB_SIZE = 256 at
    0x28100), so 1KB is 4x the derivable worst case.
  - create_ margin: header is [LINK:4][FLAGS+LEN:1][NAME:<=31]
    [align][CFA:4] = 40 bytes before alignment; the guard uses 72
    (40 + slack), generous on purpose.

Residue decision (deliberate, not a side effect): in the GREEN
state test 4 manufactures exactly the defect class
ARCHITECTURE-CUSTODIAN.md section 3.3 names -- create_ passes its
own check, writes the header, updates LATEST (global AND the
current vocab's cell), and THEN the backstop refuses the body.
That leaves LATEST pointing at a structurally complete but
never-finished header, which every later name lookup walks (test
5's BT-REC links through it).  Walking is safe; EXECUTING it is a
wild jump, so this suite never runs BT-X.  The dangling head is
ACCEPTED here rather than unwound, with reason: it is the same
residue any mid-definition abort leaves (an ABORT" firing inside a
colon body produces the identical LATEST-reachable stub -- Bug #31,
break-mid-definition residue: STATE=1 with HERE/LATEST left
advanced, docs/bug_break_state_restore.md).  Unwind-on-abort is
that bug's fix, one mechanism for
every abort path; hiding a private unwind inside dict_full_ would
fix the guard's residue while leaving every other abort's, and the
two would then diverge.

Red-first (pre-registered 2026-08-24, outcome recorded below the
expectations, per docket discipline):
  EXPECTED RED against the unguarded kernel, by name:
    - 'overflow ALLOT refused with a message'  (no message today)
    - 'overflow ALLOT left HERE unchanged'     (HERE moves today)
    - 'compile-path backstop fired'            (definition compiles
                                                silently today)
    - 'backstop blocked the definition'        (it runs today)
  EXPECTED GREEN both sides (positive controls): liveness, HERE
  plausibility, small-ALLOT round trip, post-restore definition.
  OUTCOME 2026-08-24: red 10/14, all four named FAILs fired for
  the pre-registered reasons (dict-bounds-red-2026-08-24.log);
  green 18/18 after the ceiling guards
  (dict-bounds-green-2026-08-24.log).

Floor extension (pre-registered 2026-08-25, against the
ceiling-only kernel; outcome recorded below):
  The ceiling guards were one-sided -- negative ALLOT could carry
  HERE below DICT_START into the sysvar/TIB/block-buffer region
  with no refusal.  EXPECTED RED, by name:
    - 'floor ALLOT refused with a message'    (passes silently
                                               today)
    - 'floor ALLOT left HERE unchanged'       (HERE lands at
                                               0x2F000 today)
    - 'large negative ALLOT attributed as underflow'
        (refused today, but as "DICT FULL" via the unsigned wrap
         above the ceiling -- a true refusal with a false
         diagnosis, the F1 defect class; green ALLOT branches on
         request sign and must say "DICT UNDERFLOW")
  EXPECTED GREEN both sides: 'large negative ALLOT refused
  (control)' (refusal happens in both states; only the
  attribution flips), 'interpreter alive after refused floor
  ALLOT', 'negative literals parse' (instrument control -- an
  unparsed negative literal would fake the floor legs green).
  OUTCOME 2026-08-25: 21/24 red -> 24/24 green, same 24 checks
  both sides.  Red: exactly the three named FAILs, landing spot
  0x2F000 hit to the byte, attribution captured as
  'DICT FULL\\r\\nok' (dict-bounds-floor-red-2026-08-25.log).
  Green: after the floor guards + sign-branched ALLOT
  (dict-bounds-floor-green-2026-08-25.log).  Different kernels,
  as they must be -- a green reusing the red's hash would mean
  the fix never assembled in.  Hashes unwrapped on purpose (a
  wrapped hash cannot be grepped or diffed, which is its job):
  red image sha256 b83802137a641a4db832ee5faac91d1a6c6f5ed22111e51a86cb03e3e6dc1b62
  green image sha256 964674c7ef002f07d2300d7dcdfd83669e10e2fc2ade810729ab10efd8ff0cfa
  Count lineage: 18 (ceiling green) -> 24 = +5 in test 3b, +1
  'negative literals parse' in test 1 -- five added in one place
  and one in another, NOT six in one.

Typed-numeral invariant: every line that pokes the dictionary
pointer carries its own DECIMAL.  The suite's val() prefix protects
its own probes; relying on that for the pokes would be the
accidental-protection pattern this project has removed four times.

Parsing discipline follows tests/test_abort.py: exact integers,
'could not determine' is a failure, echo line stripped before any
substring check.
"""
import hashlib
import re
import socket
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4597

CEILING = 0x80000
DICT_START = 0x30000
BACKSTOP_MARGIN = 1024

# Result-carries-input-hash: a quoted "Passed: N/N" must identify
# the code it ran against.  The image path comes from the caller
# (the Makefile passes $(ACTIVE_IMAGE), the same variable the QEMU
# recipe boots) so the hash is of what actually booted -- a
# hardcoded name here could identify a file QEMU never loaded,
# which is a false provenance claim, worse than no hash.
IMG = sys.argv[2] if len(sys.argv) > 2 else 'build/bmforth.img'
with open(IMG, 'rb') as f:
    print(f'input sha256 {hashlib.sha256(f.read()).hexdigest()}  {IMG}')

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
    """Set the dict pointer.  DECIMAL on the line itself: the value
    being poked is the dictionary pointer, so this line must not
    depend on what BASE the previous send left behind."""
    return send(f'DECIMAL {n} HERE !', 1.0)



def hx(v):
    """Render a pointer in hex, or repr if unreadable.  Every
    pointer in a detail string uses the same radix: the 2026-08-25
    floor red printed before= in hex and after= in decimal on the
    same line, which required hand conversion to confirm the
    pre-registered landing spot -- mixed radix in diagnostics is
    this project's sticky-BASE reading hazard wearing a harness."""
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
    """Read the dict pointer.  HERE is a DEFVAR (pushes the EQU
    address), so the value needs @ -- verified 2026-08-24:
    'HERE .' -> 28004, 'HERE @ .' -> 5E1F0 at bare boot."""
    v, raw = val('HERE @')
    return v, raw


# ---------------------------------------------------------------
print("\nTest 1: positive controls")
send('DECIMAL', 0.5)
check('interpreter alive at start', alive())
# Instrument verification for the STATE probe (the same treatment
# HERE got: print both forms before trusting either).  Test 4's
# escape-hatch leg asserts STATE @ == 0, which a broken probe --
# wrong address, value-not-address DEFVAR -- could also read.  So
# prove the probe distinguishes: it must read BOTH values.  Note
# that '[ STATE @ . ]' is the WRONG instrument on this kernel:
# '[' clears STATE before the probe runs, so it prints 0 inside a
# definition too.  An IMMEDIATE word is the right one -- it
# executes DURING compilation, reading STATE while it is 1, and
# the same word prints 0 in interpret mode.  (Residue: BT-STATE?
# and BT-PROBE stay in the dictionary; defined before h0 is
# captured so test 2's arithmetic is unaffected.  Consequence:
# this suite PERTURBS the dictionary before measuring it -- h0
# here sits above bare-boot HERE by the probes' cost (~60 bytes
# as of 2026-08-25; drifts with any probe change).  The headroom figures in
# docs/evidence/dict-headroom-2026-08-24.txt come from the G6
# harness dashboard, not from this suite's h0; keep it that way.)
send(': BT-STATE? STATE @ . ; IMMEDIATE', 1.0)
r = send('BT-STATE?', 1.0)
nums = re.findall(r'-?\d+', body_of(r))
check('STATE probe reads 0 in interpret mode',
      bool(nums) and int(nums[-1]) == 0,
      repr(body_of(r).strip()[-60:]))
r = send(': BT-PROBE BT-STATE? ;', 1.0)
nums = re.findall(r'-?\d+', body_of(r))
check('STATE probe reads 1 in compile mode',
      bool(nums) and int(nums[-1]) == 1,
      repr(body_of(r).strip()[-60:]))
# Negative-literal instrument control: test 3b's floor leg types
# a negative ALLOT.  If this kernel did not parse negative
# literals, ALLOT would never run, HERE would not move, and the
# pre-registered expected-FAIL 'floor ALLOT left HERE unchanged'
# would come back PASS in the red state -- a false green in the
# exact leg meant to expose the defect.  Verify the instrument
# can express the thing before asserting on it.
nv, raw = val('-5')
check('negative literals parse', nv == -5,
      f'got {nv!r} from {raw.strip()[-60:]!r}')
h0, raw = here()
check('HERE plausible (in dict region)',
      h0 is not None and DICT_START <= h0 < CEILING,
      f'got {h0!r} from {raw.strip()[-90:]!r}')
if h0 is None:
    print('\nPassed: 0/2 (cannot continue without a HERE reading)')
    sys.exit(1)

# ---------------------------------------------------------------
print("\nTest 2: small ALLOT round trip (guard must not tax "
      "legitimate use)")
send('DECIMAL 8 ALLOT', 1.0)
h1, raw = here()
check('8 ALLOT moved HERE by 8', h1 == h0 + 8,
      f'before={hx(h0)} after={hx(h1)}')
poke_here(h0)               # restore via direct poke (interpret
h2, _ = here()              # mode, always available by design)
check('HERE restored', h2 == h0, f'got {hx(h2)} want {hx(h0)}')

# ---------------------------------------------------------------
print("\nTest 3: overflow ALLOT is refused, before mutation")
# Size the request to cross the ceiling from wherever HERE is now,
# with 4KB to spare -- derived from this boot's own reading, not a
# frozen number.
n = (CEILING - h0) + 4096
r = send(f'DECIMAL {n} ALLOT', 2.0)
b = body_of(r)
check('overflow ALLOT refused with a message', 'DICT FULL' in b,
      repr(b.strip()[-90:]))
h3, raw = here()
check('overflow ALLOT left HERE unchanged', h3 == h0,
      f'before={hx(h0)} after={hx(h3)} (moved = unguarded)')
check('interpreter alive after refused ALLOT', alive())
if h3 is not None and h3 != h0:
    # RED-state hygiene: put the pointer back so the rest of the
    # suite still measures something.
    poke_here(h0)

# ---------------------------------------------------------------
print("\nTest 3b: floor -- negative ALLOT below DICT_START is "
      "refused")
# The guard is two-sided: below DICT_START lie the block buffers,
# TIB, and system variables, so a below-floor HERE plus one store
# is the ceiling defect with a different victim.  This probe
# demonstrates THE POINTER CROSSING THE FLOOR, deliberately not
# the corruption: the request is sized to land HERE at 0x2F000 --
# 4KB below DICT_START, in the unclaimed gap between the block
# buffers (top 0x2A200) and the dictionary -- and ALLOT stores
# nothing, so the red state measures the defect without writing
# into live sysvars.  (The store sites share the same floor check
# in the refusal routine; proving one caller fires is the same
# discipline as test 4's backstop leg.)
n = (h0 - DICT_START) + 4096    # derived from this boot's HERE
r = send(f'DECIMAL -{n} ALLOT', 2.0)
b = body_of(r)
check('floor ALLOT refused with a message', 'DICT UNDERFLOW' in b,
      repr(b.strip()[-90:]))
h3b, raw = here()
check('floor ALLOT left HERE unchanged', h3b == h0,
      f'before={hx(h0)} after={hx(h3b)} (moved = floor unguarded)')
check('interpreter alive after refused floor ALLOT', alive())
if h3b is not None and h3b != h0:
    poke_here(h0)               # RED-state hygiene
# Attribution discriminator: a LARGE negative wraps EDX above the
# ceiling unsigned, so the floor-unguarded kernel ALREADY refuses
# it -- but with "DICT FULL" for what is really an underflow (the
# F1 defect class: a true refusal carrying the wrong diagnosis).
# The green ALLOT branches on the sign of the request, so this
# same probe must say "DICT UNDERFLOW".  Refusal itself is green
# on both sides; the ATTRIBUTION is the discriminator.
r = send('DECIMAL -1000000 ALLOT', 2.0)
b = body_of(r)
check('large negative ALLOT refused (control)',
      'DICT UNDERFLOW' in b or 'DICT FULL' in b,
      repr(b.strip()[-90:]))
check('large negative ALLOT attributed as underflow',
      'DICT UNDERFLOW' in b, repr(b.strip()[-90:]))
h3c, _ = here()
if h3c is not None and h3c != h0:
    poke_here(h0)

# ---------------------------------------------------------------
print("\nTest 4: compile-path backstop fires (the guard covering "
      "the ~40 unedited inline sites)")
# Park HERE just inside the backstop margin: above CEILING-1KB so
# the backstop threshold is crossed, but with >>72 bytes below the
# ceiling so create_'s own entry check is NOT the guard that fires
# -- this leg must prove the INTERPRET backstop specifically.
park = CEILING - BACKSTOP_MARGIN + 8
poke_here(park)
r = send(': BT-X 1 ;', 2.0)
b = body_of(r)
check('compile-path backstop fired', 'DICT FULL' in b,
      repr(b.strip()[-90:]))
# Discriminator that never executes BT-X (see residue decision in
# the docstring: green leaves a dangling LATEST-reachable header
# whose body was refused; executing it is a wild jump).  Red: the
# definition completed silently, so no message and this fails too.
check('backstop blocked the definition', 'DICT FULL' in b and
      'ok' not in b.split('DICT FULL')[0].lower(),
      repr(b.strip()[-90:]))
check('interpreter alive after backstop', alive())
hb, _ = here()
# Named for what it measures: one instant, after test 3's hygiene
# poke.  The first red run proved the old name 'HERE never crossed
# the ceiling' was a lie -- it read PASS in a run where HERE had
# reached 0x81000 twelve lines earlier.
check('HERE below ceiling after backstop',
      hb is not None and hb <= CEILING,
      f'HERE={hx(hb)}')
# Escape-hatch leg: the refusal ends in ABORT, which zeroes STATE
# (forth.asm code_ABORT).  Without that, a backstop that fired on
# ';' would wedge the machine in compile mode -- the guard would
# make a full dictionary WORSE.  In the red state this passes
# trivially (the definition completed, ';' ran), so it is a
# green-side invariant, not a discriminator.
sv, raw = val('STATE @')
check('STATE cleared by refusal (escape hatch open)', sv == 0,
      f'STATE={sv!r} from {raw.strip()[-90:]!r}')
poke_here(h0)               # recovery poke: interpret mode is the
                            # deliberate escape hatch
hr, _ = here()
check('interpret-mode poke lands after refusal', hr == h0,
      f'got {hx(hr)} want {hx(h0)}')
# ---------------------------------------------------------------
print("\nTest 5: recovered -- definitions work again below the "
      "ceiling")
r = send(': BT-REC 5 5 + ;', 1.5)
check('post-restore definition compiles',
      '?' not in body_of(r) and 'DICT FULL' not in body_of(r),
      repr(body_of(r).strip()[-90:]))
v, raw = val('BT-REC')
check('post-restore definition runs (BT-REC = 10)', v == 10,
      f'got {v!r} from {raw.strip()[-90:]!r}')
check('interpreter alive at end', alive())

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
