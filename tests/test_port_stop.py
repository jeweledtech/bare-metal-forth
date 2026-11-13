#!/usr/bin/env python3
"""PORT-STOP waits 1 ms after CR clears, as iron always ran it (private
TASK_AHCI_PORTSTOP_DELAY).  Five checks: T0, T1, T2, T3, T4.

  python3 tests/test_port_stop.py <serial-port> [image]    (cwd: tree root)

Until 2026-11-12 the kernel's LEAVE was Forth-79: it set index = limit and
the loop body ran on.  In ahci.fth PORT-STOP that ran one `1 MS-DELAY`
after CR read clear, before FRE was cleared, and every iron boot ran it.
The Forth-83 kernel (public b0591d8) leaves at once, so the delay went.
PORT-STOP now runs it explicitly before LEAVE: the CR-clear path waits
1 ms again, and the timeout path (CR never clears) is unchanged.

How a 1 ms delay is seen under QEMU: US-LOOPS is multiplied by 100 (hex,
256), so one `1 MS-DELAY` takes about 2 s of wall time.  US-LOOPS is
hardware.fth's default 3E8 (1000) on every embedded boot: embed-vocabs.py
strips the HARDWARE-INIT call (STRIP_INIT_CALLS), so CALIBRATE-DELAY never
runs.  MS-DELAY computes ms * 3E8 * US-LOOPS in one 32-bit cell and US-DELAY
skips a non-positive count; the stretched product is 256,000,000, 8.4 times
below 2^31.  T1 measures the delay directly, so no QEMU speed is assumed.
T2 counts two delays as 2; T3 counts PORT-STOP's as round(elapsed / T1).
QEMU's AHCI clears CR and FR in the same register write that clears ST and
FRE (reasoned from QEMU's port write, not observed here), so
PORT-STOP's own polling adds no delays: the count is the delay after LEAVE.

Boot: the image (default build/combined.img, copied) on floppy, a blank
4 MiB disk on ICH9 AHCI.  The subject is private (ahci.fth): with
PRIVATE_REPO absent at the Makefile default the test is SKIPPED, not
passed.
"""
import atexit, hashlib, os, re, subprocess, sys, time

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import run_mode
import serial as ser

PORT = int(sys.argv[1])
TOTAL = 5
B = os.path.join(ROOT, 'build')
SRC = os.path.abspath(sys.argv[2]) if len(sys.argv) > 2 else os.path.join(B, 'combined.img')
D = os.path.join(B, 'port-stop.d')
PF = qemu_pid.pidfile('port-stop')            # under QEMU_PIDDIR, the recipe's kill trap
_D = ('forth/dict/ahci.fth',)
_MODE = run_mode.resolve(ROOT, private=_D, tree=_D)
if not _MODE.private:
    print(f'SKIPPED (public mode: PRIVATE_REPO absent): test-port-stop, {TOTAL} checks not run '
          '(AHCI is private)', flush=True)
    sys.exit(0)

if not os.path.exists(SRC):
    sys.exit(f'NO INPUT: {SRC} (make combined)')
os.makedirs(D, exist_ok=True)
atexit.register(qemu_pid.kill_pidfile, PF)
PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}', flush=True)
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''), flush=True)


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


IMG, DISK = os.path.join(D, 'image.img'), os.path.join(D, 'disk.img')
subprocess.run(['cp', SRC, IMG], check=True)
with open(DISK, 'wb') as f:
    f.truncate(4 << 20)
for p in (SRC, os.path.join(ROOT, 'forth', 'dict', 'ahci.fth'),
          os.path.join(ROOT, 'forth', 'dict', 'hardware.fth'), os.path.abspath(__file__)):
    print(f'input sha256 {sha(p)}  {p}', flush=True)
for p in (IMG, DISK):
    assert os.path.dirname(os.path.realpath(p)) == os.path.realpath(D), p

qemu_pid.kill_pidfile(PF)
r = subprocess.run(['qemu-system-i386', '-m', '256',
                    '-drive', f'file={IMG},format=raw,if=floppy',
                    '-drive', f'file={DISK},format=raw,if=none,id=sata0',
                    '-device', 'ich9-ahci,id=ahci0',
                    '-device', 'ide-hd,drive=sata0,bus=ahci0.0',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                    '-display', 'none', '-daemonize', '-pidfile', PF], capture_output=True)
qemu_pid.check_launch(r, PF, PORT, 'port-stop')
s = ser.connect_and_sync(PORT, budget=60)


def send(cmd, budget=60.0):
    t = time.monotonic()
    rep, how = ser.send_until_prompt(s, cmd, budget=budget)
    dt = time.monotonic() - t
    body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
    print(f'>>> {cmd}\n    {body.strip()!r}  [{how}, {dt:.3f} s]', flush=True)
    return body, dt


def nums(body):
    return re.findall(r'(?<![\w-])-?[0-9A-F]+(?![\w-])', body.replace('ok', ' '))


def depth():
    v = nums(send('DECIMAL DEPTH .')[0])
    return v[-1] if v else None


# T0 (control): AHCI-INIT finds the drive; the stack is clean.
send('ONLY FORTH ALSO HARDWARE ALSO AHCI HEX')
body, _ = send('AHCI-INIT', budget=60)
d0 = depth()
check('T0 (control) AHCI-INIT: "AHCI at" and "Drive on port 0"; DEPTH 0',
      'AHCI at' in body and re.search(r'Drive on port\s+0\b', body) is not None and d0 == '0',
      f'{body.strip()!r}, DEPTH {d0}')

# Stretch the delay: US-LOOPS x 100 (hex).  The product US-LOOPS x 3E8 must stay
# below 2^31 or US-DELAY's 0> test skips the loop.
cal = nums(send('HEX US-LOOPS @ .')[0])
cal = int(cal[-1], 16) if cal else 0
stretched = cal * 0x100
print(f'US-LOOPS {cal} (decimal); stretched {stretched}; '
      f'loops per 1 MS-DELAY {stretched * 1000}', flush=True)
if not (0 < stretched * 1000 < 2 ** 31):
    print('INSTRUMENT FAIL: the stretched delay overflows US-DELAY; no measurement', flush=True)
    sys.exit(3)
send('HEX US-LOOPS @ 100 * US-LOOPS !')

# T1 (instrument): one 1 MS-DELAY, timed, the round trip subtracted.  At
# least 1 s, so the round trip (the reply's 0.3 s quiet plus tens of ms)
# cannot be counted as a delay.
_, base = send('HEX', budget=10)   # a command with no delay: the round trip
_, t1 = send('1 MS-DELAY', budget=120)
t1 -= base
check(f'T1 (instrument) one stretched 1 MS-DELAY takes 1-30 s: {t1:.3f} s', 1.0 <= t1 <= 30.0)
if not 1.0 <= t1 <= 30.0:
    print('INSTRUMENT FAIL: T1 out of range; no count', flush=True)
    sys.exit(3)

# T2 (instrument): two delays count 2.
_, t2 = send('1 MS-DELAY 1 MS-DELAY', budget=240)
n2 = round((t2 - base) / t1)
check(f'T2 (instrument) "1 MS-DELAY 1 MS-DELAY" counts 2: {(t2 - base) / t1:.3f}', n2 == 2)

# T3: PORT-STOP's delays.  1 = the 1 ms after CR clears (what iron ran).
_, tp = send('PORT-STOP', budget=600)
n3 = round((tp - base) / t1)
check(f'T3 PORT-STOP runs one 1 ms delay (the wait after CR clears): '
      f'{(tp - base) / t1:.3f} delays', n3 == 1, f'counted {n3}')

# T4 (control): PORT-STOP left ST, FRE, CR and FR clear; DEPTH 0.
pc = nums(send('HEX PxCMD P@ C011 AND .')[0])
d4 = depth()
check('T4 (control) after PORT-STOP, PxCMD AND C011 is 0 (ST, FRE, FR, CR clear); DEPTH 0',
      pc[-1:] == ['0'] and d4 == '0', f'PxCMD&C011 {pc}, DEPTH {d4}')

print(f'\n' + _MODE.line(PASS, TOTAL), flush=True)
sys.exit(0 if PASS == TOTAL and PASS + FAIL == TOTAL else 1)
