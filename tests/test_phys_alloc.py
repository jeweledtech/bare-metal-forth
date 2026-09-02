#!/usr/bin/env python3
"""Physical allocator gate: PHYS-RELEASE, PHYS-AUDIT, owner tags.

History that earns the suite: PHYS-ALLOC (forth/dict/hardware.fth)
was a bump allocator over 0x100000-0x400000 with no free path and
no record of who allocated -- xHCI hot-plug (allocate rings/DCBAA
on device arrival, release on removal) is the workload it could
not serve.  Design measured before built (2026-08-31 probe,
docs/evidence/phys-current-probe-2026-08-30.log): all four
existing callers allocate at LOAD time under their own
DEFINITIONS, so VAR_CURRENT is a truthful owner tag today; a
run-time allocation from the prompt lands tagged FORTH -- the
phase pun, measured live.  Ruling: FORTH's cell is a distinct
third state, UNATTRIBUTED, reported on its own audit line, never
folded into a vocabulary's total.

Design under test (option b -- no tombstones):
  - Owner side table: LIVE entries only, static carve at pool
    origin (capacity derived from the ORIGIN, gated three ways in
    kernel_constants.check_phys_table()).  Entry dropped on
    release; double-release DERIVED from free-list membership --
    the free list is the only representation of freed memory, so
    there is nothing to disagree with it.
  - Refusals, all distinct, none folded: "owner table full"
    (backstop, exercised by the cap-8 fixture suite, NOT here --
    unreachable by construction with the real capacity, and a
    refusal only reachable in states nobody produces is the
    folding-branch defect), "not allocated", "double release",
    "size mismatch", and bare 0 for out-of-memory (unchanged).
    The two membership refusals are BASE-ADDRESS answers: addr+1
    inside a live allocation reads "not allocated", inside a freed
    extent reads "double release" -- both refuse, both misattribute
    interior pointers.
  - Free-list walk bounded and self-checking: node count capped at
    OWN-CAP, strictly ascending, inside the pool; loud refusal,
    never a hang.  Nodes live in the freed pages themselves, so a
    late DMA write from a badly-exited driver corrupts the
    allocator's own structure -- CUSTODIAN's founding scenario.
  - PHYS-AUDIT closing sum: live + freelist + tail + table ==
    PHYS-TOP - POOL-ORIGIN, exact.  An allocator whose accounting
    does not sum is reporting on a state it has lost track of.
  - Rounding rule: sizes are compared page-ROUNDED, so releasing
    with the original request size (e.g. 400 for MFT-BUF) is legal.

Pre-registered green addresses (derived 2026-08-31 BEFORE any
green run, from the 3-page carve + the seven boot allocations):
  CL-BUF 103000  FIS-BUF 104000  CT-BUF 105000  SEC-BUF 106000
  TX-DESC 107000  TX-BUF 108000  MFT-BUF 109000 (400 rounds to a
  page); first prompt-side allocation 10A000.

Red-first (pre-registered 2026-08-31; prediction corrected BEFORE
the run, per the T4 lesson -- a prediction corrected after seeing
the result is not a prediction).  Sequencing, not bypass: the red
runs against a tree that ALREADY carries the constants and the
static carve (inert declarations, not behavior) so the import-time
gate check_phys_table() passes and every word-level red fires by
name.  An abort is not a red, and bypassing the gate would be
changing the instrument between red and green.
  RED-STATE TREE: memory-map constants + carve in hardware.fth
  (PHYS-HEAP init moves to POOL-BASE), NO CURRENT kernel word,
  NO PHYS-RELEASE, NO PHYS-AUDIT, no table logic.
  EXPECTED RED, by name:
    - 'CURRENT kernel word exists'      (no such word yet)
    - 'PHYS-RELEASE exists'             (no free path yet)
    - 'PHYS-AUDIT exists'               (no audit yet)
    - every release/audit behavioural check downstream
  EXPECTED GREEN both sides (positive controls): liveness; ALL
  SEVEN boot addresses at their pre-registered values (the carve
  is in the red tree, so CL-BUF at 0x103000 is a positive control
  proving the carve shifted the pool BEFORE any allocator
  behavior changed); fresh alloc at 10A000 (bump path unchanged);
  exhaustion returns bare 0 (true of the old allocator too --
  the control that proves the OOM path did not change shape).
  OUTCOME: recorded in docs/evidence/phys-alloc-red-2026-09-01.log
  and phys-alloc-green-2026-09-01.log (different image hashes, as
  they must be).
  UNFREEZE NOTE: the suite frozen after red run 4 was unfrozen
  DELIBERATELY (mentor-directed, reason recorded in the run-4
  superseded log): (a) Phase 7 gained the membership-unanswerable
  leg so the refusal branch added in review does not ship as
  untested code inside a guard; (b) Phase 4 gained measured
  timing so a slow run fails by name instead of impersonating a
  coalescing defect.  Red re-run as run 5 with the re-frozen
  suite.  SECOND UNFREEZE (2026-09-01, after green run 1 came
  back 39/42): Phase 7's comment described the DEADBEEF clobber
  of the freed node's next pointer, but the store itself was
  never sent -- the suite went from release straight to audit,
  so the free list stayed healthy and all three corruption
  checks were unreachable-green: a red that could never turn.
  Fix is one line (the store the comment already specified).
  Red re-run as run 6 against the reconstructed red tree; THAT
  red pairs with the green.  Logs are named for the day the runs HAPPEN
  (2026-09-01), not the day this pre-registration was drafted
  (2026-08-31) -- the make-test-pm filename/mtime trap, recorded
  in the docket the day before, does not get in the door here.

Refusal-string contract (pinned here, honored by hardware.fth):
every named refusal begins with the prefix "PHYS: " -- e.g.
"PHYS: size mismatch".  Phase 4's no-refusal-fired check greps
for that prefix, so the prefix is load-bearing and gated: Phase 3
asserts one full prefixed string verbatim.

Audit summary contract (pinned here, honored by PHYS-AUDIT, all
figures HEX): "live: N unattributed: N", "total: N", and
"extents: N" (free-list extent count).  The extent count is the
fragmentation observable: Phase 4 asserts EQUALITY with the
pre-churn shape across 200 varying-size cycles (derivation at
the check site), the check that proves merge-on-insert
coalescing actually merges under the hot-plug workload this task
exists for.

Destructive checks (free-list corruption) run LAST: they poison
the session's free list by design, and everything after them
would be measuring the poison.
"""
import hashlib
import re
import socket
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4610

import kernel_constants
kernel_constants.check_backstop_derivation()
kernel_constants.check_pool_bounds()
kernel_constants.check_phys_table()

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


def send_timed(cmd, limit):
    """Send and poll for the trailing 'ok' prompt, up to limit
    seconds.  Returns (response, elapsed, completed).  Exists so
    a slow Phase 4 reports 'exceeded N seconds' BY NAME instead
    of draining a partial response and impersonating a
    coalescing defect (instrument failure wearing the costume of
    the finding -- fourth occurrence of the pattern).
    Drains the socket BEFORE sending: a stale ' ok ' from the
    preceding send would otherwise satisfy the break condition
    at elapsed ~0, and 'completed' would be satisfiable by the
    absence of evidence rather than the presence of it."""
    s.settimeout(0.1)
    try:
        while s.recv(4096):
            pass
    except Exception:
        pass
    s.sendall((cmd + '\r').encode())
    t0 = time.time()
    resp = b''
    s.settimeout(0.5)
    while time.time() - t0 < limit:
        try:
            d = s.recv(4096)
            if d:
                resp += d
        except Exception:
            pass
        if b'ok' in resp:
            break
    return (resp.decode('ascii', errors='replace'),
            time.time() - t0, b'ok' in resp)


def body_of(raw):
    """Drop the echoed input line (the echo contains the command's
    own characters, which would satisfy substring checks)."""
    return raw.split('\n', 1)[1] if '\n' in raw else raw


def val(expr, wait=1.5):
    """Read one value in DECIMAL.  The DECIMAL prefix on the probe
    line protects the probe only -- lines that must be radix-safe
    carry their own base word (typed-numeral invariant)."""
    raw = send(f'DECIMAL {expr} .', wait)
    body = body_of(raw)
    if '?' in body:
        return None, raw
    nums = re.findall(r'-?\d+', body)
    return (int(nums[-1]) if nums else None), raw


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


def audit(wait=4.0):
    """Run PHYS-AUDIT and parse its summary.  Returns dict or None.
    The wait is generous: the audit walks the whole table.  A hang
    (no prompt back) returns what arrived -- the corruption check
    asserts on refusal text plus liveness, so a hang fails as
    'interpreter dead', named, rather than wedging the harness."""
    raw = send('PHYS-AUDIT', wait)
    body = body_of(raw)
    out = {'raw': raw, 'body': body}
    m = re.search(r'live: ([0-9A-F]+) unattributed: ([0-9A-F]+)',
                  body)
    # audit prints in HEX (it saves/restores BASE itself)
    out['live'] = int(m.group(1), 16) if m else None
    out['unat'] = int(m.group(2), 16) if m else None
    m = re.search(r'total: ([0-9A-F]+)', body)
    out['total'] = int(m.group(1), 16) if m else None
    m = re.search(r'extents: ([0-9A-F]+)', body)
    out['extents'] = int(m.group(1), 16) if m else None
    out['mismatch'] = 'audit sum mismatch' in body
    out['corrupt'] = ('free list corrupt' in body
                      or 'free list too long' in body)
    return out


print('\n=== Phase 0: instrument controls ===')
check('interpreter alive', alive())
raw = send('HEX CURRENT @ U. DECIMAL')
check('CURRENT kernel word exists', '?' not in body_of(raw),
      'no CURRENT word -- kernel change absent')
check('CURRENT @ at prompt is FORTH cell (28048)',
      '28048' in body_of(raw),
      f'got: {body_of(raw)!r}')

print('\n=== Phase 1: boot-state allocations (pre-registered) ===')
send('ONLY FORTH DEFINITIONS')
send('ALSO AHCI')
expected = [('CL-BUF', 0x103000), ('FIS-BUF', 0x104000),
            ('CT-BUF', 0x105000), ('SEC-BUF', 0x106000)]
for name, addr in expected:
    v, raw = val(name)
    check(f'{name} at pre-registered 0x{addr:X}', v == addr,
          f'got {v if v is None else hex(v)}')
send('ONLY FORTH DEFINITIONS')
send('ALSO RTL8168')
for name, addr in [('TX-DESC', 0x107000), ('TX-BUF', 0x108000)]:
    v, raw = val(name)
    check(f'{name} at pre-registered 0x{addr:X}', v == addr,
          f'got {v if v is None else hex(v)}')
send('ONLY FORTH DEFINITIONS')
send('ALSO NTFS')
v, raw = val('MFT-BUF')
check('MFT-BUF at pre-registered 0x109000 (400 rounds up)',
      v == 0x109000, f'got {v if v is None else hex(v)}')
send('ONLY FORTH DEFINITIONS')
# The allocator words live in the HARDWARE vocabulary; ONLY FORTH
# dropped it and find_'s FORTH fallback does not reach vocab
# words.  Without this, every PHYS-* send reads '?' -- the
# instrument defect that invalidated red run 1 (see
# phys-alloc-red-run1-invalid-2026-09-01.log).
send('ALSO HARDWARE')

a = audit()
check('PHYS-AUDIT exists', a['live'] is not None,
      f'no parseable summary: {a["body"]!r}')
check('boot audit: live 7', a['live'] == 7, f'got {a["live"]}')
check('boot audit: unattributed 0 (all 7 tagged by owner)',
      a['unat'] == 0, f'got {a["unat"]}')
check('boot audit sum closes to 300000', a['total'] == 0x300000
      and not a['mismatch'], f'total={a["total"]}')

print('\n=== Phase 2: release and reuse ===')
raw = send('HEX 1000 PHYS-ALLOC U. DECIMAL')
check('fresh alloc at pre-registered 10A000',
      '10A000' in body_of(raw), f'got: {body_of(raw)!r}')
raw = send('HEX 10A000 1000 PHYS-RELEASE DECIMAL')
check('PHYS-RELEASE exists', '?' not in body_of(raw),
      'no PHYS-RELEASE word -- free path absent')
raw = send('HEX 1000 PHYS-ALLOC U. DECIMAL')
check('re-alloc reuses freed extent (10A000 again)',
      '10A000' in body_of(raw), f'got: {body_of(raw)!r}')
a = audit()
check('live == 8 (7 boot + 1 held)',
      a['live'] == 8, f'got {a["live"]}')

print('\n=== Phase 3: refusals, each by name ===')
# size mismatch: the live 10A000 alloc was 1000; claim 2000.
# Full prefixed string verbatim -- this is the check that GATES
# the "PHYS: " prefix contract Phase 4 depends on.
raw = send('HEX 10A000 2000 PHYS-RELEASE DECIMAL')
check('size mismatch refused by name (full prefixed string)',
      'PHYS: size mismatch' in body_of(raw),
      f'got: {body_of(raw)!r}')
a = audit()
check('mismatched release left the allocation live',
      a['live'] == 8, f'got {a["live"]}')
# rounding rule: release with an unrounded size that rounds right
raw = send('HEX 10A000 FFF PHYS-RELEASE DECIMAL')
check('release with unrounded size (rounding rule)',
      'mismatch' not in body_of(raw)
      and '?' not in body_of(raw), f'got: {body_of(raw)!r}')
# positive discriminator: the rounding-rule release ACTUALLY
# released -- occupancy dropped 8 -> 7.  Without this, the check
# above only proves the refusal didn't fire, not that the release
# happened (a no-op would also print nothing).
a = audit()
check('rounding-rule release took effect (live 8 -> 7)',
      a['live'] == 7, f'got {a["live"]}')
# double release: same base again -- now inside a freed extent
raw = send('HEX 10A000 1000 PHYS-RELEASE DECIMAL')
check('double release refused by name',
      'double release' in body_of(raw), f'got: {body_of(raw)!r}')
# never allocated: in-pool address no one owns
raw = send('HEX 123000 1000 PHYS-RELEASE DECIMAL')
check('never-allocated refused by name',
      'not allocated' in body_of(raw), f'got: {body_of(raw)!r}')
# The two membership refusals ('double release' vs 'not
# allocated') are distinct strings by construction; the two
# checks above each match their own name, which is the actual
# runtime evidence -- a check(..., True) here would be a
# tautology, not an observable.

print('\n=== Phase 4: 200 varying alloc/release cycles ===')
a0 = audit()
send(': PACYC 0 DO I 7 AND 1+ 1000 * DUP PHYS-ALLOC'
     ' SWAP PHYS-RELEASE LOOP ;')
# Measured calibration, not a round number: run 10 cycles, scale
# by 20x with 3x slack, floor 30s.  A timeout here fails BY NAME
# ('exceeded'), and liveness is asserted BEFORE the audit read,
# so a slow run cannot present as a wrong extent count.
raw10, t10, done10 = send_timed('HEX A PACYC DECIMAL', 30.0)
check('10-cycle calibration completed', done10,
      f'elapsed {t10:.1f}s, no ok prompt')
limit = max(30.0, t10 * 20 * 3)
raw, t, done = send_timed('HEX C8 PACYC DECIMAL', limit)
check('200 cycles completed, not exceeded time budget',
      done, f'exceeded {limit:.0f}s (elapsed {t:.1f}s)')
check('interpreter alive after churn (before audit read)',
      alive())
check('no refusal fired during cycles',
      'PHYS:' not in body_of(raw10) and 'PHYS:' not in
      body_of(raw), f'got: {body_of(raw10)!r} {body_of(raw)!r}')
a1 = audit()
# not-None required: None == None would pass while asserting
# nothing (a delivery flag is not content)
check('flat occupancy across 200 cycles',
      a0['live'] is not None and a0['live'] == a1['live'],
      f'{a0["live"]} -> {a1["live"]}')
check('audit sum still closes after churn',
      a1['total'] == 0x300000 and not a1['mismatch'],
      f'total={a1["total"]}')
# Flat live count proves the TABLE doesn't leak; it says nothing
# about the free list.  200 varying-size cycles that each return
# what they took must coalesce -- "coalescing that never merges
# is a slower leak, not a fix" (original spec).  EQUALITY, not a
# tolerance, and it is derived: the churn opens with one free
# extent abutting the bump frontier, every cycle returns exactly
# what it took, and any bump-extended allocation is adjacent to
# that frontier extent -- so merge-on-insert (both directions:
# predecessor and successor) folds every release back to the
# pre-churn shape.  A +1 hedge here would be a place a
# coalescing defect could live rent-free.
check('free list returned to pre-churn shape (extents ==)',
      a0['extents'] is not None
      and a1['extents'] == a0['extents'],
      f'{a0["extents"]} -> {a1["extents"]} extents')

print('\n=== Phase 5: unattributed detection ===')
# a colon definition executed from the prompt allocates at RUN
# time with CURRENT = FORTH's cell -- the measured pun, permitted
# for operators, reported as its own class
send(': PATST HEX 1000 PHYS-ALLOC DROP DECIMAL ;')
send('PATST')
a = audit()
check('prompt-side run-time alloc counted unattributed',
      a['unat'] == 1, f'got {a["unat"]}')
check('boot allocations still attributed (unat exactly 1)',
      a['unat'] == 1 and a['live'] == 8,
      f'live={a["live"]} unat={a["unat"]}')

print('\n=== Phase 6: exhaustion is bare 0, not table-full ===')
raw = send('HEX 400000 PHYS-ALLOC U. DECIMAL')
check('oversize alloc returns 0', re.search(r'\b0\b',
      body_of(raw)) is not None, f'got: {body_of(raw)!r}')
check('OOM did NOT say table full (distinct refusals)',
      'table full' not in body_of(raw), f'got: {body_of(raw)!r}')

print('\n=== Phase 7 (destructive, last): corrupted free list ===')
raw = send('HEX 1000 PHYS-ALLOC U. DECIMAL')
m = re.search(r'\b1[0-9A-F]{5}\b', body_of(raw))
check('corruption-victim alloc succeeded', m is not None,
      f'got: {body_of(raw)!r}')
victim = m.group(0) if m else '10B000'
send(f'HEX {victim} 1000 PHYS-RELEASE DECIMAL')
# clobber the node the allocator keeps INSIDE the freed page:
# the freed extent's node lives at the freed page base, next
# pointer at offset 0.
send(f'HEX DEADBEEF {victim} ! DECIMAL')
# DEADBEEF as a next pointer is ASCENDING (greater than any pool
# address) but OUTSIDE the pool -- of the walk's three checks
# (node cap / ascending / in-pool), exactly the in-pool bound
# fires.  So the expected refusal is "free list corrupt" by
# name; "free list too long" here would mean the wrong check
# caught it (the cap masking a bounds defect).
a = audit(wait=6.0)
check('audit refused with "free list corrupt" (in-pool check)',
      'free list corrupt' in a['body'], f'got: {a["body"]!r}')
check('walk did NOT misreport as too-long (wrong discriminator)',
      'free list too long' not in a['body'],
      f'got: {a["body"]!r}')
check('interpreter alive after refusal', alive(),
      'walk hung or crashed -- refusal must be loud AND survivable')
# The membership question against a corrupted list: PHYS-RELEASE
# must honor the walk's verdict, not print a confident verdict
# derived from the truncated prefix.  Both halves matter: the
# named refusal appearing, AND neither membership verdict
# appearing -- the second half is the actual fix (the old code
# would print 'unanswerable' checks green while still emitting
# a verdict afterward).
raw = send('HEX 123000 1000 PHYS-RELEASE DECIMAL', 6.0)
check('release on corrupt list: membership unanswerable by name',
      'PHYS: membership unanswerable' in body_of(raw),
      f'got: {body_of(raw)!r}')
check('release on corrupt list: NO membership verdict printed',
      'double release' not in body_of(raw)
      and 'not allocated' not in body_of(raw),
      f'got: {body_of(raw)!r}')
check('interpreter alive after unanswerable refusal', alive())

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
