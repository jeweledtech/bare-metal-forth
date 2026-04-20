#!/usr/bin/env python3
"""Test PIT timer driver vocabulary.

Loads the PIT-TIMER vocabulary from blocks, initializes the PIT
at 100 Hz, verifies TICK-COUNT increments, and tests MS-WAIT.

Usage:
    python3 tests/test_pit_timer.py [PORT]

The test expects QEMU to be running with the block disk attached
on the specified TCP serial port (default 4471).

PIT-TIMER blocks are determined by write-catalog.py output.
Currently PIT-TIMER is at blocks 80-84.
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4471

# Determine PIT-TIMER block range from write-catalog.py
PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))

def get_pit_blocks():
    """Get PIT-TIMER start and end block from catalog."""
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
    if v['name'] == 'PIT-TIMER':
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
    # Fallback to known layout
    return 80, 84


PIT_START, PIT_END = get_pit_blocks()
print(f"PIT-TIMER blocks: {PIT_START}-{PIT_END}")

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)

# Retry connection in case QEMU isn't ready
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
    """Extract a decimal number from Forth output.

    The response typically looks like:
        'TICK-COUNT @ .\\r\\n42 ok'
    We want the number just before 'ok'.
    """
    # Split and look for numbers
    words = text.replace('\r', ' ').replace('\n', ' ').split()
    # Walk backwards from 'ok' to find the number
    for i in range(len(words) - 1, -1, -1):
        if words[i] == 'ok' or words[i] == 'OK':
            # Check previous word
            if i > 0:
                try:
                    return int(words[i - 1])
                except ValueError:
                    pass
    # Fallback: try each word
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


# ---- Load PIT-TIMER vocabulary from blocks ----
print(f"\nLoading PIT-TIMER ({PIT_START} {PIT_END} THRU)...")
r = send(f'{PIT_START} {PIT_END} THRU', 5)
thru_ok = '?' not in r
print(f"  THRU response: {r.strip()!r}")

# ---- Test 1: PIT-TIMER vocabulary loaded ----
print("\nTest 1: PIT-TIMER vocabulary accessible")
r = send('USING PIT-TIMER', 2)
has_ok = 'ok' in r.lower()
no_error = '?' not in r
check('USING PIT-TIMER succeeds',
      has_ok and no_error,
      f'response: {r.strip()!r}')

# ---- Test 2: PIT-INIT programs the timer ----
print("\nTest 2: Initialize PIT at 100 Hz")
# Set base to DECIMAL first, then pass 100
r = send('DECIMAL 100 PIT-INIT', 2)
no_error = '?' not in r
check('PIT-INIT executes without error',
      no_error,
      f'response: {r.strip()!r}')

# ---- Test 3: TICKS/SEC stores the rate ----
print("\nTest 3: TICKS/SEC stores 100")
r = send('DECIMAL TICKS/SEC @ .', 1)
val = extract_number(r)
print(f"  TICKS/SEC @ . => {r.strip()!r} (parsed: {val})")
check('TICKS/SEC = 100', val == 100,
      f'expected 100, got {val}')

# ---- Test 4: TICK-COUNT readable and numeric ----
print("\nTest 4: TICK-COUNT readable")
r = send('DECIMAL TICK-COUNT @ .', 1)
tick1 = extract_number(r)
print(f"  TICK-COUNT @ . => {r.strip()!r} (parsed: {tick1})")
check('TICK-COUNT returns a number',
      tick1 is not None and tick1 >= 0,
      f'could not parse number from {r.strip()!r}')

# ---- Test 5: TICK-COUNT increments over time ----
print("\nTest 5: TICK-COUNT increments")
# Wait 600ms for ~60 ticks at 100 Hz
time.sleep(0.6)
r = send('DECIMAL TICK-COUNT @ .', 1)
tick2 = extract_number(r)
print(f"  After 600ms: TICK-COUNT @ . => "
      f"{r.strip()!r} (parsed: {tick2})")
if tick1 is not None and tick2 is not None:
    check('TICK-COUNT increased',
          tick2 > tick1,
          f'tick1={tick1}, tick2={tick2}')
else:
    check('TICK-COUNT increased', False,
          f'could not parse: tick1={tick1}, '
          f'tick2={tick2}')

# ---- Test 6: PIT-READ returns a counter value ----
print("\nTest 6: PIT-READ returns counter")
r = send('DECIMAL PIT-READ .', 1)
pit_val = extract_number(r)
print(f"  PIT-READ . => {r.strip()!r} (parsed: {pit_val})")
check('PIT-READ returns a number',
      pit_val is not None and pit_val >= 0,
      f'could not parse from {r.strip()!r}')

# ---- Test 7: MS-WAIT returns without hanging ----
print("\nTest 7: MS-WAIT completes")
r = send('DECIMAL 50 MS-WAIT', 3)
# After MS-WAIT, verify system is responsive
r = send('DECIMAL 1 2 + .', 1)
val = extract_number(r)
print(f"  After MS-WAIT, 1 2 + . => {r.strip()!r}")
check('MS-WAIT returns (system responsive)',
      val == 3,
      f'expected 3, got {val}')

# ---- Test 8: Stack is clean after operations ----
print("\nTest 8: Stack is clean")
r = send('.S', 1)
print(f"  .S => {r.strip()!r}")
# .S shows '<>' for empty stack in this Forth
check('Stack is clean after all tests',
      '<>' in r,
      f'stack: {r.strip()!r}')

# ---- Summary ----
print()
print(f'Passed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
