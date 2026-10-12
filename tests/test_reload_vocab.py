#!/usr/bin/env python3
"""RELOAD-VOCAB recompiles an edited vocabulary in place (docs/TASK_RELOAD_VOCAB.md).

  python3 tests/test_reload_vocab.py <port>

Fixture: a one-block vocabulary RV-FIX (`1 CONSTANT RV`), added to a copy of
forth/dict and packed by tools/write-catalog.py into a copy of build/blocks.img,
behind build/bmforth.img (or build/bmforth-free.img in a public clone); all
under build/reload-vocab.d, never forth/dict or build/combined.img.
Steps: load RV-FIX; the host patches its block to `2 CONSTANT RV` in the IDE
image; the guest runs EMPTY-BUFFERS and checks it reads the edit (control);
LOAD-VOCAB again (skipped: already present); RELOAD-VOCAB; then a dependent
word compiled after RV-FIX, and RELOAD-VOCAB must refuse. Headers are counted
directly (QEMU monitor pmemsave), as in tests/test_vocab_dedup.py.
"""
import atexit, glob, hashlib, os, re, shutil, socket, struct, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid               # noqa: E402
import serial as ser          # noqa: E402

PORT = int(sys.argv[1])
B = os.path.join(ROOT, 'build')
D = os.path.join(B, 'reload-vocab.d')
IMG, IDE = os.path.join(D, 'image.img'), os.path.join(D, 'ide.img')
PF, MON, DUMP = os.path.join(D, 'qemu.pid'), os.path.join(D, 'monitor.sock'), os.path.join(D, 'dict.bin')
DICT_START, DICT_LIMIT = 0x30000, 0x80000
KERNEL_CODE = (0x7E00, 0x7E00 + 0x1C000)
BLOCKS_LBA_BASE = 225                  # combined layout: block N at LBA 225 + 2N
NAMES = ['RV-FIX', 'RV', 'RELOAD-VOCAB', 'RV-VEC', 'RV-W']
FIXTURE = r"""\ CATALOG: RV-FIX
\ RELOAD-VOCAB test fixture (build/reload-vocab.d only)
VOCABULARY RV-FIX
RV-FIX DEFINITIONS
1 CONSTANT RV
FORTH DEFINITIONS
"""
FIXTURE_VEC = r"""\ CATALOG: RV-VEC
\ RELOAD-VOCAB fixture: installs its own block writer
VOCABULARY RV-VEC
RV-VEC DEFINITIONS
BLK-WRITER@ CONSTANT RV-OLDW
: RV-W ( buf blk -- ior ) 2DROP 1 ;
' RV-W BLK-WRITER!
FORTH DEFINITIONS
"""
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
    if os.path.exists(DUMP):
        os.remove(DUMP)
    mon(f'pmemsave {DICT_START:#x} {DICT_LIMIT - DICT_START:#x} "{DUMP}"')
    for _ in range(50):
        if os.path.exists(DUMP) and os.path.getsize(DUMP) == DICT_LIMIT - DICT_START:
            break
        time.sleep(0.1)
    mem = open(DUMP, 'rb').read()
    out = {}
    for name in NAMES:
        nb, n, i = name.encode(), 0, 0
        while True:
            i = mem.find(nb, i)
            if i < 0:
                break
            if i >= 5:
                b = mem[i - 1]
                link = struct.unpack('<I', mem[i - 5:i - 1])[0]
                cfa = (i + len(nb) + 3) & ~3
                code = struct.unpack('<I', mem[cfa:cfa + 4])[0] if cfa + 4 <= len(mem) else 0
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


def num(s, cmd):
    n = re.findall(r'-?\d+', send(s, 'DECIMAL ' + cmd))
    return int(n[-1]) if n else None


def rv(s):
    t = send(s, 'DECIMAL RV .')
    n = re.findall(r'-?\d+', t)
    return (int(n[-1]) if n and '?' not in t else None), t


# ---- fixture image
kernel = os.path.join(B, 'bmforth.img') if os.path.exists(os.path.join(ROOT, 'forth', 'dict', 'ahci.fth')) \
    else os.path.join(B, 'bmforth-free.img')
for need in (kernel, os.path.join(B, 'blocks.img'), os.path.join(B, 'vbr.bin')):
    if not os.path.exists(need):
        sys.exit(f'NO INPUT: {need} (make combined, or make free blocks write-catalog)')
if os.path.isdir(D):
    shutil.rmtree(D)
os.makedirs(os.path.join(D, 'dict'))
for f in glob.glob(os.path.join(ROOT, 'forth', 'dict', '*.fth')):
    shutil.copy(f, os.path.join(D, 'dict'))
open(os.path.join(D, 'dict', 'rv-fix.fth'), 'w').write(FIXTURE)
open(os.path.join(D, 'dict', 'rv-vec.fth'), 'w').write(FIXTURE_VEC)
blocks = os.path.join(D, 'blocks.img')
shutil.copy(os.path.join(B, 'blocks.img'), blocks)
r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'write-catalog.py'), blocks,
                    os.path.join(D, 'dict') + '/', '--raw', f'VBR-TEMPLATE={os.path.join(B, "vbr.bin")}'],
                   capture_output=True, text=True)
if r.returncode != 0:
    sys.exit('FIXTURE: write-catalog failed:\n' + '\n'.join(
        l for l in (r.stdout + r.stderr).splitlines() if 'Lint OK' not in l)[-600:])
with open(IMG, 'wb') as out:
    out.write(open(kernel, 'rb').read() + open(blocks, 'rb').read())
shutil.copy(IMG, IDE)
data = open(IDE, 'rb').read()
hits = [m.start() for m in re.finditer(rb'1 CONSTANT RV\b', data)]
if len(hits) != 1:
    sys.exit(f'FIXTURE WRONG: "1 CONSTANT RV" found {len(hits)} times in the image')
OFF = hits[0]
BLK = (OFF // 512 - BLOCKS_LBA_BASE) // 2
BOFF = OFF - (BLOCKS_LBA_BASE + 2 * BLK) * 512
print('inputs (sha256):')
for p in (os.path.join(ROOT, 'forth', 'dict', 'catalog-resolver.fth'), os.path.abspath(__file__), kernel, IMG):
    print(f'  {hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]}  {p}')
print(f'fixture: RV-FIX at block {BLK}, the "1" at byte {BOFF} of it', flush=True)

qemu_pid.kill_pidfile(PF)
r = subprocess.run(['qemu-system-i386', '-drive', f'file={IMG},format=raw,if=floppy',
                    '-drive', f'file={IDE},format=raw,if=ide,index=1',
                    '-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                    '-monitor', f'unix:{MON},server=on,wait=off',
                    '-display', 'none', '-daemonize', '-pidfile', PF], capture_output=True)
qemu_pid.check_launch(r, PF, PORT, 'reload-vocab')
s = ser.connect_and_sync(PORT, budget=60)

# ---- 1. first load
send(s, 'S" RV-FIX" LOAD-VOCAB', 120)
send(s, 'USING RV-FIX')
h1, c1 = num(s, 'HERE @ .'), headers()
v1, t1 = rv(s)
check('first load: RV . = 1, one RV-FIX header, one RV header', (v1, c1['RV-FIX'], c1['RV']) == (1, 1, 1),
      f'{v1} {c1} {t1.strip()[-40:]!r}')

# ---- 2. the edit, from the host; the guest must see it
with open(IDE, 'r+b') as f:
    f.seek(OFF)
    f.write(b'2')
    f.flush()
    os.fsync(f.fileno())
send(s, 'EMPTY-BUFFERS')
b = num(s, f'{BLK} BLOCK {BOFF} + C@ .')
check('control: after EMPTY-BUFFERS the guest reads the edited block ("2")', b == ord('2'), f'{b}')

# ---- 3. LOAD-VOCAB again: skipped (D2), code unchanged
t3 = send(s, 'S" RV-FIX" LOAD-VOCAB', 120)
h3, v3 = num(s, 'HERE @ .'), rv(s)[0]
check('LOAD-VOCAB after the edit: "RV-FIX present, skipped", HERE unchanged',
      'RV-FIX present, skipped' in t3 and h3 == h1, f'{t3.strip()[-50:]!r} HERE +{(h3 or 0) - (h1 or 0)} RV={v3}')

# ---- 4. RELOAD-VOCAB
# counted in the dictionary, not asked for: ' of an undefined word pushes
# nothing, so any test word after it would read below the stack
c4 = headers()
check('RELOAD-VOCAB is defined (one header)', c4['RELOAD-VOCAB'] == 1, f"{c4['RELOAD-VOCAB']}")
t5 = send(s, 'S" RV-FIX" RELOAD-VOCAB', 120)
h5, c5 = num(s, 'HERE @ .'), headers()
v5, _ = rv(s)
check('RELOAD-VOCAB: RV . = 2, one RV-FIX header, one RV header, HERE as after the first load',
      (v5, c5['RV-FIX'], c5['RV'], h5) == (2, 1, 1, h1),
      f'RV={v5} {c5} HERE {h5} vs {h1} {t5.strip()[-50:]!r}')
n = num(s, 'DEPTH .')
check('DEPTH 0 after the reload', n == 0, f'{n}')

# ---- 5. a dependent compiled after RV-FIX: refuse, name it, change nothing
send(s, ': AFTER-RV RV ;')
h6 = num(s, 'HERE @ .')
t6 = send(s, 'S" RV-FIX" RELOAD-VOCAB', 120)
n = num(s, 'DEPTH .')
h7 = num(s, 'HERE @ .')
a7 = num(s, 'AFTER-RV .')
check('RELOAD-VOCAB with AFTER-RV compiled after RV-FIX: refused naming AFTER-RV, HERE unchanged, AFTER-RV intact',
      'refus' in t6.lower() and 'AFTER-RV' in t6 and h7 == h6 and a7 == v5,
      f'{t6.strip()[-70:]!r} HERE +{(h7 or 0) - (h6 or 0)} AFTER-RV={a7}')
print(f'    guest: {t6.strip().splitlines()[0] if t6.strip() else t6!r}', flush=True)
check('DEPTH 0 after that refusal', n == 0, f'{n}')

# ---- 6. a vocabulary that installs a vector pointing at its own word
send(s, 'S" RV-VEC" LOAD-VOCAB', 120)
send(s, 'USING RV-VEC')
h8, c8 = num(s, 'HERE @ .'), headers()
w8 = num(s, "BLK-WRITER@ ' RV-W = .")
check('RV-VEC loads; the block-writer vector is its RV-W (control)', c8['RV-W'] == 1 and w8 == -1, f'{c8} {w8}')
t9 = send(s, 'S" RV-VEC" RELOAD-VOCAB', 120)
n = num(s, 'DEPTH .')
h9, c9 = num(s, 'HERE @ .'), headers()
w9 = num(s, "BLK-WRITER@ ' RV-W = .")
# The block writer is the binding layer's BLK-WRITE since HAL slice 2
# (docs/TASK_HAL_BLOCK.md): RL-HAL names the vector, not BLK-WRITER@.
check('RV-VEC reload: refused naming the block-writer vector, HERE unchanged, RV-VEC intact',
      'refus' in t9.lower() and 'BLK-WRITE points into it' in t9 and h9 == h8 and c9['RV-W'] == 1 and c9['RV-VEC'] == 1
      and w9 == -1, f'{t9.strip()[-70:]!r} HERE +{(h9 or 0) - (h8 or 0)} {c9} vec={w9}')
print(f'    guest: {t9.strip().splitlines()[0] if t9.strip() else t9!r}', flush=True)
check('DEPTH 0 after that refusal', n == 0, f'{n}')
send(s, 'RV-OLDW BLK-WRITER!')
t10 = send(s, 'S" RV-VEC" RELOAD-VOCAB', 120)
h10, c10 = num(s, 'HERE @ .'), headers()
check('writer restored: RV-VEC reload goes through (no refusal), HERE as before, one RV-VEC, one RV-W',
      'refus' not in t10.lower() and '?' not in t10 and h10 == h8 and (c10['RV-VEC'], c10['RV-W']) == (1, 1),
      f'{t10.strip()[-70:]!r} HERE {h10} vs {h8} {c10}')
send(s, 'RV-OLDW BLK-WRITER!')

n = num(s, 'DEPTH .')
check('DEPTH 0', n == 0, f'{n}')
qemu_pid.kill_pidfile(PF)
print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
