#!/usr/bin/env python3
"""BLK-WRITER vector + execute_xt trampoline unit test.

Phase 1 gate for M4b (vectored block-write backend):
  1. Default vector is (BLK-WRITE-ATA) on non-memdisk boot.
  2. A Forth COLON DEFINITION installed via BLK-WRITER! is invoked by
     SAVE-BUFFERS through the asm->Forth trampoline (execute_xt) with
     correct args ( buf-addr blk# -- ior ) and balanced stacks.
  3. Nonzero ior from a writer produces the loud 'BLOCK WRITE FAIL'
     message, leaves the system alive, and leaves the buffer dirty.
  4. (BLK-WRITE-NONE) stub fails loudly (scenario-B semantics).
  5. Restoring (BLK-WRITE-ATA) flushes the still-dirty buffer for real:
     write -> EMPTY-BUFFERS -> BLOCK read-back round-trip.

Topology: scenario A (floppy boot + IDE slave image), same as
test_persist_quick.py.
"""

import socket
import subprocess
import sys
import time

PORT = 4479

def kill():
    subprocess.run(['pkill', '-9', '-f', f'[q]emu.*{PORT}'],
                   capture_output=True)
    time.sleep(0.3)

def start():
    kill()
    time.sleep(0.3)
    subprocess.Popen([
        'qemu-system-i386',
        '-drive', 'file=build/combined.img,format=raw,if=floppy',
        '-drive', 'file=build/combined-ide.img,format=raw,if=ide,index=1',
        '-serial', f'tcp::{PORT},server=on,wait=off',
        '-display', 'none',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    ok = 0
    fail = 0
    out = sys.stdout

    def chk(name, resp, want, unwanted=None):
        nonlocal ok, fail
        good = want in resp and (unwanted is None or unwanted not in resp)
        if good:
            out.write(f'  PASS: {name}\n')
            ok += 1
        else:
            out.write(f'  FAIL: {name}\n')
            out.write(f'    want: {want}'
                      + (f' (without: {unwanted})' if unwanted else '')
                      + '\n')
            out.write(f'    got:  {resp.strip()[:160]}\n')
            fail += 1
        out.flush()

    out.write('=== BLK-WRITER vector / execute_xt trampoline ===\n')
    out.flush()

    start()
    s = conn()
    cmd(s, 'DECIMAL')

    # 1. Boot default: vector holds (BLK-WRITE-ATA)'s XT
    r = cmd(s, 'BLK-WRITER@ . ')
    chk('BLK-WRITER@ nonzero', r, 'ok', unwanted=' 0 ok')
    r = cmd(s, "BLK-WRITER@ ' (BLK-WRITE-ATA) = .")
    chk('default = (BLK-WRITE-ATA)', r, '-1 ')

    # 2. Colon-definition writer through the trampoline
    cmd(s, 'VARIABLE WCNT VARIABLE WBLK VARIABLE WBUF')
    cmd(s, ': TESTW WBLK ! WBUF ! 1 WCNT +! 0 ;')
    r = cmd(s, "' TESTW BLK-WRITER!")
    chk('install colon writer', r, 'ok')
    cmd(s, '199 BUFFER DROP UPDATE')
    r = cmd(s, 'SAVE-BUFFERS', 2)
    chk('colon writer: no fail msg (ior=0)', r, 'ok',
        unwanted='BLOCK WRITE FAIL')
    r = cmd(s, 'WCNT @ .')
    chk('writer called exactly once', r, '1 ')
    r = cmd(s, 'WBLK @ .')
    chk('blk# arg = 199', r, '199 ')
    # buf-addr must lie inside BLK_BUF_DATA (0x28200-0x29200 =
    # 164352-168448 decimal)
    r = cmd(s, 'WBUF @ DUP 164351 > SWAP 168449 < AND .')
    chk('buf-addr inside buffer pool', r, '-1 ')
    r = cmd(s, 'DEPTH .')
    chk('stacks balanced after trampoline', r, '0 ')

    # 3. Failing colon writer -> loud failure, system alive, buffer dirty
    cmd(s, ': FAILW DROP DROP 1 ;')
    cmd(s, "' FAILW BLK-WRITER!")
    cmd(s, '199 BUFFER DROP UPDATE')
    r = cmd(s, 'SAVE-BUFFERS', 2)
    chk('failing writer: loud message', r, 'BLOCK WRITE FAIL 199')
    r = cmd(s, '3 4 + .')
    chk('system alive after failure', r, '7 ')
    r = cmd(s, 'DEPTH .')
    chk('stacks balanced after failure path', r, '0 ')

    # 4. (BLK-WRITE-NONE) stub: scenario-B semantics
    cmd(s, "' (BLK-WRITE-NONE) BLK-WRITER!")
    r = cmd(s, 'SAVE-BUFFERS', 2)
    chk('stub writer: loud message (buffer stayed dirty)', r,
        'BLOCK WRITE FAIL 199')

    # 5. Restore ATA writer: still-dirty buffer flushes for real
    cmd(s, "' (BLK-WRITE-ATA) BLK-WRITER!")
    cmd(s, '199 BUFFER 1024 42 FILL UPDATE')
    r = cmd(s, 'SAVE-BUFFERS', 3)
    chk('ATA writer: clean flush', r, 'ok', unwanted='BLOCK WRITE FAIL')
    cmd(s, 'EMPTY-BUFFERS')
    r = cmd(s, '199 BLOCK C@ .', 2)
    chk('read-back after real write (42)', r, '42 ')
    r = cmd(s, 'DEPTH .')
    chk('final stack balance', r, '0 ')

    s.close()
    kill()

    out.write(f'\nPassed: {ok}/{ok+fail}\n')
    out.flush()
    sys.exit(1 if fail else 0)

if __name__ == '__main__':
    main()
