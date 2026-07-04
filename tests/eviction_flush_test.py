#!/usr/bin/env python3
"""Decisive experiment: does dirty-buffer EVICTION alone reboot?

Hypothesis: blk_find_buffer .find_lru path calls blk_flush_one
(clobbers EAX) then uses EAX as victim index at .setup_slot.
Prediction: any BLOCK read that evicts a DIRTY buffer reboots,
no SET-LOAD involved.

Phase A: SET-BLK SET-SAVE, evict via 4 distinct reads, 3 4 + .
Phase B (control, fresh boot): explicit BUFFER/UPDATE dirty (no
SAVE-BUFFERS), evict, 3 4 + .
Phase C: SEE SET-LOAD shadowing check.
"""

import socket
import subprocess
import sys
import time

PORT = 4479
LOG = 'eviction-test.log'


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
    try:
        s.recv(4096)
    except Exception:
        pass
    return s


log = open(LOG, 'w')


def cmd(s, c, t=1.5):
    log.write(f'>>> {c}\n')
    s.sendall((c + '\r').encode())
    time.sleep(t)
    d = b''
    try:
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            d += chunk
    except Exception:
        pass
    r = d.decode('ascii', errors='replace')
    log.write(r + '\n')
    log.flush()
    return r


def alive(s, tag):
    r = cmd(s, '3 4 + .', 2)
    boot = 'bmforth' in r.lower() or 'ForthOS' in r
    if '7 ' in r and not boot:
        print(f'  {tag}: ALIVE (7 ok)')
        return True
    print(f'  {tag}: DEAD/REBOOT  resp={r.strip()[:100]!r}')
    return False


def main():
    print('=== Phase A: SET-SAVE then forced eviction ===')
    start()
    s = conn()
    r = cmd(s, 'S" SETTINGS" LOAD-VOCAB', 12)
    print(f'  LOAD-VOCAB resp: {r.strip()[-80:]!r}')
    r = cmd(s, 'USING SETTINGS')
    print(f'  USING resp: {r.strip()[:80]!r}')
    cmd(s, 'DECIMAL')
    r = cmd(s, 'SET-BLK SET-SAVE', 3)
    print(f'  SET-SAVE resp: {r.strip()[:80]!r}')
    if alive(s, 'after SET-SAVE'):
        # Force eviction: 4 buffers, read 4 distinct other blocks
        # from a colon def (matches BTEST conditions)
        cmd(s, ': EVICT 300 BLOCK DROP 301 BLOCK DROP '
               '302 BLOCK DROP 303 BLOCK DROP ;')
        r = cmd(s, 'EVICT', 3)
        print(f'  EVICT resp: {r.strip()[:80]!r}')
        if alive(s, 'after EVICT (post-SET-SAVE)'):
            # Phase C only reachable if still alive
            r = cmd(s, 'SEE SET-LOAD', 3)
            print(f'  SEE SET-LOAD: {r.strip()[:300]!r}')
            # Phase D: ground-truth repro in correct env
            r = cmd(s, 'SET-BLK SET-LOAD', 3)
            print(f'  SET-LOAD resp: {r.strip()[:100]!r}')
            alive(s, 'after SET-LOAD (ground truth)')
    s.close()
    kill()
    # Fall through to Phase B regardless — it is the decisive
    # control (isolates eviction path from all SETTINGS code)

    print('=== Phase B (control): explicit dirty, no SAVE-BUFFERS ===')
    start()
    s = conn()
    cmd(s, 'DECIMAL')
    # Dirty block 198 without flushing
    cmd(s, ': DIRTY 198 BUFFER DROP UPDATE ;')
    r = cmd(s, 'DIRTY', 2)
    print(f'  DIRTY resp: {r.strip()[:80]!r}')
    if alive(s, 'after DIRTY'):
        cmd(s, ': EVICT 300 BLOCK DROP 301 BLOCK DROP '
               '302 BLOCK DROP 303 BLOCK DROP ;')
        r = cmd(s, 'EVICT', 3)
        print(f'  EVICT resp: {r.strip()[:80]!r}')
        alive(s, 'after EVICT (explicit dirty)')
    s.close()
    kill()
    log.close()
    print(f'Full serial log: {LOG}')


if __name__ == '__main__':
    main()
