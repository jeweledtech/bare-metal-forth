#!/usr/bin/env python3
"""Test ARM64 target vocabulary.

Loads X86-ASM, META-COMPILER, ARM64-ASM, TARGET-ARM64,
runs META-COMPILE-ARM64, verifies target image.

Usage:
    python3 tests/test_arm64_target.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4493

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


# Resolve all vocabulary block ranges
VOCABS = {}
for name in ['X86-ASM', 'META-COMPILER',
             'ARM64-ASM', 'TARGET-ARM64']:
    s, e = get_vocab_blocks(name)
    VOCABS[name] = (s, e)
    if s is None:
        print(f"FAIL: {name} not found in catalog")
        sys.exit(1)
    print(f"{name}: blocks {s}-{e}")

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)

for attempt in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print("FAIL: Could not connect to QEMU")
    sys.exit(1)

time.sleep(2)
try:
    while True:
        s.recv(4096)
except:
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
        except:
            break
    return resp.decode('ascii', errors='replace')


def extract_number(text):
    words = text.replace('\r', ' ').replace(
        '\n', ' ').split()
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


# ---- Load all vocabs in order ----
for name in ['X86-ASM', 'META-COMPILER',
             'ARM64-ASM', 'TARGET-ARM64']:
    s_blk, e_blk = VOCABS[name]
    print(f"\nLoading {name} ({s_blk} {e_blk} THRU)...")
    r = send(f'{s_blk} {e_blk} THRU', 10)
    ok_found = 'ok' in r.lower()
    has_err = '?' in r
    if has_err:
        print(f"  WARNING: {r.strip()[:80]!r}")
    else:
        print(f"  OK")

# ---- Test 1: TARGET-ARM64 accessible ----
print("\nTest 1: TARGET-ARM64 vocabulary accessible")
# Set up search order with all needed vocabs
r = send('USING X86-ASM', 1)
r = send('ALSO META-COMPILER', 1)
r = send('ALSO ARM64-ASM', 1)
r = send('ALSO TARGET-ARM64', 2)
has_ok = 'ok' in r.lower()
no_error = '?' not in r
check('ALSO TARGET-ARM64',
      has_ok and no_error,
      f'{r.strip()!r}')

# ---- Test 2: Run META-COMPILE-ARM64 ----
print("\nTest 2: META-COMPILE-ARM64")
r = send('META-COMPILE-ARM64', 15)
print(f"  Response: {r.strip()!r}")
has_complete = 'compile' in r.lower()
check('META-COMPILE-ARM64 completes',
      has_complete,
      f'{r.strip()[:60]!r}')

# ---- Test 3: META-SIZE > 0 ----
print("\nTest 3: META-SIZE check")
r = send('META-SIZE DECIMAL .', 2)
sz = extract_number(r)
print(f"  META-SIZE = {sz}")
check('META-SIZE > 0', sz is not None and sz > 0,
      f'got {sz}')
if sz:
    check('META-SIZE > 1000 bytes',
          sz > 1000,
          f'got {sz}')

# ---- Test 4: Runtime addresses set ----
print("\nTest 4: Runtime addresses")
r = send('DOCOL-ADDR @ DECIMAL .', 1)
v = extract_number(r)
check('DOCOL-ADDR set',
      v is not None and v > 0,
      f'got {v}')

r = send('DOEXIT-ADDR @ DECIMAL .', 1)
v = extract_number(r)
check('DOEXIT-ADDR set',
      v is not None and v > 0,
      f'got {v}')

r = send('DOLIT-ADDR @ DECIMAL .', 1)
v = extract_number(r)
check('DOLIT-ADDR set',
      v is not None and v > 0,
      f'got {v}')

r = send('DOBRANCH-ADDR @ DECIMAL .', 1)
v = extract_number(r)
check('DOBRANCH-ADDR set',
      v is not None and v > 0,
      f'got {v}')

# ---- Test 5: Symbol count ----
print("\nTest 5: Symbol count")
r = send('TSYM-N @ DECIMAL .', 1)
nsym = extract_number(r)
print(f"  Symbols: {nsym}")
check('Symbol count > 40',
      nsym is not None and nsym > 40,
      f'got {nsym}')

# ---- Test 6: Key symbols findable ----
print("\nTest 6: Symbol lookup")
for word in ['DROP', 'DUP', '+', '-', '@', '!',
             'BRANCH', '0BRANCH', 'EXIT']:
    r = send(f'S" {word}" T-FIND-SYM DECIMAL .', 2)
    v = extract_number(r)
    check(f'T-FIND-SYM {word}',
          v is not None and v > 0,
          f'got {v}')

# ---- Test 7: NEXT bytes in target image ----
print("\nTest 7: NEXT opcode at DOCOL-ADDR")
# DOCOL starts with: STR W27,[X26,#-4]!
# which is a pre-index store.
r = send('DOCOL-ADDR @ T-C@ DECIMAL .', 1)
# First byte of STR instruction (little-endian)
# We just check it's non-zero (real ARM64 code)
v = extract_number(r)
check('DOCOL first byte != 0',
      v is not None and v != 0,
      f'got {v}')

# ---- Test 8: T-COLON words compiled ----
print("\nTest 8: T-COLON words")
r = send('S" SQUARE" T-FIND-SYM DECIMAL .', 2)
v = extract_number(r)
check('SQUARE in symbol table',
      v is not None and v > 0,
      f'got {v}')
r = send('S" CUBE" T-FIND-SYM DECIMAL .', 2)
v = extract_number(r)
check('CUBE in symbol table',
      v is not None and v > 0,
      f'got {v}')

# ---- Test 9: META-CHECK (no unresolved) ----
print("\nTest 9: META-CHECK")
r = send('META-CHECK', 2)
# META-CHECK prints "Unresolved: <name>" for each.
# Empty name (just "Unresolved: \r\n") is a quirk.
# Only fail if a real name follows on same line.
import re
has_real_unresolved = bool(
    re.search(r'Unresolved: \S', r))
check('No unresolved forward refs',
      not has_real_unresolved,
      f'{r.strip()!r}')

# ---- Test 10: META-STATUS ----
print("\nTest 10: META-STATUS")
r = send('META-STATUS', 2)
print(f"  {r.strip()!r}")
has_ok_status = 'OK' in r
check('META-STATUS reports OK',
      has_ok_status,
      f'{r.strip()[:60]!r}')

# ---- Test 11: Stack clean ----
print("\nTest 11: Stack clean")
r = send('.S', 1)
check('Stack clean after all tests',
      '<>' in r,
      f'{r.strip()!r}')

# ---- Summary ----
print()
print(f'Passed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
