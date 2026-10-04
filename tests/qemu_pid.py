"""Pidfile-based QEMU cleanup for test scripts (TASK_HARNESS_KILL_BY_PID).

A script that starts QEMU itself passes `-pidfile pidfile(role)` and stops
it with `kill_pidfile(...)`. Never a pattern kill: `pkill -f "[q]emu.*PORT"`
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
