#!/usr/bin/env python3
"""FAT32 read gate: FAT32 loaded from blocks reads a real FAT32 partition
and refuses a FAT16 one (private TASK_KERNEL_PAD_HEADROOM, the step-17
dry-run, owner 2026-11-12).

FAT32 left EMBED_VOCABS on 2026-11-11.  Before this gate no test read a
FAT32 partition at all: the suite loaded FAT32 (test-g6, test-vocab-dedup,
test-survey, test-resolve-deps) but only DISK-SURVEY reads one, and no
wired test runs it.  This gate reads one, on both boot paths, so the HP
trip only confirms what QEMU already showed.

The stick replica is test_uefi_boot.py's, built the same way (GPT, the
ESP holding GRUB, memdisk and forth.img = the combined image), booted
under OVMF (UEFI, multiboot2) and under SeaBIOS (GRUB, then memdisk).
One disk is added on q35's built-in AHCI, port 0, and each firmware boots
twice, once per disk.  Both disks are pinned 64 MiB GPT images whose one
partition (type EF00, LBA 2048) is formatted by mkfs.fat --invariant:
  FAT32 disk: root = EFI (a directory) + HELLO.TXT (12 bytes); EFI holds
              "Long File Name.txt", so the listing runs .LFN
  FAT16 disk: root = HELLO.TXT; FAT32-INIT must refuse it
The stick carries bootindex=0, so no firmware tries the AHCI disk first.

The kernel's LEAVE only sets index = limit (forth.asm LEAVE); the rest of
the loop body still runs.  Three fat32.fth sites ran code after LEAVE:
DIR-LIST and FAT32-FIND at the end-of-directory entry, .LFN at the NUL.
Each leaves the data stack short by one, so F4c, F6b, F7b and F8b put a
sentinel (77) under the word and read it back: DECIMAL DEPTH . . must
print 1 77 (DECIMAL first: FAT32-LS returns with BASE 16).

  H1      the FAT32 disk, read on the host: ESP type C12A7328 at LBA 2048;
          BPB FATSz16 (16h) = 0, RootEntCnt (11h) = 0, FATSz32 (24h) <> 0;
          root = EFI + HELLO.TXT, no LFN, ended by a 0 entry in its first
          cluster; EFI = . .. + one LFN-named file (name < 104 chars, so
          .LFN reaches a NUL), ended in its first cluster; FAT entry 77
          is 0 (free).  Every value F3, F4 and F8 expect is read here.
  H2      the FAT16 disk, read on the host: ESP type at LBA 2048, FATSz16
          <> 0 and RootEntCnt <> 0 (FAT32-INIT must say Not FAT32), and the
          cell at 24h <> 0 (the old test, FATSz32 <> 0, accepted it).
  Per firmware (U = OVMF, L = SeaBIOS/memdisk), FAT32 disk, 16 each:
  F0      banner + ok
  F0b     BOOT-MODE: 3 (OVMF), 1 (memdisk)
  F1      S" FAT32" LOAD-VOCAB: skip lines AHCI, HARDWARE (fat32.fth:6),
          no ?, ok
  F2      USING AHCI AHCI-INIT: "Drive on port 0", "AHCI ok"
  F3      ONLY FORTH DEFINITIONS USING FAT32 FAT32-INIT: exactly
          EFI at LBA / FAT at LBA / Data at LBA / Root clust /
          Sects/clust / FAT32 ready, with the values H1 read
  F4a     DECIMAL 77 FAT32-LS, first line: "EFI <DIR> cl=<c>" (one space
          before <DIR>: the block store keeps both of ."  <DIR>"'s spaces)
  F4      the same reply: exactly the root as H1 read it, in disk order
  F4b     BASE @ DECIMAL . prints 16: FAT32-INIT and DIR-LIST end with
          DECIMAL . HEX, so FAT32-LS returns with BASE 16.  Pinned so the
          HP card's DECIMAL after FAT32-LS stays needed until this check
          says otherwise.
  F4c     DECIMAL DEPTH . . prints 1 77: DIR-LIST left the sentinel
  F6      DECIMAL 77 S" NOPE.TXT" FAT32-CD: exactly "Not found"
  F6b     DECIMAL DEPTH . . prints 1 77: FAT32-FIND left the sentinel
  F7      DECIMAL LFN-RESET 65 LFN-BUF C! 66 LFN-BUF 1+ C! 77 .LFN CR:
          exactly "AB" (.LFN alone, no disk)
  F7b     DECIMAL DEPTH . . prints 1 77: .LFN left the sentinel
  F8      DECIMAL 77 S" EFI" FAT32-CD FAT32-LS: exactly EFI as H1 read
          it, the long name printed in full
  F8b     DECIMAL DEPTH . . prints 1 77
  F5      ONLY FORTH DEFINITIONS DECIMAL DEPTH .: 0
  Per firmware, FAT16 disk, 5 each:
  G0      banner + ok
  G1      S" FAT32" LOAD-VOCAB as F1
  G2      USING AHCI AHCI-INIT as F2
  G3      ONLY FORTH DEFINITIONS USING FAT32 FAT32-INIT: exactly
          "EFI at LBA 00000800" and "Not FAT32"
  G4      ONLY FORTH DEFINITIONS DECIMAL DEPTH .: 0

Usage: test_fat32_read.py <serial port> [<combined.img>]
"""
import atexit
import hashlib
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid          # noqa: E402
import serial as ser     # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4533
IMG = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'build', 'combined.img')
SCRIPT = os.path.join(ROOT, 'tools', 'make-uefi-usb.sh')
OVMF_CODE = '/usr/share/OVMF/OVMF_CODE_4M.fd'
OVMF_VARS = '/usr/share/OVMF/OVMF_VARS_4M.fd'
MEMDISK = '/usr/lib/syslinux/memdisk'
BANNER = 'Bare-Metal Forth v0.1 - Ship Builders System'   # forth.asm msg_welcome (H0 checks it)
WAIT = 60
DISK_MIB = 64
EXPECTED = 1 + 2 + 2 * (16 + 5)          # H0 (banner cites, 2026-11-13), H1-H2, two legs
SENTINEL = 77                            # decimal; a free cluster (H1)

HELLO = b'hello world\n'                 # 12 bytes
LONG = b'long file name\n'               # 15 bytes
LONG_NAME = 'Long File Name.txt'          # not 8.3: mtools writes LFN entries
EPOCH = 1790000000                       # fixed; any constant
ESP_TYPE = 0xC12A7328                    # fat32.fth:33 EFI-GUID, first cell


def die(code, msg):
    print(msg)
    sys.exit(code)


def run(argv, **kw):
    r = subprocess.run(argv, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        die(3, f'INSTRUMENT FAIL: {" ".join(argv[:3])} ... rc {r.returncode}: '
               f'{(r.stderr or r.stdout).strip()[:300]}')
    return r


failures = []
passed = 0


def check(label, cond, detail=''):
    global passed
    if cond:
        passed += 1
        print(f'[PASS] {label} {detail}', flush=True)
    else:
        failures.append(label)
        print(f'[FAIL] {label} {detail}', flush=True)


# ---- H0: BANNER is the kernel's own welcome string, host side ----
_asm = open(os.path.join(ROOT, 'src', 'kernel', 'forth.asm')).read()
_mw = re.search(r"^msg_welcome:\s+db\s+'([^']*)'", _asm, re.M)
check('H0 BANNER equals forth.asm msg_welcome', bool(_mw) and _mw.group(1) == BANNER,
      f'(read {_mw.group(1)!r})' if _mw else '(no msg_welcome in forth.asm)')

for f in (OVMF_CODE, OVMF_VARS, MEMDISK, IMG, SCRIPT):
    if not os.path.exists(f):
        die(3, f'INSTRUMENT FAIL: missing {f}')
print(f'input sha256 {hashlib.sha256(open(IMG, "rb").read()).hexdigest()}  {IMG}')

# ---- the stick's grub.cfg, from make-uefi-usb.sh (as test_uefi_boot.py) ----
src = open(SCRIPT).read()
m = re.search(r"<< 'GRUBCFG'\n(.*?)\nGRUBCFG\n", src, re.S)
if not m:
    die(1, 'FAIL: no GRUBCFG heredoc in make-uefi-usb.sh (the stick config moved)')
grub_cfg = m.group(1) + '\n'

# ---- the stick's BIOS half, rootless (test_uefi_boot.py's bios_half) ----
BIOS_MODULES = ['biosdisk', 'part_gpt', 'fat', 'normal', 'configfile', 'test',
                'echo', 'linux16', 'reboot', 'search']
KERNEL_SECTOR = 0x5C       # boot.img: LBA of core.img's first sector (u64)
BLOCKLIST = 0x200 - 12     # core.img sector 0 (diskboot): u64 start, u16 len, u16 segment


def bios_half(disk, bios_lba, bios_sectors, work):
    core = os.path.join(work, 'core.img')
    run(['grub-mkimage', '-O', 'i386-pc', '-o', core, '-p', '(hd0,gpt2)/boot/grub'] + BIOS_MODULES)
    c = bytearray(open(core, 'rb').read())
    c += b'\0' * (-len(c) % 512)
    n = len(c) // 512
    if n > bios_sectors:
        die(3, f'INSTRUMENT FAIL: core.img is {n} sectors, the BIOS-boot partition {bios_sectors}')
    struct.pack_into('<QHH', c, BLOCKLIST, bios_lba + 1, n - 1, 0x820)
    boot = open('/usr/lib/grub/i386-pc/boot.img', 'rb').read()
    with open(disk, 'r+b') as f:
        mbr = bytearray(f.read(512))
        mbr[:0x1B8] = boot[:0x1B8]          # keep the protective MBR's table + signature
        struct.pack_into('<Q', mbr, KERNEL_SECTOR, bios_lba)
        f.seek(0)
        f.write(mbr)
        f.seek(bios_lba * 512)
        f.write(c)
    return n


def gpt_disk(path, guid_tail, label, vol_id, populate, work, tag, bios=False, fat=32):
    """A pinned GPT disk with one FAT ESP (FAT32 unless fat=16) (and, for the stick, a BIOS-boot
    partition first).  Returns the ESP's first LBA."""
    with open(path, 'wb') as f:
        f.truncate(DISK_MIB * 1024 * 1024)
    run(['sgdisk', '--zap-all', path])
    esp_n = 1
    if bios:
        run(['sgdisk', '-n', '1:2048:+1M', '-t', '1:ef02', '-c', '1:BIOS Boot', path])
        esp_n = 2
        run(['sgdisk', '-n', '2:0:0', '-t', '2:ef00', '-c', '2:EFI System', path])
    else:
        run(['sgdisk', '-n', '1:2048:0', '-t', '1:ef00', '-c', '1:EFI System', path])
    args = ['sgdisk', '-U', f'F0E7B007-0000-4000-8000-{guid_tail}0']
    for i in range(1, esp_n + 1):
        args += ['-u', f'{i}:F0E7B007-0000-4000-8000-{guid_tail}{i}']
    run(args + [path])
    info = run(['sgdisk', '-i', str(esp_n), path]).stdout
    first = int(re.search(r'First sector: (\d+)', info).group(1))
    last = int(re.search(r'Last sector: (\d+)', info).group(1))
    esp = os.path.join(work, f'{tag}.fat')
    with open(esp, 'wb') as f:
        f.truncate((last - first + 1) * 512)
    env = dict(os.environ, MTOOLS_SKIP_CHECK='1', SOURCE_DATE_EPOCH=str(EPOCH))
    run(['mkfs.fat', '-F', str(fat), '-n', label, '--invariant', '-i', vol_id, esp], env=env)
    populate(esp, env)
    run(['dd', f'if={esp}', f'of={path}', 'bs=512', f'seek={first}', 'conv=notrunc',
         'status=none'])
    return first


LFN_OFFS = (1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30)   # 13 UTF-16 chars


def esp_bpb(d):
    """The GPT's first entry and the boot sector it points at."""
    ent = d[2 * 512:2 * 512 + 128]                       # GPT entry 1 (LBA 2)
    typ = struct.unpack_from('<I', ent, 0)[0]
    start = struct.unpack_from('<Q', ent, 32)[0]
    return typ, start, d[start * 512:start * 512 + 512]


def read_dir(d, off, nbytes):
    """DIR-LIST's view of one directory cluster: the lines it prints, the
    LFN entry count, whether a 0 entry ends it inside the cluster, and the
    names (8.3, or the long name when LFN entries precede the entry)."""
    names, lines, lfn, ended, parts = [], [], 0, False, {}
    for o in range(off, off + nbytes, 32):
        e = d[o:o + 32]
        if e[0] == 0:
            ended = True
            break
        if e[0] == 0xE5:
            parts = {}
            continue
        attr = e[11]
        if attr & 0x3F == 0x0F:
            lfn += 1
            chars = []
            for k in LFN_OFFS:
                c = struct.unpack_from('<H', e, k)[0]
                if c in (0, 0xFFFF):
                    break
                chars.append(chr(c))
            parts[(e[0] & 0x3F) - 1] = ''.join(chars)
            continue
        if attr & 0x08:
            parts = {}
            continue                                     # volume label: DIR-LIST skips it
        if parts:
            name = ''.join(parts[i] for i in sorted(parts))
        else:
            n = e[0:8].decode('ascii').rstrip()
            x = e[8:11].decode('ascii').rstrip()
            name = n + ('.' + x if x else '')
        parts = {}
        clu = (struct.unpack_from('<H', e, 0x14)[0] << 16) | struct.unpack_from('<H', e, 0x1A)[0]
        size = struct.unpack_from('<I', e, 0x1C)[0]
        names.append(name)
        lines.append(f'{name} <DIR> cl={clu}' if attr & 0x10 else f'{name} {size} cl={clu}')
    return names, lines, lfn, ended


def read_fat32(path):
    """H1: everything F3, F4 and F8 expect, read from the image."""
    d = open(path, 'rb').read()
    typ, start, b = esp_bpb(d)
    spc, rsvd, nfats = b[0x0D], struct.unpack_from('<H', b, 0x0E)[0], b[0x10]
    rootent = struct.unpack_from('<H', b, 0x11)[0]
    fatsz16 = struct.unpack_from('<H', b, 0x16)[0]
    fatsz32, root = struct.unpack_from('<II', b, 0x24)[0], struct.unpack_from('<I', b, 0x2C)[0]
    fat_lba = start + rsvd
    data_lba = fat_lba + nfats * fatsz32
    clus = lambda c: (data_lba + (c - 2) * spc) * 512       # noqa: E731
    rnames, rlines, rlfn, rend = read_dir(d, clus(root), spc * 512)
    efi = [ln for ln in rlines if ln.startswith('EFI <DIR> cl=')]
    ecl = int(efi[0].rsplit('=', 1)[1]) if efi else 0
    enames, elines, elfn, eend = read_dir(d, clus(ecl), spc * 512) if ecl else ([], [], 0, False)
    fat77 = struct.unpack_from('<I', d, fat_lba * 512 + SENTINEL * 4)[0] & 0x0FFFFFFF
    init = [f'EFI at LBA {start:08X}', f'FAT at LBA {fat_lba:08X}', f'Data at LBA {data_lba:08X}',
            f'Root clust {root}', f'Sects/clust {spc}', 'FAT32 ready']
    ok = (typ == ESP_TYPE and start == 2048 and fatsz16 == 0 and rootent == 0 and fatsz32 != 0
          and rnames == ['EFI', 'HELLO.TXT'] and rlfn == 0 and rend
          and enames == ['.', '..', LONG_NAME] and elfn >= 1 and eend
          and len(LONG_NAME) < 104 and fat77 == 0)
    detail = (f'(type {typ:08X}, start {start}, FATSz16 {fatsz16}, RootEntCnt {rootent}, '
              f'FATSz32 {fatsz32}, root {root}, spc {spc}, root {rnames} LFN {rlfn} ended {rend}, '
              f'EFI cl {ecl} {enames} LFN {elfn} ended {eend}, FAT[{SENTINEL}] {fat77})')
    return ok, detail, init, rlines, elines


def read_fat16(path):
    """H2: the FAT16 disk is one FAT32-INIT must refuse, and one the old
    test (the cell at 24h non-zero) accepted."""
    d = open(path, 'rb').read()
    typ, start, b = esp_bpb(d)
    rootent = struct.unpack_from('<H', b, 0x11)[0]
    fatsz16 = struct.unpack_from('<H', b, 0x16)[0]
    cell24 = struct.unpack_from('<I', b, 0x24)[0]
    ok = typ == ESP_TYPE and start == 2048 and fatsz16 != 0 and rootent != 0 and cell24 != 0
    detail = (f'(type {typ:08X}, start {start}, FATSz16 {fatsz16}, RootEntCnt {rootent}, '
              f'cell 24h {cell24:08X})')
    return ok, detail, [f'EFI at LBA {start:08X}', 'Not FAT32']


work = tempfile.mkdtemp(prefix='fat32read-')
try:
    # ---- the stick replica (test_uefi_boot.py's build) ----
    mnt = os.path.join(work, 'esp')
    os.makedirs(os.path.join(mnt, 'boot', 'grub'))
    os.makedirs(os.path.join(mnt, 'EFI', 'BOOT'))
    shutil.copy(MEMDISK, os.path.join(mnt, 'memdisk'))
    shutil.copy(IMG, os.path.join(mnt, 'forth.img'))
    run([sys.executable, os.path.join(ROOT, 'tools', 'make_font_blocks.py'), '--license',
         os.path.join(mnt, 'FONT-LICENSE.txt')])
    open(os.path.join(mnt, 'boot', 'grub', 'grub.cfg'), 'w').write(grub_cfg)
    run(['grub-mkstandalone', '--format=x86_64-efi',
         f'--output={mnt}/EFI/BOOT/BOOTX64.EFI',
         '--locales=', '--fonts=', '--themes=',
         f'boot/grub/grub.cfg={mnt}/boot/grub/grub.cfg'])
    for dp, _, fs in os.walk(mnt):
        for f in fs:
            os.utime(os.path.join(dp, f), (EPOCH, EPOCH))

    def stick_files(esp, env):
        for d in ('/boot', '/boot/grub', '/EFI', '/EFI/BOOT'):
            run(['mmd', '-i', esp, '::' + d], env=env)
        for rel in ('memdisk', 'forth.img', 'FONT-LICENSE.txt', 'boot/grub/grub.cfg',
                    'EFI/BOOT/BOOTX64.EFI'):
            run(['mcopy', '-m', '-i', esp, os.path.join(mnt, rel), '::/' + rel], env=env)

    STICK = os.path.join(work, 'stick.img')
    gpt_disk(STICK, '00000000000', 'FORTHBOOT', 'F0E7B007', stick_files, work, 'stick', bios=True)
    nbios = bios_half(STICK, 2048, 2048, work)
    print(f'stick replica: BIOS core {nbios} sectors, '
          f'sha256 {hashlib.sha256(open(STICK, "rb").read()).hexdigest()[:16]}')

    # ---- the two AHCI disks ----
    hello = os.path.join(work, 'HELLO.TXT')
    open(hello, 'wb').write(HELLO)
    longf = os.path.join(work, 'long.txt')
    open(longf, 'wb').write(LONG)
    for f in (hello, longf):
        os.utime(f, (EPOCH, EPOCH))

    def fat_files(esp, env):
        run(['mmd', '-i', esp, '::/EFI'], env=env)
        run(['mcopy', '-m', '-i', esp, hello, '::/HELLO.TXT'], env=env)
        run(['mcopy', '-m', '-i', esp, longf, '::/EFI/' + LONG_NAME], env=env)

    def fat16_files(esp, env):
        run(['mcopy', '-m', '-i', esp, hello, '::/HELLO.TXT'], env=env)

    DISK = os.path.join(work, 'fat32.img')
    gpt_disk(DISK, '0000000FA32', 'FAT32TEST', 'F0E7FA32', fat_files, work, 'disk')
    print(f'FAT32 disk: sha256 {hashlib.sha256(open(DISK, "rb").read()).hexdigest()[:16]}')
    ok, detail, WANT_INIT, WANT_LS, WANT_EFI = read_fat32(DISK)
    check('H1 the FAT32 disk: ESP at LBA 2048, FAT32 BPB, root EFI + HELLO.TXT, '
          'EFI . .. + one LFN name, FAT[77] free', ok, detail)
    print(f'  F3 expects: {WANT_INIT}\n  F4 expects: {WANT_LS}\n  F8 expects: {WANT_EFI}')
    DISK16 = os.path.join(work, 'fat16.img')
    gpt_disk(DISK16, '0000000FA16', 'FAT16TEST', 'F0E7FA16', fat16_files, work, 'disk16', fat=16)
    print(f'FAT16 disk: sha256 {hashlib.sha256(open(DISK16, "rb").read()).hexdigest()[:16]}')
    ok16, detail16, WANT_G3 = read_fat16(DISK16)
    check('H2 the FAT16 disk: ESP at LBA 2048, FATSz16 and RootEntCnt non-zero, cell 24h non-zero',
          ok16, detail16)
    print(f'  G3 expects: {WANT_G3}')
    if not (ok and ok16):
        die(3, 'INSTRUMENT FAIL: a disk is not the one this gate predicts from')

    def boot(fw, disk, tag):
        """Boot the replica with one AHCI disk; return (socket, ok seen, (pidfile, proc))."""
        argv = ['qemu-system-x86_64', '-M', 'q35', '-m', '512']
        if fw == 'ovmf':
            vars_copy = os.path.join(work, 'vars.fd')
            shutil.copy(OVMF_VARS, vars_copy)
            argv += ['-drive', f'if=pflash,format=raw,readonly=on,file={OVMF_CODE}',
                     '-drive', f'if=pflash,format=raw,file={vars_copy}']
        pf = qemu_pid.pidfile(f'fat32-read-{fw}-{tag}')
        atexit.register(qemu_pid.kill_pidfile, pf)
        errf = os.path.join(work, f'qemu-{fw}-{tag}.stderr')
        q = subprocess.Popen(
            argv + ['-drive', f'if=none,id=stick,format=raw,file={STICK}',
                    '-device', 'qemu-xhci', '-device', 'usb-storage,drive=stick,bootindex=0',
                    '-drive', f'if=none,id=fat,format=raw,file={disk}',
                    '-device', 'ide-hd,drive=fat,bus=ide.0',
                    '-display', 'none', '-net', 'none', '-no-reboot', '-pidfile', pf,
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=on'],
            stdout=subprocess.DEVNULL, stderr=open(errf, 'w'))
        qemu_pid.wait_started(q, pf, [PORT], f'fat32-read ({fw}, {tag})', errf)
        s, t0 = None, time.time()
        while s is None and time.time() - t0 < 10:
            try:
                s = socket.create_connection(('127.0.0.1', PORT), timeout=1)
            except OSError:
                time.sleep(0.2)
        if s is None:
            die(3, f'INSTRUMENT FAIL: no serial listener on {PORT} ({fw}, {tag})')
        s.settimeout(1)
        raw, seen, plain = b'', False, ''
        while time.time() - t0 < WAIT and q.poll() is None:
            try:
                d = s.recv(65536)
                if not d:
                    break
                raw += d
            except socket.timeout:
                pass
            except OSError as e:
                print(f'[{fw}] serial closed: {e!r}; QEMU stderr: {open(errf).read().strip()[-200:]!r}')
                break
            plain = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', raw.decode('utf-8', 'replace'))
            if plain.find(BANNER) >= 0 and plain.rstrip().endswith('ok'):
                seen = True
                break
        print(f'[{fw} {tag}] serial: {len(plain)} bytes after {time.time() - t0:.0f} s; '
              f'banner + ok: {seen}')
        return s, seen, (pf, q)

    def send(s, cmd, budget=30):
        rep, how = ser.send_until_prompt(s, cmd, budget=budget)
        body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
        print(f'>>> {cmd}\n    {body.strip()[-300:]!r}  [{how}]', flush=True)
        return body

    def last_num(b):
        v = re.findall(r'(-?[0-9A-F]+) ok', b)
        return v[-1] if v else None

    def lines_before_ok(b):
        ls = [ln.rstrip() for ln in b.replace('\r', '').split('\n')]
        ls = [ln for ln in ls if ln]
        return ls[:-1] if ls and ls[-1] == 'ok' else ls

    def no_q(b):
        return not re.search(r'\S+ \?', b) and not b.strip().endswith('?')

    def sentinel_back(s, tag, chk, what):
        b = send(s, 'DECIMAL DEPTH . .')
        check(f'{tag}-{chk} DECIMAL DEPTH . . prints 1 {SENTINEL}: {what} left the sentinel',
              re.fullmatch(rf'1 {SENTINEL}\s+ok', b.strip()) is not None, f'({b.strip()!r})')

    def load_and_init(s, tag, n1, n2):
        b = send(s, 'S" FAT32" LOAD-VOCAB', 90)
        sk = re.findall(r'([A-Z0-9-]+) present, skipped', b)
        check(f'{tag}-{n1} S" FAT32" LOAD-VOCAB: skip lines AHCI HARDWARE, no ?, ok',
              sk == ['AHCI', 'HARDWARE'] and no_q(b) and b.rstrip().endswith('ok'),
              f'({sk}; {b.strip()[-160:]!r})')
        b = send(s, 'USING AHCI AHCI-INIT')
        check(f'{tag}-{n2} AHCI-INIT: Drive on port 0, AHCI ok',
              'Drive on port 0' in b and 'AHCI ok' in b and no_q(b), f'({b.strip()!r})')

    def finish(s, pf, q):
        s.close()
        qemu_pid.kill_pidfile(pf)
        q.wait(timeout=10)

    for fw, mode, tag in (('ovmf', '3', 'U'), ('seabios', '1', 'L')):
        s, seen, (pf, q) = boot(fw, DISK, 'fat32')
        check(f'{tag}-F0 {fw}: banner + ok', seen)
        if seen:
            b = send(s, 'DECIMAL BOOT-MODE .')
            check(f'{tag}-F0b BOOT-MODE = {mode}', last_num(b) == mode, f'({b.strip()!r})')
            load_and_init(s, tag, 'F1', 'F2')
            b = send(s, 'ONLY FORTH DEFINITIONS USING FAT32 FAT32-INIT')
            got = lines_before_ok(b)
            check(f'{tag}-F3 FAT32-INIT prints the six lines read from the image',
                  got == WANT_INIT, f'(got {got})')
            b = send(s, f'DECIMAL {SENTINEL} FAT32-LS')
            got = lines_before_ok(b)
            check(f'{tag}-F4a FAT32-LS first line: {WANT_LS[0]!r} (one space before <DIR>)',
                  got[:1] == WANT_LS[:1], f'(got {got[:1]})')
            check(f'{tag}-F4 FAT32-LS lists the root as read from the image',
                  got == WANT_LS, f'(got {got})')
            b = send(s, 'BASE @ DECIMAL .')
            check(f'{tag}-F4b BASE after FAT32-LS is 16 (the card types DECIMAL after it)',
                  last_num(b) == '16', f'({b.strip()!r})')
            sentinel_back(s, tag, 'F4c', 'DIR-LIST')
            b = send(s, f'DECIMAL {SENTINEL} S" NOPE.TXT" FAT32-CD')
            got = lines_before_ok(b)
            check(f'{tag}-F6 FAT32-CD of a missing name: exactly Not found',
                  got == ['Not found'], f'(got {got})')
            sentinel_back(s, tag, 'F6b', 'FAT32-FIND')
            b = send(s, f'DECIMAL LFN-RESET 65 LFN-BUF C! 66 LFN-BUF 1+ C! {SENTINEL} .LFN CR')
            got = lines_before_ok(b)
            check(f'{tag}-F7 .LFN prints exactly AB', got == ['AB'], f'(got {got})')
            sentinel_back(s, tag, 'F7b', '.LFN')
            b = send(s, f'DECIMAL {SENTINEL} S" EFI" FAT32-CD FAT32-LS')
            got = lines_before_ok(b)
            check(f'{tag}-F8 FAT32-CD EFI, FAT32-LS: EFI as read from the image, long name in full',
                  got == WANT_EFI, f'(got {got})')
            sentinel_back(s, tag, 'F8b', 'FAT32-CD and DIR-LIST')
            b = send(s, 'ONLY FORTH DEFINITIONS DECIMAL DEPTH .')
            check(f'{tag}-F5 DEPTH 0', last_num(b) == '0', f'({b.strip()!r})')
        finish(s, pf, q)

        s, seen, (pf, q) = boot(fw, DISK16, 'fat16')
        check(f'{tag}-G0 {fw}, FAT16 disk: banner + ok', seen)
        if seen:
            load_and_init(s, tag, 'G1', 'G2')
            b = send(s, 'ONLY FORTH DEFINITIONS USING FAT32 FAT32-INIT')
            got = lines_before_ok(b)
            check(f'{tag}-G3 FAT32-INIT on FAT16: exactly {WANT_G3}', got == WANT_G3, f'(got {got})')
            b = send(s, 'ONLY FORTH DEFINITIONS DECIMAL DEPTH .')
            check(f'{tag}-G4 DEPTH 0', last_num(b) == '0', f'({b.strip()!r})')
        finish(s, pf, q)
finally:
    shutil.rmtree(work, ignore_errors=True)

print(f'Passed: {passed}/{EXPECTED}')
print(f'FAILED: {failures}' if failures else
      'FAT32 read gate passes' if passed == EXPECTED else
      f'NOT ALL RUN: {EXPECTED - passed} of {EXPECTED} checks did not run')
sys.exit(1 if failures or passed != EXPECTED else 0)
