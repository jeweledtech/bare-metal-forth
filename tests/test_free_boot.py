#!/usr/bin/env python3
"""The free image boots and its embedded NOTEPAD loads clean (private
TASK_WINDOW_FOCUS, the free-boot target). Three checks, FB1-FB3.

  python3 tests/test_free_boot.py <serial-port> [bmforth-free.img]   (cwd: tree root)

bmforth-free.img (make free) embeds NOTEPAD and the vocabularies it uses
(EMBED_VOCABS_FREE); no other test boots it. The serial port waits for this
script (wait=on), so the whole boot transcript is read: an embedded line
that does not resolve prints `<word> ?` and EMBED ABORTED, and the rest of
the embedded vocabularies are not loaded.
"""
import hashlib, os, socket, subprocess, sys, time

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import serial as ser

PORT = int(sys.argv[1])
IMG = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'build', 'bmforth-free.img')
OUT = os.path.join(ROOT, 'build', 'free-boot.d')
os.makedirs(OUT, exist_ok=True)
PF = os.path.join(OUT, 'qemu.pid')

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}', flush=True)
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''), flush=True)


h = hashlib.sha256(open(IMG, 'rb').read()).hexdigest() if os.path.exists(IMG) else 'ABSENT'
print(f'input sha256 {h}  {IMG}', flush=True)
print(f'input sha256 {hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()}  '
      f'{os.path.abspath(__file__)}', flush=True)

qemu_pid.kill_pidfile(PF)
ERR = os.path.join(OUT, 'qemu.err')
proc = subprocess.Popen(['qemu-system-i386', '-drive', f'file={IMG},format=raw,if=floppy', '-m', '256',
                         '-display', 'none', '-snapshot',
                         '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=on', '-pidfile', PF],
                        stdout=subprocess.DEVNULL, stderr=open(ERR, 'w'))
qemu_pid.wait_started(proc, PF, PORT, 'free-boot', ERR)
try:
    s = socket.create_connection(('127.0.0.1', PORT), timeout=10)
    s.settimeout(0.2)
    buf, t0, last = b'', time.time(), time.time()
    while time.time() - t0 < 60:
        try:
            d = s.recv(65536)
            if d:
                buf += d
                last = time.time()
        except socket.timeout:
            if buf.endswith(b'ok ') and time.time() - last > 1.0:
                break
    boot = buf.decode('ascii', 'replace')
    print(f'    (boot transcript: {len(boot)} bytes; tail {boot[-120:]!r})', flush=True)
    check('FB1 the free image boots to the ok prompt', boot.endswith('ok '), f'{boot[-80:]!r}')
    bad = [ln.strip() for ln in boot.splitlines() if ln.rstrip().endswith(' ?') or 'EMBED ABORTED' in ln]
    check('FB2 every embedded line resolved: no "<word> ?", no EMBED ABORTED', not bad, f'{bad[:4]}')
    reply, how = ser.send_until_prompt(s, "ALSO NOTEPAD ' NOTEPAD-RUN . PREVIOUS", budget=15)
    out = reply.split('\r\n', 1)[1] if '\r\n' in reply else ''
    check('FB3 NOTEPAD is loaded: ALSO NOTEPAD, NOTEPAD-RUN found', how == 'prompt' and '?' not in out,
          f'{out.strip()[:80]!r} ({how})')
    s.close()
finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
sys.exit(0 if FAIL == 0 else 1)
