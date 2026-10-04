# FINDING — test-cortexm fails 2/5 on master; its ARM QEMU launches are never exercised (2026-10-04)

Recorded against master (`488d182`). Not fixed here. Owner to sequence.

## Observed

`test-cortexm` (not in `make test`) fails before and after its kill-by-PID
conversion, with the same four failures:

```
--- Phase 1: Build on x86 ---
  PASS: All vocabs loaded on x86
  PASS: META-COMPILE-CORTEXM-BOOT done
  FAIL: Image size > 0 -- got: -1900006918
--- Phase 2: Extract binary ---
  FAIL: T-IMAGE address obtained -- got: -1899983144
  FAIL: Kernel binary extracted
FAIL: No kernel to boot
Passed: 2/5
```

- Before: baseline on `35c6fe6` (old pattern-kill recipe), 2/5.
- After: the batch-3b gate run (normal and H3 rerun), 2/5. The FAIL lines
  match the baseline exactly.

The metacompiler reports a garbage image size (a large negative number), so
there is no kernel to extract and the script exits before Phase 3.

## What that leaves untested

Phase 3 boots the Cortex-M33 kernel on `qemu-system-arm` (mps2-an505). The
script has two ARM launch sites on BOOT_PORT (a `subprocess.run` and a
`Popen`). Batch 3b gave each its own pidfile (`boot-run`, `boot`). **Neither
launch has run since**, so these are untested:

- that both ARM launches start with `-pidfile` and write it;
- `kill_qemu(BOOT_PORT)` (pidfile kill) and the recipe's `QEMU_KILL_DIR`
  cleanup for them;
- H2/H3 for the ARM QEMU. Batch 3b covered only the x86 builder.

The widened QEMU_KILL guard *is* shown on a non-i386 binary elsewhere:
test-arm64-boot's aarch64 QEMU (H2 clean), and a real aarch64 orphan holding
`build/test-arm64-boot.d/boot.pid`, killed by the next run's pre-clean.

One more thing to check once Phase 3 runs: the first ARM call is a
`subprocess.run` with no `-daemonize`. Given a real kernel it may block
until that QEMU exits. The `Popen` that follows is the evident real launch.

## Not fixed

For the owner: fix (or retire) META-COMPILE-CORTEXM-BOOT's image-size
result, then rerun the batch-3b H2/H3 gates for the ARM role.
