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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--image', default='build/combined.img',
                    help='freshly built image (truth source)')
    ap.add_argument('--deployed', default=None,
                    help='image the HP will actually boot; defaults to '
                         '/srv/tftp/forth.img for pxe, REQUIRED for usb '
                         '(point at the stick, e.g. /mnt/fb/forth.img)')
    ap.add_argument('--boot-path', required=True, choices=['pxe', 'usb'],
                    help='how the HP is booted for this run (recorded in log)')
    ap.add_argument('--port', type=int, default=6666)
    ap.add_argument('--out', default='docs/EVIDENCE_HP_PORTREAD.log')
    ap.add_argument('--skip-hash-gate', action='store_true',
                    help='NOT for evidence runs. Logs SKIPPED-GATE if used.')
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

    ts = datetime.datetime.now().astimezone().isoformat()
    header = (
        f'=== HP bare-metal port-read capture ===\n'
        f'started:        {ts}\n'
        f'git HEAD:       {head}\n'
        f'image:          {args.image}\n'
        f'image sha256:   {build_hash}\n'
        f'deployed:       {args.deployed}\n'
        f'deployed sha256:{deployed_hash}\n'
        f'hash gate:      {gate}\n'
        f'boot path:      {args.boot_path}\n'
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
            stop = datetime.datetime.now().astimezone().isoformat()
            log.write(f'=== capture stopped {stop} ===\n')
            print(f'\nLog written to {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
