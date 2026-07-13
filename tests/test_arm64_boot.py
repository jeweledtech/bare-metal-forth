#!/usr/bin/env python3
"""Test ARM64 Phase C: boot ForthOS on QEMU virt.

Builds an ARM64 kernel image via metacompiler on x86,
extracts via QEMU monitor, boots on qemu-system-aarch64
virt machine, and verifies interactive Forth works.

The virt machine's PL011 UART has reliable TCP serial,
unlike raspi3b which had RX delivery problems.

Usage:
    python3 tests/test_arm64_boot.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os
import re
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
    '-display', 'none',
]
builder_proc = subprocess.Popen(
    cmd,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL)

time.sleep(4)

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

r = send(s, f'{MC_S} {MC_E} THRU', 30)
check('META-COMPILER loaded', '?' not in r,
      r.strip()[-60:])

r = send(s, f'{A64_S} {A64_E} THRU', 15)
check('ARM64-ASM loaded', '?' not in r,
      r.strip()[-60:])
check('MRS encoder KAT', 'MRS-KAT-FAIL' not in r,
      r.strip()[-60:])

r = send(s, f'{TA_S} {TA_E} THRU', 30)
check('TARGET-ARM64 loaded', '?' not in r,
      r.strip()[-60:])

send(s, 'USING TARGET-ARM64', 2)
send(s, 'ALSO META-COMPILER', 2)
send(s, 'ALSO ARM64-ASM', 2)

# Run BUILD-ARM64-VIRT (sets virt config then compiles)
print("\nRunning BUILD-ARM64-VIRT...")
r = send(s, 'BUILD-ARM64-VIRT', 60)
print(f"  Output: {r.strip()!r}")
check('BUILD-ARM64-VIRT completes',
      'ARM64 boot:' in r,
      r.strip()[:120])
check('No VBAR align fail', 'VBAR-ALIGN-FAIL' not in r,
      r.strip()[:120])
check('No stub overflow', 'VBAR-STUB-OVF' not in r,
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
# "Unresolved: " with nothing on that line = success
r = send(s, 'META-CHECK', 2)
unresolved = re.findall(r'Unresolved:[ \t]*(\S+)', r)
check('No unresolved refs',
      len(unresolved) == 0, r.strip()[:80])

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
    img_data = f.read(512)
first_word = int.from_bytes(img_data[:4], 'little')
check(f'First instruction non-zero (0x{first_word:08X})',
      first_word != 0)

# DUMP-verify: scan for MOV32 immediates that should
# encode 0x4xxxxxxx addresses (virt-config values).
# ARM64 MOV32 is MOVZ Wd,#lo16 + MOVK Wd,#hi16,hw=1.
# MOVK hw=1 has bits [22:21]=01 (shift=16).
# Check the image contains at least one 0x40xx MOVK
# (PSP=0x40040000, RSP=0x40050000, UART=0x09000000).
print("\n  Image header (first 32 bytes):")
for off in range(0, min(32, len(img_data)), 4):
    w = int.from_bytes(img_data[off:off+4], 'little')
    print(f"    +{off:02X}: 0x{w:08X}")

# Look for MOVK with hi16 containing virt-config
# addresses (must match VIRT-CONFIG in target-arm64.fth:
# ORG=0x40100000, PSP=0x40140000, RSP=0x40150000,
# SYSVARS=0x40120000, UART=0x09000000)
found_virt_addr = False
for off in range(0, len(img_data) - 3, 4):
    w = int.from_bytes(img_data[off:off+4], 'little')
    # MOVK Wd,#imm16,LSL#16: opc=11 hw=01
    if (w & 0xFFE00000) == 0x72A00000:
        imm16 = (w >> 5) & 0xFFFF
        if imm16 in (0x4014, 0x4015, 0x0900,
                      0x4012, 0x4010):
            found_virt_addr = True
            rd = w & 0x1F
            print(f"    MOVK W{rd},#0x{imm16:04X},"
                  f"LSL#16 at +{off:02X}")
check('Image contains virt-config addresses',
      found_virt_addr)

s.close()
mon.close()

# ============================================================
# Phase 3: ARM64 Boot (virt)
# ============================================================

print("\n=== Phase 3: ARM64 Boot (virt) ===")

kill_qemu(str(PORT))
time.sleep(1)

# Must match A64-ORG in VIRT-CONFIG (target-arm64.fth).
# 0x40100000 clears virt machine's DTB at 0x40000000-
# 0x40100000. Generic loader forces exact address,
# avoiding -kernel header detection heuristics.
LOAD_ADDR = '0x40100000'

boot_cmd = [
    QEMU_ARM64,
    '-M', 'virt', '-cpu', 'cortex-a57',
    '-m', '256M',
    '-device', f'loader,file={ARM64_KERNEL},'
               f'addr={LOAD_ADDR}',
    '-device', f'loader,addr={LOAD_ADDR},cpu-num=0',
    '-serial',
    f'tcp::{BOOT_PORT},server=on,wait=on,nodelay=on',
    '-display', 'none',
]
print(f"  CMD: {' '.join(boot_cmd)}")

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
time.sleep(3)
drain(bs, wait=2)

r = send(bs, '', 5)
print(f"  Boot output: {r.strip()[:120]!r}")

if 'ok' not in r.lower():
    r = send(bs, '', 5)
    print(f"  Retry: {r.strip()[:120]!r}")

check('ok prompt', 'ok' in r.lower(), r.strip()[:80])

# ============================================================
# Phase 4: Functional verification
# ============================================================

print("\n=== Phase 4: Verify ===")

# Continue using the same session from Phase 3
# (virt PL011 has reliable TCP serial)
send(bs, 'DECIMAL', 2)


def resp_after_echo(full, cmd):
    """Extract response text after the echoed command."""
    i = full.find(cmd)
    if i >= 0:
        return full[i + len(cmd):]
    return full


def has_word(text, word):
    """Word-boundary match — '7' must not match '-37'.

    Uses \\b anchors so substring false positives
    (e.g. '7' in '-37') are eliminated.  See bug #33
    verification lesson: the Phase 4 '7 in r' check
    matched DOT's broken '-37' output, manufacturing
    a false-positive green.
    """
    return bool(re.search(r'\b' + re.escape(word)
                          + r'\b', text))


# ---- Arithmetic (bug #33c: DOT output broken) ----
# These checks use has_word() for anchored matching.
# Until #33c is fixed, DOT-dependent checks will FAIL.
r = send(bs, '3 4 + .', 3)
check('3 4 + . = 7', has_word(r, '7'),
      r.strip()[:60])

r = send(bs, '10 1 - .', 3)
check('10 1 - . = 9', has_word(r, '9'),
      r.strip()[:60])

r = send(bs, '6 7 * .', 3)
check('6 7 * . = 42', has_word(r, '42'),
      r.strip()[:60])

# Floored division
r = send(bs, '-7 3 / .', 3)
check('-7 3 / . = -3 (floored)',
      has_word(r, '-3'),
      r.strip()[:60])

# Colon definition
r = send(bs, ': SQ DUP * ;', 3)
r = send(bs, '7 SQ .', 3)
check(': SQ DUP * ; 7 SQ . = 49',
      has_word(r, '49'),
      r.strip()[:60])

# IF/ELSE/THEN
r = send(bs, '1 IF 42 ELSE 99 THEN .', 3)
check('IF true = 42', has_word(r, '42'),
      r.strip()[:60])

r = send(bs, '0 IF 42 ELSE 99 THEN .', 3)
check('IF false = 99', has_word(r, '99'),
      r.strip()[:60])

# DO/LOOP
r = send(bs, '5 0 DO I . LOOP', 3)
check('DO/LOOP',
      has_word(r, '0') and has_word(r, '4'),
      r.strip()[:60])

# Undefined word
r = send(bs, 'NOTAWORD', 3)
check('Undefined word -> ?', '?' in r,
      r.strip()[:60])

# HEX mode
r = send(bs, 'HEX FF DECIMAL .', 3)
check('HEX FF = 255', has_word(r, '255'),
      r.strip()[:60])

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
