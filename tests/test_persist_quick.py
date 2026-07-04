#!/usr/bin/env python3
"""Quick M4 persistence smoke test — minimal timeouts."""

import socket
import subprocess
import sys
import time

PORT = 4473

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
    # Wait for TCP listener
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
    r = d.decode('ascii', errors='replace')
    return r

def main():
    ok = 0
    fail = 0
    out = sys.stdout

    def chk(name, resp, want):
        nonlocal ok, fail
        if want in resp:
            out.write(f'  PASS: {name}\n')
            ok += 1
        else:
            out.write(f'  FAIL: {name}\n')
            out.write(f'    want: {want}\n')
            out.write(f'    got:  {resp.strip()[:120]}\n')
            fail += 1
        out.flush()

    out.write('=== M4 Persistence Quick Test ===\n')
    out.flush()

    # --- Boot 1: clear, test defaults, save ---
    start()
    s = conn()

    r = cmd(s, 'S" SETTINGS" LOAD-VOCAB', 12)
    r = cmd(s, 'USING SETTINGS')
    chk('USING SETTINGS', r, 'ok')
    # Guard against silent USING failure ("SETTINGS ?" also
    # prints ok): probe a vocab word
    r = cmd(s, 'SET-BLK .')
    chk('SETTINGS visible (SET-BLK=199)', r, '199 ')
    # Console helpers below use IV-SET/IV-GET; ALSO is not
    # transitive, so expose UI-CORE explicitly
    r = cmd(s, 'ALSO UI-CORE')

    # Clear block 199
    r = cmd(s, ': CLR199 199 BUFFER 1024 32 FILL '
            'UPDATE SAVE-BUFFERS ;')
    r = cmd(s, 'DECIMAL CLR199', 3)

    # Virgin block -> defaults
    r = cmd(s, '2 SC-COLOR !')
    r = cmd(s, 'SET-BLK SET-LOAD')
    r = cmd(s, ': CHK1 SC-COLOR @ . ;')
    r = cmd(s, 'CHK1')
    chk('virgin block defaults (0)', r, '0 ')

    # DIGITS>N helper
    r = cmd(s, ': TD42 S" 42 " DROP DIGITS>N . ;')
    r = cmd(s, 'TD42')
    chk('DIGITS>N 42', r, '42 ')

    # Save: color=2 scan=1
    r = cmd(s, '2 SC-COLOR !')
    r = cmd(s, '1 SC-SCAN !')
    r = cmd(s, 'SET-BLK SET-SAVE', 3)

    # Clobber to different values
    r = cmd(s, '0 SC-COLOR !')
    r = cmd(s, '0 SC-SCAN !')

    # Reload same session
    r = cmd(s, 'SET-BLK SET-LOAD')
    r = cmd(s, ': RT SC-COLOR @ 100 * SC-SCAN @ + . ;')
    r = cmd(s, 'RT')
    chk('roundtrip (201)', r, '201 ')

    # LIST block 199
    r = cmd(s, '199 LIST', 3)
    chk('LIST FSET1', r, 'FSET1')
    chk('LIST COLOR=2', r, 'COLOR=2')

    # Operator test
    r = cmd(s, ': SETOP S" TestOp99" SC-INP-WI @ IV-SET ;')
    r = cmd(s, 'SETOP')
    r = cmd(s, 'SET-BLK SET-SAVE', 3)
    # Clobber with different string
    r = cmd(s, ': CLOB S" ZZZZZZ" SC-INP-WI @ IV-SET ;')
    r = cmd(s, 'CLOB')
    r = cmd(s, 'SET-BLK SET-LOAD')
    r = cmd(s, ': RDOP SC-INP-WI @ IV-GET TYPE ;')
    r = cmd(s, 'RDOP')
    chk('operator roundtrip', r, 'TestOp99')

    s.close()
    kill()

    # --- Boot 2: reboot survival ---
    out.write('\n--- Reboot ---\n')
    out.flush()
    start()
    s = conn()

    r = cmd(s, 'S" SETTINGS" LOAD-VOCAB', 12)
    r = cmd(s, 'USING SETTINGS')
    r = cmd(s, 'ALSO UI-CORE')
    r = cmd(s, 'DECIMAL')
    r = cmd(s, 'SET-BLK SET-LOAD')
    r = cmd(s, ': RB SC-COLOR @ 100 * SC-SCAN @ + . ;')
    r = cmd(s, 'RB')
    chk('reboot color+scan (201)', r, '201 ')

    r = cmd(s, ': RBOP SC-INP-WI @ IV-GET TYPE ;')
    r = cmd(s, 'RBOP')
    chk('reboot operator', r, 'TestOp99')

    s.close()
    kill()

    out.write(f'\nPassed: {ok}/{ok+fail}\n')
    out.flush()
    sys.exit(1 if fail else 0)

if __name__ == '__main__':
    main()
