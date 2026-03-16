#!/usr/bin/env python3
"""Test that driver vocabs load from blocks without crash.
Tests HARDWARE, SERIAL-16550, RTL8139, PS2-KEYBOARD, PS2-MOUSE.
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4513

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))


def get_vocab_blocks(vocab_name):
    try:
        result = subprocess.run(
            [sys.executable, '-c', f"""
import sys, os
sys.path.insert(0, os.path.join('{PROJECT_DIR}', 'tools'))
from importlib.machinery import SourceFileLoader
wc = SourceFileLoader('wc', os.path.join(
    '{PROJECT_DIR}', 'tools', 'write-catalog.py'
)).load_module()
vocabs = wc.scan_vocabs(os.path.join(
    '{PROJECT_DIR}', 'forth', 'dict'))
nb = 2
for v in vocabs:
    if v['name'] == '{vocab_name}':
        print(f"{{nb}} {{nb + v['blocks_needed'] - 1}}")
        break
    nb += v['blocks_needed']
"""],
            capture_output=True, text=True, timeout=10
        )
        if result.stdout.strip():
            parts = result.stdout.strip().split()
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
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
    print("FAIL: Could not connect")
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


def alive():
    r = send('1 2 + .', 1)
    return '3' in r


PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}' +
              (f' -- {detail}' if detail else ''))


# Vocabs to test (order matters: dependencies first)
vocabs_to_test = [
    'HARDWARE',
    'SERIAL-16550',
    'PS2-KEYBOARD',
    'PS2-MOUSE',
    'RTL8139',
]

# RTL8139 needs PCI-ENUM and HARDWARE loaded first
# All others use kernel INB/OUTB directly (no deps)

# Load PCI-ENUM first (needed by RTL8139)
pci_start, pci_end = get_vocab_blocks('PCI-ENUM')
if pci_start:
    print(f"\nPre-loading PCI-ENUM ({pci_start}-{pci_end} THRU)...")
    r = send(f'{pci_start} {pci_end} THRU', 10)
    ok = alive()
    check('PCI-ENUM loads', ok,
          f'response: {r.strip()[:80]!r}')
    if not ok:
        print("FAIL: Cannot continue without PCI-ENUM")
        sys.exit(1)

for name in vocabs_to_test:
    start, end = get_vocab_blocks(name)
    if start is None:
        print(f"  SKIP: {name} (not in catalog)")
        continue
    print(f"\nLoading {name} ({start}-{end} THRU)...")
    r = send(f'{start} {end} THRU', 10)
    ok = alive()
    check(f'{name} loads without crash', ok,
          f'response: {r.strip()[:80]!r}')
    if not ok:
        print(f"  System crashed! Stopping.")
        break

# PS2-MOUSE specific tests
print("\nPS2-MOUSE word tests:")
r = send('USING PS2-MOUSE', 2)
ok = alive()
check('USING PS2-MOUSE succeeds', ok,
      f'response: {r.strip()[:80]!r}')

if ok:
    # Verify constants have correct hex values
    r = send('HEX DEFAULT-XMAX .', 1)
    check('DEFAULT-XMAX = 280h (640d)', '280' in r,
          f'got: {r.strip()!r}')
    r = send('DEFAULT-YMAX .', 1)
    check('DEFAULT-YMAX = 1E0h (480d)', '1E0' in r,
          f'got: {r.strip()!r}')
    r = send('MOUSE-IRQ .', 1)
    check('MOUSE-IRQ = C (12d)', 'C' in r,
          f'got: {r.strip()!r}')
    # Verify kernel var access works
    r = send('MOUSE-X-VAR @ .', 1)
    check('MOUSE-X-VAR readable', '0' in r,
          f'got: {r.strip()!r}')
    r = send('MOUSE-XY . .', 1)
    check('MOUSE-XY returns two values', '0' in r,
          f'got: {r.strip()!r}')
    r = send('DECIMAL', 1)

# Final check
print("\nFinal check:")
ok = alive()
check('System alive after all loads', ok)
if ok:
    r = send('.S', 1)
    check('Stack clean', '<>' in r,
          f'stack: {r.strip()!r}')
    # Check WORDS shows our vocabs
    r = send('ORDER', 2)
    print(f'  ORDER: {r.strip()!r}')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
