"""Pidfile-based QEMU cleanup for test scripts (TASK_HARNESS_KILL_BY_PID).

A script that starts QEMU itself passes `-pidfile pidfile(role)` and stops
it with `kill_pidfile(...)`. Never a pattern kill (match on the command line):
matches any process whose argv holds that text (other trees, other
sessions, the calling shell).

The recipe sets QEMU_PIDDIR (a path relative to the tree root, e.g.
build/test-g6.d) and runs QEMU_KILL over every *.pid there on start-up and
from its trap, so a QEMU is still cleared if this script is SIGKILLed.
Run by hand, pidfiles go to build/qemu-pids.

kill_pidfile kills only a qemu-system-* process that holds that pidfile
open (QEMU keeps it open and locked while it runs), the same guard as the
Makefile's QEMU_KILL. A stale pidfile whose PID was reused is removed, not
acted on.
"""
import os
import signal
import subprocess
import sys
import time

PIDDIR = os.environ.get('QEMU_PIDDIR') or os.path.join('build', 'qemu-pids')


def pidfile(role):
    """Path for a QEMU's -pidfile, e.g. pidfile('builder')."""
    os.makedirs(PIDDIR, exist_ok=True)
    return os.path.join(PIDDIR, f'{role}.pid')


def _dead(pid):
    try:
        with open(f'/proc/{pid}/stat') as f:
            return f.read().split()[2] == 'Z'
    except OSError:
        return True


def _is_ours(pid, path):
    try:
        exe = os.path.basename(os.readlink(f'/proc/{pid}/exe'))
    except OSError:
        return False
    if not exe.startswith('qemu-system-'):
        return False
    want = os.path.abspath(path)
    try:
        fds = os.listdir(f'/proc/{pid}/fd')
    except OSError:
        return False
    for fd in fds:
        try:
            if os.readlink(f'/proc/{pid}/fd/{fd}') == want:
                return True
        except OSError:
            continue
    return False


def kill_pidfile(path, wait=5.0):
    """Kill the QEMU named by `path` if it is ours; remove the pidfile."""
    try:
        with open(path) as f:
            pid = int(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        pid = None
    if pid is not None and _is_ours(pid, path):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        deadline = time.time() + wait
        while time.time() < deadline and not _dead(pid):
            time.sleep(0.1)
    try:
        os.remove(path)
    except OSError:
        pass


# --- Did the QEMU we launched start, and is it the one on the port? -------
# (TASK_PORT_REFUSAL_4C §4.) The recipe checks its ports before launching,
# but a port can be taken between that check and the launch. These make a
# script fail at once, naming the port, instead of connecting to whatever
# else holds it.

def _ports(port):
    return list(port) if isinstance(port, (list, tuple)) else [port]


def _owns_listener(pid, port):
    """True if QEMU `pid` owns the listening socket on every port given."""
    for p in _ports(port):
        out = subprocess.run(['ss', '-Htlnp', f'( sport = :{p} )'],
                             capture_output=True, text=True).stdout
        if f'pid={pid},' not in out:
            return False
    return True


def _fail(what, port, why):
    ps = _ports(port)
    print(f'FAIL: {what} QEMU did not start on port{"s" if len(ps) > 1 else ""} '
          f'{", ".join(map(str, ps))}: {why}', flush=True)
    sys.exit(1)


def _last_line(text):
    if isinstance(text, bytes):
        text = text.decode(errors='replace')
    lines = (text or '').strip().splitlines()
    return lines[-1] if lines else '(no error output)'


def check_launch(result, path, port, what, wait=5.0):
    """After subprocess.run([QEMU, ..., '-daemonize', '-pidfile', path], capture_output=True).

    Exits at once if QEMU exited non-zero, or if the QEMU in `path` does not
    own the listening socket on `port` (an int or a list of the ports it
    listens on). path=None checks the exit only."""
    if result.returncode != 0:
        _fail(what, port, _last_line(result.stderr))
    if path is None:
        return
    deadline = time.time() + wait
    while time.time() < deadline:
        try:
            pid = int(open(path).read().split()[0])
        except (OSError, ValueError, IndexError):
            pid = None
        if pid and _is_ours(pid, path) and _owns_listener(pid, port):
            return pid
        time.sleep(0.1)
    _fail(what, port, f'no QEMU from {path} is listening on it')


def wait_started(proc, path, port, what, stderr_path=None, wait=15.0):
    """After proc = subprocess.Popen([QEMU, ..., '-pidfile', path], ...).

    Waits until that QEMU holds its pidfile and owns the listening socket on
    `port`. Exits at once, naming the port, if the process exits first."""
    deadline = time.time() + wait
    while time.time() < deadline:
        if proc.poll() is not None:
            err = open(stderr_path).read() if stderr_path and os.path.exists(stderr_path) else ''
            _fail(what, port, f'exit {proc.returncode}: {_last_line(err)}')
        try:
            pid = int(open(path).read().split()[0])
        except (OSError, ValueError, IndexError):
            pid = None
        if pid and _is_ours(pid, path) and _owns_listener(pid, port):
            return pid
        time.sleep(0.1)
    _fail(what, port, f'not listening after {wait:.0f}s')
