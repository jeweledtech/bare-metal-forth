#!/usr/bin/env python3
"""Interpreter correctness (docs/TASK_INTERPRETER_CORRECTNESS.md): an
undefined word aborts and discards the rest of its input; `(` typed over
serial ends at `)` or end of line; `."` and `.(` print in interpret mode.

  python3 tests/test_interp_abort.py <port>

Harmless words only: ZZNOPE is never defined. Fixture image under
build/test-interp.d (never forth/dict or build/combined.img):
  - three fixture vocabularies packed by write-catalog into a copy of
    build/blocks.img: IA-BAD (REQUIRES: IA-GOOD; an undefined word, then
    `: IAB-AFTER 1 ;`;
    the host later blanks the undefined word on the IDE copy), IA-GOOD
    (`42 CONSTANT IAG`) and IA-VEC (installs its own block writer, then
    an undefined word: its rollback must be refused);
  - three raw staged blocks past the catalog: `ZZNOPE  6 .` / `8 .`,
    `11 .`, and `." BANNER-TXT" CR`;
  - a control kernel whose embedded stream starts with ZZCENSUS (U9),
    built from a copy of hardware.fth with nasm -dEMBED_FILE, booted
    from floppy alone.
The checks assert the fixed behaviour. Predictions for today's kernel are
written before the run, in the evidence directory the task doc names.
"""
import atexit, glob, hashlib, os, re, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid               # noqa: E402
import serial as ser          # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4468
B = os.path.join(ROOT, 'build')
D = os.path.join(B, 'test-interp.d')
ASM = os.path.join(ROOT, 'src', 'kernel', 'forth.asm')
src = open(ASM).read()
HEADER = int(re.search(r'^BOOT_SECTOR_SIZE\s+equ\s+(\d+)', src, re.M).group(1)) + \
    int(re.search(r'^KERNEL_PADDED_SIZE\s+equ\s+0x([0-9A-Fa-f]+)', src, re.M).group(1), 16)
SIG = re.compile(r'(\S+) \? ')
FIX_BAD = r"""\ CATALOG: IA-BAD
\ interpreter-abort fixture (build/test-interp.d only)
\ REQUIRES: IA-GOOD
VOCABULARY IA-BAD
IA-BAD DEFINITIONS
ZZNOPE
: IAB-AFTER 1 ;
FORTH DEFINITIONS
"""
FIX_GOOD = r"""\ CATALOG: IA-GOOD
\ interpreter-abort fixture (build/test-interp.d only)
VOCABULARY IA-GOOD
IA-GOOD DEFINITIONS
42 CONSTANT IAG
FORTH DEFINITIONS
"""
FIX_VEC = r"""\ CATALOG: IA-VEC
\ fixture: installs its own block writer, then fails
VOCABULARY IA-VEC
IA-VEC DEFINITIONS
: IAV-W 2DROP 1 ;
' IAV-W BLK-WRITER!
ZZNOPE
FORTH DEFINITIONS
"""
FIX_DEPFAIL = r"""\ CATALOG: IA-DEPFAIL
\ interpreter-abort fixture: a dependency that fails
VOCABULARY IA-DEPFAIL
IA-DEPFAIL DEFINITIONS
ZZNOPE
FORTH DEFINITIONS
"""
FIX_OUTER = r"""\ CATALOG: IA-OUTER
\ fixture: requires a dependency that fails
\ REQUIRES: IA-DEPFAIL
VOCABULARY IA-OUTER
IA-OUTER DEFINITIONS
1 CONSTANT IAO
FORTH DEFINITIONS
"""
failures, checks = [], 0


def check(label, cond, detail='', fatal=False):
    global checks
    checks += 1
    print(f'[{"PASS" if cond else "FAIL"}] {label} {detail}', flush=True)
    if not cond:
        failures.append(label)
        if fatal:
            print('FATAL control failed -- run VOID, not red', flush=True)
            sys.exit(2)


def blk_text(lines):
    return b''.join(l.encode().ljust(64) for l in lines + [''] * (16 - len(lines)))


# ---- fixture image
kernel = os.path.join(B, 'bmforth.img') if os.path.exists(os.path.join(ROOT, 'forth', 'dict', 'ahci.fth')) \
    else os.path.join(B, 'bmforth-free.img')
for need in (kernel, os.path.join(B, 'blocks.img'), os.path.join(B, 'vbr.bin')):
    if not os.path.exists(need):
        sys.exit(f'NO INPUT: {need} (make combined, or make free blocks write-catalog)')
if os.path.isdir(D):
    shutil.rmtree(D)
os.makedirs(os.path.join(D, 'dict'))
for f in glob.glob(os.path.join(ROOT, 'forth', 'dict', '*.fth')):
    shutil.copy(f, os.path.join(D, 'dict'))
open(os.path.join(D, 'dict', 'ia-bad.fth'), 'w').write(FIX_BAD)
open(os.path.join(D, 'dict', 'ia-good.fth'), 'w').write(FIX_GOOD)
open(os.path.join(D, 'dict', 'ia-vec.fth'), 'w').write(FIX_VEC)
open(os.path.join(D, 'dict', 'ia-depfail.fth'), 'w').write(FIX_DEPFAIL)
open(os.path.join(D, 'dict', 'ia-outer.fth'), 'w').write(FIX_OUTER)
blocks = os.path.join(D, 'blocks.img')
shutil.copy(os.path.join(B, 'blocks.img'), blocks)
r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'write-catalog.py'), blocks,
                    os.path.join(D, 'dict') + '/', '--raw', f'VBR-TEMPLATE={os.path.join(B, "vbr.bin")}'],
                   capture_output=True, text=True)
if r.returncode != 0:
    sys.exit('FIXTURE: write-catalog failed:\n' + '\n'.join(
        l for l in (r.stdout + r.stderr).splitlines() if 'Lint OK' not in l)[-1200:])
NBLK = os.path.getsize(blocks) // 1024
BU, BC, BQ, BH = NBLK - 12, NBLK - 11, NBLK - 10, NBLK - 9   # past the code store (checked below)
ends = [int(m.group(1)) for m in re.finditer(r'Blocks? (?:\d+-)?(\d+):', r.stdout)]
check('C0 staged blocks lie past the code store', bool(ends) and max(ends) < BU,
      f'(catalog ends {max(ends, default=None)}, staged {BU}-{BH})', fatal=True)
with open(blocks, 'r+b') as f:
    for b, lines in ((BU, ['ZZNOPE  6 .', '8 .']), (BC, ['11 .']), (BQ, ['." BANNER-TXT" CR']),
                     (BH, ['ZZHOOK'])):
        f.seek(b * 1024)
        f.write(blk_text(lines))
IMG, IDE = os.path.join(D, 'image.img'), os.path.join(D, 'ide.img')
open(IMG, 'wb').write(open(kernel, 'rb').read() + open(blocks, 'rb').read())
shutil.copy(IMG, IDE)
_img = open(IDE, 'rb').read()
_v = _img.find(b'VOCABULARY IA-BAD')
_z = _img.find(b'ZZNOPE', _v)
assert _v > 0 and 0 < _z - _v < 256, 'IA-BAD fixture not found in the image'
IA_BAD_ZZ = _z                                         # byte offset of its ZZNOPE

# ---- control kernel: ZZCENSUS first in the embedded stream (U9)
CTL = os.path.join(D, 'control')
os.makedirs(CTL)
embed = subprocess.run(['make', '-s', 'print-embed-vocabs'], cwd=ROOT, capture_output=True,
                       text=True).stdout.split()
hw = os.path.join(ROOT, 'forth', 'dict', 'hardware.fth')
lines = open(hw).read().split('\n')
open(os.path.join(CTL, 'hardware.fth'), 'w').write('\n'.join(lines[:1] + ['ZZCENSUS'] + lines[1:]))
vlist = [os.path.join(CTL, 'hardware.fth') if os.path.abspath(os.path.join(ROOT, v)) == hw
         else os.path.join(ROOT, v) for v in embed]
eb = os.path.join(CTL, 'embedded.bin')
subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'embed-vocabs.py'), eb] + vlist,
               check=True, capture_output=True)
kb = os.path.join(CTL, 'kernel.bin')
subprocess.run(['nasm', '-f', 'bin', f'-dEMBED_FILE="{eb}"', '-o', kb, ASM], check=True, cwd=ROOT)
CTL_IMG = os.path.join(CTL, 'control.img')
open(CTL_IMG, 'wb').write(open(os.path.join(B, 'boot.bin'), 'rb').read() + open(kb, 'rb').read())

for p in (kernel, IMG, CTL_IMG, ASM, os.path.abspath(__file__)):
    print(f'input sha256 {hashlib.sha256(open(p, "rb").read()).hexdigest()}  {p}', flush=True)


def boot(args, role):
    pf = qemu_pid.pidfile(role)
    atexit.register(qemu_pid.kill_pidfile, pf)
    p = subprocess.Popen(['qemu-system-i386'] + args +
                         ['-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                          '-display', 'none', '-pidfile', pf],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    qemu_pid.wait_started(p, pf, PORT, role)
    return pf


def send(s, cmd, budget=20):
    rep, how = ser.send_until_prompt(s, cmd, budget=budget)
    body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
    print(f'>>> {cmd}\n    {body.strip()!r}  [{how}]', flush=True)
    return body, how


def nums(body):
    return [int(t) for t in re.findall(r'(?<![\w-])-?\d+(?![\w-])', body.replace('ok', ' '))]


def depth(s):
    v = nums(send(s, 'DECIMAL DEPTH .')[0])
    return v[-1] if v else None


# ---- main boot: fixture image
pf = boot(['-drive', f'file={IMG},format=raw,if=floppy',
           '-drive', f'file={IDE},format=raw,if=ide,index=1'], 'interp')
s = ser.connect_and_sync(PORT, budget=60)
send(s, 'DECIMAL')
check('C1 DEPTH 0 at start', depth(s) == 0, fatal=True)

# U1: the rest of the line is discarded
b, _ = send(s, 'ZZNOPE 7 .')
check('U1 `ZZNOPE 7 .`: ZZNOPE named, 7 not printed', 'ZZNOPE ?' in b and 7 not in nums(b),
      f'(got {b.strip()!r})')
# U2: the stack is emptied
send(s, '1 2 ZZNOPE 3')
d = depth(s)
check('U2 `1 2 ZZNOPE 3` then DEPTH = 0', d == 0, f'(got {d})')
if d and d > 0:
    send(s, ' '.join(['DROP'] * d))
# U3: a half definition is rolled back
hl = nums(send(s, 'HERE @ . LATEST @ .')[0])
b, _ = send(s, ': UT1 ZZNOPE 5 . ;')
hl2 = nums(send(s, 'HERE @ . LATEST @ .')[0])
check('U3a `: UT1 ZZNOPE 5 . ;`: nothing runs at definition time (no 5)',
      'ZZNOPE ?' in b and 5 not in nums(b), f'(got {b.strip()!r})')
check('U3b HERE and LATEST back to before `:`', hl == hl2, f'(before {hl}, after {hl2})')
b, _ = send(s, 'UT1')
check('U3c UT1 does not exist', 'UT1 ?' in b, f'(got {b.strip()!r})')
d = depth(s)
if d and d > 0:
    send(s, ' '.join(['DROP'] * d))
# U4: a loading block ends at the error; the next LOAD works
b, _ = send(s, f'{BU} LOAD')
n = nums(b)
check('U4a block LOAD stops at ZZNOPE (no 6, no 8)', 'ZZNOPE ?' in b and 6 not in n and 8 not in n,
      f'(got {b.strip()!r})')
b, _ = send(s, f'{BC} LOAD')
check('U4b the next block LOAD works (11)', 11 in nums(b), f'(got {b.strip()!r})')
check('U4c DEPTH 0', depth(s) == 0)
# U8: an aborted LOAD-VOCAB leaves the loader, the search order and the
# dictionary as they were before it; a corrected retry really loads
o1, _ = send(s, 'ORDER')
b, _ = send(s, 'S" IA-BAD" LOAD-VOCAB', 60)
o2, _ = send(s, 'ORDER')
check('U8e search order and CURRENT after the aborted load equal those before it',
      o1.strip() == o2.strip(), f'(before {o1.strip()!r}, after {o2.strip()!r})')
send(s, 'ONLY FORTH DEFINITIONS')          # known state for what follows, either way
b2, _ = send(s, 'IA-BAD IAB-AFTER .')
# After the error nothing of IA-BAD may run: today IAB-AFTER prints 1.
# (Rolled back, IA-BAD itself is undefined too, so the line aborts at it.)
check('U8a IA-BAD load stops at ZZNOPE and is rolled back: "IA-BAD ?", IAB-AFTER never answers',
      'ZZNOPE ?' in b and 1 not in nums(b2) and 'IA-BAD ?' in b2,
      f'(load {b.strip()[-80:]!r}; use {b2.strip()!r})')
send(s, 'ONLY FORTH DEFINITIONS')
d = depth(s)
if d and d > 0:
    send(s, ' '.join(['DROP'] * d))
b3, _ = send(s, 'ALSO IA-GOOD IAG . PREVIOUS')
check('U8g IA-BAD\'s dependency IA-GOOD (finished before the failing block load) survives: IAG = 42',
      42 in nums(b3) and '?' not in b3, f'(got {b3.strip()!r})')
send(s, 'ONLY FORTH DEFINITIONS')
ld = nums(send(s, 'ALSO CATALOG-RESOLVER LOADING-DEPTH @ . PREVIOUS')[0])
check('U8b loading stack empty after the aborted load (LOADING-DEPTH 0)', ld[-1:] == [0], f'(got {ld})')
b, _ = send(s, 'S" IA-GOOD" LOAD-VOCAB', 60)
b2, _ = send(s, 'USING IA-GOOD IAG . PREVIOUS')
check('U8c LOAD-VOCAB IA-GOOD afterwards answers and IAG works (42)', 42 in nums(b2), f'(got {b2.strip()!r})')
# The host fixes IA-BAD's source (ZZNOPE -> spaces) on the IDE copy; the
# guest drops its cached blocks and loads again: it must really load.
with open(IDE, 'r+b') as f:
    f.seek(IA_BAD_ZZ)
    f.write(b'      ')
send(s, 'EMPTY-BUFFERS')
b, _ = send(s, 'S" IA-BAD" LOAD-VOCAB', 60)
b2, _ = send(s, 'ALSO IA-BAD IAB-AFTER . PREVIOUS')
check('U8d corrected IA-BAD really loads on retry (no "present, skipped"; IAB-AFTER = 1)',
      'IA-BAD present, skipped' not in b and '?' not in b and 1 in nums(b2) and '?' not in b2,
      f'(load {b.strip()[-80:]!r}; use {b2.strip()!r})')
send(s, 'ONLY FORTH DEFINITIONS')
d = depth(s)
if d and d > 0:
    send(s, ' '.join(['DROP'] * d))
# U8f: a vector into the failed load blocks the rollback: kept, said so
b, _ = send(s, 'S" IA-VEC" LOAD-VOCAB', 60)
b2, _ = send(s, 'ALSO IA-VEC PREVIOUS')
check('U8f IA-VEC (BLK-WRITER! into itself, then ZZNOPE): aborts, kept, "IA-VEC partial" '
      'naming the writer vector',
      'ZZNOPE ?' in b and 'IA-VEC partial' in b and 'BLK-WRITER' in b and 'IA-VEC ?' not in b2,
      f'(load {b.strip()[-120:]!r}; ALSO {b2.strip()!r})')
send(s, "ONLY FORTH DEFINITIONS ' (BLK-WRITE-NONE) BLK-WRITER!")
d = depth(s)
if d and d > 0:
    send(s, ' '.join(['DROP'] * d))
# U8h: a dependency fails before the outer block load starts
b, _ = send(s, 'S" IA-OUTER" LOAD-VOCAB', 60)
b2, _ = send(s, 'ALSO IA-DEPFAIL PREVIOUS')
b3, _ = send(s, 'ALSO IA-OUTER PREVIOUS')
check('U8h IA-DEPFAIL fails as IA-OUTER\'s dependency: "IA-OUTER not loaded: IA-DEPFAIL failed", '
      'neither vocabulary left',
      'IA-OUTER not loaded: IA-DEPFAIL failed' in b and 'IA-DEPFAIL ?' in b2 and 'IA-OUTER ?' in b3,
      f'(load {b.strip()[-100:]!r}; {b2.strip()!r}; {b3.strip()!r})')
send(s, 'ONLY FORTH DEFINITIONS')
d = depth(s)
if d and d > 0:
    send(s, ' '.join(['DROP'] * d))
# U10-U12: the other not-found sites abort too
for tag, cmd, name in (('U10', "' ZZNOPE 7 .", "'"), ('U11', 'USING ZZVOC 7 .', 'USING'),
                       ('U12', 'SEE ZZSEE 7 .', 'SEE')):
    b, _ = send(s, cmd)
    check(f'{tag} `{cmd}`: {name} not finding the name aborts the line (no 7)',
          '?' in b and 7 not in nums(b), f'(got {b.strip()!r})')
    d = depth(s)
    if d and d > 0:
        send(s, ' '.join(['DROP'] * d))
# U13: a typo at the prompt keeps the search order
send(s, 'ALSO HARDWARE')
o1, _ = send(s, 'ORDER')
send(s, 'ZZNOPE')
o2, _ = send(s, 'ORDER')
check('U13 a typo at the prompt keeps the search order (HARDWARE still in it)',
      o1.strip() == o2.strip(), f'(before {o1.strip()!r}, after {o2.strip()!r})')
send(s, 'ONLY FORTH DEFINITIONS')
# Q5/Q6/C: ."
h1 = nums(send(s, 'HERE @ .')[0])
b, _ = send(s, '." BANNER-TXT"')
h2 = nums(send(s, 'HERE @ .')[0])
check('Q5 interpret-mode ." prints, HERE unchanged', 'BANNER-TXT' in b and h1 == h2,
      f'(printed {"BANNER-TXT" in b}; HERE {h1} -> {h2})')
b, _ = send(s, f'{BQ} LOAD')
h3 = nums(send(s, 'HERE @ .')[0])
check('Q6 block-loaded ." prints, HERE unchanged', 'BANNER-TXT' in b and h2 == h3,
      f'(printed {"BANNER-TXT" in b}; HERE {h2} -> {h3})')
send(s, ': UT2 ." IN-COLON" ;')
b, _ = send(s, 'UT2')
check('C2 compiled ." prints (control)', 'IN-COLON' in b, f'(got {b.strip()!r})')
# Q7/Q8: .(
b, _ = send(s, '.( HELLO-PAREN) 9 .')
check('Q7 `.( HELLO-PAREN) 9 .` prints HELLO-PAREN then 9',
      # .( prints its text exactly, no trailing space: "HELLO-PAREN9 ok"
      'HELLO-PAREN' in b and '?' not in b and '9 ok' in b, f'(got {b.strip()!r})')
d = depth(s)
if d and d > 0:
    send(s, ' '.join(['DROP'] * d))
b, _ = send(s, ': UT3 .( AT-COMPILE) ;')
b2, _ = send(s, 'UT3')
check('Q8 `.(` inside a definition prints at compile time; UT3 prints nothing',
      'AT-COMPILE' in b and '?' not in b and 'AT-COMPILE' not in b2 and '?' not in b2,
      f'(define {b.strip()!r}; run {b2.strip()!r})')
d = depth(s)
if d and d > 0:
    send(s, ' '.join(['DROP'] * d))
# P1/P2: `(` typed over serial (last: today it wedges; recovered with a `)`)
b, how = send(s, '( a comment ) 1 2 + .', 8)
check('P1 typed `( a comment ) 1 2 + .` prints 3', how == 'prompt' and 3 in nums(b),
      f'(got {b.strip()!r}, read ended by {how})')
if how != 'prompt':
    send(s, ')', 8)
b, how = send(s, '( unterminated', 8)
b2, how2 = send(s, '4 .', 8)
check('P2 typed `( unterminated` ends at end of line; the next line prints 4',
      how == 'prompt' and how2 == 'prompt' and 4 in nums(b2),
      f'(first {how}, second {b2.strip()!r} {how2})')
if how != 'prompt' or how2 != 'prompt':
    send(s, ')', 8)
# U14 (last on this boot: today it never returns): a hook that itself hits
# an undefined word must land at the prompt, stacks empty, and the hook
# must run again on the next abort (not left switched off).
send(s, 'ABORT-HOOK @ CONSTANT OLDHOOK')
send(s, f': BADHOOK {BH} LOAD ;')
send(s, ': MARKHOOK ." HOOK-RAN" ;')
send(s, "' BADHOOK ABORT-HOOK !")
b, how = send(s, 'ZZNOPE', 10)
check('U14a a hook that hits an undefined word (ZZHOOK) lands at the prompt, once',
      how == 'prompt' and b.count('ZZHOOK ?') == 1, f'(read ended by {how}; {b.strip()[:120]!r})')
if how == 'prompt':
    check('U14b stacks empty after the nested abort (DEPTH 0)', depth(s) == 0)
    send(s, "' MARKHOOK ABORT-HOOK !")
    b, how2 = send(s, 'ZZNOPE', 10)
    check('U14c the next abort runs the hook again (HOOK-RAN)', 'HOOK-RAN' in b,
          f'(got {b.strip()!r})')
    send(s, 'OLDHOOK ABORT-HOOK !')
else:
    check('U14b stacks empty after the nested abort (DEPTH 0)', False, '(no prompt: not reached)')
    check('U14c the next abort runs the hook again (HOOK-RAN)', False, '(no prompt: not reached)')
s.close()
qemu_pid.kill_pidfile(pf)
time.sleep(0.5)

# ---- control kernel (U9): an undefined word in the embedded stream
pf = boot(['-drive', f'file={CTL_IMG},format=raw,if=floppy,readonly=on'], 'interp-ctl')
log = os.path.join(D, 'control-serial.log')
s = ser.connect_and_sync(PORT, budget=60)
b, how = send(s, 'DECIMAL 1 2 + .')
s.close()
qemu_pid.kill_pidfile(pf)
check('U9a control kernel reaches the prompt and answers (3)', how == 'prompt' and 3 in nums(b),
      f'(got {b.strip()!r})')
# The boot banner is sent before a client connects (wait=off); boot again with
# serial to a file to read what the stream printed.
pf = qemu_pid.pidfile('interp-ctl2')
atexit.register(qemu_pid.kill_pidfile, pf)
subprocess.Popen(['qemu-system-i386', '-drive', f'file={CTL_IMG},format=raw,if=floppy,readonly=on',
                  '-serial', f'file:{log}', '-display', 'none', '-pidfile', pf],
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(15)
qemu_pid.kill_pidfile(pf)
boot_txt = open(log, 'rb').read().decode('ascii', 'replace')
print(f'control boot log: {boot_txt.strip()!r}', flush=True)
check('U9b the boot names it loudly: EMBED ABORTED at ZZCENSUS',
      'EMBED ABORTED at ZZCENSUS' in boot_txt and boot_txt.rstrip().endswith('ok'),
      f'(log {boot_txt.strip()[-120:]!r})')

print(f'Passed: {checks - len(failures)}/{checks}', flush=True)
sys.exit(0 if not failures else 1)
