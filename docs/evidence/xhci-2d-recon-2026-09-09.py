#!/usr/bin/env python3
"""2d recon: read-only PORTSC survey with usb-kbd attached.

Measures (no writes to any xHCI register except the 2b bind path):
  HCS1 raw, MAX-PORTS, MAX-SLOTS, HCC1
  PORTSC dword for every port (OP-BASE + 0x400 + (p-1)*0x10)
Decodes CCS/PED/PP/PR/speed/PLS/CSC in Python -- no new Forth.
"""
import re
import socket
import subprocess
import sys
import time

PORT = 4606
PROJECT = '/home/bbrown/projects/forthos'

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
for _ in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print('FAIL: connect')
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
    return raw.split('\n', 1)[1] if '\n' in raw else raw


def val(expr, wait=1.5):
    raw = send(f'DECIMAL {expr} .', wait)
    body = body_of(raw)
    if '?' in body:
        return None, raw
    nums = re.findall(r'-?\d+', body)
    return (int(nums[-1]) if nums else None), raw


def get_vocab_blocks(name):
    r = subprocess.run([sys.executable, '-c', f"""
import os, importlib.util
spec = importlib.util.spec_from_file_location('wc', os.path.join(
    '{PROJECT}', 'tools', 'write-catalog.py'))
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)
vocabs = wc.scan_vocabs(os.path.join('{PROJECT}', 'forth', 'dict'))
_nc = (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
nb = 1 + _nc
for v in vocabs:
    nb = wc.place_vocab(nb, v['blocks_needed'])
    if v['name'] == '{name}':
        print(f"{{nb}} {{nb + v['blocks_needed'] - 1}}")
        break
    nb += v['blocks_needed']
"""], capture_output=True, text=True, timeout=10)
    p = r.stdout.strip().split()
    return int(p[0]), int(p[1])


send('ONLY FORTH DEFINITIONS')
send('ALSO PCI-ENUM')
xs, xe = get_vocab_blocks('XHCI')
send(f'{xs} {xe} THRU', 10)
send('ONLY FORTH DEFINITIONS')
send('ALSO PCI-ENUM')
send('ALSO XHCI')
send('ALSO HARDWARE')
print('BIND:', val('XHCI-BIND')[0])
hcs1, _ = val('HCS1')
print(f'HCS1 = {hcs1:#010x}')
mp, _ = val('MAX-PORTS')
ms, _ = val('MAX-SLOTS')
hcc, _ = val('HCC1')
print(f'MAX-PORTS = {mp}  MAX-SLOTS = {ms}  HCC1 = {hcc:#010x}')

SPEED = {0: 'undef', 1: 'FS', 2: 'LS', 3: 'HS', 4: 'SS'}
for p in range(1, (mp or 0) + 1):
    off = 0x400 + (p - 1) * 0x10
    v, _ = val(f'HEX OP-BASE {off:X} + @ DECIMAL', 1.5)
    if v is None:
        print(f'port {p}: read failed')
        continue
    v &= 0xFFFFFFFF
    print(f'port {p}: PORTSC={v:#010x} CCS={v & 1} PED={(v >> 1) & 1} '
          f'PR={(v >> 4) & 1} PLS={(v >> 5) & 0xF} PP={(v >> 9) & 1} '
          f'speed={(v >> 10) & 0xF}({SPEED.get((v >> 10) & 0xF, "?")}) '
          f'CSC={(v >> 17) & 1} PRC={(v >> 21) & 1}')

# ---- part 2: PSCE question -- what does the event ring actually
# contain after UP/RUN/32 NOPs, with usb-kbd attached?
# NOP1 never inspects TRB type (counts events, not completions),
# so 2c's 32/32 proves tolerance, not absence.  Dump settles it.
print()
print('---- part 2: event-ring dump (UP/RUN/NOP-TEST 32) ----')
print('UP:', val('XHCI-UP', 3.0)[0])
print('RUN:', val('XHCI-RUN', 3.0)[0])
nt, _ = val('32 NOP-TEST', 8.0)
print('NOP-TEST 32 ->', nt)
xedq, _ = val('XEDQ @')
xenq, _ = val('XENQ @')
ering, _ = val('XERING @')
print(f'XEDQ (events consumed) = {xedq}  XENQ = {xenq}')
TYPES = {32: 'transfer-event', 33: 'command-completion',
         34: 'port-status-change', 35: 'bandwidth-request',
         36: 'doorbell', 37: 'host-controller', 38: 'device-notify',
         39: 'MFINDEX-wrap'}
counts = {}
# dump consumed entries plus 4 beyond (unconsumed stragglers)
for i in range((xedq or 0) + 4):
    st, _ = val(f'{ering} {i} 16 * + 8 + @')
    ct, _ = val(f'{ering} {i} 16 * + 12 + @')
    if ct is None:
        print(f'  trb {i}: read failed')
        continue
    ct &= 0xFFFFFFFF
    st = (st or 0) & 0xFFFFFFFF
    ttype = (ct >> 10) & 0x3F
    cyc = ct & 1
    cc = (st >> 24) & 0xFF
    name = TYPES.get(ttype, f'type-{ttype}')
    mark = 'consumed' if i < (xedq or 0) else 'beyond'
    counts[name] = counts.get(name, 0) + (1 if i < (xedq or 0) else 0)
    print(f'  trb {i:2}: ctrl={ct:#010x} type={ttype}({name}) '
          f'cycle={cyc} cc={cc} [{mark}]')
print('consumed-by-type:', counts)
print('DOWN:', val('XHCI-DOWN', 3.0)[0])
