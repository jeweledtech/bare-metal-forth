"""Shared serial-console helpers for the QEMU-backed tests.

Both the connect and the command exchange are bounded *in aggregate*. A
per-operation timeout is not a test timeout: a hundred individually-timely
recvs is a twenty-minute hang built out of compliant operations (see
docs/evidence/finding-qemu-test-no-serial-output-2026-10-02.md). The same
unbounded-recv shape bit twice — once at the banner drain, once in the
command loop — so both live here, one implementation rather than one per
test (TASK_HARNESS_KILL_BY_PID §3a/§3c).

The recipe's `timeout $(T_<NAME>)` is the hard outer cap; these budgets keep
any single step from consuming it.
"""
import socket
import time


def connect_and_sync(port, budget=30.0, host='127.0.0.1'):
    """Connect and synchronize on the guest's `ok` prompt; return the socket.

    Does not depend on the banner — a fast QEMU start emits it before this
    client attaches, and `-serial …,wait=off` discards pre-connection output,
    so a blind drain blocks forever on an idle prompt. Instead: connect
    (retrying until QEMU's socket is up), then *provoke* — send a newline and
    read until the guest answers `ok`, retrying until it does or `budget`
    elapses. Synchronized by construction. Raises TimeoutError on budget.
    """
    deadline = time.time() + budget
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    while time.time() < deadline:
        try:
            s.connect((host, port))
            break
        except OSError:
            time.sleep(0.25)
    else:
        raise TimeoutError(f'could not connect to {host}:{port} within {budget}s')
    seen = ''
    while time.time() < deadline:
        try:
            s.sendall(b'\r')
        except OSError as e:
            raise TimeoutError(f'send failed before prompt: {e!r}')
        try:
            while True:
                d = s.recv(4096)
                if not d:
                    break
                seen += d.decode('ascii', errors='replace')
        except socket.timeout:
            pass
        if 'ok' in seen:
            return s
        time.sleep(0.5)
    raise TimeoutError(f'guest never reached `ok` within {budget}s')


def send_expect(sock, cmd, expect=None, budget=15.0, settle=1.0, gap=2.0):
    """Send `cmd` (CR-terminated) and read the reply, bounded in aggregate.

    Reads until one of: `expect` (a substring) appears, a `gap`-second quiet
    (the reply finished), an empty recv (peer closed), or `budget` seconds
    total — whichever is first. The `budget` cap is what a plain per-recv
    timeout lacks: a guest that streams continuously can never outlast it.
    Returns the decoded reply (echo included; callers strip it as before).
    If `expect` is given and not seen within budget, raises TimeoutError so
    the caller fails fast rather than hanging.
    """
    deadline = time.time() + budget
    sock.sendall((cmd + '\r').encode())
    time.sleep(settle)
    sock.settimeout(gap)
    resp = ''
    while time.time() < deadline:
        try:
            d = sock.recv(4096)
            if not d:
                break
            resp += d.decode('ascii', errors='replace')
            if expect is not None and expect in resp:
                return resp
        except socket.timeout:
            break  # a `gap`-second quiet = the reply is complete
    if expect is not None and expect not in resp:
        raise TimeoutError(
            f'{cmd!r}: {expect!r} not seen within {budget}s; got {resp[:160]!r}')
    return resp
