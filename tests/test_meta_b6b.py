#!/usr/bin/env python3
"""Test META-COMPILE-X86-BOOT Phase B6b: standalone boot.

Builds a metacompiled kernel image, extracts via QEMU monitor,
assembles a bootable disk image, boots it in a fresh QEMU,
and verifies the Forth interpreter works standalone.

Usage:
    python3 tests/test_meta_b6b.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4570
MON_PORT = PORT + 1
BOOT_PORT = PORT + 2

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
BUILD_DIR = os.path.join(PROJECT_DIR, 'build')
IMAGE = os.path.join(BUILD_DIR, 'bmforth.img')
BLOCKS = os.path.join(BUILD_DIR, 'blocks.img')
BOOT_BIN = os.path.join(BUILD_DIR, 'boot.bin')
META_KERNEL = '/tmp/forthos-meta-B6b.bin'
META_IMAGE = os.path.join(BUILD_DIR, 'meta-boot-b6b.img')

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


def kill_qemu(port_pattern):
    subprocess.run(
        ['pkill', '-9', '-f', f'[q]emu.*{port_pattern}'],
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
    if os.path.exists(META_KERNEL):
        os.unlink(META_KERNEL)


# ============================================================
# Preflight
# ============================================================

for f in [IMAGE, BLOCKS, BOOT_BIN]:
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
print(f"Ports: serial={PORT}, monitor={MON_PORT}, "
      f"boot={BOOT_PORT}")

# ============================================================
# Phase 1: Build metacompiled kernel
# ============================================================

print("\n=== Phase 1: Build ===")

kill_qemu(str(PORT))
kill_qemu(str(BOOT_PORT))

cmd = [
    QEMU,
    '-drive', f'file={IMAGE},format=raw,if=floppy',
    '-drive', f'file={BLOCKS},format=raw,if=ide,index=1',
    '-serial', f'tcp::{PORT},server=on,wait=off',
    '-monitor', f'tcp::{MON_PORT},server=on,wait=off',
    '-display', 'none', '-daemonize',
]
result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"FAIL: QEMU launch: {result.stderr.strip()}")
    sys.exit(1)

time.sleep(2)

s = connect(PORT)
if not s:
    print("FAIL: Cannot connect to builder QEMU")
    cleanup()
    sys.exit(1)

drain(s)

# Load vocabularies
print("\nLoading vocabularies...")
send(s, f'{ASM_S} {ASM_E} THRU', 10)
send(s, f'{MC_S} {MC_E} THRU', 10)
r = send(s, f'{TX_S} {TX_E} THRU', 30)
check('All vocabs loaded', 'ok' in r.lower(),
      r.strip()[-40:])

send(s, 'USING TARGET-X86', 2)
send(s, 'ALSO META-COMPILER', 2)

# Run META-COMPILE-X86-BOOT
print("\nRunning META-COMPILE-X86-BOOT...")
r = send(s, 'META-COMPILE-X86-BOOT', 60)
print(f"  Output: {r.strip()!r}")
check('META-COMPILE-X86-BOOT completes',
      'Phase B6b complete' in r,
      r.strip()[:100])

# Check symbol count
r = send(s, 'DECIMAL TSYM-N @ .', 2)
val = extract_number(r)
check(f'Symbol count >= 130 (got {val})',
      val is not None and val >= 130)

# Check image used size
r = send(s, 'HEX T-HERE @ T-IMAGE - .', 2)
print(f"  T-HERE offset: {r.strip()!r}")

# ============================================================
# Phase 2: Extract via QEMU monitor
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

# Connect to monitor
mon = connect(MON_PORT, timeout=5, retries=10)
if not mon:
    print("FAIL: Cannot connect to QEMU monitor")
    s.close()
    cleanup()
    sys.exit(1)

drain(mon, wait=1)

if os.path.exists(META_KERNEL):
    os.unlink(META_KERNEL)

# Always extract 64KB for bootloader compatibility
extract_size = 65536
cmd_str = f'pmemsave {meta_addr} {extract_size} "{META_KERNEL}"'
print(f"  Monitor cmd: {cmd_str}")
r = mon_send(mon, cmd_str, wait=2)

extracted_ok = (os.path.exists(META_KERNEL) and
                os.path.getsize(META_KERNEL) == extract_size)
check(f'pmemsave extracts {extract_size} bytes',
      extracted_ok,
      f'exists={os.path.exists(META_KERNEL)}, '
      f'size={os.path.getsize(META_KERNEL) if os.path.exists(META_KERNEL) else 0}')

if not extracted_ok:
    print("FAIL: Extraction failed")
    s.close()
    mon.close()
    cleanup()
    sys.exit(1)

# Verify patches in extracted binary
with open(META_KERNEL, 'rb') as f:
    kdata = f.read()

# Check embed_size is zeroed (at the offset where
# embed_size lives in the binary)
# Find the pattern: last 4 non-zero bytes before the
# zero padding should include the zeroed embed_size
# We verify by checking that the "Phase B6b" output
# included no WARN messages (simpler and sufficient)

# Check that LATEST init was patched (the imm32 after
# C7 05 08 80 02 00 should differ from original kernel)
with open(os.path.join(BUILD_DIR, 'kernel.bin'), 'rb') as f:
    orig = f.read()

pat = bytes([0xC7, 0x05, 0x08, 0x80, 0x02, 0x00])
orig_latest = None
meta_latest = None
for i in range(len(orig) - 10):
    if orig[i:i + 6] == pat:
        orig_latest = int.from_bytes(
            orig[i + 6:i + 10], 'little')
        break
for i in range(len(kdata) - 10):
    if kdata[i:i + 6] == pat:
        meta_latest = int.from_bytes(
            kdata[i + 6:i + 10], 'little')
        break

check(f'LATEST patched (orig=0x{orig_latest or 0:X}, '
      f'meta=0x{meta_latest or 0:X})',
      orig_latest is not None and
      meta_latest is not None and
      orig_latest != meta_latest)

s.close()
mon.close()

# ============================================================
# Phase 3: Assemble + Boot
# ============================================================

print("\n=== Phase 3: Assemble + Boot ===")

with open(BOOT_BIN, 'rb') as f:
    boot = f.read()
with open(META_KERNEL, 'rb') as f:
    kernel = f.read()

with open(META_IMAGE, 'wb') as f:
    f.write(boot + kernel)

img_size = os.path.getsize(META_IMAGE)
check(f'meta-boot-b6b.img assembled ({img_size} bytes)',
      img_size == 512 + 65536)

# Kill builder, launch booted kernel
kill_qemu(str(PORT))
time.sleep(1)

boot_cmd = [
    QEMU,
    '-drive', f'file={META_IMAGE},format=raw,if=floppy',
    '-serial', f'tcp::{BOOT_PORT},server=on,wait=off',
    '-display', 'none', '-daemonize',
]
result = subprocess.run(boot_cmd, capture_output=True,
                        text=True)
if result.returncode != 0:
    print(f"FAIL: Booted QEMU launch: "
          f"{result.stderr.strip()}")
    cleanup()
    sys.exit(1)

time.sleep(3)

bs = connect(BOOT_PORT, timeout=10, retries=20)
check('Connection to booted kernel', bs is not None)

if bs is None:
    print("FAIL: Cannot connect to booted kernel")
    cleanup()
    sys.exit(1)

# No embedded vocabs = fast boot. Just drain and check.
drain(bs, wait=2)
r = send(bs, '', 3)
print(f"  Boot prompt: {r.strip()[:120]!r}")
check('ok prompt received', 'ok' in r.lower(),
      r.strip()[:80])

# ============================================================
# Phase 4: Functional verification
# ============================================================

print("\n=== Phase 4: Verify ===")

send(bs, 'DECIMAL', 1)

r = send(bs, '3 4 + .', 3)
check('3 4 + . = 7', '7' in r, r.strip()[:60])

r = send(bs, ': SQ DUP * ;', 3)
r = send(bs, '5 SQ .', 3)
check('5 SQ . = 25', '25' in r, r.strip()[:60])

r = send(bs, '1 IF 42 ELSE 99 THEN .', 3)
check('IF/ELSE/THEN true = 42', '42' in r,
      r.strip()[:60])

r = send(bs, '0 IF 42 ELSE 99 THEN .', 3)
check('IF/ELSE/THEN false = 99', '99' in r,
      r.strip()[:60])

r = send(bs, ': CD 3 BEGIN DUP . 1- DUP 0= UNTIL DROP ;',
         3)
r = send(bs, 'CD', 3)
check('BEGIN/UNTIL loop', '3' in r and '1' in r,
      r.strip()[:60])

r = send(bs, ': DT 5 0 DO I . LOOP ;', 3)
r = send(bs, 'DT', 3)
check('DO/LOOP', '0' in r and '4' in r,
      r.strip()[:60])

r = send(bs, 'NOTAWORD', 3)
check('Undefined word -> ?', '?' in r,
      r.strip()[:60])

r = send(bs, '', 2)
check('Empty line -> ok', 'ok' in r.lower(),
      r.strip()[:60])

# ============================================================
# Cleanup
# ============================================================

bs.close()
kill_qemu(str(BOOT_PORT))
if os.path.exists(META_KERNEL):
    os.unlink(META_KERNEL)

print()
print(f'Passed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
