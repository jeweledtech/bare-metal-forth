#!/usr/bin/env python3
"""Test VGA graphics driver vocabulary.

Loads PCI-ENUM then VGA-GRAPHICS from blocks, verifies
VBE version readable, LFB address obtained, mode set/text
mode switch works without crash.

Usage:
    python3 tests/test_vga_graphics.py [PORT]

Headless test — verifies words exist and VBE registers
respond. No actual pixel verification (no display).
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4476

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


PCI_START, PCI_END = get_vocab_blocks('PCI-ENUM')
VGA_START, VGA_END = get_vocab_blocks('VGA-GRAPHICS')
if PCI_START is None or VGA_START is None:
    print("FAIL: Could not determine block ranges")
    print(f"  PCI-ENUM: {PCI_START}-{PCI_END}")
    print(f"  VGA-GRAPHICS: {VGA_START}-{VGA_END}")
    sys.exit(1)
print(f"PCI-ENUM blocks: {PCI_START}-{PCI_END}")
print(f"VGA-GRAPHICS blocks: {VGA_START}-{VGA_END}")

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
r = send('USING PCI-ENUM', 2)

# ---- Load VGA-GRAPHICS vocabulary ----
print(f"\nLoading VGA-GRAPHICS "
      f"({VGA_START} {VGA_END} THRU)...")
r = send(f'{VGA_START} {VGA_END} THRU', 5)
print(f"  THRU response: {r.strip()!r}")

# ---- Test 1: VGA-GRAPHICS vocab accessible ----
print("\nTest 1: VGA-GRAPHICS vocabulary accessible")
r = send('USING VGA-GRAPHICS', 2)
has_ok = 'ok' in r.lower()
no_error = '?' not in r
check('USING VGA-GRAPHICS succeeds',
      has_ok and no_error,
      f'response: {r.strip()!r}')

# ---- Test 2: VBE version readable ----
print("\nTest 2: VBE version readable")
r = send('DECIMAL VBE-VER .', 1)
val = extract_number(r)
print(f"  VBE-VER . => {r.strip()!r} (parsed: {val})")
# Bochs VBE returns 0xB0C0..0xB0C5
check('VBE-VER returns a number',
      val is not None and val > 0,
      f'expected >0, got {val}')

# ---- Test 3: VGA-FIND-LFB returns address ----
print("\nTest 3: VGA-FIND-LFB returns address")
r = send('DECIMAL VGA-FIND-LFB .', 1)
val = extract_number(r)
print(f"  VGA-FIND-LFB . => {r.strip()!r} (parsed: {val})")
check('VGA-FIND-LFB returns non-zero',
      val is not None and val != 0,
      f'expected non-zero, got {val}')

# ---- Test 4: VGA-MODE! doesn't crash ----
print("\nTest 4: VGA-MODE! sets mode")
r = send('DECIMAL 640 480 32 VGA-MODE!', 3)
r2 = send('DECIMAL 1 2 + .', 1)
val = extract_number(r2)
check('VGA-MODE! system responsive after',
      val == 3,
      f'expected 3, got {val}')

# ---- Test 5: VGA-LFB has valid address ----
print("\nTest 5: VGA-LFB valid")
r = send('DECIMAL VGA-LFB @ .', 1)
val = extract_number(r)
print(f"  VGA-LFB @ . => {r.strip()!r} (parsed: {val})")
check('VGA-LFB is non-zero',
      val is not None and val != 0,
      f'expected non-zero, got {val}')

# ---- Test 6: VGA-TEXT returns to text mode ----
print("\nTest 6: VGA-TEXT returns to text mode")
r = send('VGA-TEXT', 1)
r2 = send('DECIMAL 1 2 + .', 1)
val = extract_number(r2)
check('VGA-TEXT system responsive',
      val == 3,
      f'expected 3, got {val}')

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
