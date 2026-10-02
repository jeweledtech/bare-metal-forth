#!/usr/bin/env python3
"""PCI-BAR vocab gate, (bz) R2: instances of a class, in scan order.

docs/evidence/bz-base-finding-prereg-2026-09-27.md.  pci-bar.fth is a
public, block-loaded vocabulary (no boot-time caller, ruling
2026-09-07).  It holds PCI-BAR64@ (moved verbatim from xhci.fth) and
the find-nth-by-class search that translated driver vocabularies use
to find their device without a hand-typed address.

The fixture has TWO intel-hda functions, so "never chosen implicitly"
is exercised with more than one instance, which the HP cannot do.

Pre-registered red (2026-09-27, written before the first run; red
tree = HEAD without forth/dict/pci-bar.fth): 16 scored checks.  Red:
1 (no catalog placement), 2 (THRU not attempted), 3-15 (every one
needs a PCI-BAR word).  Green on red: 16 (DEPTH 0 at exit: the red
path leaves nothing on the stack).  Red totals 1/16, exit 1.

Instrument controls (fatal, unscored): interpreter alive; DEF? says
yes to PCI-FIND and no to a word that never existed; the fixture's
first 04/03 function is found by embedded PCI-FIND-CLASS.
"""
import hashlib
import os
import re
import socket
import subprocess
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4587
IMG = sys.argv[2] if len(sys.argv) > 2 else 'build/combined.img'
with open(IMG, 'rb') as f:
    print(f'input sha256 {hashlib.sha256(f.read()).hexdigest()}  {IMG}')

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_vocab_blocks(vocab_name):
    """Host-side catalog placement, the same scan write-catalog uses
    (test_xhci.py's resolver, unchanged)."""
    result = subprocess.run([sys.executable, '-c', f"""
import os
import importlib.util
spec = importlib.util.spec_from_file_location('wc', os.path.join(
    '{PROJECT_DIR}', 'tools', 'write-catalog.py'))
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)
vocabs = wc.scan_vocabs(os.path.join('{PROJECT_DIR}', 'forth', 'dict'))
_nc = (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
nb = 1 + _nc
for v in vocabs:
    nb = wc.place_vocab(nb, v['blocks_needed'])
    if v['name'] == '{vocab_name}':
        print(f"{{nb}} {{nb + v['blocks_needed'] - 1}}")
        break
    nb += v['blocks_needed']
"""], capture_output=True, text=True, timeout=10)
    parts = result.stdout.split()
    return (int(parts[0]), int(parts[1])) if len(parts) == 2 else (None, None)


import serial as _ser  # tests/serial.py; script-dir sys.path shadows pyserial
s = _ser.connect_and_sync(PORT, budget=30.0)


def send(cmd, wait=1.0):
    # Bounded in aggregate via serial.send_expect (TASK_HARNESS_KILL_BY_PID
    # §3c). Same raw-reply contract.
    return _ser.send_expect(s, cmd, budget=max(wait + 6.0, 10.0), settle=wait)


def body_of(raw):
    """Drop the echoed input line (it holds the command's own text)."""
    return raw.split('\n', 1)[1] if '\n' in raw else raw


def val(expr, wait=1.5):
    """One value, read in DECIMAL."""
    raw = send(f'DECIMAL {expr} .', wait)
    body = body_of(raw)
    if '?' in body:
        return None, raw
    nums = re.findall(r'-?\d+', body)
    return (int(nums[-1]) if nums else None), raw


def stack(expr, wait=1.5):
    """The whole stack after EXPR, in DECIMAL, as a list (None if the
    line did not resolve).  ZAP before and after, so each reading
    starts and ends empty."""
    zap()
    raw = send(f'DECIMAL {expr} .S', wait)
    body = body_of(raw)
    zap()
    if '?' in body:
        return None, raw
    m = re.search(r'<([^>]*)>', body)
    return ([int(x) for x in m.group(1).split()] if m else None), raw


PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- {detail}' if detail else f'  FAIL: {name}')
    return ok


def instrument(name, ok, detail=''):
    if not ok:
        print(f'INSTRUMENT FAIL: {name} -- {detail} -- aborting, no score')
        sys.exit(3)
    print(f'  instrument: {name}')


def alive():
    v, _ = val('7 6 *')
    return v == 42


def zap():
    send('ZAP')
    v, raw = val('ZBAD @')
    if v != 0:
        print(f'INSTRUMENT FAIL: ZAP refused (ZBAD={v}): {body_of(raw)!r}')
        sys.exit(3)


def defined(name):
    v, _ = val(f'DEF? {name}')
    return v is not None and v != 0


print('\n=== Phase 0: instrument controls (fatal on failure) ===')
instrument('interpreter alive', alive())
send('ONLY FORTH DEFINITIONS')
send('ALSO PCI-ENUM')
send(': DEF? WORD FIND NIP ;')
send('VARIABLE ZN')
send('VARIABLE ZBAD')
send(': ZAP 0 ZBAD !  DEPTH DUP 0< SWAP 1024 > OR '
     'IF -1 ZBAD ! EXIT THEN '
     '64 ZN !  BEGIN DEPTH 0<> ZN @ 0> AND '
     'WHILE DROP -1 ZN +! REPEAT ;')
zap()
_pos, _ = val('DEF? PCI-FIND')
_neg, _ = val('DEF? ZZZ-NEVER-DEFINED')
instrument('DEF? says yes and no', _pos not in (None, 0) and _neg == 0,
           f'PCI-FIND={_pos} ZZZ-NEVER-DEFINED={_neg}')
first, raw = stack('4 3 PCI-FIND-CLASS')
instrument('fixture: embedded PCI-FIND-CLASS finds an 04/03 function',
           first is not None and len(first) == 4 and first[3] == -1,
           f'{body_of(raw)!r}')
print(f'  PCI-FIND-CLASS 4 3 -> {first[:3]}')

print('\n=== Phase 1: block-load PCI-BAR (pre-registered red) ===')
bs, be = get_vocab_blocks('PCI-BAR')
check('PCI-BAR has catalog placement', bs is not None,          # 1
      'forth/dict/pci-bar.fth absent from the scan')
if bs is not None:
    print(f'  loading PCI-BAR ({bs}-{be} THRU)...')
    send(f'DECIMAL {bs} {be} THRU', 10)
    check('PCI-BAR blocks load (interpreter alive after THRU)',  # 2
          alive())
else:
    check('PCI-BAR blocks load (interpreter alive after THRU)',  # 2
          False, 'no placement: THRU not attempted')
send('ONLY FORTH DEFINITIONS')
send('ALSO PCI-ENUM')
d_voc = defined('PCI-BAR')
check('PCI-BAR vocabulary defined', d_voc)                      # 3
if d_voc:
    send('ALSO PCI-BAR')       # guarded: ALSO of an undefined name corrupts
d_cnt = defined('PCI-CLASS-COUNT')
d_nth = defined('PCI-CLASS-NTH')
d_lst = defined('PCI-CLASS-LIST')
d_bar = defined('PCI-BAR64@')
check('PCI-CLASS-COUNT, -NTH, -LIST defined',                   # 4
      d_cnt and d_nth and d_lst, f'{d_cnt} {d_nth} {d_lst}')
check('PCI-BAR64@ defined in PCI-BAR', d_bar)                   # 5

print('\n=== Phase 2: two intel-hda functions ===')
zap()
n, raw = val('4 3 PCI-CLASS-COUNT') if d_cnt else (None, '')
check('4 3 PCI-CLASS-COUNT = 2', n == 2, f'got {n}')            # 6
i0, raw0 = stack('4 3 0 PCI-CLASS-NTH') if d_nth else (None, '')
check('instance 0 found', i0 is not None and len(i0) == 4       # 7
      and i0[3] == -1, f'{body_of(raw0)!r}')
check('instance 0 = PCI-FIND-CLASS (agreement control)',        # 8
      i0 is not None and i0 == first, f'{i0} vs {first}')
i1, raw1 = stack('4 3 1 PCI-CLASS-NTH') if d_nth else (None, '')
check('instance 1 found, a different b:d:f',                    # 9
      i1 is not None and len(i1) == 4 and i1[3] == -1
      and i0 is not None and i1[:3] != i0[:3], f'{i1} vs {i0}')
r2, _ = stack('4 3 2 PCI-CLASS-NTH') if d_nth else (None, '')
check('instance 2 refuses: <0 >', r2 == [0], f'{r2}')           # 10
rm, _ = stack('4 3 -1 PCI-CLASS-NTH') if d_nth else (None, '')
check('instance -1 refuses: <0 >', rm == [0], f'{rm}')          # 11
if d_nth and d_bar:
    send(': IB >R 4 3 R> PCI-CLASS-NTH IF 0 PCI-BAR64@ ELSE 0 THEN ;')
    b0, _ = val('0 IB')
    b1, _ = val('1 IB')
else:
    b0 = b1 = None
check('the two instances have distinct nonzero BAR0',           # 12
      b0 not in (None, 0) and b1 not in (None, 0) and b0 != b1,
      f'{b0} {b1}')
zap()
lst = body_of(send('HEX 4 3 PCI-CLASS-LIST DECIMAL', 2)) if d_lst else ''
rows = re.findall(r'^\s*(\d+) ([0-9A-F]{2}):([0-9A-F]{2})\.([0-7])',
                  lst, re.M)
print(f'  PCI-CLASS-LIST rows: {rows}')
check('PCI-CLASS-LIST prints exactly 2 rows, 0 and 1',          # 13
      [r[0] for r in rows] == ['0', '1'], f'{lst!r}')
check('row 0 is instance 0', i0 is not None and len(rows) > 0   # 14
      and [int(x, 16) for x in rows[0][1:]] == i0[:3],
      f'{rows[:1]} vs {i0}')
z, _ = val('7 7 PCI-CLASS-COUNT') if d_cnt else (None, '')
zn, _ = stack('7 7 0 PCI-CLASS-NTH') if d_nth else (None, '')
check('absent class 7/7: count 0, instance 0 refuses',          # 15
      z == 0 and zn == [0], f'{z} {zn}')

zap()
dep, _ = val('DEPTH')
check('DEPTH 0 at exit', dep == 0, f'got {dep}')                # 16

print(f'\nResults: {PASS}/{PASS + FAIL} passed')
sys.exit(0 if FAIL == 0 else 1)
