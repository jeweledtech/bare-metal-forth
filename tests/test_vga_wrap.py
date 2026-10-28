#!/usr/bin/env python3
"""VGA console wrap at column 80 (private TASK_VGA_WRAP). Checks W1-W5,
M1-M3, M1s and S1 (serial identity), over two boots.

  python3 tests/test_vga_wrap.py <serial-port> <monitor-port>     (cwd: tree root)

print_char wrapped by returning to column 0 of the same row, so the 81st
character overwrote the row's start (LOG-DUMP's long record, a typed line
past column 80). The screen is read through the QEMU monitor (pmemsave of
0xB8000); serial has no columns and must not change. Expected values are the
task doc's, written before any code.
"""
import hashlib, os, re, shutil, socket, subprocess, sys, time

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import serial as ser

SP, MP = int(sys.argv[1]), int(sys.argv[2])
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
OUT = os.path.join(ROOT, 'build', 'vga-wrap.d')
os.makedirs(OUT, exist_ok=True)
PF = os.path.join(OUT, 'qemu.pid')
IDE = os.path.join(OUT, 'combined-ide.img')
SEQ = ''.join(chr(65 + i % 7) for i in range(3000))    # A-G: period 7, so an overwrite shows
BLANK = ' ' * 80
# S1: sha256 of boot 1's serial bytes under the unmodified base kernel
# (combined.img 60ddb274, the red run after 5653442; 709 bytes), pinned
# before any print_char change.
SERIAL_BASE = '9e2ca8f83b778799c7b85d1609eb747032d1b412ced60a98ab01b4f09806fc6c'

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}', flush=True)
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''), flush=True)


for p in (COMBINED, os.path.join(ROOT, 'src', 'kernel', 'forth.asm'), os.path.abspath(__file__)):
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else 'ABSENT'
    print(f'input sha256 {h}  {p}', flush=True)


class Rec:
    """The serial socket, keeping every byte received after the boot sync."""
    def __init__(self, s):
        self.s, self.got = s, bytearray()

    def recv(self, n):
        d = self.s.recv(n)
        self.got += d
        return d

    def sendall(self, d):
        self.s.sendall(d)

    def settimeout(self, t):
        self.s.settimeout(t)

    def close(self):
        self.s.close()


_mon = None


def mon(cmd):
    global _mon
    if _mon is None:
        _mon = socket.create_connection(('127.0.0.1', MP), 5)
        time.sleep(0.3)
        _mon.recv(65536)
    _mon.sendall((cmd + '\n').encode())
    time.sleep(0.8)
    return _mon.recv(65536)


def screen():
    path = os.path.join(OUT, 'vga.bin')
    if os.path.exists(path):
        os.remove(path)
    mon(f'pmemsave 0xb8000 4000 "{path}"')
    raw = open(path, 'rb').read() if os.path.exists(path) else b''
    return [raw[i * 160:(i + 1) * 160:2].decode('latin-1') for i in range(25)] if len(raw) == 4000 else None


def boot(tag):
    global _mon
    _mon = None
    shutil.copyfile(COMBINED, IDE)
    qemu_pid.kill_pidfile(PF)
    q = subprocess.run(['qemu-system-i386', '-drive', f'file={COMBINED},format=raw,if=floppy', '-m', '256',
                        '-drive', f'file={IDE},format=raw,if=ide,index=1', '-display', 'none', '-snapshot',
                        '-serial', f'tcp:127.0.0.1:{SP},server=on,wait=off',
                        '-monitor', f'tcp:127.0.0.1:{MP},server=on,wait=off',
                        '-daemonize', '-pidfile', PF], capture_output=True)
    qemu_pid.check_launch(q, PF, SP, f'vga-wrap {tag}')
    print(f'--- boot {tag}', flush=True)
    return Rec(ser.connect_and_sync(SP, budget=60))


def send(s, cmd, budget=30):
    reply, how = ser.send_until_prompt(s, cmd, budget=budget)
    body = reply.split('\r\n', 1)[1] if '\r\n' in reply else ''
    print(f'    >>> {cmd[:70]}\n        {body.strip()[-100:]!r}  [{how}]', flush=True)
    return body


def raw(s, data, wait=1.5):
    """Send bytes without waiting for a prompt; return what came back."""
    s.sendall(data)
    time.sleep(wait)
    s.settimeout(0.3)
    got = b''
    try:
        while True:
            d = s.recv(65536)
            if not d:
                break
            got += d
    except Exception:
        pass
    return got.decode('latin-1')


def until_prompt(s, budget=10):
    """Read until an 'ok ' prompt (after a raw send that ran a line)."""
    end, got = time.time() + budget, ''
    while time.time() < end:
        got += raw(s, b'', 0.3)
        if got.endswith('ok ') or got.rstrip().endswith('ok'):
            break
    return got


def rows(scr, *rs):
    return ' | '.join(f'{r}:{scr[r].rstrip()!r}' for r in rs) if scr else 'no screen'


try:
    # ---- Boot 1: MORE off; its serial bytes are S1's subject
    s = boot('1')
    send(s, ': SEQ ( n -- ) 0 DO I 7 MOD 65 + EMIT LOOP ;')
    send(s, ': ROWS ( n -- ) 0 DO CR LOOP ;')

    raw(s, b'PAGE 100 SEQ KEY DROP\r')
    scr = screen()
    check('W1 100 letters: row 0 = the first 80, row 1 = the last 20',
          bool(scr) and scr[0] == SEQ[:80] and scr[1] == SEQ[80:100].ljust(80), rows(scr, 0, 1))
    raw(s, b'x', 0.5)
    until_prompt(s, 5)

    raw(s, b'PAGE 80 SEQ CR 90 EMIT KEY DROP\r')
    scr = screen()
    check('W2 exactly 80 then CR: row 0 = the 80, row 1 = Z at column 0',
          bool(scr) and scr[0] == SEQ[:80] and scr[1] == 'Z'.ljust(80), rows(scr, 0, 1))
    raw(s, b'x', 0.5)
    until_prompt(s, 5)

    raw(s, b'PAGE 24 ROWS 80 SEQ KEY DROP\r')
    scr = screen()
    check('W3 80 letters on row 24: there, no scroll (rows 0 and 23 blank)',
          bool(scr) and scr[24] == SEQ[:80] and scr[23] == BLANK and scr[0] == BLANK, rows(scr, 0, 23, 24))
    raw(s, b'x', 0.5)
    until_prompt(s, 5)
    scr = screen()
    check('W3b the next prompt wraps: row 23 = the 80, row 24 starts "ok"',
          bool(scr) and scr[23] == SEQ[:80] and scr[24].startswith('ok'), rows(scr, 23, 24))

    send(s, 'PAGE')
    line = ('1 DROP ' * 14)[:93]           # harmless when run; period 7
    send(s, line)
    shown = 'ok ' + line
    scr = screen()
    check('W4 a typed 93-character line: row 0 = its first 80 (with the prompt), row 1 the rest',
          bool(scr) and scr[0] == shown[:80] and scr[1].startswith(shown[80:]), rows(scr, 0, 1))

    send(s, 'PAGE')
    typed = ('1 DROP ' * 12)[:78]           # with "ok ", 81 characters: the last on row 1
    raw(s, typed.encode(), 1.0)
    raw(s, b'\x08\x08', 1.0)
    scr = screen()
    shown = 'ok ' + typed
    check('W5a two backspaces from row 1 column 1: row 1 column 0 and row 0 column 79 erased',
          bool(scr) and scr[1] == BLANK and scr[0] == shown[:79] + ' ', rows(scr, 0, 1))
    raw(s, b'Q', 1.0)
    scr = screen()
    check('W5b the next key lands at row 0 column 79',
          bool(scr) and scr[0] == shown[:79] + 'Q' and scr[1] == BLANK, rows(scr, 0, 1))
    raw(s, b'\r', 0.5)
    until_prompt(s, 5)

    got = hashlib.sha256(bytes(s.got)).hexdigest()
    print(f'  boot 1 serial: {len(s.got)} bytes, sha256 {got}', flush=True)
    if SERIAL_BASE is None:
        print('  RECORDED (not a check): S1 base serial; the green compares against it', flush=True)
    else:
        check('S1 boot 1 serial byte-identical to the base kernel', got == SERIAL_BASE, f'{got}')
    open(os.path.join(OUT, 'boot1-serial.bin'), 'wb').write(bytes(s.got))
    s.close()

    # ---- Boot 2: MORE on
    s = boot('2')
    send(s, ': SEQ ( n -- ) 0 DO I 7 MOD 65 + EMIT LOOP ;')
    send(s, ': M1RUN ( -- ) 30 0 DO 80 SEQ LOOP ;')       # DO loops only when compiled
    send(s, ': M3RUN ( -- ) 30 0 DO I . CR LOOP ;')
    out = raw(s, b'PAGE MORE-ON M1RUN MORE-OFF\r', 3.0)
    body = out.split('\r\n', 1)[1] if '\r\n' in out else out
    before = body.split('-- more --')[0]
    n = len(re.findall(r'[A-G]', before))
    scr = screen()                          # read while the pause holds
    shown = sum(len(re.findall(r'[A-G]', r)) for r in scr[:23]) if scr else -1
    check('M1 2400 letters, no CR: at the pause, rows 0-22 hold 1840 letters (23 wrapped rows), row 23 "-- more --"',
          bool(scr) and shown == 1840 and scr[23].startswith('-- more --'),
          f'letters on rows 0-22 {shown}; {rows(scr, 22, 23)}; raw {out!r}')
    # M1s, added after the first green run (task doc, miss 2): print_char
    # mirrors to serial before its VGA path wraps, and the wrap is what
    # pauses, so serial carries the 1841st letter before the pause.
    check('M1s serial: 1841 letters before "-- more --" (mirror first, then the 23rd wrap pauses)',
          '-- more --' in body and n == 1841, f'more {"-- more --" in body}, letters before {n}')
    rest = ''
    if '-- more --' in body:                # the release key only when there is a pause to take it
        rest = raw(s, b'x', 1.5)
    rest += until_prompt(s, 5)
    total = len(re.findall(r'[A-G]', body + rest))
    check('M2 one pause; all 2400 letters', body.count('-- more --') + rest.count('-- more --') == 1 and total == 2400,
          f'pauses {body.count("-- more --") + rest.count("-- more --")}, letters {total}')
    out = raw(s, b'MORE-ON M3RUN MORE-OFF\r', 3.0)
    check('M3 30 numbered lines: "-- more --" right after "22 " (23 line feeds), as before',
          re.search(r'(^|\n)22 \r\n-- more --', out) is not None, repr(out[-80:]))
    if '-- more --' in out:
        raw(s, b'x', 1.5)
    until_prompt(s, 5)
    s.close()
finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(1 if FAIL else 0)
