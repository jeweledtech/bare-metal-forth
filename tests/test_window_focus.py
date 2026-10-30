#!/usr/bin/env python3
"""Focus between windows: Ctrl+W (private TASK_WINDOW_FOCUS,
DESIGN_WINDOW_FOCUS step 2). Twenty-two checks, D0 W0 K1-K4 S1-S6 E1 E2 F0
F1 F2 O1 N1-N3 U0.

  python3 tests/test_window_focus.py <serial-port> <monitor-port>   (cwd: tree root)

The kernel: read_key runs FOCUS-HOOK through execute_xt when it reads 0x17
(serial, or PS/2 Ctrl+W), unless none is set or one is running, and reads
again; FOCUS-SWITCH does the same from Forth and says whether it ran; an
ABORT inside the hook clears the busy flag; on a BIOS boot the hardware
cursor follows the console's cursor before each key of a line and when the
hook returns. WINDOW: WIN-KEYS! gives a window a key handler and makes it
Ctrl+W's target; WIN-FOCUS switches to it now; WIN-FORM-KEYS runs a form as
a handler, clearing its window, never the screen.

The console is the band in rows 17-24; window 1 is rows 0-16. TH, the test
handler, counts the keys it reads into TN, writes each into window 1's row
0, and leaves on 0x17. Keys reach the guest over serial, or as PS/2 key
events from the monitor's sendkey. CRTC@ reads the hardware cursor's cell.

Blocks come from a copy of the image attached as an IDE disk; D0 is the
positive control that it is attached (as test_console_band.py).
"""
import hashlib, os, shutil, socket, subprocess, sys, time

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import serial as ser

PORT = int(sys.argv[1])
MON = int(sys.argv[2])
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
OUT = os.path.join(ROOT, 'build', 'window-focus.d')
os.makedirs(OUT, exist_ok=True)
PF = os.path.join(OUT, 'qemu.pid')
IDE = os.path.join(OUT, 'combined-ide.img')
CTRL_W = '\x17'

SETUP = [
    'ONLY FORTH DEFINITIONS DECIMAL ALSO HAL',
    ': CELLOF ( ch -- idx ) -1 SWAP 2000 0 DO FB-BASE I 2 * + C@ OVER = IF NIP I SWAP THEN LOOP DROP ;',
    ': PAINT 1360 0 DO 1857 FB-BASE I 2 * + W! LOOP ;',
    ': UNPAINTED ( -- n ) 0 1360 0 DO FB-BASE I 2 * + W@ 1857 = 0= IF 1+ THEN LOOP ;',
    # rows 20-24 of the band: 'B', counted back
    ': BMARK 2000 1600 DO 1858 FB-BASE I 2 * + W! LOOP ;',
    ': BCOUNT ( -- n ) 0 2000 1600 DO FB-BASE I 2 * + W@ 1858 = IF 1+ THEN LOOP ;',
    ': ROW1 16 1 DO FB-BASE 80 I + 2 * + C@ EMIT LOOP ;',
    ': ROW0 ( n -- ) 0 DO FB-BASE I 2 * + C@ EMIT LOOP ;',
    'HEX : CRTC@ ( -- cell ) 0E 3D4 OUTB 3D5 INB 8 LSHIFT 0F 3D4 OUTB 3D5 INB OR ; DECIMAL',
]
HANDLERS = [
    'ALSO UI-CORE ALSO WINDOW',
    'VARIABLE TN VARIABLE TACT VARIABLE TFS',
    # FOCUS-SWITCH inside the switch: refused (busy), so TFS gets 0
    ': TH 0 TN ! WIN-ACTIVE TACT ! FOCUS-SWITCH TFS ! 40 5 CURSOR-AT'
    ' BEGIN KEY DUP 23 = IF DROP EXIT THEN TN @ 0 1 WIN-AT C! 1 TN +! AGAIN ;',
    ': TH2 KEY DROP ABORT ;',
]

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}', flush=True)
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''), flush=True)


def mon_cmd(cmd):
    """One HMP command over the monitor socket, read to the next prompt."""
    m = socket.create_connection(('127.0.0.1', MON), timeout=5)
    buf, t0 = b'', time.time()
    while not buf.rstrip().endswith(b'(qemu)') and time.time() - t0 < 5:
        buf += m.recv(4096)
    m.sendall((cmd + '\n').encode())
    buf, t0 = b'', time.time()
    while not buf.rstrip().endswith(b'(qemu)') and time.time() - t0 < 10:
        buf += m.recv(4096)
    m.close()
    return buf.decode('ascii', 'replace')


for p in (COMBINED, os.path.join(ROOT, 'src', 'kernel', 'forth.asm'),
          os.path.join(ROOT, 'forth', 'dict', 'window.fth'),
          os.path.join(ROOT, 'forth', 'dict', 'notepad.fth'), os.path.abspath(__file__)):
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else 'ABSENT'
    print(f'input sha256 {h}  {p}', flush=True)

lay = subprocess.run(['python3', 'tools/catalog_layout.py', 'UI-PARSER'], capture_output=True, text=True)
UIP = lay.stdout.split()[:2]
print(f'UI-PARSER in build/blocks.img: {UIP}', flush=True)

qemu_pid.kill_pidfile(PF)
shutil.copyfile(COMBINED, IDE)
q = subprocess.run(['qemu-system-i386', '-drive', f'file={COMBINED},format=raw,if=floppy', '-m', '256',
                    '-drive', f'file={IDE},format=raw,if=ide,index=1', '-display', 'none', '-snapshot',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                    '-monitor', f'tcp:127.0.0.1:{MON},server=on,wait=off',
                    '-daemonize', '-pidfile', PF], capture_output=True)
qemu_pid.check_launch(q, PF, PORT, 'window-focus')
try:
    s = ser.connect_and_sync(PORT, budget=60)

    def send(cmd, budget=30):
        reply, how = ser.send_until_prompt(s, cmd, budget=budget)
        if how != 'prompt':
            print(f'    (read of {cmd[:40]!r} ended by {how})', flush=True)
        return reply

    def raw(text, wait=1.0):
        """Bytes with no CR appended; what the guest echoes is read and shown."""
        s.sendall(text.encode('latin-1'))
        s.settimeout(0.1)
        buf, t0 = b'', time.time()
        while time.time() - t0 < wait:
            try:
                d = s.recv(65536)
                if d:
                    buf += d
            except socket.timeout:
                pass
        return buf.decode('ascii', 'replace')

    def key(k, wait=1.0):
        mon_cmd(f'sendkey {k}')
        return raw('', wait)

    def body(reply):
        return reply.split('\r\n', 1)[1] if '\r\n' in reply else ''

    SETUP_BAD = []

    def setup(cmd, budget=30):
        """A setup step: its reply must hold no `?`; U0 reports every one that did."""
        r = send(cmd, budget)
        if '?' in body(r):
            SETUP_BAD.append((cmd[:50], body(r).strip()[-60:]))
        return r

    def screen():
        """Rows 0-24 as saved by the monitor: read before the test sends any
        further console line, so its own output cannot move the band first."""
        dump = os.path.join(OUT, 'screen.bin')
        if os.path.exists(dump):
            os.unlink(dump)
        mon_cmd(f'pmemsave 0xB8000 4000 "{dump}"')
        for _ in range(20):
            if os.path.exists(dump) and os.path.getsize(dump) == 4000:
                break
            time.sleep(0.1)
        return open(dump, 'rb').read() if os.path.exists(dump) else b''

    def nums(reply):
        # control characters (a marker EMIT, an echoed 0x17) split tokens
        t = ''.join(' ' if ord(c) < 32 else c for c in body(reply))
        return t.replace('ok', ' ').split()

    v = nums(send('ALSO CATALOG-RESOLVER S" UI-PARSER" CATALOG-FIND .S PREVIOUS'))
    got = [x.strip('<>') for x in v if x.strip('<>')]     # .S: <first last -1 >
    ok = len(UIP) == 2 and got[:3] == UIP + ['-1']
    check('D0 block disk attached: CATALOG-FIND UI-PARSER gives its range from build/blocks.img',
          ok, f'guest {got}, image {UIP}')
    if not ok:
        print('  no block disk: stopping before any check that loads from blocks', flush=True)
        print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
        sys.exit(1)                   # the finally below stops QEMU
    send('DROP DROP DROP')

    for line in SETUP:
        setup(line)
    r = send('S" WINDOW" LOAD-VOCAB', budget=60)
    check('W0 WINDOW loads, no ?', '?' not in body(r), body(r).strip()[-120:])
    for line in HANDLERS:
        setup(line)

    # ---- the kernel, no hook ----
    v = nums(send('FOCUS-HOOK @ .'))
    check('K1 FOCUS-HOOK is 0 at boot', v[:1] == ['0'], f'{v}')
    v = nums(send('FOCUS-SWITCH .'))
    check('K2 FOCUS-SWITCH with no hook: 0, nothing runs', v[:1] == ['0'], f'{v}')

    # The console in rows 17-24, window 1 in rows 0-16.
    setup('8 WIN-CONSOLE')
    v = nums(setup('0 0 80 17 WIN-NEW .'))
    if v[:1] != ['1']:
        SETUP_BAD.append(('0 0 80 17 WIN-NEW .', f'{v}'))

    # The cursor follows the prompt: after PAGE the prompt is `ok ` at
    # (0, 17); the 14 typed characters end at column 17: cell 1377.
    send('PAGE')
    v = nums(send('CRTC@ 6 EMIT .'))
    check('K3 before Enter the hardware cursor is at the end of the typed line (1377)',
          v[:1] == ['1377'], f'CRTC {v}')

    v = nums(send("' TH 1 WIN-KEYS! FOCUS-HOOK @ ' WIN-SWITCH = ."))
    check('K4 WIN-KEYS! sets FOCUS-HOOK to WIN-SWITCH', v[:1] == ['-1'], f'{v}')

    # ---- serial Ctrl+W, mid-line ----
    send('PAGE')
    send('PAINT')
    raw('12')
    raw(CTRL_W)
    raw('abc')
    raw(CTRL_W)
    v = nums(send('3 . TN @ . TACT @ . TFS @ .'))
    check('S1 mid-line Ctrl+W: the handler reads abc, the line resumes: 123 3 1 0',
          v[:4] == ['123', '3', '1', '0'], f'{v}')
    u = nums(send('UNPAINTED .'))
    t = body(send('3 ROW0')).replace('ok', '').strip()
    check('S2 the window got the keys, rows 0-16 otherwise untouched: UNPAINTED 3, row 0 abc',
          u[:1] == ['3'] and t.startswith('abc'), f'unpainted {u}, row 0 {t!r}')
    v = nums(send('WIN-ACTIVE .'))
    check('S3 back in the console: WIN-ACTIVE 0', v[:1] == ['0'], f'{v}')

    # TH puts the cursor at (40, 5); returning, it goes back to the line's end.
    send('PAGE')
    raw('CRTC@ 6 EMIT .')
    raw(CTRL_W)
    raw('x')
    raw(CTRL_W)
    v = nums(send(''))
    check('S4 after the switch the hardware cursor is back at the line (1377, not 440)',
          v[:1] == ['1377'], f'{v}')

    # ---- PS/2 Ctrl+W ----
    raw('4')
    key('ctrl-w')
    raw('q')
    key('ctrl-w')
    v = nums(send('5 . TN @ .'))
    check('S5 PS/2 Ctrl+W in and out: 45 1', v[:2] == ['45', '1'], f'{v}')

    raw('1 WIN-FOCUS\r')
    raw('k')
    raw(CTRL_W, 2.0)
    v = nums(send('TN @ .'))
    check('S6 1 WIN-FOCUS runs the handler: TN 1', v[:1] == ['1'], f'{v}')

    # ---- ABORT inside the handler ----
    setup("' TH2 1 WIN-KEYS!")
    raw(CTRL_W)
    raw('z', 2.0)
    send('')
    # The ABORT skipped WIN-SWITCH's reset; WIN-ACTIVE must still say 0.
    a0 = nums(send('WIN-ACTIVE .'))
    setup("' TH 1 WIN-KEYS!")
    raw('7')
    raw(CTRL_W)
    raw('a')
    raw(CTRL_W)
    v = nums(send(' . TN @ . TACT @ . WIN-ACTIVE .'))
    check('E1 after an ABORT in a handler Ctrl+W still switches: 7 1', v[:2] == ['7', '1'], f'{v}')
    check('E2 after the ABORT WIN-ACTIVE names the console (0); the next switch: active 1, then 0',
          a0[:1] == ['0'] and v[2:4] == ['1', '0'], f'after ABORT {a0}, after the switch {v}')

    # ---- a form in window 1 ----
    # HELLO-APP's load ends in ONLY FORTH DEFINITIONS: the order is set
    # again after it. FORM-WIRE is GUI-HARVEST's, so HF compiles with it.
    setup('ONLY FORTH DEFINITIONS')   # a load's ALSOs need room: 8 entries
    setup('S" HELLO-APP" LOAD-VOCAB', budget=90)
    setup('ALSO HELLO-APP ALSO UI-PARSER ALSO GUI-HARVEST ALSO CATALOG-RESOLVER')
    setup(': HF S" HELLO-FORM" CATALOG-FIND DROP FORM-LOAD FORM-WIRE HA-FIND-WIDGETS ;')
    setup('PREVIOUS PREVIOUS PREVIOUS PREVIOUS HF')
    setup('ONLY FORTH DEFINITIONS DECIMAL ALSO HAL ALSO UI-CORE ALSO WINDOW')
    w = nums(send('WT-COUNT @ .'))
    check('F0 HELLO-FORM loaded: WT-COUNT > 0', w[:1] != [] and w[0].isdigit() and int(w[0]) > 0, f'{w}')
    setup("' WIN-FORM-KEYS 1 WIN-KEYS!")
    send('PAGE')
    send('PAINT BMARK')
    raw(CTRL_W, 2.0)
    raw(CTRL_W, 2.0)
    m = screen()
    t = ''.join(chr(c) for c in m[160 + 2:160 + 32:2])          # row 1, cols 1-15
    b = sum(1 for i in range(1600, 2000) if m[2 * i:2 * i + 2] == b'B\x07')
    check('F1 the form draws in window 1 and the band survives: Hello Form Test, BCOUNT 400',
          t == 'Hello Form Test' and b == 400, f'row 1 {t!r}, band B cells {b}')
    v = nums(send('WIN-ACTIVE .'))
    check('F2 Ctrl+W leaves the form: the console answers, WIN-ACTIVE 0', v[:1] == ['0'], f'{v}')

    # ---- NOTEPAD's editor ----
    setup("' TH 1 WIN-KEYS! 0 TN !")
    setup('ONLY FORTH DEFINITIONS')   # a load's ALSOs need room: 8 entries
    setup('S" NOTEPAD" LOAD-VOCAB', budget=90)

    # NOTEPAD borrows its search order's top slot for KB-MODS; the order
    # after the borrow must equal the order before it. The file ends in
    # ONLY FORTH DEFINITIONS, so a comparison around the whole load cannot
    # see this: the shipped file's own lines are replayed, its ALSO list,
    # ORDER, its borrow lines, ORDER.
    src = open(os.path.join(ROOT, 'forth', 'dict', 'notepad.fth')).read().split('\n')
    also = src[src.index('NOTEPAD DEFINITIONS') + 1:]
    also = also[:next(i for i, l in enumerate(also) if not l.startswith('ALSO '))]
    bor = [i for i, l in enumerate(src) if l.startswith('PREVIOUS ALSO PS2-KEYBOARD')]
    if bor and also:
        send('ONLY FORTH NOTEPAD')
        for line in also:
            send(line)
        before = body(send('ORDER')).replace('ok', '').strip()
        send(src[bor[0]])
        send(src[bor[0] + 1])
        send('DROP')                  # KB-MODS's address (the file's CONSTANT takes it)
        after = body(send('ORDER')).replace('ok', '').strip()
        check('O1 NOTEPAD\'s borrow restores its search order: ORDER before = ORDER after',
              bool(before) and before == after, f'{before!r} / {after!r}')
    else:
        check('O1 NOTEPAD\'s borrow restores its search order', False,
              f'borrow lines {bor}, ALSO lines {len(also)} in notepad.fth')
    setup('ONLY FORTH DEFINITIONS DECIMAL ALSO HAL ALSO UI-CORE ALSO WINDOW')
    setup('ALSO NOTEPAD')
    raw('NOTEPAD-RUN\r', 3.0)
    raw('1', 2.0)                      # button 1 = New: edit mode (RAW-SCAN)
    key('ctrl-w', 2.0)
    raw('n')
    raw(CTRL_W, 2.0)
    key('esc', 2.0)                    # leave edit mode
    r = raw('\x1b', 3.0)               # the form quits
    v = nums(send('TN @ . DEPTH .'))
    n1 = v[:2] == ['1', '0']
    check('N1 Ctrl+W in NOTEPAD\'s editor switches: TN 1, DEPTH 0', n1 and 'NOTEPAD closed' in r,
          f'{v}, {r.strip()[-60:]!r}')
    # The switch's key wait took Ctrl's release from the PS/2 ring, which
    # NOTEPAD's RAW-SCAN never saw: NOTEPAD clears Ctrl itself.
    v = nums(send('ALSO PS2-KEYBOARD KB-MODS @ 2 AND . PREVIOUS'))
    check('N3 after N1\'s switch NOTEPAD\'s Ctrl is clear: KB-MODS Ctrl bit 0',
          n1 and v[:1] == ['0'], f'N1 {n1}, {v}')

    # NOTEPAD as the handler: inside the switch its Ctrl+W is ignored.
    setup("' NOTEPAD-RUN 1 WIN-KEYS! 0 TN !")
    raw(CTRL_W, 3.0)
    raw('1', 2.0)
    key('ctrl-w', 2.0)
    key('esc', 2.0)
    r = raw('\x1b', 3.0)
    v = nums(send('TN @ . WIN-ACTIVE . DEPTH .'))
    check('N2 NOTEPAD inside a switch: Ctrl+W ignored, Esc leaves; TN 0, WIN-ACTIVE 0, DEPTH 0',
          v[:3] == ['0', '0', '0'] and 'NOTEPAD closed' in r, f'{v}, {r.strip()[-60:]!r}')
    check('U0 every setup step replied without ?', not SETUP_BAD, f'{SETUP_BAD[:6]}')
    s.close()
finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
sys.exit(0 if FAIL == 0 else 1)
