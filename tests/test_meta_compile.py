#!/usr/bin/env python3
"""Test META-COMPILE-X86 with B5 extensions.

Loads X86-ASM, META-COMPILER, TARGET-X86 from blocks,
runs META-COMPILE-X86, verifies I/O + compiler words.

Manages its own QEMU instance for clean state.

Usage:
    python3 tests/test_meta_compile.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os
import signal

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4520

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
BUILD_DIR = os.path.join(PROJECT_DIR, 'build')
COMBINED = os.path.join(BUILD_DIR, 'combined.img')
COMBINED_IDE = os.path.join(BUILD_DIR, 'combined-ide.img')
QEMU = 'qemu-system-i386'


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


def send(s, cmd, wait=1.0):
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


# ============================================================
# Preflight
# ============================================================

for f in [COMBINED, COMBINED_IDE]:
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
    '-drive', f'file={COMBINED},format=raw,if=floppy',
    '-drive', f'file={COMBINED_IDE},format=raw,if=ide,index=1',
    '-serial', f'tcp::{PORT},server=on,wait=off',
    '-display', 'none',
    '-daemonize',
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
r = send(s, 'META-COMPILE-X86', 15)
print(f"  {r.strip()!r}")
check('META-COMPILE-X86 completes',
      'Phase B' in r and 'complete' in r,
      r.strip()[:80])

r = send(s, 'DECIMAL TSYM-N @ .', 1)
val = extract_number(r)
check(f'Symbol count >= 100 (got {val})',
      val is not None and val >= 100)

r = send(s, 'DECIMAL META-SIZE .', 1)
val = extract_number(r)
check(f'META-SIZE > 2500 (got {val})',
      val is not None and val > 2500)

# ============================================================
# Symbol checks
# ============================================================

print("\n=== Symbol Verification ===")

io_words = ['KEY', 'EMIT', 'CR', 'SPACE', 'TYPE']
io_found = 0
for w in io_words:
    r = send(s, f'S" {w}" T-FIND-SYM DECIMAL .', 2)
    val = extract_number(r)
    if val and val > 0:
        io_found += 1
check(f'I/O words ({io_found}/5)',
      io_found == 5)

disp_found = 0
for w in ['.']:
    r = send(s, f'S" {w}" T-FIND-SYM DECIMAL .', 2)
    val = extract_number(r)
    if val and val > 0:
        disp_found += 1
check(f'Display words ({disp_found}/1)',
      disp_found == 1)

var_words = ['STATE', 'HERE', 'LATEST', 'BASE']
var_found = 0
for w in var_words:
    r = send(s, f'S" {w}" T-FIND-SYM DECIMAL .', 2)
    val = extract_number(r)
    if val and val > 0:
        var_found += 1
check(f'Variable words ({var_found}/4)',
      var_found == 4)

comp_words = ['WORD', 'NUMBER', 'FIND',
              'CREATE', 'ALLOT']
comp_found = 0
for w in comp_words:
    r = send(s, f'S" {w}" T-FIND-SYM DECIMAL .', 2)
    val = extract_number(r)
    if val and val > 0:
        comp_found += 1
check(f'Compiler words ({comp_found}/5)',
      comp_found == 5)

# ============================================================
# CALL-ABS displacement verification
# ============================================================

print("\n=== CALL-ABS Displacement ===")

# KEY: E8 <disp32> 50 AD FF 20
r = send(s, 'S" KEY" T-FIND-SYM T-@ 1+ T-@ '
         'DECIMAL .', 2)
actual = extract_number(r)
r = send(s, 'ADDR-READ-KEY '
         'S" KEY" T-FIND-SYM T-@ 5 + - '
         'DECIMAL .', 2)
expected = extract_number(r)
check(f'KEY disp (a={actual} e={expected})',
      actual == expected)

# EMIT: 58 E8 <disp32> AD FF 20
r = send(s, 'S" EMIT" T-FIND-SYM T-@ '
         '2 + T-@ DECIMAL .', 2)
actual = extract_number(r)
r = send(s, 'ADDR-PRINT-CHAR '
         'S" EMIT" T-FIND-SYM T-@ 6 + - '
         'DECIMAL .', 2)
expected = extract_number(r)
check(f'EMIT disp (a={actual} e={expected})',
      actual == expected)

# ============================================================
# Stack clean
# ============================================================

r = send(s, '.S', 1)
check('Stack clean', '<>' in r,
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
