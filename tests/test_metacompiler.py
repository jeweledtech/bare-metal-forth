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

# ---- Test 4: T-C! and T-C@ ----
print("\nTest 4: T-C! writes, T-C@ reads back")
r = send('META-INIT', 2)
r = send('HEX 42 7E00 T-C! 7E00 T-C@ DECIMAL .', 2)
val = extract_number(r)
print(f"  T-C@ => {r.strip()!r} (parsed: {val})")
check('T-C@ returns 0x42 (66)',
      val == 0x42,
      f'expected 66, got {val}')

# ---- Test 5: T-! and T-@ ----
print("\nTest 5: T-! writes, T-@ reads back")
r = send('META-INIT', 2)
r = send('HEX 12345678 7E00 T-! 7E00 T-@ DECIMAL .', 2)
val = extract_number(r)
print(f"  T-@ => {r.strip()!r} (parsed: {val})")
check('T-@ returns 0x12345678',
      val == 0x12345678,
      f'expected 0x12345678, got {val}')

# ---- Test 6: T-ALLOT advances T-ADDR ----
print("\nTest 6: T-ALLOT advances T-ADDR")
r = send('META-INIT', 2)
r = send('HEX T-ADDR 100 T-ALLOT T-ADDR SWAP -', 2)
r2 = send('DECIMAL .', 1)
val = extract_number(r2)
check('T-ALLOT advances T-ADDR by n',
      val == 0x100,
      f'expected 256, got {val}')

# ---- Test 7: T-ALIGN pads to 4-byte boundary ----
print("\nTest 7: T-ALIGN pads to 4-byte boundary")
r = send('META-INIT', 2)
r = send('1 T-ALLOT T-ALIGN T-ADDR 3 AND DECIMAL .', 2)
val = extract_number(r)
check('T-ALIGN aligns to 4 bytes',
      val == 0,
      f'expected 0, got {val}')

# ---- Test 8: T-STATE starts at 0 ----
print("\nTest 8: T-STATE starts at 0")
r = send('META-INIT T-STATE @ DECIMAL .', 3)
val = extract_number(r)
check('T-STATE starts at 0',
      val == 0,
      f'expected 0, got {val}')

# ---- Test 9: T-ALLOT + T-ALIGN combined ----
print("\nTest 9: T-ALLOT then T-ALIGN")
r = send('META-INIT', 2)
r = send('HEX 5 T-ALLOT T-ALIGN T-ADDR', 2)
r2 = send('DECIMAL .', 1)
val = extract_number(r2)
# 0x7E00 + 5 = 0x7E05, aligned to 8 = 0x7E08
check('T-ALLOT 5 + T-ALIGN -> 0x7E08',
      val == 0x7E08,
      f'expected 0x7E08 (32264), got {val}')

# ---- Test 10: META-BUILD completes ----
print("\nTest 10: META-BUILD builds minimal kernel")
r = send('META-BUILD', 5)
print(f"  META-BUILD => {r.strip()!r}")
check('META-BUILD outputs complete message',
      'complete' in r.lower(),
      f'response: {r.strip()!r}')

# ---- Test 11: META-SIZE > 0 ----
print("\nTest 11: META-SIZE > 0")
r = send('DECIMAL META-SIZE .', 1)
val = extract_number(r)
print(f"  META-SIZE => {r.strip()!r} (parsed: {val})")
check('META-SIZE > 0',
      val is not None and val > 0,
      f'expected >0, got {val}')

# ---- Test 12: META-STATUS works ----
print("\nTest 12: META-STATUS works")
r = send('META-STATUS', 1)
print(f"  META-STATUS => {r.strip()!r}")
check('META-STATUS shows OK',
      'OK' in r or 'ok' in r.lower(),
      f'response: {r.strip()!r}')

# ---- Test 13: DOEXIT-ADDR set after META-BUILD ----
print("\nTest 13: DOEXIT-ADDR set after META-BUILD")
r = send('DOEXIT-ADDR @ DECIMAL .', 1)
val = extract_number(r)
check('DOEXIT-ADDR > 0 after META-BUILD',
      val is not None and val > 0,
      f'expected >0, got {val}')

# ---- Test 14: FORWARD + META-CHECK ----
print("\nTest 14: FORWARD + META-CHECK")
r = send('META-INIT', 2)
r = send('S" TEST-FWD" FORWARD', 2)
r = send('META-CHECK', 2)
print(f"  META-CHECK => {r.strip()!r}")
check('META-CHECK shows unresolved ref',
      'Unresolved' in r and 'TEST-FWD' in r,
      f'response: {r.strip()!r}')

# ---- Test 15: T-FORWARD, + RESOLVE ----
print("\nTest 15: T-FORWARD, + RESOLVE")
r = send('META-INIT', 2)
r = send('S" MYWORD" FORWARD', 2)
# compile placeholder at 7E00 (current T-ADDR)
r = send('S" MYWORD" T-FORWARD,', 2)
# placeholder at 7E00 should be 0 (no prior chain)
r = send('HEX 7E00 T-@ DECIMAL .', 1)
val = extract_number(r)
check('T-FORWARD, writes chain link (0)',
      val == 0,
      f'expected 0, got {val}')
# resolve MYWORD to address 0xBEEF
r = send('HEX BEEF S" MYWORD" RESOLVE', 2)
# now 7E00 should contain 0xBEEF
r = send('HEX 7E00 T-@ DECIMAL .', 1)
val = extract_number(r)
check('RESOLVE patches to 0xBEEF',
      val == 0xBEEF,
      f'expected 0xBEEF (48879), got {val}')

# ---- Test 16: T-VARIABLE creates header ----
print("\nTest 16: T-VARIABLE creates header")
r = send('META-INIT', 2)
r = send('HEX 1234 DOCREATE-ADDR !', 1)
r = send('S" MYVAR" T-VARIABLE', 2)
# link at 7E00 = 0 (first word)
r = send('7E00 T-@ DECIMAL .', 1)
val = extract_number(r)
check('T-VARIABLE link = 0 (first word)',
      val == 0,
      f'expected 0, got {val}')

# ---- Test 17: T-CONSTANT creates header + value ----
print("\nTest 17: T-CONSTANT creates header + value")
r = send('META-INIT', 2)
r = send('HEX 5678 DOCON-ADDR !', 1)
r = send('HEX 2A S" MYCONST" T-CONSTANT', 2)
# Check flags+len byte at 7E04: len=7 (MYCONST)
r = send('HEX 7E04 T-C@ DECIMAL .', 1)
val = extract_number(r)
check('T-CONSTANT flags+len = 7',
      val == 7,
      f'expected 7, got {val}')

# ---- Test 18: T-IMMEDIATE sets flag ----
print("\nTest 18: T-IMMEDIATE sets flag")
r = send('META-INIT', 2)
r = send('HEX 1234 DOCREATE-ADDR !', 1)
r = send('S" IMM" T-VARIABLE T-IMMEDIATE', 2)
# flags+len at 7E04: 0x80 | 3 = 0x83 = 131
r = send('HEX 7E04 T-C@ DECIMAL .', 1)
val = extract_number(r)
check('T-IMMEDIATE sets bit 7',
      val == 0x83,
      f'expected 131 (0x83), got {val}')

# ---- Test 19: T-IF/T-THEN offset ----
print("\nTest 19: T-IF/T-THEN branch offset")
r = send('META-INIT', 2)
r = send('HEX 9999 DO0BRANCH-ADDR !', 1)
r = send('HEX AAAA DOEXIT-ADDR !', 1)
# Build: T-IF <4 bytes filler> T-THEN
# 0BRANCH at 7E00, offset at 7E04, filler at 7E08
r = send('T-IF 4 T-ALLOT T-THEN', 2)
# offset at 7E04:
# T-ADDR after T-IF = 7E08, after allot = 7E0C
# offset = 7E0C - 7E04 = 8
r = send('HEX 7E04 T-@ DECIMAL .', 1)
val = extract_number(r)
check('T-IF/T-THEN offset = 8',
      val == 8,
      f'expected 8, got {val}')

# ---- Test 20: T-BEGIN/T-UNTIL backward offset ----
print("\nTest 20: T-BEGIN/T-UNTIL backward offset")
r = send('META-INIT', 2)
r = send('HEX 9999 DO0BRANCH-ADDR !', 1)
# BEGIN at 7E00, emit filler, UNTIL at 7E04+
r = send('T-BEGIN 4 T-ALLOT T-UNTIL', 2)
# 0BRANCH XT at 7E04, offset at 7E08
# offset = 7E00 - 7E08 = -8 = FFFFFFF8
r = send('HEX 7E08 T-@ DECIMAL .', 1)
val = extract_number(r)
check('T-BEGIN/T-UNTIL offset = -8',
      val == -8,
      f'expected -8, got {val}')

# ---- Test 21: D# parses decimal in HEX mode ----
print("\nTest 21: D# parses decimal in HEX mode")
r = send('HEX D# 42 DECIMAL .', 2)
val = extract_number(r)
print(f"  D# => {r.strip()!r} (parsed: {val})")
check('D# 42 in HEX mode = 42 decimal',
      val == 42,
      f'expected 42, got {val}')

# ---- Test 22: H# parses hex in DECIMAL mode ----
print("\nTest 22: H# parses hex in DECIMAL mode")
r = send('DECIMAL H# FF .', 2)
val = extract_number(r)
print(f"  H# => {r.strip()!r} (parsed: {val})")
check('H# FF in DECIMAL mode = 255',
      val == 255,
      f'expected 255, got {val}')

# ---- Test 23: META-SAVE stub executes ----
print("\nTest 23: META-SAVE stub executes")
r = send('META-SAVE', 2)
check('META-SAVE executes without crash',
      'stub' in r.lower(),
      f'response: {r.strip()!r}')

# ---- Test 24: Full regression META-BUILD ----
print("\nTest 24: Full regression after all words")
r = send('META-BUILD', 5)
check('META-BUILD still works after all additions',
      'complete' in r.lower(),
      f'response: {r.strip()!r}')

# ---- Test 25: Stack is clean ----
print("\nTest 25: Stack is clean")
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
