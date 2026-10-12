#!/usr/bin/env python3
"""Kernel-pad move (docs/TASK_KERNEL_PAD_MOVE.md): hello, notepad and the
file browser leave the embedded boot stream and load from blocks.

  python3 tests/test_pad_move.py <port>

  K1  kernel-only image (bmforth.img): NOTEPAD, HELLO-APP, FILE-BROWSER are
      not vocabularies at boot (ALSO <name> aborts with `<name> ?`).
  K2  combined image: each loads with LOAD-VOCAB (no "present, skipped",
      no error signature) and its entry word is then found; DEPTH 0.
  K3  combined image: NOTEPAD-FORM resolves from the catalog blocks before
      its load (CATALOG-MEM 0) and from the in-memory registry after it
      (CATALOG-MEM 1).
  K5  after loading each app, its form (loaded by the app's REQUIRES: line)
      is a registry hit and FORM-LOAD builds widgets.
  K4  host: the move itself -- the embedded boot stream built from today's
      EMBED_VOCABS plus the six moved files (where they sat in 3f58be6^) is
      at least 14,000 B larger than the stream from today's list alone (owner 2026-10-12:
      the old ">= 14,800 B of pad left" was the move's acceptance number,
      not a budget; free pad is now reported on every kernel build and held
      to KERNEL_PAD_FLOOR by forth.asm).
  I1  the installed instance, observed: no memdisk, AHCI on an HP-549
      fixture laid out the way ADD-BOOT-ENTRY writes it (P6 34-582, VBR
      at 34, the 224 kernel sectors from 35). Stand-in: the kernel boots
      from floppy instead of through GRUB's chainload -- the same BLOCK
      state (BLK_IMAGE_BASE 0, AHCI's BLOCK reading LBA 225+2N of the SATA
      disk). After `USING AHCI AHCI-INIT`, LOAD-VOCAB of a block-loaded
      vocabulary (MIRROR, FIRSTBOOT) loads nothing. A characterisation:
      the same before and after the move.
Predictions are written before each run, in the evidence directory the
task doc names.
"""
import atexit, hashlib, os, re, shutil, struct, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid          # noqa: E402
import serial as ser     # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4469
B = os.path.join(ROOT, 'build')
D = os.path.join(B, 'test-pad-move.d')
os.makedirs(D, exist_ok=True)
ASM = os.path.join(ROOT, 'src', 'kernel', 'forth.asm')
KERNEL_IMG = os.path.join(B, 'bmforth.img')
COMBINED = os.path.join(B, 'combined.img')
AHCI_FTH = os.path.join(ROOT, 'forth', 'dict', 'ahci.fth')
APPS = [('NOTEPAD', 'NOTEPAD-RUN'), ('HELLO-APP', 'HELLO-RUN'), ('FILE-BROWSER', 'FILE-BROWSER-RUN')]
failures, skips, checks = [], [], 0


def check(label, cond, detail='', fatal=False):
    global checks
    checks += 1
    print(f'[{"PASS" if cond else "FAIL"}] {label} {detail}', flush=True)
    if not cond:
        failures.append(label)
        if fatal:
            print('FATAL control failed -- run VOID, not red', flush=True)
            sys.exit(2)


for p in (KERNEL_IMG, COMBINED, ASM, os.path.abspath(__file__)):
    print(f'input sha256 {hashlib.sha256(open(p, "rb").read()).hexdigest()}  {p}', flush=True)


def boot(args, role):
    pf = qemu_pid.pidfile(role)
    atexit.register(qemu_pid.kill_pidfile, pf)    # also when connect fails
    p = subprocess.Popen(['qemu-system-i386'] + args +
                         ['-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                          '-display', 'none', '-pidfile', pf],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    qemu_pid.wait_started(p, pf, PORT, role)
    return pf, ser.connect_and_sync(PORT, budget=60)


def send(s, cmd, budget=30):
    rep, how = ser.send_until_prompt(s, cmd, budget=budget)
    body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
    print(f'>>> {cmd}\n    {body.strip()[-200:]!r}  [{how}]', flush=True)
    return body


def depth(s):
    v = re.findall(r'(-?\d+) ok', send(s, 'DECIMAL DEPTH .'))
    return int(v[-1]) if v else None


# ---- K4 (host): the move itself, the boot stream with and without the
# six moved files.  The "with" side is today's list plus them (where they
# sat before the move, 3f58be6^), so a vocabulary embedded later (hal.fth,
# 2026-10-12) counts on both sides and doesn't read as the move shrinking.
MOVED = {'notepad-form': 'file-editor-disk', 'notepad': 'notepad-form', 'hello-form': 'notepad',
         'hello-app': 'hello-form', 'file-browser-form': 'file-stream', 'file-browser': 'file-browser-form'}
mk = open(os.path.join(ROOT, 'Makefile')).read()
now = re.search(r'^EMBED_VOCABS = (.*)$', mk, re.M).group(1).split()
pre = list(now)
for name, after in MOVED.items():             # dict order = insertion order
    pre.insert(pre.index(f'forth/dict/{after}.fth') + 1, f'forth/dict/{name}.fth')
sizes = {}
for tag, files in (('pre', pre), ('now', now)):
    out = os.path.join(D, f'embed-{tag}.bin')
    subprocess.run(['python3', 'tools/embed-vocabs.py', out] + files, check=True, cwd=ROOT,
                   stdout=subprocess.DEVNULL)
    sizes[tag] = os.path.getsize(out)
check('K4 the move: the boot stream is >= 14,000 B smaller than with the six moved files',
      sizes['pre'] - sizes['now'] >= 14000,
      f'(with them {sizes["pre"]}, now {sizes["now"]}, shrank {sizes["pre"] - sizes["now"]})')

# ---- K1: kernel-only image
pf, s = boot(['-drive', f'file={KERNEL_IMG},format=raw,if=floppy,readonly=on'], 'padmove-k')
try:
    check('C1 kernel-only boot answers (DEPTH 0)', depth(s) == 0, fatal=True)
    for v, _ in APPS:
        b = send(s, f'ALSO {v} PREVIOUS')
        check(f'K1 {v} is not a vocabulary at boot (kernel-only image)', f'{v} ?' in b,
              f'(got {b.strip()!r})')
finally:
    s.close()
    qemu_pid.kill_pidfile(pf)

# ---- K2, K3: combined image
F, I = os.path.join(D, 'floppy.img'), os.path.join(D, 'ide.img')
shutil.copyfile(COMBINED, F)
shutil.copyfile(COMBINED, I)
pf, s = boot(['-drive', f'file={F},format=raw,if=floppy', '-drive', f'file={I},format=raw,if=ide,index=1'],
             'padmove-c')
try:
    check('C2 combined boot answers (DEPTH 0)', depth(s) == 0, fatal=True)
    send(s, 'ALSO CATALOG-RESOLVER')
    b = send(s, 'S" NOTEPAD-FORM" CATALOG-FIND . DROP DROP CATALOG-MEM @ .')
    m = re.findall(r'(-?\d+)', b.replace('ok', ' '))
    check('K3a NOTEPAD-FORM found in the catalog blocks before its load (CATALOG-MEM 0)',
          m[-2:] == ['-1', '0'], f'(flag, MEM = {m[-2:]})')
    send(s, 'PREVIOUS')
    for v, w in APPS:
        b = send(s, f'S" {v}" LOAD-VOCAB', 90)
        b2 = send(s, f"ALSO {v} ' {w} DROP PREVIOUS")
        check(f'K2 {v} loads from blocks and {w} is found',
              f'{v} present, skipped' not in b and not re.search(r'\S+ \? ', b)
              and '?' not in b2, f'(load {b.strip()[-120:]!r}; {b2.strip()!r})')
    send(s, 'ALSO CATALOG-RESOLVER')
    b = send(s, 'S" NOTEPAD-FORM" CATALOG-FIND . DROP DROP CATALOG-MEM @ .')
    m = re.findall(r'(-?\d+)', b.replace('ok', ' '))
    check('K3b NOTEPAD-FORM from the in-memory registry after the load (CATALOG-MEM 1)',
          m[-2:] == ['-1', '1'], f'(flag, MEM = {m[-2:]})')
    # K5: each app's REQUIRES: loaded its form, so FORM-LOAD builds widgets
    # from the registry (the form's catalog blocks hold Forth source, not
    # form text: a block-path FORM-LOAD would not do).
    send(s, 'ALSO UI-PARSER ALSO UI-CORE')
    # IF is compile-only: the load runs inside a definition.
    send(s, ': K5L CATALOG-FIND IF FORM-LOAD THEN WT-COUNT @ . ;')
    for form in ('NOTEPAD-FORM', 'HELLO-FORM', 'FILE-BROWSER-FORM'):
        b = send(s, f'S" {form}" CATALOG-FIND DROP DROP DROP CATALOG-MEM @ . S" {form}" K5L')
        m = re.findall(r'(-?\d+)', b.replace('ok', ' '))
        check(f'K5 {form} loaded with its app: registry hit and FORM-LOAD builds widgets',
              len(m) >= 2 and m[-2] == '1' and int(m[-1]) >= 1 and '?' not in b,
              f'(MEM, WT-COUNT = {m[-2:]})')
    send(s, 'ONLY FORTH DEFINITIONS')
    check('K2d DEPTH 0 after the loads', depth(s) == 0)
finally:
    s.close()
    qemu_pid.kill_pidfile(pf)

# ---- I1: the installed instance (needs AHCI, a paid vocabulary)
if not os.path.exists(AHCI_FTH):
    skips.append('I1')
    print('[SKIPPED] I1 (forth/dict/ahci.fth absent)', flush=True)
else:
    import g6_fixture as g6
    DISK = os.path.join(D, 'installed.img')
    if os.path.exists(DISK):
        os.remove(DISK)
    g6.build(DISK)
    subprocess.run(['sgdisk', '-a', '1', '-n', '6:34:582', '-t', '6:4E011D24-9E20-45E8-BC49-85EB14C68532',
                    '-c', '6:FORTHOS', DISK], check=True, capture_output=True)
    kern = open(KERNEL_IMG, 'rb').read()
    with open(DISK, 'r+b') as f:
        f.seek(34 * 512)
        f.write(open(os.path.join(B, 'vbr.bin'), 'rb').read()[:512])   # the VBR at OWN-BASE
        f.seek(35 * 512)
        f.write(kern[512:512 + 224 * 512])                              # KERNEL-SECTORS at OWN-BASE+1
    # -boot order=a: QEMU's default tries the hard disk first, and this one
    # is an HP-549 fixture (protective MBR, a VBR at 34), not a kernel image.
    pf, s = boot(['-boot', 'order=a',
                  '-drive', f'file={KERNEL_IMG},format=raw,if=floppy,readonly=on',
                  '-drive', f'file={DISK},format=raw,if=none,id=sata0',
                  '-device', 'ich9-ahci,id=ahci0', '-device', 'ide-hd,drive=sata0,bus=ahci0.0'],
                 'padmove-i')
    try:
        b = send(s, 'HEX 28098 @ . DECIMAL')
        check('C3 installed stand-in: no memdisk (BLK_IMAGE_BASE 0)',
              re.findall(r'(-?\d+) ok', b)[-1:] == ['0'], f'(got {b.strip()!r})', fatal=True)
        send(s, 'USING AHCI')
        b = send(s, 'AHCI-INIT', 30)
        check('C4 AHCI-INIT on the installed disk', 'AHCI ok' in b, f'({b.strip()!r})', fatal=True)
        found = []
        for v, probe in (('MIRROR', 'MIRROR-BLK'), ('FIRSTBOOT', 'FIRSTBOOT-RUN')):
            send(s, f'S" {v}" LOAD-VOCAB', 60)
            b = send(s, f'ALSO {v} PREVIOUS')
            found.append((v, f'{v} ?' not in b))
        check('I1 installed instance: LOAD-VOCAB loads nothing (MIRROR, FIRSTBOOT absent after it)',
              not any(f for _, f in found), f'(present: {[v for v, f in found if f]})')
        check('I1b the prompt still answers afterwards (DEPTH 0)', depth(s) == 0)
    finally:
        s.close()
        qemu_pid.kill_pidfile(pf)

print(f'Passed: {checks - len(failures)}/{checks}'
      + (f'  SKIPPED: {" ".join(skips)}' if skips else ''), flush=True)
sys.exit(0 if not failures else 1)
