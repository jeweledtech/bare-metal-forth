#!/usr/bin/env python3
"""CARRIER-0b fix, host-safety red: a cell-0 boot must NOT write blocks to a
fixed disk by default.

docs/evidence/carrier-0b-write-vector-2026-09-29.md + TASK_REMOVE_BOOT_CARRIER
§3a.1. On a non-memdisk (cell-0) boot the kernel used to arm (BLK-WRITE-ATA),
which writes block N to IDE-slave 0x1F0 LBA 225+2N with no guard — so a
SAVE-BUFFERS on a UEFI/installed machine whose SATA sits in IDE-compat mode
overwrites the host disk and reports ior=0. The fail-closed default is N1's
first half: cell-0 must arm (BLK-WRITE-NONE) so the write refuses loudly.

Fixture: bmforth.img on floppy (cell-0, no memdisk) + a scratch IDE disk
(primary slave, index=1) pre-filled with a sentinel at block 199's LBA (623).
The guest fills block 199 in a buffer, UPDATE, SAVE-BUFFERS. Host-safety check
(gate C5): the scratch sector at LBA 623 is UNCHANGED afterward.

  red  (default (BLK-WRITE-ATA)): SAVE-BUFFERS writes -> sentinel gone -> FAIL
  green (default (BLK-WRITE-NONE)): refuses -> sentinel intact -> PASS

While the name is in CARRIER_REDS: sentinel-clobbered = XFAIL (exit 0);
sentinel-intact = XPASS (exit 1, remove the red). After removal a clobber is
a plain FAIL.

usage: test_carrier_write_safe.py [serial-port]
"""
import os
import socket
import subprocess
import sys
import time

import qemu_pid  # tests/qemu_pid.py: pidfile-based QEMU cleanup

# red removed after its XPASS gate fired on exactly this name
# (fix-carrier0b-xpass-gate-2026-09-29.log); a clobber is now a plain FAIL.
CARRIER_REDS = []
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLOPPY = os.path.join(ROOT, 'build', 'bmforth.img')
SCRATCH = os.path.join(ROOT, 'build', 'carrier-write-scratch.img')
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4585
CARRIER_PIDFILE = qemu_pid.pidfile('carrier')
BLK = 199
LBA = 225 + 2 * BLK                 # 623: where block 199 would be written
SENTINEL = b'\x5a' * 512            # 0x5A, distinct from the guest's fill (0x41)


def die(code, msg):
    qemu_pid.kill_pidfile(CARRIER_PIDFILE)
    print(msg)
    sys.exit(code)


if not os.path.exists(FLOPPY):
    die(3, f'INSTRUMENT FAIL: {FLOPPY} missing — run make first')

# 2 MiB scratch IDE disk, sentinel at the block-199 sectors (LBA 623,624)
with open(SCRATCH, 'wb') as f:
    f.write(b'\x00' * (4096 * 512))
    f.seek(LBA * 512)
    f.write(SENTINEL + SENTINEL)

qemu_pid.kill_pidfile(CARRIER_PIDFILE)
q = subprocess.Popen(
    ['qemu-system-i386',
     '-drive', f'file={FLOPPY},format=raw,if=floppy,readonly=on',
     '-drive', f'file={SCRATCH},format=raw,if=ide,index=1',
     '-serial', f'tcp::{PORT},server=on,wait=off', '-display', 'none', '-no-reboot',
     '-pidfile', CARRIER_PIDFILE],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    s = None
    for _ in range(40):
        try:
            s = socket.create_connection(('127.0.0.1', PORT)); break
        except OSError:
            time.sleep(0.25)
    if not s:
        die(3, 'INSTRUMENT FAIL: serial never connected')
    s.settimeout(2)
    time.sleep(3)

    def cmd(c, t=1.5):
        s.sendall((c + '\r').encode()); time.sleep(t)
        b = b''
        while True:
            try:
                d = s.recv(65536)
                if not d: break
                b += d
            except socket.timeout:
                break
        return b.decode('latin-1')

    if '42' not in cmd('7 6 * .'):
        die(3, 'INSTRUMENT FAIL: no ok prompt (7 6 * . != 42)')
    # introspect the armed write vector (informational)
    cmd(': WV BLK-WRITER@ ;')
    none_xt = cmd("' (BLK-WRITE-NONE) .").strip()
    wv = cmd('WV .').strip()
    print(f'  BLK-WRITER@ = {wv!r}; (BLK-WRITE-NONE) = {none_xt!r}')
    # fill block 199 (BUFFER = no read), mark dirty, save
    cmd('DECIMAL')
    cmd(f'{BLK} BUFFER 1024 65 FILL')      # 0x41
    cmd('UPDATE')
    save = cmd('SAVE-BUFFERS', 4)
    print(f'  SAVE-BUFFERS -> {save.strip()[-60:]!r}')
    cmd('DEPTH .')
finally:
    q.kill(); q.wait()
    qemu_pid.kill_pidfile(CARRIER_PIDFILE)

with open(SCRATCH, 'rb') as f:
    f.seek(LBA * 512)
    after = f.read(512)
intact = after == SENTINEL
clob = after == b'\x41' * 512
print(f'  scratch LBA {LBA}: sentinel intact={intact}, clobbered-by-write={clob}')

if CARRIER_REDS:
    if intact:
        die(1, f'XPASS: {CARRIER_REDS[0]} — host disk untouched; remove the red')
    if clob:
        print(f'XFAIL (expected): {CARRIER_REDS[0]} — cell-0 default wrote block to the fixed disk')
        sys.exit(0)
    die(3, f'INSTRUMENT FAIL: scratch LBA {LBA} neither intact nor cleanly clobbered: {after[:8].hex()}')
# red removed: host-safety is now a hard requirement
if not intact:
    die(1, f'FAIL: cell-0 SAVE-BUFFERS reached the fixed disk (LBA {LBA} not the sentinel)')
print(f'PASS: cell-0 block write refused; host disk untouched (LBA {LBA} sentinel intact)')
sys.exit(0)
