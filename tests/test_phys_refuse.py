#!/usr/bin/env python3
"""A refused DMA buffer is refused by the driver, not used at address 0
(private TASK_PHYS_CEILING, the drivers' part). Ten checks: B1, B2, L1,
R1, R2, A1, A2, C1, N1, N2.

  python3 tests/test_phys_refuse.py <serial-port>     (cwd: tree root)

AHCI, RTL8168 and NTFS take their DMA buffers with PHYS-ALLOC when they
load and used the result unchecked: with the pool exhausted each buffer
is 0, and the drivers wrote, and had the controller write, at physical 0.
Each entry word now refuses a 0 buffer ("DMA BUFFER REFUSED") and
returns its own failure, so its caller's failure path runs; UDP-SEND,
with no failure path, aborts.

The free kernel (build/bmforth-free.img) with the full block image
(build/blocks.img), so the drivers load from blocks after the pool is
exhausted. An AHCI disk: the g6 fixture (tests/g6_fixture.py) plus a
minimal NTFS boot sector at its first NTFS partition, so NTFS-INIT reaches
MFT-READ0. No NIC: QEMU has no RTL8168, so RTL8168-INIT's refusal is not
exercised here. Low memory is the witness: 0x5A over 0x0-0x4FF (below
every window ForthOS owns, forth.asm mb2_windows from 0x500), read with
the monitor's pmemsave, refilled before each step.

The subject is private (ahci, rtl8168, ntfs, auto-detect): with
PRIVATE_REPO absent at the Makefile default the test is SKIPPED, not
passed; set but absent, or present without the drivers, it fails.
"""
import atexit, hashlib, os, re, socket, struct, subprocess, sys, time

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import serial as ser
import g6_fixture

PORT = int(sys.argv[1])
TOTAL = 10
B = os.path.join(ROOT, 'build')
D = os.path.join(B, 'phys-refuse.d')
PF = os.path.join(D, 'qemu.pid')
MON = os.path.join(D, 'monitor.sock')
DUMP = os.path.join(D, 'low.bin')
LOW = 0x500
DRIVERS = ('ahci.fth', 'rtl8168.fth', 'ntfs.fth', 'auto-detect.fth')
PRIV_REPO = os.environ.get('PRIVATE_REPO') or os.path.join(ROOT, '..', 'forthos-vocabularies')
PRIV_ORIGIN = os.environ.get('PRIVATE_REPO_ORIGIN', 'file')
if os.path.isdir(os.path.join(PRIV_REPO, 'forth', 'dict')):
    _miss = [w + '/forth/dict/' + f for w in (PRIV_REPO, ROOT) for f in DRIVERS
             if not os.path.exists(os.path.join(w, 'forth', 'dict', f))]
    if _miss:
        print(f'FAIL: PRIVATE_REPO {PRIV_REPO} found, the drivers not: {_miss} '
              '(no fallback to public mode)', flush=True)
        sys.exit(1)
elif PRIV_ORIGIN != 'file':
    print(f'FAIL: PRIVATE_REPO set ({PRIV_ORIGIN}) to {PRIV_REPO}, not found '
          '(no fallback to public mode)', flush=True)
    sys.exit(1)
else:
    print(f'SKIPPED (public mode: PRIVATE_REPO absent): test-phys-refuse, {TOTAL} checks not run '
          '(AHCI, RTL8168, NTFS are private)', flush=True)
    sys.exit(0)

for need in ('bmforth-free.img', 'blocks.img'):
    if not os.path.exists(os.path.join(B, need)):
        sys.exit(f'NO INPUT: build/{need} (make free combined)')
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


# ---- fixtures: the free kernel then the blocks, an IDE copy, the AHCI disk
IMG, IDE, DISK = (os.path.join(D, n) for n in ('image.img', 'ide.img', 'disk.img'))
with open(IMG, 'wb') as out:
    for part in ('bmforth-free.img', 'blocks.img'):
        out.write(open(os.path.join(B, part), 'rb').read())
subprocess.run(['cp', IMG, IDE], check=True)
if os.path.exists(DISK):
    os.remove(DISK)
g6_fixture.build(DISK)
NTFS_LBA = 567296                                # the first NTFS partition (g6_fixture.PARTS)
bs = bytearray(512)
bs[0:3] = b'\xEB\x52\x90'
bs[3:11] = b'NTFS    '
bs[0x0B:0x0D] = struct.pack('<H', 512)
bs[0x0D] = 8                                     # sectors per cluster
bs[0x30:0x38] = struct.pack('<Q', 4)             # MFT at cluster 4: LBA NTFS_LBA + 32
bs[510:512] = b'\x55\xAA'
with open(DISK, 'r+b') as f:
    f.seek(NTFS_LBA * 512)
    f.write(bs)
REGIONS = ((0, 34), (NTFS_LBA, 256))             # GPT and the partition's first 128 KB


def disk_hash():
    h = hashlib.sha256()
    with open(DISK, 'rb') as f:
        for lba, n in REGIONS:
            f.seek(lba * 512)
            h.update(f.read(n * 512))
    return h.hexdigest()


DISK0 = disk_hash()
for p in (os.path.join(B, 'bmforth-free.img'), os.path.join(B, 'blocks.img'),
          os.path.join(ROOT, 'forth', 'dict', 'hardware.fth')) + \
        tuple(os.path.join(ROOT, 'forth', 'dict', f) for f in DRIVERS) + (os.path.abspath(__file__),):
    print(f'input sha256 {hashlib.sha256(open(p, "rb").read()).hexdigest()}  {p}', flush=True)
print(f'disk regions sha256 {DISK0}', flush=True)


def mon(cmd):
    m = socket.socket(socket.AF_UNIX)
    m.connect(MON)
    m.settimeout(2)
    try:
        m.recv(4096)
    except socket.timeout:
        pass
    m.sendall(cmd.encode() + b'\n')
    time.sleep(0.5)
    m.close()


def low():
    """Physical 0x0-0x4FF, read by the monitor."""
    if os.path.exists(DUMP):
        os.remove(DUMP)
    mon(f'pmemsave 0 {LOW:#x} "{DUMP}"')
    for _ in range(50):
        if os.path.exists(DUMP) and os.path.getsize(DUMP) == LOW:
            break
        time.sleep(0.1)
    return open(DUMP, 'rb').read() if os.path.exists(DUMP) else b''


def whole(mem):
    return mem == b'\x5A' * LOW


def broken(mem):
    bad = [i for i, c in enumerate(mem) if c != 0x5A]
    return f'{len(bad)} bytes changed, first at {bad[0]:#x}' if bad else ('unread' if len(mem) != LOW else 'whole')


def boot(role):
    qemu_pid.kill_pidfile(PF)
    for p in (MON,):
        if os.path.exists(p):
            os.remove(p)
    r = subprocess.run(['qemu-system-i386', '-m', '256',
                        '-drive', f'file={IMG},format=raw,if=floppy',
                        '-drive', f'file={IDE},format=raw,if=ide,index=1',
                        '-drive', f'file={DISK},format=raw,if=none,id=sata0',
                        '-device', 'ich9-ahci,id=ahci0',
                        '-device', 'ide-hd,drive=sata0,bus=ahci0.0',
                        '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                        '-monitor', f'unix:{MON},server=on,wait=off',
                        '-display', 'none', '-daemonize', '-pidfile', PF], capture_output=True)
    qemu_pid.check_launch(r, PF, PORT, role)
    return ser.connect_and_sync(PORT, budget=60)


def send(s, cmd, budget=60.0):
    rep, how = ser.send_until_prompt(s, cmd, budget=budget)
    body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
    print(f'>>> {cmd}\n    {body.strip()!r}  [{how}]', flush=True)
    return body


def nums(body):
    return [int(t) for t in re.findall(r'(?<![\w-])-?\d+(?![\w-])', body.replace('ok', ' '))]


def depth(s):
    v = nums(send(s, 'DECIMAL DEPTH .'))
    return v[-1] if v else None


def fill(s):
    send(s, 'HEX 0 500 5A FILL DECIMAL')


ORDER = 'ONLY FORTH ALSO HARDWARE ALSO RTL8168 ALSO AHCI ALSO NTFS ALSO AUTO-DETECT DECIMAL'
REFUSED = 'DMA BUFFER REFUSED'

try:
    # ---- Boot 1: the pool exhausted before the load
    s = boot('phys-refuse-1')
    send(s, 'DECIMAL')
    fill(s)
    m0 = low()
    send(s, 'HEX 77 100 C! DECIMAL')
    m1 = low()
    fill(s)
    m2 = low()
    check('B1 (control) the sentinel reads back whole; a byte stored at 0x100 is seen',
          whole(m0) and len(m1) == LOW and m1[0x100] == 0x77 and m1[:0x100] + m1[0x101:] == b'\x5A' * (LOW - 1)
          and whole(m2), f'{broken(m0)}; at 0x100 {m1[0x100:0x101].hex() if len(m1) == LOW else None}; {broken(m2)}')

    send(s, 'ALSO HARDWARE')
    send(s, 'HEX PHYS-HEAP-END @ PHYS-HEAP @ - PHYS-ALLOC DROP DECIMAL')
    b = send(s, 'HEX 1000 PHYS-ALLOC . DECIMAL')
    check('B2 (control) the pool exhausted: 1000 PHYS-ALLOC gives 0', nums(b)[-1:] == [0], f'{b.strip()!r}')

    b = send(s, 'S" AUTO-DETECT" LOAD-VOCAB', 300.0)
    d = depth(s)
    check('L1 (control) S" AUTO-DETECT" LOAD-VOCAB loads (RTL8168, AHCI, NTFS), no abort, DEPTH 0',
          '?' not in b and 'ABORT' not in b.upper() and d == 0, f'depth {d}; {b.strip()[-200:]!r}')

    send(s, ORDER)
    fill(s)
    b = send(s, 'S" x" RTL8168-SEND .')
    m = low()
    check('R1 RTL8168-SEND direct: "DMA BUFFER REFUSED", 1; low memory whole',
          REFUSED in b and nums(b)[-1:] == [1] and whole(m), f'{b.strip()!r}; {broken(m)}')

    fill(s)
    b = send(s, 'S" x" UDP-SEND')
    b2 = send(s, '7 .')
    m = low()
    check('R2 UDP-SEND: "DMA BUFFER REFUSED", aborted (no TX), the prompt answers 7; low memory whole',
          REFUSED in b and 'TX timeout' not in b and nums(b2)[-1:] == [7] and whole(m),
          f'{b.strip()!r} / {b2.strip()!r}; {broken(m)}')

    send(s, ORDER)
    fill(s)
    b = send(s, 'TRY-AHCI AUTO-DETECT-REPORT')
    m = low()
    check('A1 caller TRY-AHCI AUTO-DETECT-REPORT: "DMA BUFFER REFUSED", "AHCI: none"; low memory whole',
          REFUSED in b and 'AHCI: none' in b and whole(m), f'{b.strip()!r}; {broken(m)}')

    fill(s)
    b = send(s, 'MBR.')
    m = low()
    check('A2 caller MBR.: "DMA BUFFER REFUSED", "Read err"; low memory whole',
          REFUSED in b and 'Read err' in b and whole(m), f'{b.strip()!r}; {broken(m)}')
    qemu_pid.kill_pidfile(PF)

    # ---- Boot 2: AHCI on a fresh pool, then the pool exhausted, then NTFS
    s = boot('phys-refuse-2')
    send(s, 'DECIMAL')
    send(s, 'S" AHCI" LOAD-VOCAB', 300.0)
    send(s, 'ONLY FORTH ALSO HARDWARE ALSO AHCI DECIMAL')
    fill(s)
    b = send(s, 'AHCI-INIT')
    f_ = send(s, 'AH-FOUND @ 0<> .')
    r = send(s, '0 1 AHCI-READ .')
    m = low()
    check('C1 (control) AHCI on a fresh pool: drive found, 0 1 AHCI-READ gives 0; low memory whole',
          nums(f_)[-1:] == [-1] and nums(r)[-1:] == [0] and whole(m),
          f'{b.strip()!r} / {f_.strip()!r} / {r.strip()!r}; {broken(m)}')

    send(s, 'HEX PHYS-HEAP-END @ PHYS-HEAP @ - PHYS-ALLOC DROP DECIMAL')
    send(s, 'HEX 1000 PHYS-ALLOC . DECIMAL')
    send(s, 'S" NTFS" LOAD-VOCAB', 300.0)
    send(s, 'ONLY FORTH ALSO HARDWARE ALSO AHCI ALSO NTFS DECIMAL')
    fill(s)
    b = send(s, 'NTFS-INIT')
    m = low()
    check('N1 caller NTFS-INIT: "NTFS at LBA", "DMA BUFFER REFUSED", "MFT read err"; low memory whole',
          'NTFS at LBA' in b and REFUSED in b and 'MFT read err' in b and whole(m), f'{b.strip()!r}; {broken(m)}')

    fill(s)
    b = send(s, '0 MFT-WRITE .')
    m = low()
    qemu_pid.kill_pidfile(PF)
    d1 = disk_hash()
    check('N2 MFT-WRITE direct: "DMA BUFFER REFUSED", 1; low memory whole; the disk unchanged',
          REFUSED in b and nums(b)[-1:] == [1] and whole(m) and d1 == DISK0,
          f'{b.strip()!r}; {broken(m)}; disk {"unchanged" if d1 == DISK0 else "changed " + d1}')
finally:
    qemu_pid.kill_pidfile(PF)

print(f'\nPassed: {PASS}/{TOTAL}')
sys.exit(0 if FAIL == 0 and PASS == TOTAL else 1)
