#!/usr/bin/env python3
"""
HP bare-metal port-read evidence capture.

Preflight (HARD GATE): the deployed PXE image must hash-identical to the
current build. On mismatch this script ABORTS — it does not warn-and-proceed.
(A passive hash reminder once failed silently for 37 days; this artifact will
be cited in a federal application, so the gate is mechanical.)

Then: listens on UDP :6666 (ForthOS NET-CONSOLE-ON mirror) and writes every
payload, timestamped, to a log file with a provenance header. The operator
types the test sequence on the HP keyboard; everything echoed lands here.

The --boot-path flag records INTENT only. At stop, the actual path is
detected from evidence on this box (a PXE boot leaves a TFTP fetch of the
boot file in the capture window; USB cannot be positively confirmed from the
listener) and appended; a flag/evidence conflict is flagged loudly. The
header no longer asserts the flag as an observation.

Usage:
    python3 tools/hp-portread-capture.py --boot-path pxe \
        [--image build/combined.img] [--deployed /srv/tftp/forth.img] \
        [--port 6666] [--out docs/EVIDENCE_HP_PORTREAD.log]

Stop with Ctrl+C; the log is flushed per-packet, so a hard stop loses nothing.
"""

import argparse
import datetime
import hashlib
import socket
import subprocess
import sys


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def detect_boot_path(start_dt, stop_dt, bootfile, hp_mac, dhcp_log):
    """Independently observe how the HP booted during the capture window,
    instead of trusting the --boot-path flag (which only records intent).

    The listener runs on the dev box and cannot see USB enumeration on the
    HP, so it can never positively confirm a USB boot. But a PXE boot leaves
    a side effect on THIS box: a TFTP fetch of the boot file. So:
      - a TFTP fetch of <bootfile>/forth.img in the window -> 'pxe' (+ cite)
      - a log was readable but shows no such fetch          -> USB is
        consistent, but say it is not independently confirmed
      - no log readable at all                              -> 'undetermined'
    The flag is NEVER echoed as if it were an observation.
    Returns (observed, evidence_lines).
    """
    since = start_dt.strftime('%Y-%m-%d %H:%M:%S')
    until = stop_dt.strftime('%Y-%m-%d %H:%M:%S')
    base = bootfile.rsplit('/', 1)[-1]
    ev = []

    # 1) tftpd-hpa journal: in.tftpd logs an RRQ line per fetch.
    rc, out = _run(['journalctl', '-u', 'tftpd-hpa', '--no-pager',
                    '--since', since, '--until', until])
    journal_readable = (rc == 0)
    if journal_readable:
        hits = [l for l in out.splitlines()
                if 'RRQ' in l or base in l or 'forth.img' in l]
        if hits:
            ev.append('tftpd-hpa journal, in capture window:')
            ev += ['    ' + h for h in hits[:6]]
            return 'pxe', ev

    # 2) forthos-pxe DHCP log: DHCPACK + bootfile to the HP MAC. Typically
    #    root-only (640); try, and degrade if unreadable.
    dhcp_readable = True
    dhcp_hits = []
    try:
        with open(dhcp_log) as f:
            for line in f:
                low = line.lower()
                if hp_mac.lower() in low and (
                        'dhcpack' in low or base in low or 'bootfile' in low):
                    dhcp_hits.append(line.rstrip())
    except (FileNotFoundError, PermissionError) as e:
        dhcp_readable = False
        ev_dhcp_err = str(e)

    if dhcp_hits:
        ev.append(f'{dhcp_log} (confirm the timestamp is in the window):')
        ev += ['    ' + h for h in dhcp_hits[-6:]]
        return 'pxe', ev

    # No positive PXE evidence. Distinguish "USB-consistent" (a log was
    # readable and clean) from "undetermined" (nothing was readable).
    if journal_readable or dhcp_readable:
        if journal_readable:
            ev.append('tftpd-hpa journal readable; no TFTP fetch of '
                      f'{base}/forth.img in the window.')
        if not dhcp_readable:
            ev.append(f'{dhcp_log}: not readable ({ev_dhcp_err}).')
        ev.append('Consistent with a USB boot, but the listener cannot '
                  'positively confirm USB — rests on the operator F9 note.')
        return 'usb (not independently confirmed)', ev

    ev.append(f'Could not read tftpd-hpa journal or {dhcp_log} '
              f'({ev_dhcp_err}).')
    ev.append('Determine manually, windowed to the capture:')
    ev.append(f'    journalctl -u tftpd-hpa --since "{since}" --until "{until}"')
    ev.append(f'    sudo grep -i "{hp_mac}" {dhcp_log}')
    return 'undetermined', ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', default='build/combined.img',
                    help='freshly built image (truth source)')
    ap.add_argument('--deployed', default=None,
                    help='image the HP will actually boot; defaults to '
                         '/srv/tftp/forth.img for pxe, REQUIRED for usb '
                         '(point at the stick, e.g. /mnt/fb/forth.img)')
    ap.add_argument('--boot-path', required=True, choices=['pxe', 'usb'],
                    help='INTENDED boot path for this run. Recorded as intent '
                         'only; the observed path is detected and appended at '
                         'stop, and a flag/evidence conflict is flagged.')
    ap.add_argument('--port', type=int, default=6666)
    ap.add_argument('--out', default='docs/EVIDENCE_HP_PORTREAD.log')
    ap.add_argument('--skip-hash-gate', action='store_true',
                    help='NOT for evidence runs. Logs SKIPPED-GATE if used.')
    # Boot-path detection inputs (see detect_boot_path).
    ap.add_argument('--bootfile', default='grub/i386-pc/core.0',
                    help='PXE boot file name, for TFTP-fetch detection')
    ap.add_argument('--hp-mac', default='ac:e2:d3:39:0f:40',
                    help='HP NIC MAC, for DHCP-log detection')
    ap.add_argument('--dhcp-log', default='/var/log/forthos-pxe.log',
                    help='forthos-pxe DHCP log, for boot-path detection')
    args = ap.parse_args()

    # --deployed has no correct default for a USB boot: the PXE tree is
    # never what a USB run boots, so a stale-hash abort was guaranteed.
    if args.deployed is None:
        if args.boot_path == 'pxe':
            args.deployed = '/srv/tftp/forth.img'
        else:
            ap.error('--deployed is required for --boot-path usb: point '
                     'it at the STICK (e.g. /mnt/fb/forth.img); the PXE '
                     'tree is never what a USB boot loads')
    deploy_hint = ('make pxe-push' if args.boot_path == 'pxe'
                   else 'refresh the FORTHBOOT stick (desk card Section 0)')

    # ---- Provenance ----
    head = subprocess.run(['git', 'rev-parse', 'HEAD'],
                          capture_output=True, text=True).stdout.strip()
    build_hash = sha256(args.image)

    # ---- HARD GATE: deployed medium must match the build ----
    if args.skip_hash_gate:
        gate = 'SKIPPED-GATE (run is NOT evidence-grade)'
        deployed_hash = '(not checked)'
    else:
        try:
            deployed_hash = sha256(args.deployed)
        except (FileNotFoundError, PermissionError) as e:
            print(f'ABORT: cannot read deployed image {args.deployed}: {e}')
            print(f'Deploy first: {deploy_hint}   (then re-run this script)')
            return 2
        if deployed_hash != build_hash:
            print('ABORT: HASH MISMATCH — the HP would boot a stale image.')
            print(f'  build    {args.image}: {build_hash}')
            print(f'  deployed {args.deployed}: {deployed_hash}')
            print(f'Fix: make && {deploy_hint}, then re-run. Do NOT proceed.')
            return 1
        gate = 'PASS (deployed == build)'

    start_dt = datetime.datetime.now().astimezone()
    ts = start_dt.isoformat()
    header = (
        f'=== HP bare-metal port-read capture ===\n'
        f'started:        {ts}\n'
        f'git HEAD:       {head}\n'
        f'image:          {args.image}\n'
        f'image sha256:   {build_hash}\n'
        f'deployed:       {args.deployed}\n'
        f'deployed sha256:{deployed_hash}\n'
        f'hash gate:      {gate}\n'
        f'boot path (intended): {args.boot_path}  '
        f'(flag only; observed path appended at stop)\n'
        f'listener:       udp/:{args.port}\n'
        f'=======================================\n'
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', args.port))

    with open(args.out, 'a') as log:
        log.write(header)
        log.flush()
        print(header, end='')
        print('Listening. On the HP, run the sequence from TASK_HP_PORTREAD.md.')
        print('Ctrl+C to stop.\n')
        try:
            while True:
                data, addr = sock.recvfrom(2048)
                stamp = datetime.datetime.now().astimezone().isoformat(
                    timespec='milliseconds')
                text = data.decode('ascii', errors='backslashreplace')
                line = f'[{stamp} {addr[0]}] {text}'
                log.write(line if line.endswith('\n') else line + '\n')
                log.flush()
                print(line, end='' if line.endswith('\n') else '\n')
        except KeyboardInterrupt:
            stop_dt = datetime.datetime.now().astimezone()
            log.write(f'=== capture stopped {stop_dt.isoformat()} ===\n')
            # Record the OBSERVED boot path from evidence in the window,
            # never the --boot-path flag. A flag/evidence conflict is loud.
            observed, ev = detect_boot_path(
                start_dt, stop_dt, args.bootfile, args.hp_mac, args.dhcp_log)
            foot = [f'boot path (intended, --boot-path flag): {args.boot_path}',
                    f'boot path (observed from this box):      {observed}']
            foot += ['    ' + e for e in ev]
            # Only a POSITIVE pxe detection (a TFTP fetch in the window)
            # proves the flag wrong. An unconfirmed usb or undetermined
            # result is a caution, not a contradiction.
            positive_pxe = observed == 'pxe'
            if positive_pxe and args.boot_path == 'usb':
                foot.append('*** DISCREPANCY: flag says usb, but a TFTP fetch '
                            'was observed — the HP booted PXE, flag is wrong ***')
            elif args.boot_path == 'pxe' and observed.startswith('usb'):
                foot.append('*** CAUTION: --boot-path pxe, but no TFTP fetch '
                            'was found — a USB boot or an unlogged fetch; '
                            'resolve before citing this as a PXE run ***')
            block = '\n'.join(foot) + '\n'
            log.write(block)
            log.flush()
            print('\n' + block, end='')
            print(f'Log written to {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
