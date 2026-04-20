#!/usr/bin/env python3
"""Test x86 assembler vocabulary.

Loads X86-ASM from blocks, assembles instructions into a
buffer, verifies bytes match expected machine code.

Usage:
    python3 tests/test_x86_asm.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4478

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


ASM_START, ASM_END = get_vocab_blocks('X86-ASM')
if ASM_START is None:
    print("FAIL: Could not determine X86-ASM block range")
    sys.exit(1)
print(f"X86-ASM blocks: {ASM_START}-{ASM_END}")

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


# ---- Load X86-ASM vocabulary ----
print(f"\nLoading X86-ASM ({ASM_START} {ASM_END} THRU)...")
r = send(f'{ASM_START} {ASM_END} THRU', 8)
print(f"  THRU response: {r.strip()!r}")

# ---- Test 1: X86-ASM vocab accessible ----
print("\nTest 1: X86-ASM vocabulary accessible")
r = send('USING X86-ASM', 2)
has_ok = 'ok' in r.lower()
no_error = '?' not in r
check('USING X86-ASM succeeds',
      has_ok and no_error,
      f'response: {r.strip()!r}')

# ---- Test 2: Set up target buffer ----
print("\nTest 2: Target buffer setup")
# Use HERE as a scratch buffer for assembling
r = send('HEX HERE @ T-HERE !', 1)
r = send('T-HERE @ DECIMAL .', 1)
val = extract_number(r)
print(f"  T-HERE @ . => {r.strip()!r} (parsed: {val})")
check('T-HERE points to valid address',
      val is not None and val > 0,
      f'expected >0, got {val}')

# ---- Test 3: NOP assembles to 0x90 ----
print("\nTest 3: NOP, assembles 0x90")
r = send('HEX HERE @ T-HERE !', 1)
r = send('HEX NOP, T-HERE @ 1- C@ DECIMAL .', 1)
val = extract_number(r)
print(f"  NOP byte => {r.strip()!r} (parsed: {val})")
check('NOP assembles to 0x90 (144)',
      val == 0x90,
      f'expected 144, got {val}')

# ---- Test 4: PUSH EAX = 0x50 ----
print("\nTest 4: PUSH %EAX assembles 0x50")
r = send('HEX HERE @ T-HERE !', 1)
r = send('HEX %EAX PUSH, T-HERE @ 1- C@ DECIMAL .', 1)
val = extract_number(r)
print(f"  PUSH EAX byte => {r.strip()!r} (parsed: {val})")
check('PUSH EAX assembles to 0x50 (80)',
      val == 0x50,
      f'expected 80, got {val}')

# ---- Test 5: RET = 0xC3 ----
print("\nTest 5: RET, assembles 0xC3")
r = send('HEX HERE @ T-HERE !', 1)
r = send('HEX RET, T-HERE @ 1- C@ DECIMAL .', 1)
val = extract_number(r)
print(f"  RET byte => {r.strip()!r} (parsed: {val})")
check('RET assembles to 0xC3 (195)',
      val == 0xC3,
      f'expected 195, got {val}')

# ---- Test 6: Register constants ----
print("\nTest 6: Register constants correct")
r = send('DECIMAL %EAX .', 1)
val = extract_number(r)
check('%EAX = 0', val == 0, f'got {val}')
r = send('DECIMAL %ESI .', 1)
val = extract_number(r)
check('%ESI = 6', val == 6, f'got {val}')

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
