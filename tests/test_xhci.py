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

--- Step 2c: DCBAA / command+event rings / Running / NOP round-trip

Pre-registered red (2026-09-07, written before any 2c Forth; red
tree = HEAD 5cf99a2, which has 2a+2b live): 67 checks per run
(68 call sites; the phase-1 placement pair is unchanged).  Green
on red: 1-42 (2a/2b, proven), instruments 43-45 (2b + HARDWARE
machinery only), 63 (absence check -- vacuously, which is exactly
why 64 exists), 64 (presence control, HARDWARE machinery only),
65-66 (restore pair -- nothing net-allocated on red), 67 (BASE
tripwire).  Red: 46-62, every one executing a 2c word or
measuring its allocation effect (52's NLIVE delta is 0 on red
because the failed XHCI-UP allocates nothing).  Red totals
50/67, exit 1.

RED RE-REGISTERED 2026-09-09 (first red run 49/67, a mismatch
= a finding; bisect /tmp/bisect_2c_run2.log): (1) check 50 was
GREEN on red -- .H8 already exists (pci-enum.fth:396,
base-transparent by construction), a pre-registration walk
error; the 2b debt shrinks to rerouting XHCI-RESET's prints
through it.  (2) checks 64-66 were RED on red -- NOT an
allocator bug: sending the absent 2c words underflowed SP
('?' does not abort the line), DEPTH then read ~2^30, and the
old DEPTH-trusting ZAP marched SP past the stack floor until
the target WARM-RESET silently (Bug #35, kernel debt), scoring
plausible FAILs against a kernel-only dictionary.  Remedies in
this file: DEF?-guard scores 51-63 red WITHOUT sending them
when any of 46-49 is absent (one guard-loop call site; 69 call
sites total, still 67 checks/run); ZAP refuses an implausible
DEPTH via ZBAD + fatal zap() wrapper; SESS-NONCE continuity
probe (unscored, fatal) at every phase boundary and before the
score.  Corrected red: green 1-45, 50, 64-67; red 46-49 and
51-63 (17).  Red totals 50/67, exit 1.  Named alternative: if
64-66 fail again WITH the guards in place, the reset
explanation is incomplete -- stop and investigate.

--- Step 2d: PORTSC decode + port survey (READ-ONLY)

Pre-registered red (2026-09-09, written before any 2d Forth; red
tree = HEAD 48e2404, 2a-2c live).  Fixture adds -device usb-kbd;
neutrality was MEASURED first, decoupling the two variables: the
unmodified 67 ran 67/67 under the new fixture with zero PASS-line
diffs (xhci-2d-neutrality log; the one info-line change is
pre-halt HCH=0 -- SeaBIOS starts the controller to drive the
keyboard, which hardware-proves XHCI-HALT's does-real-work branch
for free).  PSCE question settled with DATA, not inheritance:
recon part 2 dumped the event ring after UP/RUN/32 NOPs under the
fixture -- 32 consumed TRBs, all type-33 command-completions
cc=1, zero port-status-change events, beyond-slots zeroed
(xhci-2d-recon log).  NOP1 never inspects TRB type, so 2c's 32/32
alone proved tolerance, not absence; the dump proves absence.

Decoder controls (72-83) feed the two dwords measured in recon --
occupied 0x0E03, empty 0x202A0 -- as decimal literals (3587,
131744): decode proven with hardware never consulted, and no HEX
send exists anywhere in phase 6.  Invariant-vs-incidental rule:
#CONNECTED=1 and the FIRST-CCS identity are asserted; WHICH port
(recon: 5) and its speed code (recon: 3) are printed, not pinned
-- a QEMU attach-order reshuffle is a log line, not a red.
Bounds guard on PORTSC-ADDR is tested on both sides (84-85) --
the guard-with-no-test lesson.  Read-only is proven twice: the
source-side no-write rule (weak: catches writes that look like
writes) and check 98's twice-read byte-identity (load-bearing:
catches a leaked RW1C clear from anywhere).

Pre-registered red: 99 checks per run (82 check call sites by
AST; the 2c guard contributes 13 either way, the 2d guard 27
either way, loops counted as one site each).  Green on red:
1-66 (proven under the fixture by the neutrality run), 71
(MAX-PORTS pin, 2b machinery only), 99 (BASE tripwire; phase 6
sends no HEX).  Red: 67-70 (presence) and 72-98 (guarded, not
sent -- Bug #35 rule).  Red totals 68/99, exit 1.  Named
alternative: any of 1-66 red under the unchanged fixture means
the neutrality measurement was unstable -- stop, re-run
neutrality twice before touching anything.

AMENDED 2026-09-09 after green 1 (97/99): checks 89 and 92
failed exactly as the occupied-port named alternative allowed
-- the recon measured COLD-BOOT port state (SeaBIOS had enabled
the port to drive the keyboard), but phase 6 reads POST-HCRST
state.  Stage probe (xhci-2d-stages log) pinned the transition
to XHCI-RESET alone: 0x0E03 -> 0x20EE1 at HCRST (PED 1->0,
CSC 0->1, PLS 0->7 Polling, CCS and speed preserved), stable
through UP/RUN/NOP/DOWN.  Corrected expectations: 89 = PED
false (HCRST cleared the enable; re-enable is a step-3 port
reset), 92 = CSC true (re-detection set the change bit).  The
decode controls 72-83 still carry the cold-boot dwords -- they
are constants proving the decoders, not state claims.  Red
re-run owed after the name changes; red arithmetic unchanged
(68/99, exit 1).

2E PREP (2026-09-10): phase 7 adds the trip machinery -- the
handoff request (the third outcome's missing code), the
SMI-clear, the HCRST elapsed capture, the fixed-base display
reroute, and the memdisk-gate discriminator.  qemu-xhci has NO
legacy cap (handoff code 0, measured in 2b), so (CLAIM) and
(SMI-OFF) take an ADDRESS (the 2b poll-control pattern) and run
against suite-owned cells; the wrappers XHCI-CLAIM / SMI-OFF
are the card's exact lines and prove outcome A in the QEMU
habitat.  Rulings encoded: uniform claim on cap-present (105
asserts the OS-owned bit is written even when BIOS never held
it -- "yielded" vs "never held" stay distinguishable only as
the OWNER/CLAIM pair, which the desk card records adjacently);
SMI-clear is read-record-conditional-write (111: an
already-clear cell is BYTE-IDENTICAL afterwards, which proves
no write happened, because any write ORs 0xE0000000 in); .PSC
renders '15 pls' while BASE=16 (123 -- the exact ambiguity that
opened the debt), and .PORTS -- the looped display that
actually goes to iron -- must emit MAX-PORTS lines (127).
SMI masks were VERIFIED against Linux xhci-ext-caps.h fetched
2026-09-10 (the header cites spec section 7.1.2), not recalled:
preserve mask 0xE1FEE, RW1C events 0xE0000000, enable-detect
0xE011 including bit 4 (SMI on Host System Error); the
bit-4-only control (114-115) exists because both bulk fixtures
would pass under a detect mask that silently misses it.  .D
avoids >R/R> (BASE @ SWAP DECIMAL . BASE !) because .PORTS
calls it inside DO..LOOP and this project deliberately keeps
>R out of DO..LOOP bodies.  MEMDISK-BASE@ = 0 in QEMU proves
the card gate's REFUSAL side (128); the iron pass side is
pre-registered from measurement, not assumption: nonzero AND
4KiB-aligned, prior reading 0x37BB7000 on the HP 2026-09-05
(the then-unnamed page-aligned pointer probed at 0x28098 --
the mystery cell now has a name; a different boot may relocate
it, alignment and nonzero are the invariant).  PN is shared
(2b), so HRST-LEFT is the only surviving copy of the HCRST
figure; the card must read CNR's 3E8 PN @ - on the same line
as XHCI-RESET or the next poll destroys it.  Untestable in
this habitat, named: (CLAIM)'s released-after-held timing (no
concurrent BIOS to clear the bit mid-poll) and (SMI-OFF)'s
code-2 write-didn't-stick arm (RAM always sticks) -- both are
iron-only branches and the card treats code 2 as a STOP.

Pre-registered red for 2e prep (tree = b912a37 with the suite
extension only, 2e-prep words absent): 130 checks per run (113
check call sites by AST, same site-counting rule as 2d's 82,
plus a ninth instrument; the 2c guard contributes 13, the 2d
guard 27, the 2e guard 26, each either way).  Green on red:
1-98 (unchanged tree and fixture -- the 2d green), 99
(control-cell instrument, kernel machinery only), 130 (BASE
tripwire: phase 7's HEX sends are bracketed by explicit DECIMAL
restores, and .D's own restore is under test).  Red: 100-103
(presence) and 104-129 (guarded, not sent -- Bug #35 rule).
Red totals 100/130, exit 1.  Named alternative: any of 1-98 red
means the 2d green was unstable on an unchanged tree -- stop
and re-run a plain green at HEAD before touching anything.

ALLOCATOR-INTERNALS DEPENDENCY (read this before changing
hardware.fth): the suite probes NLIVE and AVAIL walk HARDWARE's
owner table (OWN-CAP / OWN-SLOT, size at record offset 0) and
free list (FL-ADDR / FL-WALK / FL-TOT, plus the PHYS-HEAP /
PHYS-HEAP-END bump tail) DIRECTLY.  This suite depends on
allocator internals, not just its API: a change to the owner
record layout, the free-list node shape, or FL-WALK's side
variables breaks these probes first.  Update them together with
hardware.fth.  AVAIL returns -1 (impossible as a real byte
count) when FL-WALK refuses, so a corrupt list cannot alias a
valid total.

Refusal legs (three, and only together do they say anything):
(a) clean arm -- XHCI-UP, run, 32-NOP round-trip, XHCI-DOWN ->
-1, then a second XHCI-DOWN -> 0 (nothing to tear down);
(b) refusal arm -- XHCI-UP again, the SUITE releases the DCBAA
page directly (valid base+size, so it succeeds silently), then
XHCI-DOWN must cross-check each record against the owner table
(OWN-FIND + size match) BEFORE releasing, skip the vanished
record, release the rest, and return 1 (partial).  The log must
NOT contain "PHYS: double release" -- an absence assertion,
vacuous alone;
(c) presence control -- the suite double-releases a page
DIRECTLY (not through XHCI-DOWN) and asserts the message DOES
appear, proving the guard text is live and the transcript
carries it.  Net allocation effect of all three legs is zero,
so the restore pair (65-66) closes over everything since the
phase-5 snapshot.

Named hardware predictions: scratchpad count 0 in QEMU (named
alt >0 -- XHCI-UP then allocates the array page plus one
contiguous buffer block, two more owner records, XSPA nonzero;
actual printed either way); 32 NOPs complete 32/32 with the
16-TRB ring (link TRB slot 15, toggle-cycle) wrapped twice --
XENQ predicted 2 and XEDQ predicted 32 are printed alongside
the count, because a link-toggle stall dies at the first wrap
(count pins near 15) while an ERDP stall pins XEDQ with the
count short -- the pair localizes which; running proof is the
HCH 1->0 transition (CRCR reads back ~0 by spec, so it proves
nothing); XHCI-DOWN codes: -1 all released / 0 nothing to tear
down / 1 partial refusal.  Word/variable contract with
xhci.fth: XDCBAA XCRING XERING XERST XSPA (allocation records,
0 = not held), XENQ XCCS (command ring producer), XEDQ XECS
(event ring consumer), XHCI-UP XHCI-RUN NOP-TEST XHCI-DOWN.
Event-ring polling honors POLL non-re-entrancy: single-level
only, never nested.

.H8 fold-in (2b debt): XHCI-RESET's two timeout prints rendered
in the caller's BASE; 2c lands .H8 ( x -- ) -- fixed 8-digit hex
regardless of BASE -- and reroutes both prints through it.
Check 50 proves the fixed-base property from DECIMAL.

Sweep arithmetic (read off sweep-2026-09-07b.log, not
recalled): test-xhci line 43 -> 67 (+24), lines stay 31 (no new
target, no wiring), total 1122 -> 1146.
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


# ---- QEMU HMP monitor (step 4 fixture, design §4) ----
# argv[3] = monitor TCP port (Makefile: TEST_PORT_BASE+93; the design
# said +95 but that offset is test-block-reload's).  `sendkey` is the
# only way to make QEMU's usb-kbd produce a report and `device_del kbd`
# the only way to unplug it, so a silent monitor would turn every
# keystroke check into a plausible red against nothing.
MON_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else PORT - 1
_mon = None


def mon(cmd, wait=0.5):
    """Send one HMP command, return the text up to the next prompt."""
    global _mon
    if _mon is None:
        _mon = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _mon.settimeout(5)
        _mon.connect(('127.0.0.1', MON_PORT))
        _mon_read_prompt()            # banner + first "(qemu) "
    _mon.sendall((cmd + '\n').encode())
    time.sleep(wait)
    return _mon_read_prompt()


def _mon_read_prompt():
    buf = b''
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            d = _mon.recv(4096)
        except socket.timeout:
            break
        if not d:
            break
        buf += d
        if buf.rstrip().endswith(b'(qemu)'):
            break
    return buf.decode('ascii', errors='replace')


def instrument_unscored(name, ok, detail=''):
    """Fatal like instrument(), but NOT counted in PASS/FAIL: the
    design pre-registers the monitor control as 'unscored for the
    headline but printed', so the 242 baseline does not move."""
    if ok:
        print(f'  INSTRUMENT: {name} -- OK')
    else:
        print(f'  INSTRUMENT FAIL: {name} -- {detail} -- aborting, no score')
        sys.exit(3)


print('\n=== Phase 0: instrument controls (fatal on failure) ===')
try:
    _ver = mon('info version')
except OSError as e:
    _ver = f'(no monitor: {e!r})'
instrument_unscored('monitor answers info version (control)',
                    re.search(r'\d+\.\d+\.\d+', _ver) is not None,
                    f'got {_ver!r}')
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
# Counted drain, DEPTH-sanity-bounded (2026-09-09 correction):
# an underflowed stack does NOT read as negative DEPTH -- it
# reads ~2^30 (observed 0x3FFFFFFF, Bug #35), so a drain that
# trusts DEPTH marches SP 256 bytes past the floor per call and
# the FOURTH call warm-resets the target silently.  ZAP now
# refuses an implausible reading (negative OR > 1024) and flags
# ZBAD; the zap() wrapper aborts the run on refusal -- no score
# beats a plausible one scored against a rebooted machine.
# BEGIN/WHILE/REPEAT only: Forth-83 LEAVE does not transfer
# control, and this kernel's LEAVE semantics are unprobed.
send('VARIABLE ZN')
send('VARIABLE ZBAD')
send(': ZAP 0 ZBAD !  DEPTH DUP 0< SWAP 1024 > OR '
     'IF -1 ZBAD ! EXIT THEN '
     '64 ZN !  BEGIN DEPTH 0<> ZN @ 0> AND '
     'WHILE DROP -1 ZN +! REPEAT ;')
# Session nonce (2026-09-09): a warm reset reverts the dictionary
# to kernel-only and every later check scores a PLAUSIBLE fail
# against the wrong machine (it forged the mid-chain-break
# signature for a day).  Re-probed at every phase boundary; if it
# is gone the target rebooted -- named diagnostic, exit 3, no
# score.  Continuity probes are unscored (not check()), so the
# 67-check numbering is unchanged.
send(': SESS-NONCE 20260909 ;')
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


def zap():
    """Drain the stack; abort (no score) if ZAP refused an
    implausible DEPTH -- the Bug-#35 underflow shape."""
    send('ZAP')
    v, raw = val('ZBAD @')
    if v != 0:
        print('INSTRUMENT FAIL: ZAP refused -- DEPTH implausible '
              f'(underflow, Bug #35 shape), ZBAD={v}: '
              f'{body_of(raw)!r} -- aborting, no score')
        sys.exit(3)


def continuity(where):
    """Session-continuity probe: SESS-NONCE gone = the target
    warm-reset underneath the suite.  Unscored; fatal."""
    v, raw = val('SESS-NONCE')
    if v != 20260909:
        print(f'CONTINUITY FAIL: target rebooted before {where} '
              f'(SESS-NONCE={v}: {body_of(raw)!r}) -- aborting, '
              'no score')
        sys.exit(3)
    print(f'  continuity: nonce OK ({where})')


print('\n=== Phase 1: block-load XHCI (pre-registered red) ===')
continuity('phase 1')
zap()
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
continuity('phase 2')
zap()
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
continuity('phase 3')
zap()
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
continuity('phase 4')
zap()
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

zap()
v, raw = val('XHCI-BIND')
bind_ok = (v == -1)
check('XHCI-BIND returns -1', bind_ok,                       # 31
      f'got {v}: {body_of(raw)!r}')
v, raw = val('XHCI-BASE @ XB =')
check('XHCI-BASE matches PCI-BAR64@ (XB)',                   # 32
      bind_ok and v == -1, f'got {v}: {body_of(raw)!r}')
cl, raw = val('CAP-LEN')
check('CAP-LEN in 0x20..0x80', cl is not None and            # 33
      32 <= cl <= 128, f'got {cl}: {body_of(raw)!r}')
# Upper bound raised 0x7F -> 0x80 after the 2e iron trip measured
# CAP-LEN = 0x80 on HP 15-bs0xx (docs/evidence/xhci-iron-2026-09-10.log).
# The old bound was tuned to QEMU's 0x40 and falsified by real silicon.
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

zap()
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

zap()
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

print('\n=== Phase 5 (2c): DCBAA/rings/Running/NOP round-trip ===')
continuity('phase 5')
zap()
# Entry instrument (user ruling): the pre-run HCH=1 premise is
# ASSERTED here, not assumed from check 41 -- 2b words only, so
# green on the 2c red tree.
v, raw = val('USBSTS@ 1 AND')
instrument('HCH=1 at phase-5 entry (control; 2b words only)',  # 43
           v == 1, f'got {v}: {body_of(raw)!r}')
# Internals-visibility instrument: NLIVE/AVAIL walk HARDWARE's
# owner table and free list directly (see docstring).  DEF?
# results are XTs, so normalize each with 0<> before AND.
v, raw = val('DEF? OWN-SLOT 0<> DEF? FL-WALK 0<> AND '
             'DEF? PHYS-RELEASE 0<> AND')
instrument('HARDWARE allocator internals visible (control)',  # 44
           v == -1, f'got {v}: {body_of(raw)!r}')
# Probes compile on both trees (HARDWARE words only).  AVAIL's
# -1 leg makes a refused walk visible instead of aliasing 0.
send('VARIABLE NLV')
send(': NLIVE 0 NLV !  OWN-CAP 0 DO '
     'I OWN-SLOT @ 0= 0= IF NLV @ 1+ NLV ! THEN '
     'LOOP NLV @ ;')
send(': AVAIL 0 FL-ADDR !  FL-WALK 0= IF -1 EXIT THEN '
     'FL-TOT @ PHYS-HEAP-END @ PHYS-HEAP @ - + ;')
AV0, raw = val('AVAIL', 2.0)
instrument('AVAIL sane at snapshot (walk clean, >= 0)',       # 45
           AV0 is not None and AV0 >= 0,
           f'got {AV0}: {body_of(raw)!r}')
NL0, _ = val('NLIVE', 2.0)
print(f'  phase-5 snapshot: NLIVE={NL0} AVAIL={AV0}')

d_up = defined('XHCI-UP')
check('XHCI-UP defined (DEF? nonzero)', d_up)                # 46
d_run = defined('XHCI-RUN')
check('XHCI-RUN defined (DEF? nonzero)', d_run)              # 47
d_nop = defined('NOP-TEST')
check('NOP-TEST defined (DEF? nonzero)', d_nop)              # 48
d_down = defined('XHCI-DOWN')
check('XHCI-DOWN defined (DEF? nonzero)', d_down)            # 49
# .H8 fold-in (2b debt): fixed 8-digit hex regardless of BASE.
d_h8 = defined('.H8')
if d_h8:
    send(': H8T 255 .H8 ;')
raw = send('H8T')
check('.H8 fixed-base: 255 prints 000000FF from DECIMAL',    # 50
      '000000FF' in body_of(raw), f'got: {body_of(raw)!r}')

# Bug-#35 execution guard (2026-09-09): on a tree where the 2c
# words are absent, sending them anyway underflows SP ('?' does
# not abort the line, the trailing ops still pop), DEPTH then
# reads ~2^30, and a drained march past the stack floor
# warm-resets the target -- which then scores plausible FAILs
# against a kernel-only dictionary.  Checks 51-63 are scored
# red WITHOUT being sent when any DEF? probe came back absent.
ALL_2C = d_up and d_run and d_nop and d_down
if ALL_2C:
    zap()
    v, raw = val('XHCI-UP', 3.0)
    up_ok = (v == -1)
    check('XHCI-UP returns -1', up_ok,                           # 51
          f'got {v}: {body_of(raw)!r}')
    sc, _ = val('XSPA @')
    print('  scratchpads: ' + ('none demanded (XSPA=0, predicted)'
          if sc == 0 else f'XSPA={sc} (named alternative: HCSPARAMS2 '
          'demanded buffers)' if sc is not None else
          'unreadable on this tree'))
    nl1, raw = val('NLIVE', 2.0)
    check('XHCI-UP allocated something (NLIVE delta > 0)',       # 52
          nl1 is not None and NL0 is not None and nl1 - NL0 > 0,
          f'NLIVE {NL0} -> {nl1}: {body_of(raw)!r}')
    if up_ok:
        # Readback probes: DCBAAP at OP-BASE+30, ERSTBA at runtime
        # base (RTSOFF = cap+18, mask FFFFFFE0) + interrupter-0
        # +10 past its +20 origin = +30.  Reserved low bits masked
        # inside the guard so the DECIMAL probes stay literal-free.
        send('HEX')
        send(': QDCB OP-BASE 30 + @ FFFFFFC0 AND ;')
        send(': QERB XHCI-BASE @ 18 + @ FFFFFFE0 AND '
             'XHCI-BASE @ + 30 + @ FFFFFFC0 AND ;')
        send('DECIMAL')
    v, raw = val('QDCB XDCBAA @ =')
    check('DCBAAP readback matches XDCBAA record', v == -1,      # 53
          f'got {v}: {body_of(raw)!r}')
    v, raw = val('QERB XERST @ =')
    check('ERSTBA readback matches XERST record', v == -1,       # 54
          f'got {v}: {body_of(raw)!r}')

    v, raw = val('XHCI-RUN', 3.0)
    check('XHCI-RUN returns -1 (HCH cleared in budget)',         # 55
          v == -1, f'got {v}: {body_of(raw)!r}')
    v, raw = val('USBSTS@ 1 AND')
    check('running proof: HCH 1 -> 0 transition', v == 0,        # 56
          f'got {v}: {body_of(raw)!r}')

    zap()
    v, raw = val('32 NOP-TEST', 6.0)
    check('32 NOPs complete 32/32 (16-TRB ring wrapped twice, '  # 57
          'link-toggle executed)', v == 32,
          f'got {v}: {body_of(raw)!r}')
    enq, _ = val('XENQ @')
    edq, _ = val('XEDQ @')
    print(f'  completions = {v}, XENQ = {enq} (predicted 2), '
          f'XEDQ = {edq} (predicted 32) -- a link-toggle stall '
          'pins the count near 15; an ERDP stall pins XEDQ short')

    v, raw = val('XHCI-DOWN', 3.0)
    check('XHCI-DOWN (clean arm) returns -1 (all released)',     # 58
          v == -1, f'got {v}: {body_of(raw)!r}')
    v, raw = val('USBSTS@ 1 AND')
    check('HCH=1 after XHCI-DOWN (stopped before release)',      # 59
          v == 1, f'got {v}: {body_of(raw)!r}')
    v, raw = val('XHCI-DOWN')
    check('second XHCI-DOWN returns 0 (nothing to tear down)',   # 60
          v == 0, f'got {v}: {body_of(raw)!r}')

    # Refusal arm: the suite releases the DCBAA page directly
    # (valid base + size -> silent success), then XHCI-DOWN must
    # skip the vanished record via its owner-table cross-check.
    zap()
    v, raw = val('XHCI-UP', 3.0)
    up2 = (v == -1)
    check('XHCI-UP (refusal arm) returns -1', up2,               # 61
          f'got {v}: {body_of(raw)!r}')
    if up2:
        send('XDCBAA @ 4096 PHYS-RELEASE')
    v, down_raw = val('XHCI-DOWN', 3.0)
    check('XHCI-DOWN after direct release returns 1 (partial: '  # 62
          'vanished record skipped, rest released)', v == 1,
          f'got {v}: {body_of(down_raw)!r}')
    # Absence assertion -- vacuous alone (passes on red, passes if
    # the message text drifted); check 64 is its presence control.
    check('refusal arm emitted no "PHYS: double release" '        # 63
          '(cross-check skipped, did not re-release)',
          'PHYS: double release' not in body_of(down_raw),
          f'got: {body_of(down_raw)!r}')
else:
    for _name in (
        'XHCI-UP returns -1',                            # 51
        'XHCI-UP allocated something (NLIVE delta > 0)', # 52
        'DCBAAP readback matches XDCBAA record',         # 53
        'ERSTBA readback matches XERST record',          # 54
        'XHCI-RUN returns -1 (HCH cleared in budget)',   # 55
        'running proof: HCH 1 -> 0 transition',          # 56
        '32 NOPs complete 32/32 (16-TRB ring wrapped '
        'twice, link-toggle executed)',                  # 57
        'XHCI-DOWN (clean arm) returns -1 (all released)',  # 58
        'HCH=1 after XHCI-DOWN (stopped before release)',   # 59
        'second XHCI-DOWN returns 0 (nothing to tear down)',  # 60
        'XHCI-UP (refusal arm) returns -1',              # 61
        'XHCI-DOWN after direct release returns 1 (partial: '
        'vanished record skipped, rest released)',       # 62
        'refusal arm emitted no "PHYS: double release" '
        '(cross-check skipped, did not re-release)',     # 63
    ):
        check(_name, False,
              'red by guard: 2c words absent, not executed')
# Presence control: double-release DIRECTLY -- not through
# XHCI-DOWN -- and the message MUST appear.  Net effect zero.
# Continuity first: on the first red run the target had warm-
# reset by this point and 64-66 scored plausible FAILs against
# a kernel-only dictionary.
continuity('presence control (check 64)')
send('VARIABLE PPG')
send(': PGRAB 4096 PHYS-ALLOC PPG ! ;')
send('PGRAB')
send('PPG @ 4096 PHYS-RELEASE')
raw = send('PPG @ 4096 PHYS-RELEASE', 1.5)
check('presence control: direct double release DOES print '   # 64
      '"PHYS: double release"',
      'PHYS: double release' in body_of(raw),
      f'got: {body_of(raw)!r}')

# Restore pair (user ruling: split -- as one check it is
# vacuous).  Closes over all three legs since the snapshot.
nl2, raw = val('NLIVE', 2.0)
check('owner table restored (NLIVE back to snapshot)',       # 65
      nl2 is not None and nl2 == NL0,
      f'NLIVE {NL0} -> {nl2}: {body_of(raw)!r}')
av2, raw = val('AVAIL', 2.0)
check('free bytes restored (AVAIL back to snapshot)',        # 66
      av2 is not None and av2 == AV0,
      f'AVAIL {AV0} -> {av2}: {body_of(raw)!r}')

print('\n=== Phase 6 (2d): PORTSC decode + port survey '
      '(READ-ONLY) ===')
continuity('phase 6')
zap()
# Read-only invariant: every change bit in PORTSC (CSC/PEC/PRC/
# ...) is RW1C -- a read-modify-write clears them silently.  No
# 2d word writes a port register; port reset belongs to step 3.
# The load-bearing proof is check 98 (twice-read byte-identical,
# catches a leaked write from ANYWHERE); the source-side grep for
# ! near PORTSC-ADDR only catches writes that look like writes.
d_pa = defined('PORTSC-ADDR')
check('PORTSC-ADDR defined (DEF? nonzero)', d_pa)            # 67
d_pq = defined('PORTSC@')
check('PORTSC@ defined (DEF? nonzero)', d_pq)                # 68
v, raw = val('DEF? P-CCS 0<> DEF? P-PED 0<> AND '
             'DEF? P-PR 0<> AND DEF? P-PP 0<> AND '
             'DEF? P-SPEED 0<> AND DEF? P-PLS 0<> AND '
             'DEF? P-CSC 0<> AND')
d_dec = (v == -1)
check('all seven PORTSC field decoders defined', d_dec,      # 69
      f'got {v}: {body_of(raw)!r}')
# FIRST-CCS is FIXTURE-SIDE from 3a (ruling 2026-09-12): which
# port is policy, not mechanism.  On iron it would return port 1
# (the internal high-speed device, enabled pre-HCRST) and look
# like it worked; the card finds the keyboard by a .PORTS survey
# diff instead.  The word not existing on the stick is the guard.
# Defined here only when its three ingredients are nameable (the
# Bug-#31 fence); on a pre-3a tree the vocab's own copy is shadowed.
if d_pq and d_dec:
    send(': FIRST-CCS 0 MAX-PORTS 1+ 1 DO '
         'I PORTSC@ P-CCS OVER 0= AND IF DROP I THEN LOOP ;')
v, raw = val('DEF? #CONNECTED 0<> DEF? FIRST-CCS 0<> AND '
             'DEF? .PORT 0<> AND DEF? .PORTS 0<> AND')
d_srv = (v == -1)
check('survey + display words defined', d_srv,               # 70
      f'got {v}: {body_of(raw)!r}')
# Fixture pin -- 2b machinery only, so GREEN on red: proves the
# usb-kbd fixture is the one the recon measured even before any
# 2d code exists.  A QEMU bump moving this is fixture drift,
# not a 2d defect.
mp, raw = val('MAX-PORTS')
check('fixture pin: MAX-PORTS = 8 (qemu-xhci default)',      # 71
      mp == 8, f'got {mp}: {body_of(raw)!r}')

# Decoder controls feed the two dwords MEASURED in recon
# (xhci-2d-recon-2026-09-09.log): occupied 0x0E03 = 3587,
# empty 0x202A0 = 131744.  Decimal literals -- no HEX sends
# anywhere in phase 6.  Decoders take the VALUE, not the port,
# so these prove decode with the hardware never consulted.
DEC_2D = [
    ('decode 0x0E03 (occupied, measured): P-CCS true',       # 72
     '3587 P-CCS', -1),
    ('decode 0x0E03: P-PED true', '3587 P-PED', -1),         # 73
    ('decode 0x0E03: P-PR false', '3587 P-PR', 0),           # 74
    ('decode 0x0E03: P-PP true', '3587 P-PP', -1),           # 75
    ('decode 0x0E03: P-SPEED = 3 (HS)', '3587 P-SPEED', 3),  # 76
    ('decode 0x0E03: P-PLS = 0 (U0)', '3587 P-PLS', 0),      # 77
    ('decode 0x0E03: P-CSC false', '3587 P-CSC', 0),         # 78
    ('decode 0x202A0 (empty, measured): P-CCS false',        # 79
     '131744 P-CCS', 0),
    ('decode 0x202A0: P-PP true', '131744 P-PP', -1),        # 80
    ('decode 0x202A0: P-SPEED = 0', '131744 P-SPEED', 0),    # 81
    ('decode 0x202A0: P-PLS = 5 (RxDetect)',                 # 82
     '131744 P-PLS', 5),
    ('decode 0x202A0: P-CSC true (QEMU quirk, measured)',    # 83
     '131744 P-CSC', -1),
    ('bounds: 0 PORTSC-ADDR refused (0) -- the dword below '  # 84
     'the array reads plausibly', '0 PORTSC-ADDR', 0),
    ('bounds: MAX-PORTS 1+ PORTSC-ADDR refused (0)',         # 85
     'MAX-PORTS 1+ PORTSC-ADDR', 0),
    ('address identity: 1 PORTSC-ADDR = OP-BASE + 0x400',    # 86
     '1 PORTSC-ADDR OP-BASE 1024 + =', -1),
]
HW_2D_NAMES = [
    'invariant: #CONNECTED = 1 (usb-kbd fixture)',           # 87
    'FIRST-CCS identity: in 1..MAX-PORTS and its own CCS '   # 88
    'reads set',
    'occupied port: P-PED false post-HCRST (controller '     # 89
    'reset cleared the enable; re-enable = port reset, '
    'step 3)',
    'occupied port: P-PR false (no reset in flight)',        # 90
    'occupied port: P-PP true (powered)',                    # 91
    'occupied port: P-CSC true post-HCRST (re-detection '    # 92
    'set the change bit)',
    'occupied port: P-SPEED valid (1..4); value printed, '   # 93
    'not asserted',
    'empty port: P-CCS false',                               # 94
    'empty port: P-PP true (powered, PPC=0)',                # 95
    'empty port: P-PLS = 5 (RxDetect)',                      # 96
    'empty port: P-CSC true (QEMU quirk, measured)',         # 97
    'read-only proof: occupied and empty PORTSC each read '  # 98
    'twice byte-identical (catches a leaked RW1C write '
    'from anywhere)',
]
ALL_2D = d_pa and d_pq and d_dec and d_srv
if ALL_2D:
    for _name, _expr, _want in DEC_2D:
        v, raw = val(_expr)
        check(_name, v == _want, f'got {v}: {body_of(raw)!r}')
    # Hardware leg.  Controller is HALTED here (post-DOWN),
    # and the occupied port is in POST-HCRST state, not the
    # cold-boot state recon measured: HCRST clears PED (and
    # only a step-3 port reset restores it) and the re-detect
    # sets CSC (stage probe xhci-2d-stages log; the original
    # cold-state prediction failed on green 1 exactly as the
    # named alternative said it might).
    nconn, raw = val('#CONNECTED')
    check(HW_2D_NAMES[0], nconn == 1,
          f'got {nconn}: {body_of(raw)!r}')
    fp, raw = val('FIRST-CCS')
    v, raw2 = val('FIRST-CCS PORTSC@ P-CCS')
    check(HW_2D_NAMES[1],
          fp is not None and mp is not None and 1 <= fp <= mp
          and v == -1,
          f'FIRST-CCS={fp}, its P-CCS={v}: {body_of(raw2)!r}')
    print(f'  connected port = {fp} (incidental: recon read 5; '
          'a reshuffle is a log line, not a failure)')
    v, raw = val('FIRST-CCS PORTSC@ P-PED')
    check(HW_2D_NAMES[2], v == 0, f'got {v}: {body_of(raw)!r}')
    v, raw = val('FIRST-CCS PORTSC@ P-PR')
    check(HW_2D_NAMES[3], v == 0, f'got {v}: {body_of(raw)!r}')
    v, raw = val('FIRST-CCS PORTSC@ P-PP')
    check(HW_2D_NAMES[4], v == -1, f'got {v}: {body_of(raw)!r}')
    v, raw = val('FIRST-CCS PORTSC@ P-CSC')
    check(HW_2D_NAMES[5], v == -1, f'got {v}: {body_of(raw)!r}')
    spd, raw = val('FIRST-CCS PORTSC@ P-SPEED')
    check(HW_2D_NAMES[6], spd is not None and 1 <= spd <= 4,
          f'got {spd}: {body_of(raw)!r}')
    print(f'  occupied speed = {spd} (incidental: recon read '
          '3 = HS)')
    ep = 1 if fp != 1 else 2
    print(f'  empty-port probe uses port {ep}')
    v, raw = val(f'{ep} PORTSC@ P-CCS')
    check(HW_2D_NAMES[7], v == 0, f'got {v}: {body_of(raw)!r}')
    v, raw = val(f'{ep} PORTSC@ P-PP')
    check(HW_2D_NAMES[8], v == -1, f'got {v}: {body_of(raw)!r}')
    v, raw = val(f'{ep} PORTSC@ P-PLS')
    check(HW_2D_NAMES[9], v == 5, f'got {v}: {body_of(raw)!r}')
    v, raw = val(f'{ep} PORTSC@ P-CSC')
    check(HW_2D_NAMES[10], v == -1, f'got {v}: {body_of(raw)!r}')
    v, raw = val('FIRST-CCS PORTSC@ FIRST-CCS PORTSC@ = '
                 f'{ep} PORTSC@ {ep} PORTSC@ = AND')
    check(HW_2D_NAMES[11], v == -1, f'got {v}: {body_of(raw)!r}')
else:
    for _name, _expr, _want in DEC_2D:
        check(_name, False,
              'red by guard: 2d words absent, not executed')
    for _name in HW_2D_NAMES:
        check(_name, False,
              'red by guard: 2d words absent, not executed')

print('\n=== Phase 7 (2e prep): claim / SMI-clear / elapsed / '
      'fixed-base display / memdisk gate ===')
continuity('phase 7')
zap()
# The iron trip's machinery, QEMU-proven first.  qemu-xhci has
# no legacy cap (2b: handoff code 0), so the claim and SMI-clear
# logic runs against suite-owned cells via the address-taking
# inner words -- the 2b poll-control pattern -- while the
# hardware wrappers exercise the cap-absent (outcome A) arm,
# which is exactly the card's dry run.  Control cells are
# kernel machinery only, so the instrument is GREEN on red.
send('VARIABLE C1  VARIABLE C2  VARIABLE C3')
send('VARIABLE C4  VARIABLE C5  VARIABLE C6')
v, raw = val('12345 C1 !  C1 @')
instrument('control cells round-trip (kernel machinery only)',  # 99
           v == 12345, f'got {v}: {body_of(raw)!r}')
d_clm = defined('(CLAIM)') and defined('XHCI-CLAIM')
check('(CLAIM) + XHCI-CLAIM defined', d_clm)                 # 100
d_smi = defined('(SMI-OFF)') and defined('SMI-OFF')
check('(SMI-OFF) + SMI-OFF defined', d_smi)                  # 101
d_aux = defined('HRST-LEFT') and defined('MEMDISK-BASE@')
check('HRST-LEFT + MEMDISK-BASE@ defined', d_aux)            # 102
d_dsp = defined('.D') and defined('.PSC')
check('.D + .PSC defined', d_dsp)                            # 103

# Decimal literals for the control dwords (no HEX sends except
# the two .D/.PSC base tests, each bracketed by DECIMAL).
# Masks VERIFIED against Linux xhci-ext-caps.h (fetched
# 2026-09-10; the header cites spec section 7.1.2):
#   XHCI_LEGACY_DISABLE_SMI = (0x7<<1)+(0xff<<5)+(0x7<<17)
#     = 0xE1FEE preserve mask ("bits 1:3, 5:12, and 17:19
#     need to be preserved; bits 21:28 should be zero")
#   XHCI_LEGACY_SMI_EVENTS  = 0x7<<29 = 0xE0000000 (RW1C)
#   enable bits (RW, written zero) = 0, 4, 13, 14, 15
#     -> detect mask 0xE011.  Bit 4 is SMI-on-Host-System-
#     Error Enable: a fixture without it set cannot catch a
#     detect mask that misses it, hence the bit-4-only pair.
#   0x1000000 OS-owned bit 24        = 16777216
#   0x10000   BIOS-owned bit 16      = 65536
#   0x1010000 both                   = 16842752
#   0x1FE0    reserved set, en clear = 8160
#   0xE011    all five SMI enables   = 57361
#   0x10      bit-4-only (HSE SMI)   = 16
#   0xFFFFF   both preserve groups   = 1048575
#   0xE0000000 signed                = -536870912
#   0xE00E1FEE signed                = -535945234
E_NAMES = [
    '(CLAIM) released: code -1 when BIOS bit already clear',  # 104
    '(CLAIM) released: OS-owned bit 24 written even when '    # 105
    'BIOS never held it (uniform-claim ruling)',
    '(CLAIM) stuck: code 1 after the full 1000 ms budget',    # 106
    "(CLAIM) stuck: unmasked print 'handoff stuck, "          # 107
    "legsup=01010000' (our bit 24 visible in it proves "
    'set-before-poll ordering)',
    '(CLAIM) stuck: cell = OS bit + BIOS bit (0x1010000)',    # 108
    'XHCI-CLAIM hardware: 0 in QEMU (outcome A, cap absent '  # 109
    '-- the card dry-run)',
    '(SMI-OFF) already-clear: code -1, write path not taken',  # 110
    '(SMI-OFF) already-clear: cell byte-identical (0x1FE0) '  # 111
    '-- proves NO write occurred (any write ORs 0xE0000000)',
    '(SMI-OFF) all five enables (0xE011): code 1',            # 112
    '(SMI-OFF) all five enables: cell = 0xE0000000 '          # 113
    '(enables cleared, RW1C status bits written to clear)',
    '(SMI-OFF) bit-4-only (HSE SMI): code 1 -- the enable '   # 114
    'a 0xE001-style mask would silently leave armed',
    '(SMI-OFF) bit-4-only: cell = 0xE0000000',                # 115
    '(SMI-OFF) mixed 0xFFFFF: code 1',                        # 116
    '(SMI-OFF) mixed: cell = 0xE00E1FEE (preserve mask '      # 117
    'keeps 17:19 AND 12:5, 3:1 -- Linux-shaped write, not '
    'write-zero)',
    'SMI-OFF hardware: 0 in QEMU (outcome A -- card '         # 118
    'dry-run)',
    'HCRST elapsed 0..1 ms in QEMU (instant reset); the '     # 119
    'iron figure is the 2e payload',
    ".D renders decimal under HEX ('15' for F)",              # 120
    ".D restores caller BASE (BASE @ renders '10' = 16 "      # 121
    'in hex)',
    '.PSC occupied synthetic: raw dword via .H8 '             # 122
    '(000013E3)',
    ".PSC occupied synthetic: '15 pls' while BASE=16 "        # 123
    '(the base-transparency debt)',
    ".PSC occupied synthetic: 'conn' + ' en ' + '4 spd' "     # 124
    'all render',
    ".PSC empty synthetic: 000202A0 + '5 pls', no 'conn'",    # 125
    ".PORT on occupied port: 'conn' without ' en ' "          # 126
    '(post-HCRST hardware)',
    '.PORTS emits MAX-PORTS lines (the looped display '       # 127
    'going to iron)',
    'memdisk gate: MEMDISK-BASE@ = 0 in QEMU (refusal '       # 128
    'side); iron pass side pre-registered nonzero + 4KiB-'
    'aligned, prior reading 0x37BB7000 (2026-09-05)',
    'no-touch bracket: occupied PORTSC byte-identical '       # 129
    'across phase 7',
]
ALL_2E = d_clm and d_smi and d_aux and d_dsp
if ALL_2E:
    # No-touch bracket open: phase 7's controls write suite
    # cells only, and the wrappers are no-ops in this habitat
    # (cap absent) -- the close at 126 proves it.
    pt0, raw = val('FIRST-CCS PORTSC@')
    # (CLAIM) released path: BIOS bit already clear, poll
    # returns immediately -- the code-2 uniform-claim case.
    v, raw = val('0 C1 !  C1 (CLAIM)')
    check(E_NAMES[0], v == -1, f'got {v}: {body_of(raw)!r}')
    v, raw = val('C1 @')
    check(E_NAMES[1], v == 16777216,
          f'got {v}: {body_of(raw)!r}')
    # (CLAIM) stuck path: bit 16 held, full budget elapses in
    # real time.  Green-1 was 128/130: this send's 4.0 s window
    # missed the output while the CELL check passed -- the word
    # completed, late.  Isolating probe (2026-09-10, echo-proof
    # marker): full-budget poll = 8.09 s wall under QEMU TCG
    # (MS-DELAY iterations run ~8x wall here).  Window widened
    # to 15 s with the mechanism recorded; the expectations
    # themselves are unchanged (re-pin rule: instrument window,
    # not prediction, moved).
    send('65536 C2 !')
    v, raw = val('C2 (CLAIM)', 15.0)
    body = body_of(raw)
    check(E_NAMES[2], v == 1, f'got {v}: {body!r}')
    check(E_NAMES[3],
          'handoff stuck, legsup=01010000' in body,
          f'got: {body!r}')
    v, raw = val('C2 @')
    check(E_NAMES[4], v == 16842752,
          f'got {v}: {body_of(raw)!r}')
    v, raw = val('XHCI-CLAIM', 4.0)
    check(E_NAMES[5], v == 0, f'got {v}: {body_of(raw)!r}')
    # (SMI-OFF) already-clear: reserved bits set, enables
    # clear.  Byte-identity afterwards is the no-write proof.
    v, raw = val('8160 C3 !  C3 (SMI-OFF)')
    check(E_NAMES[6], v == -1, f'got {v}: {body_of(raw)!r}')
    v, raw = val('C3 @')
    check(E_NAMES[7], v == 8160, f'got {v}: {body_of(raw)!r}')
    v, raw = val('57361 C4 !  C4 (SMI-OFF)')
    check(E_NAMES[8], v == 1, f'got {v}: {body_of(raw)!r}')
    v, raw = val('C4 @')
    check(E_NAMES[9], v == -536870912,
          f'got {v}: {body_of(raw)!r}')
    # Bit-4-only: with a detect mask that misses bit 4 this
    # returns -1 (already clear) and HSE SMI stays armed on
    # iron -- during the reset leg, the exact wrong moment.
    v, raw = val('16 C6 !  C6 (SMI-OFF)')
    check(E_NAMES[10], v == 1, f'got {v}: {body_of(raw)!r}')
    v, raw = val('C6 @')
    check(E_NAMES[11], v == -536870912,
          f'got {v}: {body_of(raw)!r}')
    v, raw = val('1048575 C5 !  C5 (SMI-OFF)')
    check(E_NAMES[12], v == 1, f'got {v}: {body_of(raw)!r}')
    v, raw = val('C5 @')
    check(E_NAMES[13], v == -535945234,
          f'got {v}: {body_of(raw)!r}')
    v, raw = val('SMI-OFF', 2.0)
    check(E_NAMES[14], v == 0, f'got {v}: {body_of(raw)!r}')
    # HRST elapsed: set during the last XHCI-RESET (phase 4).
    # PN is shared and long since clobbered; HRST-LEFT is the
    # only surviving copy of the HCRST figure.
    v, raw = val('1000 HRST-LEFT @ -')
    check(E_NAMES[15], v is not None and 0 <= v <= 1,
          f'got {v}: {body_of(raw)!r}')
    print(f'  HCRST elapsed = {v} ms (incidental here; the '
          'iron reading is what 2e is for)')
    # .D base transparency: the two HEX sends in this phase,
    # each closed with an explicit DECIMAL.
    send('HEX')
    raw = send('F .D')
    check(E_NAMES[16],
          re.search(r'\b15\b', body_of(raw)) is not None,
          f'got: {body_of(raw)!r}')
    raw = send('BASE @ .')
    check(E_NAMES[17],
          re.search(r'\b10\b', body_of(raw)) is not None,
          f'got: {body_of(raw)!r}')
    send('DECIMAL')
    # .PSC synthetics: value pushed in DECIMAL, displayed with
    # BASE=16 -- the discriminating condition for the debt.
    # 5091 = 0x13E3: CCS|PED|PLS=15|PP|speed=4.
    raw = send('DECIMAL 5091 HEX .PSC', 2.0)
    body = body_of(raw)
    send('DECIMAL')
    check(E_NAMES[18], '000013E3' in body, f'got: {body!r}')
    check(E_NAMES[19], '15 pls' in body, f'got: {body!r}')
    check(E_NAMES[20],
          'conn' in body and ' en ' in body and '4 spd' in body,
          f'got: {body!r}')
    raw = send('DECIMAL 131744 HEX .PSC', 2.0)
    body = body_of(raw)
    send('DECIMAL')
    check(E_NAMES[21],
          '000202A0' in body and '5 pls' in body
          and 'conn' not in body,
          f'got: {body!r}')
    raw = send('FIRST-CCS .PORT', 2.0)
    body = body_of(raw)
    check(E_NAMES[22],
          'conn' in body and ' en ' not in body,
          f'got: {body!r}')
    raw = send('.PORTS', 3.0)
    body = body_of(raw)
    check(E_NAMES[23], mp is not None and body.count('pls') == mp,
          f"{body.count('pls')} 'pls' lines for MAX-PORTS={mp}: "
          f'{body!r}')
    v, raw = val('MEMDISK-BASE@')
    check(E_NAMES[24], v == 0, f'got {v}: {body_of(raw)!r}')
    pt1, raw = val('FIRST-CCS PORTSC@')
    check(E_NAMES[25], pt0 is not None and pt0 == pt1,
          f'{pt0} -> {pt1}: {body_of(raw)!r}')
else:
    for _name in E_NAMES:
        check(_name, False,
              'red by guard: 2e-prep words absent, not executed')

print('\n=== Phase 8: unbound-base guards (refusal + positive control) ===')
continuity('phase 8')
zap()
# Iron 2026-09-10 (a6a6cae correction 2): XHCI-CLAIM executed before
# XHCI-BIND against XHCI-BASE=0, read HCC1 from the real-mode IVT at
# 0x10, and returned 0 -- indistinguishable from "cap absent" -- only
# because bits 31:16 there were clear.  (CLAIM) writes.  Guard: each
# address-deriving word refuses at entry; the code-returning wrappers
# return -2 (unused by CLAIM {0,-1,1} and SMI-OFF {0,-1,1,2}) so a
# refusal can never be read as outcome A.  The address words return 0
# (every caller dereferences nonzero).  Positive control: on a valid
# base the same words must NOT refuse -- a guard proven only on the
# null side is fail-open the other way.  Base saved to a suite cell
# and restored; the restore is itself checked.
#
# Pre-registered (2026-09-11, before the red run; sweep of the
# untouched tree = 1209/31, docs/evidence/sweep-2026-09-11.log):
#   9 checks (130-138); BASE tripwire moves 130 -> 139.
#   Red (xhci.fth untouched): 133, 134 CERTAIN (today's wrappers
#     return 0 or -1, never -2).  131 LIKELY red: SeaBIOS IVT entry
#     4 at 0x10 is F000:xxxx, HCC1 10 RSHIFT = 0xF000, XECP-BASE =
#     0x3C000.  Named alternative: bits 31:16 clear (the HP shape)
#     -> 131 green-on-red, a non-discriminating guard in this
#     habitat, kept; red count drops to 2.  132 direction UNKNOWN
#     (walk from 0x3C000, <=16 hops) -- not counted either way.
#   Green on red: 130, 135, 136, 137, 138 (existing behaviour or
#     machinery).  Predicted red total: 136/139 (131 red) or
#     137/139 (alt), +/-1 for 132.
#   Hazard: if 132's walk finds a cap-ID byte, unguarded (CLAIM)
#     ORs 0x1000000 into a dictionary cell near 0x3C000; phase is
#     last so a red tripwire is attributed to that write.
#   Green: 139/139; sweep test-xhci 130 -> 139, lines 31 => 1218/31.
#   OUTCOME: red 136/139 (xhci-guard-red-2026-09-11.log; 131 red
#     with XECP-BASE = 245760 = 0x3C000, 132 green-on-red), green
#     139/139 (xhci-guard-green-2026-09-11.log), sweep 1218/31
#     (sweep-2026-09-11b.log).
# Rev 2 (same day, ruling): XHCI-OWNER guarded too -- read-only,
#   but unguarded it prints "0 = absent" on a card pre-bind, the
#   confidently-wrong reading that cost the 09-10 trip.  +2 checks
#   (135 unbound = -2; 140 bound = 0, not -2), tripwire -> 141.
#   Red on the guarded-four tree: 140/141 (135 only).  Green
#   141/141; sweep 139 -> 141 => 1220/31.
send('VARIABLE XB0')
v, raw = val('XHCI-BASE @ DUP XB0 !  0<>')
check('phase-8 entry: XHCI-BASE bound (saved to XB0)',        # 130
      v == -1, f'got {v}: {body_of(raw)!r}')
send('0 XHCI-BASE !')
v, raw = val('XECP-BASE')
check('unbound: XECP-BASE refuses (0) -- HCC1 would read '   # 131
      'the IVT at 0x10', v == 0, f'got {v}: {body_of(raw)!r}')
v, raw = val('1 XECP-FIND', 4.0)
check('unbound: 1 XECP-FIND refuses (0)', v == 0,             # 132
      f'got {v}: {body_of(raw)!r}')
v, raw = val('XHCI-CLAIM', 15.0)
check('unbound: XHCI-CLAIM = -2 (refused, distinct from 0 = '  # 133
      'cap absent -- the iron misreading)', v == -2,
      f'got {v}: {body_of(raw)!r}')
v, raw = val('SMI-OFF', 4.0)
check('unbound: SMI-OFF = -2 (refused, distinct from 0)',     # 134
      v == -2, f'got {v}: {body_of(raw)!r}')
v, raw = val('XHCI-OWNER', 4.0)
check('unbound: XHCI-OWNER = -2 (refused; read-only, but 0 '  # 135
      'would read as "absent" on a pre-bind card line)', v == -2,
      f'got {v}: {body_of(raw)!r}')
v, raw = val('XB0 @ XHCI-BASE !  XHCI-BASE @ XB0 @ =')
check('restore: XHCI-BASE = XB0 (base back before the '       # 136
      'positive controls)', v == -1, f'got {v}: {body_of(raw)!r}')
v, raw = val('XECP-BASE 0<>')
check('positive control, bound: XECP-BASE nonzero (QEMU walks '  # 137
      '2 caps; sweep-2026-09-10.log:344)', v == -1,
      f'got {v}: {body_of(raw)!r}')
v, raw = val('XHCI-CLAIM', 4.0)
check('positive control, bound: XHCI-CLAIM = 0 (absent), NOT '  # 138
      '-2 -- guard does not refuse a valid base', v == 0,
      f'got {v}: {body_of(raw)!r}')
v, raw = val('SMI-OFF', 2.0)
check('positive control, bound: SMI-OFF = 0 (absent), NOT -2',  # 139
      v == 0, f'got {v}: {body_of(raw)!r}')
v, raw = val('XHCI-OWNER', 2.0)
check('positive control, bound: XHCI-OWNER = 0 (absent), NOT '  # 140
      '-2', v == 0, f'got {v}: {body_of(raw)!r}')

print('\n=== Phase 9 (3a): port reset / typed events / CTX-SIZE ===')
continuity('phase 9')
zap()
# Step 3a (design rulings 2026-09-12): the FIRST port WRITE in the
# vocab.  PORTSC mixes RO status, RWS state, RW1S (PR, bit 4) and
# RW1C bits (PED bit 1 -- writing 1 DISABLES the port -- and the
# change bits 17-23), so a read-modify-write must pass through a
# neutral mask.  Mask 0x4E00FFE9 = the RO/ROS + RWS classes of
# xHCI 1.2 section 5.4.8 Table 5-27 (bits 0,3,5-15,25-27,30; bit
# 24 CAS omitted, RO ignores writes).  Derived from the spec table;
# cross-checked equal to Linux xhci-hub.c XHCI_PORT_RO|RWS at
# pinned tag v6.12 (sha256 7cc388b7...) -- spec is the source,
# Linux a version-pinned check, not master (provenance ruling
# 2026-09-12; master can drift, so the cross-check names a tag).
# Bit-isolating controls (feedback_mask_blindness): all-ones,
# PED-only, change-bits-only, PR-only, and the measured post-HCRST
# dword 0x20EE1 each get their own check.
# Typed event consumer: 2c's NOP1 never inspects the TRB type, so
# a port-status-change event ahead of a command completion would
# be counted as one.  EV-WAIT skips-with-record (XEV-SKIP/XEV-LAST,
# bound 20); the skip path is exercised by a real NOP completion.
# CTX-SIZE from HCCPARAMS1 bit 2 (Linux xhci-caps.h CTX_SIZE).
#
# Pre-registered (2026-09-12, before the red run; suite-alone
# baseline 141/141, xhci-owner-green-2026-09-11.log):
#   39 checks (142-180); BASE tripwire moves 141 -> 180.
#   Red (xhci.fth untouched): all 39 red BY GUARD (definedness
#     142-144 red, the rest scored red without sending -- the
#     hardware leg writes PORTSC and must not run on a tree
#     without the neutral mask).  Predicted red: 141/181 exactly;
#     every existing check unchanged (FIRST-CCS moves to the
#     fixture, shadowing the vocab's copy on the red tree).
#     [As written before the run this line said 141/181 and the
#     tripwire 181: the 141 baseline already INCLUDED the
#     tripwire, so 141 + 39 = 180.  Counting error, recorded.]
#   Green derivations (source, not recall):
#     CTX-SIZE = 32: QEMU hcd-xhci.c HCCPARAMS read returns
#       0x00080000 or 0x00080001 -- bit 2 clear either way.
#       Iron: unmeasured; pre-registered 64 (Intel), named alt 32.
#     P-SPEED = 1 after reset: dev-hid.c desc_keyboard has .full
#       only (no .high), bMaxPacketSize0 = 8.  Named alt: any
#       other value = fixture drift, not a 3a defect.
#       [WRONG -- green 1 = 179/180, speed read 3.  Derived from
#       MASTER dev-hid.c; the installed QEMU is 8.2.2, whose
#       desc_keyboard has .high = &desc_device_keyboard2
#       (bMaxPacketSize0 = 64), dropped upstream later.  The 2d
#       recon had ALREADY banked speed 3 on this port
#       (xhci-2d-green-2026-09-09.log:129) and the derivation was
#       not cross-checked against it.  Re-pinned to 3 WITH the
#       mechanism (version-pinned source, sha256 706a9cf2...).
#       3 IS A QEMU FIXTURE VALUE (same species as the CAP-LEN
#       0x20..0x7F bound): iron will NOT read 3.  A USB boot
#       keyboard is typically LOW-speed (P-SPEED=2), sometimes
#       full-speed (1) -- never high-speed.  Carried to 3b,
#       CORRECTED: bMaxPacketSize0 is mandated 8 ONLY for
#       low-speed; full-speed may report 8/16/32/64 and QEMU's
#       HS keyboard reports 64.  So 3b MUST read bMaxPacketSize0
#       via GET_DESCRIPTOR(8) and build the EP0 context from the
#       value read -- never hardcode 8 or 64 (earlier note said
#       "FS iron = 8", right byte, wrong premise: fixed here).]
#     elapsed 0 ms: hcd-xhci.c xhci_port_write handles PR
#       synchronously (PED set, PLS U0, PR cleared, PRC notified
#       before the write returns).  Iron pre-registered 10..100 ms.
#     PSCE: xhci_port_notify emits {PORT_STATUS_CHANGE, CC_SUCCESS,
#       portnr << 24} only when running (hence UP/RUN first) and
#       only if PRC was clear (measured 0x20EE1: bit 21 clear).
#     P-CSC false after reset: the second write clears bits 17-23.
#   Green: 180/180.  Sweep deferred to step-3 close (cadence
#     ruling 2026-09-12: test-xhci alone per rung).
#   OUTCOME: red 141/180 (xhci-3a-red-2026-09-12.log): 39 red by
#     guard, 142-144 the only sent failures, no existing check
#     moved; denominator 180 not 181 (see bracket above).
#     Green 1: 179/180 (xhci-3a-green1-179of180-2026-09-12.log),
#     check 167 only -- speed bracket above.  Green 2: (fill)
d_pr = (defined('PORT-RESET') and defined('P-NEUTRAL')
        and defined('P-PRC'))
check('PORT-RESET + P-NEUTRAL + P-PRC defined', d_pr)         # 142
v, raw = val('DEF? T-TYPE 0<> DEF? T-CC 0<> AND '
             'DEF? T-SLOT 0<> AND DEF? T-PORT 0<> AND '
             'DEF? EV-D0 0<> AND DEF? EV-TYPE 0<> AND '
             'DEF? EV-CC 0<> AND DEF? EV-SLOT 0<> AND '
             'DEF? EV-WAIT 0<> AND')
d_ev = (v == -1)
check('typed event words defined (T-TYPE T-CC T-SLOT T-PORT '  # 143
      'EV-D0 EV-TYPE EV-CC EV-SLOT EV-WAIT)', d_ev,
      f'got {v}: {body_of(raw)!r}')
d_cs = defined('CTX-SIZE')
check('CTX-SIZE defined', d_cs)                               # 144

# Decimal literals (no HEX sends in phase 9):
#   0x4E00FFE9 neutral mask          = 1308688361
#   0xFE0000   change bits 17-23     = 16646144
#   0x20EE1    measured post-HCRST   = 134881 -> & mask = 0xEE1 = 3809
#   0x200000   PRC bit 21            = 2097152
#   0x8401     type 33 | cycle       = 33793
#   0x8801     type 34 | cycle       = 34817
#   0x01000000 cc 1 / slot 1 field   = 16777216
#   0x01008401 slot 1, type 33       = 16811009
#   0x05000000 port 5 in dword0      = 83886080
LOGIC_3A = [
    ('-1 P-NEUTRAL = 0x4E00FFE9: RO + RWS survive an all-ones '  # 145
     'read', '-1 P-NEUTRAL', 1308688361),
    ('2 P-NEUTRAL = 0: PED (RW1C, 1 = DISABLE) never written '  # 146
     'back', '2 P-NEUTRAL', 0),
    ('0xFE0000 P-NEUTRAL = 0: change bits 17-23 (RW1C) never '  # 147
     'written back by a neutral write', '16646144 P-NEUTRAL', 0),
    ('16 P-NEUTRAL = 0: PR (RW1S) not re-asserted by a neutral '  # 148
     'write', '16 P-NEUTRAL', 0),
    ('0x20EE1 (measured post-HCRST) P-NEUTRAL = 0xEE1: CSC '     # 149
     'dropped, CCS/PLS/PP/speed kept', '134881 P-NEUTRAL', 3809),
    ('P-PRC: bit 21 true, 0 false', '2097152 P-PRC 0 P-PRC 0= AND',  # 150
     -1),
    ('T-TYPE 0x8401 = 33 (command completion)', '33793 T-TYPE', 33),  # 151
    ('T-TYPE 0x8801 = 34 (port status change)', '34817 T-TYPE', 34),  # 152
    ('T-CC 0x01000000 = 1 (success)', '16777216 T-CC', 1),      # 153
    ('T-SLOT 0x01008401 = 1', '16811009 T-SLOT', 1),            # 154
    ('T-PORT 0x05000000 = 5', '83886080 T-PORT', 5),            # 155
    ('CTX-SIZE = 32 (QEMU HCCPARAMS derivation: CSZ clear; '    # 156
     'iron pre-registered 64, named alt 32)', 'CTX-SIZE', 32),
]
UNB_3A_NAMES = [
    'unbound: CTX-SIZE = 0 (refused; 32/64 would read as a '   # 157
    'plausible answer on a pre-bind card line)',
    'unbound: PORT-RESET = 0 (refused; PORTSC-ADDR alone is '  # 158
    'fail-open read-only and this word WRITES)',
    'restore: XHCI-BASE = XB0 after the 3a unbound pair',      # 159
]
HW_3A_NAMES = [
    'XHCI-UP returns -1 (3a leg)',                             # 160
    'XHCI-RUN returns -1 (PSCE is dropped when halted)',       # 161
    'FIRST-CCS PORT-RESET returns -1 (PRC seen, PED set)',     # 162
    'occupied port: P-PED true after port reset (the 2d '     # 163
    '"re-enable = step 3" debt)',
    'occupied port: P-PR false (reset complete)',              # 164
    'occupied port: P-PRC false (change bits cleared by the '  # 165
    'second write)',
    'occupied port: P-CSC false (cleared in the same write)',  # 166
    'occupied port: P-SPEED = 3 (QEMU 8.2.2 FIXTURE value: '   # 167
    'dev-hid.c desc_keyboard .high; iron reads 1/FS or 2/LS, '
    'never 3)',
    'elapsed: 1000 PRST-LEFT @ - = 0 ms (QEMU resets '         # 168
    'synchronously in xhci_port_write; iron pre-registered '
    '10..100 ms)',
    '34 EV-WAIT = -1: the PSCE from the reset reached the '    # 169
    'event ring',
    'EV-TYPE = 34 at the un-consumed TRB',                     # 170
    'EV-D0 T-PORT = FIRST-CCS (the event names the port)',     # 171
    'EV-CC = 1 (CC_SUCCESS in the PSCE)',                       # 172
    'XEV-SKIP = 0 (nothing skipped ahead of the PSCE)',        # 173
    '34 EV-WAIT = 0 after EV-NEXT (negative control: ring '    # 174
    'empty, budget elapses)',
    'skip-with-record: NOP ringed, 34 EV-WAIT = 0 (no PSCE; '  # 175
    'the completion was skipped, not counted)',
    'skip-with-record: XEV-SKIP = 1',                          # 176
    'skip-with-record: XEV-LAST = 33',                         # 177
    '1 NOP-TEST = 1 (command path intact after typed '        # 178
    'consumption)',
    'XHCI-DOWN returns -1 (3a leg released)',                  # 179
    'allocator symmetry: NLIVE after DOWN = NLIVE before UP',  # 180
]
ALL_3A = d_pr and d_ev and d_cs
if ALL_3A:
    for _name, _expr, _want in LOGIC_3A:
        v, raw = val(_expr)
        check(_name, v == _want, f'got {v}: {body_of(raw)!r}')
    # Unbound pair, phase-8 shape: save, null, refuse, restore.
    send('XHCI-BASE @ XB0 !')
    send('0 XHCI-BASE !')
    v, raw = val('CTX-SIZE')
    check(UNB_3A_NAMES[0], v == 0, f'got {v}: {body_of(raw)!r}')
    _port = fp if (ALL_2D and fp) else 1
    v, raw = val(f'{_port} PORT-RESET', 4.0)
    check(UNB_3A_NAMES[1], v == 0, f'got {v}: {body_of(raw)!r}')
    v, raw = val('XB0 @ XHCI-BASE !  XHCI-BASE @ XB0 @ =')
    check(UNB_3A_NAMES[2], v == -1, f'got {v}: {body_of(raw)!r}')
    if ALL_2C and ALL_2D:
        zap()
        nl_a, _ = val('NLIVE', 2.0)
        v, raw = val('XHCI-UP', 3.0)
        check(HW_3A_NAMES[0], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XHCI-RUN', 3.0)
        check(HW_3A_NAMES[1], v == -1, f'got {v}: {body_of(raw)!r}')
        # Window 12 s: a stuck PRC poll runs the full 1000 ms
        # budget = ~8 s wall under TCG (2e-prep measurement).
        v, raw = val('FIRST-CCS PORT-RESET', 12.0)
        check(HW_3A_NAMES[2], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('FIRST-CCS PORTSC@ P-PED')
        check(HW_3A_NAMES[3], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('FIRST-CCS PORTSC@ P-PR')
        check(HW_3A_NAMES[4], v == 0, f'got {v}: {body_of(raw)!r}')
        v, raw = val('FIRST-CCS PORTSC@ P-PRC')
        check(HW_3A_NAMES[5], v == 0, f'got {v}: {body_of(raw)!r}')
        v, raw = val('FIRST-CCS PORTSC@ P-CSC')
        check(HW_3A_NAMES[6], v == 0, f'got {v}: {body_of(raw)!r}')
        v, raw = val('FIRST-CCS PORTSC@ P-SPEED')
        check(HW_3A_NAMES[7], v == 3, f'got {v}: {body_of(raw)!r}')
        v, raw = val('1000 PRST-LEFT @ -')
        check(HW_3A_NAMES[8], v == 0, f'got {v}: {body_of(raw)!r}')
        # EV-POLL budget 0x100 iterations = ~2 s wall under TCG;
        # 6 s windows on every EV-WAIT that may run it out.
        v, raw = val('34 EV-WAIT', 6.0)
        check(HW_3A_NAMES[9], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('EV-TYPE')
        check(HW_3A_NAMES[10], v == 34, f'got {v}: {body_of(raw)!r}')
        v, raw = val('EV-D0 T-PORT FIRST-CCS =')
        check(HW_3A_NAMES[11], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('EV-CC')
        check(HW_3A_NAMES[12], v == 1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XEV-SKIP @')
        check(HW_3A_NAMES[13], v == 0, f'got {v}: {body_of(raw)!r}')
        send('EV-NEXT')
        v, raw = val('34 EV-WAIT', 6.0)
        check(HW_3A_NAMES[14], v == 0, f'got {v}: {body_of(raw)!r}')
        send('TRB-NOP! DOORBELL0')
        v, raw = val('34 EV-WAIT', 6.0)
        check(HW_3A_NAMES[15], v == 0, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XEV-SKIP @')
        check(HW_3A_NAMES[16], v == 1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XEV-LAST @')
        check(HW_3A_NAMES[17], v == 33, f'got {v}: {body_of(raw)!r}')
        v, raw = val('1 NOP-TEST', 4.0)
        check(HW_3A_NAMES[18], v == 1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XHCI-DOWN', 3.0)
        check(HW_3A_NAMES[19], v == -1, f'got {v}: {body_of(raw)!r}')
        nl_b, raw = val('NLIVE', 2.0)
        check(HW_3A_NAMES[20], nl_a is not None and nl_b == nl_a,
              f'NLIVE {nl_a} -> {nl_b}: {body_of(raw)!r}')
    else:
        for _name in HW_3A_NAMES:
            check(_name, False,
                  'red by guard: 2c/2d machinery absent, not executed')
else:
    for _name, _expr, _want in LOGIC_3A:
        check(_name, False,
              'red by guard: 3a words absent, not executed')
    for _name in UNB_3A_NAMES + HW_3A_NAMES:
        check(_name, False,
              'red by guard: 3a words absent, not executed')

print('\n=== Phase 10 (3b): slot commands / contexts / Address Device ===')
continuity('phase 10')
zap()
send('VARIABLE XSLOT2  VARIABLE CMD-CC2')
# Step 3b (design rulings 2026-09-12): the first structures the
# CONTROLLER reads back -- input + output device contexts it
# dereferences, not just rings it consumes.  Generic command TRB
# + Enable Slot / Address Device / Disable Slot; device reaches
# Addressed.  Control transfers + the real bMaxPacketSize0 read are
# 3c (spec bootstrap: cannot GET_DESCRIPTOR before Addressed).
#
# CONTEXT SIZE is the load-bearing bit QEMU cannot exercise: QEMU
# reads the input context at hardcoded +32/+64 (always 32-byte
# stride), so a 32 hardcode passes here and writes wrong offsets
# into DMA on a 64-byte controller.  CTX-SZ caches CTX-SIZE and
# every offset word scales with it; the scaling control forces
# CTX-SZ=64 to prove the 64-byte layout the emulator can't
# (feedback_mask_blindness).  The BUILD-ICTX readback proves the
# exact bytes the controller dereferences (the two-gate content
# side; a completion code alone is only delivery).
#
# Constants xHCI 1.2 Table 6-90/6-91 (QEMU v8.2.2 hcd-xhci.c
# confirms): Enable Slot 9, Disable Slot 10, Address Device 11;
# Command Completion event 33; CC Success 1, TRB Error 5, Slot Not
# Enabled 11, Parameter Error 17; slot state Addressed 2.  QEMU
# requires input control Drop=0/Add=3 or returns TRB Error 5 --
# that is what a wrong context reads as, pre-registered.
#
# Pre-registered (2026-09-12, before the red run; suite-alone
# baseline 180/180, xhci-3a-provenance-2026-09-12.log):
#   35 new checks.  Baseline (green2/HEAD) = 180 executed
#   (the BASE tripwire is one of them); new total = 215, DERIVED
#   from the red log's PASS/FAIL line count, not reconciled.
#   Emitted positions: phase-10 checks 180-214, tripwire 215.
#   The # 181-215 labels in the code below are nominal (+1),
#   inherited from the 3a tripwire label collision; the load-
#   bearing number is the emitted total 215.
#   Red (xhci.fth untouched by 3b -- 3a source is HEAD): 181-183
#     definedness red (sent); 184-215 red BY GUARD (not sent -- the
#     context builders and command path must not run on a tree
#     without them).  Predicted red 180/215 exactly (180
#     baseline green + 35 new red); no existing check moves.
#   Green derivations (source, not recall):
#     SPEED>MPS: HS 64 / SS 512 / LS,FS 8 (spec 4.3, USB 2.0 5.5.3).
#     CTX-SZ scaling: pure multiply, 64->{64,128,64}, 32->{32,64}.
#     BUILD-ICTX @ CTX-SZ=32, port 5, HS: ctrl+4=3; slot+32=
#       0x08300000 (ctxentries 1<<27 | speed 3<<20); slot+36=
#       0x00050000 (port 5<<16); ep0+68=0x00400026 (mps 64<<16 |
#       type Control 4<<3 | CErr 3<<1); ep0+72 = ring|1 (DCS);
#       ep0+80 = 8 (avg TRB len).
#     HW leg: ENABLE-SLOT cc=1 slot>=1; ENUM-ADDRESS returns the
#       slot; SLOT-STATE=2 (Addressed) -- QEMU xhci_address_slot
#       writes SLOT_ADDRESSED to output slot_ctx[3]; SLOT-DOWN=-1;
#       NLIVE symmetric across UP..DOWN.
#   Green: 215/215.  Sweep at step-3 close (cadence ruling), not here.
#   SCOPE OF PROOF (delivery vs content): forcing CTX-SZ=64
#   proves the offset words SCALE; it CANNOT prove a 64-byte
#   controller accepts the layout, because QEMU reads at
#   hardcoded 32-byte stride regardless.  Record green as
#   'scaling proven, 64-byte acceptance unproven' -- 64-byte
#   context acceptance is an iron finding (named for the trip).
#   OUTCOME: red 180/215 (xhci-3b-red-2026-09-12.log), DERIVED
#   from 215 PASS/FAIL lines: 180 baseline green, 35 phase-10 red
#   (3 definedness sent + 32 by guard), no baseline check moved.
#   Green 1: 214/215 (xhci-3b-green-2026-09-12.log): check 204
#   only.  NOT a vocab defect -- the probe compared XCRING's
#   base ADDRESS to the constant (missing @); check 205 passed,
#   proving CMD-ENQ wrote the control dword.  Probe corrected to
#   dereference all four dwords; CMD-ENQ correct by stack trace
#   (plo+0/phi+4/sts+8/ctl+C).  Range moved 1724-1755 -> 1724-
#   1764 (3b added ~90 lines; suite reads it live, THRU loaded).
#   Green 2: 215/215 (xhci-3b-green2-2026-09-12.log), DERIVED
#   from 215 PASS/FAIL lines, 0 fail -- params landing now
#   OBSERVED (all four dwords), not only reasoned.
d_ctx = (defined('CTX-CACHE') and defined('CTX-SZ')
         and defined('I-SLOT') and defined('I-EP0')
         and defined('O-EP0'))
check('CTX-CACHE/CTX-SZ/I-SLOT/I-EP0/O-EP0 defined', d_ctx)   # 181
v, raw = val('DEF? CMD-ENQ 0<> DEF? CMD-RUN 0<> AND '
             'DEF? ENABLE-SLOT 0<> AND DEF? DISABLE-SLOT 0<> AND '
             'DEF? SPEED>MPS 0<> AND')
d_cmd = (v == -1)
check('command words defined (CMD-ENQ/CMD-RUN/ENABLE-SLOT/'   # 182
      'DISABLE-SLOT/SPEED>MPS)', d_cmd, f'got {v}: {body_of(raw)!r}')
v, raw = val('DEF? BUILD-ICTX 0<> DEF? SLOT-ALLOC 0<> AND '
             'DEF? SLOT-FREE 0<> AND DEF? SLOT-STATE 0<> AND '
             'DEF? ENUM-ADDRESS 0<> AND DEF? SLOT-DOWN 0<> AND')
d_slot = (v == -1)
check('slot words defined (BUILD-ICTX/SLOT-ALLOC/SLOT-FREE/'  # 183
      'SLOT-STATE/ENUM-ADDRESS/SLOT-DOWN)', d_slot,
      f'got {v}: {body_of(raw)!r}')

ALL_3B = d_ctx and d_cmd and d_slot
LOGIC_3B = [
    ('SPEED>MPS FS(1) = 8', '1 SPEED>MPS', 8),               # 184
    ('SPEED>MPS LS(2) = 8', '2 SPEED>MPS', 8),               # 185
    ('SPEED>MPS HS(3) = 64', '3 SPEED>MPS', 64),             # 186
    ('SPEED>MPS SS(4) = 512', '4 SPEED>MPS', 512),           # 187
]
SCALE_NAMES = [
    'CTX-SZ scaling 64: 0 I-SLOT = 64 (slot ctx at 1x)',     # 188
    'CTX-SZ scaling 64: 0 I-EP0 = 128 (ep0 ctx at 2x)',      # 189
    'CTX-SZ scaling 64: 0 O-EP0 = 64 (output ep0 at 1x)',    # 190
    'CTX-SZ scaling 32: 0 I-SLOT = 32',                      # 191
    'CTX-SZ scaling 32: 0 I-EP0 = 64',                       # 192
]
ICTX_NAMES = [
    'scratch input ctx + ring allocated',                    # 193
    'BUILD-ICTX input control +4 = 3 (Drop 0 / Add A0|A1)',  # 194
    'BUILD-ICTX slot +32 = 0x08300000 (ctxentries 1 | HS)',  # 195
    'BUILD-ICTX slot +36 = 0x00050000 (root port 5)',        # 196
    'BUILD-ICTX ep0 +68 = 0x00400026 (mps 64 | Control | '   # 197
    'CErr 3)',
    'BUILD-ICTX ep0 +72 = ring | DCS(1)',                    # 198
    'BUILD-ICTX ep0 +80 = 8 (avg TRB length)',               # 199
]
UNB_3B_NAMES = [
    'unbound: ENUM-ADDRESS = 0 (refused, no write to DMA)',  # 200
    'idle: SLOT-DOWN = 0 (nothing held)',                    # 201
]
HW_3B_NAMES = [
    'XHCI-UP returns -1 (3b leg)',                           # 202
    'XHCI-RUN returns -1 (command ring runs)',               # 203
    'CMD-ENQ layout: params land, cycle bit set in control',  # 204
    'CMD-ENQ layout: control type field = 9 (the Enable Slot '  # 205
    'opcode written)',
    'ENABLE-SLOT completion cc = 1 (Success)',               # 206
    'ENABLE-SLOT slot in 1..MAX-SLOTS',                      # 207
    'DISABLE-SLOT (standalone slot) cc = 1',                 # 208
    'ENUM-ADDRESS(occupied port) returns a slot (nonzero)',  # 209
    'ENUM-ADDRESS slot = XSLOT (the enabled slot)',          # 210
    'SLOT-STATE = 2 (Addressed) -- output device context '   # 211
    'written by the controller',
    'DCBAA[slot] low = output device context (XODC)',        # 212
    'SLOT-DOWN returns -1 (all released)',                   # 213
    'SLOT-DOWN then idle SLOT-DOWN = 0 (nothing held)',      # 214
    'allocator symmetry: NLIVE after SLOT-DOWN = before UP',  # 215
]
if ALL_3B:
    for _name, _expr, _want in LOGIC_3B:
        v, raw = val(_expr)
        check(_name, v == _want, f'got {v}: {body_of(raw)!r}')
    # Scaling control: base 0 so the offset IS the stride.
    send('64 CTX-SZ !')
    for _nm, _ex, _w in ((SCALE_NAMES[0], '0 I-SLOT', 64),
                         (SCALE_NAMES[1], '0 I-EP0', 128),
                         (SCALE_NAMES[2], '0 O-EP0', 64)):
        v, raw = val(_ex)
        check(_nm, v == _w, f'got {v}: {body_of(raw)!r}')
    send('32 CTX-SZ !')
    for _nm, _ex, _w in ((SCALE_NAMES[3], '0 I-SLOT', 32),
                         (SCALE_NAMES[4], '0 I-EP0', 64)):
        v, raw = val(_ex)
        check(_nm, v == _w, f'got {v}: {body_of(raw)!r}')
    # BUILD-ICTX layout against suite-owned scratch (no controller):
    # the exact bytes Address Device will dereference.
    send('4096 PHYS-ALLOC XICTX !')
    send('4096 PHYS-ALLOC XEP0R !')
    xi, raw = val('XICTX @ 0<> XEP0R @ 0<> AND')
    alloc_ok = (xi == -1)
    check(ICTX_NAMES[0], alloc_ok, f'got {xi}: {body_of(raw)!r}')
    if alloc_ok:
        send('32 CTX-SZ !')
        send('5 3 BUILD-ICTX')
        for _nm, _ex, _w in (
                (ICTX_NAMES[1], 'XICTX @ 4 + @', 3),
                (ICTX_NAMES[2], 'XICTX @ 32 + @', 137363456),
                (ICTX_NAMES[3], 'XICTX @ 36 + @', 327680),
                (ICTX_NAMES[4], 'XICTX @ 68 + @', 4194342),
                (ICTX_NAMES[6], 'XICTX @ 80 + @', 8)):
            v, raw = val(_ex)
            check(_nm, v == _w, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XICTX @ 72 + @ XEP0R @ 1 OR =')
        check(ICTX_NAMES[5], v == -1, f'got {v}: {body_of(raw)!r}')
        # release the scratch, clear the vars for the HW leg
        send('XICTX @ 4096 PHYS-RELEASE 0 XICTX !')
        send('XEP0R @ 4096 PHYS-RELEASE 0 XEP0R !')
    else:
        for _nm in (ICTX_NAMES[1], ICTX_NAMES[2], ICTX_NAMES[3],
                    ICTX_NAMES[4], ICTX_NAMES[6], ICTX_NAMES[5]):
            check(_nm, False, 'scratch alloc failed')
    # Unbound / idle refusals (phase-8 shape).
    send('XHCI-BASE @ XB0 !')
    send('0 XHCI-BASE !')
    v, raw = val('5 ENUM-ADDRESS')
    check(UNB_3B_NAMES[0], v == 0, f'got {v}: {body_of(raw)!r}')
    v, raw = val('ENUM-CONFIGURE')
    check('unbound: ENUM-CONFIGURE = 0 (guard xhci.fth:736; the Sec-2 '
          'iron 0 ok was this guard firing, not an unguarded run)',
          v == 0, f'got {v}: {body_of(raw)!r}')
    send('XB0 @ XHCI-BASE !')
    v, raw = val('SLOT-DOWN')
    check(UNB_3B_NAMES[1], v == 0, f'got {v}: {body_of(raw)!r}')
    if ALL_2C and ALL_2D:
        zap()
        nl_a, _ = val('NLIVE', 2.0)
        v, raw = val('XHCI-UP', 3.0)
        check(HW_3B_NAMES[0], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XHCI-RUN', 3.0)
        check(HW_3B_NAMES[1], v == -1, f'got {v}: {body_of(raw)!r}')
        # CMD-ENQ layout on the live ring, doorbell NOT rung: write a
        # synthetic Enable-Slot TRB, read the 4 dwords back, reset the
        # producer.  Proves params + cycle-last before any hardware.
        send('0 XENQ !  1 XCCS !')
        send('286331153 286331153 286331153 9216 CMD-ENQ')
        # all four dwords: plo+0 phi+4 sts+8 (each 0x11111111 =
        # 286331153) and control+12 (0x2400 | cycle 1 = 9217).
        # (green 1 probe compared XCRING's ADDRESS, not @ -- fixed.)
        v, raw = val('XCRING @ @ 286331153 = '
                     'XCRING @ 4 + @ 286331153 = AND '
                     'XCRING @ 8 + @ 286331153 = AND '
                     'XCRING @ 12 + @ 9217 = AND')
        check(HW_3B_NAMES[2], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XCRING @ 12 + @ T-TYPE')
        check(HW_3B_NAMES[3], v == 9, f'got {v}: {body_of(raw)!r}')
        # reset the producer (controller never advanced -- no doorbell),
        # then a standalone Enable Slot: slot -> XSLOT2, cc -> CMD-CC2.
        send('0 XENQ !  1 XCCS !')
        send('ENABLE-SLOT XSLOT2 !  CMD-CC2 !')
        cc, raw = val('CMD-CC2 @')
        check(HW_3B_NAMES[4], cc == 1, f'got {cc}: {body_of(raw)!r}')
        sl, raw = val('XSLOT2 @')
        mps_ms, _ = val('MAX-SLOTS')
        check(HW_3B_NAMES[5],
              sl is not None and mps_ms is not None
              and 1 <= sl <= mps_ms, f'slot {sl}, MAX-SLOTS {mps_ms}')
        v, raw = val('XSLOT2 @ DISABLE-SLOT', 4.0)
        check(HW_3B_NAMES[6], v == 1, f'got {v}: {body_of(raw)!r}')
        # ENUM-ADDRESS refuses a not-enabled port with -3 (the trip's
        # highest-value fix): an out-of-range port reads PORTSC 0 ->
        # PED clear -> -3 at the ENTRY, not cc4 two layers down.  Runs
        # before the success case so the pre-fix vocab's allocate/fail
        # cleanup does not disturb the addressed slot.  Red-first: the
        # unguarded vocab allocates, fails Address Device, returns 0.
        v, raw = val('MAX-PORTS 1+ ENUM-ADDRESS', 4.0)
        check('ENUM-ADDRESS not-enabled port -> -3 (distinct from 0 '
              'and from a valid slot)', v == -3,
              f'got {v}: {body_of(raw)!r}')
        v, raw = val('FIRST-CCS ENUM-ADDRESS', 6.0)
        slot = v
        check(HW_3B_NAMES[7], slot is not None and slot > 0,
              f'got {slot}: {body_of(raw)!r}')
        v, raw = val('XSLOT @')
        check(HW_3B_NAMES[8], slot is not None and v == slot,
              f'XSLOT {v} vs returned {slot}: {body_of(raw)!r}')
        v, raw = val('SLOT-STATE')
        check(HW_3B_NAMES[9], v == 2, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XDCBAA @ XSLOT @ 8 * + @ XODC @ =')
        check(HW_3B_NAMES[10], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('SLOT-DOWN', 4.0)
        check(HW_3B_NAMES[11], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('SLOT-DOWN')
        check(HW_3B_NAMES[12], v == 0, f'got {v}: {body_of(raw)!r}')
        # tear down the controller and check allocator symmetry.
        send('XHCI-DOWN DROP')
        nl_b, raw = val('NLIVE', 2.0)
        check(HW_3B_NAMES[13], nl_a is not None and nl_b == nl_a,
              f'NLIVE {nl_a} -> {nl_b}: {body_of(raw)!r}')
    else:
        for _nm in HW_3B_NAMES:
            check(_nm, False,
                  'red by guard: 2c/2d machinery absent, not executed')
else:
    for _name, _expr, _want in LOGIC_3B:
        check(_name, False, 'red by guard: 3b words absent')
    for _nm in (SCALE_NAMES + ICTX_NAMES + UNB_3B_NAMES + HW_3B_NAMES):
        check(_nm, False, 'red by guard: 3b words absent')

print('\n=== Phase 11 (3c): EP0 control transfers / configure ===')
continuity('phase 11')
zap()
send('VARIABLE GB')
# Step 3c (design rulings 2026-09-12): EP0 control transfers ->
# read the real bMaxPacketSize0, correct via Evaluate Context when
# it differs from the 3b speed-derived default, read
# bConfigurationValue from the config descriptor (not assumed), set
# it, prove it with a GET_CONFIGURATION readback taken BEFORE (0)
# and AFTER (the value) -- a transition, not a value.
#
# Two forced-condition controls, because QEMU's fixture is too
# well-behaved to run the corrective branches (feedback_fixture_
# too_well_behaved):
#  - Evaluate Context is dead in the ENUM path on QEMU: the HS
#    keyboard's bMaxPacketSize0 = 64 = the HS default, so real ==
#    default and the compare never trips.  Force the output EP0
#    MPS to 8, call 64 EVAL-MPS, assert it corrects to 64.  Proves
#    OUR correction logic + that QEMU accepts Evaluate Context;
#    real-controller acceptance is an iron finding.
#  - GET_DESCRIPTOR(8) completion code: pre-registered 1 (Success).
#    QEMU's xhci_xfer_report resets shortpkt at the Status stage
#    before the IOC event, and no ISP is set on the data stage, so
#    the single event reports Success -- VERIFIED in v8.2.2 source,
#    not the short-packet 13 first assumed.  13 kept as the named
#    alternative (a controller with ISP semantics on a sub-MPS
#    read); CC-OK? accepts both so neither habitat reds.
#
# Pre-registered (2026-09-12, before the red run; suite-alone
# baseline 215/215, xhci-3b-green2-2026-09-12.log):
#   25 new checks.  New total = 240, DERIVED from the red log's
#   PASS/FAIL line count (not reconciled).  Emitted positions:
#   phase-11 checks 215-239, tripwire 240.
#   Red (3c stashed, 3b=HEAD): 216-218 definedness sent-red; the
#   rest red BY GUARD (control transfers must not run without the
#   words).  Predicted red 215/240 exactly, no baseline check moves.
#   Green derivations (source): CC-OK? {1,D}->T, {5,0}->F.  Device
#   desc byte1=1 (DEVICE), byte7=64 (HS kbd, dev-hid.c
#   desc_device_keyboard2).  bConfigurationValue=1 (dev-hid.c).
#   CFG-STATE 0 before SET, 1 after.  EVAL-MPS corrects output EP0
#   MPS 8->64 (QEMU xhci_evaluate_slot copies iep0[1] bits 31:16).
#   Green: 240/240.  Sweep at step-3 close, not here.
#   OUTCOME: red 215/240 (xhci-3c-red-2026-09-12.log), DERIVED.
#   Green 1: 237/240 (xhci-3c-green-2026-09-12.log): checks
#   227/228/234, ONE real bug + one fixture cause, two
#   symptoms (not three findings).  Diagnosed by unscored probe
#   (diag-3c.log): GET-CONFIG cc=1 cfg-before=1 | 1 SET-CONFIG
#   cc=0 | cfg-after=1.  (a) REAL BUG: SET-CONFIG's setup TRB
#   carried transfer-length 0; QEMU xhci_fire_ctl_transfer
#   rejects setup len != 8, fired no event, EP0-WAIT timed out
#   to 0 -> ENUM-CONFIGURE returned 0 (check 228; 234 cascade).
#   Fixed: setup len 0->8 (GET-DESC/GET-CONFIG already passed 8,
#   which is why they worked).  (b) FIXTURE (Cause B): QEMU's
#   usb-kbd is configured at realize, so cfg-before=1; no suite
#   phase configured it (audited), and usb_device_reset does not
#   clear dev->config.  Suite deconfigures (0 SET-CONFIG) for a
#   reliable 0 before-reading; iron reads 0 after Address Device.
#   Green 2: 240/240 (xhci-3c-green2-2026-09-12.log), DERIVED,
#   0 fail -- real 0->1 config transition observed; SET-CONFIG
#   returns 1 after the setup-length fix.
d_ep0 = (defined('EP0-ENQ') and defined('EP0-BELL')
         and defined('EP0-WAIT') and defined('CC-OK?'))
check('EP0-ENQ/EP0-BELL/EP0-WAIT/CC-OK? defined', d_ep0)      # 215
v, raw = val('DEF? GET-DESC 0<> DEF? EVAL-MPS 0<> AND '
             'DEF? SET-CONFIG 0<> AND DEF? GET-CONFIG 0<> AND')
d_xfer = (v == -1)
check('GET-DESC/EVAL-MPS/SET-CONFIG/GET-CONFIG defined', d_xfer,  # 216
      f'got {v}: {body_of(raw)!r}')
v, raw = val('DEF? ENUM-CONFIGURE 0<> DEF? CFG-STATE 0<> AND '
             'DEF? CTX-MPS 0<> AND')
d_cfg = (v == -1)
check('ENUM-CONFIGURE/CFG-STATE/CTX-MPS defined', d_cfg,      # 217
      f'got {v}: {body_of(raw)!r}')
ALL_3C = d_ep0 and d_xfer and d_cfg
CC_LOGIC = [
    ('CC-OK? 1 (Success) = true', '1 CC-OK?', -1),           # 218
    ('CC-OK? 13 (Short Packet) = true', '13 CC-OK?', -1),    # 219
    ('CC-OK? 5 (TRB Error) = false', '5 CC-OK?', 0),         # 220
    ('CC-OK? 0 (poll timeout) = false', '0 CC-OK?', 0),      # 221
]
HW_3C = [
    'XHCI-UP returns -1 (3c leg)',                           # 222
    'XHCI-RUN returns -1',                                   # 223
    'ENUM-ADDRESS(occupied port) returns a slot',            # 224
    'EP0-ENQ layout: four dwords land, cycle set in control',  # 225
    'EP0-ENQ layout: control type field = 9',                # 226
    'CFG-STATE before SET_CONFIGURATION = 0 (unconfigured)',  # 227
    'ENUM-CONFIGURE returns bConfigurationValue (nonzero)',   # 228
    'CFGCC8 (GET_DESCRIPTOR 8) in {1,13}; QEMU 1 (Success)',  # 229
    'CFGVAL = 1 (bConfigurationValue read, not assumed)',     # 230
    'standalone GET-DESC(device,18) cc in {1,13}',           # 231
    'device descriptor byte1 = 1 (DEVICE type -- read landed)',  # 232
    'device descriptor byte7 = 64 (HS bMaxPacketSize0)',      # 233
    'CFG-STATE after SET = CFGVAL (transition 0 -> value)',   # 234
    'forced EVAL: output EP0 MPS = 8 before (control set it)',  # 235
    'forced EVAL: 64 EVAL-MPS returns cc 1',                  # 236
    'forced EVAL: output EP0 MPS = 64 after (Evaluate '       # 237
    'Context corrected it)',
    'SLOT-DOWN returns -1',                                   # 238
    'allocator symmetry: NLIVE after teardown = before UP',   # 239
]
if ALL_3C:
    for _n, _e, _w in CC_LOGIC:
        v, raw = val(_e)
        check(_n, v == _w, f'got {v}: {body_of(raw)!r}')
    if ALL_2C and ALL_2D and ALL_3B:
        zap()
        nl_a, _ = val('NLIVE', 2.0)
        v, raw = val('XHCI-UP', 3.0)
        check(HW_3C[0], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XHCI-RUN', 3.0)
        check(HW_3C[1], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('FIRST-CCS ENUM-ADDRESS', 6.0)
        slot = v
        check(HW_3C[2], slot is not None and slot > 0,
              f'got {slot}: {body_of(raw)!r}')
        # EP0-ENQ layout on the live EP0 ring, doorbell NOT rung.
        send('286331153 286331153 286331153 9216 EP0-ENQ')
        v, raw = val('XEP0R @ @ 286331153 = '
                     'XEP0R @ 4 + @ 286331153 = AND '
                     'XEP0R @ 8 + @ 286331153 = AND '
                     'XEP0R @ 12 + @ 9217 = AND')
        check(HW_3C[3], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XEP0R @ 12 + @ T-TYPE')
        check(HW_3C[4], v == 9, f'got {v}: {body_of(raw)!r}')
        send('0 XEP0ENQ !  1 XEP0CCS !')   # controller never advanced
        # QEMU's usb-kbd is configured at realize (Cause B, diag
        # 2026-09-12): GET_CONFIGURATION reads 1 before any SET, and
        # no suite phase configured it.  Deconfigure so the before-
        # reading is a reliable 0 in BOTH habitats (iron reads 0
        # after Address Device regardless) -- the transition is then
        # a real 0->value, not dependent on device state that no
        # controller/port reset in this suite can clear.
        # IRON PRE-REGISTRATION (named for the trip): the card takes
        # the before-reading WITHOUT this deconfigure and expects 0 --
        # a freshly-plugged, just-Addressed keyboard is unconfigured.
        # Nonzero on the HP = firmware configured the device at USB
        # level (XHCI-OWNER=1 family, plausible on a BIOS that was
        # driving USB minutes earlier); record it, do not paper over.
        send('0 SET-CONFIG')
        v, raw = val('CFG-STATE', 4.0)
        check(HW_3C[5], v == 0, f'got {v}: {body_of(raw)!r}')
        v, raw = val('ENUM-CONFIGURE', 8.0)
        cfgret = v
        check(HW_3C[6], cfgret is not None and cfgret != 0,
              f'got {cfgret}: {body_of(raw)!r}')
        v, raw = val('CFGCC8 @')
        check(HW_3C[7],
              v in (1, 13), f'got {v} (expected 1 on QEMU): '
              f'{body_of(raw)!r}')
        v, raw = val('CFGVAL @')
        check(HW_3C[8], v == 1, f'got {v}: {body_of(raw)!r}')
        # standalone GET-DESC content (its own buffer).
        send('4096 PHYS-ALLOC GB !  GB @ 4096 0 FILL')
        v, raw = val('1 0 18 GB @ GET-DESC', 4.0)
        check(HW_3C[9], v is not None and v in (1, 13),
              f'got {v}: {body_of(raw)!r}')
        v, raw = val('GB @ 1 + C@')
        check(HW_3C[10], v == 1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('GB @ 7 + C@')
        check(HW_3C[11], v == 64, f'got {v}: {body_of(raw)!r}')
        send('GB @ 4096 PHYS-RELEASE  0 GB !')
        v, raw = val('CFG-STATE', 4.0)
        check(HW_3C[12], v == cfgret, f'got {v} vs {cfgret}: '
              f'{body_of(raw)!r}')
        # forced Evaluate Context control: set output EP0 MPS = 8,
        # correct to 64, read it back.  8<<16 | 0x26 = 524326.
        send('524326 XODC @ O-EP0 4 + !')
        v, raw = val('XODC @ O-EP0 4 + @ 16 RSHIFT 65535 AND')
        check(HW_3C[13], v == 8, f'got {v}: {body_of(raw)!r}')
        v, raw = val('64 EVAL-MPS', 4.0)
        check(HW_3C[14], v == 1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XODC @ O-EP0 4 + @ 16 RSHIFT 65535 AND')
        check(HW_3C[15], v == 64, f'got {v}: {body_of(raw)!r}')
        v, raw = val('SLOT-DOWN', 4.0)
        check(HW_3C[16], v == -1, f'got {v}: {body_of(raw)!r}')
        send('XHCI-DOWN DROP')
        nl_b, raw = val('NLIVE', 2.0)
        check(HW_3C[17], nl_a is not None and nl_b == nl_a,
              f'NLIVE {nl_a} -> {nl_b}: {body_of(raw)!r}')
    else:
        for _n in HW_3C:
            check(_n, False,
                  'red by guard: 2c/2d/3b machinery absent')
else:
    for _n, _e, _w in CC_LOGIC:
        check(_n, False, 'red by guard: 3c words absent')
    for _n in HW_3C:
        check(_n, False, 'red by guard: 3c words absent')

# ============================================================
# Phase 12: step 4 -- Configure Endpoint + HID interrupt-IN
# ============================================================
# Design: forthos-vocabularies/docs/xhci-step4-design-2026-09-14.md
# (rev 2 + rulings 2026-09-14, fixture note 2026-09-15).  The 63
# checks below are §5's list 1-63 written BEFORE the red run; the
# tripwire (64) moves to the end.  Pre-registered red on HEAD
# (ecd48e4 + fixture bc6f279, 242/242): 1-3 definedness sent-red,
# 4-63 red BY GUARD (nothing here may run without the words).
# Predicted 242/305 exactly, no baseline check moves; the total is
# READ from the red log's PASS/FAIL line count, never reconciled.
# Counting is by list length: PURE 12 + WALK 7 + EPCTX 7 + REFUSE 4
# + HW 30 = 60, + 3 definedness = 63.
#
# Spec ground (§1): DCI = 2*EPnum + dir; input ctrl Drop=0, Add=A0|A3
# = 9 (A1 clear: QEMU hcd-xhci.c:3486-3489 returns TRB Error 5
# otherwise); Configure Endpoint TRB type 12 (0x3000); Stop Endpoint
# type 15 (0x3C00); Normal TRB type 1, IOC|ISP = 0x424; EP type 7 =
# Interrupt IN -> dword1 = mps<<16 | 0x3E; dword4 = 8<<16 | 8 =
# 0x80008; FS interval = 3 + floor(log2(bInterval)), HS = bInterval-1;
# QEMU usb-kbd is HS, bInterval 7 -> field 6; cc 19 Context State
# Error (3493-3496), cc 12 Endpoint Not Enabled (2912-2919).
# Two habitats, two numbers: QEMU values asserted, iron's named in
# the design (HID-BINT predicted 8 or 10 on iron, any 1..255 legal).
print('\n=== Phase 12: step 4 Configure Endpoint + HID interrupt-IN ===')

v, raw = val('DEF? EP-DCI 0<> DEF? INTERVAL-FS 0<> AND '
             'DEF? INTERVAL-HS 0<> AND DEF? I-EPN 0<> AND '
             'DEF? O-EPN 0<> AND')
d_s4a = (v == -1)
check('EP-DCI/INTERVAL-FS/INTERVAL-HS/I-EPN/O-EPN defined', d_s4a,  # 1
      f'got {v}: {body_of(raw)!r}')
v, raw = val('DEF? EP-FIND 0<> DEF? BUILD-EPCTX 0<> AND '
             'DEF? CONFIGURE-EP 0<> AND DEF? STOP-EP 0<> AND '
             'DEF? EP-BELL 0<> AND')
d_s4b = (v == -1)
check('EP-FIND/BUILD-EPCTX/CONFIGURE-EP/STOP-EP/EP-BELL defined',  # 2
      d_s4b, f'got {v}: {body_of(raw)!r}')
v, raw = val('DEF? EP1-ENQ 0<> DEF? HID-POLL 0<> AND '
             'DEF? SET-PROTOCOL 0<> AND DEF? ENUM-HID 0<> AND '
             'DEF? HID-DOWN 0<> AND')
d_s4c = (v == -1)
check('EP1-ENQ/HID-POLL/SET-PROTOCOL/ENUM-HID/HID-DOWN defined',  # 3
      d_s4c, f'got {v}: {body_of(raw)!r}')
ALL_4 = d_s4a and d_s4b and d_s4c

# 4-15: pure logic, pushed literals.  13 forces CTX-SZ=64 (scaling
# proven; 64-byte acceptance stays an iron finding), 14-15 at 32.
PURE_4 = [
    ('129 EP-DCI = 3 (0x81 IN)', '129 EP-DCI', 3),                    # 4
    ('1 EP-DCI = 2 (0x01 OUT; direction bit isolated)', '1 EP-DCI', 2),  # 5
    ('130 EP-DCI = 5 (0x82; number field isolated)', '130 EP-DCI', 5),  # 6
    ('1 INTERVAL-FS = 3', '1 INTERVAL-FS', 3),                        # 7
    ('8 INTERVAL-FS = 6', '8 INTERVAL-FS', 6),                        # 8
    ('10 INTERVAL-FS = 6 (rounds DOWN to 8 ms)', '10 INTERVAL-FS', 6),  # 9
    ('255 INTERVAL-FS = 10 (clamp at table top)', '255 INTERVAL-FS', 10),  # 10
    ('7 INTERVAL-HS = 6 (QEMU HS keyboard)', '7 INTERVAL-HS', 6),     # 11
    ('1 INTERVAL-HS = 0', '1 INTERVAL-HS', 0),                        # 12
    ('forced CTX-SZ=64: 0 3 I-EPN = 256 (4x64)', '0 3 I-EPN', 256),   # 13
    ('CTX-SZ=32: 0 3 I-EPN = 128', '0 3 I-EPN', 128),                 # 14
    ('CTX-SZ=32: 0 3 O-EPN = 96', '0 3 O-EPN', 96),                   # 15
]

# 16-22: descriptor walker on suite-owned synthetic blobs (forced:
# QEMU's real blob only ever walks the happy path).  USB 2.0 §9.6
# shapes: config hdr 9, interface 9, HID 9, endpoint 7.
def _cfg(total):
    return [9, 2, total & 0xFF, total >> 8, 1, 1, 0, 0xA0, 50]


def _iface(n):
    return [9, 4, n, 0, 1, 3, 1, 1, 0]


_HID = [9, 0x21, 0x11, 1, 0, 1, 0x22, 0x3F, 0]


def _ep(addr, bint=10):
    return [7, 5, addr, 3, 8, 0, bint]


_VENDOR9 = [9, 0x23, 1, 2, 3, 4, 5, 6, 7]        # an unknown 9-byte descriptor
_BLOB_QEMU = _cfg(34) + _iface(0) + _HID + _ep(0x81)              # 34, EP @27
_BLOB_EXTRA = _cfg(43) + _iface(0) + _HID + _VENDOR9 + _ep(0x81)  # 43, EP @36
_BLOB_OUTIN = _cfg(41) + _iface(0) + _HID + _ep(0x01) + _ep(0x81)  # IN @34
_BLOB_NOIN = _cfg(34) + _iface(0) + _HID + _ep(0x01)              # no IN
_BLOB_BL0 = _cfg(34) + _iface(0) + [0] + _HID[1:] + _ep(0x81)     # bLength 0 @18
_BLOB_2IF = (_cfg(59) + _iface(0) + _HID + _ep(0x01)
             + _iface(1) + _HID + _ep(0x81))                        # 59, IN @52
assert len(_BLOB_2IF) == 59 and len(_BLOB_QEMU) == 34 \
    and len(_BLOB_EXTRA) == 43 and len(_BLOB_OUTIN) == 41 \
    and len(_BLOB_NOIN) == 34 and len(_BLOB_BL0) == 34   # wTotalLength = real length
WALK_4 = [
    ('EP-FIND: QEMU-shaped blob (34, EP at 27), len 34 = 27',    # 16
     _BLOB_QEMU, 34, 27),
    ('EP-FIND: extra 9-byte descriptor before EP, len 43 = 36',  # 17
     _BLOB_EXTRA, 43, 36),
    ('EP-FIND: interrupt OUT before IN -> the IN offset (34)',   # 18
     _BLOB_OUTIN, 41, 34),
    ('EP-FIND: no interrupt IN endpoint = 0', _BLOB_NOIN, 34, 0),  # 19
    ('EP-FIND: bLength 0 descriptor -> 0 within budget (step guard)',  # 20
     _BLOB_BL0, 34, 0),
    ('EP-FIND: wTotalLength 34 but len 20 (short read) = 0',     # 21
     _BLOB_QEMU, 20, 0),
    ('EP-FIND: two-interface blob -> HID-IFACE = 1 (the owner)',  # 22
     _BLOB_2IF, 59, None),
]


def poke(base_word, data):
    """Write bytes into a suite-owned page, 8 stores per line (TIB
    256; the longest line here is ~170 chars)."""
    for i in range(0, len(data), 8):
        chunk = data[i:i + 8]
        send(' '.join(f'{b} {base_word} {i + j} + C!'
                      for j, b in enumerate(chunk)), 0.3)


# 23-29: BUILD-EPCTX layout on scratch (no controller): XODC/XICTX/
# XEP1R from suite PHYS-ALLOC, HID-* cells set by the test (addr
# 0x81, mps 8, bInterval 10, DCI 3), synthetic XODC slot dword0 =
# 0x08100000 (entries 1, speed FS=1).  Expected slot dword0 after =
# 0x18100000 (entries 3<<27 | speed preserved) = 403701760.
EPCTX_4 = [
    ('BUILD-EPCTX: input ctrl +0 = 0 (Drop) and +4 = 9 (Add A0|A3)',  # 23
     'XICTX @ @ 0= XICTX @ 4 + @ 9 = AND', -1),
    ('BUILD-EPCTX: input slot dword0 = 0x18100000 (entries 3, FS kept)',  # 24
     'XICTX @ I-SLOT @', 403701760),
    ('BUILD-EPCTX: EP ctx dword0 interval bits 23:16 = 6 (bInt 10 @ FS)',  # 25
     'XICTX @ 3 I-EPN @ 16 RSHIFT 255 AND', 6),
    ('BUILD-EPCTX: EP ctx dword1 = 0x8003E (mps 8, Interrupt IN, CErr 3)',  # 26
     'XICTX @ 3 I-EPN 4 + @', 524350),
    ('BUILD-EPCTX: EP ctx dword2 = XEP1R | 1 (DCS)',                 # 27
     'XICTX @ 3 I-EPN 8 + @ XEP1R @ 1 OR =', -1),
    ('BUILD-EPCTX: EP ctx dword4 = 0x80008 (ESIT lo 8, avg TRB 8)',  # 28
     'XICTX @ 3 I-EPN 16 + @', 524296),
    ('BUILD-EPCTX: DEPTH unchanged (stray-cell control, Bug #35 shape)',  # 29
     'DEPTH >R BUILD-EPCTX DEPTH R> -', 0),
]

# 30-33: refusals (phase-8 shape; XB0 holds the bound base).
REFUSE_4 = [
    'unbound: ENUM-HID = 0 (no DMA write)',                       # 30
    'bound, no slot: ENUM-HID = 0',                               # 31
    'idle: HID-DOWN = 0',                                         # 32
    'no ring: HID-POLL = 0 and HID-PEND = 0 (refused, no enqueue)',  # 33
]

# 34-63: hardware leg on QEMU (iron values named in the design).
HW_4 = [
    'XHCI-UP returns -1 (step-4 leg)',                            # 34
    'XHCI-RUN returns -1',                                        # 35
    'FIRST-CCS ENUM-ADDRESS returns a slot (> 0)',                # 36
    'ENUM-CONFIGURE returns nonzero',                             # 37
    'ENUM-HID = -1 (full config read, EP found, Configure cc 1)',  # 38
    'ENUM-HID second call = 0 (already configured) and NLIVE unchanged',  # 39
    'HID-EPADDR = 129 (0x81, read from the endpoint descriptor)',  # 40
    'HID-MPS = 8',                                                # 41
    'HID-BINT = 7 (QEMU HS; iron: predicted 8 or 10, any 1..255 recorded)',  # 42
    'HID-IFACE = 0 (QEMU single interface)',                      # 43
    'GD-RESID = 0 after the full-config read (34 requested, 34 received)',  # 44
    'output slot ctx entries (XODC dword0 >> 27) = 3 after Configure',  # 45
    'output EP ctx (XODC 3 O-EPN) state bits 2:0 = 1 (Running)',  # 46
    '0 SET-PROTOCOL cc = 1',                                      # 47
    'no key: HID-POLL = 0 (timeout) and HID-PEND = -1 (TRB left pending)',  # 48
    'sendkey a then HID-POLL: cc in {1,13} (QEMU 1)',             # 49
    'HIDBUF byte2 = 4 (usage a) and byte0 = 0 (no modifier)',     # 50
    'next HID-POLL (release): cc OK and HIDBUF byte2 = 0',        # 51
    'forced wrap: 16 reports drained, all cc OK; XEP1ENQ < 15 and XEP1CCS = 0',  # 52
    'key after the wrap lands (HIDBUF byte2 = 5, usage b)',       # 53
    'forced refusal: CONFIGURE-EP with Add = 3 -> cc 5 TRB Error',  # 54
    'forced state error: CONFIGURE-EP on an Enabled-only slot -> cc 19',  # 55
    'forced: 5 STOP-EP (DCI never enabled) -> cc 12',             # 56
    'HID-DCI STOP-EP -> cc 1 and output EP ctx state = 3 (Stopped)',  # 57
    'forced unplug: HID-POLL after device_del kbd != 1 (cc 4 or 0 with XEV-LAST 34)',  # 58
    '#CONNECTED after device_del = before - 1',                   # 59
    'HID-DOWN after unplug in {-1, 1} (recorded)',                # 60
    'after HID-DOWN: HID-PEND = 0, XEP1R = 0, HID-POLL = 0 (refused)',  # 61
    'SLOT-DOWN returns -1',                                       # 62
    'allocator symmetry: NLIVE after teardown = before UP (whole leg)',  # 63
]


def _drain_polls(n, wait=2.0):
    """n HID-POLL calls; returns list of cc values."""
    out = []
    for _ in range(n):
        v, _r = val('HID-POLL', wait)
        out.append(v)
    return out


if ALL_4:
    # ---- 4-15 pure logic ----
    for i, (_n, _e, _w) in enumerate(PURE_4):
        if i == 9:
            send('64 CTX-SZ !')
        if i == 10:
            send('32 CTX-SZ !')
        v, raw = val(_e)
        check(_n, v == _w, f'got {v}: {body_of(raw)!r}')
    send('32 CTX-SZ !')
    # ---- 16-22 walker ----
    # Twelfth rule: the definition, its gate, and the store on
    # separate lines (a failed VARIABLE must not leave a store to run
    # against whatever is on the stack).
    send('VARIABLE S4B')
    v, raw = val('DEF? S4B 0<>')
    instrument_unscored('S4B defined (walker scratch cell)', v == -1,
                        f'got {v}: {body_of(raw)!r}')
    send('4096 PHYS-ALLOC S4B !')
    for _n, _blob, _len, _want in WALK_4:
        send('S4B @ 128 0 FILL')
        poke('S4B @', _blob)
        if _want is None:
            send(f'0 HID-IFACE !  S4B @ {_len} EP-FIND DROP', 3.0)
            v, raw = val('HID-IFACE @')
            check(_n, v == 1, f'got {v}: {body_of(raw)!r}')
        else:
            v, raw = val(f'S4B @ {_len} EP-FIND', 3.0)
            check(_n, v == _want, f'got {v}: {body_of(raw)!r}')
    send('S4B @ 4096 PHYS-RELEASE  0 S4B !')
    # ---- 23-29 BUILD-EPCTX on scratch ----
    send('4096 PHYS-ALLOC XODC !  4096 PHYS-ALLOC XICTX !  '
         '4096 PHYS-ALLOC XEP1R !')
    send('XODC @ 4096 0 FILL  XICTX @ 4096 0 FILL')
    send('129 HID-EPADDR !  8 HID-MPS !  10 HID-BINT !  3 HID-DCI !')
    send('134742016 XODC @ !')            # slot dword0 = 0x08100000
    send('BUILD-EPCTX', 2.0)
    for _n, _e, _w in EPCTX_4:
        v, raw = val(_e, 2.0)
        check(_n, v == _w, f'got {v}: {body_of(raw)!r}')
    send('XODC @ 4096 PHYS-RELEASE  XICTX @ 4096 PHYS-RELEASE  '
         'XEP1R @ 4096 PHYS-RELEASE')
    send('0 XODC !  0 XICTX !  0 XEP1R !')
    # Zero EVERY HID-* cell the scratch group set: 40/41 assert the
    # same 129/8 the scratch wrote, and must not pass on residue.
    send('0 HID-EPADDR !  0 HID-MPS !  0 HID-BINT !  0 HID-IFACE !  '
         '0 HID-DCI !')
    # ---- 30-33 refusals ----
    send('0 XHCI-BASE !')
    v, raw = val('ENUM-HID', 2.0)
    check(REFUSE_4[0], v == 0, f'got {v}: {body_of(raw)!r}')
    send('XB0 @ XHCI-BASE !  0 XSLOT !')
    v, raw = val('ENUM-HID', 2.0)
    check(REFUSE_4[1], v == 0, f'got {v}: {body_of(raw)!r}')
    v, raw = val('HID-DOWN', 2.0)
    check(REFUSE_4[2], v == 0, f'got {v}: {body_of(raw)!r}')
    v, raw = val('HID-POLL HID-PEND @ 0= SWAP 0= AND', 2.0)
    check(REFUSE_4[3], v == -1, f'got {v}: {body_of(raw)!r}')
    # ---- 34-63 hardware leg ----
    if ALL_2C and ALL_2D and ALL_3B and ALL_3C:
        zap()
        send('0 HID-EPADDR !  0 HID-MPS !  0 HID-BINT !  0 HID-IFACE !  '
             '0 HID-DCI !')                  # no scratch residue into 40-44
        nl_a, _ = val('NLIVE', 2.0)
        v, raw = val('XHCI-UP', 3.0)
        check(HW_4[0], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XHCI-RUN', 3.0)
        check(HW_4[1], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('FIRST-CCS ENUM-ADDRESS', 6.0)
        check(HW_4[2], v is not None and v > 0, f'got {v}: {body_of(raw)!r}')
        v, raw = val('ENUM-CONFIGURE', 8.0)
        check(HW_4[3], v is not None and v != 0, f'got {v}: {body_of(raw)!r}')
        v, raw = val('ENUM-HID', 8.0)
        check(HW_4[4], v == -1, f'got {v}: {body_of(raw)!r}')
        nl_h, _ = val('NLIVE', 2.0)
        v, raw = val('ENUM-HID', 4.0)
        nl_h2, raw2 = val('NLIVE', 2.0)
        check(HW_4[5], v == 0 and nl_h is not None and nl_h2 == nl_h,
              f'got {v}, NLIVE {nl_h} -> {nl_h2}: {body_of(raw)!r}')
        v, raw = val('HID-EPADDR @')
        check(HW_4[6], v == 129, f'got {v}: {body_of(raw)!r}')
        v, raw = val('HID-MPS @')
        check(HW_4[7], v == 8, f'got {v}: {body_of(raw)!r}')
        v, raw = val('HID-BINT @')
        check(HW_4[8], v == 7, f'got {v} (iron: record): {body_of(raw)!r}')
        v, raw = val('HID-IFACE @')
        check(HW_4[9], v == 0, f'got {v}: {body_of(raw)!r}')
        v, raw = val('GD-RESID @')
        check(HW_4[10], v == 0, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XODC @ @ 27 RSHIFT')
        check(HW_4[11], v == 3, f'got {v}: {body_of(raw)!r}')
        v, raw = val('XODC @ 3 O-EPN @ 7 AND')
        check(HW_4[12], v == 1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('0 SET-PROTOCOL', 4.0)
        check(HW_4[13], v == 1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('HID-POLL', 3.0)
        p, raw2 = val('HID-PEND @')
        check(HW_4[14], v == 0 and p == -1,
              f'poll {v}, pend {p}: {body_of(raw)!r}')
        mon('sendkey a')
        v, raw = val('HID-POLL', 3.0)
        check(HW_4[15], v in (1, 13), f'got {v}: {body_of(raw)!r}')
        v, raw = val('HIDBUF @ 2 + C@ 4 = HIDBUF @ C@ 0= AND')
        check(HW_4[16], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('HID-POLL', 3.0)
        b2, raw2 = val('HIDBUF @ 2 + C@')
        check(HW_4[17], v in (1, 13) and b2 == 0,
              f'cc {v}, byte2 {b2}: {body_of(raw)!r}')
        # forced wrap: 8 keys = 16 reports over a 15-slot ring.
        for _ in range(8):
            mon('sendkey a', 0.3)
            time.sleep(0.3)
        ccs = _drain_polls(16)
        enq, raw = val('XEP1ENQ @')
        ccs_, raw2 = val('XEP1CCS @')
        check(HW_4[18],
              all(c in (1, 13) for c in ccs) and enq is not None
              and enq < 15 and ccs_ == 0,
              f'ccs {ccs}, XEP1ENQ {enq}, XEP1CCS {ccs_}')
        mon('sendkey b')
        v, raw = val('HID-POLL', 3.0)
        b2, raw2 = val('HIDBUF @ 2 + C@')
        check(HW_4[19], v in (1, 13) and b2 == 5,
              f'cc {v}, byte2 {b2}: {body_of(raw)!r}')
        val('HID-POLL', 3.0)                 # drain the release
        # forced refusal: Address-Device-shaped Add flags.
        send('3 XICTX @ 4 + !')
        v, raw = val('CONFIGURE-EP', 4.0)
        check(HW_4[20], v == 5, f'got {v}: {body_of(raw)!r}')
        send('9 XICTX @ 4 + !')
        # forced state error: a slot that is Enabled, never Addressed.
        # ENABLE-SLOT ( -- cc slot ), CMD-RUN ( .. -- cc slot ): slot
        # on top, so SWAP DROP keeps the slot.  The new XSLOT must be
        # > 0 and differ from the saved one, or cc 19 could come from
        # the wrong slot; a bad setup fails 55 with the reason.
        send('VARIABLE S4S')
        v, raw = val('DEF? S4S 0<>')
        instrument_unscored('S4S defined (saved-slot cell)', v == -1,
                            f'got {v}: {body_of(raw)!r}')
        send('XSLOT @ S4S !')
        send('ENABLE-SLOT SWAP DROP XSLOT !', 4.0)
        ns, raw_ns = val('XSLOT @')
        ss, _ = val('S4S @')
        if ns is not None and ns > 0 and ns != ss:
            v, raw = val('CONFIGURE-EP', 4.0)
            check(HW_4[21], v == 19, f'got {v}: {body_of(raw)!r}')
        else:
            check(HW_4[21], False,
                  f'setup: ENABLE-SLOT gave XSLOT {ns} (saved {ss}): '
                  f'{body_of(raw_ns)!r}')
        send('XSLOT @ DISABLE-SLOT DROP  S4S @ XSLOT !', 4.0)
        v, raw = val('5 STOP-EP', 4.0)
        check(HW_4[22], v == 12, f'got {v}: {body_of(raw)!r}')
        v, raw = val('HID-DCI @ STOP-EP', 4.0)
        st, raw2 = val('XODC @ 3 O-EPN @ 7 AND')
        check(HW_4[23], v == 1 and st == 3,
              f'cc {v}, state {st}: {body_of(raw)!r}')
        # forced unplug on a fresh UP/ADDRESS/CONFIGURE/HID cycle
        # (re-arming a stopped ring is out of scope).
        send('HID-DOWN DROP  SLOT-DOWN DROP  XHCI-DOWN DROP', 6.0)
        send('XHCI-UP DROP  XHCI-RUN DROP', 6.0)
        send('FIRST-CCS ENUM-ADDRESS DROP', 6.0)
        send('ENUM-CONFIGURE DROP  ENUM-HID DROP', 12.0)
        val('HID-POLL', 3.0)                 # pending, no key
        nc_a, _ = val('#CONNECTED')
        mon('device_del kbd')
        time.sleep(1.0)
        v, raw = val('HID-POLL', 4.0)
        xl, raw2 = val('XEV-LAST @')
        check(HW_4[24], v is not None and v != 1,
              f'poll {v}, XEV-LAST {xl}: {body_of(raw)!r}')
        print(f'  (unplug shape recorded: HID-POLL={v}, XEV-LAST={xl})')
        nc_b, raw = val('#CONNECTED')
        check(HW_4[25], nc_a is not None and nc_b == nc_a - 1,
              f'#CONNECTED {nc_a} -> {nc_b}: {body_of(raw)!r}')
        v, raw = val('HID-DOWN', 6.0)
        check(HW_4[26], v in (-1, 1), f'got {v}: {body_of(raw)!r}')
        print(f'  (HID-DOWN after unplug recorded: {v})')
        v, raw = val('HID-PEND @ 0= XEP1R @ 0= AND HID-POLL 0= AND', 3.0)
        check(HW_4[27], v == -1, f'got {v}: {body_of(raw)!r}')
        v, raw = val('SLOT-DOWN', 4.0)
        check(HW_4[28], v == -1, f'got {v}: {body_of(raw)!r}')
        send('XHCI-DOWN DROP', 4.0)
        nl_b, raw = val('NLIVE', 2.0)
        check(HW_4[29], nl_a is not None and nl_b == nl_a,
              f'NLIVE {nl_a} -> {nl_b}: {body_of(raw)!r}')
    else:
        for _n in HW_4:
            check(_n, False, 'red by guard: 2c/2d/3b/3c machinery absent')
else:
    for _n, _e, _w in PURE_4:
        check(_n, False, 'red by guard: step-4 words absent')
    for _n, _b, _l, _w in WALK_4:
        check(_n, False, 'red by guard: step-4 words absent')
    for _n, _e, _w in EPCTX_4:
        check(_n, False, 'red by guard: step-4 words absent')
    for _n in REFUSE_4:
        check(_n, False, 'red by guard: step-4 words absent')
    for _n in HW_4:
        check(_n, False, 'red by guard: step-4 words absent')

raw = send('BASE @ DECIMAL .')
check('BASE tripwire: reads 10 at exit',                     # 305 (was 240)
      re.search(r'\b10\b', body_of(raw)) is not None,
      f'got: {body_of(raw)!r}')

continuity('final score')
print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
