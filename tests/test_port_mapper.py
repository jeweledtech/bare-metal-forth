#!/usr/bin/env python3
"""Test PORT-MAPPER vocabulary: hardware I/O port discovery.
Requires HARDWARE vocab loaded first (dependency).
"""
import socket
import time
import sys
import subprocess
import os

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4750

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


# Load HARDWARE dependency first
hw_start, hw_end = get_vocab_blocks('HARDWARE')
if hw_start:
    print(f"\nPre-loading HARDWARE ({hw_start}-{hw_end} THRU)...")
    r = send(f'{hw_start} {hw_end} THRU', 10)
    ok = alive()
    check('HARDWARE loads', ok,
          f'response: {r.strip()[:80]!r}')
    if not ok:
        print("FAIL: Cannot continue without HARDWARE")
        s.close()
        sys.exit(1)
else:
    print("FAIL: HARDWARE not found in catalog")
    s.close()
    sys.exit(1)

# Load PORT-MAPPER
pm_start, pm_end = get_vocab_blocks('PORT-MAPPER')
if pm_start is None:
    print("FAIL: PORT-MAPPER not found in catalog")
    s.close()
    sys.exit(1)

print(f"\nLoading PORT-MAPPER ({pm_start}-{pm_end} THRU)...")
r = send(f'{pm_start} {pm_end} THRU', 10)
ok = alive()
check('PORT-MAPPER loads from blocks', ok,
      f'response: {r.strip()[:80]!r}')
if not ok:
    print("FAIL: System crashed loading PORT-MAPPER")
    s.close()
    sys.exit(1)

# Activate vocabulary
print("\nPORT-MAPPER word tests:")
r = send('USING PORT-MAPPER', 2)
ok = alive()
check('USING PORT-MAPPER succeeds', ok,
      f'response: {r.strip()[:80]!r}')

if ok:
    # PORT? on PIC1 (0x20) — always present in QEMU
    r = send('HEX 20 PORT? .', 1)
    check('PORT? on PIC1 (0x20) returns -1',
          '-1' in r, f'got: {r.strip()!r}')

    # PORT? on absent port (0x200) — game port, not in QEMU
    r = send('HEX 200 PORT? .', 1)
    check('PORT? on 0x200 executes without crash',
          alive(), f'got: {r.strip()!r}')

    # PORT. on PIC1 — should print address "0020"
    r = send('HEX 20 PORT.', 1)
    check('PORT. prints port address',
          '0020' in r, f'got: {r.strip()!r}')

    # PORT-SCAN small range — 0x20 to 0x21
    r = send('HEX 20 21 PORT-SCAN', 3)
    check('PORT-SCAN executes and finds ports',
          'ports found' in r,
          f'got: {r.strip()[:80]!r}')

    # PORT-ID on COM1 (0x3F8) — should identify
    r = send('HEX 3F8 PORT-ID', 2)
    check('PORT-ID identifies COM1 at 0x3F8',
          'COM1' in r, f'got: {r.strip()!r}')

    # PORT-ID on PIC1 (0x20) — should identify
    r = send('HEX 20 PORT-ID', 2)
    check('PORT-ID identifies PIC1 at 0x20',
          'PIC1' in r, f'got: {r.strip()!r}')

    # PIC-STATUS — should print PIC1 and PIC2
    r = send('PIC-STATUS', 2)
    check('PIC-STATUS prints PIC info',
          'PIC1' in r and 'PIC2' in r,
          f'got: {r.strip()[:80]!r}')

    # CMOS-DUMP — should print CMOS header
    r = send('CMOS-DUMP', 3)
    check('CMOS-DUMP executes without crash',
          'CMOS' in r, f'got: {r.strip()[:80]!r}')

    # PIT-STATUS — should print PIT info
    r = send('PIT-STATUS', 2)
    check('PIT-STATUS prints PIT info',
          'PIT' in r, f'got: {r.strip()!r}')

    r = send('DECIMAL', 1)

# Final check
print("\nFinal check:")
ok = alive()
check('System alive after all tests', ok)
if ok:
    r = send('.S', 1)
    check('Stack clean', '<>' in r,
          f'stack: {r.strip()!r}')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
