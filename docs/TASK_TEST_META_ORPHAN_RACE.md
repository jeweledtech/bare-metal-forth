# TASK: test-meta QEMU orphaned by a SIGTERM to its recipe

Status: FIXED (F1, owner ruling 2026-10-10); gates in §7.2. Plan and red
came first, reported before the fix. Finding: public
`docs/evidence/finding-test-meta-orphan-after-sigterm-2026-10-09.md`.

## 1. What is known

Observed (2026-10-09):

- Command, as recorded with the run: inside a backgrounded
  `{ ...; } > floor-regress.log 2>&1` group,
  `timeout 1800 make test-meta 2>&1 | grep -E 'FAIL|Passed|passed|Error|\?' | tail -12`.
  At 1,800 s `timeout` sent SIGTERM. test-meta takes 1,886-1,905 s; its last
  fixture, test_meta_does, starts near 1,660 s and launches its booted QEMU
  about 145 s in, i.e. near 1,805 s: the signal landed close to that launch.
- Afterwards the booted QEMU ran, and `build/test-meta.d/meta-does-booted.pid`
  **still existed**.
- Experiment the same day (`setsid timeout 3000 make test-meta
  META_FIXTURES=test_meta_does`, SIGTERM to the group 15 s after the booted
  pidfile named a live QEMU, no pipe): cleared, exit 143, no pidfiles.

From the source:

- The recipe: `trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP; set -e`. The
  fixture runs under `timeout --foreground`. `QEMU_KILL_DIR` runs
  `QEMU_KILL` on every `$QPIDDIR/*.pid`; `QEMU_KILL` kills only a
  qemu-system process holding that pidfile open, and then **always**
  `rm -f`s the pidfile.
- So a pidfile that survives means: at the moment the trap ran, that file
  did not exist yet, or the trap never ran.
- The booted QEMU is launched with `subprocess.run([... '-daemonize',
  '-pidfile', ...])`; test_meta_does installs no signal handler.
- QEMU 8.2.2. With `-daemonize`, a pre-daemon parent stays in the caller's
  process group until the daemon reports that start-up finished; the daemon
  leaves the group with setsid. When the daemon writes its pidfile, relative
  to the fork and to the parent's exit, I have not measured.

## 2. Candidates (pre-registered)

- **R1 launch window** (the finding's explanation): SIGTERM kills the
  pre-daemon parent and python; the trap runs before the daemon has written
  its pidfile, finds nothing, and the daemon writes it afterwards. Needs a
  measurable gap between the fork and the pidfile write.
- **R2 the fixture outlives the trap**: python (or the launch) continues
  after the trap has run, then starts the booted QEMU. Under R2 a SIGTERM
  shortly BEFORE the launch can still orphan.
- **R3 the trap never ran** under the original wrapper (the pipe into
  `grep | tail`, the backgrounded group): then even a settled QEMU is
  orphaned. The 10-09 experiment never tested this; it used `setsid` and no
  pipe.

Prediction, written before any run: **R1, weakly.** It fits the timing; but
if E1 shows QEMU writing its pidfile within a few ms of the fork, the window
is too small to hit by chance, and R3 becomes the stronger candidate.

## 3. Experiments (after make -k test finishes; one run at a time; images
and pidfiles under `build/orphan.d/`; kill by pidfile only)

- **E0 signal dispositions.** `SigIgn`/`SigBlk` of the shell in a
  backgrounded group like the original, of `make`'s recipe shell and of the
  fixture's python. Prediction: SIGTERM neither ignored nor blocked anywhere.
- **E1 the QEMU 8.2.2 timeline.** 20 launches of the booted command line
  (same flags, any small image), polling every 1 ms: when the pidfile
  appears, when the daemon leaves the caller's group, when the pre-daemon
  parent exits. Output: the window between parent alive and pidfile written.
- **E2 (R3 discriminator) original wrapper, settled QEMU.** The original
  shape exactly (backgrounded `{ }` group, `timeout N make test-meta 2>&1 |
  grep ... | tail -12`), with `META_FIXTURES=test_meta_does` and N set to
  expire about 30 s after the booted pidfile appears. Predicted under R1/R2:
  cleared. Under R3: orphan.
- **E3 (R1 red) the shipped recipe, SIGTERM in the window.** A watcher
  sends SIGTERM to the recipe's process group at the first poll where a
  qemu-system process with `meta-boot-does.img` on its command line exists
  and `meta-does-booted.pid` does not. Three trials. Predicted under R1: at
  least one orphan (QEMU alive and its pidfile present after make exits).
- **E4 (R2) SIGTERM about 0.5 s before the launch** (at the
  `kill_qemu(str(PORT))` that precedes it, found by the builder pidfile
  disappearing). Two trials. Predicted under R1/R3: no orphan. Under R2:
  orphan.

A trial's orphan is recorded with its pid, age and pidfile, then killed with
`qemu_pid.kill_pidfile`.

## 4. The red

Whichever of E2-E4 orphans becomes the red: a trial on the shipped recipe
that ends with a live QEMU named by a surviving pidfile in
`build/test-meta.d/`. The fix (owner decision after this report) must turn
that trial clear, three times out of three, and leave a full test-meta's
counts unchanged.

Fix candidates, by mechanism (not chosen):

- R1: after `QEMU_KILL_DIR`, a short wait and a second sweep; or a sweep by
  identity (a qemu-system process holding any file in `$QPIDDIR` open),
  which needs no pidfile.
- R2: the trap waits for the fixture's process to be gone before sweeping.
- R3: whatever stops the trap running, fixed at that point.

Scope: every recipe that uses `QEMU_KILL_DIR` with a `-daemonize` launch
(batch 3b) shares R1/R2; the red is on test-meta only.

## 5. Results

### E1 the QEMU 8.2.2 timeline (`meta-boot-does.img`, 20 launches)

Pidfile written (with its pid) 5.7-7.0 ms after the launch; pre-daemon
parent exits 19.5-31.1 ms after; the daemon's process group is its own
(never the caller's) by the time the pidfile exists. So R1's window, from
the daemon's fork to its pidfile, is at most a millisecond or two of each
launch (a SIGTERM before the fork kills the one QEMU process; one after
the pidfile finds it). Hitting that by chance with a 1,800 s timeout is
improbable. Per §2, R3 is now the stronger candidate.

### E2 prediction (written before the run)

Original shape, `META_FIXTURES=test_meta_does`, `timeout 180` (booted QEMU
up from ~145 s, so settled ~35 s when the signal lands). Under R3: orphan.
Under R1: cleared. My prediction now: **orphan (R3)**, mechanism unknown.

### E2 result: ORPHAN, as predicted (R3)

`{ timeout 180 make test-meta META_FIXTURES=test_meta_does 2>&1 | grep ...
| tail -12; }` in a backgrounded group: the booted QEMU (pid 665399) came
up at 147.3 s; at 181.0 s make, the recipe shell, the inner timeout and
python all vanished within one 50 ms poll; afterwards the QEMU was alive
and `meta-does-booted.pid` still existed. The QEMU had been settled 34 s,
the case the 10-09 `setsid` experiment showed the trap clearing. So the
trap did not run: R1 is not needed to explain the orphan.

E0 (signal state, from the watcher): SIGTERM is neither ignored nor
blocked in any process; the recipe shell (`/bin/sh`, dash) catches HUP,
INT, TERM and CHLD and does NOT catch PIPE; python ignores PIPE.

Process groups: the shell that ran it has job control on (`$-` =
`hmtBc`), so a pipeline gets one process group led by its first element,
here `timeout` (pgrp 661720), and `grep` and `tail` are IN it. timeout's
group-wide SIGTERM therefore also kills the pipe's readers.

Named mechanism **R3a** (from the source of dash, not yet observed
directly): the inner `timeout --foreground` dies by SIGTERM (it re-raises
its child's signal); dash, as for any foreground job killed by a signal
other than INT/PIPE, writes `Terminated` to its stderr, the dead pipe;
dash dies of SIGPIPE before running its TERM trap, and a shell killed by
a signal runs no EXIT trap.

### E2b prediction (before the run)

Same as E2, but `grep` and `tail` ignore TERM (`(trap '' TERM; exec grep
...)`), so the pipe keeps its readers. Under R3a: **cleared**. If it still
orphans, R3a is wrong.

### E2b result: CLEARED, as predicted

Same run with `grep` and `tail` ignoring TERM: the booted QEMU (674879) went
at 181.03 s with the recipe; no pidfile left; make reported `Error 143`.
Keeping the pipe's readers alive is enough for the trap to run.

### R3a observed directly (no QEMU)

`timeout 2 strace -f ... sh -c "trap 'touch FLAG' EXIT TERM; set -e;
timeout --foreground 100 sleep 100" 2>&1 | grep zzz | tail -1`, run from a
job-control shell:

- readers in timeout's group: the inner timeout is `killed by SIGTERM`;
  dash then `write(2, "Terminated\n", 11) = -1 EPIPE (Broken pipe)`,
  gets `SIGPIPE` and is `killed by SIGPIPE`; FLAG not created.
- readers ignoring TERM: the same write returns 11; FLAG created.

`/bin/sh` here is `/usr/bin/dash`.

### What explains the 10-09 orphan

R3a, observed: under a pipe whose readers share timeout's process group,
the recipe shell dies of SIGPIPE while reporting the fixture's death, and
its trap never runs, whatever state the QEMU is in. The 10-09 `setsid`
experiment had no pipe, so it could not show this. The finding's launch
window (R1) is real but at most a millisecond or two per launch (E1); it
is not needed to explain the orphan, and the R3a fix does not close it.
E3 (R1) and E4 (R2) were not run: E1 sized R1, and R3a reproduces the
event from a settled QEMU, which neither R1 nor R2 can.

### Scope

31 recipe traps in the Makefile use the same list, `EXIT INT TERM HUP`,
and none has PIPE: 10 `QEMU_KILL_DIR`, 19 `QEMU_KILL`, 1 `GUI_KILL_ALL`,
1 `VOCABS_KILL_ALL`. Every one of them is exposed whenever its output goes
into a pipe whose reader dies with it. `make test` run directly to a file
or terminal is not exposed.

## 6. The red

- **Dynamic (the event itself):** E2 on the shipped recipe: QEMU alive
  and `meta-does-booted.pid` left after the wrapper returns. Trials: see
  6.1.
- **Static (all 31 traps):** a check (in test-make-wiring, or its own
  test) that every recipe trap naming a kill macro also handles PIPE.
  Today: 0 of 31; red.

Fix candidates (owner's choice; none applied):

- **F1** add PIPE to each trap list (`EXIT INT TERM HUP PIPE`): the sweep
  runs on the SIGPIPE itself, then `set -e` and the EXIT trap end the
  shell (the sweep is idempotent).
- **F2** `trap '' PIPE` in each recipe: the write fails with EPIPE, dash
  carries on and runs its TERM trap.
- F1 also covers a pipe that breaks without any SIGTERM (a reader that
  exits early). Either needs the gate: E2 clear 3/3, the static check
  31/31, a full test-meta unchanged, make -k test only xhci red.
- R1 (the millisecond launch window) stays open under both; a second
  sweep after a short wait would close it, as a separate decision.

### 6.1 Red trials (E2 shape, shipped recipe, `build/combined.img` `5fdfb315…`)

| trial | booted QEMU after the wrapper | `meta-does-booted.pid` |
|---|---|---|
| 1 (E2) | alive (pid 665399, 3:27 old when removed) | left |
| 2 | alive (36 s old) | left |
| 3 | alive (36 s old) | left |

**3/3 orphaned.** Each was removed with `qemu_pid.kill_pidfile`.

## 7. Fix (owner ruling 2026-10-10: F1)

F2 ruled out: `trap '' PIPE` would leave SIGPIPE ignored in every child the
recipe starts (QEMU, Python, the shell tools); a handler is not inherited.

- All 31 kill traps: `EXIT INT TERM HUP` -> `EXIT INT TERM HUP PIPE`.
- The trap action writes nothing. `QEMU_KILL`: `kill -9 ... 2>/dev/null`,
  `grep -q`, `rm -f` and `readlink` (no `-v`; checked: silent with exit 1
  on a missing pid) print nothing; the one possible writer was
  `QPID=$$(cat $$PIDF)` if the pidfile vanished between the `-f` test and
  the `cat`; now `cat $$PIDF 2>/dev/null`. `QEMU_KILL_DIR`,
  `GUI_KILL_ALL` and `VOCABS_KILL_ALL` are loops over `QEMU_KILL` and add
  no output.
- Static check `tools/check_kill_traps.py`, wired into `make test` as
  `test-kill-traps` (like `test-port-inventory`): every trap whose action
  names a kill macro must list PIPE; fails if none are found. Red on the
  committed Makefile: `kill traps with PIPE: 0/31`, exit 1. After the fix:
  31/31, exit 0. test-make-wiring 48/48.
- strace reproduction with PIPE in the list (silent action, then `touch
  FLAG`): the shell takes `SIGTERM`, `write(2, "Terminated\n") = -1 EPIPE`,
  exactly one `SIGPIPE`, no further write, then `exit_group(143)` /
  `exited with 143`: the trap ran to completion (FLAG created) and the
  shell was not killed by the signal.

### 7.1 Gate predictions (before the runs; image `5fdfb315…`, not rebuilt)

- Real-recipe red (E2 shape) x3: each **cleared**, no booted QEMU, no
  pidfile left.
- test-meta in full: exit 0; 26/26, 11/11, 21/21, 20/20, 17/17, 19/19;
  DICT MARGIN lines unchanged.
- make -k test: only test-xhci red; test-kill-traps passes.

The launch window (R1, about 1-2 ms per launch, E1) is queued and not
fixed here (owner ruling).

### 7.2 Gate results (Makefile `9323d5ff…`, check `b6cdde59…`, image `5fdfb315…`)

- **Real-recipe red, after the fix: 3/3 cleared** (trials 4-6, each run
  from a job-control shell, `$-` = `hmtBc`, the same conditions as the red;
  the wrapper printed `Terminated`, i.e. the pipe's readers died again):

  | trial | booted QEMU up | gone | pidfile left |
  |---|---|---|---|
  | 4 | 147.29 s | 181.03 s, with the recipe | none |
  | 5 | 147.25 s | 181.06 s | none |
  | 6 | 147.27 s | 181.00 s | none |

  Trials 1-3 (also clear) do NOT count: they ran inside a non-interactive
  script (job control off), where `grep` and `tail` stay outside timeout's
  process group and the pipe never loses its reader, so they would have
  cleared without the fix.
- test-kill-traps: 31/31 (red 0/31 on the committed Makefile).
- test-meta in full: exit 0, 1,905 s; 26/26, 11/11, 21/21, 20/20, 17/17,
  19/19; DICT MARGIN lines unchanged (66,388 / 39,228 / 39,228 / 39,204 /
  39,228 / 39,228).
- make -k test: only test-xhci red (MAKE_TEST_EXIT=2, 2,863 s);
  `kill traps with PIPE: 31/31`; test-make-wiring reports
  `test-kill-traps wired into test:`; census 429 across 27 suites
  (baseline 429); check-sync OK.
- No QEMU or pidfile left after any run.
