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
import os
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


PROMPT = b'ok '


def send_until_prompt(sock, cmd, budget=15.0, quiet=0.3):
    """Send `cmd` (CR appended) and read until the guest has answered every line.

    End-of-reply rule (measured, TASK_BOUNDED_READS_4B §3a, 2026-10-06): the
    guest ends each reply with the prompt `ok ` (lowercase, then a space) and
    sends nothing after it. A word's own output can also contain `ok `, and
    no text separates it from the prompt, so the rule is: N = the number of
    CR-terminated lines sent; the reply ends when at least N prompts have
    arrived (prompts = `ok ` occurrences received minus those in the echoed
    command text), the buffer ends with `ok `, and then `quiet` seconds pass
    with no byte. Otherwise it ends when the peer closes or `budget` runs out.

    KNOWN LIMIT: output containing `ok ` followed by more than `quiet`
    seconds of silent work ends the read early (measured: a 60M-iteration
    loop after a printed `x ok ` was silent 0.48s). Gate G1 (transcript
    equivalence) is what catches that in a real script.

    Returns (reply, how): reply decoded as before; how in
    {'prompt', 'closed', 'budget'}. Catches only socket timeouts and OSError,
    so KeyboardInterrupt passes through. With SERIAL_TRACE=<file> in the
    environment, appends one JSON line per call (for gate G1).
    """
    data = (cmd + '\r').encode()
    n = data.count(b'\r')
    echoed_oks = data.count(PROMPT)
    deadline = time.time() + budget
    sock.sendall(data)
    sock.settimeout(0.05)
    buf = b''
    last = time.time()
    how = 'budget'
    while time.time() < deadline:
        try:
            d = sock.recv(65536)
        except socket.timeout:
            if (buf.endswith(PROMPT) and buf.count(PROMPT) - echoed_oks >= n
                    and time.time() - last >= quiet):
                how = 'prompt'
                break
            continue
        except OSError:
            how = 'closed'
            break
        if not d:
            how = 'closed'
            break
        buf += d
        last = time.time()
    reply = buf.decode('ascii', errors='replace')
    trace(cmd, reply, how)
    return reply, how


def trace(cmd, reply, how):
    """With SERIAL_TRACE=<file> set, append one exchange as a JSON line
    (gate G1). Scripts that keep a fixed wait for a listed exception call
    this with how='fixed', so the exchange stays in the trace."""
    path = os.environ.get('SERIAL_TRACE')
    if path:
        import json
        with open(path, 'a') as f:
            f.write(json.dumps({'cmd': cmd, 'reply': reply, 'how': how}) + '\n')
