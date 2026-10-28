#!/usr/bin/env python3
"""Data-stack floor guard (Bug #35; private TASK_STACK_FLOOR). Ten checks,
F0-F8, over four fresh boots.

  python3 tests/test_stack_floor.py <serial-port>     (cwd: tree root)

A pop on an empty stack reads the dword at 0x7C00 (DATA_STACK_TOP: the boot
sector's first four bytes, -1900006918) and, without the guard, leaves ESP
above the top: DEPTH reads 1073741823 and later pushes are miscounted. With
the guard, INTERPRET prints STACK UNDERFLOW, empties the stack and drops
the rest of the line. Expected values are the task doc's, written before
any code.
"""
import hashlib, os, re, shutil, subprocess, sys

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import serial as ser

PORT = int(sys.argv[1])
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
OUT = os.path.join(ROOT, 'build', 'stack-floor.d')
os.makedirs(OUT, exist_ok=True)
PF = os.path.join(OUT, 'qemu.pid')
IDE = os.path.join(OUT, 'combined-ide.img')
MSG = 'STACK UNDERFLOW'
BOOT_DWORD = '-1900006918'          # bytes FA 31 C0 8E at 0x7C00

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


def boot(tag):
    shutil.copyfile(COMBINED, IDE)
    qemu_pid.kill_pidfile(PF)
    q = subprocess.run(['qemu-system-i386', '-drive', f'file={COMBINED},format=raw,if=floppy', '-m', '256',
                        '-drive', f'file={IDE},format=raw,if=ide,index=1', '-display', 'none', '-snapshot',
                        '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                        '-daemonize', '-pidfile', PF], capture_output=True)
    qemu_pid.check_launch(q, PF, PORT, f'stack-floor {tag}')
    print(f'--- boot {tag}', flush=True)
    return ser.connect_and_sync(PORT, budget=60)


def sender(s):
    def send(cmd, budget=30):
        reply, how = ser.send_until_prompt(s, cmd, budget=budget)
        body = reply.split('\r\n', 1)[1] if '\r\n' in reply else ''
        print(f'    >>> {cmd}\n        {body.strip()[-160:]!r}  [{how}]', flush=True)
        return body
    return send


def toks(b):
    return b.replace('\r\n', ' ').split()


try:
    # A: the HP trip's line, then what it did to DEPTH and .S
    s = boot('A')
    send = sender(s)
    b = send('DECIMAL DEPTH .')
    check('F0 boot A, DEPTH 0', toks(b)[-2:] == ['0', 'ok'], repr(b))
    b = send('HEX 28098 @ . DECIMAL .')
    t = toks(b)
    check(f'F1a the second . prints {BOOT_DWORD} (the dword at 0x7C00)', BOOT_DWORD in t, repr(b))
    after = t[t.index(BOOT_DWORD) + 1:] if BOOT_DWORD in t else []
    check(f'F1b {MSG} follows it', ' '.join(after[:2]) == MSG, repr(b))
    b = send('DECIMAL DEPTH .')
    check('F2 DEPTH . then reads 0', toks(b)[-2:] == ['0', 'ok'], repr(b))
    b = send('1 2 3 .S')
    check('F3 1 2 3 .S shows <1 2 3 >', '<1 2 3 >' in b, repr(b))
    s.close()

    # B: the rest of the line after an underflow is not run
    s = boot('B')
    send = sender(s)
    b = send('. 5 5 + .')
    check(f'F4 ". 5 5 + .": {MSG}, and 10 is not printed', MSG in b and '10' not in toks(b), repr(b))
    s.close()

    # C: an underflow inside a colon definition; no warm reset
    s = boot('C')
    send = sender(s)
    send(': POP2 DROP DROP ;')
    b = send('1 POP2 5 .')
    check(f'F5 "1 POP2 5 .": {MSG}, and 5 is not printed', MSG in b and '5' not in toks(b), repr(b))
    b = send('DECIMAL DEPTH .')
    check('F6 DEPTH . then reads 0', toks(b)[-2:] == ['0', 'ok'], repr(b))
    b = send("' POP2 0<> .")
    check('F8 POP2 still defined (no warm reset): -1', toks(b)[-2:] == ['-1', 'ok'], repr(b))
    s.close()

    # D: should not move: an empty stack reached by balanced pops
    s = boot('D')
    send = sender(s)
    b = send('1 2 3 DROP DROP DROP DECIMAL DEPTH .')
    check(f'F7 balanced pops to empty: DEPTH 0, no {MSG}', toks(b)[-2:] == ['0', 'ok'] and MSG not in b, repr(b))
    s.close()
finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(1 if FAIL else 0)
