#!/usr/bin/env python3
"""Memdisk-boot block writer test (M4b Phase 3, scenario B + HP analog).

Boots ForthOS the way the HP does: QEMU built-in TFTP serves
pxelinux.0 -> memdisk -> combined.img, so MEMDISK_BASE is set and
the kernel installs (BLK-WRITE-NONE) as the default block writer.

Scenario B (loud refusal):
  1. BLK-WRITER@ equals ' (BLK-WRITE-NONE) at boot.
  2. Block reads work (RAM-backed memdisk path).
  3. SAVE-BUFFERS of a dirty buffer prints BLOCK WRITE FAIL,
     leaves the system alive, stacks balanced.

HP analog (the M4 persistence path on real iron):
  4. ALSO AHCI / AHCI-INIT / AHCI-RW installs the AHCI writer.
  5. The still-dirty buffer now flushes cleanly to the AHCI disk;
     verified by AHCI-READ of the target LBA.

Skips the AHCI half cleanly on free builds (no ahci.fth).
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

PORT = 4483
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(ROOT, 'build', 'memdisk-ahci-scratch.img')

PXELINUX = '/usr/lib/PXELINUX/pxelinux.0'
LDLINUX = '/usr/lib/syslinux/modules/bios/ldlinux.c32'
MEMDISK = '/usr/lib/syslinux/memdisk'

def kill():
    subprocess.run(['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
                   capture_output=True)
    time.sleep(0.3)

def make_tftp_root():
    d = tempfile.mkdtemp(prefix='forthos-pxe-')
    shutil.copy(PXELINUX, d)
    shutil.copy(LDLINUX, d)
    shutil.copy(MEMDISK, d)
    shutil.copy(os.path.join(ROOT, 'build', 'combined.img'),
                os.path.join(d, 'forth.img'))
    os.mkdir(os.path.join(d, 'pxelinux.cfg'))
    with open(os.path.join(d, 'pxelinux.cfg', 'default'),
              'w') as f:
        f.write('DEFAULT forthos\n'
                'PROMPT 0\n'
                'TIMEOUT 1\n'
                'LABEL forthos\n'
                '  KERNEL memdisk\n'
                '  APPEND initrd=forth.img harddisk\n')
    return d

def start(tftp_root, with_ahci):
    kill()
    args = [
        'qemu-system-i386',
        '-m', '64',
        '-netdev', f'user,id=n0,tftp={tftp_root},'
                   'bootfile=pxelinux.0',
        '-device', 'e1000,netdev=n0',
        '-boot', 'n',
        '-serial', f'tcp::{PORT},server=on,wait=off',
        '-display', 'none',
    ]
    if with_ahci:
        with open(SCRATCH, 'wb') as f:
            f.write(b'\x00' * (2048 * 512))
        args += [
            '-drive', f'file={SCRATCH},format=raw,'
                      'if=none,id=sata0',
            '-device', 'ich9-ahci,id=ahci0',
            '-device', 'ide-hd,drive=sata0,bus=ahci0.0',
        ]
    subprocess.Popen(args, cwd=ROOT, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
    for _ in range(30):
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
    return s

def wait_boot(s):
    # PXE -> memdisk -> kernel takes longer than floppy boot
    deadline = time.time() + 30
    seen = b''
    while time.time() < deadline:
        try:
            seen += s.recv(4096)
        except: pass
        if b'ok' in seen:
            return True
        time.sleep(0.5)
    return False

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
    for p in (PXELINUX, LDLINUX, MEMDISK):
        if not os.path.exists(p):
            print(f'SKIP: {p} not installed')
            sys.exit(0)

    have_ahci = os.path.exists(
        os.path.join(ROOT, 'forth', 'dict', 'ahci.fth'))

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

    out.write('=== Memdisk boot: (BLK-WRITE-NONE) + AHCI '
              'install ===\n')
    out.flush()

    tftp_root = make_tftp_root()
    try:
        start(tftp_root, have_ahci)
        s = conn()
        if not wait_boot(s):
            out.write('FAIL: no ok prompt after PXE boot\n')
            sys.exit(1)
        out.write('  (booted via pxelinux -> memdisk)\n')
        cmd(s, 'DECIMAL')

        # Scenario B: memdisk defaults are the loud stubs
        r = cmd(s, "BLK-WRITER@ ' (BLK-WRITE-NONE) = .")
        chk('memdisk default = (BLK-WRITE-NONE)', r, '-1 ')
        r = cmd(s, "BLK-READER@ ' (BLK-READ-NONE) = .")
        chk('memdisk default = (BLK-READ-NONE)', r, '-1 ')
        r = cmd(s, '1 BLOCK C@ . ', 2)
        chk('RAM-backed BLOCK read works', r, 'ok',
            unwanted='?')
        # Loud read refusal: the stub must NEVER fall back to
        # the RAM copy — that silent fallback is the stale-
        # settings bug the read vector exists to kill.
        cmd(s, 'CREATE RBUF 1024 ALLOT')
        r = cmd(s, 'RBUF 199 PBLK-READ .', 2)
        chk('PBLK-READ refused loudly on memdisk', r,
            'BLOCK READ FAIL 199')
        chk('loud reader returns ior=1', r, '1 ')
        # Sentinel 77 at byte 900: second sector, and past a
        # DECIMAL-400 truncation — proves full 1024-byte copy
        # when read back through the vector below.
        cmd(s, '199 BUFFER DUP 1024 42 FILL '
               '900 + 77 SWAP C! UPDATE')
        r = cmd(s, 'SAVE-BUFFERS', 3)
        chk('SAVE-BUFFERS fails loudly on memdisk', r,
            'BLOCK WRITE FAIL 199')
        r = cmd(s, '3 4 + .')
        chk('system alive after refusal', r, '7 ')
        r = cmd(s, 'DEPTH .')
        chk('stacks balanced', r, '0 ')

        if have_ahci:
            # HP analog: install AHCI writer, dirty buffer
            # from the refusal above now flushes for real.
            r = cmd(s, 'ALSO AHCI')
            chk('ALSO AHCI', r, 'ok', unwanted='?')
            r = cmd(s, 'AHCI-INIT', 5)
            chk('AHCI-INIT on memdisk boot', r, 'AHCI ok')
            cmd(s, 'DECIMAL')  # AHCI-INIT leaves base HEX
            r = cmd(s, 'AHCI-RW')
            chk('AHCI-RW installs writer', r,
                'AHCI writer installed')
            chk('AHCI-RW installs reader', r,
                'AHCI reader installed')
            r = cmd(s, 'BLK-READER@ AHCI-READER-XT = .')
            chk('BLK-READER@ = AHCI-READER-XT', r, '-1 ')
            r = cmd(s, 'SAVE-BUFFERS', 3)
            chk('dirty buffer flushes via AHCI', r, 'ok',
                unwanted='BLOCK WRITE FAIL')
            # block 199 -> LBA 623; pattern byte 42
            r = cmd(s, '623 1 AHCI-READ .', 3)
            chk('AHCI-READ LBA 623 ok', r, '0 ')
            r = cmd(s, 'SEC-BUF C@ .')
            chk('persisted pattern 42 on AHCI disk', r, '42 ')
            # Vectored read-back: zero RBUF first so the
            # sentinel can only have come from the disk.
            cmd(s, 'RBUF 1024 0 FILL')
            r = cmd(s, 'RBUF 199 PBLK-READ .', 3)
            chk('PBLK-READ via AHCI ior=0', r, '0 ',
                unwanted='BLOCK READ FAIL')
            r = cmd(s, 'RBUF C@ .')
            chk('vectored read returns pattern 42', r, '42 ')
            r = cmd(s, 'RBUF 900 + C@ .')
            chk('sentinel at byte 900 survives (full '
                '1024-byte copy)', r, '77 ')
            r = cmd(s, 'DEPTH .')
            chk('final stack balance', r, '0 ')
        else:
            out.write('  (free build: AHCI half skipped)\n')

        s.close()
    finally:
        kill()
        shutil.rmtree(tftp_root, ignore_errors=True)

    out.write(f'\nPassed: {ok}/{ok+fail}\n')
    out.flush()
    sys.exit(1 if fail else 0)

if __name__ == '__main__':
    main()
