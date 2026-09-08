#!/usr/bin/env python3
"""xHCI vocab gate, step 2a: BAR64-MASK + PCI-BAR64@ block-load.

Docket step 2 (BUS-USB-XHCI) opens here.  The 2026-09-05 iron trip
read BAR0 = 0xB1210004 at the HP's xHCI function: type bits 2:1 =
10 (64-bit BAR), upper dword at config offset 0x14 = 0.  Ruling:
PCI-BAR64@ is a correctness word -- read the upper dword, refuse
the device if nonzero.  It is NOT an enabler for >4GB MMIO
(reading 3 ruled out); ECAM stays deferred.

Placement: forth/dict/xhci.fth, BLOCK-LOADED, not embedded.  Grep
proved no boot-time caller exists (ahci.fth uses PCI-BAR@ and is
untouched); per the embed-placement rule the word lives with its
only caller.  Loading is by catalog placement + THRU, computed
host-side from the same scan write-catalog uses (the
test_driver_vocabs precedent), so the suite exercises the real
delivery path.

Word contracts under test:
  BAR64-MASK ( lo hi -- addr|0 )   pure logic, exposed for the
    refusal paths no QEMU device can produce: I/O bit set -> 0;
    type 00 -> lo FFFFFFF0 AND (hi ignored -- for a 32-bit BAR
    config offset +4 is the NEXT BAR and must never enter the
    decision); type 10 -> hi 0<> IF 0 ELSE lo FFFFFFF0 AND THEN;
    reserved types (01/11) -> 0.  FFFFFFF0 matches PCI-BAR@'s
    MMIO leg exactly (pci-enum.fth:195, read from source), which
    is what grounds the check-16 equality.
  PCI-BAR64@ ( bus dev func bar# -- addr|0 )   reads the low
    dword, branches on the type bits BEFORE touching +4, feeds
    BAR64-MASK.

Instrument controls are FATAL: liveness (1), FIND-XHCI capture
(2), host catalog resolver on RTL8139 (3), and the DEF? sanity
brackets each sys.exit(3) with a named diagnostic on failure
(3, not 2: make already uses exit 2 for a failed recipe, so the
two can never be confused in a log).  A
broken instrument on this suite produces the predicted red's
exact shape (DEF_OK False fails 6-8; a missed FIND-XHCI leaves
TB/TD/TF at 0:0.0 and RAWLO reads the host bridge), so per the
instrument rule a dead instrument must produce NO score rather
than a plausible one.

Bug-#31 fencing per test_pci_typing.py: no colon definition names
a new word until DEF? (compiled WORD FIND NIP) proves it
nameable.  ALSO XHCI is sent only after DEF? XHCI reads nonzero
-- ALSO of an undefined name corrupts the dictionary
(lesson_also_undefined_corruption).  ZAP is a counted drain
(BEGIN/WHILE/REPEAT + a countdown variable, never dropping on an
empty stack): the red run underflows the stack five times
(undefined L1-L5 print '?' but the trailing '.' still executes --
the interpreter does not ABORT, yesterday's Finding 5), an
unbounded BEGIN..DEPTH 0<> loop never terminates on a negative
depth, and Forth-83 LEAVE does not transfer control so a
DO..LEAVE..DROP..LOOP shape drops once on an already-empty stack.

Pre-registered red (2026-09-07, corrected in review before the
red run, on the tree WITHOUT forth/dict/xhci.fth): checks 4-13
and 15-17 red; checks 1-3, 14, 18 and 19 green.  14 and 18 read
type bits/upper dword with phase-0 machinery only and never touch
the new words; 19 is the BASE tripwire and nothing in a red run
enters HEX.  Red totals 6/19, exit 1.

Named prediction for the hardware leg: qemu-xhci BAR0 type bits
read 10 (matching iron) and the upper dword reads 0 -- check 18
branch A.  Named alternative: type bits 00 (32-bit BAR in QEMU),
check 18 branch B -- then the 64-bit refusal coverage rests
entirely on the BAR64-MASK literal checks 9-13, and 2e iron is
the only 64-bit-path hardware exercise.  Either branch passes 18;
type 01/11 or type 10 with nonzero upper fails it.

BASE discipline: every guest compile block brackets HEX..DECIMAL;
the final check asserts BASE reads 10 at exit (the AHCI BASE=16
escape, finding_thru_before_ahci_unexplained, is the precedent).
Guard rule (2b review): every send('HEX') and its matching
send('DECIMAL') live inside the same guard or outside all guards,
verified mechanically (indent-paired scan), not by reading.

--- Step 2b: bind / caps decode / halt / reset / handoff skeleton

Pre-registered red (2026-09-07, written before any 2b Forth; red
tree = HEAD d558668, which HAS the committed 2a xhci.fth -- no
file moves this time): 43 checks per run (44 call sites; the
placement check has an if/else pair of which one executes).
Green on red: 1-18 (2a, proven), instruments 19-20 (kernel + 2a
machinery only), 43 (BASE tripwire; no unguarded HEX on the red
path).  Red: 21-42 (every one executes a 2b word).  Red totals
21/43, exit 1.

Poll-loop failing controls (checks 27-30): the hardware
prediction is that the controller is ALREADY halted on entry, so
a poll loop that exits after zero iterations (wrong limit,
inverted mask, condition tested before first read) would pass
every hardware check.  POLL-UNTIL/POLL-CLEAR are therefore
exercised against a suite-owned VARIABLE: never-satisfied cell ->
0 after the counted limit (timeout path fires), pre-satisfied
cell -> -1 (success path reads the cell).  Halt-before-reset
ordering is enforced by suite construction (HCRST on a running
controller is undefined per spec).

Named hardware predictions (branch discipline): CAP-LEN 0x40
(range 0x20..0x7F accepted, actual printed); HCIVERSION 0x100
(named alt 0x110); pre-halt HCH=1 already-halted (named alt:
running, halt does real work; either passes, branch printed);
handoff XHCI-OWNER = 0 cap-absent (named alt 2 = present with
BIOS Owned Semaphore clear -- NOT "OS-owned", bit 24 is never
checked; 1 BIOS-owned FAILS -- that is a finding, and the
fail-closed sequence belongs to 2e).  Reset polls carry a
1000 ms budget (real silicon holds HCRST/CNR far longer than
QEMU's instant reset) and print the unmasked register on
timeout so iron can tell stuck-bit from dead-window.  XECP-FIND's visited-cap count is
printed so a runaway walk is visible even when the check passes.

Sweep arithmetic (read off sweep-2026-09-07.log, not recalled):
test-xhci line 19 -> 43 (+24), lines stay 31 (no new target, no
wiring +1), total 1098 -> 1122.
"""
import hashlib
import os
import re
import socket
import subprocess
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4594

IMG = sys.argv[2] if len(sys.argv) > 2 else 'build/combined.img'
with open(IMG, 'rb') as f:
    print(f'input sha256 {hashlib.sha256(f.read()).hexdigest()}  {IMG}')

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))


def get_vocab_blocks(vocab_name):
    """Host-side catalog placement, same scan write-catalog uses
    (test_driver_vocabs precedent; exec_module not the removed
    load_module -- Python 3.12)."""
    try:
        result = subprocess.run(
            [sys.executable, '-c', f"""
import os
import importlib.util
spec = importlib.util.spec_from_file_location('wc', os.path.join(
    '{PROJECT_DIR}', 'tools', 'write-catalog.py'))
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)
vocabs = wc.scan_vocabs(os.path.join(
    '{PROJECT_DIR}', 'forth', 'dict'))
_nc = (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
nb = 1 + _nc
for v in vocabs:
    nb = wc.place_vocab(nb, v['blocks_needed'])
    if v['name'] == '{vocab_name}':
        print(f"{{nb}} {{nb + v['blocks_needed'] - 1}}")
        break
    nb += v['blocks_needed']
"""],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            print(f'  resolver stderr: {result.stderr.strip()[:200]}')
        if result.stdout.strip():
            parts = result.stdout.strip().split()
            return int(parts[0]), int(parts[1])
    except Exception as e:
        print(f'  resolver exception: {e!r}')
    return None, None


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
    """Read one value in DECIMAL.  The DECIMAL prefix protects the
    probe only (typed-numeral invariant)."""
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
    return ok


def instrument(name, ok, detail=''):
    """A failed instrument control aborts the run (exit 3 --
    distinct from make's exit 2 for a failed recipe): no score
    beats a plausible one."""
    if not check(name, ok, detail):
        print(f'INSTRUMENT FAIL: {name} -- aborting, no score')
        sys.exit(3)


def alive():
    v, _ = val('7 6 *')
    return v == 42


print('\n=== Phase 0: instrument controls (fatal on failure) ===')
instrument('interpreter alive', alive())                     # 1
send('ONLY FORTH DEFINITIONS')
send('ALSO PCI-ENUM')
# Capture instrument: FIND-XHCI is embedded pci-enum (d9ce54a),
# present on both trees.  Stores b/d/f; val prints the flag.
send('VARIABLE TB  VARIABLE TD  VARIABLE TF')
send(': XCAP FIND-XHCI IF TF ! TD ! TB ! -1 ELSE 0 THEN ;')
v, raw = val('XCAP')
instrument('qemu-xhci found via FIND-XHCI (control)',        # 2
           v == -1, f'got {v}: {body_of(raw)!r}')
rs, re_ = get_vocab_blocks('RTL8139')
instrument('host catalog resolver resolves RTL8139 (control)',  # 3
           rs is not None, 'resolver instrument broken')
# Nameability probe + sanity brackets (fatal instrument: DEF_OK
# False would fail checks 6-8 in the predicted red's exact shape).
send(': DEF? WORD FIND NIP ;')
# Counted drain: the red run leaves a NEGATIVE depth (five
# underflows from undefined L1-L5), where an unbounded
# BEGIN..DEPTH 0<> loop spins forever.  BEGIN/WHILE/REPEAT only:
# Forth-83 LEAVE does not transfer control (it runs the rest of
# the loop body -- one extra DROP on an empty stack), and this
# kernel's LEAVE semantics are unprobed.
send('VARIABLE ZN')
send(': ZAP 64 ZN !  BEGIN DEPTH 0<> ZN @ 0> AND '
     'WHILE DROP -1 ZN +! REPEAT ;')
_pos, _ = val('DEF? PCI-FIND')
_neg, _ = val('DEF? ZZZ-NEVER-DEFINED')
DEF_OK = (_pos is not None and _pos != 0 and _neg == 0)
print(f'  probe sanity: DEF? PCI-FIND={_pos} '
      f'ZZZ-NEVER-DEFINED={_neg} -> {"OK" if DEF_OK else "BROKEN"}')
if not DEF_OK:
    print('INSTRUMENT FAIL: DEF? sanity bracket -- aborting, '
          'no score')
    sys.exit(3)
# Raw type-bit instrument: old words only, compiles on both trees.
send('HEX')
send(': RAWLO TB @ TD @ TF @ 10 PCI-READ ;')
send(': RAWHI TB @ TD @ TF @ 14 PCI-READ ;')
send('DECIMAL')


def defined(name):
    v, _ = val(f'DEF? {name}')
    return v is not None and v != 0


print('\n=== Phase 1: block-load XHCI (pre-registered red) ===')
send('ZAP')
xs, xe = get_vocab_blocks('XHCI')
check('XHCI has catalog placement',                          # 4
      xs is not None, 'forth/dict/xhci.fth absent from scan')
if xs is not None:
    print(f'  loading XHCI ({xs}-{xe} THRU)...')
    send(f'{xs} {xe} THRU', 10)
    check('XHCI blocks load (interpreter alive after THRU)',  # 5
          alive())
else:
    check('XHCI blocks load (interpreter alive after THRU)',  # 5
          False, 'no placement -- THRU not attempted')
send('ONLY FORTH DEFINITIONS')
send('ALSO PCI-ENUM')
d_vocab = defined('XHCI')
check('XHCI vocabulary defined (DEF? nonzero)', d_vocab)     # 6
if d_vocab:
    # Guarded: ALSO of an undefined name corrupts the dictionary.
    send('ALSO XHCI')
d_mask = defined('BAR64-MASK')
check('BAR64-MASK defined (DEF? nonzero)', d_mask)           # 7
d_bar = defined('PCI-BAR64@')
check('PCI-BAR64@ defined (DEF? nonzero)', d_bar)            # 8

print('\n=== Phase 2: BAR64-MASK logic (pushed literals) ===')
send('ZAP')
if d_mask:
    send('HEX')
    send(': L1 B1210004 0 BAR64-MASK B1210000 = ;')
    send(': L2 B1210004 1 BAR64-MASK 0= ;')
    send(': L3 E001 0 BAR64-MASK 0= ;')
    send(': L4 12 0 BAR64-MASK 0= ;')
    send(': L5 FEBC0008 DEADBEEF BAR64-MASK FEBC0000 = ;')
    send('DECIMAL')
v, raw = val('L1')
check('iron literal: B1210004/0 masks to B1210000',          # 9
      v == -1, f'got {v}: {body_of(raw)!r}')
v, raw = val('L2')
check('refusal: nonzero upper dword -> 0',                   # 10
      v == -1, f'got {v}: {body_of(raw)!r}')
v, raw = val('L3')
check('refusal: I/O BAR (bit 0 set) -> 0',                   # 11
      v == -1, f'got {v}: {body_of(raw)!r}')
v, raw = val('L4')
check('refusal: reserved type 01 -> 0',                      # 12
      v == -1, f'got {v}: {body_of(raw)!r}')
v, raw = val('L5')
check('32-bit type: lo masked, hi ignored',                  # 13
      v == -1, f'got {v}: {body_of(raw)!r}')

print('\n=== Phase 3: hardware path (qemu-xhci) ===')
send('ZAP')
# Type bits via old machinery: (lo >> 1) & 3 doubled = lo 6 AND.
tbits, raw = val('RAWLO 6 AND')
check('BAR0 type bits read (instrument; predicted 4=64-bit)',  # 14
      tbits in (0, 4), f'got {tbits}: {body_of(raw)!r}')
print(f'  type bits 2:1 = {"10 (64-bit)" if tbits == 4 else tbits}')
if d_bar:
    send('HEX')
    send(': XB TB @ TD @ TF @ 0 PCI-BAR64@ ;')
    send('DECIMAL')
v, raw = val('XB 0<>')
xb_nonzero = (v == -1)
check('PCI-BAR64@ at qemu-xhci nonzero', xb_nonzero,         # 15
      f'got {v}: {body_of(raw)!r}')
v, raw = val('XB TB @ TD @ TF @ 0 PCI-BAR@ =')
# Same FFFFFFF0 mask on both sides (pci-enum.fth:195): equality
# holds whenever the upper dword is 0, fails when PCI-BAR64@
# refuses (returns 0) or masks differently.
check('agrees with PCI-BAR@ (upper dword zero here)',        # 16
      xb_nonzero and v == -1, f'got {v}: {body_of(raw)!r}')
v, raw = val('XB 15 AND')
check('result 16-byte aligned (low 4 bits clear)',           # 17
      xb_nonzero and v == 0, f'got {v}: {body_of(raw)!r}')
hi, raw = val('RAWHI')
check('64-bit leg consistent: type 10 + upper 0 (A) '        # 18
      'or type 00 (B, named alternative)',
      (tbits == 4 and hi == 0) or tbits == 0,
      f'type={tbits} upper={hi}: {body_of(raw)!r}')
if tbits == 4:
    print('  branch A: 64-bit BAR, upper dword 0 (matches iron)')
elif tbits == 0:
    print('  branch B: 32-bit BAR in QEMU -- 64-bit coverage '
          'rests on checks 9-13 + 2e iron')
print('\n=== Phase 4 (2b): bind/caps/halt/reset/handoff ===')
send('ZAP')
send('ALSO HARDWARE')
# 2b instruments (fatal).  Both run on 2a-or-later machinery only,
# so they are GREEN on the 2b red run (red tree = HEAD with 2a).
v, raw = val('DEF? MS-DELAY')
instrument('MS-DELAY available after ALSO HARDWARE (control)',  # 19
           v is not None and v != 0, f'got {v}: {body_of(raw)!r}')
# Cap dword at base+0 is CAPLENGTH | HCIVERSION<<16 -- nonzero and
# never all-ones (all-ones = dead MMIO window, which would fail
# every 2b check in the predicted red's shape).
v, raw = val('XB @ DUP 0<> SWAP -1 = 0= AND')
instrument('MMIO window live at XB (control; 2a words only)',  # 20
           v == -1, f'got {v}: {body_of(raw)!r}')
d_poll = defined('POLL-UNTIL')
check('POLL-UNTIL defined (DEF? nonzero)', d_poll)           # 21
d_pollc = defined('POLL-CLEAR')
check('POLL-CLEAR defined (DEF? nonzero)', d_pollc)          # 22
d_bind = defined('XHCI-BIND')
check('XHCI-BIND defined (DEF? nonzero)', d_bind)            # 23
d_halt = defined('XHCI-HALT')
check('XHCI-HALT defined (DEF? nonzero)', d_halt)            # 24
d_reset = defined('XHCI-RESET')
check('XHCI-RESET defined (DEF? nonzero)', d_reset)          # 25
d_owner = defined('XHCI-OWNER')
check('XHCI-OWNER defined (DEF? nonzero)', d_owner)          # 26

# Poll-loop failing controls against memory the suite owns: the
# hardware is predicted ALREADY in the target state (halted), so a
# loop that exits after zero iterations would pass every hardware
# check.  Only these four prove the timeout path fires and the
# success path reads the cell.
send('VARIABLE PV')
if d_poll:
    send(': PT0 0 PV !  PV 1 8 POLL-UNTIL ;')
    send(': PT1 1 PV !  PV 1 8 POLL-UNTIL ;')
if d_pollc:
    send(': PC0 1 PV !  PV 1 8 POLL-CLEAR ;')
    send(': PC1 0 PV !  PV 1 8 POLL-CLEAR ;')
v, raw = val('PT0', 2.0)
check('POLL-UNTIL timeout fires (never-set cell -> 0)',      # 27
      v == 0, f'got {v}: {body_of(raw)!r}')
v, raw = val('PT1')
check('POLL-UNTIL prompt success (pre-set cell -> -1)',      # 28
      v == -1, f'got {v}: {body_of(raw)!r}')
v, raw = val('PC0', 2.0)
check('POLL-CLEAR timeout fires (stuck-set cell -> 0)',      # 29
      v == 0, f'got {v}: {body_of(raw)!r}')
v, raw = val('PC1')
check('POLL-CLEAR prompt success (pre-clear cell -> -1)',    # 30
      v == -1, f'got {v}: {body_of(raw)!r}')

send('ZAP')
v, raw = val('XHCI-BIND')
bind_ok = (v == -1)
check('XHCI-BIND returns -1', bind_ok,                       # 31
      f'got {v}: {body_of(raw)!r}')
v, raw = val('XHCI-BASE @ XB =')
check('XHCI-BASE matches PCI-BAR64@ (XB)',                   # 32
      bind_ok and v == -1, f'got {v}: {body_of(raw)!r}')
cl, raw = val('CAP-LEN')
check('CAP-LEN in 0x20..0x7F', cl is not None and            # 33
      32 <= cl <= 127, f'got {cl}: {body_of(raw)!r}')
if cl is not None:
    print(f'  CAP-LEN = {cl:#04x} (predicted 0x40)')
hv, raw = val('HCI-VER')
check('HCIVERSION 0x100 (predicted) or 0x110 (named alt)',   # 34
      hv in (256, 272), f'got {hv}: {body_of(raw)!r}')
if hv is not None:
    print(f'  HCIVERSION = {hv:#05x}')
v, raw = val('MAX-SLOTS')
check('MAX-SLOTS > 0', v is not None and v > 0,              # 35
      f'got {v}: {body_of(raw)!r}')
v, raw = val('MAX-PORTS')
check('MAX-PORTS in 1..255', v is not None and               # 36
      1 <= v <= 255, f'got {v}: {body_of(raw)!r}')

send('ZAP')
pre, raw = val('USBSTS@ 1 AND')
print(f'  pre-halt HCH = {pre} '
      + ('(already halted -- predicted)' if pre == 1 else
         '(running -- named alternative, halt does real work)'
         if pre == 0 else '(unreadable on this tree)'))
v, raw = val('XHCI-HALT')
check('XHCI-HALT returns -1', v == -1,                       # 37
      f'got {v}: {body_of(raw)!r}')
v, raw = val('USBSTS@ 1 AND')
check('HCH=1 after halt', v == 1, f'got {v}: {body_of(raw)!r}')  # 38
v, raw = val('XHCI-RESET', 3.0)
check('XHCI-RESET returns -1 (HCRST+CNR clear in bound)',    # 39
      v == -1, f'got {v}: {body_of(raw)!r}')
v, raw = val('USBCMD@ 1 AND')
check('post-reset R/S=0', v == 0, f'got {v}: {body_of(raw)!r}')  # 40
v, raw = val('USBSTS@ 1 AND')
check('post-reset HCH=1', v == 1, f'got {v}: {body_of(raw)!r}')  # 41

send('ZAP')
oc, raw = val('XHCI-OWNER')
check('handoff skeleton: cap absent (0, predicted) or '      # 42
      'present, BIOS bit clear (2, named alt); BIOS-owned (1) fails',
      oc in (0, 2), f'got {oc}: {body_of(raw)!r}')
print('  handoff code = ' + ('0: legacy cap absent (predicted)'
      if oc == 0 else '2: present, BIOS bit clear (named alt; '
      'OS semaphore bit 24 NOT checked)'
      if oc == 2 else f'{oc}'))
nc, raw = val('XCAPS @')
print(f'  xECP caps visited = {nc} (bounded walk; a runaway '
      'is visible here even when check 42 passes)')

raw = send('BASE @ DECIMAL .')
check('BASE tripwire: reads 10 at exit',                     # 43
      re.search(r'\b10\b', body_of(raw)) is not None,
      f'got: {body_of(raw)!r}')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
