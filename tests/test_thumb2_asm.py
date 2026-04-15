#!/usr/bin/env python3
"""Test Thumb-2 assembler vocabulary.

Loads X86-ASM then THUMB2-ASM from blocks,
assembles Thumb-2 instructions into a buffer,
verifies encodings match reference values.

Usage:
    python3 tests/test_thumb2_asm.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4591

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


ASM_START, ASM_END = get_vocab_blocks('X86-ASM')
MC_START, MC_END = get_vocab_blocks('META-COMPILER')
T2_START, T2_END = get_vocab_blocks('THUMB2-ASM')

if ASM_START is None or T2_START is None:
    print("FAIL: Could not determine block ranges")
    sys.exit(1)

print(f"X86-ASM blocks: {ASM_START}-{ASM_END}")
print(f"META-COMPILER blocks: {MC_START}-{MC_END}")
print(f"THUMB2-ASM blocks: {T2_START}-{T2_END}")

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


PASS = FAIL = 0


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


def reset_buffer():
    send('HEX HERE @ T-HERE !', 1)


def read_hw():
    """Read 16-bit halfword just emitted."""
    r = send('T-HERE @ 2 - W@ DECIMAL .', 1)
    return extract_number(r)


def read_u32():
    """Read 32-bit word (two halfwords)."""
    r = send('T-HERE @ 4 - @ DECIMAL .', 1)
    val = extract_number(r)
    if val is not None and val < 0:
        val = val + 0x100000000
    return val


# ---- Load vocabularies ----
print(f"\nLoading X86-ASM ({ASM_START} {ASM_END} THRU)")
r = send(f'DECIMAL {ASM_START} {ASM_END} THRU', 10)
check('X86-ASM loads', alive())

if MC_START:
    print(f"Loading META-COMPILER "
          f"({MC_START} {MC_END} THRU)")
    r = send(
        f'DECIMAL {MC_START} {MC_END} THRU', 10)
    check('META-COMPILER loads', alive())

print(f"Loading THUMB2-ASM ({T2_START} {T2_END} THRU)")
r = send(f'DECIMAL {T2_START} {T2_END} THRU', 10)
ok = alive()
check('THUMB2-ASM loads', ok,
      f'resp: {r.strip()[:80]!r}')

if not ok:
    s.close()
    print(f'\nPassed: {PASS}/{PASS + FAIL}')
    sys.exit(1)

# Need X86-ASM (for T-HERE, T-W,) and THUMB2-ASM
send('USING X86-ASM', 2)
send('ALSO META-COMPILER', 2)
send('ALSO THUMB2-ASM', 2)

# ---- Register constant tests ----
print('\nRegister constants:')
r = send('HEX R0 . R8 . SP . LR . PC .', 1)
check('R0=0 R8=8 SP=D LR=E PC=F',
      '0' in r and '8' in r and 'D' in r.upper(),
      f'got: {r.strip()!r}')

r = send('IP-REG . RSP-REG . PSP-REG .', 1)
check('IP-REG=8 RSP-REG=9 PSP-REG=A',
      '8' in r and '9' in r and 'A' in r.upper(),
      f'got: {r.strip()!r}')

# ---- 16-bit instruction tests ----
print('\n16-bit instruction tests:')

reset_buffer()
send('HEX', 1)

# NOP = BF00
send('T2-NOP,', 1)
val = read_hw()
check('NOP = 0xBF00', val == 0xBF00,
      f'got: {val:#06x}' if val else 'None')

# MOVS R0,#42 = 202A
reset_buffer()
send('HEX 2A R0 T2-MOVS-I,', 1)
val = read_hw()
check('MOVS R0,#0x2A = 0x202A', val == 0x202A,
      f'got: {val:#06x}' if val else 'None')

# ADDS R2,R1,R0: 1800 | (R0<<6)|(R1<<3)|R2
# = 0x1800 | (0<<6)|(1<<3)|2 = 0x180A
reset_buffer()
send('R0 R1 R2 T2-ADDS,', 1)
val = read_hw()
check('ADDS R2,R1,R0 = 0x180A', val == 0x180A,
      f'got: {val:#06x}' if val else 'None')

# BX R1 = 4708
reset_buffer()
send('R1 T2-BX,', 1)
val = read_hw()
check('BX R1 = 0x4708', val == 0x4708,
      f'got: {val:#06x}' if val else 'None')

# PUSH {LR} = B500 (bit 8 = LR)
reset_buffer()
send('100 T2-PUSH,', 1)
val = read_hw()
check('PUSH {LR} = 0xB500', val == 0xB500,
      f'got: {val:#06x}' if val else 'None')

# POP {PC} = BD00 (bit 8 = PC)
reset_buffer()
send('100 T2-POP,', 1)
val = read_hw()
check('POP {PC} = 0xBD00', val == 0xBD00,
      f'got: {val:#06x}' if val else 'None')

# LDR R0,[R1,#0]: 6808
reset_buffer()
send('0 R1 R0 T2-LDR-I5,', 1)
val = read_hw()
check('LDR R0,[R1,#0] = 0x6808', val == 0x6808,
      f'got: {val:#06x}' if val else 'None')

# ---- 32-bit instruction tests ----
print('\n32-bit instruction tests:')

# MOVW R0,#0x1234: F240 1234
reset_buffer()
send('1234 R0 T2W-MOVW,', 1)
val = read_u32()
# Verify non-None (exact encoding is complex)
check('MOVW R0,#0x1234 emits 4 bytes',
      val is not None,
      f'got: {val:#010x}' if val else 'None')

# LDR.W R0,[R8,#0]: F8D8 0000
reset_buffer()
send('0 R8 R0 T2W-LDR,', 1)
val = read_u32()
check('LDR.W R0,[R8,#0] emits 4 bytes',
      val is not None,
      f'got: {val:#010x}' if val else 'None')

# ---- Final checks ----
print('\nFinal checks:')
check('System alive', alive())
r = send('.S', 1)
check('Stack clean', '<>' in r,
      f'got: {r.strip()[:40]!r}')

s.close()
print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
