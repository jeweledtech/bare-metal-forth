#!/usr/bin/env python3
"""Boot-path detection in tools/hp-portread-capture.py counts a TFTP fetch
as PXE evidence only when the RRQ comes from the HP's own address (private
TASK_TFTP_TRANSFER_LOGGING, addendum 1).

The HP's PXE firmware and GRUB fetch from their DHCP lease, which the
forthos-pxe dnsmasq config pins with a dhcp-host line; 10.42.0.100 is
ForthOS's own netcon source, used only after boot. A fetch from any other
client (a dev-box probe from 127.0.0.1, another machine) proves nothing
about the HP.

Host-only: the journal is canned by replacing the module's _run, the conf
files are temp files, and the DHCP log path does not exist, so only the
journal step can decide.
"""
import datetime
import hashlib
import importlib.util
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(ROOT, 'tools', 'hp-portread-capture.py')
MAC = 'ac:e2:d3:39:0f:40'
HP = '10.42.0.50'
NO_DHCP_LOG = os.path.join(tempfile.gettempdir(), 'no-such-dir-capture-test',
                           'forthos-pxe.log')

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name}' + (f' -- {detail}' if detail else ''))


# Hash the inputs before running them (see tests/test_g6_chain.py).
_unreadable = []
for _label, _p in (('harness', os.path.abspath(__file__)),
                   ('hp-portread-capture.py', TOOL)):
    try:
        with open(_p, 'rb') as _f:
            _h = hashlib.sha256(_f.read()).hexdigest()
    except OSError as _e:
        _h = '<UNREADABLE>'
        _unreadable.append(f'{_label}: {_e}')
    print(f'input sha256 {_h}  {_label}')
check('C0 all declared inputs readable', not _unreadable, '; '.join(_unreadable))

cap = None
try:
    _spec = importlib.util.spec_from_file_location('capture', TOOL)
    cap = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(cap)
except Exception as e:  # counted, never a bare traceback
    _err = f'{type(e).__name__}: {e}'
else:
    _err = ''
check('C1 capture tool imports', cap is not None, _err)

START = datetime.datetime(2026, 11, 10, 7, 0, 0)
STOP = datetime.datetime(2026, 11, 10, 7, 30, 0)


def rrq(ip, name='grub/i386-pc/core.0'):
    return f'Nov 10 07:06:11 devbox in.tftpd[4242]: RRQ from {ip} filename {name}'


def detect(journal_lines, hp_ip):
    """Run detect_boot_path over a canned journal. Returns (observed, ev)
    or (None, error text) so a missing API counts as a FAIL."""
    if cap is None:
        return None, 'tool did not import'
    saved = cap._run
    cap._run = lambda cmd: (0, '\n'.join(journal_lines) + '\n')
    try:
        return cap.detect_boot_path(START, STOP, 'grub/i386-pc/core.0', MAC,
                                    NO_DHCP_LOG, hp_ip=hp_ip)
    except Exception as e:
        return None, f'{type(e).__name__}: {e}'
    finally:
        cap._run = saved


USB = 'usb (not independently confirmed)'

print('\nD: journal RRQ lines, by source address')
obs, ev = detect([rrq(HP)], HP)
check('D1 RRQ from the HP -> pxe', obs == 'pxe', f'{obs!r} {ev!r}')

obs, ev = detect([rrq('10.42.0.77')], HP)
check('D2 RRQ only from 10.42.0.77 (another client) -> usb, not confirmed',
      obs == USB, f'{obs!r} {ev!r}')

obs, ev = detect([rrq('127.0.0.1', 'pxelinux.0')], HP)
check('D3 RRQ only from 127.0.0.1 (a dev-box probe) -> not pxe',
      obs is not None and obs != 'pxe', f'{obs!r} {ev!r}')

obs, ev = detect([rrq('10.42.0.77'), rrq(HP, 'grub/grub.cfg')], HP)
# Cited journal lines are the evidence entries indented four spaces;
# headings are not citations (A2 miss: the heading "RRQ from the HP
# (...)" was counted as one).
_cited = [l for l in (ev if isinstance(ev, list) else [])
          if l.startswith('    ') and 'RRQ from' in l]
check('D4 other + HP -> pxe, the evidence cites the HP line only, once',
      obs == 'pxe' and len(_cited) == 1 and f'RRQ from {HP} ' in _cited[0],
      f'{obs!r} {ev!r}')

obs, ev = detect([rrq('10.42.0.77')], HP)
_text = '\n'.join(ev) if isinstance(ev, list) else str(ev)
check('D5 an other-address RRQ is named as not counted',
      isinstance(ev, list) and 'not counted' in _text
      and 'RRQ from 10.42.0.77 ' in _text, f'{ev!r}')

obs, ev = detect([rrq(HP)], None)
check('D6 HP address unknown + an RRQ -> undetermined',
      obs == 'undetermined', f'{obs!r} {ev!r}')

print('\nR: resolving the HP address')


def resolve(flag, conf_text, mac=MAC, unreadable=False):
    if cap is None or not hasattr(cap, 'resolve_hp_ip'):
        return None, 'resolve_hp_ip missing'
    d = tempfile.mkdtemp(prefix='capconf-')
    path = os.path.join(d, 'forthos-pxe-dnsmasq.conf')
    if not unreadable:
        with open(path, 'w') as f:
            f.write(conf_text)
    try:
        return cap.resolve_hp_ip(flag, path, mac)
    except Exception as e:
        return None, f'{type(e).__name__}: {e}'
    finally:
        if os.path.exists(path):
            os.unlink(path)
        os.rmdir(d)


CONF = ('dhcp-range=10.42.0.10,10.42.0.200,12h\n'
        'dhcp-boot=grub/i386-pc/core.0,,10.42.0.1\n'
        'dhcp-host=AC:E2:D3:39:0F:40,forthbox,10.42.0.50\n')

ip, why = resolve('10.42.0.99', CONF)
check('R1 --hp-ip wins over the conf', ip == '10.42.0.99', f'{ip!r} {why!r}')

ip, why = resolve(None, CONF)
check('R2 dhcp-host line for the MAC (upper case in conf) -> 10.42.0.50',
      ip == '10.42.0.50' and 'dhcp-host' in str(why), f'{ip!r} {why!r}')

ip, why = resolve(None, 'dhcp-host=11:22:33:44:55:66,other,10.42.0.60\n')
check('R3 no dhcp-host line for the MAC -> none, saying why',
      ip is None and MAC in str(why), f'{ip!r} {why!r}')

ip, why = resolve(None, '', unreadable=True)
check('R4 conf unreadable -> none, saying why',
      ip is None and 'not readable' in str(why), f'{ip!r} {why!r}')

ip, why = resolve(None, CONF + 'dhcp-host=ac:e2:d3:39:0f:40,again,10.42.0.51\n')
check('R5 two dhcp-host lines for the MAC -> none (ambiguous)',
      ip is None and 'ambiguous' in str(why), f'{ip!r} {why!r}')

print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(1 if FAIL else 0)
