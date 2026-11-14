#!/usr/bin/env python3
"""FORTH83: the checks that stay on the host (private TASK_FORTH83_VOCAB).

The portable 33 (K1-K4, LV0-LV8, R1, R2, H1, H3-H5, P1-P6, C1-C3, O1-O3,
A1, A2) moved into the machine: tests/forth/forth83.fth under the same
labels, run by make test-forth (TASK_FORTH_TEST_RUNNER step 7). D0, L1 and
Z were dropped as redundant there; E1 left with the metacompiler park
(owner ruling B, 2026-11-13). What stays here needs the host:
  K5      UM/MOD's OUT OF RANGE abort (the runner stops at an abort)
  H2      SPACES (its result is printed text only)
  R3      TIB at the prompt (inside a block load TIB is the block)
  B1, B2  SEE (printed text), and the see1 red below
  M1-M4   a MIRROR image across a reboot
The same 9 run in public and private mode.

  python3 tests/test_forth83.py <serial-port>     (cwd: tree root)

Blocks come from a copy of the image attached as an IDE disk. Before any
check the run confirms it is attached (CATALOG-FIND UI-PARSER against the
range tools/catalog_layout.py reads from build/blocks.img) and that
FORTH83 loads; either failing stops the run. No -snapshot: boot B reads the
MIRROR image boot A wrote, so both boots run on copies in build/forth83.d.
MIRROR is loaded first in both boots, so LOOKINGGLASS overwrites it with
itself.

Also carries see1_RED_decompile_prints_cell_addresses (private
TASK_SEE_CELLS; docs/evidence/x64-open-register-2026-09-20.md): SEE prints
each cell's address, not the word in it. Reported apart from the Passed
count: XFAIL (expected) as predicted; XPASS (SEE shows the words) is a
FAIL, stop and remove the red; anything else is a plain FAIL.
"""
import hashlib, os, re, shutil, subprocess, sys

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import run_mode
import serial as ser

PORT = int(sys.argv[1])
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
VOCAB = os.path.join(ROOT, 'forth', 'dict', 'forth83.fth')
# The mode (tests/run_mode.py) only names the line: the 9 checks are the
# same in both modes.
MODE = run_mode.resolve(ROOT)
TOTAL = 9
OUT = os.path.join(ROOT, 'build', 'forth83.d')
os.makedirs(OUT, exist_ok=True)
PF = os.path.join(OUT, 'qemu.pid')
FLOPPY = os.path.join(OUT, 'combined-floppy.img')
IDE = os.path.join(OUT, 'combined-ide.img')
SEE_RED = 'see1_RED_decompile_prints_cell_addresses'

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}', flush=True)
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''), flush=True)


for p in (COMBINED, os.path.join(ROOT, 'src', 'kernel', 'forth.asm'), VOCAB, os.path.abspath(__file__)):
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else 'ABSENT'
    print(f'input sha256 {h}  {p}', flush=True)

lay = subprocess.run(['python3', 'tools/catalog_layout.py', 'UI-PARSER'], capture_output=True, text=True)
UIP = lay.stdout.split()[:2]
print(f'UI-PARSER in build/blocks.img: {UIP}', flush=True)

qemu_pid.kill_pidfile(PF)
shutil.copyfile(COMBINED, FLOPPY)
shutil.copyfile(COMBINED, IDE)


def boot(tag):
    q = subprocess.run(['qemu-system-i386', '-drive', f'file={FLOPPY},format=raw,if=floppy', '-m', '256',
                        '-drive', f'file={IDE},format=raw,if=ide,index=1', '-display', 'none',
                        '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                        '-daemonize', '-pidfile', PF], capture_output=True)
    qemu_pid.check_launch(q, PF, PORT, f'forth83-{tag}')
    return ser.connect_and_sync(PORT, budget=60)


def session(s):
    def send(cmd, budget=30):
        reply, how = ser.send_until_prompt(s, cmd, budget=budget)
        if how != 'prompt':
            print(f'    (read of {cmd[:40]!r} ended by {how})', flush=True)
        return reply

    def body(cmd, budget=30):
        r = send(cmd, budget)
        return r.split('\r\n', 1)[1] if '\r\n' in r else ''

    def nums(cmd):
        return body(cmd).replace('ok', ' ').split()

    def text(cmd):
        """What the line printed, without the prompt."""
        return re.sub(r'\s*ok\s*$', '', body(cmd).replace('\r', '')).strip('\n')

    return send, body, nums, text


def finish():
    print('\n' + MODE.line(PASS, TOTAL, 'the same 9 checks'), flush=True)
    sys.exit(0 if FAIL == 0 and PASS == TOTAL else 1)


try:
    # ---------------- boot A ----------------
    s = boot('a')
    send, body, nums, text = session(s)
    send('ONLY FORTH DEFINITIONS DECIMAL')
    v = nums('ALSO CATALOG-RESOLVER S" UI-PARSER" CATALOG-FIND .S PREVIOUS')
    got = [x.strip('<>') for x in v if x.strip('<>')]     # .S: <first last -1 >
    ok = len(UIP) == 2 and got[:3] == UIP + ['-1']
    print(f'  block disk: CATALOG-FIND UI-PARSER guest {got}, image {UIP}', flush=True)
    if not ok:
        print('  FAIL: no block disk: stopping before any check that loads from blocks', flush=True)
        finish()

    # MIRROR first, so boot B's MIRROR lies where boot A's did
    r = body('S" MIRROR" LOAD-VOCAB', 90)
    print(f'    (MIRROR load: {r.strip()[-80:]!r})', flush=True)

    # K5: UM/MOD's abort (K1-K4 run in the machine)
    r1, r2 = body('1 0 0 UM/MOD'), body('0 5 5 UM/MOD')
    d = nums('DEPTH .')
    check('K5 a zero divisor and a quotient past 32 bits: UM/MOD OUT OF RANGE, DEPTH 0',
          'UM/MOD OUT OF RANGE' in r1 and 'UM/MOD OUT OF RANGE' in r2 and d[:1] == ['0'],
          f'{r1.strip()[:40]!r} {r2.strip()[:40]!r} depth {d}')

    r = body('S" FORTH83" LOAD-VOCAB ALSO FORTH83', 90)
    if '?' in r or 'not found' in r:
        print(f'  FAIL: FORTH83 did not load: {r.strip()[-120:]!r}; stopping', flush=True)
        finish()

    # R3: TIB at the prompt
    check('R3 TIB is ADDR-TIB @ at the prompt, 164096', nums('TIB ADDR-TIB @ = . TIB .')[:2] == ['-1', '164096'])

    # H2: SPACES, read from the printed text
    a, b = text('91 EMIT 3 SPACES 93 EMIT'), text('91 EMIT 0 SPACES -2 SPACES 93 EMIT')
    check('H2 SPACES: 3 gives [   ], 0 and -2 give []', a == '[   ]' and b == '[]', f'{a!r} {b!r}')

    # A DOES> parent and child for SEE (B1, B2) and MIRROR (M3, M4)
    send(': MYCONST CREATE , DOES> @ ;')
    send('42 MYCONST X42')
    send('DECIMAL')

    # B: SEE on a child and on its parent
    b1 = body('SEE X42')
    check('B1 SEE X42: <primitive>', re.search(r'SEE: [0-9A-F]+: <primitive>', b1) is not None, b1.strip()[:80])
    b2 = body('SEE MYCONST')
    m = re.search(r'SEE: [0-9A-F]+: ((?:[0-9A-F]{4} )*);', b2)
    d = nums('DEPTH .')
    check('B2 SEE MYCONST: six cells, then ;  and DEPTH 0 after both',
          m is not None and len(m.group(1).split()) == 6 and d[:1] == ['0'], f'{b2.strip()[:120]} depth {d}')

    # see1_RED: SEE prints each cell's address, not the word in it
    send(': SW DUP DROP ;')
    xt_sw, xt_dup, xt_drop = (int((nums(f"' {w} .") or ['0'])[0]) for w in ('SW', 'DUP', 'DROP'))
    out = body('SEE SW')
    m = re.search(r'SEE: [0-9A-F]+: ((?:[0-9A-F]{4} )*);', out)
    groups = m.group(1).split() if m else []
    addrs = [f'{(xt_sw + 4) & 0xFFFF:04X}', f'{(xt_sw + 8) & 0xFFFF:04X}']
    words = [f'{xt_dup & 0xFFFF:04X}', f'{xt_drop & 0xFFFF:04X}']
    if ('DUP' in out and 'DROP' in out) or groups == words:
        check(f'XPASS: {SEE_RED} -- SEE shows the words; stop, record it, remove the red', False, out.strip()[:80])
    elif groups == addrs:
        print(f'  XFAIL (expected): {SEE_RED} -- groups {groups} are the cells\' addresses, '
              f'not DUP {words[0]} DROP {words[1]}', flush=True)
    else:
        check(f'{SEE_RED}: SEE SW printed neither the addresses {addrs} nor the words {words}', False,
              out.strip()[:80])

    # M (boot A half): an image with MYCONST and X42 in it
    send("ALSO MIRROR ' (BLK-WRITE-ATA) BLK-WRITER!")
    r = body('DECIMAL 216 MIRROR', 300)
    check('M1 216 MIRROR saved', 'MIRROR saved to block 216' in r, r.strip()[-80:])
    s.close()
    qemu_pid.kill_pidfile(PF)

    # ---------------- boot B: the same disks ----------------
    s = boot('b')
    send, body, nums, text = session(s)
    send('ONLY FORTH DEFINITIONS DECIMAL')
    body('S" MIRROR" LOAD-VOCAB', 90)
    send("ALSO MIRROR ' (BLK-READ-ATA) BLK-READER!")
    r = body('DECIMAL 216 LOOKINGGLASS', 120)
    check('M2 216 LOOKINGGLASS restored', 'LOOKINGGLASS restored' in r, r.strip()[-80:])
    check('M3 X42 . gives 42 after the reboot', nums('DECIMAL X42 .')[:1] == ['42'])
    check('M4 7 MYCONST X7  X7 . gives 7 (the restored parent makes a new child)',
          nums('7 MYCONST X7  X7 .')[:1] == ['7'])
    s.close()
finally:
    qemu_pid.kill_pidfile(PF)

finish()
