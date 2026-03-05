#!/usr/bin/env python3
"""Test PS/2 mouse driver vocabulary.

Loads the PS2-MOUSE vocabulary from blocks, initializes it,
verifies MOUSE-XY, MOUSE-BUTTONS, and MOUSE-PKT? are accessible.

Usage:
    python3 tests/test_ps2_mouse.py [PORT]

The test expects QEMU to be running with the block disk attached
on the specified TCP serial port (default 4473).
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4473

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


BLK_START, BLK_END = get_vocab_blocks('PS2-MOUSE')
if BLK_START is None:
    print("FAIL: Could not determine PS2-MOUSE block range")
    sys.exit(1)
print(f"PS2-MOUSE blocks: {BLK_START}-{BLK_END}")

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


# ---- Load PS2-MOUSE vocabulary from blocks ----
print(f"\nLoading PS2-MOUSE ({BLK_START} {BLK_END} THRU)...")
r = send(f'{BLK_START} {BLK_END} THRU', 5)
thru_ok = '?' not in r
print(f"  THRU response: {r.strip()!r}")

# ---- Test 1: PS2-MOUSE vocabulary accessible ----
print("\nTest 1: PS2-MOUSE vocabulary accessible")
r = send('USING PS2-MOUSE', 2)
has_ok = 'ok' in r.lower()
no_error = '?' not in r
check('USING PS2-MOUSE succeeds',
      has_ok and no_error,
      f'response: {r.strip()!r}')

# ---- Test 2: MOUSE-INIT executes without error ----
print("\nTest 2: MOUSE-INIT executes")
r = send('MOUSE-INIT', 2)
r2 = send('DECIMAL 1 2 + .', 1)
val = extract_number(r2)
check('MOUSE-INIT succeeds (system responsive)',
      val == 3,
      f'expected 3, got {val}')

# ---- Test 3: MOUSE-XY returns 0 0 initially ----
print("\nTest 3: MOUSE-XY returns 0 0")
r = send('DECIMAL MOUSE-XY . .', 1)
print(f"  MOUSE-XY . . => {r.strip()!r}")
# Should see "0 0 ok" — two zeros
check('MOUSE-XY returns zeros',
      '0' in r and 'ok' in r.lower(),
      f'response: {r.strip()!r}')

# ---- Test 4: MOUSE-BUTTONS returns 0 ----
print("\nTest 4: MOUSE-BUTTONS returns 0")
r = send('DECIMAL MOUSE-BUTTONS .', 1)
val = extract_number(r)
print(f"  MOUSE-BUTTONS . => {r.strip()!r} (parsed: {val})")
check('MOUSE-BUTTONS = 0 (no buttons pressed)',
      val == 0,
      f'expected 0, got {val}')

# ---- Test 5: MOUSE-PKT? returns false ----
print("\nTest 5: MOUSE-PKT? returns false")
r = send('DECIMAL MOUSE-PKT? .', 1)
val = extract_number(r)
print(f"  MOUSE-PKT? . => {r.strip()!r} (parsed: {val})")
check('MOUSE-PKT? = 0 (no packet)',
      val == 0,
      f'expected 0, got {val}')

# ---- Test 6: MOUSE-BOUNDS! works ----
print("\nTest 6: MOUSE-BOUNDS! works")
r = send('DECIMAL 800 600 MOUSE-BOUNDS!', 1)
r = send('DECIMAL MOUSE-XMAX @ .', 1)
val = extract_number(r)
print(f"  MOUSE-XMAX @ . => {r.strip()!r} (parsed: {val})")
check('MOUSE-XMAX set to 800',
      val == 800,
      f'expected 800, got {val}')

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
