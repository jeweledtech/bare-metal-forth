#!/usr/bin/env python3
"""Would QEMU fail to listen on these ports? (TASK_PORT_REFUSAL_4C)

free(port, form) answers for one QEMU listen form: can the tests (which
connect to 127.0.0.1) reach a QEMU that listens on this port? The rule must
agree with a real QEMU in every row of tools/ports_probe_gate.py.

Measured 2026-10-05 (QEMU 8.2.2): one IPv4 bind on 0.0.0.0 with
SO_REUSEADDR gives that answer for all three forms in use (tcp::P,
tcp:127.0.0.1:P, socket listen=:P) and all six holders. Note that for tcp::P
with an IPv4 listener already on the port, QEMU does NOT fail: it binds
[::] alone and starts, and a 127.0.0.1 connection reaches the other
listener. So "QEMU started" is not the same as "the tests reach QEMU".
"""
import errno, socket

RULE = 'IPv4 bind 0.0.0.0, SO_REUSEADDR (measured, Gate P 2026-10-05)'


def _binds(fam, host, port, v6only=None):
    s = socket.socket(fam, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if v6only is not None:
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, v6only)
        s.bind((host, port))
        return True
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            return False
        raise
    finally:
        s.close()


def free(port, form='tcp::P'):
    return _binds(socket.AF_INET, '0.0.0.0', port)


def holder(port):
    """Who listens on port (best effort, from ss -tlnp; empty if not visible)."""
    import subprocess
    out = subprocess.run(['ss', '-Htlnp', f'( sport = :{port} )'], capture_output=True, text=True).stdout
    users = sorted({u for ln in out.splitlines() for u in __import__('re').findall(r'\("([^"]+)",pid=(\d+)', ln)})
    return ', '.join(f'pid {p} {c}' for c, p in users) or 'holder not visible (another user, or TIME_WAIT)'


def main(argv):
    """ports_free.py --recipe R [--fixture F] --base B : exit 1 naming the first busy port."""
    import json, os, sys
    a = dict(zip(argv[1::2], argv[2::2]))
    recipe, fixture, base = a['--recipe'], a.get('--fixture', '-'), int(a['--base'])
    table = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'qemu_ports.json')))
    if recipe not in table or fixture not in table[recipe]:
        print(f'ports_free: {recipe}{"/" + fixture if fixture != "-" else ""} is not in tools/qemu_ports.json '
              f'(regenerate: python3 tools/port_inventory.py > tools/qemu_ports.json)', file=sys.stderr)
        return 2
    busy = 0
    for e in table[recipe][fixture]:
        if 'offset' not in e:
            continue
        port = base + e['offset']
        if not free(port, e['form']):
            print(f'PORT BUSY: {port} ({recipe}{"/" + fixture if fixture != "-" else ""} {e["kind"]} '
                  f'+{e["offset"]}) held by {holder(port)}', file=sys.stderr)
            busy += 1
    return 1 if busy else 0


if __name__ == '__main__':
    import sys
    sys.exit(main(sys.argv))
