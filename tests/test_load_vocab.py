#!/usr/bin/env python3
"""LOAD-VOCAB keeps the caller's search order and names a miss (private
TASK_LOAD_VOCAB_ORDER). Seven checks, L0-L6.

  python3 tests/test_load_vocab.py <serial-port>     (cwd: tree root)

Boots build/combined.img as a floppy with its own IDE copy (BLOCK reads the
IDE disk). The caller's order is set first; "order" is the ten cells at
0x28020 (search order, depth, CURRENT), printed in hex.
"""
import os, re, subprocess, sys, time

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import qemu_pid
import serial as ser
import catalog_layout

PORT = int(sys.argv[1])
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
BLOCKS = os.path.join(ROOT, 'build', 'blocks.img')
OUT = os.path.join(ROOT, 'build', 'load-vocab.d')
os.makedirs(OUT, exist_ok=True)
PF = os.path.join(OUT, 'qemu.pid')
IDE = os.path.join(OUT, 'combined-ide.img')
CALLER = 'ONLY FORTH ALSO UI-CORE ALSO UI-PARSER ALSO UI-EVENTS ALSO CATALOG-RESOLVER'
CELLS = 'HEX ' + ' '.join(f'{0x28020 + 4 * i:X} @ .' for i in range(10)) + ' DECIMAL'

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}', flush=True)
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''), flush=True)


with open(COMBINED, 'rb') as fi, open(IDE, 'wb') as fo:
    fo.write(fi.read())
qemu_pid.kill_pidfile(PF)
q = subprocess.run(['qemu-system-i386', '-drive', f'file={COMBINED},format=raw,if=floppy', '-m', '256',
                    '-drive', f'file={IDE},format=raw,if=ide,index=1', '-display', 'none', '-snapshot',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                    '-daemonize', '-pidfile', PF], capture_output=True)
qemu_pid.check_launch(q, PF, PORT, 'load-vocab')
try:
    s = ser.connect_and_sync(PORT, budget=60)

    def send(cmd, budget=30):
        reply, how = ser.send_until_prompt(s, cmd, budget=budget)
        if how != 'prompt':
            print(f'    (read of {cmd[:40]!r} ended by {how})', flush=True)
        return reply

    def body(reply):
        return reply.split('\r\n', 1)[1] if '\r\n' in reply else ''

    def cells():
        return body(send(CELLS)).replace('ok', '').split()

    rep = send(CALLER)
    before = cells()
    check('L0 boot, the caller\'s order set', '?' not in rep and len(before) == 10, f'{rep.strip()[-60:]!r} {before}')

    # L1, L2, L6 share DIALOG's first load (a second load is "present,
    # skipped" and would not run the file), inside the DIALOG-RUN card's
    # flow without its search-order line.
    send('S" HELLO-FORM" LOAD-VOCAB', 60)
    before = cells()
    send('S" DIALOG" LOAD-VOCAB', 60)
    after = cells()
    rep = send('ALSO DIALOG PREVIOUS')
    check('L1 S" DIALOG" LOAD-VOCAB: order cells unchanged, DIALOG in the dictionary',
          after == before and '?' not in body(rep), f'before {before} after {after}; {body(rep).strip()!r}')

    first, last = catalog_layout.vocab_blocks('DIALOG', BLOCKS)
    rep = send('S" DIALOG" CATALOG-FIND .S')
    m = re.search(r'<(-?\d+) (-?\d+) -1 >ok', rep.replace('\r\n', ' '))
    found = m is not None and first is not None and (int(m.group(1)), int(m.group(2))) == (first, last)
    check(f'L2 then CATALOG-FIND still found: <{first} {last} -1 >', found, f'got {body(rep).strip()!r}')
    if '?' in rep:
        pass                                   # the line aborted: nothing left
    elif m:
        send('DROP DROP DROP')
    else:
        send('DROP')                           # a miss leaves one cell

    send('ALSO DIALOG')
    rep = send('S" HELLO-FORM" CATALOG-FIND DROP FORM-LOAD WT-COUNT @ .')
    loaded = '?' not in rep and body(rep).split()[:1] == ['9']
    out = ''
    if loaded:
        s.sendall(b'DIALOG-RUN .\r')
        time.sleep(2.0)
        s.sendall(bytes([27]))
        time.sleep(1.5)
        s.settimeout(0.5)
        b = b''
        try:
            while True:
                d = s.recv(4096)
                if not d:
                    break
                b += d
        except Exception:
            pass
        out = b.decode('latin-1').replace('\r\n', ' ')
    dep = body(send('DECIMAL DEPTH .')).split()
    check('L6 card flow without the order line: HELLO-FORM loads (9), DIALOG-RUN Esc 2, DEPTH 0',
          loaded and out.split()[-2:] == ['2', 'ok'] and dep[:1] == ['0'],
          f'load {body(rep).strip()!r}, out {out.strip()[-30:]!r}, depth {dep}')

    # L3: a load with REQUIRES:. HELLO-APP adds five ALSOs of its own, so the
    # caller's order is short: under a five-entry order its load overflows the
    # eight-entry search order, aborts, and the abort's restore would pass
    # this check without testing it. The load must also succeed.
    send('ONLY FORTH ALSO CATALOG-RESOLVER')
    before = cells()
    rep = send('S" HELLO-APP" LOAD-VOCAB', 90)
    after = cells()
    rep2 = send("ALSO HELLO-APP ' HELLO-RUN DROP PREVIOUS")   # found in its own vocabulary
    check('L3 S" HELLO-APP" LOAD-VOCAB (with REQUIRES:): loaded, order cells unchanged',
          after == before and 'rolled back' not in rep and '?' not in body(rep2),
          f'before {before} after {after}; {body(rep).strip()[-60:]!r} {body(rep2).strip()!r}')

    after = cells()                            # L3's ALSO/PREVIOUS rewrote a slot past the depth
    rep = send('S" NO-SUCH-VOCAB" LOAD-VOCAB')
    after2 = cells()
    dep = body(send('DEPTH .')).split()
    check('L4 unknown name: "NO-SUCH-VOCAB not found", DEPTH 0, order unchanged',
          'NO-SUCH-VOCAB not found' in rep and dep[:1] == ['0'] and after2 == after,
          f'{body(rep).strip()!r} depth {dep} order {after2 == after}')

    rep = send('S" UI-CORE" LOAD-VOCAB')
    after3 = cells()
    check('L5 S" UI-CORE" LOAD-VOCAB: "present, skipped", order unchanged',
          'UI-CORE present, skipped' in rep and after3 == after2, f'{body(rep).strip()!r}')

finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
