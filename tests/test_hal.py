#!/usr/bin/env python3
"""HAL slice 1 (docs/TASK_HAL_DISPLAY.md): the binding mechanism and the
display contract, on the combined image booted by BIOS.

  python3 tests/test_hal.py <port>

  D1  host: @ ! C@ C! W@ W! and the port words INB INW INL OUTB OUTW OUTL
      (this kernel's PC@ / PC!) call nothing: direct access is never routed
      through a binding.
  Q1  the HAL vocabulary is there at boot (embedded).
  Q2  HAL-LIST shows FB-BASE and FB-FLUSH, both bound.
  Q3  FB-BASE = B8000 on this BIOS boot.
  Q4  an unbound vector aborts the line, naming itself: `HAL-VECTOR
      XQ-TEST  XQ-TEST 1 2 + .` prints `XQ-TEST: HAL vector not bound`,
      never `3`; DEPTH 0 after.
  Q5  a live rebind at the prompt takes effect on the next call: FB-BASE
      and UI-CORE's VGA-BASE both follow it, and binding back restores both.
  Q6  RELOAD-VOCAB refuses to free code a vector is bound to, naming the
      vector: MIRROR (block-loaded, nothing points into it) reloads (Q6a,
      the control); with FB-FLUSH bound to one of its words it is refused,
      naming FB-FLUSH (Q6b).
  Q7  DEPTH 0 at the end.
"""
import atexit, hashlib, os, re, shutil, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid          # noqa: E402
import serial as ser     # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4404
B = os.path.join(ROOT, 'build')
D = os.path.join(B, 'test-hal.d')
os.makedirs(D, exist_ok=True)
ASM = os.path.join(ROOT, 'src', 'kernel', 'forth.asm')
COMBINED = os.path.join(B, 'combined.img')
failures, checks = [], 0


def check(label, cond, detail=''):
    global checks
    checks += 1
    print(f'[{"PASS" if cond else "FAIL"}] {label} {detail}', flush=True)
    if not cond:
        failures.append(label)


for p in (COMBINED, ASM, os.path.abspath(__file__)):
    print(f'input sha256 {hashlib.sha256(open(p, "rb").read()).hexdigest()}  {p}', flush=True)

# ---- D1 (host): direct access calls nothing
src = open(ASM).read()
bad = []
for name in ('@', '!', 'C@', 'C!', 'W@', 'W!', 'INB', 'INW', 'INL', 'OUTB', 'OUTW', 'OUTL'):
    m = re.search(r'^DEFCODE "' + re.escape(name) + r'",[^\n]*\n(.*?)(?=^DEFCODE |^DEFWORD |^DEFVAR |^DEFCONST |^;)',
                  src, re.M | re.S)
    body = m.group(1) if m else ''
    if not m or re.search(r'\bcall\b|\bjmp\s+\[', body):
        bad.append(name)
check('D1 @ ! C@ C! W@ W! INB INW INL OUTB OUTW OUTL are direct: found, and call nothing', not bad,
      f'(not direct: {bad})')


def send(s, cmd, budget=30):
    rep, how = ser.send_until_prompt(s, cmd, budget=budget)
    body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
    print(f'>>> {cmd}\n    {body.strip()[-200:]!r}  [{how}]', flush=True)
    return body


def nums(b):
    return re.findall(r'(-?[0-9A-F]+) ok', b)


F, I = os.path.join(D, 'floppy.img'), os.path.join(D, 'ide.img')
shutil.copyfile(COMBINED, F)
shutil.copyfile(COMBINED, I)
pf = qemu_pid.pidfile('hal')
atexit.register(qemu_pid.kill_pidfile, pf)
p = subprocess.Popen(['qemu-system-i386', '-drive', f'file={F},format=raw,if=floppy',
                      '-drive', f'file={I},format=raw,if=ide,index=1',
                      '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                      '-display', 'none', '-pidfile', pf],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
qemu_pid.wait_started(p, pf, PORT, 'hal')
s = ser.connect_and_sync(PORT, budget=60)
try:
    b = send(s, 'ALSO HAL')
    check('Q1 the HAL vocabulary is there at boot', '?' not in b, f'({b.strip()!r})')
    b = send(s, 'HAL-LIST')
    rows = {m.group(1): m.group(2) for m in re.finditer(r'^(\S+) -> (.+?)\s*$', b, re.M)}
    check('Q2 HAL-LIST: FB-BASE and FB-FLUSH, both bound',
          {'FB-BASE', 'FB-FLUSH'} <= set(rows) and 'unbound' not in rows.get('FB-BASE', 'unbound')
          and 'unbound' not in rows.get('FB-FLUSH', 'unbound'), f'({rows})')
    b = send(s, 'HEX FB-BASE . DECIMAL')
    check('Q3 FB-BASE = B8000 (BIOS)', nums(b)[-1:] == ['B8000'], f'({b.strip()!r})')
    b = send(s, 'HAL-VECTOR XQ-TEST  XQ-TEST 1 2 + .')
    check('Q4 an unbound vector aborts the line, naming itself',
          'XQ-TEST: HAL vector not bound' in b and not re.search(r'\b3 ok', b), f'({b.strip()!r})')
    b = send(s, 'DECIMAL DEPTH .')
    check('Q4b DEPTH 0 after the abort', nums(b)[-1:] == ['0'], f'({b.strip()!r})')
    send(s, 'ALSO HAL')
    send(s, ': XQ-BASE 12345 ;')
    send(s, "' FB-BASE HAL-GET CONSTANT XQ-OLD")
    send(s, "' XQ-BASE BIND FB-BASE")
    b1 = send(s, 'DECIMAL FB-BASE .')
    b2 = send(s, 'ALSO UI-CORE DECIMAL VGA-BASE . PREVIOUS')
    send(s, "XQ-OLD ' FB-BASE HAL-SET")
    b3 = send(s, 'HEX FB-BASE . ALSO UI-CORE VGA-BASE . PREVIOUS DECIMAL')
    check('Q5 a live rebind takes effect on the next call (FB-BASE and UI-CORE VGA-BASE), and binding back restores both',
          nums(b1)[-1:] == ['12345'] and nums(b2)[-1:] == ['12345'] and re.search(r'B8000 B8000 ok', b3) is not None,
          f'(rebound {b1.strip()!r} / {b2.strip()!r}; back {b3.strip()!r})')
    # saved before MIRROR loads: anything compiled after a vocabulary blocks
    # its reload for that reason alone
    send(s, "' FB-FLUSH HAL-GET CONSTANT XQ-FL")
    send(s, 'S" MIRROR" LOAD-VOCAB', 90)
    b = send(s, 'S" MIRROR" RELOAD-VOCAB', 90)
    check('Q6a control: MIRROR reloads while nothing is bound into it',
          'refused' not in b and 'MIRROR vocabulary loaded' in b, f'({b.strip()[-120:]!r})')
    # MIRROR's load ends with ONLY FORTH DEFINITIONS: HAL back in the order
    send(s, 'ALSO HAL')
    b = send(s, "ALSO MIRROR ' MIRROR-BLK PREVIOUS BIND FB-FLUSH")
    if '?' in b:
        print('INSTRUMENT FAIL: the Q6b binding did not happen -- no score', flush=True)
        sys.exit(3)
    b = send(s, 'S" MIRROR" RELOAD-VOCAB', 90)
    check('Q6b RELOAD-VOCAB refuses to free code FB-FLUSH is bound to, naming it',
          'refused' in b and 'FB-FLUSH' in b, f'({b.strip()[-160:]!r})')
    send(s, "XQ-FL ' FB-FLUSH HAL-SET")
    b = send(s, 'ONLY FORTH DEFINITIONS DECIMAL DEPTH .')
    check('Q7 DEPTH 0 at the end', nums(b)[-1:] == ['0'], f'({b.strip()!r})')
finally:
    s.close()
    qemu_pid.kill_pidfile(pf)

print(f'Passed: {checks - len(failures)}/{checks}', flush=True)
sys.exit(0 if not failures else 1)
