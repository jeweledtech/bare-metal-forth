# TASK 4b — bounded reads instead of fixed sleeps; the 13 bare-`except:` scripts (plan, 2026-10-06)

Branch `bounded-reads` from master `127baa3`. Queue position: after 4c,
before the LOG-HARNESS validation pass (TASK_HARNESS_KILL_BY_PID §5).
No script is edited before the owner approves this plan.

## 1. Why

Most test scripts send a command, `time.sleep(wait)`, then read until a
1-second quiet, so every exchange costs at least `wait + 1` seconds
whatever the guest does. `make -k test` takes about 2h07m (seven full runs,
2026-10-03..06, 1h55m-2h07m). test_install.py alone makes 442
`send(..., wait)` calls (~35 min, measured 2026-10-04). Counted 2026-10-06
over the recipe-run scripts: 51 scripts; 46 sleep before reading; only
test_pci_bar.py and test_xhci.py use `tests/serial.py`.

`tests/serial.py`'s `send_expect` is already bounded in aggregate, but
without an `expect` it still waits a fixed 1s settle plus a 2s quiet gap.
Bounding is not enough: the read must end when the reply is **complete**,
i.e. at the guest's prompt.

## 2. Timing baseline (before any change)

The speedup is a measured number, not an estimate.

- **B1, per target, whole suite.** One full run on `127baa3`, each `test:`
  prerequisite run as its own `make <target>` in `test:` order, with its
  wall time and exit code logged. Same reds as `make -k test` expected
  (the known five); any other red stops 4b and is reported.
- **B2, repeats for the targets to be converted.** Each converted target run
  again before its change, n=3 (test-install n=2, about 35 min each);
  median and range reported. The after-runs use the same n, the same
  machine, idle (one harness at a time).
- Recorded in §8 with `HEAD`, script sha256 and QEMU version.

## 3. The conversion

**3a. Terminator, measured first (step 0).** Before writing the helper,
record the exact bytes the guest sends after: a normal command, a word that
prints nothing, an error (`?`), `ABORT"`, a multi-block `THRU`, a command
that prints its own `ok` text, and a blank line. The helper's end-of-reply
rule comes from that record, not from an assumption.

**3b. One shared helper.** `tests/serial.py` gets
`send_until_prompt(sock, cmd, budget)`: send, read until the reply (after
the echo) ends with the measured prompt, or the budget runs out, or the peer
closes. It returns the reply and how the read ended (`prompt`, `budget`,
`closed`). It catches only `socket.timeout`/`OSError`, never a bare
`except:`.

**3c. Per script, minimal diff.** Each script keeps its own `send(cmd,
wait)` signature, so the hundreds of call sites do not change; only the body
changes. `wait` becomes part of the budget (an upper bound, not a sleep).
Fixed sleeps before the first connect become `connect_and_sync`. Check
names, counts and logic do not change.

**3d. Exceptions are explicit.** A command whose useful output arrives
after its prompt (network receive, timer reads, reboots, anything
asynchronous) keeps a deliberate wait, passed explicitly and listed in §8
with the transcript line that shows why. Found by gate G1, not guessed.

## 4. Gates per converted script

- **G1, transcript equivalence.** For every command: the reply before (old
  `send`, recorded through a one-off trace copy of the old function, not
  committed) and after (the helper's trace) must be identical. A
  difference is either an exception for §3d or a defect.
- **G2, same checks.** Same check count and the same PASS/FAIL for every
  check name as the baseline run.
- **G3, no silent budget endings.** Every read ends at the prompt, except
  the listed §3d exceptions.
- **G4, timing.** n runs after, against B2: median before/after and the
  speedup, per target.
- **G5, SIGINT.** The rewritten `send` must not swallow SIGINT: one aimed
  SIGINT to the test (`tools/sigint_sweep.py --to-test <case>`) ends it in
  0-1s by KeyboardInterrupt.

## 5. The 13 bare-`except:` scripts

26 sites, 2 per file (counted 2026-10-06, `git ls-files '*.py'`). Each gets
its own aimed single-SIGINT red (before: swallowed, the script runs on) and
green (after: KeyboardInterrupt, exit 0-1s), with SigIgn shown first, via
`tools/sigint_sweep.py --to-test`. The fix is `except:` ->
`except Exception:` (or the 3b helper where that script's `send` is being
rewritten anyway).

| Script | Run by | Starts its own QEMU | Sweep case today |
|---|---|---|---|
| test_memdisk_blk_writer.py | test-memdisk | yes | `test-memdisk` |
| test_ahci_blk_reader.py | nothing (direct) | yes | `script/test_ahci_blk_reader` |
| test_ahci_blk_writer.py | nothing (direct) | yes | `script/test_ahci_blk_writer` |
| test_blk_writer_vector.py | nothing (direct) | yes | `script/test_blk_writer_vector` |
| test_persist_quick.py | nothing (direct) | yes | `script/test_persist_quick` |
| test_catalog_registry.py | nothing | no | none |
| test_dump.py | nothing | no | none |
| test_ne2000.py | nothing | no | none |
| test_pci_enum.py | nothing | no | none |
| test_pit_timer.py | nothing | no | none |
| test_ps2_keyboard.py | nothing | no | none |
| test_ps2_mouse.py | nothing | no | none |
| test_vga_graphics.py | nothing | no | none |

The last eight connect to a QEMU someone else started. `tools/sigint_sweep.py`
gets a **fixture case kind**: start a QEMU like the test-vocabs fixture line
(on 127.0.0.1, by pidfile, with the device each script needs, e.g. ne2k_pci
for test_ne2000.py), run the script against it, aim the SIGINT, stop the
fixture by pidfile. No recipe runs these eight, so whether they pass today
is unknown: each one's plain result is recorded before its red, and the red
needs only that it reaches a blocking `recv`.

## 6. Order

0. Terminator probe (3a).
1. B1 baseline full run; B2 repeats for test-install.
2. test-install: G1-G5.
3. The other converted scripts, in order of B1 time, each with its own
   B2 and G1-G5. Which ones are converted is decided from B1 (where the
   minutes are), listed in §8 before they are touched.
4. The 13 bare-`except:` scripts (§5).
5. Full `make -k test`: only the known five red, and the total time
   against B1.

Report before each merge, as before.

## 7. Not in 4b

Changing what any test checks; lowering the `T_*` budgets (they can be
re-measured after 4b, separately); the eight unrun scripts' own failures,
if any (recorded, not fixed).

## 8. Results

(filled as the steps land)
