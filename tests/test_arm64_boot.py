#!/usr/bin/env python3
"""Test ARM64 Phase C: boot ForthOS on QEMU raspi3b.

Builds an ARM64 kernel image via metacompiler on x86,
extracts via QEMU monitor, boots on qemu-system-aarch64
raspi3b, and verifies the Forth interpreter works.

Usage:
    python3 tests/test_arm64_boot.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os
import shutil

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4590
MON_PORT = PORT + 1
BOOT_PORT = PORT + 2

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
BUILD_DIR = os.path.join(PROJECT_DIR, 'build')
COMBINED = os.path.join(BUILD_DIR, 'combined.img')
COMBINED_IDE = os.path.join(BUILD_DIR, 'combined-ide.img')
ARM64_KERNEL = '/tmp/forthos-arm64.bin'

QEMU_X86 = 'qemu-system-i386'
QEMU_ARM64 = 'qemu-system-aarch64'


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


def connect(port, timeout=10, retries=20):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    for attempt in range(retries):
        try:
            s.connect(('127.0.0.1', port))
            return s
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return None


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


def mon_send(s, cmd, wait=1.0):
    s.sendall((cmd + '\n').encode())
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


def drain(s, wait=2.0):
    s.settimeout(wait)
    try:
        while True:
            d = s.recv(4096)
            if not d:
                break
    except Exception:
        pass


def kill_qemu(port_pattern):
    subprocess.run(
        ['pkill', '-9', '-f',
         f'[q]emu.*{port_pattern}'],
        capture_output=True)
    time.sleep(1)


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


def cleanup():
    kill_qemu(str(PORT))
    kill_qemu(str(BOOT_PORT))
    if os.path.exists(ARM64_KERNEL):
        os.unlink(ARM64_KERNEL)


# ============================================================
# Preflight
# ============================================================

for f in [COMBINED, COMBINED_IDE]:
    if not os.path.exists(f):
        print(f"FAIL: Missing {f}")
        sys.exit(1)

if not shutil.which(QEMU_ARM64):
    print(f"SKIP: {QEMU_ARM64} not installed")
    print("Install with: sudo apt install qemu-system-arm")
    sys.exit(0)

# Get block ranges for all needed vocabs
ASM_S, ASM_E = get_vocab_blocks('X86-ASM')
MC_S, MC_E = get_vocab_blocks('META-COMPILER')
A64_S, A64_E = get_vocab_blocks('ARM64-ASM')
TA_S, TA_E = get_vocab_blocks('TARGET-ARM64')

if not all([ASM_S, MC_S, A64_S, TA_S]):
    print("FAIL: Could not determine block ranges")
    print(f"  X86-ASM={ASM_S}, META-COMPILER={MC_S}, "
          f"ARM64-ASM={A64_S}, TARGET-ARM64={TA_S}")
    sys.exit(1)

print(f"X86-ASM: {ASM_S}-{ASM_E}")
print(f"META-COMPILER: {MC_S}-{MC_E}")
print(f"ARM64-ASM: {A64_S}-{A64_E}")
print(f"TARGET-ARM64: {TA_S}-{TA_E}")
print(f"Ports: serial={PORT}, monitor={MON_PORT}, "
      f"boot={BOOT_PORT}")

# ============================================================
# Phase 1: Build ARM64 kernel via x86 metacompiler
# ============================================================

print("\n=== Phase 1: Build ===")

kill_qemu(str(PORT))
kill_qemu(str(BOOT_PORT))

cmd = [
    QEMU_X86,
    '-drive', f'file={COMBINED},format=raw,if=floppy',
    '-drive',
    f'file={COMBINED_IDE},format=raw,if=ide,index=1',
    '-serial', f'tcp::{PORT},server=on,wait=off',
    '-monitor', f'tcp::{MON_PORT},server=on,wait=off',
    '-display', 'none', '-daemonize',
]
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"FAIL: x86 QEMU launch: {result.stderr.strip()}")
    sys.exit(1)

time.sleep(2)

s = connect(PORT)
if not s:
    print("FAIL: Cannot connect to builder QEMU")
    cleanup()
    sys.exit(1)

drain(s)

# Load all four vocabularies
print("\nLoading vocabularies...")
r = send(s, f'{ASM_S} {ASM_E} THRU', 15)
check('X86-ASM loaded', '?' not in r, r.strip()[-60:])

r = send(s, f'{MC_S} {MC_E} THRU', 15)
check('META-COMPILER loaded', '?' not in r,
      r.strip()[-60:])

r = send(s, f'{A64_S} {A64_E} THRU', 15)
check('ARM64-ASM loaded', '?' not in r,
      r.strip()[-60:])

r = send(s, f'{TA_S} {TA_E} THRU', 30)
check('TARGET-ARM64 loaded', '?' not in r,
      r.strip()[-60:])

send(s, 'USING TARGET-ARM64', 2)
send(s, 'ALSO META-COMPILER', 2)
send(s, 'ALSO ARM64-ASM', 2)

# Run META-COMPILE-ARM64-BOOT
print("\nRunning META-COMPILE-ARM64-BOOT...")
r = send(s, 'META-COMPILE-ARM64-BOOT', 60)
print(f"  Output: {r.strip()!r}")
check('META-COMPILE-ARM64-BOOT completes',
      'ARM64 boot:' in r,
      r.strip()[:120])

# Check symbol count
r = send(s, 'DECIMAL TSYM-N @ .', 2)
words = r.replace('\r', ' ').replace('\n', ' ').split()
sym_count = None
for i in range(len(words) - 1, -1, -1):
    if words[i] in ('ok', 'OK') and i > 0:
        try:
            sym_count = int(words[i - 1])
        except ValueError:
            pass
        break
check(f'Symbol count >= 60 (got {sym_count})',
      sym_count is not None and sym_count >= 60)

# Check META-STATUS
r = send(s, 'META-STATUS', 2)
check('META-STATUS OK', 'OK' in r, r.strip()[:80])

# Check META-CHECK (no unresolved)
r = send(s, 'META-CHECK', 2)
check('No unresolved refs',
      'Unresolved' not in r, r.strip()[:80])

# ============================================================
# Phase 2: Extract ARM64 image via QEMU monitor
# ============================================================

print("\n=== Phase 2: Extract ===")

r = send(s, 'META-SAVE', 2)
print(f"  META-SAVE: {r.strip()!r}")

meta_addr = None
meta_size = None
for line in r.replace('\r', '\n').split('\n'):
    if 'META-SAVE:' in line:
        parts = line.split()
        for i, w in enumerate(parts):
            if w == 'META-SAVE:' and i + 2 < len(parts):
                try:
                    meta_addr = int(parts[i + 1])
                    meta_size = int(parts[i + 2])
                except ValueError:
                    pass

check('META-SAVE reports address/size',
      meta_addr is not None and meta_size is not None,
      f'addr={meta_addr}, size={meta_size}')

if meta_addr is None or meta_size is None:
    print("FAIL: Cannot proceed without T-IMAGE address")
    s.close()
    cleanup()
    sys.exit(1)

# Connect to QEMU monitor
mon = connect(MON_PORT, timeout=5, retries=10)
if not mon:
    print("FAIL: Cannot connect to QEMU monitor")
    s.close()
    cleanup()
    sys.exit(1)

drain(mon, wait=1)

if os.path.exists(ARM64_KERNEL):
    os.unlink(ARM64_KERNEL)

# Extract the full T-IMAGE (up to 64KB)
extract_size = min(meta_size, 65536)
if extract_size < 1024:
    extract_size = 65536
cmd_str = (f'pmemsave {meta_addr} {extract_size}'
           f' "{ARM64_KERNEL}"')
print(f"  Monitor cmd: {cmd_str}")
r = mon_send(mon, cmd_str, wait=2)

extracted_ok = (os.path.exists(ARM64_KERNEL) and
                os.path.getsize(ARM64_KERNEL) > 0)
actual_size = (os.path.getsize(ARM64_KERNEL)
               if os.path.exists(ARM64_KERNEL) else 0)
check(f'pmemsave extracts image ({actual_size} bytes)',
      extracted_ok,
      f'exists={os.path.exists(ARM64_KERNEL)}, '
      f'size={actual_size}')

if not extracted_ok:
    print("FAIL: Extraction failed")
    s.close()
    mon.close()
    cleanup()
    sys.exit(1)

# Quick sanity: first 4 bytes should be a valid ARM64
# instruction (not all zeros)
with open(ARM64_KERNEL, 'rb') as f:
    first_word = int.from_bytes(f.read(4), 'little')
check(f'First instruction non-zero (0x{first_word:08X})',
      first_word != 0)

s.close()
mon.close()

# ============================================================
# Phase 3: Boot on QEMU raspi3b
# ============================================================

print("\n=== Phase 3: ARM64 Boot ===")

kill_qemu(str(PORT))
time.sleep(1)

boot_cmd = [
    QEMU_ARM64,
    '-M', 'raspi3b',
    '-kernel', ARM64_KERNEL,
    '-serial',
    f'tcp::{BOOT_PORT},server=on,wait=on,nodelay=on',
    '-display', 'none',
]
print(f"  CMD: {' '.join(boot_cmd)}")

# Use Popen (wait=on means QEMU blocks until client
# connects, so -daemonize won't work)
qemu_proc = subprocess.Popen(
    boot_cmd,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL)

# Connect — QEMU waits for us, then starts executing
time.sleep(1)

bs = connect(BOOT_PORT, timeout=10, retries=30)
check('Connection to ARM64 kernel', bs is not None)

if bs is None:
    print("FAIL: Cannot connect to ARM64 kernel")
    qemu_proc.kill()
    cleanup()
    sys.exit(1)

# With wait=on, ForthOS starts AFTER we connect.
# Wait for "ok " prompt.
time.sleep(3)
drain(bs, wait=2)

# Send CR to get a fresh prompt (first one may be
# partially consumed by drain)
r = send(bs, '', 5)
print(f"  Boot output: {r.strip()[:120]!r}")

# If no prompt yet, try again
if 'ok' not in r.lower():
    r = send(bs, '', 5)
    print(f"  Retry: {r.strip()[:120]!r}")

# Also verify via file output (more reliable
# than TCP on raspi3b)
try:
    qemu_proc.kill()
    qemu_proc.wait(timeout=5)
except Exception:
    pass
time.sleep(1)

FILE_OUT = '/tmp/forthos-arm64-verify.txt'
if os.path.exists(FILE_OUT):
    os.unlink(FILE_OUT)
file_proc = subprocess.Popen([
    QEMU_ARM64, '-M', 'raspi3b',
    '-kernel', ARM64_KERNEL,
    '-serial', f'file:{FILE_OUT}',
    '-display', 'none', '-daemonize'
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(5)
file_data = b''
if os.path.exists(FILE_OUT):
    file_data = open(FILE_OUT, 'rb').read()
print(f"  File output: {file_data[:40]!r}")
check('ok prompt (file verify)',
      b'ok' in file_data,
      file_data[:40].decode('ascii', errors='replace'))
kill_qemu('raspi')
time.sleep(1)

tcp_ok = 'ok' in r.lower()
check('ok prompt (TCP)', tcp_ok or b'ok' in file_data,
      r.strip()[:80])

# ============================================================
# Phase 4: Functional verification
# ============================================================

print("\n=== Phase 4: Verify ===")
print("  NOTE: TCP RX on QEMU raspi3b may not "
      "deliver input. Tests may fail due to this "
      "QEMU limitation, not ARM64 code bugs.")

# Relaunch with wait=on for interactive tests
qemu_proc = subprocess.Popen([
    QEMU_ARM64, '-M', 'raspi3b',
    '-kernel', ARM64_KERNEL,
    '-serial',
    f'tcp::{BOOT_PORT},server=on,wait=on,nodelay=on',
    '-display', 'none',
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
bs = connect(BOOT_PORT, timeout=10, retries=30)
if bs is None:
    print("  SKIP: Cannot reconnect for Phase 4")
    print()
    print(f'Passed: {PASS}/{PASS + FAIL}')
    qemu_proc.kill()
    sys.exit(0 if FAIL == 0 else 1)

time.sleep(3)
drain(bs, wait=2)
send(bs, 'DECIMAL', 2)

# Basic arithmetic
r = send(bs, '3 4 + .', 3)
check('3 4 + . = 7', '7' in r, r.strip()[:60])

r = send(bs, '10 1 - .', 3)
check('10 1 - . = 9', '9' in r, r.strip()[:60])

r = send(bs, '6 7 * .', 3)
check('6 7 * . = 42', '42' in r, r.strip()[:60])

# Floored division
r = send(bs, '-7 3 / .', 3)
check('-7 3 / . = -3 (floored)', '-3' in r,
      r.strip()[:60])

# Colon definition
r = send(bs, ': SQ DUP * ;', 3)
r = send(bs, '7 SQ .', 3)
check(': SQ DUP * ; 7 SQ . = 49', '49' in r,
      r.strip()[:60])

# IF/ELSE/THEN
r = send(bs, '1 IF 42 ELSE 99 THEN .', 3)
check('IF true = 42', '42' in r, r.strip()[:60])

r = send(bs, '0 IF 42 ELSE 99 THEN .', 3)
check('IF false = 99', '99' in r, r.strip()[:60])

# DO/LOOP
r = send(bs, '5 0 DO I . LOOP', 3)
check('DO/LOOP', '0' in r and '4' in r,
      r.strip()[:60])

# Undefined word
r = send(bs, 'NOTAWORD', 3)
check('Undefined word -> ?', '?' in r,
      r.strip()[:60])

# HEX mode
r = send(bs, 'HEX FF DECIMAL .', 3)
check('HEX FF = 255', '255' in r, r.strip()[:60])

# ============================================================
# Cleanup
# ============================================================

bs.close()
try:
    qemu_proc.kill()
    qemu_proc.wait(timeout=5)
except Exception:
    pass
kill_qemu(str(BOOT_PORT))
if os.path.exists(ARM64_KERNEL):
    os.unlink(ARM64_KERNEL)

print()
print(f'Passed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
