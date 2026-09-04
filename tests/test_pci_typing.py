#!/usr/bin/env python3
"""PCI class-code typing gate: PCI-PROGIF@, PCI-FIND-CLASS,
PCI-FIND-TYPE, FIND-USB/FIND-XHCI, PCI-TYPES.

Docket step 1 (main line).  pci-enum.fth already reads class and
subclass into PCI-TBL at scan time and ships PCI-CLASS@/PCI-BAR@;
what this suite gates is the step from "prints vendor:device" to
typed discovery: the prog-IF byte (offset 0x08 bits 8-15 -- the
UHCI 00 / OHCI 10 / EHCI 20 / xHCI 30 / USB4 40 discriminator),
find-by-class with the live config dword as authority (the stored
table bytes are a pre-filter only -- a typed match split across
two points in time is a gap on any machine step 2 rescans), and
the human-readable PCI-TYPES listing that feeds the adaptive
shell's USING offers.

The harness QEMU carries -M pc -device qemu-xhci (Red Hat
1b36:000d, class 0C/03/30): the default i440FX machine has no USB
controller, so the target class exists only by construction.  -M
pc is pinned so a future QEMU default flip to q35 cannot silently
change the bus this suite characterizes.

Instrument controls (green on BOTH red and green runs):
liveness; PCI-COUNT nonzero (boot auto-scan ran); and
1B36:000D found via the OLD machinery (PCI-FIND) -- chosen over
the host bridge 8086:1237 because it is machine-type-independent
and proves the exact device the new words must find.  An all-'?'
dead session fails the PCI-FIND control, so an instrument failure
cannot impersonate the pre-registered red (the fd67765 lesson:
ONLY FORTH DEFINITIONS without ALSO PCI-ENUM turns every probe
into '?' and mimics red exactly).

Bug-#31 fencing (lesson of this suite's invalid run 1, retained
as docs/evidence/pci-typing-red-2026-09-03-run1-invalid.log): a
colon definition that references a not-yet-existing word fails
MID-DEFINITION and leaves STATE=1, wedging the session -- every
later probe returns empty and the "red" is an instrument corpse.
So no colon definition here ever names a new word until DEF?
(compiled WORD FIND NIP -- interactive WORD..FIND self-clobbers
word_buffer, test_install.py precedent) proves it nameable, and
DEF? itself is bracketed by a found-control and a never-existed
control before it is believed (the clobber symptom is identical
nonzero for found and not-found alike).  Capture words do not
print; val() is the only printer, so the stack stays balanced
(run 1's underflow: XCAP printed its flag AND val appended '.').

Pre-registered red (2026-09-03, before the red run): checks 4-18
red, 1-3 green.  On the red tree DEF? reads 0 for every new word,
capture definitions are skipped, and every dependent probe reads
'?' at use.

BASE legs: PCI-TYPES prints only via ." and the nibble-masked
.H2/.H4/.H8 chain (>HEXCH does F AND -- verified in source, not
assumed), so it is base-transparent by construction; the suite
proves it from BOTH entered-DECIMAL and entered-HEX, because a
one-legged probe passes coincidentally (commit 78ac6fd).  BASE
probes are 'BASE @ DECIMAL .' -- a bare 'BASE @ .' prints 10 in
every base and asserts nothing.

Out of scope, recorded: FIND-AHCI (paid tier) migration to
01 06 PCI-FIND-CLASS is a follow-on -- private repo, iron-frozen
artifacts.  ECAM and the 64-bit BAR upper dword are deferred;
QEMU maps BAR0 below 4G, and step 2 adds PCI-BAR64@ if iron
needs it.
"""
import hashlib
import re
import socket
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4596

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


def alive():
    v, _ = val('7 6 *')
    return v == 42


print('\n=== Phase 0: instrument controls (green both runs) ===')
check('interpreter alive', alive())
send('ONLY FORTH DEFINITIONS')
send('ALSO PCI-ENUM')
v, raw = val('PCI-COUNT @')
check('PCI-COUNT nonzero (boot auto-scan populated PCI-TBL)',
      v is not None and v > 0, f'got {v}: {body_of(raw)!r}')
# Capture instrument: variables + a finder that stores b/d/f and
# leaves the flag alone (val prints it), so the stack is balanced
# whichever way it goes.  Uses only words that exist on BOTH
# trees -- this is the instrument, not the test.
send('VARIABLE TB  VARIABLE TD  VARIABLE TF')
send('HEX')
send(': XCAP 1B36 000D PCI-FIND IF TF ! TD ! TB ! -1 ELSE 0 THEN ;')
send('DECIMAL')
v, raw = val('XCAP')
check('qemu-xhci 1B36:000D found via OLD PCI-FIND (control)',
      v == -1, f'got {v}: {body_of(raw)!r}')

# Nameability probe + its two sanity brackets (instrument, not
# named checks: if either bracket fails, defined() answers False
# for everything, capture defs are skipped, and checks 4-18 fail
# loudly by name -- a broken probe cannot impersonate green).
send(': DEF? WORD FIND NIP ;')
# Stack drain, old words only: aborts on the red tree may leave
# residue; ZAP before each phase makes every val self-contained.
send(': ZAP BEGIN DEPTH 0<> WHILE DROP REPEAT ;')
_pos, _raw_p = val('DEF? PCI-FIND')
_neg, _raw_n = val('DEF? ZZZ-NEVER-DEFINED')
DEF_OK = (_pos is not None and _pos != 0 and _neg == 0)
print(f'  probe sanity: DEF? PCI-FIND={_pos} '
      f'ZZZ-NEVER-DEFINED={_neg} -> {"OK" if DEF_OK else "BROKEN"}')


def defined(name):
    """True iff the live search order resolves name AND the probe
    itself passed both sanity brackets."""
    if not DEF_OK:
        return False
    v, _ = val(f'DEF? {name}')
    return v is not None and v != 0


print('\n=== Phase 1: prog-IF read ===')
send('ZAP')
d_progif = defined('PCI-PROGIF@')
check('PCI-PROGIF@ defined (DEF? nonzero)', d_progif)
v, raw = val('TB @ TD @ TF @ PCI-PROGIF@')
check('prog-IF of 1B36:000D is 30 (xHCI, known nonzero)',
      v == 0x30, f'got {v}: {body_of(raw)!r}')

print('\n=== Phase 2: find-by-class ===')
send('ZAP')
d_findclass = defined('PCI-FIND-CLASS')
check('PCI-FIND-CLASS defined (DEF? nonzero)', d_findclass)
# Compile capture words ONLY when the word is nameable: a colon
# def referencing a missing word dies mid-definition with STATE
# stuck at 1 (Bug #31 -- this suite's run-1 corpse).
if d_findclass:
    send('HEX')
    send(': CCAP 0C 03 PCI-FIND-CLASS '
         'IF TF ! TD ! TB ! -1 ELSE 0 THEN ;')
    send(': NCAP 0F 00 PCI-FIND-CLASS '
         'IF TF ! TD ! TB ! -1 ELSE 0 THEN ;')
    send('DECIMAL')
# Zero the capture vars so a red (CCAP never compiled) cannot let
# downstream checks read the CONTROL's capture and pass vacuously:
# 0/0/0 is the host bridge (class 06/00), which fails every
# xHCI-shaped assertion by value, not by accident.
send('0 TB !  0 TD !  0 TF !')
v, raw = val('CCAP')
check('class 0C sub 03 found (xHCI present by construction)',
      v == -1, f'got {v}: {body_of(raw)!r}')
raw = send('DECIMAL TB @ TD @ TF @ PCI-CLASS@ . .')
nums = re.findall(r'-?\d+', body_of(raw))
check('round-trip: found b/d/f reads back class 0C sub 03',
      v == -1 and len(nums) >= 2 and int(nums[-1]) == 0x0C
      and int(nums[-2]) == 0x03,
      f'got: {body_of(raw)!r}')
send('ZAP')
v, raw = val('NCAP')
check('negative control: class 0F sub 00 returns 0',
      v == 0, f'got {v}: {body_of(raw)!r}')

print('\n=== Phase 3: typed find (prog-IF discriminates) ===')
send('ZAP')
d_xhci = defined('FIND-XHCI')
d_type = defined('PCI-FIND-TYPE')
if d_xhci and d_type:
    send('HEX')
    send(': TCAP FIND-XHCI IF TF ! TD ! TB ! -1 ELSE 0 THEN ;')
    send(': OCAP 0C 03 10 PCI-FIND-TYPE '
         'IF TF ! TD ! TB ! -1 ELSE 0 THEN ;')
    send('DECIMAL')
# Re-zero: a red TCAP must not inherit Phase 2's capture (see the
# Phase 2 note -- same vacuous-green hazard, same defense).
send('0 TB !  0 TD !  0 TF !')
v, raw = val('TCAP')
check('FIND-XHCI finds the controller', v == -1,
      f'got {v}: {body_of(raw)!r}')
v, raw = val('TB @ TD @ TF @ PCI-PROGIF@')
check('typed find landed on prog-IF 30', v == 0x30,
      f'got {v}: {body_of(raw)!r}')
# OCAP overwrites TB/TD/TF only on a hit; a hit here is itself the
# failure, so the clobber cannot poison a passing run.
send('ZAP')
v, raw = val('OCAP')
check('negative: prog-IF 10 (OHCI) on this machine returns 0',
      v == 0, f'got {v}: {body_of(raw)!r}')
bar_v, raw = val('TB @ TD @ TF @ 0 PCI-BAR@')
check('BAR0 at found function nonzero',
      bar_v is not None and bar_v != 0,
      f'got {bar_v}: {body_of(raw)!r}')
v, raw = val('TB @ TD @ TF @ 0 PCI-BAR@ 1 AND')
# Gated on the nonzero read above: bit-0-of-zero is 0, so a bare
# ==0 here would pass on a dead read -- absence of evidence.
check('BAR0 bit 0 clear (MMIO, not I/O)',
      bar_v is not None and bar_v != 0 and v == 0,
      f'bar={bar_v} bit0={v}: {body_of(raw)!r}')

print('\n=== Phase 4: PCI-TYPES, both BASE legs ===')
MMIO_RE = re.compile(r'MMIO [0-9A-F]{8}')
send('ZAP')
send('DECIMAL')
raw = send('PCI-TYPES', 2.0)
body = body_of(raw)
dec_listed = ('USB host (xHCI)' in body
              and MMIO_RE.search(body) is not None)
check('entered DECIMAL: typed listing names USB host (xHCI) + MMIO',
      dec_listed, f'got: {body!r}')
raw = send('BASE @ DECIMAL .')
# Gated on the listing having printed: an errored PCI-TYPES also
# leaves BASE alone, so an ungated ==10 would go green on red.
check('entered DECIMAL: BASE untouched by the listing (reads 10)',
      dec_listed and re.search(r'\b10\b', body_of(raw)) is not None
      and '?' not in body_of(raw), f'got: {body_of(raw)!r}')
send('HEX')
raw = send('PCI-TYPES', 2.0)
body = body_of(raw)
hex_listed = ('USB host (xHCI)' in body
              and MMIO_RE.search(body) is not None)
check('entered HEX: typed listing names USB host (xHCI) + MMIO',
      hex_listed, f'got: {body!r}')
raw = send('BASE @ DECIMAL .')
check('entered HEX: BASE untouched by the listing (reads 16)',
      hex_listed and re.search(r'\b16\b', body_of(raw)) is not None
      and '?' not in body_of(raw), f'got: {body_of(raw)!r}')
send('DECIMAL')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
