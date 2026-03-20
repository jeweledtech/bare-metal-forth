#!/usr/bin/env python3
"""Test NE2000 network communication between two
QEMU instances connected via socket backend.

Phases tested:
1. Raw frame send/receive
2. Single block transfer
3. Vocabulary transfer (PIT-TIMER)
"""
import socket
import time
import sys
import subprocess
import os

PORT_A = int(sys.argv[1]) if len(sys.argv) > 1 else 4750
PORT_B = PORT_A + 1
NET_PORT = PORT_A + 100  # socket backend port

PROJECT_DIR = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))
IMAGE = os.path.join(PROJECT_DIR, 'build', 'bmforth.img')
BLOCKS = os.path.join(PROJECT_DIR, 'build', 'blocks.img')
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


def start_qemu_pair(zero_range=None):
    """Start two QEMU instances with socket-paired NICs.
    Each needs its own copy of disk images (QEMU locks).
    zero_range: (first, last) block range to zero on B's
    disk before boot, so transfer tests are provable."""
    # Copy images for instance B
    image_b = IMAGE + '.b'
    blocks_b = BLOCKS + '.b'
    subprocess.run(['cp', IMAGE, image_b],
                   capture_output=True)
    subprocess.run(['cp', BLOCKS, blocks_b],
                   capture_output=True)
    # Zero target blocks on B's disk so transfer is provable
    if zero_range:
        first, last = zero_range
        with open(blocks_b, 'r+b') as f:
            for blk in range(first, last + 1):
                f.seek(blk * 1024)
                f.write(b'\x00' * 1024)

    # Instance A: listen side
    cmd_a = [
        QEMU,
        '-drive', f'file={IMAGE},format=raw,if=floppy',
        '-drive',
        f'file={BLOCKS},format=raw,if=ide,index=1',
        '-netdev', f'socket,id=net0,listen=:{NET_PORT}',
        '-device', 'ne2k_pci,netdev=net0',
        '-serial',
        f'tcp::{PORT_A},server=on,wait=off',
        '-display', 'none', '-daemonize'
    ]
    subprocess.run(cmd_a, capture_output=True)
    time.sleep(2)

    # Instance B: connect side
    cmd_b = [
        QEMU,
        '-drive',
        f'file={image_b},format=raw,if=floppy',
        '-drive',
        f'file={blocks_b},format=raw,if=ide,index=1',
        '-netdev',
        f'socket,id=net0,connect=127.0.0.1:{NET_PORT}',
        '-device', 'ne2k_pci,netdev=net0',
        '-serial',
        f'tcp::{PORT_B},server=on,wait=off',
        '-display', 'none', '-daemonize'
    ]
    subprocess.run(cmd_b, capture_output=True)
    time.sleep(2)
    return blocks_b


def connect(port):
    """Connect to QEMU serial port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(10)
    for attempt in range(20):
        try:
            s.connect(('127.0.0.1', port))
            break
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    else:
        return None
    time.sleep(2)
    try:
        while True:
            s.recv(4096)
    except Exception:
        pass
    return s


def send(sock, cmd, wait=1.0):
    sock.sendall((cmd + '\r').encode())
    time.sleep(wait)
    sock.settimeout(2)
    resp = b''
    while True:
        try:
            d = sock.recv(4096)
            if not d:
                break
            resp += d
        except Exception:
            break
    return resp.decode('ascii', errors='replace')


def alive(sock):
    r = send(sock, '1 2 + .', 1)
    return '3' in r


def wait_for(sock, target, timeout=30):
    """Poll socket until target string appears or timeout.
    Used for commands that block the Forth interpreter
    (e.g., NET-RECV polling loop)."""
    sock.settimeout(2)
    resp = b''
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            d = sock.recv(4096)
            if d:
                resp += d
                if target.encode() in resp:
                    return resp.decode('ascii',
                                       errors='replace')
        except socket.timeout:
            continue
        except Exception:
            break
    return resp.decode('ascii', errors='replace')


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


def cleanup():
    """Kill both QEMU instances and temp files."""
    subprocess.run(
        ['pkill', '-9', '-f',
         f'[q]emu.*{PORT_A}'],
        capture_output=True
    )
    subprocess.run(
        ['pkill', '-9', '-f',
         f'[q]emu.*{PORT_B}'],
        capture_output=True
    )
    for f in [BLOCKS + '.b', IMAGE + '.b']:
        if os.path.exists(f):
            os.unlink(f)


# --- Main ---
cleanup()
time.sleep(1)

# Get PIT-TIMER blocks early (needed for zeroing B's disk)
pit_s, pit_e = get_vocab_blocks('PIT-TIMER')

print("Starting QEMU pair...")
blocks_b = start_qemu_pair(
    zero_range=(pit_s, pit_e) if pit_s else None)

sa = connect(PORT_A)
sb = connect(PORT_B)
if sa is None or sb is None:
    print("FAIL: Could not connect to QEMU instances")
    cleanup()
    sys.exit(1)

check('Instance A alive', alive(sa))
check('Instance B alive', alive(sb))
if not alive(sa) or not alive(sb):
    print("Cannot continue without both instances.")
    cleanup()
    sys.exit(1)

# Find vocab blocks
pci_s, pci_e = get_vocab_blocks('PCI-ENUM')
ne_s, ne_e = get_vocab_blocks('NE2000')
nd_s, nd_e = get_vocab_blocks('NET-DICT')
# pit_s, pit_e already retrieved above (for zeroing)

if None in (pci_s, ne_s, nd_s, pit_s):
    print("FAIL: Could not find required vocab blocks")
    print(f"  PCI-ENUM: {pci_s}-{pci_e}")
    print(f"  NE2000: {ne_s}-{ne_e}")
    print(f"  NET-DICT: {nd_s}-{nd_e}")
    print(f"  PIT-TIMER: {pit_s}-{pit_e}")
    cleanup()
    sys.exit(1)

print(f"\nVocab blocks:")
print(f"  PCI-ENUM: {pci_s}-{pci_e}")
print(f"  NE2000: {ne_s}-{ne_e}")
print(f"  NET-DICT: {nd_s}-{nd_e}")
print(f"  PIT-TIMER: {pit_s}-{pit_e}")

# Load vocabs on both instances
print("\nLoading vocabs on both instances...")
for label, sock in [('A', sa), ('B', sb)]:
    r = send(sock, f'{pci_s} {pci_e} THRU', 10)
    ok = alive(sock)
    check(f'Instance {label}: PCI-ENUM loads', ok,
          f'{r.strip()[:80]!r}')
    if not ok:
        cleanup()
        sys.exit(1)

    r = send(sock, f'{ne_s} {ne_e} THRU', 10)
    ok = alive(sock)
    check(f'Instance {label}: NE2000 loads', ok,
          f'{r.strip()[:80]!r}')
    if not ok:
        cleanup()
        sys.exit(1)

    r = send(sock, f'{nd_s} {nd_e} THRU', 10)
    ok = alive(sock)
    check(f'Instance {label}: NET-DICT loads', ok,
          f'{r.strip()[:80]!r}')
    if not ok:
        cleanup()
        sys.exit(1)

# Init NIC on both
# Need NE2000 in search order for NE2K-INIT
# and NET-DICT for BLOCK-SEND/RECV
print("\nInitializing NICs...")
for label, sock in [('A', sa), ('B', sb)]:
    send(sock, 'ALSO NE2000', 2)
    r = send(sock, 'NE2K-INIT', 3)
    ok = 'NE2000 at' in r
    check(f'Instance {label}: NE2K-INIT', ok,
          f'{r.strip()[:80]!r}')
    send(sock, 'ALSO NET-DICT', 2)

# Test 1: MAC addresses are different
print("\nTest: MAC addresses")
r_a = send(sa, 'NE2K-MAC.', 2)
r_b = send(sb, 'NE2K-MAC.', 2)
check('Both have MAC addresses',
      'MAC' in r_a and 'MAC' in r_b,
      f'A={r_a.strip()!r} B={r_b.strip()!r}')

# Test 2: Single block transfer
# Write known data to block 900 on A
print("\nTest: Single block transfer")
# Write a marker value to block 900 on A
r = send(sa,
         'DECIMAL 900 BUFFER '
         'DUP 1024 66 FILL DROP UPDATE '
         'SAVE-BUFFERS HEX', 4)
ok = alive(sa)
check('A: wrote block 900', ok)

# Send block 900 from A
r = send(sa, 'DECIMAL 900 BLOCK-SEND HEX', 4)
ok_a = alive(sa)
check('A: BLOCK-SEND 900 completes', ok_a,
      f'{r.strip()[:120]!r}')

# Receive on B (poll with retries)
time.sleep(2)
got_900 = False
for attempt in range(10):
    r = send(sb, 'BLOCK-RECV DECIMAL . HEX', 2)
    if '900' in r:
        got_900 = True
        break
    time.sleep(0.5)
check('B: BLOCK-RECV returns 900',
      got_900,
      f'{r.strip()[:120]!r}')

if got_900:
    # Verify block content on B
    r = send(sb,
             'DECIMAL 900 BLOCK C@ . HEX', 3)
    check('B: block 900 first byte = 66',
          '66' in r,
          f'{r.strip()[:80]!r}')

# Test 3: Verify received block content
print("\nTest: Verify block content integrity")
if got_900:
    r = send(sb,
             'DECIMAL 900 BLOCK 500 + C@ . HEX',
             3)
    check('B: block 900 mid-byte = 66',
          '66' in r,
          f'{r.strip()[:80]!r}')

# Flush block caches on B before consecutive test
time.sleep(1)
send(sb, 'SAVE-BUFFERS EMPTY-BUFFERS', 3)
check('B alive between tests', alive(sb))
if not alive(sb):
    print("B crashed after single block test!")
    cleanup()
    sys.exit(1)

# Test: consecutive block transfers via BLOCK-RECV
print("\nTest: Consecutive block transfers")
consec_ok = True
for blk_num, fill_byte in [(902, 170), (903, 187),
                            (904, 204)]:
    # Write known pattern to block on A (decimal)
    r = send(sa,
             f'DECIMAL {blk_num} BUFFER '
             f'DUP 1024 {fill_byte} FILL '
             f'DROP UPDATE SAVE-BUFFERS HEX', 4)
    ok_w = alive(sa)
    check(f'A: wrote block {blk_num}', ok_w)
    if not ok_w:
        consec_ok = False
        break
    # Send block from A
    r = send(sa,
             f'DECIMAL {blk_num} BLOCK-SEND HEX', 4)
    ok_s = alive(sa)
    check(f'A: BLOCK-SEND {blk_num}', ok_s,
          f'{r.strip()[:80]!r}')
    if not ok_s:
        consec_ok = False
        break
    time.sleep(2)
    # Receive on B (poll with retries)
    got_blk = False
    for attempt in range(10):
        r = send(sb,
                 'BLOCK-RECV DECIMAL . HEX', 3)
        if str(blk_num) in r:
            got_blk = True
            break
        time.sleep(0.5)
    check(f'B: received block {blk_num}',
          got_blk, f'{r.strip()[:80]!r}')
    if not got_blk:
        consec_ok = False
        break
    # Verify content on B (output is decimal)
    r2 = send(sb,
              f'DECIMAL {blk_num} BLOCK C@ . HEX',
              2)
    check(f'B: block {blk_num} byte = {fill_byte}',
          str(fill_byte) in r2,
          f'{r2.strip()[:60]!r}')

check('A alive after consecutive transfers',
      alive(sa))
check('B alive after consecutive transfers',
      alive(sb) if consec_ok else False)

# ---- Multi-block vocabulary transfer ----
# Send PIT-TIMER (5 blocks) from A->B over network,
# compile on B, verify words work.
print("\nTest: Multi-block vocabulary transfer")
pit_count = pit_e - pit_s + 1

# Verify B's PIT-TIMER blocks are blank (we zeroed them)
r = send(sb,
         f'DECIMAL {pit_s} BLOCK C@ . HEX', 3)
check('B: PIT-TIMER blocks are blank',
      '0 ' in r or r.strip().endswith('0'),
      f'{r.strip()[:80]!r}')

# Send/receive all blocks, then bulk flush
recv_ok = True
for i in range(pit_count):
    blk = pit_s + i
    r = send(sa,
             f'DECIMAL {blk} BLOCK-SEND HEX', 3)
    ok = alive(sa)
    check(f'A: BLOCK-SEND {blk}', ok,
          f'{r.strip()[:80]!r}')
    if not ok:
        recv_ok = False
        break
    time.sleep(2)
    got = False
    for attempt in range(10):
        r = send(sb,
                 'BLOCK-RECV DECIMAL . HEX', 3)
        if str(blk) in r:
            got = True
            break
        time.sleep(0.5)
    check(f'B: received block {blk}',
          got, f'{r.strip()[:80]!r}')
    if not got:
        recv_ok = False
        break
send(sb, 'SAVE-BUFFERS EMPTY-BUFFERS', 3)
check('B: alive after transfer', alive(sb))

# Compile PIT-TIMER on B via THRU
r = send(sb,
         f'DECIMAL {pit_s} {pit_e} THRU HEX', 10)
check('B: THRU compiles PIT-TIMER', alive(sb),
      f'{r.strip()[:80]!r}')

# Activate PIT-TIMER vocab on B
send(sb, 'ALSO PIT-TIMER', 2)

# Verify PIT-TIMER constants
r = send(sb, 'PIT-CH0 .', 2)
check('B: PIT-CH0 = 40h',
      '40 ' in r or r.strip().endswith('40'),
      f'{r.strip()[:80]!r}')

r = send(sb, 'PIT-CMD .', 2)
check('B: PIT-CMD = 43h',
      '43 ' in r or r.strip().endswith('43'),
      f'{r.strip()[:80]!r}')

r = send(sb, 'DECIMAL PIT-FREQ . HEX', 2)
check('B: PIT-FREQ = 1193182',
      '1193182' in r,
      f'{r.strip()[:80]!r}')

# Hardware test: PIT-READ returns a value (no error)
r = send(sb, 'PIT-READ .', 2)
check('B: PIT-READ works',
      '?' not in r and len(r.strip()) > 0,
      f'{r.strip()[:80]!r}')

check('A alive after vocab transfer', alive(sa))
check('B alive after vocab transfer', alive(sb))

# Final: both instances still alive
print("\nFinal checks:")
check('A alive after all tests', alive(sa))
check('B alive after all tests', alive(sb))

print(f'\nPassed: {PASS}/{PASS + FAIL}')

cleanup()
sys.exit(0 if FAIL == 0 else 1)
