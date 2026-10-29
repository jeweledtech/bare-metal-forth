#!/usr/bin/env python3
"""The net console flushes on LF, not on the caller's DL (private
TASK_NET_FLUSH_LF). Seven checks, N0-N6.

  python3 tests/test_net_flush_lf.py <serial-port>     (cwd: tree root)

mirror_char buffers each character for the UDP console and flushes on LF.
QEMU has no RTL8168, but net_flush only touches memory, so NET-RTL-BASE,
NET-TX-DESC and NET-TX-BUF point at buffers allotted here (the TxOK poll
reads back the 0x000C it wrote). A flush shows as net_pkt_id moving by 1;
net_buf_pos and net_pkt_id are addressed from NET-RTL-BASE by the
declaration order in forth.asm, checked first (N0). DL is set on purpose:
inside a colon definition `23 13 /MOD DROP DROP` leaves EDX = 10 (the
remainder) and `24 13 /MOD DROP DROP` leaves 11, and only LIT, DROP and
NEXT run before EMIT.
"""
import hashlib, os, subprocess, sys

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import serial as ser

PORT = int(sys.argv[1])
COMBINED = os.path.join(ROOT, 'build', 'combined.img')
OUT = os.path.join(ROOT, 'build', 'net-flush-lf.d')
os.makedirs(OUT, exist_ok=True)
PF = os.path.join(OUT, 'qemu.pid')

SETUP = [
    'DECIMAL CREATE NC-REG 64 ALLOT NC-REG 64 0 FILL',
    'CREATE NC-DESC 16 ALLOT CREATE NC-TXB 512 ALLOT',
    'NC-REG NET-RTL-BASE ! NC-DESC NET-TX-DESC ! NC-TXB NET-TX-BUF !',
    'NET-RTL-BASE 4 - CONSTANT POS NET-RTL-BASE 12 + CONSTANT PKT',
    'VARIABLE P0 VARIABLE PS VARIABLE D1 VARIABLE D2 VARIABLE D3 VARIABLE D4 VARIABLE D5',
    # N1: a letter with DL 11 (no flush either way), then NET-FLUSH
    ': N1W 24 13 /MOD DROP DROP 65 EMIT PKT @ P0 ! NET-FLUSH PKT @ P0 @ - D1 ! POS @ PS ! ;',
    ': N2W PKT @ P0 ! 23 13 /MOD DROP DROP 65 EMIT PKT @ P0 @ - D2 ! ;',
    ': N3W PKT @ P0 ! 24 13 /MOD DROP DROP 65 EMIT PKT @ P0 @ - D3 ! ;',
    ': N4W PKT @ P0 ! 23 13 /MOD DROP DROP 10 EMIT PKT @ P0 @ - D4 ! ;',
    ': N5W PKT @ P0 ! 24 13 /MOD DROP DROP 10 EMIT PKT @ P0 @ - D5 ! ;',
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


for p in (COMBINED, os.path.join(ROOT, 'src', 'kernel', 'forth.asm'), os.path.abspath(__file__)):
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else 'ABSENT'
    print(f'input sha256 {h}  {p}', flush=True)

qemu_pid.kill_pidfile(PF)
q = subprocess.run(['qemu-system-i386', '-drive', f'file={COMBINED},format=raw,if=floppy', '-m', '256',
                    '-display', 'none', '-snapshot',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                    '-daemonize', '-pidfile', PF], capture_output=True)
qemu_pid.check_launch(q, PF, PORT, 'net-flush-lf')
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

    send('ONLY FORTH DEFINITIONS DECIMAL')
    lay = nums(send('NET-TX-DESC NET-RTL-BASE - . NET-TX-BUF NET-RTL-BASE - . NET-RTL-BASE NET-CON-ENABLED - .'))
    check('N0 layout: TX-DESC = RTL-BASE + 4, TX-BUF = + 8, RTL-BASE = CON-ENABLED + 8',
          lay[:3] == ['4', '8', '8'], f'{lay}')

    bad = [line for line in SETUP if '?' in body(send(line))]
    if bad:
        print(f'    (setup lines with ?: {bad})', flush=True)
    send('NET-CON-ON')
    for w in ('N1W', 'N2W', 'N3W', 'N4W', 'N5W'):
        send(w)
    send('NET-CON-OFF')
    v = nums(send('D1 @ . PS @ . D2 @ . D3 @ . D4 @ . D5 @ .'))
    v = (v + ['?'] * 6)[:6]
    check('N1 NET-FLUSH with a byte buffered: packet id +1, buffer position 0',
          v[0] == '1' and v[1] == '0', f'delta {v[0]}, pos {v[1]}')
    check('N2 A with DL 10: no flush (delta 0)', v[2] == '0', f'delta {v[2]}')
    check('N3 A with DL 11: no flush (delta 0)', v[3] == '0', f'delta {v[3]}')
    check('N4 LF with DL 10: flush (delta 1)', v[4] == '1', f'delta {v[4]}')
    check('N5 LF with DL 11: flush (delta 1)', v[5] == '1', f'delta {v[5]}')

    dep = nums(send('DEPTH .'))
    check('N6 DEPTH 0', dep[:1] == ['0'], f'{dep}')
    s.close()
finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{PASS + FAIL}', flush=True)
sys.exit(0 if FAIL == 0 else 1)
