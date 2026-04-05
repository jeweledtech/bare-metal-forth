#!/usr/bin/env python3
"""Test metacompiled kernel boot (Phase B3 + B4).

Phase B3: T-BINARY, copies running kernel into T-IMAGE, verify in-memory
Phase B4: Extract T-IMAGE via QEMU monitor, assemble bootable image,
          boot in fresh QEMU, verify Forth interpreter works.

This test manages its own QEMU instances (builder + booted).

Usage:
    python3 tests/test_meta_boot.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os
import signal

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4510
MON_PORT = PORT + 1
BOOT_PORT = PORT + 2

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
BUILD_DIR = os.path.join(PROJECT_DIR, 'build')
IMAGE = os.path.join(BUILD_DIR, 'bmforth.img')
BLOCKS = os.path.join(BUILD_DIR, 'blocks.img')
BOOT_BIN = os.path.join(BUILD_DIR, 'boot.bin')
KERNEL_BIN = os.path.join(BUILD_DIR, 'kernel.bin')
META_KERNEL = '/tmp/forthos-meta-B4.bin'
META_IMAGE = os.path.join(BUILD_DIR, 'meta-boot.img')

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


def connect(port, timeout=10, retries=20):
    """Connect to QEMU serial or monitor port."""
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


def mon_send(s, cmd, wait=1.0):
    """Send QEMU monitor command and collect response."""
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


def drain(s, wait=2.0):
    """Drain any pending data from socket."""
    s.settimeout(wait)
    try:
        while True:
            d = s.recv(4096)
            if not d:
                break
    except Exception:
        pass


def kill_qemu(port_pattern):
    """Kill QEMU instances matching a port pattern."""
    subprocess.run(
        ['pkill', '-9', '-f', f'[q]emu.*{port_pattern}'],
        capture_output=True)
    time.sleep(1)


def launch_builder():
    """Launch builder QEMU with serial + monitor ports."""
    cmd = [
        QEMU,
        '-drive', f'file={IMAGE},format=raw,if=floppy',
        '-drive', f'file={BLOCKS},format=raw,if=ide,index=1',
        '-serial', f'tcp::{PORT},server=on,wait=off',
        '-monitor', f'tcp::{MON_PORT},server=on,wait=off',
        '-display', 'none',
        '-daemonize',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAIL: Could not launch builder QEMU: "
              f"{result.stderr.strip()}")
        sys.exit(1)


def launch_booted():
    """Launch QEMU from the metacompiled image."""
    cmd = [
        QEMU,
        '-drive', f'file={META_IMAGE},format=raw,if=floppy',
        '-serial', f'tcp::{BOOT_PORT},server=on,wait=off',
        '-display', 'none',
        '-daemonize',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAIL: Could not launch booted QEMU: "
              f"{result.stderr.strip()}")
        return False
    return True


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
    """Kill all QEMU instances we might have started."""
    kill_qemu(str(PORT))
    kill_qemu(str(MON_PORT))
    kill_qemu(str(BOOT_PORT))
    if os.path.exists(META_KERNEL):
        os.unlink(META_KERNEL)


# ============================================================
# Preflight checks
# ============================================================

for f in [IMAGE, BLOCKS, BOOT_BIN, KERNEL_BIN]:
    if not os.path.exists(f):
        print(f"FAIL: Missing {f} -- run 'make && make blocks"
              " && make write-catalog' first")
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

# Kill any stale QEMU on our ports
cleanup()

# ============================================================
# Phase B3: In-memory kernel copy verification
# ============================================================

print("\n=== Phase B3: In-Memory Verification ===")

# Launch builder QEMU
print("\nStep 1: Launch builder QEMU")
launch_builder()
time.sleep(2)

s = connect(PORT)
if not s:
    print("FAIL: Cannot connect to builder serial")
    cleanup()
    sys.exit(1)

drain(s)

# Load vocabularies
print("\nStep 2: Load vocabularies")
send(s, f'{ASM_S} {ASM_E} THRU', 10)
send(s, f'{MC_S} {MC_E} THRU', 10)
r = send(s, f'{TX_S} {TX_E} THRU', 10)
ok = 'ok' in r
check('Vocabs loaded', ok, r.strip()[:60])
send(s, 'USING TARGET-X86', 2)
send(s, 'ALSO META-COMPILER', 2)

# META-COPY-KERNEL
print("\nStep 3: Copy kernel via T-BINARY,")
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

# Spot check: compare 16 byte positions
print("\nStep 4: Verify copy integrity (spot checks)")
offsets = [
    0, 1, 2, 3,
    0x100, 0x200,
    0x1000, 0x2000,
    0x5000, 0x7000,
    0x8000, 0x9000,
    0xC000, 0xE000,
    0xFFFC, 0xFFFD,
]

mismatches = 0
for off in offsets:
    addr = 0x7E00 + off
    r = send(s, f'HEX {addr:X} C@ DECIMAL .', 1)
    orig = extract_number(r)
    r = send(s, f'HEX {addr:X} T-C@ DECIMAL .', 1)
    copy = extract_number(r)
    if orig != copy:
        mismatches += 1
        print(f"  MISMATCH at 0x{off:X}:"
              f" orig={orig} copy={copy}")

check(f'Spot check {len(offsets)} bytes',
      mismatches == 0,
      f'{mismatches} mismatches')

# Extended: every 1KB boundary
print("\nStep 5: Extended comparison (64 bytes)")
ext_off = list(range(0, 0x10000, 0x400))
ext_miss = 0
for off in ext_off:
    addr = 0x7E00 + off
    r = send(s, f'HEX {addr:X} C@ DECIMAL .', 1)
    orig = extract_number(r)
    r = send(s, f'HEX {addr:X} T-C@ DECIMAL .', 1)
    copy = extract_number(r)
    if orig != copy:
        ext_miss += 1
        if ext_miss <= 3:
            print(f"  0x{off:X}: {orig}!={copy}")
check(f'{len(ext_off)} byte spot check',
      ext_miss == 0,
      f'{ext_miss} mismatches')

# META-COMPILE-X86 dictionary size
print("\nStep 6: META-COMPILE-X86 dictionary")
r = send(s, 'META-COMPILE-X86', 10)
r = send(s, 'DECIMAL META-SIZE .', 1)
dict_size = extract_number(r)
print(f"  Dictionary-only image: {dict_size} bytes")
check('Dictionary builds successfully',
      dict_size is not None and dict_size > 2000,
      f'got {dict_size}')

# Host kernel still works
print("\nStep 7: Host kernel still operational")
r = send(s, '3 4 + .', 2)
check('3 4 + . = 7', '7' in r, r.strip()[:40])

r = send(s, ': SQ DUP * ; 5 SQ .', 3)
check('5 SQ . = 25', '25' in r, r.strip()[:40])

r = send(s, '.S', 1)
check('Stack clean', '<>' in r, r.strip()[:60])

# ============================================================
# Phase B4: Extract, assemble, boot
# ============================================================

print("\n=== Phase B4: Extract + Boot ===")

# Re-run META-COPY-KERNEL for a clean 64KB image
print("\nStep 8: Prepare extraction image")
r = send(s, 'META-COPY-KERNEL', 30)
check('Fresh META-COPY-KERNEL',
      'bytes' in r.lower(),
      r.strip()[:60])

# Get T-IMAGE address via META-SAVE
print("\nStep 9: Extract via QEMU monitor")
r = send(s, 'META-SAVE', 2)
print(f"  META-SAVE output: {r.strip()!r}")

# Parse address and size from "META-SAVE: <addr> <size> bytes"
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
      meta_addr is not None and meta_size == 65536,
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

# Drain monitor greeting
drain(mon, wait=1)

# Remove stale extraction file
if os.path.exists(META_KERNEL):
    os.unlink(META_KERNEL)

# pmemsave: dump T-IMAGE from guest physical memory
cmd = f'pmemsave {meta_addr} {meta_size} "{META_KERNEL}"'
print(f"  Monitor cmd: {cmd}")
r = mon_send(mon, cmd, wait=2)

# Verify extracted file
extracted_ok = (os.path.exists(META_KERNEL) and
                os.path.getsize(META_KERNEL) == 65536)
check('pmemsave extracts 65536 bytes',
      extracted_ok,
      f'exists={os.path.exists(META_KERNEL)}, '
      f'size={os.path.getsize(META_KERNEL) if os.path.exists(META_KERNEL) else 0}')

if not extracted_ok:
    print("FAIL: Extraction failed, cannot proceed")
    s.close()
    mon.close()
    cleanup()
    sys.exit(1)

# Compare extracted bytes against build/kernel.bin
# NOTE: The running kernel modifies its data section after
# boot (cursor vars, tick count, keyboard buffer, etc.), so
# the code region should match but the data section may differ.
# The real proof is whether the extracted image boots.
with open(KERNEL_BIN, 'rb') as f:
    original = f.read()
with open(META_KERNEL, 'rb') as f:
    extracted = f.read()

# Compare first 0x2000 bytes (code region, immutable)
code_match = (original[:0x2000] == extracted[:0x2000])
if not code_match:
    for i in range(min(0x2000, len(original), len(extracted))):
        if original[i] != extracted[i]:
            print(f"  Code mismatch at 0x{i:X}: "
                  f"disk=0x{original[i]:02X}, "
                  f"extracted=0x{extracted[i]:02X}")
            break
check('Code region matches build/kernel.bin',
      code_match,
      f'orig={len(original)}, ext={len(extracted)}')

# Close builder connections
s.close()
mon.close()

# ============================================================
# Assemble bootable image
# ============================================================

print("\nStep 10: Assemble bootable image")
with open(BOOT_BIN, 'rb') as f:
    boot = f.read()
with open(META_KERNEL, 'rb') as f:
    kernel = f.read()

with open(META_IMAGE, 'wb') as f:
    f.write(boot + kernel)

img_size = os.path.getsize(META_IMAGE)
check(f'meta-boot.img assembled ({img_size} bytes)',
      img_size == 512 + 65536,
      f'expected {512 + 65536}, got {img_size}')

# ============================================================
# Kill builder, launch booted kernel
# ============================================================

print("\nStep 11: Boot metacompiled kernel")
kill_qemu(str(PORT))
time.sleep(1)

if not launch_booted():
    print("FAIL: Could not launch booted QEMU")
    cleanup()
    sys.exit(1)

time.sleep(2)

bs = connect(BOOT_PORT, timeout=10, retries=20)
check('Connection to booted kernel',
      bs is not None)

if bs is None:
    print("FAIL: Cannot connect to booted kernel")
    cleanup()
    sys.exit(1)

# Wait for boot + embedded vocab loading (9 vocabs)
# Then send a no-op to elicit an "ok" prompt
time.sleep(8)
drain(bs, wait=2)
r = send(bs, '', 3)
print(f"  Boot prompt: {r.strip()[:120]!r}")
check('ok prompt received',
      'ok' in r.lower(),
      r.strip()[:80])

# ============================================================
# Verify booted kernel functionality
# ============================================================

print("\nStep 12: Verify booted kernel")

r = send(bs, '3 4 + .', 2)
check('3 4 + . = 7', '7' in r, r.strip()[:40])

r = send(bs, ': SQ DUP * ; 5 SQ .', 3)
check('5 SQ . = 25', '25' in r, r.strip()[:40])

r = send(bs, '1 IF 42 ELSE 99 THEN .', 2)
check('IF/ELSE/THEN = 42', '42' in r, r.strip()[:40])

r = send(bs, 'WORDS', 3)
check('WORDS executes',
      len(r.strip()) > 20,
      f'len={len(r.strip())}')

bs.close()

# ============================================================
# Cleanup and summary
# ============================================================

kill_qemu(str(BOOT_PORT))
if os.path.exists(META_KERNEL):
    os.unlink(META_KERNEL)

print()
print(f'Passed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
