#!/usr/bin/env python3
"""Every abort through abort_common, and Ctrl+C read by KEY (private
TASK_ABORT_ROUTES). Sixteen checks: D0, R1-R10, E0, E1, B0-B2.

  python3 tests/test_abort_routes.py <serial-port>     (cwd: tree root)

ABORT and every fired ABORT" used to reset the stacks and the input only:
no definition roll-back, no ABORT-HOOK (so a load they stopped stayed
loaded, with the file's search order and CURRENT), and no EMBED ABORTED
when they stopped the boot. They now go through abort_common, as an
undefined word does; so does a dictionary refusal (DICT FULL,
UNTERMINATED STRING: dict_refuse_ ends in ABORT), and inside a load it
rolls the load back whole, HERE and LATEST as before it (R5-R10,
private TASK_REFUSE_LOAD_ROLLBACK). And a Ctrl+C read by KEY (a window's key handler)
used to leave the break flag set, so the console's next line was thrown
away as a break; only read_line's own break sets it now.

Fixtures under build/abort-routes.d/fx (never forth/dict or
build/combined.img), as test_interp_abort.py builds its own:
  - a catalog: a copy of forth/dict plus ABORT-PROBE (fires ABORT" while
    loading), ABORT-PROBE2 (a plain ABORT), ABORT-PROBE3 (DICT FULL
    outside a definition) and ABORT-PROBE4 (UNTERMINATED STRING inside
    one, its last line: the S" walk reaches the block's end), packed by write-catalog
    into a copy of build/blocks.img, booted after build/bmforth.img with
    an IDE copy (D0 checks it is attached);
  - two kernels, nasm -dEMBED_FILE: EMBED_VOCABS plus one more line at
    the end of the stream, an undefined word (the control, E0) or a fired
    ABORT" (E1), booted from floppy alone.
The serial port waits for this script (wait=on), so each boot transcript
is read whole.
"""
import glob, hashlib, os, shutil, socket, subprocess, sys, time

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import qemu_pid
import serial as ser
import catalog_layout

PORT = int(sys.argv[1])
B = os.path.join(ROOT, 'build')
OUT = os.path.join(B, 'abort-routes.d')
FX = os.path.join(OUT, 'fx')
PF = os.path.join(OUT, 'qemu.pid')
ASM = os.path.join(ROOT, 'src', 'kernel', 'forth.asm')
CTRL_W, CTRL_C = '\x17', '\x03'
os.makedirs(OUT, exist_ok=True)

FIX_AP = r"""\ CATALOG: ABORT-PROBE
\ abort-routes fixture (build/abort-routes.d only)
VOCABULARY ABORT-PROBE
ABORT-PROBE DEFINITIONS
: AP-WORD 1 ;
: AP-FAIL 1 ABORT" ABORT-PROBE: refused" ;
AP-FAIL
FORTH DEFINITIONS
"""
FIX_AP2 = r"""\ CATALOG: ABORT-PROBE2
\ abort-routes fixture (build/abort-routes.d only)
VOCABULARY ABORT-PROBE2
ABORT-PROBE2 DEFINITIONS
: AP2-WORD 1 ;
: AP2-FAIL ABORT ;
AP2-FAIL
FORTH DEFINITIONS
"""
FIX_AP3 = r"""\ CATALOG: ABORT-PROBE3
\ abort-routes fixture (build/abort-routes.d only)
VOCABULARY ABORT-PROBE3
ABORT-PROBE3 DEFINITIONS
: AP3-WORD 1 ;
HEX 100000 ALLOT
FORTH DEFINITIONS
"""
FIX_AP4 = r"""\ CATALOG: ABORT-PROBE4
\ abort-routes fixture (build/abort-routes.d only)
VOCABULARY ABORT-PROBE4
ABORT-PROBE4 DEFINITIONS
: AP4-WORD 1 ;
: AP4-FAIL S" never closed
"""
EMBED_CTL = 'ZZEMBEDNOPE\n'
EMBED_NEG = ': EB-FAIL 1 ABORT" EMBED-PROBE: refused" ;\nEB-FAIL\n'

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
for need in ('bmforth.img', 'boot.bin', 'blocks.img', 'vbr.bin'):
    if not os.path.exists(os.path.join(B, need)):
        sys.exit(f'NO INPUT: build/{need} (make combined)')
qemu_pid.kill_pidfile(PF)
if os.path.isdir(FX):
    shutil.rmtree(FX)
os.makedirs(os.path.join(FX, 'dict'))
for f in glob.glob(os.path.join(ROOT, 'forth', 'dict', '*.fth')):
    shutil.copy(f, os.path.join(FX, 'dict'))
open(os.path.join(FX, 'dict', 'abort-probe.fth'), 'w').write(FIX_AP)
open(os.path.join(FX, 'dict', 'abort-probe2.fth'), 'w').write(FIX_AP2)
open(os.path.join(FX, 'dict', 'abort-probe3.fth'), 'w').write(FIX_AP3)
open(os.path.join(FX, 'dict', 'abort-probe4.fth'), 'w').write(FIX_AP4)
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
APR = [str(n) for n in catalog_layout.vocab_blocks('ABORT-PROBE', BLOCKS)]

embed = subprocess.run(['make', '-s', 'print-embed-vocabs'], capture_output=True, text=True).stdout.split()


def kernel(tag, extra):
    """boot.bin + a kernel whose embedded stream is EMBED_VOCABS, then `extra`."""
    fx = os.path.join(FX, f'embed-{tag}.fth')
    open(fx, 'w').write(extra)
    eb = os.path.join(FX, f'embedded-{tag}.bin')
    subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'embed-vocabs.py'), eb] +
                   [os.path.join(ROOT, v) for v in embed] + [fx], check=True, capture_output=True)
    kb = os.path.join(FX, f'kernel-{tag}.bin')
    subprocess.run(['nasm', '-f', 'bin', f'-dEMBED_FILE="{eb}"', '-o', kb, ASM], check=True)
    img = os.path.join(FX, f'{tag}.img')
    open(img, 'wb').write(open(os.path.join(B, 'boot.bin'), 'rb').read() + open(kb, 'rb').read())
    return img


CTL_IMG, NEG_IMG = kernel('control', EMBED_CTL), kernel('negative', EMBED_NEG)

for p in (os.path.join(B, 'bmforth.img'), IMG, CTL_IMG, NEG_IMG, ASM,
          os.path.join(ROOT, 'forth', 'dict', 'catalog-resolver.fth'), os.path.abspath(__file__)):
    print(f'input sha256 {hashlib.sha256(open(p, "rb").read()).hexdigest()}  {p}', flush=True)
print(f'ABORT-PROBE in the fixture catalog: {APR}', flush=True)


def boot(drives, role):
    """Start QEMU, read its boot transcript to the prompt; (socket, transcript)."""
    qemu_pid.kill_pidfile(PF)
    err = os.path.join(OUT, f'qemu-{role}.err')
    proc = subprocess.Popen(['qemu-system-i386'] + drives + ['-m', '256', '-display', 'none', '-snapshot',
                             '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=on', '-pidfile', PF],
                            stdout=subprocess.DEVNULL, stderr=open(err, 'w'))
    qemu_pid.wait_started(proc, PF, PORT, role, err)
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
    t = buf.decode('ascii', 'replace')
    print(f'    ({role} boot: {len(t)} bytes; tail {t[-120:]!r})', flush=True)
    return s, t


try:
    # ---- the fixture boot: loads that abort
    s, _ = boot(['-drive', f'file={IMG},format=raw,if=floppy',
                 '-drive', f'file={IDE},format=raw,if=ide,index=1'], 'abort-routes')

    def send(cmd, budget=30):
        reply, how = ser.send_until_prompt(s, cmd, budget=budget)
        if how != 'prompt':
            print(f'    (read of {cmd[:40]!r} ended by {how})', flush=True)
        return reply

    def raw(text, wait=1.0):
        s.sendall(text.encode())
        buf, t0 = b'', time.time()
        while time.time() - t0 < wait:
            try:
                d = s.recv(65536)
                if d:
                    buf += d
            except socket.timeout:
                pass
        return buf.decode('ascii', 'replace')

    def body(reply):
        return reply.split('\r\n', 1)[1] if '\r\n' in reply else ''

    def nums(reply):
        # control characters (an echoed 0x17) split tokens
        t = ''.join(' ' if ord(c) < 32 else c for c in body(reply))
        return t.replace('ok', ' ').split()

    def order():
        """The entries ORDER prints (top first), and the Compile cell."""
        t = body(send('ORDER')).replace('ok', ' ')
        if 'Search:' not in t or 'Compile:' not in t:
            return None
        a, b = t.split('Search:', 1)[1].split('Compile:', 1)
        return a.split(), b.split()[:1]

    v = nums(send('ALSO CATALOG-RESOLVER S" ABORT-PROBE" CATALOG-FIND .S PREVIOUS'))
    got = [x.strip('<>') for x in v if x.strip('<>')]     # .S: <first last -1 >
    ok = len(APR) == 2 and got[:3] == APR + ['-1']
    check('D0 fixture catalog attached: CATALOG-FIND ABORT-PROBE gives its range', ok,
          f'guest {got}, image {APR}')
    if not ok:
        print('  no fixture catalog: stopping before any check that loads from blocks', flush=True)
        print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
        sys.exit(1)                   # the finally below stops QEMU
    send('DROP DROP DROP')

    def probe(name, msg, rn, on, wn=None):
        send('ONLY FORTH ALSO HAL DEFINITIONS ALSO UI-CORE')
        before = order()
        if wn:
            h0 = nums(send('DECIMAL HERE @ . LATEST @ .'))[:2]
        r = body(send(f'S" {name}" LOAD-VOCAB', budget=60))
        print(f'    ({name}: {r.strip()[-90:]!r})', flush=True)
        after = order()
        if wn:
            h1 = nums(send('DECIMAL HERE @ . LATEST @ .'))[:2]
        p = nums(send(f'ALSO CATALOG-RESOLVER S" {name}" VOCAB-PRESENT? . PREVIOUS'))
        check(f'{rn} {name} aborts while loading: {msg + ", " if msg else ""}rolled back, absent (0)',
              (not msg or msg in r) and f'{name} rolled back' in r and p[:1] == ['0'],
              f'{r.strip()[-90:]!r}; present {p[:1]}')
        check(f'{on} after it the caller\'s order and CURRENT are back', before is not None and before == after,
              f'{before} -> {after}')
        if wn:
            check(f'{wn} rolled back whole: HERE and LATEST as before the load', len(h0) == 2 and h0 == h1,
                  f'{h0} -> {h1}')

    probe('ABORT-PROBE', 'ABORT-PROBE: refused', 'R1', 'R2')
    probe('ABORT-PROBE2', '', 'R3', 'R4')
    # a dictionary refusal inside the load: outside a definition, then inside one
    probe('ABORT-PROBE3', 'DICT FULL', 'R5', 'R6', 'R7')
    probe('ABORT-PROBE4', 'UNTERMINATED STRING', 'R8', 'R9', 'R10')

    # ---- Ctrl+C read by KEY inside a switch (TH as test_window_focus)
    bad = []
    for cmd in ('ONLY FORTH DEFINITIONS DECIMAL ALSO HAL', 'S" WINDOW" LOAD-VOCAB',
                'ALSO UI-CORE ALSO WINDOW', 'VARIABLE TN VARIABLE TACT VARIABLE TFS',
                ': TH 0 TN ! WIN-ACTIVE TACT ! FOCUS-SWITCH TFS ! 40 5 CURSOR-AT'
                ' BEGIN KEY DUP 23 = IF DROP EXIT THEN TN @ 0 1 WIN-AT C! 1 TN +! AGAIN ;',
                '0 0 80 17 WIN-NEW .', "' TH 1 WIN-KEYS!"):
        r = body(send(cmd, budget=60))
        if '?' in r:
            bad.append((cmd[:40], r.strip()[-60:]))
    raw(CTRL_W)
    raw('a')
    raw(CTRL_W)
    r = send('11 22 + .')
    check('B0 (control) Ctrl+W, a, Ctrl+W, then 11 22 + . prints 33', not bad and '33' in nums(r),
          f'setup {bad}; {body(r).strip()[:60]!r}')
    raw(CTRL_W)
    raw(CTRL_C)
    raw(CTRL_W)
    r = send('44 55 + .')
    check('B1 Ctrl+C read by the window\'s KEY: the next console line runs (99, no BREAK)',
          '99' in nums(r) and 'BREAK' not in r, f'{body(r).strip()[:60]!r}')
    raw('12')
    b2 = raw(CTRL_C)
    r = send('66 77 + .')
    check('B2 (control) Ctrl+C at the prompt still discards its line (BREAK); the next runs (143)',
          'BREAK' in b2 and '143' in nums(r), f'{b2.strip()[:40]!r}; {body(r).strip()[:60]!r}')
    s.close()

    # ---- the embedded stream stops the boot
    s, t = boot(['-drive', f'file={CTL_IMG},format=raw,if=floppy'], 'abort-routes-ctl')
    s.close()
    check('E0 (control) an undefined embedded word: EMBED ABORTED at ZZEMBEDNOPE, then the prompt',
          'EMBED ABORTED at ZZEMBEDNOPE' in t and t.endswith('ok '), f'{t[-120:]!r}')
    s, t = boot(['-drive', f'file={NEG_IMG},format=raw,if=floppy'], 'abort-routes-neg')
    s.close()
    check('E1 a fired embedded ABORT": its message and EMBED ABORTED at, then the prompt',
          'EMBED-PROBE: refused' in t and 'EMBED ABORTED at' in t and t.endswith('ok '), f'{t[-120:]!r}')
finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
sys.exit(0 if FAIL == 0 else 1)
