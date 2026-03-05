#!/usr/bin/env python3
"""Test NE2000 network driver vocabulary.

Loads PCI-ENUM then NE2000 from blocks, initializes NIC,
verifies MAC address readable and stats words work.

Usage:
    python3 tests/test_ne2000.py [PORT]

QEMU MUST be started with: -nic model=ne2k_pci
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4475

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


PCI_START, PCI_END = get_vocab_blocks('PCI-ENUM')
NE_START, NE_END = get_vocab_blocks('NE2000')
if PCI_START is None or NE_START is None:
    print("FAIL: Could not determine block ranges")
    print(f"  PCI-ENUM: {PCI_START}-{PCI_END}")
    print(f"  NE2000: {NE_START}-{NE_END}")
    sys.exit(1)
print(f"PCI-ENUM blocks: {PCI_START}-{PCI_END}")
print(f"NE2000 blocks: {NE_START}-{NE_END}")

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


# ---- Load PCI-ENUM first ----
print(f"\nLoading PCI-ENUM ({PCI_START} {PCI_END} THRU)...")
r = send(f'{PCI_START} {PCI_END} THRU', 8)
print(f"  THRU response: {r.strip()!r}")

print("\nActivating PCI-ENUM...")
r = send('USING PCI-ENUM', 2)

# ---- Load NE2000 vocabulary ----
print(f"\nLoading NE2000 ({NE_START} {NE_END} THRU)...")
r = send(f'{NE_START} {NE_END} THRU', 5)
print(f"  THRU response: {r.strip()!r}")

# ---- Test 1: NE2000 vocabulary accessible ----
print("\nTest 1: NE2000 vocabulary accessible")
r = send('USING NE2000', 2)
has_ok = 'ok' in r.lower()
no_error = '?' not in r
check('USING NE2000 succeeds',
      has_ok and no_error,
      f'response: {r.strip()!r}')

# ---- Test 2: NE2K-INIT finds NIC ----
print("\nTest 2: NE2K-INIT finds NIC")
r = send('NE2K-INIT', 3)
print(f"  NE2K-INIT response: {r.strip()!r}")
found = 'not found' not in r
has_at = 'at' in r or 'NE2000' in r
check('NE2K-INIT finds NE2000',
      found and has_at,
      f'response: {r.strip()!r}')

# ---- Test 3: NE-BASE is non-zero ----
print("\nTest 3: NE-BASE has valid address")
r = send('DECIMAL NE-BASE @ .', 1)
val = extract_number(r)
print(f"  NE-BASE @ . => {r.strip()!r} (parsed: {val})")
check('NE-BASE is non-zero',
      val is not None and val > 0,
      f'expected >0, got {val}')

# ---- Test 4: NE2K-MAC. prints values ----
print("\nTest 4: NE2K-MAC. prints MAC")
r = send('NE2K-MAC.', 1)
print(f"  NE2K-MAC. => {r.strip()!r}")
check('NE2K-MAC. produces output',
      'MAC' in r,
      f'response: {r.strip()!r}')

# ---- Test 5: NE2K-STATS works ----
print("\nTest 5: NE2K-STATS works")
r = send('NE2K-STATS', 1)
print(f"  NE2K-STATS => {r.strip()!r}")
check('NE2K-STATS produces output',
      'TX' in r and 'RX' in r,
      f'response: {r.strip()!r}')

# ---- Test 6: NE2K-RECV? returns false ----
print("\nTest 6: NE2K-RECV? returns false")
r = send('DECIMAL NE2K-RECV? .', 1)
val = extract_number(r)
print(f"  NE2K-RECV? . => {r.strip()!r} (parsed: {val})")
check('NE2K-RECV? = 0 (no packets)',
      val == 0,
      f'expected 0, got {val}')

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
