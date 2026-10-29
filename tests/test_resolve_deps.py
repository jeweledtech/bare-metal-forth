#!/usr/bin/env python3
"""RESOLVE-DEPS loads every name on a REQUIRES: line (private
TASK_RESOLVE_DEPS_EVERY_NAME). Seven checks, R1-R7.

  python3 tests/test_resolve_deps.py <serial-port>     (cwd: tree root)

Boots build/combined.img as a floppy with its own IDE copy (BLOCK reads the
IDE disk). MSI-READER's line names CAB-EXTRACT DEFLATE HARDWARE, and its
load works with the first name alone, so its case is the resolver's trace:
the "NAME present, skipped" lines LOAD-VOCAB-INNER prints for each name it
is handed that is already loaded. TARGET-X86's line names X86-ASM
META-COMPILER, and its source does ALSO META-COMPILER: that load fails
when the second name is dropped.
"""
import hashlib, os, re, subprocess, sys

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import serial as ser

PORT = int(sys.argv[1])
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
OUT = os.path.join(ROOT, 'build', 'resolve-deps.d')
os.makedirs(OUT, exist_ok=True)
PF = os.path.join(OUT, 'qemu.pid')
IDE = os.path.join(OUT, 'combined-ide.img')

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}', flush=True)
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''), flush=True)


def skipped(text):
    return re.findall(r'(\S+) present, skipped', text)


for p in (COMBINED, os.path.join(ROOT, 'forth', 'dict', 'catalog-resolver.fth'), os.path.abspath(__file__)):
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else 'ABSENT'
    print(f'input sha256 {h}  {p}', flush=True)

with open(COMBINED, 'rb') as fi, open(IDE, 'wb') as fo:
    fo.write(fi.read())
qemu_pid.kill_pidfile(PF)
q = subprocess.run(['qemu-system-i386', '-drive', f'file={COMBINED},format=raw,if=floppy', '-m', '256',
                    '-drive', f'file={IDE},format=raw,if=ide,index=1', '-display', 'none', '-snapshot',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                    '-daemonize', '-pidfile', PF], capture_output=True)
qemu_pid.check_launch(q, PF, PORT, 'resolve-deps')
try:
    s = ser.connect_and_sync(PORT, budget=60)

    def send(cmd, budget=30):
        reply, how = ser.send_until_prompt(s, cmd, budget=budget)
        if how != 'prompt':
            print(f'    (read of {cmd[:40]!r} ended by {how})', flush=True)
        return reply

    def body(reply):
        return reply.split('\r\n', 1)[1] if '\r\n' in reply else ''

    send('ONLY FORTH DEFINITIONS DECIMAL')

    rep = body(send('S" MSI-READER" LOAD-VOCAB', 90))
    want = ['HARDWARE', 'HARDWARE', 'DEFLATE', 'HARDWARE']
    check(f'R1 S" MSI-READER" LOAD-VOCAB: present, skipped {" ".join(want)}',
          skipped(rep) == want, f'got {skipped(rep)}; reply {rep.strip()!r}')
    check('R2 the MSI-READER load: no ?', '?' not in rep, repr(rep.strip()))
    send('ONLY FORTH DEFINITIONS')
    rep = body(send('USING MSI-READER'))
    check('R3 USING MSI-READER: no ?', '?' not in rep, repr(rep.strip()))

    send('ONLY FORTH DEFINITIONS')
    rep = body(send('S" TARGET-X86" LOAD-VOCAB', 120))
    check('R4 S" TARGET-X86" LOAD-VOCAB: no ?, present, skipped X86-ASM',
          '?' not in rep and skipped(rep) == ['X86-ASM'], f'got {skipped(rep)}; reply {rep.strip()!r}')
    send('ONLY FORTH DEFINITIONS')
    rep = body(send('USING META-COMPILER'))
    check('R5 USING META-COMPILER: no ?', '?' not in rep, repr(rep.strip()))
    send('ONLY FORTH DEFINITIONS')
    rep = body(send('USING TARGET-X86'))
    check('R6 USING TARGET-X86: no ?', '?' not in rep, repr(rep.strip()))

    send('ONLY FORTH DEFINITIONS DECIMAL')
    dep = body(send('DEPTH .')).split()
    check('R7 DEPTH 0', dep[:1] == ['0'], f'{dep}')
    s.close()
finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
sys.exit(0 if FAIL == 0 else 1)
