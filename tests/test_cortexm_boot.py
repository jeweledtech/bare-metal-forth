#!/usr/bin/env python3
"""Test Cortex-M33 Phase C: boot on QEMU MPS2-AN505.

Phase 1: Build Cortex-M kernel on x86 via metacompiler
Phase 2: Extract binary via QEMU monitor pmemsave
Phase 3: Boot on qemu-system-arm mps2-an505
Phase 4: Verify Forth interpreter works

Usage:
    python3 tests/test_cortexm_boot.py [PORT]
"""
import socket
import time
import sys
import subprocess
import os
import shutil

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4594
MON_PORT = PORT + 1
BOOT_PORT = PORT + 2

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
BUILD_DIR = os.path.join(PROJECT_DIR, 'build')
COMBINED = os.path.join(BUILD_DIR, 'combined.img')
COMBINED_IDE = os.path.join(BUILD_DIR, 'combined-ide.img')
CM_KERNEL = '/tmp/forthos-cortexm.bin'

QEMU_X86 = 'qemu-system-i386'
QEMU_ARM = 'qemu-system-arm'


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
    sk = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sk.settimeout(timeout)
    for attempt in range(retries):
        try:
            sk.connect(('127.0.0.1', port))
            return sk
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return None


def send(sk, cmd, wait=1.0):
    sk.sendall((cmd + '\r').encode())
    time.sleep(wait)
    sk.settimeout(2)
    resp = b''
    while True:
        try:
            d = sk.recv(4096)
            if not d:
                break
            resp += d
        except Exception:
            break
    return resp.decode('ascii', errors='replace')


def mon_send(sk, cmd, wait=1.0):
    sk.sendall((cmd + '\n').encode())
    time.sleep(wait)
    sk.settimeout(2)
    resp = b''
    while True:
        try:
            d = sk.recv(4096)
            if not d:
                break
            resp += d
        except Exception:
            break
    return resp.decode('ascii', errors='replace')


def drain(sk, wait=2.0):
    sk.settimeout(wait)
    try:
        while True:
            d = sk.recv(4096)
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


def extract_number(text):
    words = text.replace('\r', ' ').replace(
        '\n', ' ').split()
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


def cleanup():
    kill_qemu(str(PORT))
    kill_qemu(str(BOOT_PORT))
    if os.path.exists(CM_KERNEL):
        os.unlink(CM_KERNEL)


# ============================================
# Preflight
# ============================================
for f in [COMBINED, COMBINED_IDE]:
    if not os.path.exists(f):
        print(f"FAIL: Missing {f}")
        sys.exit(1)

if not shutil.which(QEMU_ARM):
    print(f"SKIP: {QEMU_ARM} not installed")
    sys.exit(0)

# Get vocab blocks
vocabs = ['X86-ASM', 'META-COMPILER',
          'THUMB2-ASM', 'TARGET-CORTEX-M']
vblocks = {}
for v in vocabs:
    s, e = get_vocab_blocks(v)
    if s is None:
        print(f"FAIL: {v} not in catalog")
        sys.exit(1)
    vblocks[v] = (s, e)

# ============================================
# Phase 1: Build Cortex-M kernel on x86
# ============================================
print('\n--- Phase 1: Build on x86 ---')

kill_qemu(str(PORT))
subprocess.run([
    QEMU_X86,
    '-drive', f'file={COMBINED},format=raw,if=floppy',
    '-drive',
    f'file={COMBINED_IDE},format=raw,if=ide,index=1',
    '-serial',
    f'tcp::{PORT},server=on,wait=off',
    '-monitor',
    f'tcp::{MON_PORT},server=on,wait=off',
    '-display', 'none', '-daemonize'
], capture_output=True)

sx = connect(PORT)
if not sx:
    print("FAIL: Could not connect to x86 QEMU")
    cleanup()
    sys.exit(1)

drain(sx)

# Load vocabs in order
for v in vocabs:
    sb, eb = vblocks[v]
    print(f'  Loading {v} ({sb}-{eb})...')
    send(sx, f'DECIMAL {sb} {eb} THRU', 15)

alive = '3' in send(sx, '1 2 + .', 1)
check('All vocabs loaded on x86', alive)

if not alive:
    cleanup()
    sx.close()
    print(f'\nPassed: {PASS}/{PASS + FAIL}')
    sys.exit(1)

# Run full metacompile
print('  Running META-COMPILE-CORTEXM-BOOT...')
r = send(sx, 'META-COMPILE-CORTEXM-BOOT', 60)
print(f'  MC output: {r.strip()[:200]!r}')

alive = '3' in send(sx, '1 2 + .', 1)
check('META-COMPILE-CORTEXM-BOOT done', alive)

# Get image size
r = send(sx, 'META-SIZE DECIMAL .', 1)
img_size = extract_number(r)
check('Image size > 0',
      img_size is not None and img_size > 0,
      f'got: {img_size}')

if img_size is None or img_size == 0:
    cleanup()
    sx.close()
    print(f'\nPassed: {PASS}/{PASS + FAIL}')
    sys.exit(1)

# ============================================
# Phase 2: Extract via monitor
# ============================================
print('\n--- Phase 2: Extract binary ---')

mon = connect(MON_PORT)
if not mon:
    print("FAIL: Could not connect to monitor")
    cleanup()
    sx.close()
    sys.exit(1)

drain(mon)

# T-IMAGE is a CREATE'd buffer in host memory
# Get its address
r = send(sx, 'HEX T-IMAGE DECIMAL .', 1)
img_addr = extract_number(r)
check('T-IMAGE address obtained',
      img_addr is not None and img_addr > 0,
      f'got: {img_addr}')

if img_addr and img_size:
    # pmemsave to extract
    if os.path.exists(CM_KERNEL):
        os.unlink(CM_KERNEL)
    cmd = f'pmemsave {img_addr} {img_size} {CM_KERNEL}'
    mon_send(mon, cmd, 3)
    time.sleep(2)
    exists = os.path.exists(CM_KERNEL)
    check('Kernel binary extracted', exists)
    if exists:
        actual = os.path.getsize(CM_KERNEL)
        check(f'Kernel size = {img_size}',
              actual == img_size,
              f'got: {actual}')

mon.close()
sx.close()
kill_qemu(str(PORT))

if not os.path.exists(CM_KERNEL):
    print("FAIL: No kernel to boot")
    cleanup()
    print(f'\nPassed: {PASS}/{PASS + FAIL}')
    sys.exit(1)

# ============================================
# Phase 3: Boot on Cortex-M33
# ============================================
print('\n--- Phase 3: Boot on MPS2-AN505 ---')

subprocess.run([
    QEMU_ARM,
    '-machine', 'mps2-an505',
    '-cpu', 'cortex-m33',
    '-kernel', CM_KERNEL,
    '-serial',
    f'tcp::{BOOT_PORT},server=on,wait=off',
    '-display', 'none',
    '-nographic',
    '-semihosting-config', 'enable=off'
], capture_output=True, start_new_session=True)

time.sleep(1)
# Daemonize doesn't work the same for ARM QEMU
# so we launched it as background process above
subprocess.Popen([
    QEMU_ARM,
    '-machine', 'mps2-an505',
    '-cpu', 'cortex-m33',
    '-kernel', CM_KERNEL,
    '-serial',
    f'tcp::{BOOT_PORT},server=on,wait=off',
    '-display', 'none', '-nographic'
], stdout=subprocess.DEVNULL,
   stderr=subprocess.DEVNULL)

sb = connect(BOOT_PORT, timeout=10, retries=30)
if not sb:
    print("FAIL: Could not connect to ARM QEMU")
    cleanup()
    print(f'\nPassed: {PASS}/{PASS + FAIL}')
    sys.exit(1)

drain(sb, 3)

# ============================================
# Phase 4: Verify Forth interpreter
# ============================================
print('\n--- Phase 4: Verify Forth ---')

# Test basic arithmetic
r = send(sb, '1 2 + .', 3)
check('1 2 + . = 3', '3' in r,
      f'got: {r.strip()[:80]!r}')

# Test WORDS
r = send(sb, 'WORDS', 3)
has_words = ('DROP' in r or 'DUP' in r
             or 'SWAP' in r)
check('WORDS shows dictionary', has_words,
      f'got: {r.strip()[:100]!r}')

# Test multiply
r = send(sb, '6 7 * .', 3)
check('6 7 * . = 42', '42' in r,
      f'got: {r.strip()[:80]!r}')

# Test colon definition
r = send(sb, ': DOUBLE DUP + ;', 3)
r = send(sb, '21 DOUBLE .', 3)
check('DOUBLE 21 = 42', '42' in r,
      f'got: {r.strip()[:80]!r}')

# Test HEX/DECIMAL
r = send(sb, 'HEX FF DECIMAL .', 3)
check('HEX FF = 255', '255' in r,
      f'got: {r.strip()[:80]!r}')

# System alive
alive = '3' in send(sb, '1 2 + .', 2)
check('System alive', alive)

sb.close()
cleanup()

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
