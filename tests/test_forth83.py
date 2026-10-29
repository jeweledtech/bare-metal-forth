#!/usr/bin/env python3
"""FORTH83: Forth-83 Required words the kernel lacked (private
TASK_FORTH83_VOCAB). The kernel's UM* and UM/MOD (K1-K5); the block-loaded
FORTH83 vocabulary's renames (R), high-level words (H), pictured output
(P), CONVERT (C) and DOES> (O), with DOES>'s five checks: A another CURRENT
vocabulary, B SEE, E TARGET-X86 loaded alongside (private; skipped and not
counted without forth/dict/target-x86.fth), M a MIRROR image across a
reboot, and the UEFI and SeaBIOS paths (U30/L30 in test_uefi_boot.py).

  python3 tests/test_forth83.py <serial-port>     (cwd: tree root)

Blocks come from a copy of the image attached as an IDE disk; D0 is a
positive control that it is attached (CATALOG-FIND UI-PARSER against the
range tools/catalog_layout.py reads from build/blocks.img), and on failure
the run stops with `no block disk`. No -snapshot: boot B reads the MIRROR
image boot A wrote, so both boots run on copies in build/forth83.d. MIRROR
is loaded first in both boots, so LOOKINGGLASS overwrites it with itself.

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
import serial as ser

PORT = int(sys.argv[1])
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
VOCAB = os.path.join(ROOT, 'forth', 'dict', 'forth83.fth')
TARGET_X86 = os.path.join(ROOT, 'forth', 'dict', 'target-x86.fth')
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
    print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
    sys.exit(0 if FAIL == 0 else 1)


try:
    # ---------------- boot A ----------------
    s = boot('a')
    send, body, nums, text = session(s)
    send('ONLY FORTH DEFINITIONS DECIMAL')
    v = nums('ALSO CATALOG-RESOLVER S" UI-PARSER" CATALOG-FIND .S PREVIOUS')
    got = [x.strip('<>') for x in v if x.strip('<>')]     # .S: <first last -1 >
    ok = len(UIP) == 2 and got[:3] == UIP + ['-1']
    check('D0 block disk attached: CATALOG-FIND UI-PARSER gives its range from build/blocks.img',
          ok, f'guest {got}, image {UIP}')
    if not ok:
        print('  no block disk: stopping before any check that loads from blocks', flush=True)
        finish()

    # MIRROR first, so boot B's MIRROR lies where boot A's did
    r = body('S" MIRROR" LOAD-VOCAB', 90)
    print(f'    (MIRROR load: {r.strip()[-80:]!r})', flush=True)

    # K: the kernel's UM* and UM/MOD
    check('K1 -1 -1 UM* . . gives -2 1', nums('-1 -1 UM* . .')[:2] == ['-2', '1'])
    check('K2 65536 65536 UM* . . gives 1 0', nums('65536 65536 UM* . .')[:2] == ['1', '0'])
    check('K3 -2 1 -1 UM/MOD . . gives 2 0', nums('-2 1 -1 UM/MOD . .')[:2] == ['2', '0'])
    check('K4 7 0 2 UM/MOD . . gives 3 1', nums('7 0 2 UM/MOD . .')[:2] == ['3', '1'])
    r1, r2 = body('1 0 0 UM/MOD'), body('0 5 5 UM/MOD')
    d = nums('DEPTH .')
    check('K5 a zero divisor and a quotient past 32 bits: UM/MOD OUT OF RANGE, DEPTH 0',
          'UM/MOD OUT OF RANGE' in r1 and 'UM/MOD OUT OF RANGE' in r2 and d[:1] == ['0'],
          f'{r1.strip()[:40]!r} {r2.strip()[:40]!r} depth {d}')

    r = body('S" FORTH83" LOAD-VOCAB ALSO FORTH83', 90)
    check('L1 FORTH83 loads: no ?, no not found', '?' not in r and 'not found' not in r, r.strip()[-120:])

    # R: renames
    check('R1 0 NOT . 5 NOT . gives -1 -6', nums('0 NOT . 5 NOT .')[:2] == ['-1', '-6'])
    check('R2 >IN is ADDR-TOIN', nums('>IN ADDR-TOIN = .')[:1] == ['-1'])
    check('R3 TIB is ADDR-TIB @ at the prompt, 164096', nums('TIB ADDR-TIB @ = . TIB .')[:2] == ['-1', '164096'])

    # H: strings and the stack
    send('CREATE CS 3 C, 65 C, 66 C, 67 C,')
    check('H1 COUNT: ABC, and addr+1 3', text('CS COUNT TYPE') == 'ABC'
          and nums('CS COUNT SWAP CS - . .')[:2] == ['1', '3'])
    a, b = text('91 EMIT 3 SPACES 93 EMIT'), text('91 EMIT 0 SPACES -2 SPACES 93 EMIT')
    check('H2 SPACES: 3 gives [   ], 0 and -2 give []', a == '[   ]' and b == '[]', f'{a!r} {b!r}')
    check('H3 ROLL: 3 ROLL, 0 ROLL, 2 ROLL',
          nums('1 2 3 4 3 ROLL . . . .')[:4] == ['1', '4', '3', '2']
          and nums('1 2 0 ROLL . .')[:2] == ['2', '1']
          and nums('1 2 3 2 ROLL . . .')[:3] == ['1', '3', '2'])
    send('CREATE TS 65 C, 32 C, 32 C,')
    check('H4 -TRAILING: A__ to 1, __ to 0, empty to 0',
          nums('TS 3 -TRAILING . TS - .')[:2] == ['1', '0']
          and nums('TS 1+ 2 -TRAILING . DROP')[:1] == ['0']
          and nums('TS 0 -TRAILING . DROP')[:1] == ['0'])
    check('H5 PAD is HERE@ + 100 and moves with it',
          nums('PAD HERE@ - .')[:1] == ['100'] and nums('PAD 8 ALLOT PAD SWAP - .')[:1] == ['8'])

    # P: pictured output
    for name, cmd, want in [
            ('P1 -123 with SIGN', '-123 DUP ABS 0 <# #S ROT SIGN #> TYPE', '-123'),
            ('P2 0 gives one digit', '0 0 <# #S #> TYPE', '0'),
            ('P3 HEX FF', 'HEX FF 0 <# #S #> TYPE DECIMAL', 'FF'),
            ('P4 2^64 - 1', '-1 -1 <# #S #> TYPE', '18446744073709551615'),
            ('P5 HOLD between digits', '1234 0 <# # # 46 HOLD #S #> TYPE', '12.34')]:
        got = text(cmd)
        check(f'{name}: {want}', got == want, repr(got))
    check('P6 64 binary digits', nums('2 BASE ! -1 -1 <# #S #> NIP DECIMAL .')[:1] == ['64'])
    send('DECIMAL')

    # C: CONVERT
    check('C1 CONVERT x123: 123 0, stops at the space',
          nums('0 0 S" x123 " DROP CONVERT C@ . . .')[:3] == ['32', '0', '123'])
    check('C2 CONVERT 2^64 - 1', nums('0 0 S" x18446744073709551615 " DROP CONVERT DROP . .')[:2] == ['-1', '-1'])
    check('C3 CONVERT HEX FF', nums('HEX 0 0 S" xFF " DROP CONVERT DROP DECIMAL . .')[:2] == ['0', '255'])
    send('DECIMAL')

    # O: DOES>
    send(': MYCONST CREATE , DOES> @ ;')
    send('42 MYCONST X42')
    check('O1 42 MYCONST X42  X42 . gives 42', nums('X42 .')[:1] == ['42'])
    send('5 MYCONST X5')
    check('O2 two children of one parent: X42 X5 + gives 47', nums('X42 X5 + .')[:1] == ['47'])
    send(': ARRAY CREATE CELLS ALLOT DOES> SWAP CELLS + ;')
    send('3 ARRAY AR  7 0 AR !  9 2 AR !')
    check('O3 ARRAY: 0 AR @ 2 AR @ + gives 16', nums('0 AR @ 2 AR @ + .')[:1] == ['16'])

    # A: a child made while another vocabulary is CURRENT
    a1 = nums('VOCABULARY DV ALSO DV DEFINITIONS 11 MYCONST X11  X11 . X42 .')
    check('A1 a child in DV: X11 11, X42 still 42', a1[:2] == ['11', '42'], f'{a1}')
    a2 = body('ONLY FORTH DEFINITIONS ALSO FORTH83 X11')
    check('A2 X11 lives in DV: not found with FORTH and FORTH83 only', a1[:2] == ['11', '42'] and 'X11 ?' in a2,
          a2.strip()[:60])
    send('ONLY FORTH DEFINITIONS ALSO FORTH83 DECIMAL')

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

    # E: TARGET-X86 alongside (private)
    if not os.path.exists(TARGET_X86):
        print(f'  SKIPPED (not counted): E1 TARGET-X86 alongside: {TARGET_X86} absent', flush=True)
    else:
        r = body('S" TARGET-X86" LOAD-VOCAB', 120)
        e = nums('ALSO META-COMPILER ALSO TARGET-X86 ALSO FORTH83 : MC3 CREATE , DOES> @ ; 3 MC3 X3  X3 .')
        check('E1 with META-COMPILER and TARGET-X86 in the order, a DOES> child answers 3',
              e[:1] == ['3'] and '?' not in r, f'{e} load {r.strip()[-60:]!r}')
        send('ONLY FORTH DEFINITIONS ALSO FORTH83 DECIMAL')

    # M (boot A half): an image with MYCONST and X42 in it
    send("ALSO MIRROR ' (BLK-WRITE-ATA) BLK-WRITER!")
    r = body('DECIMAL 216 MIRROR', 300)
    check('M1 216 MIRROR saved', 'MIRROR saved to block 216' in r, r.strip()[-80:])
    check('Z DEPTH 0 at the end of boot A', nums('DEPTH .')[:1] == ['0'])
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
