#!/usr/bin/env python3
"""Gate P (TASK_PORT_REFUSAL_4C §1): does the port probe agree with QEMU?

For each listener kind holding a port, and each QEMU listen form the tree
uses, start a real QEMU against that port and record whether it could
listen (and on what address), next to what the probe says. With --measure
it also prints every candidate bind, which is how the probe's rule was
chosen. "Reaches" is observed: the gate connects to 127.0.0.1:P as the
tests do and checks that QEMU owns the accepted connection. Exit 1 if the
probe disagrees with "reaches" in any row, or if, for a listen form the
tree still uses, QEMU starts but is not reached (a hijack) in any row.

Run from the tree root. Starts one QEMU at a time, pidfile under
build/ports-gate.d, killed by that pidfile. Port: GATE_PORT (default
TEST_PORT_BASE + 190).
"""
import errno, os, signal, socket, subprocess, sys, time

WT = os.getcwd()
sys.path.insert(0, os.path.join(WT, 'tools'))
import ports_free  # noqa: E402

D = os.path.join('build', 'ports-gate.d')
PF = os.path.join(D, 'gate.pid')
QEMU = 'qemu-system-i386'

FORMS = {
    'tcp::P':          lambda p: ['-nic', 'none', '-serial', f'tcp::{p},server=on,wait=off'],
    'tcp:127.0.0.1:P': lambda p: ['-nic', 'none', '-monitor', f'tcp:127.0.0.1:{p},server=on,wait=off'],
    'listen=:P':       lambda p: ['-netdev', f'socket,id=n0,listen=:{p}', '-device', 'ne2k_pci,netdev=n0'],
}


def forms_in_use():
    """QEMU listen forms that appear in the Makefile and tests/*.py."""
    import glob, re
    text = open('Makefile').read() + ''.join(open(f).read() for f in glob.glob('tests/*.py'))
    use = set()
    if re.search(r"tcp::[0-9$({]", text):
        use.add('tcp::P')
    if 'tcp:127.0.0.1:' in text:
        use.add('tcp:127.0.0.1:P')
    if 'listen=:' in text:
        use.add('listen=:P')
    return use


def base():
    if os.environ.get('GATE_PORT'):
        return int(os.environ['GATE_PORT'])
    if os.environ.get('TEST_PORT_BASE'):
        return int(os.environ['TEST_PORT_BASE']) + 190
    ck = subprocess.run(['cksum'], input=WT.encode(), capture_output=True).stdout.split()[0]
    return 2200 + (int(ck) % 34) * 200 + 190


def listen(fam, host, port, v6only=None):
    s = socket.socket(fam, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if v6only is not None:
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, v6only)
    s.bind((host, port))
    s.listen(1)
    return s


def time_wait(port):
    """Leave `port` in TIME_WAIT on the listening side (server closes first)."""
    srv = listen(socket.AF_INET, '0.0.0.0', port)
    cli = socket.create_connection(('127.0.0.1', port))
    conn, _ = srv.accept()
    conn.close()
    time.sleep(0.2)
    cli.close()
    srv.close()
    out = subprocess.run(['ss', '-Htan', 'state', 'time-wait', f'( sport = :{port} )'],
                         capture_output=True, text=True).stdout
    assert out.strip(), f'no TIME_WAIT on :{port}'
    return []


HOLDERS = {
    'nothing':          lambda p: [],
    '127.0.0.1':        lambda p: [listen(socket.AF_INET, '127.0.0.1', p)],
    '0.0.0.0':          lambda p: [listen(socket.AF_INET, '0.0.0.0', p)],
    '[::] dual-stack':  lambda p: [listen(socket.AF_INET6, '::', p, v6only=0)],
    '[::] v6-only':     lambda p: [listen(socket.AF_INET6, '::', p, v6only=1)],
    'TIME_WAIT':        time_wait,
}


def candidate_binds(port):
    """Every bind the probe could use; True = bind succeeded (port free for it)."""
    out = {}
    for name, fam, host, v6 in (('v4 any', socket.AF_INET, '0.0.0.0', None),
                                ('v4 lo', socket.AF_INET, '127.0.0.1', None),
                                ('v6 dual', socket.AF_INET6, '::', 0),
                                ('v6 only', socket.AF_INET6, '::', 1),
                                ('v6 lo', socket.AF_INET6, '::1', None)):
        try:
            listen(fam, host, port, v6).close()
            out[name] = True
        except OSError as e:
            out[name] = False if e.errno == errno.EADDRINUSE else f'err{e.errno}'
    return out


def kill_gate_qemu():
    try:
        q = int(open(PF).read())
    except (OSError, ValueError):
        return
    try:
        held = any(os.readlink(f'/proc/{q}/fd/{f}') == os.path.join(WT, PF) for f in os.listdir(f'/proc/{q}/fd'))
        if held and os.readlink(f'/proc/{q}/exe').rsplit('/', 1)[-1].startswith('qemu-system'):
            os.kill(q, signal.SIGKILL)
    except OSError:
        pass
    for _ in range(40):
        try:
            if open(f'/proc/{q}/stat').read().split()[2] == 'Z':
                break
        except OSError:
            break
        time.sleep(0.05)
    try:
        os.remove(PF)
    except OSError:
        pass


def reaches_qemu(port, q):
    """Connect to 127.0.0.1:port as the tests do; does QEMU own the accepted end?"""
    try:
        c = socket.create_connection(('127.0.0.1', port), timeout=3)
    except OSError:
        return False
    try:
        for _ in range(20):
            ss = subprocess.run(['ss', '-Htnp', 'state', 'established', f'( sport = :{port} )'],
                                capture_output=True, text=True).stdout
            if f'pid={q},' in ss:
                return True
            time.sleep(0.1)
        return False
    finally:
        c.close()


def qemu_listens(form, port):
    """(could listen, what it bound or its error line)"""
    kill_gate_qemu()
    r = subprocess.run([QEMU, '-S', '-display', 'none', '-daemonize', '-pidfile', PF] + FORMS[form](port),
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        msg = (r.stderr.strip().splitlines() or ['?'])[-1]
        return False, msg.split(': ', 1)[-1][:70], False
    q = int(open(PF).read())
    ss = subprocess.run(['ss', '-Htlnp', f'( sport = :{port} )'], capture_output=True, text=True).stdout
    bound = sorted({ln.split()[3] for ln in ss.splitlines() if f'pid={q},' in ln})
    reach = reaches_qemu(port, q)
    kill_gate_qemu()
    return True, ' '.join(bound), reach


def main():
    measure = '--measure' in sys.argv
    port = base()
    os.makedirs(D, exist_ok=True)
    print(f'QEMU: {subprocess.run([QEMU, "--version"], capture_output=True, text=True).stdout.splitlines()[0]}')
    print(f'port {port}; probe rule: {ports_free.RULE}')
    bad = 0
    rows = []
    for hk, hold in HOLDERS.items():
        for form in FORMS:
            # a fresh port per row: TIME_WAIT and lingering sockets must not leak between rows
            p = port
            held = hold(p)
            try:
                cand = candidate_binds(p) if measure else None
                probe_free = ports_free.free(p, form)
                q_ok, q_detail, q_reach = qemu_listens(form, p)
            finally:
                for s in held:
                    s.close()
            agree = probe_free == q_ok
            agree_reach = probe_free == q_reach
            bad += not agree_reach
            rows.append((hk, form, q_ok, q_detail, q_reach, probe_free, agree, agree_reach, cand))
            # wait out TIME_WAIT before reusing the port for the next row
            while subprocess.run(['ss', '-Htan', f'( sport = :{p} )'], capture_output=True, text=True).stdout.strip():
                time.sleep(1)
    yn = lambda v: 'yes' if v else 'no'
    print('| Holder | QEMU form | QEMU starts? | QEMU bound / error | 127.0.0.1 reaches QEMU? | Probe: free? | = starts? | = reaches? |' + (' Candidate binds (True = could bind) |' if measure else ''))
    print('|---|---|---|---|---|---|---|---|' + ('---|' if measure else ''))
    for hk, form, q_ok, q_detail, q_reach, pf, agree, agree_reach, cand in rows:
        c = (' ' + ', '.join(f'{k}={v}' for k, v in cand.items()) + ' |') if measure else ''
        print(f'| {hk} | `{form}` | {yn(q_ok)} | {q_detail} | {yn(q_reach)} | {yn(pf)} | {yn(agree) if agree else "**no**"} | {yn(agree_reach) if agree_reach else "**no**"} |' + c)
    use = forms_in_use()
    # a form in use where QEMU starts but the tests do not reach it is a hijack
    hijack = [(r[0], r[1]) for r in rows if r[1] in use and r[2] != r[4]]
    print(f'rows={len(rows)} disagree_with_starts={sum(not r[6] for r in rows)} disagree_with_reaches={bad}')
    print(f'forms in use: {sorted(use)}; starts-but-not-reached rows in a form in use: {len(hijack)}'
          + ''.join(f'\n  HIJACK: holder {h}, form {f}' for h, f in hijack))
    sys.exit(1 if bad or hijack else 0)


if __name__ == '__main__':
    main()
