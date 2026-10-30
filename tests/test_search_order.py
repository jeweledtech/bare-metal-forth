#!/usr/bin/env python3
"""ALSO and USING on a full search order, and a load's own fresh order
(private TASK_ALSO_FULL, parts a and b). Eight checks: D0, A1-A4, B1-B3.

  python3 tests/test_search_order.py <serial-port>     (cwd: tree root)

The search order holds 8 entries. At depth 8 ALSO and USING used to do
nothing, so the vocabulary word after them replaced the top entry and the
old top was lost without a word. They now refuse: SEARCH ORDER FULL, the
order unchanged, and the rest of the line not run (as an undefined word);
inside a load the load rolls back with that reason. A top-level
LOAD-VOCAB starts the file at ONLY FORTH DEFINITIONS and gives the caller
its order and CURRENT back after, so a file's depth and the vocabulary its
words go into do not depend on its caller. ORDER prints each
entry's address, top first, so two ORDER outputs compare as strings.

Blocks come from a copy of the image attached as an IDE disk; D0 is the
positive control that it is attached (as test_console_band.py).
"""
import hashlib, os, shutil, subprocess, sys

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import serial as ser

PORT = int(sys.argv[1])
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
OUT = os.path.join(ROOT, 'build', 'search-order.d')
os.makedirs(OUT, exist_ok=True)
PF = os.path.join(OUT, 'qemu.pid')
IDE = os.path.join(OUT, 'combined-ide.img')
FULL = 'SEARCH ORDER FULL'

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

lay = subprocess.run(['python3', 'tools/catalog_layout.py', 'UI-PARSER'], capture_output=True, text=True)
UIP = lay.stdout.split()[:2]
print(f'UI-PARSER in build/blocks.img: {UIP}', flush=True)

qemu_pid.kill_pidfile(PF)
shutil.copyfile(COMBINED, IDE)
q = subprocess.run(['qemu-system-i386', '-drive', f'file={COMBINED},format=raw,if=floppy', '-m', '256',
                    '-drive', f'file={IDE},format=raw,if=ide,index=1', '-display', 'none', '-snapshot',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                    '-daemonize', '-pidfile', PF], capture_output=True)
qemu_pid.check_launch(q, PF, PORT, 'search-order')
try:
    s = ser.connect_and_sync(PORT, budget=60)

    def send(cmd, budget=30):
        reply, how = ser.send_until_prompt(s, cmd, budget=budget)
        if how != 'prompt':
            print(f'    (read of {cmd[:40]!r} ended by {how})', flush=True)
        return reply

    def body(reply):
        return reply.split('\r\n', 1)[1] if '\r\n' in reply else ''

    def order():
        """The entries ORDER prints (top first), and the Compile cell."""
        t = body(send('ORDER')).replace('ok', ' ')
        if 'Search:' not in t or 'Compile:' not in t:
            return None, t.strip()[:80]
        a, b = t.split('Search:', 1)[1].split('Compile:', 1)
        return a.split(), b.split()[:1]

    v = body(send('ALSO CATALOG-RESOLVER S" UI-PARSER" CATALOG-FIND .S PREVIOUS')).replace('ok', ' ').split()
    got = [x.strip('<>') for x in v if x.strip('<>')]     # .S: <first last -1 >
    ok = len(UIP) == 2 and got[:3] == UIP + ['-1']
    check('D0 block disk attached: CATALOG-FIND UI-PARSER gives its range from build/blocks.img',
          ok, f'guest {got}, image {UIP}')
    if not ok:
        print('  no block disk: stopping before any check that loads from blocks', flush=True)
        print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
        sys.exit(1)                   # the finally below stops QEMU
    send('DROP DROP DROP')

    # Depth 7, then the eighth entry: the control.
    send('ONLY FORTH ' + 'ALSO FORTH ' * 6)
    seven, _ = order()
    send('ALSO HAL')
    eight, _ = order()
    check('A1 at depth 7 ALSO HAL works: 8 entries, HAL on top',
          seven is not None and eight is not None and len(seven) == 7 and len(eight) == 8
          and eight[0] != seven[0] and eight[1:] == seven, f'{seven} -> {eight}')

    # Depth 8: ALSO refuses; the line's rest does not run.
    r = body(send('ALSO UI-CORE 5 .'))
    check('A2 at depth 8 ALSO UI-CORE 5 . says SEARCH ORDER FULL and does not print 5',
          FULL in r and '5' not in r.replace(FULL, '').split(), f'{r.strip()[:80]!r}')
    after, _ = order()
    check('A3 the refused ALSO leaves the order as it was', after == eight, f'{eight} -> {after}')

    r = body(send('USING UI-EVENTS 5 .'))
    after2, _ = order()
    check('A4 at depth 8 USING UI-EVENTS 5 . says SEARCH ORDER FULL, no 5, order unchanged',
          FULL in r and '5' not in r.replace(FULL, '').split() and after2 == after,
          f'{r.strip()[:80]!r}; {after} -> {after2}')

    # A load from a 4-deep caller: HELLO-APP adds five. Started at its own
    # fresh order it loads; either way the caller's order is restored.
    send('ONLY FORTH ALSO HAL ALSO UI-CORE ALSO UI-EVENTS')
    o3 = order()
    r = body(send('S" HELLO-APP" LOAD-VOCAB', budget=90))
    print(f'    (HELLO-APP from depth 4: {r.strip()[-90:]!r})', flush=True)
    check('B1 HELLO-APP loads from a 4-deep caller: no ?, not rolled back',
          '?' not in r and 'rolled back' not in r and FULL not in r, f'{r.strip()[-90:]!r}')
    o4 = order()
    check('B2 a load from a 4-deep caller gives the caller its order back',
          o3[0] is not None and o3 == o4, f'{o3} -> {o4}')

    # A file with no DEFINITIONS line (NOTEPAD-FORM) defines into FORTH,
    # not into its caller's CURRENT (here HAL).
    send('ONLY FORTH ALSO HAL DEFINITIONS')
    r = body(send('S" NOTEPAD-FORM" LOAD-VOCAB', budget=60))
    print(f'    (NOTEPAD-FORM from CURRENT HAL: {r.strip()[-60:]!r})', flush=True)
    send('FORTH DEFINITIONS')
    r = body(send("ONLY FORTH ' NF-DATA ."))
    check('B3 a file without DEFINITIONS defines into FORTH: NF-DATA found under ONLY FORTH',
          '?' not in r and r.replace('ok', '').strip() != '', f'{r.strip()[:60]!r}')
    s.close()
finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
sys.exit(0 if FAIL == 0 else 1)
