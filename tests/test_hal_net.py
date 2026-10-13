#!/usr/bin/env python3
"""HAL: the NET-SEND contract (docs/TASK_HAL_NET_SEND.md), on the combined
image booted by BIOS (floppy + IDE blocks), two boots.

  python3 tests/test_hal_net.py <serial-port> <dgram-local> <dgram-remote> [image]

  Boot A, ne2k_pci (mac 52:54:00:12:34:56) on a dgram netdev, QEMU's
  filter-dump writing every frame to a pcap:
  A0  NE2000 block-loads; HAL-LIST before init: NET-SEND -> unbound.
  A1  NE2K-INIT prints `NET-SEND -> NE2K-NET-SEND`; HAL-LIST shows its XT.
  A2  a 64-byte frame (broadcast, the card's MAC, type 88B5, bytes 0E-3F)
      through NET-SEND: ior 0; the pcap holds exactly those 64 bytes.
  A3  its first 20 bytes as a frame: ior 0; on the wire 60 bytes, the 20
      then zeros.
  A4  lengths 13 and 1515: ior 1; no frame added (the pcap's 88B5 frames
      are exactly A2's and A3's, in order).
  A5  RTL8168-INIT (no RTL8168 here): `RTL8168 not found`; NET-SEND still
      NE2K-NET-SEND's.
  A6  DEPTH 0.
  Boot B, no NIC:
  N1  HAL-LIST: NET-SEND -> unbound.
  N2  RTL8168-INIT and NE2K-INIT find nothing, bind nothing; calling
      NET-SEND prints `NET-SEND: HAL vector not bound`.
  N4  NET-DICT loaded above HAL in the search order: NET-SEND is still the
      HAL vector (its code field is DOVEC's), and NET-DICT's block sender is
      NET-SEND-BLOCKS (two NET-SENDs with different stack effects, picked by
      search order, could corrupt the stack).
  N3  DEPTH 0.
"""
import atexit, hashlib, os, re, shutil, struct, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tests'))
import qemu_pid          # noqa: E402
import serial as ser     # noqa: E402

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4412
DLOC = int(sys.argv[2]) if len(sys.argv) > 2 else 4413
DREM = int(sys.argv[3]) if len(sys.argv) > 3 else 4414
B = os.path.join(ROOT, 'build')
D = os.path.join(B, 'test-hal-net.d')
os.makedirs(D, exist_ok=True)
COMBINED = sys.argv[4] if len(sys.argv) > 4 else os.path.join(B, 'combined.img')
PCAP = os.path.join(D, 'net.pcap')
MAC = bytes.fromhex('525400123456')
failures, checks = [], 0


def check(label, cond, detail=''):
    global checks
    checks += 1
    print(f'[{"PASS" if cond else "FAIL"}] {label} {detail}', flush=True)
    if not cond:
        failures.append(label)


for p in (COMBINED, os.path.join(ROOT, 'forth', 'dict', 'hal.fth'),
          os.path.join(ROOT, 'forth', 'dict', 'ne2000.fth'),
          os.path.join(ROOT, 'forth', 'dict', 'rtl8168.fth'), os.path.abspath(__file__)):
    h = hashlib.sha256(open(p, 'rb').read()).hexdigest() if os.path.exists(p) else 'ABSENT'
    print(f'input sha256 {h}  {p}', flush=True)


def send(s, cmd, budget=30):
    rep, how = ser.send_until_prompt(s, cmd, budget=budget)
    body = rep.split('\r\n', 1)[1] if '\r\n' in rep else ''
    print(f'>>> {cmd}\n    {body.strip()[-240:]!r}  [{how}]', flush=True)
    return body


def nums(b):
    return re.findall(r'(-?[0-9A-F]+) ok', b)


def hal_rows(b):
    return {m.group(1): m.group(2) for m in re.finditer(r'^(\S+) -> (.+?)\s*$', b, re.M)}


def pcap_frames(path):
    data = open(path, 'rb').read() if os.path.exists(path) else b''
    out, i = [], 24
    while i + 16 <= len(data):
        incl = struct.unpack('<I', data[i + 8:i + 12])[0]
        out.append(data[i + 16:i + 16 + incl])
        i += 16 + incl
    return out


def boot(tag, nic):
    F, I = os.path.join(D, 'floppy.img'), os.path.join(D, 'ide.img')
    shutil.copyfile(COMBINED, F)
    shutil.copyfile(COMBINED, I)          # the blocks: the kernel reads the IDE slave
    pf = qemu_pid.pidfile(f'hal-net-{tag}')
    atexit.register(qemu_pid.kill_pidfile, pf)
    p = subprocess.Popen(['qemu-system-i386', '-drive', f'file={F},format=raw,if=floppy',
                          '-drive', f'file={I},format=raw,if=ide,index=1'] + nic +
                         ['-serial', f'tcp:127.0.0.1:{PORT},server=on,wait=off',
                          '-display', 'none', '-pidfile', pf],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    qemu_pid.wait_started(p, pf, PORT, f'hal-net ({tag})')
    return ser.connect_and_sync(PORT, budget=60), pf, p


def stop(s, pf, p):
    s.close()
    qemu_pid.kill_pidfile(pf)
    p.wait(timeout=10)


FRAME = b'\xff' * 6 + MAC + b'\x88\xb5' + bytes(range(0x0E, 0x40))   # 64 bytes

# ---- Boot A: a machine with a NIC QEMU models (ne2k_pci)
if os.path.exists(PCAP):
    os.remove(PCAP)
s, pf, p = boot('nic', ['-netdev', f'dgram,id=u1,local.type=inet,local.host=127.0.0.1,local.port={DLOC},'
                        f'remote.type=inet,remote.host=127.0.0.1,remote.port={DREM}',
                        '-device', 'ne2k_pci,netdev=u1,mac=52:54:00:12:34:56',
                        '-object', f'filter-dump,id=f1,netdev=u1,file={PCAP}'])
iors = {}
try:
    b0 = send(s, 'S" NE2000" LOAD-VOCAB', 90)
    hb = send(s, 'ONLY FORTH DEFINITIONS ALSO HAL HAL-LIST')
    check('A0 NE2000 block-loads; NET-SEND -> unbound before init',
          not re.search(r'\S+ \?', b0) and hal_rows(hb).get('NET-SEND') == 'unbound',
          f'({b0.strip()[-120:]!r}; {hal_rows(hb)})')
    bi = send(s, 'ALSO NE2000 NE2K-INIT', 30)
    ha = send(s, 'HAL-LIST')
    xt = re.findall(r'([0-9A-F]+) ', send(s, "HEX ' NE2K-NET-SEND U. CR DECIMAL"))
    check('A1 NE2K-INIT binds NET-SEND to NE2K-NET-SEND (said; HAL-LIST shows its XT)',
          'NET-SEND -> NE2K-NET-SEND' in bi and bool(xt) and hal_rows(ha).get('NET-SEND') == xt[0],
          f'({bi.strip()[-160:]!r}; {hal_rows(ha)}; xt {xt})')
    send(s, 'HEX CREATE HF 600 ALLOT  HF 6 FF FILL  NE-MAC HF 6 + 6 CMOVE  88 HF C + C!  B5 HF D + C!')
    send(s, ': HF-FILL 40 E DO I HF I + C! LOOP ;  HF-FILL DECIMAL')
    for tag, n in (('A2', 64), ('A3', 20), ('A4a', 13), ('A4b', 1515)):
        r = send(s, f'DECIMAL HF {n} NET-SEND .')
        iors[tag] = nums(r)[-1:]
    br = send(s, 'ALSO RTL8168 RTL8168-INIT PREVIOUS', 30)
    hr = send(s, 'HAL-LIST')
    check('A5 RTL8168-INIT finds no RTL8168 and leaves NET-SEND on NE2K-NET-SEND',
          'RTL8168 not found' in br and bool(xt) and hal_rows(hr).get('NET-SEND') == xt[0],
          f'({br.strip()[-120:]!r}; {hal_rows(hr)})')
    b = send(s, 'ONLY FORTH DEFINITIONS DECIMAL DEPTH .')
    check('A6 DEPTH 0', nums(b)[-1:] == ['0'], f'({b.strip()!r})')
finally:
    stop(s, pf, p)

fr = [f for f in pcap_frames(PCAP) if f[12:14] == b'\x88\xb5']
print(f'pcap: {len(pcap_frames(PCAP))} frame(s), {len(fr)} of type 88B5: {[len(f) for f in fr]}', flush=True)
check('A2 a 64-byte frame through NET-SEND: ior 0, the pcap holds exactly it',
      iors.get('A2') == ['0'] and len(fr) >= 1 and fr[0] == FRAME,
      f'(ior {iors.get("A2")}; first {fr[0].hex() if fr else None})')
check('A3 a 20-byte frame: ior 0, on the wire 60 bytes, the 20 then zeros',
      iors.get('A3') == ['0'] and len(fr) >= 2 and fr[1] == FRAME[:20] + bytes(40),
      f'(ior {iors.get("A3")}; second {fr[1].hex() if len(fr) > 1 else None})')
check('A4 lengths 13 and 1515 refused (ior 1), no frame added',
      iors.get('A4a') == ['1'] and iors.get('A4b') == ['1'] and len(fr) == 2,
      f'(iors {iors.get("A4a")} {iors.get("A4b")}; 88B5 frames {len(fr)})')

# ---- Boot B: no NIC
s, pf, p = boot('none', ['-nic', 'none'])
try:
    h1 = send(s, 'ONLY FORTH DEFINITIONS ALSO HAL HAL-LIST')
    check('N1 no NIC: NET-SEND -> unbound', hal_rows(h1).get('NET-SEND') == 'unbound', f'({hal_rows(h1)})')
    send(s, 'S" NE2000" LOAD-VOCAB', 90)
    bn = send(s, 'ONLY FORTH DEFINITIONS ALSO HAL ALSO NE2000 NE2K-INIT', 30)
    br = send(s, 'ALSO RTL8168 RTL8168-INIT PREVIOUS', 30)
    h2 = send(s, 'HAL-LIST')
    bc = send(s, 'HEX 0 0 NET-SEND . DECIMAL')
    check('N2 the inits find nothing and bind nothing; a NET-SEND call says so by name',
          'NE2000 not found' in bn and 'RTL8168 not found' in br and hal_rows(h2).get('NET-SEND') == 'unbound'
          and 'NET-SEND: HAL vector not bound' in bc,
          f'({bn.strip()[-80:]!r}; {br.strip()[-80:]!r}; {hal_rows(h2)}; {bc.strip()!r})')
    bl = send(s, 'S" NET-DICT" LOAD-VOCAB', 90)
    b4 = send(s, "ONLY FORTH DEFINITIONS ALSO HAL ALSO NET-DICT "
                 "' NET-SEND @ ' FB-BASE @ = . ' NET-SEND-BLOCKS 0<> .")
    check('N4 above HAL, NET-DICT does not shadow NET-SEND; its block sender is NET-SEND-BLOCKS',
          'NET-DICT loaded' in bl and re.search(r'-1 -1 ok', b4) is not None,
          f'({bl.strip()[-80:]!r}; {b4.strip()!r})')
    b = send(s, 'ONLY FORTH DEFINITIONS DECIMAL DEPTH .')
    check('N3 DEPTH 0', nums(b)[-1:] == ['0'], f'({b.strip()!r})')
finally:
    stop(s, pf, p)

print(f'Passed: {checks - len(failures)}/{checks}', flush=True)
sys.exit(0 if not failures else 1)
