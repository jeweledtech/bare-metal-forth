#!/usr/bin/env python3
"""Full integration test — load verified vocabs, check no conflicts.

Loads EDITOR, X86-ASM, and META-COMPILER from blocks, verifies
they don't interfere with each other and core Forth still works.

Usage:
    python3 tests/test_full_integration.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4500

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


# Get block ranges for verified vocabs
ED_START, ED_END = get_vocab_blocks('EDITOR')
ASM_START, ASM_END = get_vocab_blocks('X86-ASM')
MC_START, MC_END = get_vocab_blocks('META-COMPILER')

for name, s, e in [('EDITOR', ED_START, ED_END),
                    ('X86-ASM', ASM_START, ASM_END),
                    ('META-COMPILER', MC_START, MC_END)]:
    if s is None:
        print(f"FAIL: Could not find {name} blocks")
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
    print("FAIL: Could not connect to QEMU on port", PORT)
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


def extract_number(text):
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


def alive():
    r = send('1 2 + .', 1)
    return '3' in r


# ---- Test 1: Core Forth before loading ----
print("\nTest 1: Core Forth baseline")
r = send('1 2 + .', 1)
val = extract_number(r)
check('Arithmetic works', val == 3, f'got {val}')

# ---- Test 2: Load all three vocabs ----
print("\nTest 2: Load EDITOR")
r = send(f'{ED_START} {ED_END} THRU', 8)
check('EDITOR loads', alive(), 'system crashed')

print("\nTest 3: Load X86-ASM")
r = send(f'{ASM_START} {ASM_END} THRU', 8)
check('X86-ASM loads', alive(), 'system crashed')

print("\nTest 4: Load META-COMPILER")
r = send(f'{MC_START} {MC_END} THRU', 8)
check('META-COMPILER loads', alive(), 'system crashed')

# ---- Test 5: USING each vocab ----
print("\nTest 5: Access each vocabulary")
for name in ['EDITOR', 'X86-ASM', 'META-COMPILER']:
    r = send(f'USING {name}', 2)
    has_ok = 'ok' in r.lower()
    no_error = '?' not in r
    check(f'USING {name}', has_ok and no_error,
          f'response: {r.strip()!r}')

# ---- Test 6: Use words from each vocab ----
print("\nTest 6: Words from each vocab work")

# EDITOR: ED-BLK variable
r = send('USING EDITOR', 1)
r = send('DECIMAL ED-BLK @ .', 1)
val = extract_number(r)
check('EDITOR ED-BLK accessible', val is not None,
      f'got {val}')

# X86-ASM: register constants
r = send('USING X86-ASM', 1)
r = send('DECIMAL %EAX .', 1)
val = extract_number(r)
check('X86-ASM %EAX = 0', val == 0, f'got {val}')

# META-COMPILER: META-BUILD
r = send('USING META-COMPILER', 1)
r = send('META-BUILD', 5)
check('META-BUILD completes', 'complete' in r.lower(),
      f'response: {r.strip()!r}')

# ---- Test 7: Core Forth still works ----
print("\nTest 7: Core Forth unaffected")
r = send('DECIMAL 100 200 + .', 1)
val = extract_number(r)
check('Addition works', val == 300, f'got {val}')

r = send(': INTEG-T 5 3 * ;', 1)
r = send('INTEG-T .', 1)
val = extract_number(r)
check('Colon def works', val == 15, f'got {val}')

r = send('VARIABLE IV 42 IV ! IV @ .', 1)
val = extract_number(r)
check('VARIABLE works', val == 42, f'got {val}')

# BEGIN/WHILE/REPEAT
r = send(': BWR-T 5 BEGIN DUP WHILE 1- REPEAT ;', 1)
r = send('BWR-T .', 1)
val = extract_number(r)
check('BEGIN/WHILE/REPEAT works', val == 0,
      f'got {val}')

# DO/LOOP
r = send(': DL-T 0 5 0 DO 1+ LOOP ;', 1)
r = send('DL-T .', 1)
val = extract_number(r)
check('DO/LOOP works', val == 5, f'got {val}')

# ---- Test 8: Stack is clean ----
print("\nTest 8: Stack is clean")
r = send('.S', 1)
check('Stack clean', '<>' in r, f'stack: {r.strip()!r}')

# ---- Summary ----
print()
print(f'Passed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
