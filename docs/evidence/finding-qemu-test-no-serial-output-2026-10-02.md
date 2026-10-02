# FINDING — QEMU vocab tests reach no serial prompt, produce zero output, and hang (2026-10-02)

Recorded, not diagnosed (owner: defer until the kill-by-PID conversion lands).
This is the second, separate question split off from
`finding-harness-pkill-cross-worktree-2026-09-30.md`: that one was *how a hang
orphans a QEMU and wedges the suite*; this one is *why the test hangs at all*.

## Observed

`tests/test_xhci.py` and `tests/test_pci_bar.py` connect to their QEMU's
serial port successfully, then receive **zero bytes** and loop on the recv
until killed:

- `test_xhci.py` against an unmodified-arg QEMU: **3/3 hang**, each killed at
  60s, each log empty (differential probe, 2026-10-02).
- A full `make test` on a quiet machine (load 1.46, 0 other QEMU) wedged at
  `test-xhci` until the 20-min cap.
- `test-pci-bar`, converted, hung the same way (killed at its 90s budget).
- The 2h vocab-stage wedge (`test_driver_vocabs`) has the same shape.

**Yet both passed earlier the same day** — the firstboot merge-verify run
(`661486c`, "All tests passed!") and the first batch-1 run both ran *through*
`test-xhci` and `test-pci-bar` on the same image (combined `17e7da0f`). So it
is timing / environment dependent, **not** a deterministic break from any
image or code change. The THRU range is derived (`catalog_layout.py`), so the
catalog shift is not the cause.

## Why it hangs for ~20 minutes, not seconds

The per-operation timeouts in the scripts (`test_xhci.py`: 10s connect, 2s
recv) are **not** a test timeout. A hundred individually-timely 2s recvs that
each return nothing is a 20-minute hang built entirely out of compliant
operations. The read loop is unbounded in aggregate.

## Mitigation already shipped (separate change)

`TASK_HARNESS_KILL_BY_PID` §3b: each converted recipe wraps its test in
`timeout $(T_<NAME>)`. This converts the hang into a **bounded fast fail** with
clean teardown (trap kills the QEMU, no orphan, no held image lock) — verified
(H7). It does **not** make a no-output test *pass*; it stops the wedge.

## Not diagnosed — candidates for the red-first gate when this is opened

The specific signature to explain is **zero bytes, not a partial capture** —
the test connects but ForthOS emits nothing. Candidates, none investigated:

- QEMU running without KVM (TCG software emulation) booting far slower than
  the recipe's `sleep 2`, so the test connects before ForthOS reaches `ok`.
- `qemu-xhci` + `usb-kbd` enumeration timing (xHCI only — but `test-pci-bar`
  uses `intel-hda`, so a shared cause is more likely than a device-specific
  one).
- Machine contention at test time (the earlier passes vs later hangs correlate
  loosely with a busy vs quiet machine, but the quiet-machine run also hung).
- A boot regression that only manifests under some timing.

**Owed red-first:** capture `combined.img`'s serial boot directly
(`-serial file:…`, no test client) and check whether it reaches `ok`, and how
long it takes, to separate "ForthOS did not boot" from "the test connected too
early." Open this with its own gate once the conversion lands; starting it
mid-refactor turns a bounded mechanical task open-ended.

## Status

OPEN, deferred (owner, 2026-10-02). Blocks a *green* `make test` (the suite
now fails fast at `test-xhci` instead of wedging), so it also gates the H4
"green between batches" check for the remaining kill-by-PID batches — see that
task's §6.
