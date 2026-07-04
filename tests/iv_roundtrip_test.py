#!/usr/bin/env python3
"""Isolate IV-SET/IV-GET roundtrip (no save/load involved)."""

import socket
import subprocess
import sys
import time

PORT = 4481


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
    except Exception:
        pass
    return d.decode('ascii', errors='replace')


def main():
    start()
    s = conn()
    # UI-CORE is embedded; expose it
    print(cmd(s, 'ALSO UI-CORE').strip())
    # Direct roundtrip on widget 0
    print(cmd(s, ': TSET S" TestOp99" 0 IV-SET ;').strip())
    print(cmd(s, 'TSET').strip())
    print(cmd(s, ': TGET 0 IV-GET TYPE ;').strip())
    print(cmd(s, 'TGET').strip())
    # Inspect count byte and first data byte
    print(cmd(s, 'HEX 20D000 C@ . 20D001 C@ . DECIMAL').strip())
    s.close()
    kill()


if __name__ == '__main__':
    main()
