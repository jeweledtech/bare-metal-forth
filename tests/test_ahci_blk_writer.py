#!/usr/bin/env python3
"""AHCI-BLK-WRITE wiring test (M4b Phase 2 / scenario C).

Proves the paid AHCI vocab plugs into the kernel BLK-WRITER!
vector:
  1. AHCI-INIT on ICH9 (Q35 ahci device) succeeds.
  2. AHCI-WPROBE exercises AHCI-BLK-WRITE standalone BEFORE
     install; pattern verified on the AHCI disk via AHCI-READ.
  3. AHCI-RW installs the writer; BLK-WRITER@ probe confirms.
  4. Kernel-path round trip: kernel BUFFER/UPDATE/SAVE-BUFFERS
     (shadows dropped via ONLY FORTH) flushes through the vector
     onto the AHCI disk; verified via AHCI-READ.
  5. LBA-2048 range guard: block 910 passes (boundary), block
     911 refused standalone AND loudly via SAVE-BUFFERS.

Topology: floppy boot + IDE slave (kernel BLOCK reads) +
ICH9-AHCI with a 1 MB scratch disk (2048 sectors, so the guard
boundary is also the physical disk boundary).

Requires forth/dict/ahci.fth (paid vocab, embedded build).
Skips cleanly if absent.
"""

import os
import socket
import subprocess
import sys
import time

PORT = 4481
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(ROOT, 'build', 'ahci-blkw-scratch.img')

def kill():
    subprocess.run(['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
                   capture_output=True)
    time.sleep(0.3)

def start():
    kill()
    with open(SCRATCH, 'wb') as f:
        f.write(b'\x00' * (2048 * 512))
    subprocess.Popen([
        'qemu-system-i386',
        '-drive', 'file=build/combined.img,format=raw,if=floppy',
        '-drive', 'file=build/combined-ide.img,format=raw,'
                  'if=ide,index=1',
        '-drive', f'file={SCRATCH},format=raw,if=none,id=sata0',
        '-device', 'ich9-ahci,id=ahci0',
        '-device', 'ide-hd,drive=sata0,bus=ahci0.0',
        '-serial', f'tcp::{PORT},server=on,wait=off',
        '-display', 'none',
    ], cwd=ROOT, stdout=subprocess.DEVNULL,
       stderr=subprocess.DEVNULL)
    for _ in range(20):
        time.sleep(0.5)
        try:
            s = socket.socket()
            s.settimeout(1)
            s.connect(('127.0.0.1', PORT))
            s.close()
            return
        except (ConnectionRefusedError, OSError):
            continue
    print('QEMU TCP never came up')
    sys.exit(1)

def conn():
    s = socket.socket()
    s.settimeout(3)
    s.connect(('127.0.0.1', PORT))
    time.sleep(0.5)
    try: s.recv(4096)
    except: pass
    return s

def cmd(s, c, t=1.5):
    s.sendall((c + '\r').encode())
    time.sleep(t)
    d = b''
    try:
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            d += chunk
    except: pass
    return d.decode('ascii', errors='replace')

def main():
    if not os.path.exists(os.path.join(ROOT, 'forth', 'dict',
                                       'ahci.fth')):
        print('SKIP: ahci.fth not present (free build)')
        sys.exit(0)

    ok = 0
    fail = 0
    out = sys.stdout

    def chk(name, resp, want, unwanted=None):
        nonlocal ok, fail
        good = want in resp and (unwanted is None
                                 or unwanted not in resp)
        if good:
            out.write(f'  PASS: {name}\n')
            ok += 1
        else:
            out.write(f'  FAIL: {name}\n')
            out.write(f'    want: {want}'
                      + (f' (without: {unwanted})'
                         if unwanted else '') + '\n')
            out.write(f'    got:  {resp.strip()[:160]}\n')
            fail += 1
        out.flush()

    out.write('=== AHCI-BLK-WRITE / BLK-WRITER! wiring ===\n')
    out.flush()

    start()
    s = conn()
    cmd(s, 'DECIMAL')

    # 1. Embedded vocab + controller init
    r = cmd(s, 'ALSO AHCI')
    chk('ALSO AHCI (embedded vocab)', r, 'ok', unwanted='?')
    r = cmd(s, 'AHCI-INIT', 5)
    chk('AHCI-INIT finds ICH9', r, 'AHCI ok')
    if 'AHCI ok' not in r:
        out.write('FATAL: no AHCI controller\n')
        s.close()
        kill()
        sys.exit(1)
    # AHCI-INIT leaves base in HEX (runtime DECIMAL . HEX)
    cmd(s, 'DECIMAL')

    # 2. Standalone probe BEFORE install (contract seam)
    r = cmd(s, '199 AHCI-WPROBE', 3)
    chk('AHCI-WPROBE block 199 ior=0', r, 'ior=0')
    r = cmd(s, '623 1 AHCI-READ .', 3)
    chk('AHCI-READ LBA 623 ok', r, '0 ')
    r = cmd(s, 'SEC-BUF C@ .')
    chk('probe pattern 0xAA on AHCI disk', r, '170 ')

    # 3. Install + vector probe
    r = cmd(s, 'AHCI-RW')
    chk('AHCI-RW installs writer', r, 'AHCI writer installed')
    r = cmd(s, 'BLK-WRITER@ AHCI-WRITER-XT = .')
    chk('BLK-WRITER@ = AHCI-WRITER-XT', r, '-1 ')

    # 4. Kernel-path round trip through the vector.
    #    ONLY FORTH drops the AHCI BLOCK/BUFFER/etc shadows so
    #    kernel BUFFER/UPDATE/SAVE-BUFFERS run; the flush goes
    #    through BLK_WRITE_VEC -> AHCI-BLK-WRITE.
    cmd(s, 'ONLY FORTH DEFINITIONS')
    cmd(s, '210 BUFFER 1024 66 FILL UPDATE')
    r = cmd(s, 'SAVE-BUFFERS', 3)
    chk('kernel SAVE-BUFFERS via AHCI writer', r, 'ok',
        unwanted='BLOCK WRITE FAIL')
    cmd(s, 'ALSO AHCI')
    r = cmd(s, '645 1 AHCI-READ .', 3)
    chk('AHCI-READ LBA 645 ok', r, '0 ')
    r = cmd(s, 'SEC-BUF C@ .')
    chk('kernel-path pattern 66 on AHCI disk', r, '66 ')

    # 5. LBA-2048 range guard
    r = cmd(s, 'SEC-BUF 910 AHCI-BLK-WRITE .', 3)
    chk('block 910 (LBA 2045-2046) passes', r, '0 ',
        unwanted='GUARD')
    r = cmd(s, 'SEC-BUF 911 AHCI-BLK-WRITE .', 3)
    chk('block 911 (LBA 2047-2048) refused', r, 'BLK LBA GUARD')
    chk('guard returns ior=1', r, '1 ')
    # Loud kernel-path failure: guard ior -> BLOCK WRITE FAIL
    cmd(s, 'ONLY FORTH DEFINITIONS')
    cmd(s, '911 BUFFER DROP UPDATE')
    r = cmd(s, 'SAVE-BUFFERS', 3)
    chk('kernel flush of block 911 fails loudly', r,
        'BLOCK WRITE FAIL 911')
    # Refused writes must leave the disk untouched. LBA 2047 is
    # where block 911 would have started (block 910's legal
    # write ends at 2046; scratch disk is zero-filled).
    cmd(s, 'ALSO AHCI')
    r = cmd(s, '2047 1 AHCI-READ .', 3)
    chk('LBA 2047 readable', r, '0 ')
    r = cmd(s, 'SEC-BUF C@ .')
    chk('refused writes left LBA 2047 untouched', r, '0 ')
    cmd(s, 'ONLY FORTH DEFINITIONS')
    r = cmd(s, '3 4 + .')
    chk('system alive after guard refusal', r, '7 ')
    r = cmd(s, 'DEPTH .')
    chk('final stack balance', r, '0 ')

    s.close()
    kill()

    out.write(f'\nPassed: {ok}/{ok+fail}\n')
    out.flush()
    sys.exit(1 if fail else 0)

if __name__ == '__main__':
    main()
