#!/usr/bin/env python3
"""LOAD-VOCAB of a vocabulary already present adds nothing (docs/TASK_VOCAB_DEDUP.md).

  python3 tests/test_vocab_dedup.py <port> [image [blocks]]

Boot setup: an image given = kernel + blocks, booted as floppy with an IDE
copy; else build/combined.img (a full tree); else, in a public clone (where
make combined has no private sources), build/bmforth-free.img + build/blocks.img
(make free blocks write-catalog) concatenated into the same combined layout.
Images are copied into build/vocab-dedup.d first (never booted in place).
Public cases (always): PCI-ENUM again (embedded), FIRSTBOOT (block-loaded
in both the full and the free build; REQUIRES four vocabularies embedded in
both, one per line), FIRSTBOOT again. Private cases (only when forth/dict/ahci.fth and surveyor.fth
are in the tree; else SKIPPED, exit 0): AHCI again, SURVEYOR (REQUIRES AHCI),
SURVEYOR again, INSTALL (REQUIRES SURVEYOR). Each step measures HERE, counts
the "<name> present, skipped" lines (each REQUIRES resolves exactly once per
load), and counts dictionary headers directly: the guest's
dictionary region is dumped through the QEMU monitor (pmemsave) and a header
is counted only when the name is preceded by its length byte (len & 0x3F,
not hidden) and a plausible link cell. FIND is not used for the count.
The checks are the gates after the fix.
"""
import atexit, hashlib, os, re, socket, struct, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid               # noqa: E402
import serial as ser          # noqa: E402

PORT = int(sys.argv[1])
B = os.path.join(ROOT, 'build')
if len(sys.argv) > 2:
    SRC = sys.argv[2]
    IDE_SRC = sys.argv[3] if len(sys.argv) > 3 else SRC
elif os.path.exists(os.path.join(B, 'combined.img')):
    SRC = IDE_SRC = os.path.join(B, 'combined.img')
elif os.path.exists(os.path.join(B, 'bmforth-free.img')) and os.path.exists(os.path.join(B, 'blocks.img')):
    # the combined layout (Makefile: cat $(IMAGE) $(BLOCKS)): block N is LBA 225 + 2N
    os.makedirs(os.path.join(B, 'vocab-dedup.d'), exist_ok=True)
    SRC = IDE_SRC = os.path.join(B, 'vocab-dedup.d', 'combined-free.img')
    with open(SRC, 'wb') as out:
        for part in ('bmforth-free.img', 'blocks.img'):
            out.write(open(os.path.join(B, part), 'rb').read())
else:
    sys.exit('NO IMAGE: build/combined.img (make combined), or in a public clone '
             'build/bmforth-free.img + build/blocks.img (make free blocks write-catalog)')
D = os.path.join(ROOT, 'build', 'vocab-dedup.d')
os.makedirs(D, exist_ok=True)
IMG = os.path.join(D, 'image.img')
IDE = os.path.join(D, 'ide.img')
PF = os.path.join(D, 'qemu.pid')
MON = os.path.join(D, 'monitor.sock')
DUMP = os.path.join(D, 'dict.bin')
PRIVATE = all(os.path.exists(os.path.join(ROOT, 'forth', 'dict', f)) for f in ('ahci.fth', 'surveyor.fth'))
DICT_START, DICT_LIMIT = 0x30000, 0x80000
NAMES = ['AHCI-INIT', 'AHCI', 'PCI-ENUM', 'HARDWARE', 'NTFS', 'FAT32', 'SURVEYOR', 'INSTALL',
         'FIRSTBOOT', 'UI-CORE', 'UI-PARSER', 'UI-EVENTS', 'GUI-HARVEST', 'CATALOG-RESOLVER']
# One word unique to each vocabulary: which vocabularies were actually compiled.
WORDS = ['PCI-ADDR', 'CALIBRATE-DELAY', 'PARTITION-MAP', 'FREE-EXTENT']
KERNEL_CODE = (0x7E00, 0x7E00 + 0x1C000)      # code fields point into the kernel (DOCOL, DOVOC, ...)
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


def mon(cmd):
    s = socket.socket(socket.AF_UNIX)
    s.connect(MON)
    s.settimeout(2)
    try:
        s.recv(4096)
    except socket.timeout:
        pass
    s.sendall(cmd.encode() + b'\n')
    time.sleep(0.5)
    s.close()


def headers():
    """Count dictionary headers per name in DICT_START..DICT_LIMIT."""
    if os.path.exists(DUMP):
        os.remove(DUMP)
    mon(f'pmemsave {DICT_START:#x} {DICT_LIMIT - DICT_START:#x} "{DUMP}"')
    for _ in range(50):
        if os.path.exists(DUMP) and os.path.getsize(DUMP) == DICT_LIMIT - DICT_START:
            break
        time.sleep(0.1)
    mem = open(DUMP, 'rb').read()
    out = {}
    for name in NAMES + WORDS:
        nb, n, i = name.encode(), 0, 0
        while True:
            i = mem.find(nb, i)
            if i < 0:
                break
            if i >= 5:
                b = mem[i - 1]
                link = struct.unpack('<I', mem[i - 5:i - 1])[0]
                cfa = (i + len(nb) + 3) & ~3      # create_ aligns the absolute address after the name
                code = struct.unpack('<I', mem[cfa:cfa + 4])[0] if cfa + 4 <= len(mem) else 0
                # a real header: length byte, plausible link, and a code field into the kernel;
                # the loader's own name copies (LOADING-PUSH, REQUIRES parse) have no code field
                if ((b & 0x3F) == len(nb) and not (b & 0x40) and (link == 0 or 0x7E00 <= link < DICT_LIMIT)
                        and KERNEL_CODE[0] <= code < KERNEL_CODE[1]):
                    n += 1
            i += 1
        out[name] = n
    return out


def send(s, cmd, budget=60.0):
    reply, how = ser.send_until_prompt(s, cmd, budget=budget)
    if how != 'prompt':
        print(f'    (read of {cmd[:40]!r} ended by {how})', flush=True)
    return reply.split('\r\n', 1)[1] if '\r\n' in reply else reply


def here(s):
    n = re.findall(r'-?\d+', send(s, 'DECIMAL HERE @ .'))
    return int(n[-1]) if n else None


def step(s, label, cmd):
    r = send(s, cmd, 300.0) if cmd else ''
    h, c = here(s), headers()
    print(f'  [{label}] HERE {h:#x}  ' + ' '.join(f'{k}={v}' for k, v in c.items())
          + (f'  reply {r.strip()[-40:]!r}' if cmd else ''), flush=True)
    return h, c, r


def skips(reply):
    """{name: count} of '<name> present, skipped' lines in a reply."""
    out = {}
    for m in re.finditer(r'([A-Z0-9-]+) present, skipped', reply):
        out[m.group(1)] = out.get(m.group(1), 0) + 1
    return out


def found(s, vocab, word):
    t = send(s, f"USING {vocab} ' {word} 0<> . PREVIOUS")
    return '?' not in t and re.findall(r'-?\d+', t)[-1:] == ['-1'], t


print('inputs (sha256):')
for p in dict.fromkeys((os.path.join(ROOT, 'forth', 'dict', 'catalog-resolver.fth'), os.path.abspath(__file__), SRC, IDE_SRC)):
    print(f'  {hashlib.sha256(open(p, "rb").read()).hexdigest()}  {p}')
subprocess.run(['cp', SRC, IMG], check=True)
subprocess.run(['cp', IDE_SRC, IDE], check=True)
print(f'private vocabularies in this tree: {"yes" if PRIVATE else "no"}', flush=True)
qemu_pid.kill_pidfile(PF)
r = subprocess.run(['qemu-system-i386', '-drive', f'file={IMG},format=raw,if=floppy',
                    '-drive', f'file={IDE},format=raw,if=ide,index=1',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                    '-monitor', f'unix:{MON},server=on,wait=off',
                    '-display', 'none', '-daemonize', '-pidfile', PF], capture_output=True)
qemu_pid.check_launch(r, PF, PORT, 'vocab-dedup')
s = ser.connect_and_sync(PORT, budget=60)

h0, c0, _ = step(s, 'boot', None)
check('boot: the embedded vocabularies checked here have one header each',
      all(c0[k] == 1 for k in ('PCI-ENUM', 'HARDWARE', 'UI-CORE', 'UI-PARSER', 'UI-EVENTS', 'GUI-HARVEST',
                               'CATALOG-RESOLVER') + (('AHCI', 'AHCI-INIT', 'NTFS', 'FAT32') if PRIVATE else ())),
      f'{c0}')

print('-- public cases')
h1, c1, r1 = step(s, 'S" PCI-ENUM" LOAD-VOCAB', 'S" PCI-ENUM" LOAD-VOCAB')
check('PCI-ENUM (embedded) again: HERE unchanged', h1 == h0, f'+{h1 - h0} bytes')
check('PCI-ENUM again: one skip line, one PCI-ENUM, one PCI-ADDR',
      skips(r1) == {'PCI-ENUM': 1} and (c1['PCI-ENUM'], c1['PCI-ADDR']) == (1, 1), f'{skips(r1)} {c1}')
h2, c2, r2 = step(s, 'S" FIRSTBOOT" LOAD-VOCAB', 'S" FIRSTBOOT" LOAD-VOCAB')
emb = ('UI-CORE', 'UI-EVENTS', 'PCI-ENUM', 'CATALOG-RESOLVER')
check('FIRSTBOOT loads once', c2['FIRSTBOOT'] == 1, f'{c2}')
check('FIRSTBOOT: each REQUIRES resolved exactly once (one skip line each), none recompiled',
      skips(r2) == {k: 1 for k in emb} and all(c2[k] == 1 for k in emb), f'{skips(r2)} {c2}')
h3, c3, r3 = step(s, 'S" FIRSTBOOT" LOAD-VOCAB again', 'S" FIRSTBOOT" LOAD-VOCAB')
check('FIRSTBOOT (previously loaded) again: HERE unchanged, one skip line',
      h3 == h2 and skips(r3) == {'FIRSTBOOT': 1} and c3['FIRSTBOOT'] == 1, f'+{h3 - h2} bytes {skips(r3)}')

PRIV_CHECKS = 8
if not PRIVATE:
    print(f'  SKIPPED: private vocabularies (AHCI, SURVEYOR) are not in this tree: '
          f'{PRIV_CHECKS} private checks not run', flush=True)
    h7 = h3
else:
    print('-- private cases')
    h4, c4, r4 = step(s, 'S" AHCI" LOAD-VOCAB', 'S" AHCI" LOAD-VOCAB')
    check('AHCI (embedded) again: HERE unchanged, one skip line', h4 == h3 and skips(r4) == {'AHCI': 1},
          f'+{h4 - h3} bytes {skips(r4)}')
    check('AHCI again: one AHCI, one AHCI-INIT, one PCI-ENUM', (c4['AHCI'], c4['AHCI-INIT'], c4['PCI-ENUM']) == (1, 1, 1),
          f'{c4}')
    h5, c5, r5 = step(s, 'S" SURVEYOR" LOAD-VOCAB', 'S" SURVEYOR" LOAD-VOCAB')
    check('SURVEYOR loads once; its REQUIRES (AHCI) resolved exactly once', c5['SURVEYOR'] == 1 and skips(r5) == {'AHCI': 1},
          f'{skips(r5)} {c5}')
    check('SURVEYOR: no copy of its dependencies',
          all(c5[k] == 1 for k in ('AHCI-INIT', 'AHCI', 'PCI-ENUM', 'HARDWARE', 'NTFS', 'FAT32')), f'{c5}')
    ok, t = found(s, 'SURVEYOR', 'PARTITION-MAP')
    check('SURVEYOR finds its words (PARTITION-MAP defined)', ok, repr(t[-40:]))
    h6, c6, r6 = step(s, 'S" SURVEYOR" LOAD-VOCAB again', 'S" SURVEYOR" LOAD-VOCAB')
    check('SURVEYOR again: HERE unchanged, one skip line', h6 == h5 and skips(r6) == {'SURVEYOR': 1} and c6['SURVEYOR'] == 1,
          f'+{h6 - h5} bytes {skips(r6)}')
    h7, c7, r7 = step(s, 'S" INSTALL" LOAD-VOCAB', 'S" INSTALL" LOAD-VOCAB')
    check('INSTALL loads once, no DICT FULL; its REQUIRES (SURVEYOR) resolved exactly once',
          'DICT FULL' not in r7 and c7['INSTALL'] == 1 and skips(r7) == {'SURVEYOR': 1} and c7['AHCI-INIT'] == 1,
          f'{skips(r7)} {c7} {r7.strip()[-40:]!r}')
    ok, t = found(s, 'INSTALL', 'FREE-EXTENT')
    check('INSTALL finds its words (FREE-EXTENT defined)', ok, repr(t[-40:]))
n = re.findall(r'-?\d+', send(s, 'DECIMAL DEPTH .'))
check('DEPTH 0', n[-1:] == ['0'], f'{n}')
print(f'  HERE: boot {h0:#x}, after all loads {h7:#x}; headroom below 0x7F800: {0x7F800 - h7}', flush=True)
qemu_pid.kill_pidfile(PF)
print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
