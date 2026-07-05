#!/usr/bin/env python3
"""Test ASM-VOCAB inline assembler vocabulary.

Loads ASM-VOCAB from blocks, defines CODE words, verifies
both DUMP byte sequences AND execution results.

Covers:
  - Core pipeline (CODE/END-CODE, NEXT,, register ops)
  - CFA self-reference (CODE override mechanism)
  - Two-operand direction (SUB non-commutative)
  - Opcode-extension encoding (NEG /3, ADD-IMM /0, CMP-IMM /7, SHL-CL /4)
  - Structured control flow (IF/THEN, UNTIL, IF/ELSE/THEN, WHILE/REPEAT)
  - Regression guard: HERE corruption, VAR_STATE, search-order balance

Usage:
    python3 tests/test_asm_vocab.py [PORT]
"""
import os
import shutil
import socket
import subprocess
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4580
PROJECT = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
BUILD = os.path.join(PROJECT, 'build')

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


# ---- Vocab block lookup (reused from test_x86_asm.py) ----

def get_vocab_blocks(vocab_name):
    """Get vocab start and end block from catalog."""
    try:
        result = subprocess.run(
            [sys.executable, '-c', f"""
import sys, os
sys.path.insert(0, os.path.join('{PROJECT}', 'tools'))
from importlib.machinery import SourceFileLoader
wc = SourceFileLoader('wc', os.path.join(
    '{PROJECT}', 'tools', 'write-catalog.py'
)).load_module()
vocabs = wc.scan_vocabs(os.path.join(
    '{PROJECT}', 'forth', 'dict'))
_nc = (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
nb = 1 + _nc
for v in vocabs:
    nb = wc.place_vocab(nb, v['blocks_needed'])
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


BLK_START, BLK_END = get_vocab_blocks('ASM-VOCAB')
if BLK_START is None:
    print("FAIL: Could not determine ASM-VOCAB block range")
    sys.exit(1)
print(f"ASM-VOCAB blocks: {BLK_START}-{BLK_END}")


# ---- Launch QEMU ----

subprocess.run(
    ['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
    capture_output=True)
time.sleep(1)

combined = os.path.join(BUILD, 'combined.img')
combined_ide = os.path.join(BUILD, 'combined-ide.img')
if not os.path.exists(combined):
    print(f'FAIL: {combined} not found (run make combined)')
    sys.exit(1)

# Block reads use ATA PIO (IDE), not floppy — need IDE copy
shutil.copy2(combined, combined_ide)

qemu_cmd = [
    'qemu-system-i386',
    '-drive', f'file={combined},format=raw,if=floppy',
    '-drive', f'file={combined_ide},format=raw,if=ide,index=1',
    '-serial', f'tcp::{PORT},server=on,wait=off',
    '-display', 'none',
    '-daemonize',
]

print(f'Launching QEMU (port {PORT})...')
r = subprocess.run(qemu_cmd, capture_output=True)
if r.returncode != 0:
    print(f'FAIL: QEMU launch: {r.stderr.decode()[:200]}')
    sys.exit(1)
time.sleep(3)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
for _ in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print('FAIL: Could not connect to QEMU')
    subprocess.run(
        ['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
        capture_output=True)
    sys.exit(1)

time.sleep(2)
try:
    while True:
        s.recv(4096)
except Exception:
    pass


# ---- Serial helpers ----

def drain():
    """Drain stale bytes from serial buffer."""
    s.settimeout(0.3)
    try:
        while True:
            d = s.recv(4096)
            if not d:
                break
    except Exception:
        pass


def send(cmd, wait=1.0, recv_cap=65536):
    """Send Forth command, collect response."""
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(1.0)
    resp = b''
    while len(resp) < recv_cap:
        try:
            d = s.recv(8192)
            if not d:
                break
            resp += d
        except Exception:
            break
    return resp.decode('ascii', errors='replace')


def alive():
    r = send('DECIMAL 1 2 + .', 0.5)
    return '3' in r


def cleanup():
    s.close()
    subprocess.run(
        ['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
        capture_output=True)


def extract_decimal(resp):
    """Extract signed decimal number from `. ` output.

    Strategy: find the last numeric token before 'ok'.
    Handles negative numbers (-7).
    """
    lines = resp.replace('\r', '').split('\n')
    for line in reversed(lines):
        tokens = line.split()
        # Walk backward through tokens on this line
        found_ok = False
        for tok in reversed(tokens):
            if tok == 'ok':
                found_ok = True
                continue
            if found_ok or not any(t == 'ok' for t in tokens):
                try:
                    return int(tok)
                except ValueError:
                    continue
    # Fallback: scan all tokens
    for line in reversed(lines):
        for tok in reversed(line.split()):
            if tok == 'ok':
                continue
            try:
                return int(tok)
            except ValueError:
                continue
    return None


def extract_hex_val(resp):
    """Extract hex number from Forth output (BASE=HEX)."""
    lines = resp.replace('\r', '').split('\n')
    for line in reversed(lines):
        tokens = line.split()
        for tok in reversed(tokens):
            if tok.lower() == 'ok':
                continue
            try:
                return int(tok, 16)
            except ValueError:
                continue
    return None


def parse_dump_bytes(resp):
    """Parse DUMP output into a list of byte values.

    DUMP format: XXXXXXXX: XX XX XX XX ...
    Returns list of ints.
    """
    result = []
    for line in resp.replace('\r', '').split('\n'):
        line = line.strip()
        if ':' not in line:
            continue
        # Split on first colon — everything after is hex bytes
        _, _, after = line.partition(':')
        for tok in after.split():
            if len(tok) == 2:
                try:
                    result.append(int(tok, 16))
                except ValueError:
                    break  # hit ASCII column or non-hex
            else:
                break
    return result


def check_bytes(name, actual, expected, offset=0):
    """Assert a subsequence of bytes matches expected."""
    sub = actual[offset:offset + len(expected)]
    ok = sub == expected
    if not ok:
        exp_s = ' '.join(f'{b:02X}' for b in expected)
        act_s = ' '.join(f'{b:02X}' for b in sub) if sub else '(empty)'
        all_s = ' '.join(f'{b:02X}' for b in actual)
        check(name, False,
              f'expected [{exp_s}] at offset {offset}, '
              f'got [{act_s}] in [{all_s}]')
    else:
        check(name, True)
    return ok


# ========== Test Suite ==========
print('\nASM-VOCAB Test Suite')
print('=' * 55)

check('System alive', alive())

# ---- Load ASM-VOCAB ----
print(f'\nLoading ASM-VOCAB ({BLK_START} {BLK_END} THRU)...')
r = send(f'{BLK_START} {BLK_END} THRU', 10)
check('THRU completed', 'ok' in r.lower(),
      f'response: {r.strip()[:200]!r}')

r = send('USING ASM-VOCAB', 2)
check('USING ASM-VOCAB', 'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')


# ============================================================
# REGRESSION GUARD (pre): 42 . must work before any CODE def
# ============================================================
print('\n--- Regression guard (pre) ---')
r = send('DECIMAL 42 .', 0.5)
val = extract_decimal(r)
check('42 . before CODE def', val == 42,
      f'got {val} (raw: {r.strip()!r})')


# ============================================================
# CORE PIPELINE: MY+
# ============================================================
print('\n--- Core pipeline: MY+ ---')

# Define MY+: pop two, add, push result, NEXT
# Body: 58 59 01 C8 50 AD FF 20
r = send('CODE MY+', 1)
send('%EAX POP,', 0.3)
send('%ECX POP,', 0.3)
send('%ECX %EAX ADD,', 0.3)
send('%EAX PUSH,', 0.3)
send('NEXT,', 0.3)
r = send('END-CODE', 1)
check('MY+ defined', 'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')

# DUMP body bytes
r = send("HEX ' MY+ @ 8 DUMP", 1)
body = parse_dump_bytes(r)
check_bytes('MY+ body == 58 59 01 C8 50 AD FF 20',
            body,
            [0x58, 0x59, 0x01, 0xC8, 0x50, 0xAD, 0xFF, 0x20])

# Execute
r = send('DECIMAL 3 4 MY+ .', 0.5)
val = extract_decimal(r)
check('3 4 MY+ . == 7', val == 7,
      f'got {val} (raw: {r.strip()!r})')

# CFA self-reference: ' MY+ @ == ' MY+ 4 +
# Push both values, subtract, check == 0
r = send("HEX ' MY+ @ ' MY+ 4 + - DECIMAL .", 0.5)
val = extract_decimal(r)
check("CFA self-ref: ' MY+ @ == ' MY+ 4 +", val == 0,
      f'difference = {val} (raw: {r.strip()!r})')


# ============================================================
# TWO-OPERAND: TSUB (SUB direction, non-commutative)
# ============================================================
print('\n--- Two-operand: TSUB ---')

# TSUB: pop EAX(TOS=3), pop ECX(NOS=10), ECX %EAX SUB → EAX=3-10=-7
# Body: 58 59 29 C8 50 AD FF 20
r = send('CODE TSUB', 1)
send('%EAX POP,', 0.3)
send('%ECX POP,', 0.3)
send('%ECX %EAX SUB,', 0.3)
send('%EAX PUSH,', 0.3)
send('NEXT,', 0.3)
r = send('END-CODE', 1)
check('TSUB defined', 'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')

# DUMP: check for SUB opcode + ModRM
r = send("HEX ' TSUB @ 8 DUMP", 1)
body = parse_dump_bytes(r)
check_bytes('TSUB SUB byte == 29 C8', body, [0x29, 0xC8], offset=2)

# Execute: 10 3 TSUB = 3 - 10 = -7
r = send('DECIMAL 10 3 TSUB .', 0.5)
val = extract_decimal(r)
check('10 3 TSUB . == -7', val == -7,
      f'got {val} (raw: {r.strip()!r})')


# ============================================================
# OPCODE-EXTENSION: TNEG (F7 /3 = D8)
# ============================================================
print('\n--- Opcode-extension: TNEG ---')

r = send('CODE TNEG', 1)
send('%EAX POP,', 0.3)
send('%EAX NEG,', 0.3)
send('%EAX PUSH,', 0.3)
send('NEXT,', 0.3)
r = send('END-CODE', 1)
check('TNEG defined', 'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')

# DUMP: check NEG encoding at offset 1 (after POP EAX = 58)
r = send("HEX ' TNEG @ 7 DUMP", 1)
body = parse_dump_bytes(r)
check_bytes('TNEG NEG == F7 D8', body, [0xF7, 0xD8], offset=1)

# Execute
r = send('DECIMAL 5 TNEG .', 0.5)
val = extract_decimal(r)
check('5 TNEG . == -5', val == -5,
      f'got {val} (raw: {r.strip()!r})')


# ============================================================
# OPCODE-EXTENSION: TADD-IMM (81 /0 = C0)
# ============================================================
print('\n--- Opcode-extension: TADD-IMM ---')

# Body: 58 81 C0 03 00 00 00 50 AD FF 20
r = send('CODE TADD-IMM', 1)
send('%EAX POP,', 0.3)
send('3 %EAX ADD-IMM,', 0.3)
send('%EAX PUSH,', 0.3)
send('NEXT,', 0.3)
r = send('END-CODE', 1)
check('TADD-IMM defined', 'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')

# DUMP: check ADD-IMM encoding at offset 1
r = send("HEX ' TADD-IMM @ B DUMP", 1)
body = parse_dump_bytes(r)
check_bytes('TADD-IMM == 81 C0 03 00 00 00',
            body, [0x81, 0xC0, 0x03, 0x00, 0x00, 0x00], offset=1)

# Execute
r = send('DECIMAL 7 TADD-IMM .', 0.5)
val = extract_decimal(r)
check('7 TADD-IMM . == 10', val == 10,
      f'got {val} (raw: {r.strip()!r})')


# ============================================================
# OPCODE-EXTENSION: TCMP (CMP-IMM, 81 /7 = F8) — NEW
# ============================================================
print('\n--- CMP-IMM (new): TCMP ---')

# TCMP: CMP EAX, 5 → JZ → ELSE body / fall-through → IF body
# Assembler IF, convention: JZ jumps when ZF set (equal),
# so fall-through (IF body) = not-equal, ELSE body = equal.
# Body: 58 81 F8 05 00 00 00 74 07 B8 63 00 00 00 EB 05 B8 4D 00 00 00 50 AD FF 20
#
# Layout:
#   0: 58         POP EAX
#   1: 81 F8 05 00 00 00   CMP-IMM EAX, 5
#   7: 74 07      JZ +7 (skip IF-body + ELSE jmp)
#   9: B8 63 00 00 00   MOV EAX, 99 (IF body: not-equal)
#  14: EB 05      JMP +5 (skip ELSE-body)
#  16: B8 4D 00 00 00   MOV EAX, 77 (ELSE body: equal)
#  21: 50         PUSH EAX
#  22: AD FF 20   NEXT

r = send('CODE TCMP', 1)
send('%EAX POP,', 0.3)
send('5 %EAX CMP-IMM,', 0.3)
send('#JZ IF,', 0.3)
send('99 %EAX MOV-IMM,', 0.3)    # not-equal path (fall-through)
send('ELSE,', 0.3)
send('77 %EAX MOV-IMM,', 0.3)    # equal path (JZ taken)
send('THEN,', 0.3)
send('%EAX PUSH,', 0.3)
send('NEXT,', 0.3)
r = send('END-CODE', 1)
check('TCMP defined', 'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')

# DUMP: verify CMP-IMM encoding (81 F8 05 00 00 00)
r = send("HEX ' TCMP @ 19 DUMP", 1.5)
body = parse_dump_bytes(r)
check_bytes('TCMP CMP-IMM == 81 F8 05 00 00 00',
            body, [0x81, 0xF8, 0x05, 0x00, 0x00, 0x00], offset=1)

# Verify /7 specifically — F8 is the key byte (not C0 or E8)
if len(body) > 2:
    check('CMP-IMM ModRM == F8 (reg field /7)',
          body[2] == 0xF8,
          f'got {body[2]:02X}' if len(body) > 2 else 'no data')
else:
    check('CMP-IMM ModRM == F8 (reg field /7)', False, 'no DUMP data')

# Execute: CMP-IMM sets flags, conditional branch works
# Equal: JZ taken → ELSE body → 77
r = send('DECIMAL 5 TCMP .', 0.5)
val = extract_decimal(r)
check('5 TCMP . == 77 (equal: JZ taken)', val == 77,
      f'got {val} (raw: {r.strip()!r})')

# Not-equal: JZ not taken → IF body → 99
r = send('DECIMAL 3 TCMP .', 0.5)
val = extract_decimal(r)
check('3 TCMP . == 99 (not-equal: fall-through)', val == 99,
      f'got {val} (raw: {r.strip()!r})')


# ============================================================
# OPCODE-EXTENSION: TSHL (SHL-CL, D3 /4 = E0)
# ============================================================
print('\n--- Opcode-extension: TSHL ---')

# TSHL: pop CL(shift count), pop EAX(value), SHL, push result
# Body: 59 58 D3 E0 50 AD FF 20
r = send('CODE TSHL', 1)
send('%ECX POP,', 0.3)
send('%EAX POP,', 0.3)
send('%EAX SHL-CL,', 0.3)
send('%EAX PUSH,', 0.3)
send('NEXT,', 0.3)
r = send('END-CODE', 1)
check('TSHL defined', 'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')

# DUMP
r = send("HEX ' TSHL @ 8 DUMP", 1)
body = parse_dump_bytes(r)
check_bytes('TSHL SHL-CL == D3 E0', body, [0xD3, 0xE0], offset=2)

# Execute: 1 << 3 == 8
r = send('DECIMAL 1 3 TSHL .', 0.5)
val = extract_decimal(r)
check('1 3 TSHL . == 8', val == 8,
      f'got {val} (raw: {r.strip()!r})')


# ============================================================
# CONTROL FLOW: TIF (IF/THEN, rel8 = 05)
# ============================================================
print('\n--- Control flow: TIF (IF/THEN) ---')

# TIF: test EAX; if non-zero → MOV 99; push
# Body: 58 85 C0 74 05 B8 63 00 00 00 50 AD FF 20
r = send('CODE TIF', 1)
send('%EAX POP,', 0.3)
send('%EAX %EAX TEST,', 0.3)
send('#JZ IF,', 0.3)
send('99 %EAX MOV-IMM,', 0.3)    # 99 decimal = 0x63
send('THEN,', 0.3)
send('%EAX PUSH,', 0.3)
send('NEXT,', 0.3)
r = send('END-CODE', 1)
check('TIF defined', 'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')

# DUMP: IF, at offset 3 should emit 74 05
r = send("HEX ' TIF @ E DUMP", 1)
body = parse_dump_bytes(r)
check_bytes('TIF IF rel8 == 05', body, [0x74, 0x05], offset=3)

# Execute both paths:
# Input 1: ZF clear → JZ not taken → falls to offset 5 (MOV 99)
r = send('DECIMAL 1 TIF .', 0.5)
val = extract_decimal(r)
check('1 TIF . == 99 (not-taken path)', val == 99,
      f'got {val} (raw: {r.strip()!r})')

# Input 0: ZF set → JZ taken → +5 from offset 5 = offset 10 (PUSH)
# EAX still 0 from POP → result 0
r = send('DECIMAL 0 TIF .', 0.5)
val = extract_decimal(r)
check('0 TIF . == 0 (taken path skips body)', val == 0,
      f'got {val} (raw: {r.strip()!r})')


# ============================================================
# CONTROL FLOW: TLOOP (BEGIN/UNTIL, rel8 = FB = -5)
# ============================================================
print('\n--- Control flow: TLOOP (BEGIN/UNTIL) ---')

# TLOOP: pop count, loop: DEC, TEST, JNZ back
# Body: 58 48 85 C0 75 FB 50 AD FF 20
#
# BEGIN, = offset 1 (DEC)
# DEC = 1 byte (48)
# TEST = 2 bytes (85 C0)
# UNTIL = 2 bytes (75 FB)
# rel8 = dest - (HERE@+1) = 1 - 6 = -5 = FB
r = send('CODE TLOOP', 1)
send('%EAX POP,', 0.3)
send('BEGIN,', 0.3)
send('%EAX DEC,', 0.3)
send('%EAX %EAX TEST,', 0.3)
send('#JNZ UNTIL,', 0.3)
send('%EAX PUSH,', 0.3)
send('NEXT,', 0.3)
r = send('END-CODE', 1)
check('TLOOP defined', 'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')

# DUMP: UNTIL at offset 4 should emit 75 FB
r = send("HEX ' TLOOP @ A DUMP", 1)
body = parse_dump_bytes(r)
check_bytes('TLOOP UNTIL rel8 == FB (-5)',
            body, [0x75, 0xFB], offset=4)

# Execute: 5 TLOOP → decrements to 0 → terminates
r = send('DECIMAL 5 TLOOP .', 1)
val = extract_decimal(r)
check('5 TLOOP . == 0 (terminates)', val == 0,
      f'got {val} (raw: {r.strip()!r})')


# ============================================================
# CONTROL FLOW: TELSE (IF/ELSE/THEN)
# IF rel8 == 07, ELSE rel8 == 05
# ============================================================
print('\n--- Control flow: TELSE (IF/ELSE/THEN) ---')

# TELSE: test EAX; if zero → MOV 20; else → MOV 10
# Body: 58 85 C0 74 07 B8 0A 00 00 00 EB 05 B8 14 00 00 00 50 AD FF 20
#
# offset 3: 74 07  (IF, → jump over 5-byte MOV + 2-byte ELSE JMP)
# offset 10: EB 05 (ELSE, → jump over 5-byte MOV)
r = send('CODE TELSE', 1)
send('%EAX POP,', 0.3)
send('%EAX %EAX TEST,', 0.3)
send('#JZ IF,', 0.3)
send('10 %EAX MOV-IMM,', 0.3)    # 10 decimal = 0x0A (non-zero → IF body)
send('ELSE,', 0.3)
send('20 %EAX MOV-IMM,', 0.3)    # 20 decimal = 0x14 (zero → ELSE body)
send('THEN,', 0.3)
send('%EAX PUSH,', 0.3)
send('NEXT,', 0.3)
r = send('END-CODE', 1)
check('TELSE defined', 'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')

# DUMP: IF at offset 3, ELSE at offset 10
r = send("HEX ' TELSE @ 15 DUMP", 1.5)
body = parse_dump_bytes(r)
check_bytes('TELSE IF rel8 == 07', body, [0x74, 0x07], offset=3)
check_bytes('TELSE ELSE rel8 == 05', body, [0xEB, 0x05], offset=10)

# Execute both paths:
# Input 0: ZF set → JZ taken → +7 from offset 5 = offset 12 (ELSE body, MOV 20)
r = send('DECIMAL 0 TELSE .', 0.5)
val = extract_decimal(r)
check('0 TELSE . == 20 (taken path)', val == 20,
      f'got {val} (raw: {r.strip()!r})')

# Input 1: ZF clear → JZ not taken → falls to offset 5 (IF body, MOV 10)
r = send('DECIMAL 1 TELSE .', 0.5)
val = extract_decimal(r)
check('1 TELSE . == 10 (not-taken path)', val == 10,
      f'got {val} (raw: {r.strip()!r})')


# ============================================================
# CONTROL FLOW: TWHL (BEGIN/WHILE/REPEAT)
# WHILE rel8 == 03, REPEAT rel8 == F9 (-7)
# ============================================================
print('\n--- Control flow: TWHL (WHILE/REPEAT) ---')

# TWHL: loop while non-zero, decrementing
# Body: 58 85 C0 74 03 48 EB F9 50 AD FF 20
#
# BEGIN, = offset 1 (TEST)
# offset 1: 85 C0  TEST EAX,EAX (2 bytes)
# offset 3: 74 03  JZ WHILE, → forward exit (2 bytes)
# offset 5: 48     DEC EAX (1 byte)
# offset 6: EB F9  JMP REPEAT, → backward (2 bytes)
# offset 8: 50     PUSH EAX
#
# WHILE, rel8 = HERE@(8) - fixup(3) - 1 = 8 - 3 - 1 = ... wait
# Let me recalculate:
# After JZ opcode (74), IF, pushes HERE@ as fixup, emits 0.
# fixup = offset 4 (the rel8 byte address)
# After DEC(1) + JMP(EB)(1) + rel8(1), THEN resolves:
# HERE@ = offset 8, rel8 = 8 - 4 - 1 = 3 ✓
#
# REPEAT JMP rel8: dest=offset 1 (BEGIN)
# After EB, HERE@ = offset 7
# rel8 = dest - (HERE@+1) = 1 - (7+1) = 1-8 = -7... wait
# REPEAT code: EB C, HERE @ 1 + - C,
# After EB, HERE@ = 7. Stack: ( fixup dest=1 )
# HERE@ = 7, 1 + = 8, dest - 8 = 1 - 8 = -7 → F9 ✓

r = send('CODE TWHL', 1)
send('%EAX POP,', 0.3)
send('BEGIN,', 0.3)
send('%EAX %EAX TEST,', 0.3)
send('#JZ WHILE,', 0.3)
send('%EAX DEC,', 0.3)
send('REPEAT,', 0.3)
send('%EAX PUSH,', 0.3)
send('NEXT,', 0.3)
r = send('END-CODE', 1)
check('TWHL defined', 'ok' in r.lower() and '?' not in r,
      f'response: {r.strip()!r}')

# DUMP
r = send("HEX ' TWHL @ C DUMP", 1)
body = parse_dump_bytes(r)
check_bytes('TWHL WHILE rel8 == 03', body, [0x74, 0x03], offset=3)
check_bytes('TWHL REPEAT rel8 == F9 (-7)', body, [0xEB, 0xF9], offset=6)

# Execute: 3 TWHL → decrements to 0 → exits
r = send('DECIMAL 3 TWHL .', 1)
val = extract_decimal(r)
check('3 TWHL . == 0 (terminates)', val == 0,
      f'got {val} (raw: {r.strip()!r})')


# ============================================================
# REGRESSION GUARD (post)
# ============================================================
print('\n--- Regression guard (post) ---')

# 42 . still works after all CODE definitions
r = send('DECIMAL 42 .', 0.5)
val = extract_decimal(r)
check('42 . after CODE defs', val == 42,
      f'got {val} (raw: {r.strip()!r})')

# VAR_STATE == 0 (not stuck in compile mode)
r = send('HEX 28000 @ DECIMAL .', 0.5)
val = extract_decimal(r)
check('VAR_STATE == 0 after CODE defs', val == 0,
      f'got {val} (raw: {r.strip()!r})')

# Search-order balance: plain arithmetic still resolves
r = send('DECIMAL 1 2 + .', 0.5)
val = extract_decimal(r)
check('1 2 + . == 3 (search order intact)', val == 3,
      f'got {val} (raw: {r.strip()!r})')

# Stack clean
r = send('.S', 0.5)
check('Stack clean', '<>' in r,
      f'stack: {r.strip()!r}')


# ========== Summary ==========
print(f'\nPassed: {PASS}/{PASS + FAIL}')
cleanup()
sys.exit(0 if FAIL == 0 else 1)
