#!/usr/bin/env python3
"""Test ARM64 assembler vocabulary.

Loads X86-ASM (for T-HERE/T-,) then ARM64-ASM from blocks,
assembles ARM64 instructions into a buffer, verifies the
32-bit values match expected ARM64 machine code encodings.

Usage:
    python3 tests/test_arm64_asm.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4490

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
A64_START, A64_END = get_vocab_blocks('ARM64-ASM')
if ASM_START is None or A64_START is None:
    print("FAIL: Could not determine block ranges")
    print(f"  X86-ASM: {ASM_START}-{ASM_END}")
    print(f"  ARM64-ASM: {A64_START}-{A64_END}")
    sys.exit(1)
print(f"X86-ASM blocks: {ASM_START}-{ASM_END}")
print(f"ARM64-ASM blocks: {A64_START}-{A64_END}")

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


def reset_buffer():
    """Reset T-HERE to scratch area."""
    send('HEX HERE @ T-HERE !', 1)


def read_instr():
    """Read the 32-bit instruction just assembled.

    After T-, writes 4 bytes, T-HERE points past them.
    Read the 4 bytes as a 32-bit little-endian value.
    Forth . prints signed; convert to unsigned 32-bit.
    """
    r = send('T-HERE @ 4 - @ DECIMAL .', 1)
    val = extract_number(r)
    if val is not None and val < 0:
        val = val + 0x100000000
    return val


# ---- Load vocabularies ----
print(f"\nLoading X86-ASM ({ASM_START} {ASM_END} THRU)...")
r = send(f'{ASM_START} {ASM_END} THRU', 8)
print(f"  Response: {r.strip()[:60]!r}")

print(f"\nLoading ARM64-ASM ({A64_START} {A64_END} THRU)...")
r = send(f'{A64_START} {A64_END} THRU', 8)
print(f"  Response: {r.strip()[:60]!r}")

# ---- Test 1: ARM64-ASM vocab accessible ----
print("\nTest 1: ARM64-ASM vocabulary accessible")
# Need both X86-ASM (for T-HERE, T-,) and ARM64-ASM
# in the search order for instruction assembly.
r = send('USING X86-ASM', 1)
r = send('ALSO ARM64-ASM', 2)
has_ok = 'ok' in r.lower()
no_error = '?' not in r
check('ALSO ARM64-ASM succeeds',
      has_ok and no_error,
      f'response: {r.strip()!r}')

# ---- Test 2: Register constants ----
print("\nTest 2: Register constants")
r = send('DECIMAL W0 .', 1)
check('W0 = 0', extract_number(r) == 0,
      f'got {extract_number(r)}')
r = send('DECIMAL X27 .', 1)
check('X27 = 27', extract_number(r) == 27,
      f'got {extract_number(r)}')
r = send('DECIMAL WZR .', 1)
check('WZR = 31', extract_number(r) == 31,
      f'got {extract_number(r)}')
r = send('DECIMAL IP-REG .', 1)
check('IP-REG = 27', extract_number(r) == 27,
      f'got {extract_number(r)}')

# ---- Test 3: Condition codes ----
print("\nTest 3: Condition codes")
r = send('DECIMAL COND-EQ .', 1)
check('COND-EQ = 0', extract_number(r) == 0)
r = send('DECIMAL COND-NE .', 1)
check('COND-NE = 1', extract_number(r) == 1)
r = send('DECIMAL COND-LT .', 1)
check('COND-LT = 11', extract_number(r) == 11,
      f'got {extract_number(r)}')

# ---- Test 4: NOP encoding ----
print("\nTest 4: A64-NOP, encoding")
reset_buffer()
r = send('A64-NOP,', 1)
val = read_instr()
expected = 0xD503201F
check(f'NOP = 0x{expected:08X}',
      val == expected,
      f'got {val} (0x{val:08X})' if val else 'no value')

# ---- Test 5: ADD W2, W1, W0 ----
print("\nTest 5: A64-ADD, W0 W1 W2")
# ADD W2, W1, W0 = 0x0B000022
# base=0x0B000000 | (Rm=0 << 16) | (Rn=1 << 5) | Rd=2
reset_buffer()
r = send('W0 W1 W2 A64-ADD,', 1)
val = read_instr()
expected = 0x0B000022
check(f'ADD W2,W1,W0 = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 6: SUB W0, W1, W2 ----
print("\nTest 6: A64-SUB, W2 W1 W0")
# SUB W0, W1, W2 = 0x4B020020
# base=0x4B000000 | (Rm=2 << 16) | (Rn=1 << 5) | Rd=0
reset_buffer()
r = send('W2 W1 W0 A64-SUB,', 1)
val = read_instr()
expected = 0x4B020020
check(f'SUB W0,W1,W2 = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 7: LDR post-index (NEXT pattern) ----
print("\nTest 7: LDR W0, [X27], #4 (NEXT)")
# A64-LDR-POST: B8400400 | (4<<12) | (27<<5) | 0
# = B8400400 | 0x4000 | 0x360 | 0 = B8404760
reset_buffer()
r = send('HEX 4 X27 W0 A64-LDR-POST,', 1)
val = read_instr()
expected = 0xB8404760
check(f'LDR W0,[X27],#4 = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 8: STR pre-index (PUSH pattern) ----
print("\nTest 8: STR W0, [X25, #-4]! (PUSH)")
# A64-STR-PRE: B8000C00 | (0x1FC<<12) | (25<<5) | 0
# = B8000C00 | 0x1FC000 | 0x320 | 0 = B81FCF20
reset_buffer()
r = send('HEX 1FC X25 W0 A64-STR-PRE,', 1)
val = read_instr()
expected = 0xB81FCF20
check(f'STR W0,[X25,#-4]! = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 9: BR X1 ----
print("\nTest 9: BR X1")
# D61F0000 | (1 << 5) = D61F0020
reset_buffer()
r = send('X1 A64-BR,', 1)
val = read_instr()
expected = 0xD61F0020
check(f'BR X1 = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 10: RET ----
print("\nTest 10: RET")
reset_buffer()
r = send('A64-RET,', 1)
val = read_instr()
expected = 0xD65F03C0
check(f'RET = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 11: MOVZ W0, #0x1234 ----
print("\nTest 11: MOVZ W0, #0x1234")
# 52800000 | (0x1234 << 5) | 0 = 52824680
reset_buffer()
r = send('HEX 1234 W0 A64-MOVZ,', 1)
val = read_instr()
expected = 0x52824680
check(f'MOVZ W0,#0x1234 = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 12: CMP W1, W0 ----
print("\nTest 12: CMP W1, W0")
# CMP = SUBS WZR, Wn, Wm
# 6B000000 | (Rm=0 << 16) | (Rn=1 << 5) | 31(WZR)
# = 6B00003F
reset_buffer()
r = send('W0 W1 A64-CMP,', 1)
val = read_instr()
expected = 0x6B00003F
check(f'CMP W1,W0 = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 13: ADD#X X27, X0, #4 (64-bit) ----
print("\nTest 13: ADD X27, X0, #4 (64-bit)")
# 91000000 | (4 << 10) | (0 << 5) | 27
# = 91001000 | 0 | 1B = 9100101B
reset_buffer()
r = send('HEX 4 X0 X27 A64-ADD#X,', 1)
val = read_instr()
expected = 0x9100101B
check(f'ADD X27,X0,#4 = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 14: LDR unsigned offset ----
print("\nTest 14: LDR W0, [X0, #4]")
# B9400000 | ((4>>2) << 10) | (0 << 5) | 0
# = B9400000 | 0x400 | 0 | 0 = B9400400
reset_buffer()
r = send('HEX 4 X0 W0 A64-LDR-UOFF,', 1)
val = read_instr()
expected = 0xB9400400
check(f'LDR W0,[X0,#4] = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 15: CSET W0, EQ ----
print("\nTest 15: CSET W0, EQ")
# CSET: CSINC Wd, WZR, WZR, invert(cond)
# 1A9F07E0 | (invert(EQ=0)=1 << 12) | Rd=0
# = 1A9F07E0 | 0x1000 = 1A9F17E0
reset_buffer()
r = send('COND-EQ W0 A64-CSET,', 1)
val = read_instr()
expected = 0x1A9F17E0
check(f'CSET W0,EQ = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 16: Forward branch fixup ----
print("\nTest 16: Forward B and resolve")
reset_buffer()
# Emit B (placeholder), then NOP, then resolve
# B is at offset 0, NOP at offset 4, resolve at 8
# B should jump from offset 0 to offset 8 = +2 instrs
r = send('HEX HERE @ T-HERE !', 1)
r = send('A64-B,', 1)  # fixup addr on stack
r = send('A64-NOP,', 1)  # filler
r = send('A64-B>RES', 1)  # resolve: target = HERE
# B instr is 8 bytes before T-HERE
# offset = (T-HERE - fixup) / 4 = 8/4 = 2
r = send('HEX T-HERE @ 8 - @ DECIMAL .', 1)
val = extract_number(r)
expected = 0x14000002
check(f'B +2 instrs = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 17: SXTW-ADD for BRANCH ----
print("\nTest 17: SXTW-ADD X27,X27,W0")
# 8B20C000 | (Rm=0<<16) | (Rn=27<<5) | Rd=27
# = 8B20C000 | 0 | 0x360 | 0x1B = 8B20C37B
reset_buffer()
r = send('W0 X27 X27 A64-SXTW-ADD,', 1)
val = read_instr()
expected = 0x8B20C37B
check(f'ADD X27,X27,W0,SXTW = 0x{expected:08X}',
      val == expected,
      f'got 0x{val:08X}' if val else 'no value')

# ---- Test 18: Stack clean ----
print("\nTest 18: Stack clean")
r = send('.S', 1)
print(f"  .S => {r.strip()!r}")
check('Stack is clean after tests',
      '<>' in r,
      f'stack: {r.strip()!r}')

# ---- Summary ----
print()
print(f'Passed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
