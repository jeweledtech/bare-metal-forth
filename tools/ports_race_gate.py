#!/usr/bin/env python3
"""4c port gates (TASK_PORT_REFUSAL_4C §5): refusal sweep and race gate.

For each listen entry in tools/qemu_ports.json, a plain IPv4 listener on
0.0.0.0 (the "holder") takes that port and records anything sent to it.

  --mode refuse   the holder takes the port before the recipe starts. Pass:
                  make fails, `PORT BUSY: <port>` is printed, nothing is sent
                  to the holder, no QEMU or pidfile is left.
  --mode race     the holder takes the port only after the recipe's port
                  check has passed (PORTS_FREE is replaced by a wrapper that
                  runs the real check first), i.e. between check and launch.
                  Pass: make fails, the output names the port, nothing is sent
                  to the holder, no QEMU or pidfile is left. A recipe that ends
                  before it launches the held role is NOT REACHED, not a pass.

Run from the tree root, one harness at a time:
  ports_race_gate.py --mode refuse|race [recipe[/fixture][:offset] ...]
"""
import json, os, signal, socket, subprocess, sys, threading, time

WT = os.getcwd()
D = os.path.join(WT, 'build', 'ports-gate.d')
TABLE = json.load(open(os.path.join(WT, 'tools', 'qemu_ports.json')))
LOOP_VAR = {'test-vocabs': 'VOCAB_TESTS', 'test-gui': 'GUI_TESTS', 'test-meta': 'META_FIXTURES'}
CAP = int(os.environ.get('GATE_CAP', '1500'))


def base():
    if os.environ.get('TEST_PORT_BASE'):
        return int(os.environ['TEST_PORT_BASE'])
    ck = subprocess.run(['cksum'], input=WT.encode(), capture_output=True).stdout.split()[0]
    return 2200 + (int(ck) % 34) * 200


HOLDER = r'''
import os, socket, sys, threading
port, out = int(sys.argv[1]), sys.argv[2]
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(('0.0.0.0', port)); srv.listen(8)
open(out + '.ready', 'w').write(str(os.getpid()))
def rd(c):
    while True:
        try:
            d = c.recv(4096)
        except OSError:
            return
        if not d:
            return
        with open(out, 'ab') as f:
            f.write(d)
while True:
    c, _ = srv.accept()
    with open(out + '.conns', 'a') as f:
        f.write('1')
    threading.Thread(target=rd, args=(c,), daemon=True).start()
'''

# Wrapper for --mode race: run the real check; if it passed and this is the
# target recipe/fixture, start the holder and wait until it is listening.
WRAP = r'''#!/bin/sh
python3 tools/ports_free.py "$@"; rc=$?
[ $rc -eq 0 ] || exit $rc
case " $* " in *" --recipe $RACE_RECIPE "*) ;; *) exit 0;; esac
if [ -n "$RACE_FIXTURE" ]; then case " $* " in *" --fixture $RACE_FIXTURE "*) ;; *) exit 0;; esac; fi
[ -e "$RACE_OUT.ready" ] && exit 0
setsid python3 "$RACE_HOLDER" "$RACE_PORT" "$RACE_OUT" >/dev/null 2>&1 < /dev/null &
i=0; while [ ! -e "$RACE_OUT.ready" ] && [ $i -lt 100 ]; do sleep 0.05; i=$((i+1)); done
date +%s.%N > "$RACE_OUT.t"
exit 0
'''


def tree_state():
    q = []
    for d in os.listdir('/proc'):
        if d.isdigit():
            try:
                if open(f'/proc/{d}/comm').read().startswith('qemu-system') and any(
                        os.readlink(f'/proc/{d}/fd/{f}').startswith(WT + '/build/') for f in os.listdir(f'/proc/{d}/fd')):
                    q.append(int(d))
            except OSError:
                pass
    pids = []
    for root, _, files in os.walk(os.path.join(WT, 'build')):
        if root.startswith(D):
            continue
        pids += [os.path.relpath(os.path.join(root, f), WT) for f in files if f.endswith('.pid')]
    return q, pids


def cases(sel):
    out = []
    for r, fx in TABLE.items():
        for f, ents in fx.items():
            for e in ents:
                if 'offset' not in e:
                    continue
                key = f'{r}{"/" + f if f != "-" else ""}'
                if sel and not any(s == key or s == f'{key}:{e["offset"]}' or s == r for s in sel):
                    continue
                out.append((r, f, e))
    return out


def kill_holder(out):
    try:
        pid = int(open(out + '.ready').read())
        os.kill(pid, signal.SIGKILL)
    except (OSError, ValueError):
        pass


def run_case(mode, r, f, e, B):
    port = B + e['offset']
    tag = f'{r}{"/" + f if f != "-" else ""}:+{e["offset"]}'
    out = os.path.join(D, f'{mode}-{tag.replace("/", "__").replace(":", "_")}')
    for sfx in ('', '.ready', '.conns', '.t'):
        try:
            os.remove(out + sfx)
        except OSError:
            pass
    q0, p0 = tree_state()
    if q0:
        return f'{tag} port {port}: NOT RUN (tree QEMU running: {q0})'
    holder_py = os.path.join(D, 'holder.py')
    open(holder_py, 'w').write(HOLDER)
    argv = ['make', r]
    if f != '-':
        argv.append(f'{LOOP_VAR[r]}={f}')
    env = dict(os.environ)
    if mode == 'refuse':
        h = subprocess.Popen([sys.executable, holder_py, str(port), out], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if os.path.exists(out + '.ready'):
                break
            time.sleep(0.05)
    else:
        wrap = os.path.join(D, 'wrap.sh')
        open(wrap, 'w').write(WRAP)
        argv.append(f'PORTS_FREE=sh {wrap}')
        env.update(RACE_RECIPE=r, RACE_FIXTURE='' if f == '-' else f, RACE_PORT=str(port),
                   RACE_OUT=out, RACE_HOLDER=holder_py)
    log = out + '.log'
    t0 = time.time()
    p = subprocess.Popen(argv, stdout=open(log, 'w'), stderr=subprocess.STDOUT, env=env, start_new_session=True)
    try:
        rc = p.wait(timeout=CAP); capped = ''
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGTERM); rc = p.wait(); capped = f' (CAPPED {CAP}s)'
    t_end = time.time()
    time.sleep(1)
    held = os.path.exists(out + '.ready')
    sent = os.path.getsize(out) if os.path.exists(out) else 0
    conns = os.path.getsize(out + '.conns') if os.path.exists(out + '.conns') else 0
    t_hold = float(open(out + '.t').read()) if os.path.exists(out + '.t') else t0
    kill_holder(out)
    q1, p1 = tree_state()
    for qq in q1:
        os.kill(qq, signal.SIGKILL)
    text = open(log, errors='replace').read()
    named = [ln.strip() for ln in text.splitlines()
             if str(port) in ln and ('BUSY' in ln or 'FAIL' in ln or 'qemu-system' in ln or 'Address already' in ln)]
    if mode == 'race' and not held:
        verdict = 'NOT REACHED (recipe never ran the check for this role)'
    elif mode == 'race' and rc == 0:
        verdict = '**FAIL: make passed with the port held**'
    elif rc == 0:
        verdict = '**FAIL: make passed**'
    else:
        ok = named and sent == 0 and not q1 and set(p1) <= set(p0)
        if mode == 'refuse':
            ok = ok and any('PORT BUSY' in n for n in named)
        verdict = 'PASS' if ok else '**FAIL**'
    after = t_end - (t_hold if mode == 'race' else t0)
    return (f'{tag} port {port}: {verdict}; make exit {rc}{capped}; {"held " if mode == "race" else ""}'
            f'{after:.1f}s to exit; holder got {conns} conn(s) {sent} bytes; '
            f'QEMU left {q1}; new pidfiles {sorted(set(p1) - set(p0))}\n    named: {named[0][:150] if named else "(port not named)"}')


def main():
    mode = sys.argv[sys.argv.index('--mode') + 1]
    sel = [a for a in sys.argv[1:] if a not in ('--mode', mode)]
    os.makedirs(D, exist_ok=True)
    B = base()
    cs = cases(sel)
    print(f'mode={mode} base={B} cases={len(cs)} HEAD={subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()} '
          f'start={time.strftime("%H:%M:%S")}', flush=True)
    for r, f, e in cs:
        print(run_case(mode, r, f, e, B), flush=True)
    print(f'GATE_DONE {time.strftime("%H:%M:%S")}', flush=True)


if __name__ == '__main__':
    main()
