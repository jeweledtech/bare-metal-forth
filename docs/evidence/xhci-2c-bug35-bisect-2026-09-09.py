#!/usr/bin/env python3
"""Bisect the 2c red-run findability breakage.

Replays the phase-5 red sequence against HEAD (5cf99a2), in the
suite's exact order (including the unguarded H8T send and the
DEF? checks), probing DEF? PHYS-RELEASE / DEF? NLIVE / DEPTH
after every step.  Observed signature: FORTH chain broken in the
middle (NLIVE early = lost, PPG late = findable), so post-mortem
reads PHYS-HEAP / PHYS-HEAP-END / HERE @ to test pool-vs-
dictionary overlap.  Full step output printed -- no truncation.
"""
import re
import socket
import subprocess
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4600
PROJECT = '/home/bbrown/projects/forthos'

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
for _ in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print('FAIL: connect')
    sys.exit(1)

time.sleep(2)
try:
    while True:
        s.recv(4096)
except Exception:
    pass


def send(cmd, wait=1.0):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(2)
    resp = b''
    while True:
        try:
            d = s.recv(4096)
            if not d:
                break
            resp += d
        except Exception:
            break
    return resp.decode('ascii', errors='replace')


def body_of(raw):
    return raw.split('\n', 1)[1] if '\n' in raw else raw


def val(expr, wait=1.5):
    raw = send(f'DECIMAL {expr} .', wait)
    body = body_of(raw)
    if '?' in body:
        return None, raw
    nums = re.findall(r'-?\d+', body)
    return (int(nums[-1]) if nums else None), raw


def get_vocab_blocks(name):
    r = subprocess.run([sys.executable, '-c', f"""
import os, importlib.util
spec = importlib.util.spec_from_file_location('wc', os.path.join(
    '{PROJECT}', 'tools', 'write-catalog.py'))
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)
vocabs = wc.scan_vocabs(os.path.join('{PROJECT}', 'forth', 'dict'))
_nc = (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
nb = 1 + _nc
for v in vocabs:
    nb = wc.place_vocab(nb, v['blocks_needed'])
    if v['name'] == '{name}':
        print(f"{{nb}} {{nb + v['blocks_needed'] - 1}}")
        break
    nb += v['blocks_needed']
"""], capture_output=True, text=True, timeout=10)
    p = r.stdout.strip().split()
    return int(p[0]), int(p[1])


NLIVE_DEFINED = [False]


def probe(tag):
    pr, _ = val('DEF? PHYS-RELEASE 0<>')
    nl, _ = val('DEF? NLIVE 0<>')
    dp, _ = val('DEPTH')
    # NLIVE only counts as lost once it has actually been defined
    ok = pr == -1 and (nl == -1 or not NLIVE_DEFINED[0])
    print(f'[{tag:>28}] PHYS-RELEASE={pr} NLIVE={nl} DEPTH={dp}'
          + ('' if ok else '   <<< BROKEN'))
    return ok


def postmortem(tag):
    print(f'\nBREAKAGE AT STEP: {tag}')
    for w in ('PHYS-ALLOC', 'OWN-SLOT', 'FL-WALK', 'MS-DELAY',
              'USBSTS@', 'XHCI-BIND', 'ZAP', 'DEF?', 'PCI-FIND',
              'NLV', 'AVAIL', 'H8T', 'PPG', 'PGRAB'):
        v, _ = val(f'DEF? {w} 0<>')
        print(f'  DEF? {w} -> {v}')
    # Pool vs dictionary overlap (decisive for the memory-
    # overwrite hypothesis).  HERE pushes the ADDRESS of the
    # dict-pointer cell; HERE @ is the pointer itself.
    hp, _ = val('PHYS-HEAP @')
    he, _ = val('PHYS-HEAP-END @')
    dp, _ = val('HERE @')
    fh, _ = val('FL-HEAD @')
    print(f'  PHYS-HEAP={hp}' + (f' = {hp:#x}' if hp is not None
                                 else ''))
    print(f'  PHYS-HEAP-END={he}' + (f' = {he:#x}'
                                     if he is not None else ''))
    print(f'  HERE @ (dict ptr)={dp}'
          + (f' = {dp:#x}' if dp is not None else ''))
    print(f'  FL-HEAD={fh}' + (f' = {fh:#x}' if fh is not None
                               else ''))
    if dp is not None:
        print('  dict ptr inside pool (>=0x100000): '
              f'{dp >= 0x100000}')
    # ORDER may not exist in this kernel; a '?' here means
    # nothing -- the DEF? sweep above carries the weight.
    raw = send('ORDER', 2.0)
    print('  ORDER (unverified word, ? = absent, not evidence):',
          body_of(raw).strip())
    sys.exit(0)


# ---- setup (phases 0/1/4 machinery on the red tree) ----
send('ONLY FORTH DEFINITIONS')
send('ALSO PCI-ENUM')
send('VARIABLE TB  VARIABLE TD  VARIABLE TF')
send(': XCAP FIND-XHCI IF TF ! TD ! TB ! -1 ELSE 0 THEN ;')
print('XCAP:', val('XCAP')[0])
send(': DEF? WORD FIND NIP ;')
send('VARIABLE ZN')
send(': ZAP 64 ZN !  BEGIN DEPTH 0<> ZN @ 0> AND '
     'WHILE DROP -1 ZN +! REPEAT ;')
xs, xe = get_vocab_blocks('XHCI')
send(f'{xs} {xe} THRU', 10)
send('ONLY FORTH DEFINITIONS')
send('ALSO PCI-ENUM')
send('ALSO XHCI')
send('ALSO HARDWARE')
print('BIND:', val('XHCI-BIND')[0])
print('HALT:', val('XHCI-HALT')[0])
print('RESET:', val('XHCI-RESET', 3.0)[0])

# ---- phase 5 in the suite's exact order ----
steps = [
    ('ZAP entry', lambda: send('ZAP')),
    ('instr43 USBSTS@ 1 AND', lambda: val('USBSTS@ 1 AND')),
    ('instr44 DEF? internals',
     lambda: val('DEF? OWN-SLOT 0<> DEF? FL-WALK 0<> AND '
                 'DEF? PHYS-RELEASE 0<> AND')),
    ('VARIABLE NLV', lambda: send('VARIABLE NLV')),
    ('def NLIVE',
     lambda: (NLIVE_DEFINED.__setitem__(0, True),
              send(': NLIVE 0 NLV !  OWN-CAP 0 DO '
                   'I OWN-SLOT @ 0= 0= IF NLV @ 1+ NLV ! THEN '
                   'LOOP NLV @ ;'))[1]),
    ('def AVAIL',
     lambda: send(': AVAIL 0 FL-ADDR !  FL-WALK 0= IF -1 EXIT '
                  'THEN FL-TOT @ PHYS-HEAP-END @ PHYS-HEAP @ '
                  '- + ;')),
    ('instr45 val AVAIL', lambda: val('AVAIL', 2.0)),
    ('snapshot val NLIVE', lambda: val('NLIVE', 2.0)),
    ('DEF? XHCI-UP', lambda: val('DEF? XHCI-UP')),
    ('DEF? XHCI-RUN', lambda: val('DEF? XHCI-RUN')),
    ('DEF? NOP-TEST', lambda: val('DEF? NOP-TEST')),
    ('DEF? XHCI-DOWN', lambda: val('DEF? XHCI-DOWN')),
    ('DEF? .H8', lambda: val('DEF? .H8')),
    ('def H8T', lambda: send(': H8T 255 .H8 ;')),
    ('send H8T', lambda: send('H8T')),
    ('ZAP 2', lambda: send('ZAP')),
    ('val XHCI-UP', lambda: val('XHCI-UP', 3.0)),
    ('val XSPA @', lambda: val('XSPA @')),
    ('val NLIVE (delta)', lambda: val('NLIVE', 2.0)),
    ('val QDCB XDCBAA @ =', lambda: val('QDCB XDCBAA @ =')),
    ('val QERB XERST @ =', lambda: val('QERB XERST @ =')),
    ('val XHCI-RUN', lambda: val('XHCI-RUN', 3.0)),
    ('val USBSTS@ 1 AND', lambda: val('USBSTS@ 1 AND')),
    ('ZAP 3', lambda: send('ZAP')),
    ('val 32 NOP-TEST', lambda: val('32 NOP-TEST', 6.0)),
    ('val XENQ @', lambda: val('XENQ @')),
    ('val XEDQ @', lambda: val('XEDQ @')),
    ('val XHCI-DOWN', lambda: val('XHCI-DOWN', 3.0)),
    ('val USBSTS@ 1 AND (2)', lambda: val('USBSTS@ 1 AND')),
    ('val XHCI-DOWN (2)', lambda: val('XHCI-DOWN')),
    ('ZAP 4', lambda: send('ZAP')),
    ('val XHCI-UP (2)', lambda: val('XHCI-UP', 3.0)),
    ('val XHCI-DOWN (3)', lambda: val('XHCI-DOWN', 3.0)),
    ('VARIABLE PPG', lambda: send('VARIABLE PPG')),
    (': PGRAB ...',
     lambda: send(': PGRAB 4096 PHYS-ALLOC PPG ! ;')),
    ('PGRAB', lambda: send('PGRAB')),
    ('release 1', lambda: send('PPG @ 4096 PHYS-RELEASE')),
    ('release 2', lambda: send('PPG @ 4096 PHYS-RELEASE', 1.5)),
]
if not probe('baseline'):
    postmortem('baseline')
for tag, fn in steps:
    r = fn()
    out = body_of(r).strip() if isinstance(r, str) else \
        f'{r[0]} raw={body_of(r[1]).strip()!r}'
    print(f'step {tag}: {out}')
    if not probe(tag):
        postmortem(tag)
print('\nNO BREAKAGE REPRODUCED on phase-5 replay -- divergence '
      'is in the omitted earlier-phase traffic; fall back to '
      'probing inside the real suite')
