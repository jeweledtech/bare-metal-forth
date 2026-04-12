#!/usr/bin/env python3
"""
test_graphics.py — Smoke test for GRAPHICS vocabulary.

Tests Mode 13h pixel primitives, DAC palette access,
VBE version, VSYNC, TAQOZ words. Requires VGA-GRAPHICS
dependency to be loaded first.

Usage: python3 tests/test_graphics.py [port]
"""

import socket
import sys
import time
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4560
passed = 0
failed = 0

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))


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


def send(sock, cmd, timeout=3):
    sock.sendall((cmd + '\r').encode())
    time.sleep(timeout)
    try:
        return sock.recv(4096).decode('ascii',
                                      errors='replace')
    except socket.timeout:
        return ''


def check(name, cond, detail=''):
    global passed, failed
    if cond:
        passed += 1
        print(f'  PASS: {name}')
    else:
        failed += 1
        msg = f'  FAIL: {name}'
        if detail:
            msg += f' -- {detail}'
        print(msg)


# ---- Resolve block ranges ----
VG_S, VG_E = get_vocab_blocks('VGA-GRAPHICS')
GR_S, GR_E = get_vocab_blocks('GRAPHICS')
PE_S, PE_E = get_vocab_blocks('PCI-ENUM')
if GR_S is None:
    print("FAIL: GRAPHICS not in catalog")
    sys.exit(1)
if VG_S is None:
    print("FAIL: VGA-GRAPHICS not in catalog")
    sys.exit(1)
if PE_S is None:
    print("FAIL: PCI-ENUM not in catalog")
    sys.exit(1)

print(f"GRAPHICS test (port {PORT})")
print("=" * 50)
print(f"PCI-ENUM: {PE_S}-{PE_E}")
print(f"VGA-GRAPHICS: {VG_S}-{VG_E}")
print(f"GRAPHICS: {GR_S}-{GR_E}")

# ---- Connect ----
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
except:
    pass

# ---- Load dependencies then GRAPHICS ----
print(f"\nLoading PCI-ENUM ({PE_S} {PE_E} THRU)...")
r = send(s, f'{PE_S} {PE_E} THRU', 8)

print(f"Loading VGA-GRAPHICS ({VG_S} {VG_E} THRU)...")
r = send(s, f'{VG_S} {VG_E} THRU', 8)

print(f"Loading GRAPHICS ({GR_S} {GR_E} THRU)...")
r = send(s, f'{GR_S} {GR_E} THRU', 8)

# ---- Test 1: Load without errors ----
print("\nTest 1: GRAPHICS loads")
check('GRAPHICS loads without errors',
      '?' not in r,
      f'{r.strip()[:60]!r}')

# ---- Test 2: USING GRAPHICS ----
print("\nTest 2: USING adds to search order")
# Need both VGA-GRAPHICS (VBE words) and GRAPHICS
r = send(s, 'USING VGA-GRAPHICS', 1)
r = send(s, 'ALSO GRAPHICS ORDER', 2)
check('GRAPHICS in search order',
      'GRAPHICS' in r.upper(),
      f'{r.strip()[:60]!r}')

# ---- Test 3: VGA DAC constant ----
print("\nTest 3: VGA DAC constant")
r = send(s, 'HEX VGA-DAC-WRIDX . DECIMAL', 1)
check('VGA-DAC-WRIDX = 3C8',
      '3C8' in r.upper(),
      f'{r.strip()!r}')

# ---- Test 4: GFX-ADDR computation ----
print("\nTest 4: GFX-ADDR math")
# GFX-ADDR(5, 1) = A0000 + 320 + 5 = A0145
r = send(s, 'HEX 5 1 GFX-ADDR . DECIMAL', 1)
check('GFX-ADDR(5,1) = A0145',
      'A0145' in r.upper(),
      f'{r.strip()!r}')

# ---- Test 5: VBE version readable ----
print("\nTest 5: VBE version")
r = send(s, 'HEX VBE-ID VBE@ . DECIMAL', 1)
# Bochs VBE returns 0xB0C0-0xB0C5
check('VBE version readable (B0C*)',
      'B0C' in r.upper(),
      f'{r.strip()!r}')

# ---- Test 6: PAL! + PAL@ round-trip ----
print("\nTest 6: Palette round-trip")
# Write entry 1: R=63(3F) G=0 B=0
r = send(s, 'HEX 3F 0 0 1 PAL!', 1)
# Read it back
r = send(s, '1 PAL@ . . . DECIMAL', 1)
# Stack has (r g b) with b on top, so . prints b g r
# Expect: 0 0 63 (or in hex: 0 0 3F)
check('PAL round-trip reads back 3F',
      '3F' in r.upper() or '63' in r,
      f'{r.strip()!r}')

# ---- Test 7: Search order clean after load ----
print("\nTest 7: Clean search order")
r = send(s, 'ONLY FORTH ORDER', 1)
check('ONLY FORTH resets order',
      'ok' in r.lower(),
      f'{r.strip()!r}')
# Re-enable for remaining tests
send(s, 'USING VGA-GRAPHICS', 1)
send(s, 'ALSO GRAPHICS', 1)

# ---- Test 8: VSYNC-WAIT exists ----
print("\nTest 8: VSYNC-WAIT exists")
r = send(s, "' VSYNC-WAIT . DECIMAL", 1)
check('VSYNC-WAIT findable',
      '?' not in r and 'ok' in r.lower(),
      f'{r.strip()!r}')

# ---- Test 9: !POST / !TVOFF toggle ----
print("\nTest 9: !POST / !TVOFF")
send(s, '!POST', 1)
r = send(s, 'GFX-ACTIVE @ .', 1)
post_ok = '1' in r
send(s, '!TVOFF', 1)
r = send(s, 'GFX-ACTIVE @ .', 1)
tvoff_ok = '0' in r
check('!POST sets GFX-ACTIVE=1',
      post_ok, f'{r.strip()!r}')
check('!TVOFF sets GFX-ACTIVE=0',
      tvoff_ok, f'{r.strip()!r}')

# ---- Test 10: Stack clean ----
print("\nTest 10: Stack clean")
r = send(s, '.S', 1)
check('Stack clean after all tests',
      '<>' in r,
      f'{r.strip()!r}')

# ---- Summary ----
print()
print(f'Passed: {passed}/{passed + failed}')
s.close()
sys.exit(0 if failed == 0 else 1)
