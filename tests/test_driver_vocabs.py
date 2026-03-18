#!/usr/bin/env python3
"""Test that driver vocabs load from blocks without crash.
Tests HARDWARE, SERIAL-16550, RTL8139, PS2-KEYBOARD, PS2-MOUSE, NE2000.
Requires QEMU -nic model=ne2k_pci for NE2000 PCI discovery tests.
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4513

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))


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
except Exception:
    pass


def send(cmd, wait=1.0):
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


def alive():
    r = send('1 2 + .', 1)
    return '3' in r


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


# Vocabs to test (order matters: dependencies first)
vocabs_to_test = [
    'HARDWARE',
    'SERIAL-16550',
    'PS2-KEYBOARD',
    'PS2-MOUSE',
    'NE2000',
    'RTL8139',
]

# RTL8139 and NE2000 need PCI-ENUM loaded first
# HARDWARE uses kernel INB/OUTB directly (no deps)

# Load PCI-ENUM first (needed by RTL8139)
pci_start, pci_end = get_vocab_blocks('PCI-ENUM')
if pci_start:
    print(f"\nPre-loading PCI-ENUM ({pci_start}-{pci_end} THRU)...")
    r = send(f'{pci_start} {pci_end} THRU', 10)
    ok = alive()
    check('PCI-ENUM loads', ok,
          f'response: {r.strip()[:80]!r}')
    if not ok:
        print("FAIL: Cannot continue without PCI-ENUM")
        sys.exit(1)

# PCI-ENUM word-level tests
print("\nPCI-ENUM word tests:")
r = send('USING PCI-ENUM', 2)
ok = alive()
check('USING PCI-ENUM succeeds', ok,
      f'response: {r.strip()[:80]!r}')

if ok:
    # Verify PCI config port constants (HEX mode)
    r = send('HEX PCI-APORT .', 1)
    check('PCI-APORT = CF8', 'CF8' in r.upper(),
          f'got: {r.strip()!r}')
    r = send('PCI-DPORT .', 1)
    check('PCI-DPORT = CFC', 'CFC' in r.upper(),
          f'got: {r.strip()!r}')

    # PCI-SCAN ran on vocab load — check device count
    r = send('DECIMAL PCI-COUNT @ .', 1)
    nums = [int(w) for w in r.split()
            if w.lstrip('-').isdigit()]
    has_devs = any(n > 0 for n in nums) if nums else False
    check('PCI-COUNT > 0 (QEMU devices found)',
          has_devs, f'got: {r.strip()!r}')

    # PCI-LIST runs and produces device table output
    r = send('HEX PCI-LIST', 3)
    check('PCI-LIST executes without crash',
          alive(), f'got: {r.strip()[:80]!r}')
    check('PCI-LIST shows device table',
          'Vend' in r or 'devices' in r,
          f'got: {r.strip()[:100]!r}')

    # PCI-FIND for i440FX host bridge (always in QEMU)
    r = send('8086 1237 PCI-FIND DECIMAL .', 2)
    found = '-1' in r
    check('PCI-FIND 8086:1237 (i440FX) found',
          found, f'got: {r.strip()!r}')
    if found:
        # Stack has bus dev func — print and verify
        r = send('. . .', 1)
        check('i440FX at bus 0 dev 0',
              '0' in r, f'got: {r.strip()!r}')
    r = send('DECIMAL FORTH', 1)

for name in vocabs_to_test:
    start, end = get_vocab_blocks(name)
    if start is None:
        print(f"  SKIP: {name} (not in catalog)")
        continue
    print(f"\nLoading {name} ({start}-{end} THRU)...")
    r = send(f'{start} {end} THRU', 10)
    ok = alive()
    check(f'{name} loads without crash', ok,
          f'response: {r.strip()[:80]!r}')
    if not ok:
        print(f"  System crashed! Stopping.")
        break

# PS2-MOUSE specific tests
print("\nPS2-MOUSE word tests:")
r = send('USING PS2-MOUSE', 2)
ok = alive()
check('USING PS2-MOUSE succeeds', ok,
      f'response: {r.strip()[:80]!r}')

if ok:
    # Verify constants have correct hex values
    r = send('HEX DEFAULT-XMAX .', 1)
    check('DEFAULT-XMAX = 280h (640d)', '280' in r,
          f'got: {r.strip()!r}')
    r = send('DEFAULT-YMAX .', 1)
    check('DEFAULT-YMAX = 1E0h (480d)', '1E0' in r,
          f'got: {r.strip()!r}')
    r = send('MOUSE-IRQ .', 1)
    check('MOUSE-IRQ = C (12d)', 'C' in r,
          f'got: {r.strip()!r}')
    # Verify kernel var access works
    r = send('MOUSE-X-VAR @ .', 1)
    check('MOUSE-X-VAR readable', '0' in r,
          f'got: {r.strip()!r}')
    r = send('MOUSE-XY . .', 1)
    check('MOUSE-XY returns two values', '0' in r,
          f'got: {r.strip()!r}')
    r = send('DECIMAL', 1)

# NE2000 specific tests (requires QEMU -nic model=ne2k_pci)
print("\nNE2000 word tests:")
r = send('USING NE2000', 2)
ok = alive()
check('USING NE2000 succeeds', ok,
      f'response: {r.strip()[:80]!r}')

if ok:
    # Register offset constants (HEX mode)
    r = send('HEX NE-CMD .', 1)
    check('NE-CMD = 0', '0 ' in r or r.strip().endswith('0'),
          f'got: {r.strip()!r}')
    r = send('NE-DATA .', 1)
    check('NE-DATA = 10', '10' in r,
          f'got: {r.strip()!r}')
    r = send('NE-RESET .', 1)
    check('NE-RESET = 1F', '1F' in r.upper(),
          f'got: {r.strip()!r}')

    # Command bits
    r = send('CMD-STOP .', 1)
    check('CMD-STOP = 1', '1 ' in r or r.strip().endswith('1'),
          f'got: {r.strip()!r}')
    r = send('CMD-START .', 1)
    check('CMD-START = 2', '2 ' in r or r.strip().endswith('2'),
          f'got: {r.strip()!r}')

    # NIC memory layout (QEMU PMEM boundary)
    r = send('RX-START .', 1)
    check('RX-START = 46', '46' in r,
          f'got: {r.strip()!r}')
    r = send('TX-START .', 1)
    check('TX-START = 40', '40' in r,
          f'got: {r.strip()!r}')

    # NE2K-INIT should find RTL8029 via PCI (10EC:8029)
    r = send('NE2K-INIT', 5)
    found = 'NE2000 at' in r
    check('NE2K-INIT finds NIC via PCI',
          found, f'got: {r.strip()[:100]!r}')

    if found:
        # NE-BASE should be nonzero (PCI BAR0)
        r = send('NE-BASE @ .', 1)
        nums = [w for w in r.split() if w.strip()
                and all(c in '0123456789ABCDEFabcdef'
                        for c in w.strip())]
        has_base = any(int(n, 16) > 0 for n in nums) if nums else False
        check('NE-BASE nonzero (PCI BAR0)',
              has_base, f'got: {r.strip()!r}')

        # NE2K-MAC. should print without crash
        r = send('NE2K-MAC.', 2)
        check('NE2K-MAC. executes',
              alive(), f'got: {r.strip()[:80]!r}')

        # Statistics should show 0 TX/RX
        r = send('DECIMAL NE2K-STATS', 2)
        check('NE2K-STATS shows TX: 0',
              'TX:' in r and '0' in r,
              f'got: {r.strip()!r}')
    else:
        # NIC not on PCI bus (no -nic model=ne2k_pci)
        print('  SKIP: NE2K-INIT hardware tests '
              '(NIC not on PCI bus)')
    r = send('DECIMAL', 1)

# Final check
print("\nFinal check:")
ok = alive()
check('System alive after all loads', ok)
if ok:
    r = send('.S', 1)
    check('Stack clean', '<>' in r,
          f'stack: {r.strip()!r}')
    # Check WORDS shows our vocabs
    r = send('ORDER', 2)
    print(f'  ORDER: {r.strip()!r}')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
