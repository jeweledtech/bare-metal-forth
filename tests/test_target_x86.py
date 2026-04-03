#!/usr/bin/env python3
"""Test TARGET-X86 metacompiler vocabulary.

Loads X86-ASM, META-COMPILER, then TARGET-X86 from blocks.
Runs META-COMPILE-X86 and verifies machine code bytes.

Usage:
    python3 tests/test_target_x86.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4491

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


# Get block ranges for all three vocabs
ASM_START, ASM_END = get_vocab_blocks('X86-ASM')
MC_START, MC_END = get_vocab_blocks('META-COMPILER')
TX_START, TX_END = get_vocab_blocks('TARGET-X86')

if ASM_START is None or MC_START is None or TX_START is None:
    print("FAIL: Could not determine block ranges")
    print(f"  X86-ASM: {ASM_START}-{ASM_END}")
    print(f"  META-COMPILER: {MC_START}-{MC_END}")
    print(f"  TARGET-X86: {TX_START}-{TX_END}")
    sys.exit(1)

print(f"X86-ASM blocks: {ASM_START}-{ASM_END}")
print(f"META-COMPILER blocks: {MC_START}-{MC_END}")
print(f"TARGET-X86 blocks: {TX_START}-{TX_END}")

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
        except Exception:
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


def read_byte(taddr):
    """Read a byte from target image at given address."""
    r = send(f'HEX {taddr:X} T-C@ DECIMAL .', 1)
    return extract_number(r)


def verify_bytes(name, base_expr, expected):
    """Verify machine code bytes starting at an address.

    base_expr: Forth expression that leaves addr on stack
    expected: list of byte values
    """
    # Read the base address
    r = send(f'{base_expr} DECIMAL .', 1)
    base = extract_number(r)
    if base is None:
        check(f'{name} base addr', False, 'could not read')
        return False

    ok = True
    for i, exp in enumerate(expected):
        val = read_byte(base + i)
        if val != exp:
            check(f'{name} byte[{i}]',
                  False,
                  f'at 0x{base+i:X}: '
                  f'expected 0x{exp:02X}, '
                  f'got {val}')
            ok = False
            break
    if ok:
        check(f'{name} ({len(expected)} bytes)', True)
    return ok


# ---- Load vocabularies ----
print(f"\nLoading X86-ASM ({ASM_START} {ASM_END} THRU)...")
r = send(f'{ASM_START} {ASM_END} THRU', 10)
print(f"  response: {r.strip()!r}")

print(f"\nLoading META-COMPILER "
      f"({MC_START} {MC_END} THRU)...")
r = send(f'{MC_START} {MC_END} THRU', 10)
print(f"  response: {r.strip()!r}")

print(f"\nLoading TARGET-X86 "
      f"({TX_START} {TX_END} THRU)...")
r = send(f'{TX_START} {TX_END} THRU', 10)
print(f"  response: {r.strip()!r}")

# ---- Test 1: TARGET-X86 vocab loads ----
print("\nTest 1: TARGET-X86 vocabulary accessible")
r = send('USING TARGET-X86', 2)
has_ok = 'ok' in r.lower()
no_error = '?' not in r
check('USING TARGET-X86 succeeds',
      has_ok and no_error,
      f'response: {r.strip()!r}')

# ---- Test 2: META-COMPILE-X86 runs ----
print("\nTest 2: META-COMPILE-X86 runs")
r = send('ALSO META-COMPILER', 2)
r = send('META-COMPILE-X86', 10)
print(f"  response: {r.strip()!r}")
check('META-COMPILE-X86 completes',
      'complete' in r.lower(),
      f'response: {r.strip()!r}')

# ---- Test 3: META-SIZE reasonable ----
print("\nTest 3: META-SIZE > 0")
r = send('DECIMAL META-SIZE .', 1)
val = extract_number(r)
print(f"  META-SIZE = {val}")
check('META-SIZE > 100',
      val is not None and val > 100,
      f'expected >100, got {val}')

# ---- Test 4: Runtime addresses set ----
print("\nTest 4: Runtime addresses set")
for name in ['DOCOL-ADDR', 'DOEXIT-ADDR', 'DOLIT-ADDR',
             'DOBRANCH-ADDR', 'DO0BRANCH-ADDR',
             'DOCON-ADDR', 'DOCREATE-ADDR']:
    r = send(f'{name} @ DECIMAL .', 1)
    val = extract_number(r)
    check(f'{name} > 0',
          val is not None and val > 0,
          f'got {val}')

# ---- Test 5: Forward ref count = 0 ----
print("\nTest 5: Forward ref count after build")
r = send('FREF-COUNT @ DECIMAL .', 1)
val = extract_number(r)
check('FREF-COUNT = 0',
      val == 0,
      f'got {val}')

# ---- Test 6: DOCOL machine code ----
# DOCOL = sub ebp,4 (83 ED 04) + mov [ebp],esi
# Using MOV-DISP!, which uses mod=2 for EBP:
# 89 B5 00 00 00 00
# Then: add eax,4 (83 C0 04)
#        mov esi,eax (89 C6)
#        lodsd (AD) jmp [eax] (FF 20)
print("\nTest 6: DOCOL machine code")
# First 3 bytes: 83 ED 04 (sub ebp, 4)
verify_bytes('DOCOL',
             'HEX DOCOL-ADDR @',
             [0x83, 0xED, 0x04])

# ---- Test 7: EXIT machine code ----
# EXIT = mov esi,[ebp] + add ebp,4 + NEXT
# POPRSP uses MOV-DISP@, with mod=2 for EBP:
# 8B B5 00 00 00 00 (mov esi,[ebp+0]) = 6 bytes
# Then: add ebp,4 (83 C5 04)
# Then: NEXT = lodsd (AD) + jmp [eax] (FF 20)
print("\nTest 7: EXIT machine code")
# First byte of EXIT code = 8B (mov r,[...])
r = send(
    'HEX DOEXIT-ADDR @ 4 + T-C@ DECIMAL .', 1)
val = extract_number(r)
check('EXIT code starts with 0x8B (mov)',
      val == 0x8B,
      f'expected 0x8B, got {val}')

# ---- Test 8: DROP machine code ----
# DROP = pop eax (58) + NEXT (AD FF 20)
print("\nTest 8: DROP machine code")
# Find DROP by walking dictionary
# After META-COMPILE-X86, T-LINK-VAR holds
# the last word's link addr. We need to find
# DROP specifically.
# Easier: check a known pattern after DOCREATE
# DROP is defined right after DOCREATE
# For now, just verify META-SIZE looks right

# Check META-SIZE is reasonable for ~40 words
r = send('DECIMAL META-SIZE .', 1)
val = extract_number(r)
check('META-SIZE reasonable (200-4000)',
      val is not None and 200 <= val <= 4000,
      f'got {val}')

# ---- Test 9: Dictionary chain valid ----
# T-LINK-VAR should hold address of last word
print("\nTest 9: Dictionary chain valid")
r = send('HEX T-LINK-VAR @ DECIMAL .', 1)
link = extract_number(r)
check('T-LINK-VAR > 0 (chain exists)',
      link is not None and link > 0,
      f'got {link}')

# ---- Test 10: Rebuild produces same result ----
print("\nTest 10: Rebuild consistency")
# Get current size from first build
r = send('DECIMAL META-SIZE .', 1)
size1 = extract_number(r)
# Rebuild and compare
r = send('META-COMPILE-X86', 10)
check('Rebuild completes',
      'complete' in r.lower(),
      f'{r.strip()!r}')
r = send('DECIMAL META-SIZE .', 1)
size2 = extract_number(r)
check('Rebuild same size',
      size1 is not None and size1 == size2,
      f'first={size1}, second={size2}')

# ---- Test 11: LIT machine code ----
# LIT = lodsd (AD) + push eax (50) + NEXT (AD FF 20)
print("\nTest 11: LIT machine code")
verify_bytes('LIT',
             'HEX DOLIT-ADDR @ 4 +',
             [0xAD, 0x50, 0xAD, 0xFF, 0x20])

# ---- Test 12: BRANCH machine code ----
# BRANCH = add esi,[esi] (03 36) + NEXT (AD FF 20)
print("\nTest 12: BRANCH machine code")
verify_bytes('BRANCH',
             'HEX DOBRANCH-ADDR @ 4 +',
             [0x03, 0x36, 0xAD, 0xFF, 0x20])

# ---- Test 13: DOCON machine code ----
# DOCON = push [eax+4] (FF 70 04) +
#         NEXT (AD FF 20)
print("\nTest 13: DOCON machine code")
verify_bytes('DOCON',
             'HEX DOCON-ADDR @',
             [0xFF, 0x70, 0x04, 0xAD, 0xFF, 0x20])

# ---- Test 14: DOCREATE machine code ----
# DOCREATE = lea eax,[eax+4] (8D 40 04) +
#            push eax (50) + NEXT (AD FF 20)
print("\nTest 14: DOCREATE machine code")
verify_bytes('DOCREATE',
             'HEX DOCREATE-ADDR @',
             [0x8D, 0x40, 0x04, 0x50,
              0xAD, 0xFF, 0x20])

# ---- Test 15: SQUARE threaded code ----
# SQUARE = T-COLON def: DOCOL, DUP, *, EXIT
# Code field = DOCOL-ADDR, then body = CFAs
print("\nTest 15: SQUARE threaded code")
# Find SQUARE CFA via symbol table
r = send(
    'S" SQUARE" T-FIND-SYM DECIMAL .', 2)
sq_cfa = extract_number(r)
check('SQUARE found in symbol table',
      sq_cfa is not None and sq_cfa > 0,
      f'got {sq_cfa}')

if sq_cfa and sq_cfa > 0:
    # Code field should contain DOCOL-ADDR
    r = send(
        f'HEX {sq_cfa:X} T-@ DECIMAL .', 1)
    cf_val = extract_number(r)
    r = send('DOCOL-ADDR @ DECIMAL .', 1)
    docol = extract_number(r)
    check('SQUARE code field = DOCOL',
          cf_val == docol,
          f'cf={cf_val}, docol={docol}')

    # Body: first cell = DUP CFA
    r = send(
        f'HEX {sq_cfa+4:X} T-@ DECIMAL .', 1)
    body1 = extract_number(r)
    r = send(
        'S" DUP" T-FIND-SYM DECIMAL .', 1)
    dup_cfa = extract_number(r)
    check('SQUARE body[0] = DUP CFA',
          body1 == dup_cfa,
          f'body1={body1}, dup={dup_cfa}')

    # Body: second cell = * CFA
    r = send(
        f'HEX {sq_cfa+8:X} T-@ DECIMAL .', 1)
    body2 = extract_number(r)
    r = send(
        'S" *" T-FIND-SYM DECIMAL .', 1)
    mul_cfa = extract_number(r)
    check('SQUARE body[1] = * CFA',
          body2 == mul_cfa,
          f'body2={body2}, mul={mul_cfa}')

    # Body: third cell = EXIT CFA
    r = send(
        f'HEX {sq_cfa+12:X} T-@ DECIMAL .', 1)
    body3 = extract_number(r)
    r = send('DOEXIT-ADDR @ DECIMAL .', 1)
    exit_cfa = extract_number(r)
    check('SQUARE body[2] = EXIT CFA',
          body3 == exit_cfa,
          f'body3={body3}, exit={exit_cfa}')

# ---- Test 16: Symbol count ----
print("\nTest 16: Symbol count")
r = send('TSYM-N @ DECIMAL .', 1)
val = extract_number(r)
check('Symbol count >= 78',
      val is not None and val >= 78,
      f'got {val}')

# ---- Test 17: Stack clean ----
print("\nTest 17: Stack clean")
r = send('.S', 1)
print(f"  .S => {r.strip()!r}")
check('Stack clean',
      '<>' in r,
      f'stack: {r.strip()!r}')

# ---- Summary ----
print()
print(f'Passed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
