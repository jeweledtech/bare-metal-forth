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
