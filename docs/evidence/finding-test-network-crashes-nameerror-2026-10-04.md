# FINDING — test-network crashes on a NameError 5s in; the NE2000 network test measures nothing (2026-10-04)

Recorded against master (`9eacc8b`). Not fixed here; queued as its own task
right after the kill-by-PID .py step (TASK_HARNESS_KILL_BY_PID §5, 4a).

## Observed

`make test-network` fails about 5 seconds in, every run:

```
Running NE2000 network test...
Starting QEMU pair...
Traceback (most recent call last):
  File "tests/test_ne2000_network.py", line 220, in <module>
    blocks_b = start_qemu_pair(
  File "tests/test_ne2000_network.py", line 114, in start_qemu_pair
    return blocks_b
NameError: name 'blocks_b' is not defined
make: *** [Makefile:603: test-network] Error 1
```

`start_qemu_pair` never assigns `blocks_b`. It launches both QEMUs (A
listens, B connects) and then raises before any check runs. **No NE2000
network check has run**: zero assertions, not a red result.

## The old recipe orphaned two QEMUs per run

The crash happens after both `-daemonize` launches and before the script's
`cleanup()`, and the old recipe had no cleanup of its own. Measured on master
(the py-a baseline, 2026-10-04): after the failure two qemu-system-i386
processes were still running, holding this tree's `build/combined.img`,
`combined-ide.img` and the `.b` copies. They were removed by verified PID.

After the kill-by-PID conversion (py-a), both QEMUs get pidfiles in
`build/test-network.d`, and the recipe trap clears them even though the
script still crashes. The crash itself is unchanged.

## Why it was not among the known reds

`test-network` is **not a prerequisite of `make test`**. It is on the
Makefile's exempt list: "test-network is separately DEAD-PENDING-REPAIR,
broken since 2026-08-30". So no full run ever reported it.

Two dates, not reconciled here: git shows `blocks_b`'s assignment
(`blocks_b = BLOCKS + '.b'`) removed in `22aefd9` (2026-04-13, "Combined
image: kernel+blocks in one file") while `return blocks_b` stayed. The
Makefile dates the breakage to 2026-08-30. That may be when it was noticed,
or a separate fault. Check both when fixing.

## Queued (TASK_HARNESS_KILL_BY_PID §5, 4a)

1. The current crash is the failing case: the test must reach its NE2000
   checks.
2. Fix `start_qemu_pair` (restore or replace `blocks_b`; check what else
   22aefd9 changed).
3. Set the real `T_NETWORK` from a measured run (now 300s, provisional,
   since the full runtime is unknown), and decide whether test-network
   leaves the exempt list.
