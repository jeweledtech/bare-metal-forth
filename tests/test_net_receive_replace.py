#!/usr/bin/env python3
"""net-receive.py save-and-update mode (private TASK_UNICORN_WRITER).

A sender that sets FLAG_REPLACE (0x0004) on chunk 0 asks the receiver to
overwrite <outdir>/<name>, keeping the previous version as one
<name>.bak.  This is how URWRITER's Ctrl+S reaches the dev machine (Track
A); FILE-STREAM extractions do not set the flag and keep the numbered
`.1` behaviour.

Rules checked here:
  - replace happens only for a session that saw EOF with no gaps: a
    partial, timed-out or interrupted save never touches the good file
    or its .bak (it is written as <name>.partial);
  - exactly one .bak: a third save replaces the second save's backup;
  - a replace name must be a plain file name inside outdir (no path
    separators, not '.', '..' or empty); otherwise nothing is written
    and the log says refused;
  - the log entry carries replaced (bool) and backup (path or None).

Pure host-side: datagrams are built here and fed to handle_datagram(),
the receive loop's per-datagram step.  No sockets, no QEMU.
"""
import json
import os
import sys
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} {detail}')


try:
    nr = SourceFileLoader('net_receive', str(ROOT / 'tools' / 'net-receive.py')).load_module()
except Exception as e:  # noqa: BLE001
    print(f'  FAIL: import net-receive.py: {e!r}')
    sys.exit(1)

FLAG_EOF = nr.FLAG_EOF
FLAG_REPLACE = getattr(nr, 'FLAG_REPLACE', None)
handle = getattr(nr, 'handle_datagram', None)


def frames(sid, name, data, flags0, chunk=1000, eof=True):
    """chunk 0 (name + first piece), chunks 1..n, then a bare EOF frame."""
    out, idx, pos = [], 0, 0
    pieces = [data[i:i + chunk] for i in range(0, len(data), chunk)] or [b'']
    for p in pieces:
        hdr = nr.HEADER_STRUCT.pack(nr.FBLK_MAGIC, sid, 0, idx, len(p),
                                    flags0 if idx == 0 else 0)
        if idx == 0:
            hdr += name.encode()[:255].ljust(nr.FILENAME_SIZE, b'\x00')
        out.append(hdr + p)
        idx += 1
    if eof:
        out.append(nr.HEADER_STRUCT.pack(nr.FBLK_MAGIC, sid, 0, idx, 0, FLAG_EOF))
    return out


def feed(sessions, outdir, fs):
    logs = []
    for f in fs:
        r = handle(sessions, f, outdir, False)
        if r is not None:
            logs.append(r)
    return logs


def listing(d):
    return sorted(p.name for p in Path(d).iterdir())


print('=== net-receive save-and-update (FLAG_REPLACE) ===')
check('R1 FLAG_REPLACE == 0x0004', FLAG_REPLACE == 0x0004, repr(FLAG_REPLACE))
check('R2 handle_datagram exists', callable(handle))
if FLAG_REPLACE is None or not callable(handle):
    print(f'\n{PASS}/{PASS + FAIL + 12} passed (R3-R14 not runnable)')
    sys.exit(1)

hdr = nr.parse_header(nr.HEADER_STRUCT.pack(nr.FBLK_MAGIC, 1, 0, 0, 0, FLAG_REPLACE))
check('R3 parse_header reports replace', hdr is not None and hdr.get('replace') is True, repr(hdr))

NAME = 'Chapter 1.rtf'
V1, V2, V3 = b'{\\rtf1 one}' * 300, b'{\\rtf1 two}' * 200, b'{\\rtf1 three}' * 100

with tempfile.TemporaryDirectory() as td:
    out = Path(td)
    s = {}
    l1 = feed(s, out, frames(0x111, NAME, V1, FLAG_REPLACE))
    check('R4 first save: file written, no .bak',
          (out / NAME).read_bytes() == V1 and listing(out) == [NAME], repr(listing(out)))
    check('R5 first save log: complete, replaced False, backup None',
          len(l1) == 1 and l1[0]['status'] == 'complete'
          and l1[0].get('replaced') is False and l1[0].get('backup') is None, json.dumps(l1))

    l2 = feed(s, out, frames(0x111, NAME, V2, FLAG_REPLACE))
    check('R6 second save overwrites; previous kept as one .bak',
          (out / NAME).read_bytes() == V2 and (out / (NAME + '.bak')).read_bytes() == V1
          and listing(out) == [NAME, NAME + '.bak'], repr(listing(out)))
    check('R7 second save log: replaced True, backup names the .bak',
          len(l2) == 1 and l2[0].get('replaced') is True
          and str(l2[0].get('backup', '')).endswith(NAME + '.bak'), json.dumps(l2))

    feed(s, out, frames(0x111, NAME, V3, FLAG_REPLACE))
    check('R8 third save: single .bak holds the second version',
          (out / NAME).read_bytes() == V3 and (out / (NAME + '.bak')).read_bytes() == V2
          and listing(out) == [NAME, NAME + '.bak'], repr(listing(out)))

    # A save with a missing middle chunk: the good file and .bak stay.
    fs = frames(0x222, NAME, b'X' * 3000, FLAG_REPLACE)
    del fs[1]
    l4 = feed(s, out, fs)
    check('R9 gapped save leaves file and .bak untouched, writes .partial',
          (out / NAME).read_bytes() == V3 and (out / (NAME + '.bak')).read_bytes() == V2
          and (out / (NAME + '.partial')).exists()
          and len(l4) == 1 and l4[0]['status'] == 'incomplete'
          and l4[0].get('replaced') is False, json.dumps(l4) + repr(listing(out)))

    # A save that never sends EOF (sender died): finalized by the timeout
    # path, which must not replace even though no chunk is missing.
    s2 = {}
    feed(s2, out, frames(0x333, NAME, b'Y' * 1500, FLAG_REPLACE, eof=False))
    sess = s2[0x333]
    l5 = nr.finalize_session(sess, out, False)
    check('R10 no-EOF save (timeout/interrupt path) does not replace',
          (out / NAME).read_bytes() == V3 and (out / (NAME + '.bak')).read_bytes() == V2
          and l5.get('replaced') is False, json.dumps(l5))

with tempfile.TemporaryDirectory() as td:
    out = Path(td)
    s = {}
    feed(s, out, frames(0x444, 'plain.sys', b'A' * 10, 0))
    feed(s, out, frames(0x444, 'plain.sys', b'B' * 10, 0))
    check('R11 no flag: numbered behaviour unchanged (FILE-STREAM)',
          listing(out) == ['plain.1.sys', 'plain.sys']
          and (out / 'plain.sys').read_bytes() == b'A' * 10, repr(listing(out)))

with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    out = base / 'recv'
    out.mkdir()
    (base / 'victim.rtf').write_bytes(b'keep')
    bad = ['../victim.rtf', 'sub/x.rtf', '..', '', '/tmp/abs.rtf']
    logs = []
    for i, n in enumerate(bad):
        logs += feed({}, out, frames(0x500 + i, n, b'EVIL', FLAG_REPLACE))
    check('R12 unsafe replace names write nothing anywhere',
          (base / 'victim.rtf').read_bytes() == b'keep' and listing(out) == []
          and not Path('/tmp/abs.rtf.bak').exists(), repr(listing(out)))
    check('R13 unsafe replace names are logged refused',
          len(logs) == len(bad) and all(l['status'] == 'refused' for l in logs),
          json.dumps([l['status'] for l in logs]))

with tempfile.TemporaryDirectory() as td:
    out = Path(td)
    l6 = feed({}, out, frames(0x600, 'Empty.txt', b'', FLAG_REPLACE))
    check('R14 empty replace save with a named chunk 0 writes a 0-byte file',
          listing(out) == ['Empty.txt'] and (out / 'Empty.txt').read_bytes() == b''
          and len(l6) == 1 and l6[0]['status'] == 'complete', json.dumps(l6))

print(f'\n{PASS}/{PASS + FAIL} passed')
sys.exit(0 if FAIL == 0 else 1)
