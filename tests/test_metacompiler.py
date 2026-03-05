#!/usr/bin/env python3
"""Test metacompiler vocabulary.

Loads X86-ASM then META-COMPILER from blocks,
runs META-BUILD, verifies target image built.

Usage:
    python3 tests/test_metacompiler.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4479

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


ASM_START, ASM_END = get_vocab_blocks('X86-ASM')
MC_START, MC_END = get_vocab_blocks('META-COMPILER')
if ASM_START is None or MC_START is None:
    print("FAIL: Could not determine block ranges")
    print(f"  X86-ASM: {ASM_START}-{ASM_END}")
    print(f"  META-COMPILER: {MC_START}-{MC_END}")
    sys.exit(1)
print(f"X86-ASM blocks: {ASM_START}-{ASM_END}")
print(f"META-COMPILER blocks: {MC_START}-{MC_END}")

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


# ---- Load X86-ASM first ----
print(f"\nLoading X86-ASM ({ASM_START} {ASM_END} THRU)...")
r = send(f'{ASM_START} {ASM_END} THRU', 8)
print(f"  THRU response: {r.strip()!r}")
r = send('USING X86-ASM', 2)

# ---- Load META-COMPILER ----
print(f"\nLoading META-COMPILER "
      f"({MC_START} {MC_END} THRU)...")
r = send(f'{MC_START} {MC_END} THRU', 8)
print(f"  THRU response: {r.strip()!r}")

# ---- Test 1: META-COMPILER vocab accessible ----
print("\nTest 1: META-COMPILER vocabulary accessible")
r = send('USING META-COMPILER', 2)
has_ok = 'ok' in r.lower()
no_error = '?' not in r
check('USING META-COMPILER succeeds',
      has_ok and no_error,
      f'response: {r.strip()!r}')

# ---- Test 2: META-INIT works ----
print("\nTest 2: META-INIT initializes target")
r = send('META-INIT', 2)
r2 = send('DECIMAL 1 2 + .', 1)
val = extract_number(r2)
check('META-INIT completes without crash',
      val == 3,
      f'expected 3, got {val}')

# ---- Test 3: T-ADDR returns org ----
print("\nTest 3: T-ADDR returns origin")
r = send('HEX T-ADDR DECIMAL .', 1)
val = extract_number(r)
print(f"  T-ADDR => {r.strip()!r} (parsed: {val})")
check('T-ADDR = 0x7E00 (32256)',
      val == 0x7E00,
      f'expected 32256, got {val}')

# ---- Test 4: META-BUILD completes ----
print("\nTest 4: META-BUILD builds minimal kernel")
r = send('META-BUILD', 5)
print(f"  META-BUILD => {r.strip()!r}")
check('META-BUILD outputs complete message',
      'complete' in r.lower(),
      f'response: {r.strip()!r}')

# ---- Test 5: META-SIZE > 0 ----
print("\nTest 5: META-SIZE > 0")
r = send('DECIMAL META-SIZE .', 1)
val = extract_number(r)
print(f"  META-SIZE => {r.strip()!r} (parsed: {val})")
check('META-SIZE > 0',
      val is not None and val > 0,
      f'expected >0, got {val}')

# ---- Test 6: META-STATUS works ----
print("\nTest 6: META-STATUS works")
r = send('META-STATUS', 1)
print(f"  META-STATUS => {r.strip()!r}")
check('META-STATUS shows OK',
      'OK' in r or 'ok' in r.lower(),
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
