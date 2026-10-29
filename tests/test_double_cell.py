#!/usr/bin/env python3
"""The double-cell stack words against Forth-83, and RL-VAR's recorded name
(private TASK_TWO_OVER). Six checks, K1-K5 and R1.

  python3 tests/test_double_cell.py <serial-port>     (cwd: tree root)

Expected stack effects: Forth-83 Standard 13.2, Double Number Extension
(2OVER 32b1 32b2 -- 32b1 32b2 32b3, 32b3 a copy of 32b1), a 32b read as
a cell pair; cross-checked against F83's 68000 kernel. 2ROT, 2@ and 2!
are optional in Forth-83 and absent here: reported, not counted.

R1: RL-VAR (catalog-resolver) records the name of a vector that points
into a vocabulary RELOAD-VOCAB would free. FE-SAVE-XT is pointed at 12345,
the region is set to [12345, 12346), and RL-VAR runs; RL-WL must be the
name's length and RL-WA its address. RL-WL is printed first and the name
typed only when RL-WL < 64, so a swapped pair cannot flood the port.
Embedded vocabularies only: no block disk.
"""
import hashlib, os, subprocess, sys

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import serial as ser

PORT = int(sys.argv[1])
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
OUT = os.path.join(ROOT, 'build', 'double-cell.d')
os.makedirs(OUT, exist_ok=True)
PF = os.path.join(OUT, 'qemu.pid')

ABSENT_WORDS = ['2ROT', '2@', '2!']

SETUP = [
    'ONLY FORTH DEFINITIONS DECIMAL ALSO CATALOG-RESOLVER ALSO FILE-EDITOR',
    ': CLR BEGIN DEPTH WHILE DROP REPEAT ;',
    'VARIABLE SAVED',
    ': RLT FE-SAVE-XT @ SAVED !  12345 FE-SAVE-XT !  12345 RL-LO ! 12346 RL-HI !'
    '  0 RL-WA ! 0 RL-WL !  S" FE-SAVE-XT" S" FILE-EDITOR" RL-VAR  SAVED @ FE-SAVE-XT !'
    '  RL-WL @ DUP . 64 < IF RL-WA @ RL-WL @ TYPE THEN ;',
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


for p in (COMBINED, os.path.join(ROOT, 'src', 'kernel', 'forth.asm'),
          os.path.join(ROOT, 'forth', 'dict', 'catalog-resolver.fth'), os.path.abspath(__file__)):
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else 'ABSENT'
    print(f'input sha256 {h}  {p}', flush=True)

qemu_pid.kill_pidfile(PF)
q = subprocess.run(['qemu-system-i386', '-drive', f'file={COMBINED},format=raw,if=floppy', '-m', '256',
                    '-display', 'none', '-snapshot',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                    '-daemonize', '-pidfile', PF], capture_output=True)
qemu_pid.check_launch(q, PF, PORT, 'double-cell')
absent = []
try:
    s = ser.connect_and_sync(PORT, budget=60)

    def send(cmd, budget=30):
        reply, how = ser.send_until_prompt(s, cmd, budget=budget)
        if how != 'prompt':
            print(f'    (read of {cmd[:40]!r} ended by {how})', flush=True)
        return reply

    def body(reply):
        return reply.split('\r\n', 1)[1] if '\r\n' in reply else ''

    def stack(cmd):
        out = body(send(cmd + ' .S CLR')).replace('ok', '').strip()
        return out

    bad = [line for line in SETUP if '?' in body(send(line))]
    if bad:
        print(f'    (setup lines with ?: {bad})', flush=True)

    v = stack('1 2 3 4 2OVER')
    check('K1 1 2 3 4 2OVER: <1 2 3 4 1 2 > (Forth-83 13.2)', v == '<1 2 3 4 1 2 >', v)
    v = stack('1 2 3 4 2SWAP')
    check('K2 1 2 3 4 2SWAP: <3 4 1 2 >', v == '<3 4 1 2 >', v)
    v = stack('1 2 2DUP')
    check('K3 1 2 2DUP: <1 2 1 2 >', v == '<1 2 1 2 >', v)
    v = stack('1 2 3 2DROP')
    check('K4 1 2 3 2DROP: <1 >', v == '<1 >', v)

    for w in ABSENT_WORDS:
        r = body(send(f"' {w} DROP"))
        if '?' in r:
            absent.append(w)
        else:
            print(f'  PRESENT, not checked: {w}', flush=True)
    send('CLR')

    r = body(send('RLT')).replace('ok', '').strip()
    check('R1 RL-VAR records the vector: 10 FE-SAVE-XT', r == '10 FE-SAVE-XT', repr(r[:80]))

    v = body(send('DEPTH .')).replace('ok', '').split()
    check('K5 DEPTH 0', v[:1] == ['0'], f'{v}')
    s.close()
finally:
    qemu_pid.kill_pidfile(PF)

if absent:
    print(f'  ABSENT: {" ".join(absent)} (Forth-83 13, optional; not counted)', flush=True)
print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
print(f'absent: {len(absent)}', flush=True)
sys.exit(0 if FAIL == 0 else 1)
