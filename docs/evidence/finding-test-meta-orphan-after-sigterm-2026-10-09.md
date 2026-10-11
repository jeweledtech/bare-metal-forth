# FINDING: a test-meta QEMU outlived a SIGTERM to its recipe (2026-10-09)

Against TASK_HARNESS_KILL_BY_PID. Not a SIGKILL, so not the expected H3 case.

**CORRECTED 2026-10-10: the launch-window explanation below is WRONG.**
See `docs/TASK_TEST_META_ORPHAN_RACE.md`. The real mechanism, observed:
the run was `timeout 1800 make test-meta 2>&1 | grep ... | tail -12` from
a shell with job control on, so `grep` and `tail` were in timeout's process
group and died with its SIGTERM. The fixture died of SIGTERM; the recipe
shell (`/bin/sh`, dash) then wrote `Terminated` to its stderr, the dead
pipe, got EPIPE and was killed by SIGPIPE before its TERM trap could run
(and a shell killed by a signal runs no EXIT trap). Reproduced 3/3 on the
shipped recipe with a QEMU that had been up 34-36 s; the same run with the
pipe's readers ignoring TERM cleared; seen directly with strace. The launch
window exists but is about 1-2 ms per launch, and is queued separately.
Fixed by adding PIPE to every kill trap (same date).

## Observed

- Run: a regression sequence started `timeout 1800 make test-meta` (no `-s`,
  no `-k`, no `--foreground`). At 1,800 s coreutils `timeout` sent **SIGTERM**
  to its process group. The recipe was in its last fixture, `test_meta_does`.
  The run's output was filtered to `Terminated`, so it shows no more than that.
- Afterwards a QEMU held `build/test-meta.d/meta-does-booted.pid` (the
  fixture's second, "booted kernel" QEMU) and ran for 1 h 30 min, through a
  whole `make -k test`, until removed with `qemu_pid.kill_pidfile`.
- Its age at discovery (1:30:53) against the `make -k test` that followed
  (1:30:00) puts its start within about a minute before the SIGTERM.
- No later run cleared it: only the test-meta recipe's pre-clean covers
  `build/test-meta.d`, and nothing ran that recipe again (`make test` does not
  include test-meta).

## Experiment

`setsid timeout 3000 make test-meta META_FIXTURES=test_meta_does`; waited
until `meta-does-booted.pid` named a live QEMU (145 s), then 15 s more; sent
SIGTERM to the process group as `timeout` does on expiry. Result: make exit
143, the booted QEMU gone, no pidfiles left. So the recipe trap clears a
**settled** booted QEMU on SIGTERM. (Also seen the same day: test-install's
single QEMU was cleared when its run was stopped with SIGTERM.)

## ~~Remaining explanation (reasoned, not reproduced)~~ WRONG, see the correction at the top (2026-10-10)

~~A launch-window race in `test_meta_does`: the booted QEMU is started with
`-daemonize`; its pre-daemon parent is in the recipe's process group, the
daemon child is not (setsid). If SIGTERM lands during QEMU start-up, the
parent dies, the trap's `QEMU_KILL_DIR` runs, and only then does the daemon
write its pidfile: the trap finds nothing to kill. The timing above fits;
the race itself was not reproduced.~~

## Consequence for 2026-10-09 results

The orphan ran alongside the whole `make -k test` of that sequence (which
also hit its outer 5,400 s limit, killing test-install mid-run): those
results are void and must be rerun. Everything that ran before it existed
(test_log_restore, test_log_validation, both dry runs, test_ahci_blk_writer,
test_ahci_blk_reader) and everything after its removal is unaffected.

## Not fixed here (superseded 2026-10-10: fixed by PIPE in every kill trap; the candidates below addressed the wrong mechanism)

Candidate fixes for the owner: a post-trap sweep that re-checks the pidfile
directory after a short wait; or the fixture writing its pidfile path before
launch and the trap waiting for a launching QEMU to finish start-up.
