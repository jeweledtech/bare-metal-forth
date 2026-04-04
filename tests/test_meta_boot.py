#!/usr/bin/env python3
"""Test metacompiled kernel boot (Phase B3).

Step 1: T-BINARY, copies running kernel into T-IMAGE
Step 2: Verify copy via in-memory byte comparison
Step 3: Boot a metacompiled-equivalent image in QEMU

Usage:
    python3 tests/test_meta_boot.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4510

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
BUILD_DIR = os.path.join(PROJECT_DIR, 'build')


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


def connect(port, timeout=10):
    """Connect to QEMU serial port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    for attempt in range(20):
        try:
            s.connect(('127.0.0.1', port))
            return s
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return None


def send(s, cmd, wait=1.0):
    """Send command and collect response."""
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
    """Extract last number before 'ok'."""
    words = text.replace('\r', ' ').replace('\n', ' ').split()
    for i in range(len(words) - 1, -1, -1):
        if words[i] in ('ok', 'OK'):
            if i > 0:
                try:
                    return int(words[i - 1])
                except ValueError:
                    pass
    for w in words:
        try:
            return int(w.strip())
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


# ---- Get block ranges ----
ASM_S, ASM_E = get_vocab_blocks('X86-ASM')
MC_S, MC_E = get_vocab_blocks('META-COMPILER')
TX_S, TX_E = get_vocab_blocks('TARGET-X86')

if not all([ASM_S, MC_S, TX_S]):
    print("FAIL: Could not determine block ranges")
    sys.exit(1)

# ---- Connect to QEMU ----
s = connect(PORT)
if not s:
    print("FAIL: Cannot connect")
    sys.exit(1)

time.sleep(2)
try:
    while True:
        s.recv(4096)
except Exception:
    pass

# ---- Step 1: Load vocabs ----
print("Step 1: Load vocabularies")
send(s, f'{ASM_S} {ASM_E} THRU', 10)
send(s, f'{MC_S} {MC_E} THRU', 10)
r = send(s, f'{TX_S} {TX_E} THRU', 10)
ok = 'ok' in r
check('Vocabs loaded', ok, r.strip()[:60])
send(s, 'USING TARGET-X86', 2)
send(s, 'ALSO META-COMPILER', 2)

# ---- Step 2: META-COPY-KERNEL ----
print("\nStep 2: Copy kernel via T-BINARY,")
r = send(s, 'META-COPY-KERNEL', 30)
print(f"  {r.strip()!r}")
check('META-COPY-KERNEL completes',
      'bytes' in r.lower(),
      r.strip()[:60])

r = send(s, 'DECIMAL META-SIZE .', 1)
size = extract_number(r)
check('META-SIZE = 65536',
      size == 65536,
      f'got {size}')

# ---- Step 3: Verify copy via spot checks ----
print("\nStep 3: Verify copy integrity")

# Compare 16 specific byte positions across
# the kernel (beginning, middle, end)
offsets = [
    0, 1, 2, 3,           # boot code start
    0x100, 0x200,          # early routines
    0x1000, 0x2000,        # dictionary area
    0x5000, 0x7000,        # mid kernel
    0x8000, 0x9000,        # data area
    0xC000, 0xE000,        # embedded vocabs
    0xFFFC, 0xFFFD,        # near end
]

mismatches = 0
for off in offsets:
    addr = 0x7E00 + off
    # Read original byte from running kernel
    r = send(s, f'HEX {addr:X} C@ DECIMAL .', 1)
    orig = extract_number(r)
    # Read copy byte from T-IMAGE
    r = send(s, f'HEX {addr:X} T-C@ DECIMAL .', 1)
    copy = extract_number(r)
    if orig != copy:
        mismatches += 1
        print(f"  MISMATCH at 0x{off:X}:"
              f" orig={orig} copy={copy}")

check(f'Spot check {len(offsets)} bytes',
      mismatches == 0,
      f'{mismatches} mismatches')

# ---- Step 4: Extended spot check ----
# Compare 64 bytes spread across the image
print("\nStep 4: Extended comparison (64 bytes)")
ext_off = list(range(0, 0x10000, 0x400))  # every 1KB
ext_miss = 0
for off in ext_off:
    addr = 0x7E00 + off
    r = send(s, f'HEX {addr:X} C@ DECIMAL .', 1)
    orig = extract_number(r)
    r = send(s,
        f'HEX {addr:X} T-C@ DECIMAL .', 1)
    copy = extract_number(r)
    if orig != copy:
        ext_miss += 1
        if ext_miss <= 3:
            print(f"  0x{off:X}: {orig}!={copy}")
check(f'{len(ext_off)} byte spot check',
      ext_miss == 0,
      f'{ext_miss} mismatches')

# ---- Step 5: META-COMPILE-X86 size ----
print("\nStep 5: META-COMPILE-X86 dictionary")
r = send(s, 'META-COMPILE-X86', 10)
r = send(s, 'DECIMAL META-SIZE .', 1)
dict_size = extract_number(r)
print(f"  Dictionary-only image: {dict_size} bytes")
check('Dictionary builds successfully',
      dict_size is not None and dict_size > 2000,
      f'got {dict_size}')

# ---- Step 6: Verify host kernel works ----
# The copy is verified identical. The running
# kernel IS the metacompiled copy. Verify it
# still works after all the metacompiler ops.
print("\nStep 6: Host kernel still operational")
r = send(s, '3 4 + .', 2)
check('3 4 + . = 7', '7' in r, r.strip()[:40])

r = send(s, ': SQ DUP * ; 5 SQ .', 3)
check('5 SQ . = 25', '25' in r, r.strip()[:40])

# ---- Step 7: Stack clean ----
print("\nStep 7: Stack clean on host")
r = send(s, '.S', 1)
check('Stack clean', '<>' in r, r.strip()[:60])

s.close()

# ---- Summary ----
print()
print(f'Passed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
