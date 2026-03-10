#!/usr/bin/env python3
"""Test that MIRROR vocabulary loads from blocks
and basic operations work without crash.
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4730

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


# Find MIRROR blocks
start, end = get_vocab_blocks('MIRROR')
if start is None:
    print("FAIL: MIRROR not found in catalog")
    sys.exit(1)

print(f"MIRROR blocks: {start}-{end}")
print(f"\nLoading MIRROR ({start} {end} THRU)...")
r = send(f'{start} {end} THRU', 10)
ok = alive()
check('MIRROR vocab loads from blocks', ok,
      f'response: {r.strip()[:120]!r}')
if not ok:
    print("System crashed. Cannot continue.")
    s.close()
    sys.exit(1)

# Test 2: USING MIRROR
print("\nTest 2: USING MIRROR")
r = send('USING MIRROR', 2)
check('USING MIRROR succeeds', 'ok' in r.lower(),
      f'response: {r.strip()!r}')

# Test 3: MIRROR? on unused block returns false
# Use decimal block numbers (disk is 1024 blocks)
print("\nTest 3: MIRROR? on empty block")
r = send('DECIMAL 950 MIRROR? .', 2)
check('MIRROR? on empty block returns 0',
      '0 ok' in r or '0  ok' in r,
      f'response: {r.strip()!r}')

# Test 4: MIRROR writes and MIRROR? validates
# Block 900 decimal = well within 1024-block disk
print("\nTest 4: MIRROR write + MIRROR? check")
r = send('DECIMAL 900 MIRROR', 8)
ok1 = alive()
check('MIRROR writes without crash', ok1,
      f'response: {r.strip()[:120]!r}')
if ok1:
    r = send('DECIMAL 900 MIRROR? .', 2)
    has_flag = '-1' in r
    check('MIRROR? returns true after MIRROR',
          has_flag,
          f'response: {r.strip()!r}')

# Test 5: MIRROR-INFO runs without crash
print("\nTest 5: MIRROR-INFO")
r = send('DECIMAL 900 MIRROR-INFO', 3)
ok = alive()
check('MIRROR-INFO runs without crash', ok,
      f'response: {r.strip()[:120]!r}')
if ok:
    check('MIRROR-INFO shows HERE',
          'HERE' in r,
          f'response: {r.strip()[:120]!r}')

# Test 6: Stack is clean
print("\nTest 6: Stack clean")
r = send('.S', 1)
check('Stack clean after all tests',
      '<>' in r,
      f'stack: {r.strip()!r}')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
