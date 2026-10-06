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
`test-xhci` and `test-pci-bar` on the same image (combined `17e7da0f`). No
image or code change explains it: the guest side is byte-identical to the
green run (see **Measured**, below), and the THRU range is derived
(`catalog_layout.py`), so the catalog shift is not the cause either.

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

## Measured 2026-10-02 — the guest boots fine (host-side fault)

Two discriminators were run before guessing (the earlier "environment /
timing-looking" phrasing was a characterization that had not been measured —
the same flag-not-reality error this project keeps catching):

1. **Did the image change?** No. Current on-disk `combined.img`,
   `combined-ide.img`, and `bmforth.img` are byte-identical to the hashes
   recorded when these tests passed this morning (combined `17e7da0f`, bmforth
   `b9593319`). The guest side is constant; the fault is host-side.
2. **Does the guest boot?** Yes. A minimal `-serial file:` boot of
   `combined.img` (no test client, no monitor, no pidfile, no device models)
   produced 89 bytes — the banner and the `ok` prompt — within ~12s:
   `Bare-Metal Forth v0.1 … / Type WORDS … / ok`.

So this is **outcome #1** of the capture: ForthOS boots to `ok`; the zero-byte
hang is in **how the test connects to / reads from the serial port**, not the
guest. "Guest never boots" and "boot regression" are ruled out.

**Leading suspect (reasoned, not yet measured): the TCP serial discards the
banner.** The recipes use `-serial tcp::PORT,server=on,wait=off` (`tcp:127.0.0.1:PORT` since 4c), which boots
immediately and does **not** buffer output produced before a client connects.
The guest prints banner + `ok` within ~1–2s; the test `sleep 2`s, then
connects. If the banner is emitted before the connect, it is gone, and the
test — if it reads expecting the banner/prompt first — then blocks on an idle
`ok` prompt with nothing to read: **zero bytes, until killed.** That this is a
connect-ordering race (stable within a machine-state window, flips when boot
speed changes) is consistent with "green this morning, 3/3 red now" without
being generic "flakiness."

**Discriminator to confirm when opened:** connect a client to the TCP serial
*before* the guest boots (or capture with a pre-connected reader) and check
whether the banner arrives. If it does, the fix is in the test's
connect/read ordering (connect-before-boot, or a read that tolerates a missing
banner) rather than lengthening `sleep 2`.

## Status

OPEN, deferred (owner, 2026-10-02). Blocks a *green* `make test` (the suite
now fails fast at `test-xhci` instead of wedging), so it also gates the H4
"green between batches" check for the remaining kill-by-PID batches — see that
task's §6.
