#!/usr/bin/env python3
"""The console as window 0: a band of the screen (private TASK_CONSOLE_BAND,
DESIGN_WINDOW_FOCUS step 1). Sixteen checks, B0-B15.

  python3 tests/test_console_band.py <serial-port>     (cwd: tree root)

CON-REGION ( top rows -- flag ) sets the console's band; the scroll, the
backspace's row walk, MORE's count and PAGE stay inside it. WINDOW keeps a
table of regions behind accessors; window 0 is the console. The screen is
read back from FB-BASE (0xB8000 on this BIOS boot). Markers are cells the
console never prints otherwise: EMIT 1-6 puts that character code in a cell,
and CELLOF finds it (cell index row * 80 + col, -1 if absent). PAINT fills
rows 0-16 with 'A'; UNPAINTED counts the cells there that are not.
"""
import hashlib, os, subprocess, sys

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import serial as ser

PORT = int(sys.argv[1])
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
OUT = os.path.join(ROOT, 'build', 'console-band.d')
os.makedirs(OUT, exist_ok=True)
PF = os.path.join(OUT, 'qemu.pid')

SETUP = [
    'ONLY FORTH DEFINITIONS DECIMAL ALSO HAL',
    ': CELLOF ( ch -- idx ) -1 SWAP 2000 0 DO FB-BASE I 2 * + C@ OVER = IF NIP I SWAP THEN LOOP DROP ;',
    ': PAINT 1360 0 DO 1857 FB-BASE I 2 * + W! LOOP ;',
    ': UNPAINTED ( -- n ) 0 1360 0 DO FB-BASE I 2 * + W@ 1857 = 0= IF 1+ THEN LOOP ;',
    ': L30 30 0 DO I . CR LOOP ;',
    ': T10 10 0 DO I . CR LOOP ;',
    ': XS 720 0 DO 120 EMIT LOOP ;',
    ': BSS 650 0 DO 8 EMIT LOOP ;',
    # blanks in rows 0-16: inside window 2 (cols 10-29, rows 3-7), outside
    ': IN2? ( idx -- f ) 80 /MOD DUP 3 < 0= SWAP 8 < AND SWAP DUP 10 < 0= SWAP 30 < AND AND ;',
    'VARIABLE BIN VARIABLE BOUT',
    ': BLANKS 0 BIN ! 0 BOUT ! 1360 0 DO FB-BASE I 2 * + W@ 1824 = IF I IN2? IF 1 BIN +! ELSE 1 BOUT +! THEN THEN LOOP ;',
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
          os.path.join(ROOT, 'forth', 'dict', 'window.fth'), os.path.abspath(__file__)):
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else 'ABSENT'
    print(f'input sha256 {h}  {p}', flush=True)

qemu_pid.kill_pidfile(PF)
q = subprocess.run(['qemu-system-i386', '-drive', f'file={COMBINED},format=raw,if=floppy', '-m', '256',
                    '-display', 'none', '-snapshot',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                    '-daemonize', '-pidfile', PF], capture_output=True)
qemu_pid.check_launch(q, PF, PORT, 'console-band')
try:
    s = ser.connect_and_sync(PORT, budget=60)

    def send(cmd, budget=30):
        reply, how = ser.send_until_prompt(s, cmd, budget=budget)
        if how != 'prompt':
            print(f'    (read of {cmd[:40]!r} ended by {how})', flush=True)
        return reply

    def body(reply):
        return reply.split('\r\n', 1)[1] if '\r\n' in reply else ''

    def nums(reply):
        return body(reply).replace('ok', ' ').split()

    def num(cmd):
        v = nums(send(cmd))
        return v[-1] if v else '?'

    bad = [line for line in SETUP if '?' in body(send(line))]
    if bad:
        print(f'    (setup lines with ?: {bad})', flush=True)

    r = send('S" WINDOW" LOAD-VOCAB ALSO WINDOW', budget=60)
    check('B0 WINDOW loads, no ?', '?' not in body(r), body(r).strip()[-120:])

    v = nums(send('CON-REGION@ . .'))
    check('B1 default band: CON-REGION@ is 0 25', v[:2] == ['25', '0'], f'{v}')

    # The band: rows 17-24. The cursor goes to its first row.
    send('8 WIN-CONSOLE 1 EMIT')
    c = num('1 CELLOF .')
    check('B2 8 WIN-CONSOLE: the cursor at row 17, col 0 (cell 1360)', c == '1360', f'cell {c}')

    # Rows 0-16 painted, then 30 lines scroll the band.
    send('PAINT')
    send('L30')
    u = num('UNPAINTED .')
    check('B3 30 lines in the band: rows 0-16 untouched', u == '0', f'{u} cells changed')

    # MORE in an 8-row band: 6 lines, then the pause.
    r, how = ser.send_until_prompt(s, 'MORE-ON T10', budget=6)
    before = r.split('-- more --')[0] if '-- more --' in r else None
    digits = body(before).replace('ok', ' ').split() if before is not None else []
    check('B4 MORE-ON in an 8-row band: 0-5 printed, then -- more --',
          before is not None and digits == ['0', '1', '2', '3', '4', '5'],
          f'more seen {before is not None}, before it {digits}, read ended by {how}')
    if before is not None:
        send('')                      # the key the pause waits for
    send('MORE-OFF')

    # PAGE clears the band only, and puts the cursor at its first row.
    send('PAINT PAGE 2 EMIT')
    u = num('UNPAINTED .')
    check('B5 PAGE: rows 0-16 untouched', u == '0', f'{u} cells changed')
    c = num('2 CELLOF .')
    check('B6 PAGE: the cursor at row 17, col 0', c == '1360', f'cell {c}')

    # Backspace walks up a wrapped line and stops at the band's first row.
    send('PAGE PAINT XS BSS 3 EMIT')
    u = num('UNPAINTED .')
    check('B7 backspace across 9 wrapped rows: rows 0-16 untouched', u == '0', f'{u} cells changed')
    c = num('3 CELLOF .')
    check('B8 backspace stops at row 17, col 0', c == '1360', f'cell {c}')

    # Refusals: the band is unchanged.
    r2 = body(send('2 WIN-CONSOLE'))
    r26 = body(send('26 WIN-CONSOLE'))
    v = nums(send('CON-REGION@ . .'))
    check('B9 2 and 26 WIN-CONSOLE refused, band still 17 8',
          'console band is 3 to 25 rows' in r2 and 'console band is 3 to 25 rows' in r26
          and v[:2] == ['8', '17'], f'{r2.strip()[:60]!r} {r26.strip()[:60]!r} {v}')
    v = nums(send('-1 5 CON-REGION . 20 8 CON-REGION . 0 2 CON-REGION . CON-REGION@ . .'))
    check('B10 CON-REGION refuses top -1, 20+8 rows, 2 rows: 0 0 0, band unchanged',
          v[:5] == ['0', '0', '0', '8', '17'], f'{v}')

    # The table.
    v = nums(send('0 0 80 17 WIN-NEW . 10 3 20 5 WIN-NEW . 1 WIN-REGION . . . . 0 WIN-REGION . . . .'))
    check('B11 WIN-NEW ids 1 2; 1 WIN-REGION 0 0 80 17; 0 WIN-REGION 0 17 80 8',
          v[:10] == ['1', '2', '17', '80', '0', '0', '8', '80', '17', '0'], f'{v}')
    v = nums(send('0 0 2 WIN-AT FB-BASE - . 19 4 2 WIN-AT FB-BASE - .'))
    check('B12 WIN-AT: window 2 (10,3) is cell offset 500; (19,4) is 1178',
          v[:2] == ['500', '1178'], f'{v}')
    rc = body(send('20 0 2 WIN-AT'))
    rr = body(send('0 5 2 WIN-AT'))
    ro = body(send('0 70 1 1 WIN-NEW'))
    ri = body(send('9 WIN-REGION'))
    check('B13 refusals: column, row, off the screen, no such window',
          'column outside window' in rc and 'row outside window' in rr
          and 'region off the screen' in ro and 'no such window' in ri,
          f'{rc.strip()[:40]!r} {rr.strip()[:40]!r} {ro.strip()[:40]!r} {ri.strip()[:40]!r}')

    send('PAINT 2 WIN-CLS BLANKS')
    v = nums(send('BIN @ . BOUT @ .'))
    check('B14 2 WIN-CLS blanks its 100 cells and none outside it in rows 0-16',
          v[:2] == ['100', '0'], f'{v}')

    send('25 WIN-CONSOLE 4 EMIT')
    v = nums(send('CON-REGION@ . . 4 CELLOF .'))
    dep = nums(send('DEPTH .'))
    check('B15 25 WIN-CONSOLE: band 0 25, cursor at cell 0; DEPTH 0',
          v[:3] == ['25', '0', '0'] and dep[:1] == ['0'], f'{v} depth {dep}')
    s.close()
finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
sys.exit(0 if FAIL == 0 else 1)
