#!/usr/bin/env python3
"""A failed read is reported, not taken as data (private TASK_READ_FLAGS).
Ten checks: G0, G1, K0, K1, K2, X0, F0, F1, S0, S1.

  python3 tests/test_read_flags.py <serial-port>     (cwd: tree root)

Four callers dropped a read's failure flag and used the old buffer:
GPT-PARTS decoded it as partition rows, AHCI's BLOCK returned it as the
block, SEND-RUN sent it as file data, FB-OPEN-FILE opened it as the file.
Now GPT-PARTS prints "Read err" and no rows, BLOCK aborts with BLOCK READ
FAILED, SEND-RUN stops and FILE-STREAM prints "Read err" (no EOF, no
Streamed), and FB-OPEN-FILE shows "MFT read err" and opens nothing.

The failed reads are real: the AHCI disk sits behind QEMU's blkdebug,
which fails a read covering the injected sector with EIO. One failed read
wedges the AHCI port (every later read prints "not ready"; private
finding-ahci-port-wedge-2026-10-31), so each boot injects one sector.
K2's only evidence that the second BLOCK reads again is that wedge's
"not ready": it holds only while the wedge stands. The wedge's fix
re-pins K2 (the second BLOCK returns the block's correct contents, a
fresh read, under a one-shot blkdebug error), pre-registered then.

The fixture is built once and tracked in the private repo
(tests/fixtures/read-flags: disk.img.gz, its build commands and tool
versions); its image hash is checked before any boot and the sectors are
pinned from it. Each boot is build/combined.img (copied) on floppy, a copy
on IDE index 1 (the block-loaded FILE-BROWSER), the fixture on ICH9 AHCI.
The screen is read from 0xB8000 by the monitor (a unix socket).

The subject is private (ahci, file-stream, ntfs): with PRIVATE_REPO absent
at the Makefile default the test is SKIPPED, not passed; set but absent,
or present without the drivers or the fixture, it fails.
"""
import atexit, gzip, hashlib, os, re, socket, subprocess, sys, time

ROOT = os.getcwd()
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid
import run_mode
import serial as ser

PORT = int(sys.argv[1])
TOTAL = 10
B = os.path.join(ROOT, 'build')
D = os.path.join(B, 'read-flags.d')
PF = os.path.join(D, 'qemu.pid')
MON = os.path.join(D, 'monitor.sock')
DUMP = os.path.join(D, 'vga.bin')
DRIVERS = ('ahci.fth', 'file-stream.fth', 'ntfs.fth')
FIX = os.path.join('tests', 'fixtures', 'read-flags', 'disk.img.gz')
IMG_SHA = '1455f18de181095a4069c8c3903b89dc3b8a1838d3479b72f2ec88a51b9c5d98'
GPT_ENTRIES, BLOCK_SECTOR, REC65, BIG_BATCH2 = 2, 30000, 2210, 4944
BLOCK_N = 14887                                  # (30000 - BLOCKS-LBA-BASE E1) / 2
_D = tuple('forth/dict/' + f for f in DRIVERS)
_MODE = run_mode.resolve(ROOT, private=_D + (FIX,), tree=_D)
PRIV_REPO = _MODE.repo
if not _MODE.private:
    print(f'SKIPPED (public mode: PRIVATE_REPO absent): test-read-flags, {TOTAL} checks not run '
          '(AHCI, FILE-STREAM, NTFS and the fixture are private)', flush=True)
    sys.exit(0)

if not os.path.exists(os.path.join(B, 'combined.img')):
    sys.exit('NO INPUT: build/combined.img (make combined)')
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


# ---- inputs: the product image copied, an IDE copy, the tracked fixture
IMG, IDE, DISK, CONF = (os.path.join(D, n) for n in ('image.img', 'ide.img', 'disk.img', 'bd.conf'))
subprocess.run(['cp', os.path.join(B, 'combined.img'), IMG], check=True)
subprocess.run(['cp', IMG, IDE], check=True)
with open(DISK, 'wb') as f:
    f.write(gzip.decompress(open(os.path.join(PRIV_REPO, FIX), 'rb').read()))
for p in (os.path.join(B, 'combined.img'), os.path.join(PRIV_REPO, FIX)) + \
        tuple(os.path.join(ROOT, 'forth', 'dict', f) for f in DRIVERS + ('file-browser.fth',)) + \
        (os.path.abspath(__file__),):
    print(f'input sha256 {sha(p)}  {p}', flush=True)
print(f'fixture image sha256 {sha(DISK)}  {DISK}', flush=True)
if sha(DISK) != IMG_SHA:
    print(f'FAIL: fixture image is not {IMG_SHA}; no boot', flush=True)
    sys.exit(1)
for p in (IMG, IDE, DISK, CONF):
    assert os.path.dirname(os.path.realpath(p)) == os.path.realpath(D), p


def boot(sector, role):
    qemu_pid.kill_pidfile(PF)
    if os.path.exists(MON):
        os.remove(MON)
    with open(CONF, 'w') as f:
        f.write('[inject-error]\nevent = "read_aio"\nerrno = "5"\n'
                f'sector = "{sector}"\nonce = "off"\n')
    print(f'--- boot {role}: read error injected at LBA {sector}', flush=True)
    r = subprocess.run(['qemu-system-i386', '-m', '256',
                        '-drive', f'file={IMG},format=raw,if=floppy',
                        '-drive', f'file={IDE},format=raw,if=ide,index=1',
                        '-drive', f'file=blkdebug:{CONF}:{DISK},format=raw,if=none,id=sata0',
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
    return re.findall(r'(?<![\w-])-?[0-9A-F]+(?![\w-])', body.replace('ok', ' '))


def depth(s):
    v = nums(send(s, 'DECIMAL DEPTH .'))
    return v[-1] if v else None


def screen_rows():
    """The 25 text rows, read from 0xB8000 by the monitor."""
    if os.path.exists(DUMP):
        os.remove(DUMP)
    m = socket.socket(socket.AF_UNIX)
    m.connect(MON)
    m.settimeout(2)
    try:
        m.recv(4096)
    except socket.timeout:
        pass
    m.sendall(f'pmemsave 0xB8000 4000 "{DUMP}"\n'.encode())
    time.sleep(0.5)
    m.close()
    for _ in range(50):
        if os.path.exists(DUMP) and os.path.getsize(DUMP) == 4000:
            break
        time.sleep(0.1)
    if not os.path.exists(DUMP):
        return []
    txt = open(DUMP, 'rb').read()[0::2].decode('ascii', 'replace')
    return [txt[i * 80:(i + 1) * 80].rstrip() for i in range(25)]


DRV = 'ALSO AHCI'
NTFS = 'ALSO NTFS'

try:
    # ---- Boot G: the GPT entries (LBA 2) fail; the header (LBA 1) reads
    s = boot(GPT_ENTRIES, 'read-flags-G')
    send(s, DRV)
    send(s, 'AHCI-INIT')
    g = send(s, 'GPT.')
    check('G0 (control) GPT. reads the header: "LBA1: 45 46 49 20 50 41 52 54", then "CMD timeout"',
          'LBA1: 45 46 49 20 50 41 52 54' in g and 'CMD timeout' in g, repr(g))
    gd = depth(s)
    rows = re.findall(r'P[1-4]:', g)
    check('G1 the failed entries read: "Read err", no P1-P4 row; DEPTH 0',
          'Read err' in g and not rows and gd == '0', f'rows {rows}; Read err {"Read err" in g}; DEPTH {gd}')

    # ---- Boot K: AHCI's BLOCK of a block covering LBA 30000
    s = boot(BLOCK_SECTOR, 'read-flags-K')
    send(s, DRV)
    send(s, 'AHCI-INIT')
    k0 = send(s, 'DECIMAL 991 BLOCK 512 + 4 TYPE CR DEPTH .')
    check('K0 (control) BLOCK 991 through AHCI shows record 64: "FILE"; DEPTH 0',
          'FILE' in k0 and nums(k0)[-1:] == ['0'], repr(k0))
    k1 = send(s, f'DECIMAL {BLOCK_N} BLOCK DUP 4 TYPE CR DEPTH .')
    k1d = depth(s)
    check(f'K1 BLOCK {BLOCK_N} (its read failed): "BLOCK READ FAILED", aborted (the line\'s DEPTH . not run); '
          'DEPTH 0 (today: no message, DEPTH 1; the bytes typed are not the evidence)',
          'BLOCK READ FAILED' in k1 and not nums(k1) and k1d == '0', f'{k1!r}; DEPTH {k1d}')
    k2 = send(s, f'DECIMAL {BLOCK_N} BLOCK DEPTH .')
    k2d = depth(s)
    k2x = send(s, '7 6 * .')
    check(f'K2 BLOCK {BLOCK_N} again reads again ("not ready", evidence only while the port wedge stands), '
          '"BLOCK READ FAILED" again; DEPTH 0; 7 6 * . gives 42',
          'not ready' in k2 and 'BLOCK READ FAILED' in k2 and not nums(k2) and k2d == '0'
          and nums(k2x)[-1:] == ['42'], f'{k2!r}; DEPTH {k2d}; {k2x!r}')

    # ---- Boot F: record 65 (BAD.TXT) fails
    s = boot(REC65, 'read-flags-F')
    send(s, DRV)
    send(s, 'AHCI-INIT')
    send(s, NTFS)
    send(s, 'NTFS-INIT')
    x0 = send(s, 'HEX 41 REC-LBA . DECIMAL')
    check(f'X0 (control) record 65 is where the error is: 41 REC-LBA gives {REC65:X}',
          nums(x0)[-1:] == [f'{REC65:X}'], repr(x0))
    send(s, 'S" FILE-BROWSER" LOAD-VOCAB', budget=120)
    send(s, 'ALSO FILE-EDITOR ALSO FILE-BROWSER')
    f0 = send(s, 'HEX 0 FB-EDIT-MODE ! 40 FB-OPEN-FILE FB-EDIT-MODE @ . FE-SIZE @ . DECIMAL')
    f0b = send(s, 'DECIMAL FE-BUF 13 TYPE')
    check('F0 (control) 40 FB-OPEN-FILE opens GOOD.TXT: FB-EDIT-MODE 1, FE-SIZE 13 (hex), FE-BUF "GOOD-RESIDENT"',
          nums(f0)[-2:] == ['1', '13'] and 'GOOD-RESIDENT' in f0b, f'{f0!r}; {f0b!r}')
    send(s, 'HEX 0 FB-EDIT-MODE ! FE-BUF 40 0 FILL 0 FE-SIZE ! DECIMAL')
    f1 = send(s, 'HEX 41 FB-OPEN-FILE DECIMAL')
    r23 = (screen_rows() + [''] * 25)[23]
    f1n = send(s, 'HEX FB-EDIT-MODE @ . FE-SIZE @ . FE-BUF C@ . DECIMAL')
    f1d = depth(s)
    check('F1 41 FB-OPEN-FILE (its record failed): "CMD timeout"; row 23 "MFT read err"; '
          'FB-EDIT-MODE 0, FE-SIZE 0, FE-BUF 0; DEPTH 0',
          'CMD timeout' in f1 and 'MFT read err' in r23 and nums(f1n)[-3:] == ['0', '0', '0'] and f1d == '0',
          f'{f1!r}; row 23 {r23!r}; {f1n!r}; DEPTH {f1d}')

    # ---- Boot S: BIG.BIN's second batch (LBA 4944) fails; a test sink
    s = boot(BIG_BATCH2, 'read-flags-S')
    # FILE-STREAM is block-loaded since 2026-11-11 (private
    # TASK_KERNEL_PAD_HEADROOM): load it before any *-INIT.
    send(s, 'S" FILE-STREAM" LOAD-VOCAB', budget=120)
    send(s, DRV)
    send(s, 'AHCI-INIT')
    send(s, NTFS)
    send(s, 'NTFS-INIT')
    send(s, 'ALSO FILE-STREAM')
    send(s, 'DECIMAL VARIABLE TS-N  VARIABLE TS-LEN  CREATE TS-F 64 ALLOT')
    send(s, ': TSINK DUP STREAM-SENT +! DUP TS-LEN +! DROP @ TS-N @ CELLS TS-F + ! 1 TS-N +! ;')
    send(s, "' TSINK 'FILE-SINK !")
    st = send(s, 'S" BIG.BIN" FILE-STREAM', budget=120)
    check('S0 (control) FILE-STREAM finds BIG.BIN ("Found rec 66"), then "CMD timeout"',
          'Found rec 66' in st and 'CMD timeout' in st, repr(st))
    sn = send(s, 'HEX TS-N @ . TS-LEN @ . TS-F @ . DECIMAL')
    sd = depth(s)
    check('S1 the failed batch: "Read err"; one sink call, 1000 (hex) bytes, first cell 5EC00000; '
          'no "Streamed", no "TX timeout" (STREAM-DONE not reached); DEPTH 0',
          'Read err' in st and nums(sn)[-3:] == ['1', '1000', '5EC00000']
          and 'Streamed' not in st and 'TX timeout' not in st and sd == '0',
          f'{st!r}; {sn!r}; DEPTH {sd}')
finally:
    qemu_pid.kill_pidfile(PF)

print('\n' + _MODE.line(PASS, TOTAL), flush=True)
sys.exit(0 if PASS == TOTAL and PASS + FAIL == TOTAL else 1)
