#!/usr/bin/env python3
"""AHCI-BLK-READ wiring test (M4c Phase 4 / scenario C).

Proves the persistent-read vector end to end, including the two
checks the write matrix cannot express:

Boot 1 (zeroed AHCI scratch):
  1. AHCI-RW installs BOTH vectors; BLK-READER@ probe confirms.
  2. Fresh-disk first-load: SET-LOAD on a zeroed data store reads
     ok (ior=0), finds no magic, announces "fresh block" and
     defaults — a no-op, not a crash.
  3. SET-SAVE persists real settings (color=3 scan=1) via the
     AHCI writer; a second block (205) gets pattern 42 plus a
     sentinel 77 at byte 900 — second sector, past a DECIMAL-400
     truncation — via the kernel BUFFER/UPDATE/SAVE-BUFFERS path.

Boot 2 (SAME scratch file — power-cycle analog):
  4. Stale-RAM discrimination: kernel BLOCK 199 shows the
     pristine code-store copy (0), while PBLK-READ via AHCI
     returns the saved settings ('F' of FSET1). Disk wins.
  5. Sentinel read-back: RBUF zeroed, block 205 through the
     vector, byte 0 = 42 and byte 900 = 77 — full 1024-byte,
     two-sector copy proven on the read path.
  6. SET-LOAD restores color=3 scan=1 across the power cycle.

Topology: floppy boot + private IDE copy (kernel BLOCK reads
stay pristine — shared build/combined-ide.img is mutated by
other tests) + ICH9-AHCI 1 MB scratch.

Requires forth/dict/ahci.fth (paid vocab). Skips cleanly if
absent.
"""

import os
import shutil
import socket
import subprocess
import sys
import time

PORT = 4485
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(ROOT, 'build', 'ahci-blkr-scratch.img')
IDE_COPY = os.path.join(ROOT, 'build', 'ahci-blkr-ide.img')

def kill():
    subprocess.run(['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
                   capture_output=True)
    time.sleep(0.3)

def start(zero_scratch):
    kill()
    if zero_scratch:
        with open(SCRATCH, 'wb') as f:
            f.write(b'\x00' * (2048 * 512))
        shutil.copy(os.path.join(ROOT, 'build', 'combined.img'),
                    IDE_COPY)
    subprocess.Popen([
        'qemu-system-i386',
        '-drive', 'file=build/combined.img,format=raw,if=floppy',
        '-drive', f'file={IDE_COPY},format=raw,if=ide,index=1',
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

    out.write('=== AHCI-BLK-READ / BLK-READER! wiring ===\n')
    out.write('--- Boot 1: fresh store, save, sentinel ---\n')
    out.flush()

    start(zero_scratch=True)
    s = conn()
    cmd(s, 'DECIMAL')

    # 1. Install both vectors
    r = cmd(s, 'ALSO AHCI')
    chk('ALSO AHCI', r, 'ok', unwanted='?')
    r = cmd(s, 'AHCI-INIT', 5)
    chk('AHCI-INIT finds ICH9', r, 'AHCI ok')
    if 'AHCI ok' not in r:
        out.write('FATAL: no AHCI controller\n')
        s.close()
        kill()
        sys.exit(1)
    cmd(s, 'DECIMAL')  # AHCI-INIT leaves base HEX
    r = cmd(s, 'AHCI-RW')
    chk('AHCI-RW installs writer', r, 'AHCI writer installed')
    chk('AHCI-RW installs reader', r, 'AHCI reader installed')
    r = cmd(s, 'BLK-READER@ AHCI-READER-XT = .')
    chk('BLK-READER@ = AHCI-READER-XT', r, '-1 ')

    # 2. Sentinel block 205 via kernel path (drop AHCI shadows
    #    first: ahci.fth shadows BUFFER as BLOCK)
    cmd(s, 'ONLY FORTH DEFINITIONS')
    cmd(s, '205 BUFFER DUP 1024 42 FILL '
           '900 + 77 SWAP C! UPDATE')
    r = cmd(s, 'SAVE-BUFFERS', 3)
    chk('sentinel block 205 flushes via AHCI', r, 'ok',
        unwanted='BLOCK WRITE FAIL')

    # 3. Fresh-disk first-load: zeroed store -> loud no-op
    r = cmd(s, 'S" SETTINGS" LOAD-VOCAB', 12)
    r = cmd(s, 'USING SETTINGS')
    chk('USING SETTINGS', r, 'ok')
    r = cmd(s, 'SET-BLK .')
    chk('SETTINGS visible (SET-BLK=199)', r, '199 ')
    cmd(s, 'ALSO UI-CORE')
    cmd(s, '5 SC-COLOR !')
    r = cmd(s, 'SET-BLK SET-LOAD', 2)
    chk('first-load announces fresh block', r, 'fresh block')
    r = cmd(s, 'SC-COLOR @ .')
    chk('first-load defaults, not stale RAM (0)', r, '0 ')

    # 4. Save real settings through the vector
    cmd(s, '3 SC-COLOR !')
    cmd(s, '1 SC-SCAN !')
    r = cmd(s, 'SET-BLK SET-SAVE', 3)
    chk('SET-SAVE via AHCI writer', r, 'ok',
        unwanted='BLOCK WRITE FAIL')
    r = cmd(s, 'DEPTH .')
    chk('boot 1 stack balance', r, '0 ')

    s.close()

    # --- Boot 2: SAME scratch — power-cycle analog ---
    out.write('--- Boot 2: same scratch (power cycle) ---\n')
    out.flush()
    start(zero_scratch=False)
    s = conn()
    cmd(s, 'DECIMAL')

    # 5. Stale-RAM discrimination: kernel BLOCK sees the
    #    pristine code store (build residue — old DEFLATE
    #    source, byte 0 = space), the vector sees the data
    #    store. The claim is divergence: BLOCK's view is NOT
    #    the saved settings ('F' of FSET1 = 70).
    cmd(s, ': DISC 199 BLOCK C@ 70 <> . ;')
    r = cmd(s, 'DISC', 2)
    chk('kernel BLOCK 199 diverged from saved store', r, '-1 ')

    r = cmd(s, 'ALSO AHCI')
    chk('ALSO AHCI (boot 2)', r, 'ok', unwanted='?')
    r = cmd(s, 'AHCI-INIT', 5)
    chk('AHCI-INIT (boot 2)', r, 'AHCI ok')
    cmd(s, 'DECIMAL')
    r = cmd(s, 'AHCI-RW')
    chk('AHCI-RW (boot 2)', r, 'AHCI reader installed')

    cmd(s, 'CREATE RBUF 1024 ALLOT')
    cmd(s, 'RBUF 1024 0 FILL')
    r = cmd(s, 'RBUF 199 PBLK-READ .', 3)
    chk('PBLK-READ 199 ior=0', r, '0 ',
        unwanted='BLOCK READ FAIL')
    r = cmd(s, 'RBUF C@ .')
    chk('disk wins: vector sees FSET1 (70)', r, '70 ')

    # 6. Sentinel read-back: full 1024-byte, two-sector copy
    cmd(s, 'RBUF 1024 0 FILL')
    r = cmd(s, 'RBUF 205 PBLK-READ .', 3)
    chk('PBLK-READ 205 ior=0', r, '0 ',
        unwanted='BLOCK READ FAIL')
    r = cmd(s, 'RBUF C@ .')
    chk('block 205 pattern 42', r, '42 ')
    r = cmd(s, 'RBUF 900 + C@ .')
    chk('sentinel at byte 900 survives power cycle '
        '(full copy)', r, '77 ')

    # 7. SET-LOAD restores across the power cycle
    r = cmd(s, 'S" SETTINGS" LOAD-VOCAB', 12)
    r = cmd(s, 'USING SETTINGS')
    chk('USING SETTINGS (boot 2)', r, 'ok')
    cmd(s, 'ALSO UI-CORE')
    r = cmd(s, 'SET-BLK SET-LOAD', 2)
    chk('SET-LOAD reads store', r, 'ok',
        unwanted='using defaults')
    cmd(s, ': RT SC-COLOR @ 100 * SC-SCAN @ + . ;')
    r = cmd(s, 'RT')
    chk('settings survive power cycle (301)', r, '301 ')
    r = cmd(s, 'DEPTH .')
    chk('final stack balance', r, '0 ')

    s.close()
    kill()

    out.write(f'\nPassed: {ok}/{ok+fail}\n')
    out.flush()
    sys.exit(1 if fail else 0)

if __name__ == '__main__':
    main()
