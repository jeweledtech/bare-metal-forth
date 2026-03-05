#!/usr/bin/env python3
"""Test block editor vocabulary.

Loads EDITOR from blocks, verifies words exist and basic
operations work without crash. Tests via serial commands.

Usage:
    python3 tests/test_editor.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4477

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


ED_START, ED_END = get_vocab_blocks('EDITOR')
if ED_START is None:
    print("FAIL: Could not determine EDITOR block range")
    sys.exit(1)
print(f"EDITOR blocks: {ED_START}-{ED_END}")

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


# ---- Load EDITOR vocabulary ----
print(f"\nLoading EDITOR ({ED_START} {ED_END} THRU)...")
r = send(f'{ED_START} {ED_END} THRU', 8)
print(f"  THRU response: {r.strip()!r}")

# ---- Test 1: EDITOR vocab accessible ----
print("\nTest 1: EDITOR vocabulary accessible")
r = send('USING EDITOR', 2)
has_ok = 'ok' in r.lower()
no_error = '?' not in r
check('USING EDITOR succeeds',
      has_ok and no_error,
      f'response: {r.strip()!r}')

# ---- Test 2: ED-BLK variable exists ----
print("\nTest 2: ED-BLK variable exists")
r = send('DECIMAL ED-BLK @ .', 1)
val = extract_number(r)
print(f"  ED-BLK @ . => {r.strip()!r} (parsed: {val})")
check('ED-BLK is accessible',
      val is not None,
      f'expected a number, got {val}')

# ---- Test 3: ED-MODE variable exists ----
print("\nTest 3: ED-MODE variable exists")
r = send('DECIMAL ED-MODE @ .', 1)
val = extract_number(r)
print(f"  ED-MODE @ . => {r.strip()!r} (parsed: {val})")
check('ED-MODE is accessible',
      val is not None,
      f'expected a number, got {val}')

# ---- Test 4: Block buffer accessible ----
print("\nTest 4: Block buffer accessible via ED-BUF")
r = send('HEX 2 ED-BLK ! ED-BUF DECIMAL .', 2)
val = extract_number(r)
print(f"  ED-BUF => {r.strip()!r} (parsed: {val})")
check('ED-BUF returns non-zero address',
      val is not None and val > 0,
      f'expected >0, got {val}')

# ---- Test 5: ED-SAVE-UNDO doesn't crash ----
print("\nTest 5: ED-SAVE-UNDO works")
r = send('ED-SAVE-UNDO', 1)
r2 = send('DECIMAL 1 2 + .', 1)
val = extract_number(r2)
check('System responsive after ED-SAVE-UNDO',
      val == 3,
      f'expected 3, got {val}')

# ---- Test 6: ED-DRAW-LINE doesn't crash ----
print("\nTest 6: ED-DRAW-LINE works")
r = send('0 ED-DRAW-LINE', 1)
r2 = send('DECIMAL 1 2 + .', 1)
val = extract_number(r2)
check('System responsive after ED-DRAW-LINE',
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
