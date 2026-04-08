#!/usr/bin/env python3
"""Test META-COMPILE-X86 Phase B6: INTERPRET + self-hosting.

Builds metacompiled dictionary with INTERPRET, compiler
words, and control flow. Transfers control and verifies
the metacompiled kernel can process typed input.

Usage:
    python3 tests/test_meta_b6.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4590

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
BUILD_DIR = os.path.join(PROJECT_DIR, 'build')
IMAGE = os.path.join(BUILD_DIR, 'bmforth.img')
BLOCKS = os.path.join(BUILD_DIR, 'blocks.img')
QEMU = 'qemu-system-i386'


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


def send(s, cmd, wait=2):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(3)
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
    return None


def drain(s, wait=2.0):
    s.settimeout(wait)
    try:
        while True:
            d = s.recv(4096)
            if not d:
                break
    except Exception:
        pass


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


# Preflight
for f in [IMAGE, BLOCKS]:
    if not os.path.exists(f):
        print(f"FAIL: Missing {f}")
        sys.exit(1)

ASM_S, ASM_E = get_vocab_blocks('X86-ASM')
MC_S, MC_E = get_vocab_blocks('META-COMPILER')
TX_S, TX_E = get_vocab_blocks('TARGET-X86')

if not all([ASM_S, MC_S, TX_S]):
    print("FAIL: Could not determine block ranges")
    sys.exit(1)

print(f"X86-ASM: {ASM_S}-{ASM_E}, "
      f"META-COMPILER: {MC_S}-{MC_E}, "
      f"TARGET-X86: {TX_S}-{TX_E}")
print(f"Port: {PORT}")

# Kill stale QEMU
subprocess.run(
    ['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
    capture_output=True)
time.sleep(1)

# Launch QEMU
cmd = [
    QEMU,
    '-drive', f'file={IMAGE},format=raw,if=floppy',
    '-drive', f'file={BLOCKS},format=raw,if=ide,index=1',
    '-serial', f'tcp::{PORT},server=on,wait=off',
    '-display', 'none', '-daemonize',
]
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"FAIL: QEMU launch: {result.stderr.strip()}")
    sys.exit(1)

time.sleep(2)

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
for attempt in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print("FAIL: Cannot connect to QEMU")
    sys.exit(1)

drain(s)

# ============================================================
# Load vocabularies
# ============================================================

print("\nLoading vocabularies...")
send(s, f'{ASM_S} {ASM_E} THRU', 10)
send(s, f'{MC_S} {MC_E} THRU', 10)
r = send(s, f'{TX_S} {TX_E} THRU', 30)
check('All vocabs loaded', 'ok' in r.lower(),
      r.strip()[-40:])

send(s, 'USING TARGET-X86', 2)
send(s, 'ALSO META-COMPILER', 2)

# ============================================================
# META-COMPILE-X86
# ============================================================

print("\n=== META-COMPILE-X86 ===")
r = send(s, 'META-COMPILE-X86', 45)
check('META-COMPILE-X86 completes',
      'Phase B6 complete' in r, r.strip()[:100])

r = send(s, 'DECIMAL TSYM-N @ .', 2)
val = extract_number(r)
check(f'Symbol count >= 130 (got {val})',
      val is not None and val >= 130)

r = send(s, 'DECIMAL META-SIZE .', 2)
val = extract_number(r)
check(f'META-SIZE > 3500 (got {val})',
      val is not None and val > 3500)

# ============================================================
# Symbol verification
# ============================================================

print("\n=== Symbol Checks ===")
syms = ['INTERPRET', ':', ';', 'IF', 'THEN',
        'DO', 'LOOP', 'I', 'COLD', '(DO)',
        '(LOOP)', 'LITERAL', 'IMMEDIATE']
sym_found = 0
for sym in syms:
    r = send(s, f'HEX S" {sym}" T-FIND-SYM DECIMAL .', 2)
    val = extract_number(r)
    if val and val > 0:
        sym_found += 1
check(f'Key symbols ({sym_found}/{len(syms)})',
      sym_found == len(syms))

# ============================================================
# META-TRANSFER
# ============================================================

print("\n=== META-TRANSFER ===")
drain(s)
s.sendall(b'META-TRANSFER\r')
time.sleep(5)
s.settimeout(5)
r = b''
while True:
    try:
        d = s.recv(4096)
        if not d:
            break
        r += d
    except Exception:
        break
text = r.decode('ascii', 'replace')
has_ok = 'ok' in text
check('META-TRANSFER -> ok prompt', has_ok,
      text.strip()[:80])

if has_ok:
    print("\n=== Interactive Tests ===")

    # Set DECIMAL explicitly
    send(s, 'DECIMAL', 1)

    # Basic arithmetic
    r = send(s, '3 4 + .', 3)
    check('3 4 + . = 7', '7' in r, r.strip()[:60])

    # Colon definition
    r = send(s, ': SQ DUP * ;', 3)
    r = send(s, '5 SQ .', 3)
    check(': SQ DUP * ; 5 SQ . = 25',
          '25' in r, r.strip()[:60])

    # IF/ELSE/THEN
    r = send(s, '1 IF 42 ELSE 99 THEN .', 3)
    check('1 IF 42 = 42', '42' in r, r.strip()[:60])

    r = send(s, '0 IF 42 ELSE 99 THEN .', 3)
    check('0 IF 99 = 99', '99' in r, r.strip()[:60])

    # BEGIN/UNTIL (count down)
    r = send(s, ': CD 3 BEGIN DUP . 1- DUP 0= UNTIL DROP ;',
             3)
    r = send(s, 'CD', 3)
    check('BEGIN/UNTIL loop', '3' in r and '1' in r,
          r.strip()[:60])

    # DO/LOOP
    r = send(s, ': DT 5 0 DO I . LOOP ;', 3)
    r = send(s, 'DT', 3)
    check('DO/LOOP', '0' in r and '4' in r,
          r.strip()[:60])

    # Undefined word
    r = send(s, 'NOTAWORD', 3)
    check('Undefined word -> ?', '?' in r,
          r.strip()[:60])

    # DEPTH works (may have residue from tests)
    r = send(s, 'DEPTH .', 2)
    val = extract_number(r)
    check(f'DEPTH works (got {val})',
          val is not None, r.strip()[:60])

    # Empty line -> ok prompt
    r = send(s, '', 2)
    check('Empty line -> ok', 'ok' in r.lower(),
          r.strip()[:60])

# ============================================================
# Cleanup
# ============================================================

s.close()
subprocess.run(
    ['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
    capture_output=True)

print()
print(f'Passed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
