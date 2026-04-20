#!/usr/bin/env python3
"""Test PCI bus enumeration vocabulary.

Loads PCI-ENUM from blocks, verifies PCI-SCAN finds devices,
PCI-LIST prints them, and PCI-FIND can locate the host bridge.

Usage:
    python3 tests/test_pci_enum.py [PORT]

QEMU always has at minimum: host bridge (8086:1237),
ISA bridge (8086:7000), and VGA (1234:1111).
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4474

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))


def get_vocab_blocks(vocab_name):
    """Get vocab start and end block from catalog."""
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
_nc = (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
nb = 1 + _nc
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


BLK_START, BLK_END = get_vocab_blocks('PCI-ENUM')
if BLK_START is None:
    print("FAIL: Could not determine PCI-ENUM block range")
    sys.exit(1)
print(f"PCI-ENUM blocks: {BLK_START}-{BLK_END}")

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)

for attempt in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print("FAIL: Could not connect to QEMU on port", PORT)
    sys.exit(1)

time.sleep(2)
try:
    while True:
        s.recv(4096)
except:
    pass


def send(cmd, wait=1.0):
    """Send a Forth command and collect the response."""
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
        except:
            break
    return resp.decode('ascii', errors='replace')


def extract_number(text):
    """Extract a decimal number from Forth output."""
    words = text.replace('\r', ' ').replace('\n', ' ').split()
    for i in range(len(words) - 1, -1, -1):
        if words[i] in ('ok', 'OK'):
            if i > 0:
                try:
                    return int(words[i - 1])
                except ValueError:
                    pass
    for word in words:
        word = word.strip()
        if word in ('ok', 'OK', ''):
            continue
        try:
            return int(word)
        except ValueError:
            continue
    return None


PASS = 0
FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        msg = f'  FAIL: {name}'
        if detail:
            msg += f' -- {detail}'
        print(msg)


# ---- Load PCI-ENUM vocabulary from blocks ----
# PCI-SCAN runs automatically on load
print(f"\nLoading PCI-ENUM ({BLK_START} {BLK_END} THRU)...")
r = send(f'{BLK_START} {BLK_END} THRU', 8)
print(f"  THRU response: {r.strip()!r}")

# ---- Test 1: PCI-ENUM vocabulary accessible ----
print("\nTest 1: PCI-ENUM vocabulary accessible")
r = send('USING PCI-ENUM', 2)
has_ok = 'ok' in r.lower()
no_error = '?' not in r
check('USING PCI-ENUM succeeds',
      has_ok and no_error,
      f'response: {r.strip()!r}')

# ---- Test 2: PCI-COUNT > 0 (devices found) ----
print("\nTest 2: PCI-COUNT > 0")
r = send('DECIMAL PCI-COUNT @ .', 1)
val = extract_number(r)
print(f"  PCI-COUNT @ . => {r.strip()!r} (parsed: {val})")
check('PCI-COUNT > 0 (devices found)',
      val is not None and val > 0,
      f'expected >0, got {val}')

# ---- Test 3: PCI-LIST prints output ----
print("\nTest 3: PCI-LIST shows devices")
r = send('HEX PCI-LIST', 3)
print(f"  PCI-LIST output: {r.strip()!r}")
check('PCI-LIST produces output',
      'devices' in r,
      f'no "devices" in output')

# ---- Test 4: Find QEMU host bridge 8086:1237 ----
print("\nTest 4: PCI-FIND host bridge")
r = send('HEX 8086 1237 PCI-FIND .', 2)
val = extract_number(r)
print(f"  8086 1237 PCI-FIND . => {r.strip()!r}")
# -1 = found (TRUE), 0 = not found
# But there's also bus/dev/func on stack if found
# The . prints the flag (-1 or 0)
# We check for -1 in the output
check('Host bridge 8086:1237 found',
      r is not None and '-1' in r,
      f'expected -1 (TRUE), got {r.strip()!r}')

# ---- Test 5: Clean up stack from PCI-FIND ----
# If found, PCI-FIND left bus dev func on stack
print("\nTest 5: PCI-FIND returned bus/dev/func")
r = send('DECIMAL . . .', 1)
print(f"  . . . => {r.strip()!r}")
check('PCI-FIND returned 3 values',
      'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')

# ---- Test 6: PCI-READ works directly ----
print("\nTest 6: PCI-READ config space")
r = send('HEX 0 0 0 0 PCI-READ .', 1)
print(f"  0 0 0 0 PCI-READ . => {r.strip()!r}")
check('PCI-READ returns non-FFFF',
      'ok' in r.lower() and 'FFFFFFFF' not in r,
      f'response: {r.strip()!r}')

# ---- Test 7: Stack is clean ----
print("\nTest 7: Stack is clean")
r = send('.S', 1)
print(f"  .S => {r.strip()!r}")
check('Stack is clean after all tests',
      '<>' in r,
      f'stack: {r.strip()!r}')

# ---- Summary ----
print()
print(f'Passed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
