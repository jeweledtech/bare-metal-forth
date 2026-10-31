#!/usr/bin/env python3
"""A form per window, Ctrl+W around them (private TASK_WINDOW_STEP3A).
Fifteen checks: W0-W14.

  python3 tests/test_window_forms.py <serial-port>     (cwd: tree root)

WIN-FORM! and WIN-DIALOG! give the loaded form to a window: WINDOW saves
it in the window's own area (PHYS-ALLOC) when the window loses the keys
and restores it when it gets them back. Ctrl+W runs each window with a
key handler in id order, then the console; a window with no handler is
skipped. A form that passes its window's edge is refused by name, and
so is a form PHYS-ALLOC has no memory for, the window left as it was.

Fixtures under build/window-forms.d/fx (never forth/dict or
build/combined.img), as test_abort_routes.py builds its own: a copy of
forth/dict plus three forms, WF-TOP (window 1, rows 0-7), WF-DLG (window
3, rows 10-16, a drop-down) and WF-WIDE (a drop-down whose list passes
window 3's bottom), packed by write-catalog into a copy of
build/blocks.img, booted after build/bmforth.img with an IDE copy (W0
checks it is attached). The screen is read from 0xB8000 by the monitor
(a unix socket in that directory). Keys reach the guest over serial.

W3-W11 send keys a window reads; with no form given (W2 failed) they
would reach the console's line editor instead, so they are not sent and
each is recorded as failed, not run.
"""
import atexit, glob, hashlib, os, shutil, socket, subprocess, sys, time

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import qemu_pid
import serial as ser
import catalog_layout

PORT = int(sys.argv[1])
B = os.path.join(ROOT, 'build')
OUT = os.path.join(B, 'window-forms.d')
FX = os.path.join(OUT, 'fx')
PF = os.path.join(OUT, 'qemu.pid')
MON = os.path.join(OUT, 'monitor.sock')
DUMP = os.path.join(OUT, 'screen.bin')
CTRL_W, TAB, ENTER, SPACE = '\x17', '\t', '\r', ' '
INV, NORM = 0x70, 0x07                 # ATTR-INV, ATTR-NORM (ui-core.fth 93-94)
B_CELL = 1858                          # 'B' on light grey, BMARK's cell
os.makedirs(OUT, exist_ok=True)

HDR = """\\ ============================================
\\ CATALOG: {}
\\ CATEGORY: form
\\ PLATFORM: x86
\\ SOURCE: hand-written
\\ CONFIDENCE: high
\\ ============================================
\\ Fixture for TASK_WINDOW_STEP3A.
"""
FIX = {
    'wf-top.fth': HDR.format('WF-TOP') + """FORM: wftop
LABEL: 0 0 "Top"
BUTTON: 2 2 8 "One"
BUTTON: 12 2 8 "Two"
BUTTON: 22 2 8 "Three"
END-FORM:
""",
    'wf-dlg.fth': HDR.format('WF-DLG') + """FORM: wfdlg
LABEL: 0 10 "Dialog"
DROPBOX: 2 11 14 ""
ITEM: "Red"
ITEM: "Green"
ITEM: "Blue"
ITEM: "Grey"
BUTTON: 30 11 8 "OK" 1
BUTTON: 40 11 8 "Cancel" 2
END-FORM:
""",
    'wf-wide.fth': HDR.format('WF-WIDE') + """FORM: wfwide
DROPBOX: 2 15 14 ""
ITEM: "A"
ITEM: "B"
ITEM: "C"
ITEM: "D"
ITEM: "E"
END-FORM:
""",
}

SETUP = [
    'ONLY FORTH DEFINITIONS DECIMAL ALSO HAL',
    # rows 20-24 of the band: 'B' (as test_window_focus F1)
    ': BMARK 2000 1600 DO 1858 FB-BASE I 2 * + W! LOOP ;',
]
ORDER = 'ONLY FORTH DEFINITIONS DECIMAL ALSO HAL ALSO UI-CORE ALSO WINDOW'


def load(name):
    return (f'ALSO UI-PARSER ALSO CATALOG-RESOLVER S" {name}" CATALOG-FIND DROP FORM-LOAD '
            'PREVIOUS PREVIOUS WT-COUNT @ .')


PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}', flush=True)
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''), flush=True)


# ---- fixtures
for need in ('bmforth.img', 'blocks.img', 'vbr.bin'):
    if not os.path.exists(os.path.join(B, need)):
        sys.exit(f'NO INPUT: build/{need} (make combined)')
qemu_pid.kill_pidfile(PF)
if os.path.isdir(FX):
    shutil.rmtree(FX)
os.makedirs(os.path.join(FX, 'dict'))
for f in glob.glob(os.path.join(ROOT, 'forth', 'dict', '*.fth')):
    shutil.copy(f, os.path.join(FX, 'dict'))
for f, text in FIX.items():
    open(os.path.join(FX, 'dict', f), 'w').write(text)
BLOCKS = os.path.join(FX, 'blocks.img')
shutil.copy(os.path.join(B, 'blocks.img'), BLOCKS)
r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'write-catalog.py'), BLOCKS,
                    os.path.join(FX, 'dict') + '/', '--raw', f'VBR-TEMPLATE={os.path.join(B, "vbr.bin")}'],
                   capture_output=True, text=True)
if r.returncode != 0:
    sys.exit('FIXTURE: write-catalog failed:\n' + (r.stdout + r.stderr)[-1200:])
IMG, IDE = os.path.join(FX, 'image.img'), os.path.join(FX, 'ide.img')
open(IMG, 'wb').write(open(os.path.join(B, 'bmforth.img'), 'rb').read() + open(BLOCKS, 'rb').read())
shutil.copy(IMG, IDE)
for p in (IMG, IDE, MON, DUMP):
    assert os.path.realpath(p).startswith(os.path.realpath(OUT) + os.sep), p
WFT = [str(n) for n in catalog_layout.vocab_blocks('WF-TOP', BLOCKS)]

for p in (os.path.join(B, 'bmforth.img'), os.path.join(B, 'blocks.img'), IMG,
          os.path.join(ROOT, 'forth', 'dict', 'window.fth'),
          os.path.join(ROOT, 'forth', 'dict', 'dialog.fth'),
          os.path.join(ROOT, 'forth', 'dict', 'hardware.fth'), os.path.abspath(__file__)):
    print(f'input sha256 {hashlib.sha256(open(p, "rb").read()).hexdigest()}  {p}', flush=True)
print(f'WF-TOP in the fixture catalog: {WFT}', flush=True)


def mon(cmd):
    m = socket.socket(socket.AF_UNIX)
    m.connect(MON)
    m.settimeout(2)
    try:
        m.recv(4096)
    except socket.timeout:
        pass
    m.sendall(cmd.encode() + b'\n')
    time.sleep(0.5)
    m.close()


def screen():
    """Rows 0-24, 2 bytes a cell, read before the next console line."""
    if os.path.exists(DUMP):
        os.remove(DUMP)
    mon(f'pmemsave 0xB8000 4000 "{DUMP}"')
    for _ in range(50):
        if os.path.exists(DUMP) and os.path.getsize(DUMP) == 4000:
            break
        time.sleep(0.1)
    return open(DUMP, 'rb').read() if os.path.exists(DUMP) else b''


def text(m, col, row, n):
    return ''.join(chr(m[2 * (row * 80 + col + i)]) for i in range(n)) if len(m) == 4000 else ''


def attrs(m, col, row, n):
    return {m[2 * (row * 80 + col + i) + 1] for i in range(n)} if len(m) == 4000 else set()


def at(m, col, row, word, attr):
    """word at col row, every cell in attr."""
    return text(m, col, row, len(word)) == word and attrs(m, col, row, len(word)) == {attr}


def bcount(m):
    return sum(1 for i in range(1600, 2000)
               if len(m) == 4000 and m[2 * i] | (m[2 * i + 1] << 8) == B_CELL)


qemu_pid.kill_pidfile(PF)
if os.path.exists(MON):
    os.remove(MON)
atexit.register(qemu_pid.kill_pidfile, PF)
q = subprocess.run(['qemu-system-i386', '-m', '256',
                    '-drive', f'file={IMG},format=raw,if=floppy',
                    '-drive', f'file={IDE},format=raw,if=ide,index=1', '-snapshot',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                    '-monitor', f'unix:{MON},server=on,wait=off',
                    '-display', 'none', '-daemonize', '-pidfile', PF], capture_output=True)
qemu_pid.check_launch(q, PF, PORT, 'window-forms')
try:
    s = ser.connect_and_sync(PORT, budget=60)

    def send(cmd, budget=60):
        reply, how = ser.send_until_prompt(s, cmd, budget=budget)
        b = reply.split('\r\n', 1)[1] if '\r\n' in reply else ''
        print(f'>>> {cmd}\n    {b.strip()[-200:]!r}  [{how}]', flush=True)
        return b

    def raw(t, wait=2.0):
        """Bytes with no CR appended; what the guest echoes is read and dropped."""
        s.sendall(t.encode('latin-1'))
        s.settimeout(0.1)
        t0 = time.time()
        while time.time() - t0 < wait:
            try:
                s.recv(65536)
            except socket.timeout:
                pass

    def nums(b):
        # control characters (an echoed 0x17) split tokens
        t = ''.join(' ' if ord(c) < 32 else c for c in b)
        return t.replace('ok', ' ').split()

    SETUP_BAD = []

    def setup(cmd, budget=60):
        b = send(cmd, budget)
        if '?' in b:
            SETUP_BAD.append((cmd[:50], b.strip()[-60:]))
        return b

    v = nums(send('ALSO CATALOG-RESOLVER S" WF-TOP" CATALOG-FIND .S DROP DROP DROP PREVIOUS'))
    got = [x.strip('<>') for x in v if x.strip('<>')]     # .S: <first last -1 >
    ok = len(WFT) == 2 and got[:3] == WFT + ['-1']
    check('W0 (control) fixture catalog attached: CATALOG-FIND WF-TOP gives its range',
          ok, f'guest {got}, image {WFT}')
    if not ok:
        print('  no fixture catalog: stopping before any check that loads from blocks', flush=True)
        print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
        sys.exit(1)

    for line in SETUP:
        setup(line)
    b = send('S" WINDOW" LOAD-VOCAB', budget=120)
    d = nums(send('DEPTH .'))
    check('W1 (control) WINDOW loads: no ?, DEPTH 0', '?' not in b and d[:1] == ['0'],
          f'{b.strip()[-120:]!r} depth {d}')
    setup(ORDER)

    # ---- windows 1 (rows 0-7), 2 (rows 8-9, no handler), 3 (rows 10-16)
    setup('8 WIN-CONSOLE')
    ids = nums(setup('0 0 80 8 WIN-NEW . 0 8 80 2 WIN-NEW . 0 10 80 7 WIN-NEW .'))
    if ids[:3] != ['1', '2', '3']:
        SETUP_BAD.append(('WIN-NEW x3', f'{ids}'))
    setup(load('WF-TOP'))
    r1 = send('1 WIN-FORM!')
    setup(load('WF-DLG'))
    r2 = send('3 WIN-DIALOG!')
    h = nums(send("1 WIN-HANDLER ' WIN-FORM-KEYS = . 3 WIN-HANDLER ' WIN-DIALOG-KEYS = . 2 WIN-HANDLER ."))
    w2 = ('?' not in r1 + r2 and 'WINDOW:' not in r1 + r2 and h[:3] == ['-1', '-1', '0'])
    check('W2 1 WIN-FORM!, 3 WIN-DIALOG! accepted: no ?, no refusal; handlers set, window 2 none',
          w2, f'{r1.strip()[-60:]!r} {r2.strip()[-60:]!r} handlers {h}')

    KEYS = ['W3 Ctrl+W: window 1 drawn, Top at row 0, One inverse',
            'W4 Tab Tab: Three inverse, One plain',
            'W5 Ctrl+W: window 2 skipped, window 3 drawn (Dialog at row 10), rows 8-9 untouched',
            'W6 Enter Space: list open in rows 12-15, Green inverse',
            'W7 Ctrl+W: the console, WIN-ACTIVE 0, BCOUNT 400',
            'W8 Ctrl+W: window 1 again, Three still inverse',
            'W9 Ctrl+W: window 3 again, list open, Green still inverse',
            'W10 Enter: Green in the box, list closed; Ctrl+W: the console, WIN-ACTIVE 0',
            'W11 WF-WIDE refused (form outside window); the cycle draws window 3 (Green in its box)']
    if not w2:
        for k in KEYS:
            check(f'{k} (not run: W2 failed)', False)
    else:
        send('PAGE')
        send('BMARK')
        raw(CTRL_W)
        m = screen()
        check(KEYS[0], at(m, 0, 0, 'Top', NORM) and at(m, 3, 2, 'One', INV),
              f'row 0 {text(m, 0, 0, 3)!r}, One attrs {attrs(m, 3, 2, 3)}')
        raw(TAB)
        raw(TAB)
        m4 = screen()
        check(KEYS[1], at(m4, 23, 2, 'Three', INV) and at(m4, 3, 2, 'One', NORM),
              f'Three attrs {attrs(m4, 23, 2, 5)}, One attrs {attrs(m4, 3, 2, 3)}')
        raw(CTRL_W)
        m = screen()
        check(KEYS[2], at(m, 0, 10, 'Dialog', NORM) and len(m) == 4000 and m[1280:1600] == m4[1280:1600],
              f'row 10 {text(m, 0, 10, 6)!r}, rows 8-9 same {m[1280:1600] == m4[1280:1600]}')
        raw(ENTER)
        raw(SPACE)
        m = screen()
        rows = [text(m, 3, 12 + i, len(w)) for i, w in enumerate(('Red', 'Green', 'Blue', 'Grey'))]
        check(KEYS[3], rows == ['Red', 'Green', 'Blue', 'Grey'] and at(m, 3, 13, 'Green', INV)
              and at(m, 3, 12, 'Red', NORM), f'rows 12-15 {rows}, Green attrs {attrs(m, 3, 13, 5)}')
        raw(CTRL_W)
        m = screen()
        bc = bcount(m)
        a = nums(send('WIN-ACTIVE .'))
        check(KEYS[4], a[:1] == ['0'] and bc == 400, f'WIN-ACTIVE {a}, BCOUNT {bc}')
        raw(CTRL_W)
        m = screen()
        check(KEYS[5], at(m, 23, 2, 'Three', INV) and at(m, 3, 2, 'One', NORM),
              f'Three attrs {attrs(m, 23, 2, 5)}')
        raw(CTRL_W)
        m = screen()
        check(KEYS[6], text(m, 3, 12, 3) == 'Red' and at(m, 3, 13, 'Green', INV),
              f'row 12 {text(m, 3, 12, 3)!r}, Green attrs {attrs(m, 3, 13, 5)}')
        raw(ENTER)
        m = screen()
        boxed = at(m, 3, 11, 'Green', INV) or at(m, 3, 11, 'Green', NORM)
        closed = text(m, 2, 12, 14) == ' ' * 14
        raw(CTRL_W)
        a = nums(send('WIN-ACTIVE .'))
        check(KEYS[7], boxed and closed and a[:1] == ['0'],
              f'box {text(m, 3, 11, 5)!r}, row 12 {text(m, 2, 12, 14)!r}, WIN-ACTIVE {a}')
        setup(load('WF-WIDE'))
        r = send('3 WIN-DIALOG!')
        setup(ORDER)
        raw(CTRL_W)
        raw(CTRL_W)
        m = screen()
        raw(CTRL_W)              # back to the console for W12's lines (not a check)
        check(KEYS[8], 'WINDOW: form outside window' in r and at(m, 0, 10, 'Dialog', NORM)
              and text(m, 3, 11, 5) == 'Green', f'{r.strip()[-60:]!r}, box {text(m, 3, 11, 5)!r}')

    # ---- W12: no memory, the window left as it was
    setup(ORDER)
    w4 = nums(setup('0 0 80 8 WIN-NEW .'))
    send('HEX ALSO HARDWARE 200000 PHYS-HEAP @ - PHYS-ALLOC U. PHYS-HEAP @ . PREVIOUS DECIMAL')
    setup(load('WF-TOP'))
    r = send('HEX 4 WIN-FORM!')
    send('DECIMAL')
    setup(ORDER)
    v = nums(send('4 WIN-HANDLER . 4 WIN-AREA . DEPTH .'))
    check('W12 no memory: PHYS: pool full below 200000, WINDOW: no memory for the form; '
          'window 4 no handler, no area',
          'PHYS: pool full below 200000' in r and 'WINDOW: no memory for the form' in r
          and w4[:1] == ['4'] and v[:3] == ['0', '0', '0'], f'{r.strip()[-90:]!r} id {w4} after {v}')

    # ---- W13: past WIN-MAX
    c = nums(send('0 0 80 8 WIN-NEW . 0 0 80 8 WIN-NEW . 0 0 80 8 WIN-NEW . WIN-COUNT @ .'))
    r = send('0 0 80 8 WIN-NEW')
    n = nums(send('WIN-COUNT @ .'))
    check('W13 past WIN-MAX: WINDOW: table full, WIN-COUNT 8',
          'WINDOW: table full' in r and n[:1] == ['8'], f'{c} {r.strip()[-40:]!r} count {n}')

    d = nums(send('DEPTH .'))
    check('W14 DEPTH 0 at the end', d[:1] == ['0'], f'{d}')
    if SETUP_BAD:
        print(f'  setup lines with ?: {SETUP_BAD}', flush=True)
finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
sys.exit(0 if FAIL == 0 else 1)
