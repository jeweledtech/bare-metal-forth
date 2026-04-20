#!/usr/bin/env python3
"""Test that DISASM vocabulary loads from blocks
and all disassembly operations work correctly.
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4740

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


# Find DISASM blocks
start, end = get_vocab_blocks('DISASM')
if start is None:
    print("FAIL: DISASM not found in catalog")
    sys.exit(1)

print(f"DISASM blocks: {start}-{end}")
print(f"\nLoading DISASM ({start} {end} THRU)...")
r = send(f'{start} {end} THRU', 12)
ok = alive()
check('DISASM vocab loads from blocks', ok,
      f'response: {r.strip()[:200]!r}')
if not ok:
    print("System crashed. Cannot continue.")
    s.close()
    sys.exit(1)

# Test 2: USING DISASM
print("\nTest 2: USING DISASM")
r = send('USING DISASM', 2)
ok = alive()
check('USING DISASM succeeds', ok,
      f'response: {r.strip()!r}')
if not ok:
    print("System crashed. Cannot continue.")
    s.close()
    sys.exit(1)

# Test 3: DIS on a colon definition
print("\nTest 3: DIS colon definition")
r = send(': SQUARE DUP * ;', 2)
r = send('DIS SQUARE', 2)
has_dup = 'DUP' in r
has_star = '*' in r
check('DIS SQUARE shows DUP and *',
      has_dup and has_star,
      f'response: {r.strip()[:200]!r}')

# Test 4: DIS on a constant
print("\nTest 4: DIS constant")
r = send('DECIMAL 42 CONSTANT TC HEX', 2)
r = send('DIS TC', 2)
check('DIS TC shows 42',
      '42' in r,
      f'response: {r.strip()[:200]!r}')

# Test 5: DIS on a variable
print("\nTest 5: DIS variable")
r = send('VARIABLE TV', 2)
r = send('DIS TV', 2)
has_var = 'ariable' in r or 'body' in r or 'Var' in r
check('DIS TV shows variable info',
      has_var,
      f'response: {r.strip()[:200]!r}')

# Test 6: DIS on a CODE word (DROP)
print("\nTest 6: DIS CODE word")
r = send('DIS DROP', 3)
has_code = 'Code' in r or 'code' in r
has_next = 'NEXT' in r
check('DIS DROP shows Code and NEXT',
      has_code and has_next,
      f'response: {r.strip()[:200]!r}')

# Test 7: DIS on a user-created vocabulary
print("\nTest 7: DIS vocabulary")
r = send('VOCABULARY TVOC', 2)
r = send('DIS TVOC', 2)
check('DIS TVOC shows Vocabulary',
      'ocabulary' in r,
      f'response: {r.strip()[:200]!r}')

# Test 8: >NAME and ID.
print("\nTest 8: >NAME ID.")
r = send("' DUP >NAME ID.", 2)
check('>NAME ID. prints DUP',
      'DUP' in r,
      f'response: {r.strip()[:200]!r}')

# Test 9: COLON? predicate
print("\nTest 9: COLON? predicate")
r = send("' SQUARE COLON? .", 2)
check("COLON? on SQUARE returns -1",
      '-1' in r,
      f'response: {r.strip()[:200]!r}')

# Test 10: CONST? predicate
print("\nTest 10: CONST? predicate")
r = send("' TC CONST? .", 2)
check("CONST? on TC returns -1",
      '-1' in r,
      f'response: {r.strip()[:200]!r}')

# Test 11: DECOMP with branches
print("\nTest 11: DECOMP with branches")
r = send(': BT IF 1 ELSE 2 THEN ;', 2)
r = send("' BT DECOMP", 3)
has_0br = '0BRANCH' in r
has_br = 'BRANCH' in r
check('DECOMP BT shows 0BRANCH and BRANCH',
      has_0br and has_br,
      f'response: {r.strip()[:200]!r}')

# Test 12: DIS-X86 on DROP (NEXT pattern)
print("\nTest 12: DIS-X86 on DROP")
r = send("' DROP DIS-X86", 3)
check("DIS-X86 on DROP shows NEXT",
      'NEXT' in r,
      f'response: {r.strip()[:200]!r}')

# Test 13: DIS with string literal
print("\nTest 13: DIS with string")
r = send(': ST ." hello" ;', 2)
r = send('DIS ST', 3)
has_sq = 'S"' in r or '(S")' in r or 'S\\"' in r
has_hello = 'hello' in r
check('DIS ST shows S" and hello',
      has_sq and has_hello,
      f'response: {r.strip()[:200]!r}')

# Test 14: Stack clean after all operations
print("\nTest 14: Stack clean")
r = send('.S', 1)
check('Stack clean after all tests',
      '<>' in r,
      f'stack: {r.strip()!r}')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
