#!/usr/bin/env python3
"""SIGINT re-run sweep (TASK_HARNESS_KILL_BY_PID correction, 2026-10-05).

Every case is launched through a small exec wrapper that resets SIGINT and
SIGQUIT to SIG_DFL (as a terminal Ctrl-C finds them) and makes the process a
session/group leader. Before signalling, the case PROVES SIGINT is
deliverable: SigIgn of make (recipe cases) and of the test process must have
the SIGINT bit (0x2) clear. Otherwise the case is NOT RUN. Two control
cases keep SIGINT ignored. CONTROL-test-smoke-ignored is not a valid control:
its recipe runs the test under timeout, which un-ignores SIGINT for it.
CONTROL-script-asm_vocab-ignored is: its test starts with SIGINT ignored and
must run to completion.

PIDs come from pidfiles and /proc walks, never pgrep. Run from the tree
root: `python3 tools/sigint_sweep.py [--to-test] [case-name ...]`.
--to-test first sends one SIGINT to the test process only (script-level
isolation). Logs go to $SWEEP_LOGDIR (default build/sigint-sweep/).
Ports follow TEST_PORT_BASE (env, else the Makefile's formula).
In a fresh tree, first copy in the private-owned files (forth/dict/*.fth
and tests/*.py the private repo tracks; check-sync must print OK) and run
`make combined`: recipe cases build their own images, but the script cases
(script/...) start QEMU on build/combined.img and combined-ide.img directly.
A case whose script or image is missing prints NOT RUN.
"""
import os, signal, subprocess, sys, time

WT = os.getcwd()
S = os.environ.get('SWEEP_LOGDIR', os.path.join(WT, 'build', 'sigint-sweep'))
os.makedirs(S, exist_ok=True)


def port_base():
    """TEST_PORT_BASE as the Makefile derives it from the tree path."""
    if os.environ.get('TEST_PORT_BASE'):
        return int(os.environ['TEST_PORT_BASE'])
    ck = subprocess.run(['cksum'], input=WT.encode(), capture_output=True).stdout.split()[0]
    return 2200 + (int(ck) % 34) * 200


BASE = port_base()
SWEEP_DIR = 'build/sweep.d'
MYPGID = os.getpgid(0)

LAUNCH_DFL = ("import os,signal,sys;"
              "signal.signal(signal.SIGINT,signal.SIG_DFL);"
              "signal.signal(signal.SIGQUIT,signal.SIG_DFL);"
              "os.setsid();"
              "os.execvp(sys.argv[1],sys.argv[1:])")
LAUNCH_IGN = ("import os,signal,sys;"
              "signal.signal(signal.SIGINT,signal.SIG_IGN);"
              "signal.signal(signal.SIGQUIT,signal.SIG_IGN);"
              "os.setsid();"
              "os.execvp(sys.argv[1],sys.argv[1:])")


def status(pid, key):
    try:
        for ln in open(f'/proc/{pid}/status'):
            if ln.startswith(key + ':'):
                return ln.split()[1]
    except OSError:
        return None


def alive(pid):
    try:
        return open(f'/proc/{pid}/stat').read().split()[2] != 'Z'
    except OSError:
        return False


def cmdline(pid):
    try:
        return open(f'/proc/{pid}/cmdline', 'rb').read().replace(b'\0', b' ').decode().strip()
    except OSError:
        return ''


def comm(pid):
    try:
        return open(f'/proc/{pid}/comm').read().strip()
    except OSError:
        return ''


def descendants(root):
    kids = {}
    for d in os.listdir('/proc'):
        if d.isdigit():
            try:
                ppid = int(open(f'/proc/{d}/stat').read().rsplit(')', 1)[1].split()[1])
            except (OSError, IndexError, ValueError):
                continue
            kids.setdefault(ppid, []).append(int(d))
    out, todo = [], [root]
    while todo:
        p = todo.pop()
        for c in kids.get(p, []):
            out.append(c)
            todo.append(c)
    return out


def tree_qemus():
    out = []
    for d in os.listdir('/proc'):
        if d.isdigit() and comm(d).startswith('qemu-system'):
            try:
                fds = [os.readlink(f'/proc/{d}/fd/{f}') for f in os.listdir(f'/proc/{d}/fd')]
            except OSError:
                continue
            if any(x.startswith(WT + '/build/') for x in fds):
                out.append(int(d))
    return out


def holds(qpid, pidfile):
    want = os.path.join(WT, pidfile)
    try:
        return any(os.readlink(f'/proc/{qpid}/fd/{f}') == want for f in os.listdir(f'/proc/{qpid}/fd'))
    except OSError:
        return False


def sigint_ign(pid):
    v = status(pid, 'SigIgn')
    return None if v is None else bool(int(v, 16) & 0x2)


def syscall_nr(pid):
    try:
        return open(f'/proc/{pid}/syscall').read().split()[0]
    except (OSError, IndexError):
        return None


POLL_NRS = {'7', '271'}          # x86-64 poll, ppoll: where recv(timeout) blocks
NAMES = {'7': 'poll', '271': 'ppoll', '230': 'clock_nanosleep', '45': 'recvfrom', '23': 'select', '270': 'pselect6', 'running': 'running'}


def aim_at_recv(test, limit=60):
    """Wait until the test is blocked in poll/ppoll (inside recv); return what was seen."""
    t_end = time.time() + limit
    seen = []
    while time.time() < t_end and alive(test):
        nr = syscall_nr(test)
        if nr in POLL_NRS:
            return f'aimed: in {NAMES[nr]}'
        if nr and (not seen or seen[-1] != nr):
            seen.append(nr)
        time.sleep(0.02)
    return 'UNAIMED (no poll seen in 60s; saw ' + ','.join(NAMES.get(n, n) for n in seen[-4:]) + ')'


def find_test_proc(root, script):
    for p in descendants(root):
        if comm(p) == 'python3' and f'tests/{script}' in cmdline(p):
            return p
    return None


TO_TEST = False


def run_case(name, argv, pidfile, script, env_extra=None, ignore=False, wait_s=2400):
    """argv: what the wrapper execs (['make', target, ...] or ['python3', 'tests/x.py', port])."""
    if tree_qemus():
        return f'{name}: NOT RUN (a tree QEMU is already running: {tree_qemus()})'
    env_extra = dict(env_extra or {})
    fixture = env_extra.pop('_FIXTURE', False)
    env = dict(os.environ, **env_extra)
    if fixture:
        # The script starts no QEMU: the harness starts the test-vocabs
        # fixture line on the script's port, by pidfile, before the script.
        port = int(argv[2])
        fpf = os.path.join(WT, pidfile)
        os.makedirs(os.path.dirname(fpf), exist_ok=True)
        subprocess.run(['cp', 'build/combined.img', 'build/combined-ide.img'], check=True, cwd=WT)
        r = subprocess.run(['qemu-system-i386', '-drive', 'file=build/combined.img,format=raw,if=floppy',
                            '-drive', 'file=build/combined-ide.img,format=raw,if=ide,index=1',
                            '-nic', 'model=ne2k_pci', '-serial', f'tcp:127.0.0.1:{port},server=on,wait=off',
                            '-display', 'none', '-daemonize', '-pidfile', fpf], capture_output=True, cwd=WT)
        if r.returncode != 0:
            return f'{name}: NOT RUN (fixture QEMU did not start: {r.stderr.decode().strip()[-120:]})'
        time.sleep(2)
    if not fixture:
        try:
            os.remove(os.path.join(WT, pidfile))
        except OSError:
            pass
    LOG = f"{S}/{name.replace('/', '__')}.log"
    log = open(LOG, 'w')
    pr = subprocess.Popen([sys.executable, '-c', LAUNCH_IGN if ignore else LAUNCH_DFL] + argv,
                          stdout=log, stderr=subprocess.STDOUT, env=env, cwd=WT)
    lead = pr.pid
    t_end = time.time() + wait_s
    q = None
    while time.time() < t_end and pr.poll() is None:
        try:
            q = int(open(os.path.join(WT, pidfile)).read().split()[0])
        except (OSError, ValueError, IndexError):
            q = None
        if q and alive(q) and holds(q, pidfile):
            break
        q = None
        time.sleep(0.5)
    if not q:
        rc = pr.wait() if pr.poll() is None else pr.returncode
        return f'{name}: NOT RUN (role QEMU never held {pidfile}; launcher exit {rc})'
    time.sleep(4)
    is_make = argv[0] == 'make'
    test = find_test_proc(lead, script) if is_make else lead
    ign_lead = sigint_ign(lead)
    ign_test = sigint_ign(test) if test else None
    pg = os.getpgid(lead)
    head = (f'{name}: make SigIgn={status(lead, "SigIgn")} ' if is_make else f'{name}: (script, no make) ') + \
           f'test[{test}] SigIgn={status(test, "SigIgn") if test else "?"}'
    if pg == MYPGID or pg != lead:
        pr.kill(); pr.wait()
        return head + ' -> NOT RUN (process-group guard)'
    deliverable = (ign_lead is False) and (ign_test is False)
    if not ignore and test is None:
        os.killpg(pg, signal.SIGTERM); pr.wait()
        return head + ' -> NOT RUN (no test process found: it ended before the signal)'
    if not ignore and not deliverable:
        os.killpg(pg, signal.SIGTERM); pr.wait()
        return head + ' -> NOT RUN (SIGINT bit set: not deliverable)'
    aim = aim_at_recv(test) if test else 'UNAIMED (no test process)'
    head += f' [{aim}]'
    t0 = time.time()
    if TO_TEST:                       # script-level isolation: one SIGINT, test only
        os.kill(test, signal.SIGINT)
        while alive(test) and time.time() - t0 < 300:
            time.sleep(0.25)
        t_iso = time.time() - t0
        head += f' [ISOLATED: one SIGINT to test only; test {"STILL ALIVE after 300s" if alive(test) else f"exit after {t_iso:.0f}s"}]'
    os.killpg(pg, signal.SIGINT)
    try:
        rc = pr.wait(timeout=wait_s)
    except subprocess.TimeoutExpired:
        os.killpg(pg, signal.SIGTERM); rc = pr.wait()
    dt = time.time() - t0
    # make can die at once while a test that swallows SIGINT runs on as an
    # orphan; time the test process itself (not our child: poll /proc)
    t_test = None
    if test and test != lead:
        while alive(test) and time.time() - t0 < dt + 120:
            time.sleep(0.25)
        t_test = None if alive(test) else time.time() - t0
    time.sleep(1.5)
    left_pf = os.path.exists(os.path.join(WT, pidfile))
    out = open(LOG).read()
    passed = [ln for ln in out.splitlines() if ln.startswith('Passed:')][-1:]
    causes = [c for c in ('KeyboardInterrupt', 'BrokenPipeError', 'ConnectionResetError', 'ConnectionRefusedError', 'TimeoutError') if c in out]
    cause = 'test died by ' + '+'.join(causes) if causes else 'no traceback'
    tst = ('' if not test or test == lead else
           (f'test exit after {t_test:.0f}s; ' if t_test is not None else f'test STILL ALIVE 120s after make (!); '))
    res = (f' -> SIGINT{" (CONTROL, ignored)" if ignore else ""}: launcher exit {rc} after {dt:.0f}s; ' + tst +
           (f'fixture QEMU (harness-owned) {"alive, stopped by the harness" if alive(q) else "gone"}; '
            if fixture else
            f'QEMU {"gone" if not alive(q) else "LEFT(!)"}; pidfile {"LEFT(!)" if left_pf else "gone"}; ') +
           f'tree QEMU={tree_qemus()}; {cause}' + (f'; {passed[0]}' if passed else ''))
    if test and alive(test):
        try:
            os.kill(test, signal.SIGKILL)
        except OSError:
            pass
    for leftover in tree_qemus():          # never carry a QEMU into the next case
        try:
            os.kill(leftover, signal.SIGKILL)
        except OSError:
            pass
    return head + res
    if fixture:
        try:
            os.remove(os.path.join(WT, pidfile))
        except OSError:
            pass


VOC = 'test_editor test_x86_asm test_driver_vocabs test_disasm test_port_mapper test_echoport test_catalog_complete'.split()
GUI = 'test_stub_dispatch test_ui_core test_gui_harvest test_ui_parser test_ui_events test_fe_strip_cr'.split()

CASES = [
    ('CONTROL-test-smoke-ignored', ['make', 'test-smoke'], 'build/test-smoke.pid', 'smoke_test.py', None, True),
    # control 2: the test itself starts with SIGINT ignored (direct run, no timeout); QEMU daemonized in its own session
    ('CONTROL-script-asm_vocab-ignored', ['python3', 'tests/test_asm_vocab.py', str(BASE + 64)], f'{SWEEP_DIR}/asm-vocab.pid', 'test_asm_vocab.py', {'QEMU_PIDDIR': SWEEP_DIR}, True),
    # batch 1
    ('test-log-harness', ['make', 'test-log-harness'], 'build/test-log-harness.pid', 'test_log_harness.py', None, False),
    ('test-log-harness-nic', ['make', 'test-log-harness-nic'], 'build/test-log-harness-nic.pid', 'test_log_harness_nic.py', None, False),
    ('test-xhci', ['make', 'test-xhci'], 'build/test-xhci.pid', 'test_xhci.py', None, False),
    ('test-pci-bar', ['make', 'test-pci-bar'], 'build/test-pci-bar.pid', 'test_pci_bar.py', None, False),
    ('test-firstboot/lan', ['make', 'test-firstboot'], 'build/firstboot-lan.pid', 'test_firstboot.py', None, False),
    ('test-firstboot/offline', ['make', 'test-firstboot'], 'build/firstboot-offline.pid', 'test_firstboot.py', None, False),
    # 2a
    *[(t, ['make', t], f'build/{t}.pid', s, None, False) for t, s in (
        ('test-smoke', 'smoke_test.py'), ('test-loops', 'test_begin_while.py'), ('test-abort', 'test_abort.py'),
        ('test-dict-bounds', 'test_dict_bounds.py'), ('test-phys-alloc', 'test_phys_alloc.py'),
        ('test-pci-typing', 'test_pci_typing.py'))],
    # 2b
    *[(t, ['make', t], f'build/{t}.pid', s, None, False) for t, s in (
        ('test-squote-laydown', 'test_squote_laydown.py'), ('test-squote-laydown-backstop0', 'test_squote_laydown.py'),
        ('test-flush', 'test_flush_stress.py'), ('test-file-stream', 'test_file_stream_helpers.py'),
        ('test-integration', 'test_full_integration.py'))],
    # 2c loops, every fixture
    *[(f'test-vocabs/{f}', ['make', 'test-vocabs', f'VOCAB_TESTS={f}'], f'build/test-vocabs-{f}.pid', f'{f}.py', None, False) for f in VOC],
    *[(f'test-gui/{f}', ['make', 'test-gui', f'GUI_TESTS={f}'], f'build/test-gui-{f}.pid', f'{f}.py', None, False) for f in GUI],
    ('test-install', ['make', 'test-install'], 'build/test-install.pid', 'test_install.py', None, False),
    # test-meta, every role
    *[(f'test-meta/{r}', ['make', 'test-meta', f'META_FIXTURES={fx}'], f'build/test-meta.d/{r}.pid', f'{fx}.py', None, False) for fx, r in (
        ('test_metacompiler', 'metacompiler'), ('test_meta_compile', 'meta-compile'), ('test_meta_b6', 'meta-b6'),
        ('test_meta_boot', 'meta-boot-builder'), ('test_meta_boot', 'meta-boot-booted'),
        ('test_meta_b6b', 'meta-b6b-builder'), ('test_meta_b6b', 'meta-b6b-booted'),
        ('test_meta_does', 'meta-does-builder'), ('test_meta_does', 'meta-does-booted'))],
    # 3a / 3b
    ('test-ahci-write', ['make', 'test-ahci-write'], 'build/test-ahci-write.pid', 'test_ahci_write.py', None, False),
    ('test-vbr', ['make', 'test-vbr'], 'build/test-vbr.d/vbr.pid', 'test_vbr_boot.py', None, False),
    ('test-g6', ['make', 'test-g6'], 'build/test-g6.d/g6.pid', 'test_g6_chain.py', None, False),
    ('test-block-reload', ['make', 'test-block-reload'], 'build/test-block-reload.d/block-reload.pid', 'test_block_reload.py', None, False),
    ('test-arm64-boot/builder', ['make', 'test-arm64-boot'], 'build/test-arm64-boot.d/builder.pid', 'test_arm64_boot.py', None, False),
    ('test-arm64-boot/boot', ['make', 'test-arm64-boot'], 'build/test-arm64-boot.d/boot.pid', 'test_arm64_boot.py', None, False),
    *[(f'test-cortexm/{r}', ['make', 'test-cortexm'], f'build/test-cortexm.d/{r}.pid', 'test_cortexm_boot.py', None, False) for r in ('builder', 'boot-run', 'boot')],
    # py-a
    ('test-carrier-write-safe', ['make', 'test-carrier-write-safe'], 'build/test-carrier-write-safe.d/carrier.pid', 'test_carrier_write_safe.py', None, False),
    *[(f'test-network/{r}', ['make', 'test-network'], f'build/test-network.d/{r}.pid', 'test_ne2000_network.py', None, False) for r in ('net-a', 'net-b')],
    ('test-memdisk', ['make', 'test-memdisk'], 'build/test-memdisk.d/memdisk.pid', 'test_memdisk_blk_writer.py', None, False),
    *[(f'test-survey/{p}', ['make', 'test-survey'], f'build/test-survey.d/survey-{p}.pid', 'test_survey_layouts.py', None, False) for p in range(BASE + 100, BASE + 106)],
    # py-b / py-c scripts, run directly (no make)
    *[(f'script/{s}', ['python3', f'tests/{s}.py', str(port)], f'{SWEEP_DIR}/{role}.pid', f'{s}.py', {'QEMU_PIDDIR': SWEEP_DIR}, False) for s, role, port in (
        ('eviction_flush_test', 'eviction-flush', BASE + 60), ('iv_roundtrip_test', 'iv-roundtrip', BASE + 61),
        ('test_ahci_blk_reader', 'ahci-blk-reader', BASE + 62), ('test_ahci_blk_writer', 'ahci-blk-writer', BASE + 63),
        ('test_asm_vocab', 'asm-vocab', BASE + 64), ('test_blk_writer_vector', 'blk-writer-vector', BASE + 66),
        ('test_persist_quick', 'persist-quick', BASE + 67), ('test_shutdown', 'shutdown', BASE + 68),
        ('test_mft_bounds', 'mft-bounds', BASE + 69))],
    # bare-except scripts that start no QEMU (4b step 4): the harness starts the
    # test-vocabs fixture line for them
    *[(f'fixture/{s}', ['python3', f'tests/{s}.py', str(BASE + 150 + i)], f'{SWEEP_DIR}/fixture-{s}.pid', f'{s}.py',
       {'_FIXTURE': True}, False) for i, s in enumerate((
        'test_catalog_registry', 'test_dump', 'test_ne2000', 'test_pci_enum',
        'test_pit_timer', 'test_ps2_keyboard', 'test_ps2_mouse', 'test_vga_graphics'))],
]

if __name__ == '__main__':
    TO_TEST = '--to-test' in sys.argv
    only = set(a for a in sys.argv[1:] if a != '--to-test')   # exact case names; none = all
    os.makedirs(os.path.join(WT, SWEEP_DIR), exist_ok=True)
    print(f'HEAD={subprocess.run(["git","rev-parse","--short","HEAD"],capture_output=True,text=True).stdout.strip()} '
          f'cases={len(CASES)} start={time.strftime("%H:%M:%S")}', flush=True)
    for name, argv, pidfile, script, env_extra, ignore in CASES:
        if only and name not in only:
            continue
        print(run_case(name, argv, pidfile, script, env_extra, ignore), flush=True)
    print(f'SWEEP_DONE {time.strftime("%H:%M:%S")}', flush=True)
