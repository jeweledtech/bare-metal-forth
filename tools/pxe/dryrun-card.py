#!/usr/bin/env python3
"""Rule-16 dry-run: type a desk card's ```forth blocks into the
test-xhci QEMU fixture, in card order, exactly as written.

The lines come FROM THE CARD FILE (every ```forth fence, in order), so
the script cannot drift from the card: a dry-run log produced by this
tool is a log of the card's own text.  Substitutions are only for the
card's fill-in blanks:
    ______ ______ THRU   -> the XHCI block range on this build
    ______               -> the fixture's keyboard port (FIRST-CCS)
Trailing `\\ comments` are stripped (the terminal would take them as
comments anyway; stripping keeps the log readable).  Non-forth prose
between fences is not typed.  Monitor actions (QEMU has no hands) are
injected at named headings via HOOKS below and printed as such.

Usage: dryrun-card.py <card.md> <serial-port> <monitor-port> <block-range-vocab>
Fixture: launch the test-xhci QEMU line first (see tests/test_xhci.py
and the Makefile), then run this, then kill QEMU.
"""
import os
import re
import socket
import subprocess
import sys
import time

CARD, PORT, MON, VOCAB = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def blocks(name):
    r = subprocess.run([sys.executable, '-c', f"""
import os, importlib.util
spec = importlib.util.spec_from_file_location('wc', os.path.join('{ROOT}','tools','write-catalog.py'))
wc = importlib.util.module_from_spec(spec); spec.loader.exec_module(wc)
vocabs = wc.scan_vocabs(os.path.join('{ROOT}','forth','dict'))
_nc = (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
nb = 1 + _nc
for v in vocabs:
    nb = wc.place_vocab(nb, v['blocks_needed'])
    if v['name'] == '{name}':
        print(nb, nb + v['blocks_needed'] - 1); break
    nb += v['blocks_needed']
"""], capture_output=True, text=True).stdout.split()
    return int(r[0]), int(r[1])


s = socket.socket()
s.settimeout(10)
for _ in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except OSError:
        time.sleep(0.5)
time.sleep(2)
try:
    while True:
        s.recv(4096)
except Exception:
    pass


def send(c, w):
    s.sendall((c + '\r').encode())
    time.sleep(w)
    s.settimeout(2)
    b = b''
    while True:
        try:
            d = s.recv(4096)
            if not d:
                break
            b += d
        except Exception:
            break
    out = b.decode('ascii', 'replace')
    return (out.split('\n', 1)[1] if '\n' in out else out).strip()


_m = None


def mon(c, w=0.5):
    global _m
    if _m is None:
        _m = socket.socket()
        _m.settimeout(5)
        _m.connect(('127.0.0.1', MON))
        time.sleep(0.5)
        try:
            _m.recv(4096)
        except Exception:
            pass
    _m.sendall((c + '\n').encode())
    time.sleep(w)
    try:
        _m.recv(4096)
    except Exception:
        pass
    print(f'      (monitor) {c}')


# Wait budgets by content: THRU and controller legs are slow.
def wait_for(line):
    if 'THRU' in line:
        return 12
    for k, w in (('PORT-RESET', 12), ('ENUM-CONFIGURE', 8), ('ENUM-HID', 8),
                 ('ENUM-ADDRESS', 6), ('HID-DOWN', 6), ('CONFIGURE-EP', 4),
                 ('STOP-EP', 4), ('SLOT-DOWN', 4), ('XHCI-DOWN', 4),
                 ('HID-POLL', 3), ('PHYS-AUDIT', 3), ('.PORTS', 3),
                 ('CFG-STATE', 4), ('XHCI-', 3), ('SET-PROTOCOL', 4)):
        if k in line:
            return w
    return 1.2


# Monitor hooks keyed by the card heading they follow (QEMU has no
# hands; on iron the operator presses the keys).  Each fires once,
# BEFORE the first forth line under that heading.
HOOKS = {
    '### 9.2': [('sendkey a', 'press a (QEMU cannot hold a key; press+release both queue)')],
    '### 9.3': [(f'sendkey {k}', f'press {k}') for k in 'bcdefghi'],
    '### 9.4': [('sendkey j', 'press j (after the wrap)')],
}
# Lines the card says to repeat until a condition; typed up to N times.
REPEAT = {'HID-POLL .   \\ repeat this line': 20}

xs, xe = blocks(VOCAB)
port = None
print(f'DRY-RUN {os.path.basename(CARD)} on the QEMU fixture (rule 16); '
      f'{VOCAB} THRU {xs} {xe}; alive: {send("7 6 * .", 1.2)}')

heading = ''
in_forth = False
hooks_fired = set()
saved_dword3 = None
for raw in open(CARD):
    line = raw.rstrip('\n')
    if line.startswith('#'):
        heading = line.strip()
        continue
    if line.startswith('```forth'):
        in_forth = True
        for key, acts in HOOKS.items():
            if heading.startswith(key) and key not in hooks_fired:
                hooks_fired.add(key)
                for cmd, why in acts:
                    print(f'[{heading}] hook: {why}')
                    mon(cmd, 0.3)
                    time.sleep(0.3)
        continue
    if line.startswith('```'):
        in_forth = False
        continue
    if not in_forth or not line.strip() or line.strip().startswith('\\'):
        continue
    typed = line
    repeat = 1
    for k, n in REPEAT.items():
        if k in line:
            repeat = n
    typed = re.sub(r'\s*\\.*$', '', typed).strip()      # strip trailing comment
    if '______ ______ THRU' in typed:
        typed = typed.replace('______ ______ THRU', f'{xs} {xe} THRU')
    if '______' in typed:
        if port is None:
            send(': FIRST-CCS 0 MAX-PORTS 1+ 1 DO I PORTSC@ P-CCS OVER 0= AND IF DROP I THEN LOOP ;', 1.2)
            port = re.findall(r'-?\d+', send('FIRST-CCS .', 1.2))[0]
            print(f'      (fixture: FIRST-CCS = {port}; fills every ______ port blank)')
        typed = typed.replace('______', port)
    if typed.startswith('<saved>'):
        typed = typed.replace('<saved>', saved_dword3 or '18000001')
    for i in range(repeat):
        r = send(typed, wait_for(typed))
        print(f'[{heading[:24]}] {typed}\n      -> {r}')
        if 'DUP . 7FFFFFF AND' in typed:
            m = re.findall(r'\b[0-9A-F]{6,8}\b', r)
            saved_dword3 = m[0] if m else None
        if repeat > 1:
            v = re.findall(r'-?\d+', r)
            if not v or int(v[0]) == 0:
                print(f'      (repeat stopped after {i + 1} polls; nonzero returns: {i})')
                break
print(f'EXIT DEPTH/BASE: {send("DEPTH .", 1.2)} / {send("BASE @ DECIMAL .", 1.2)}')
