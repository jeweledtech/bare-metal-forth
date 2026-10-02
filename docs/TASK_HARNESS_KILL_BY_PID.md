# TASK: Kill QEMU by PID, not by pattern

**Owner:** JeweledTech · A Jolly Genius Inc. company
**Status:** READY — mechanical, wants a quiet machine and one session
**Date:** 2026-10-02
**Repo:** `jeweledtech/bare-metal-forth`
**Source finding:** `docs/evidence/finding-harness-pkill-cross-worktree-2026-09-30.md`

---

## 1. Why now

This is the last open item from the finding. Two of its three fixes landed
(per-worktree `TEST_PORT_BASE`, the `docs/CLAUDE.md` broad-kill replacement);
the 55 Makefile recipes still tear down by name pattern.

It is being done now because the machine is quiet and one session owns the
tree. A wide mechanical change across every test recipe is exactly the work
that cannot be done safely with concurrent sessions — and the failure mode it
removes is what cost most of 2026-09-30:

- an orphaned QEMU held a monitor port and failed the next run at launch;
- an orphaned QEMU held the **write lock on `build/bmforth.img`**, which the
  port fix does not address at all;
- a pattern kill reached a process in another tree;
- each of those surfaced as a red `make test` on a tree whose code was fine.

The cost is not the lost minutes. It is that a red suite stops meaning
"you broke something."

---

## 2. Scope

| Surface | Count | Change |
|---|---|---|
| `Makefile` recipes using `pkill -9 -f "[q]emu.*<port>"` | 55 | kill by PID from a pidfile |
| `-daemonize` launches without `-pidfile` | 17 | add `-pidfile` |
| `tests/iv_roundtrip_test.py:13`, `tests/test_meta_b6b.py:133`, `tests/synced_revert*.py` | 3 | kill the `Popen` handle they already own |
| `TEST_PORT_BASE` | — | done (`65a5cdd`), no change |

Out of scope: the three translator corpus suites, anything under
`tools/translator/`, and `docs/CLAUDE.md` (already corrected).

---

## 3. The pattern — already proven

`test-firstboot` (merged at `661486c`) is the reference implementation. It was
verified across normal exit, SIGINT, SIGTERM and SIGKILL on 2026-09-29. Copy
its shape; do not invent a second one.

```make
QEMU_KILL = if [ -f $$PIDF ]; then kill -9 $$(cat $$PIDF) 2>/dev/null; rm -f $$PIDF; fi

test-firstboot: $(COMBINED)
    @PIDF=$(BUILD)/firstboot-lan.pid; $(QEMU_KILL); \
    trap '$(QEMU_KILL)' EXIT INT TERM HUP; set -e; \
    $(QEMU) ... -daemonize -pidfile $$PIDF; \
    sleep 2; \
    python3 tests/test_firstboot.py ...
```

Four properties, all load-bearing:

1. **One shell per fixture.** Make runs each recipe line in its own shell, so a
   `trap` set on line 1 is gone by line 2. The recipe must be a single
   continued shell — this is the actual work, not the kill line.
2. **Pre-clean before launch.** SIGKILL cannot be trapped, so a previous run
   killed hard leaves both a QEMU and its pidfile. Clearing the pidfile's PID
   first is what makes the *next* run succeed.
3. **Pidfile under this tree's `build/`.** A tree can then only ever kill its
   own QEMUs, by construction rather than by careful pattern-writing.
4. **Fail the recipe if the launch fails.** A QEMU that fails to start must
   fail the recipe (via `set -e` or `|| exit 1`), not fall through to a test
   that then times out mysteriously.

### 3a. Generalize the helper

Promote `FB_KILL` to one shared `QEMU_KILL` used by every recipe, so there are
not 55 copies to keep correct. Name pidfiles after the target
(`$(BUILD)/<target>.pid`, and `<target>-<fixture>.pid` where a recipe runs
more than one).

### 3b. The test invocation carries its own timeout

The per-operation timeouts inside the test scripts (`test_xhci.py`: 10s
connect, 2s recv) are **not** a test timeout: a hundred individually-timely
recvs is a twenty-minute hang built entirely out of compliant operations. The
read loop is unbounded in aggregate — which is why the xHCI and vocab stages
both wedge the same way, with different scripts.

Fix it in the conversion, not in the scripts. Every converted recipe wraps its
test invocation in `timeout $(T_<NAME>) python3 tests/...`. A hard kill at `N`
seconds propagates cleanly: `set -e` trips, the `trap` fires, `QEMU_KILL` kills
the QEMU by pidfile — no orphan, no held image lock, and the recipe fails in
bounded time instead of hanging. One word per recipe fixes the whole class; a
script-level timeout only ever fixes the one script you patch. Pick `N` from
the recipe's observed runtime with headroom, and keep it as a named
`T_<NAME>` variable so the budgets are greppable and tunable in one place.

### 3c. Connect before the guest boots (the banner race)

A second defect sits upstream of the timeout, found running §3b down
(`docs/evidence/finding-qemu-test-no-serial-output-2026-10-02.md`). The recipe
launches QEMU with `-serial tcp::PORT,server=on,wait=off`, which boots
immediately and does **not** buffer serial output produced before a client
connects. The guest prints its banner at ~0.25s; the test connects ~2s later
and reads; on a **fast** QEMU start the banner is already gone and the test's
banner-drain blocks on an idle `ok` → zero bytes → hang. It is a
**startup-speed race**: a busy machine starts QEMU slowly enough that the
banner lands *after* the connect (green); a quiet/fast machine loses it (red).
Measured: banner at 0.25s, image byte-identical across green and red.

The fix is to make the guest **wait for its reader** — `-serial
tcp::PORT,server=on` (drop `wait=off`), so QEMU holds the CPU until the test
attaches and the banner cannot be emitted into an empty socket. Verified in
isolation to deliver the banner regardless of connect timing; a converted
recipe reached `interpreter alive` + several checks where it had hung 3/3.

**Open (not settled, verify in an exclusive worktree):** `server=on` (wait)
**deadlocks with `-daemonize`** — QEMU will not detach until a client connects,
and the client connects *after* the launch line. So the launch must change
shape (background `&` + pidfile, or another mechanism that attaches a reader
before boot). This is the "conversions may need to change shape" case, and it
**cannot be verified while another session runs tests in this worktree**: the
shared `build/` images collide (the very class §1 is about), which
non-deterministically kills the guest mid-test and masquerades as a fix bug.

---

## 4. The gotcha that will bite during conversion

Collapsing a multi-line recipe into one shell **changes error semantics.**
Today make stops at the first failing line. In a single continued shell,
everything after a failure still runs unless you make it not.

Every converted recipe must either `set -e` at the top of its shell or carry
explicit `|| exit` on each step that matters. A recipe that silently continues
past a failed build and then "passes" its test is a worse outcome than the
problem being fixed.

**`set -e` has blind spots.** It does *not* fire for a command inside an `if`
condition, on the left of `||`/`&&`, or (in default bash) for a non-final
command in a pipeline. Batch 1's recipes (`test-xhci`, `test-pci-bar`) are
linear, so `set -e` holds there. For each of the 17 in batch 2, check for
those shapes as you convert; where one appears, add an explicit `|| exit 1` on
that step rather than trusting `set -e`. A failed step sailing past silently is
exactly what this section exists to stop, and in those shapes it would do so
while *appearing* guarded.

Verify this per batch, not at the end.

---

## 5. Order of work

Convert in batches, running `make test` between them. Fifty-five recipes
changed in one pass with no intermediate verification is how a clean change
becomes an unbounded debugging session.

1. **Helper + two recipes — DONE (`058ea52`).** Added `QEMU_KILL`; converted
   `test-xhci` and `test-pci-bar`. Both passed in a full run (before the
   pre-existing xHCI wedge); the conversion was exonerated by a differential
   probe (`test_xhci.py` hangs 3/3 against unmodified-arg QEMU — the hang is
   the test, not the recipe). Timeout (§3b) backfilled onto both so the
   pattern is uniform from the start. **Still owed: §3c (connect-before-boot)**
   — until it lands, a fast machine loses the banner race and both recipes
   fail (bounded by §3b, not hanging). Verification is blocked while another
   session runs tests in this worktree; finish in an exclusive worktree.
2. **The `-daemonize` seventeen.** These are the ones that can orphan. Batch of
   ~6, `make test` between.
3. **The remaining recipes.** Mechanical once the pattern is set.
4. **The three `.py` files.** Each already holds a `Popen`; kill that handle in
   a `finally`, drop the `pkill`.
5. **Optional, recommended:** have a recipe refuse to start when its serial
   port is already bound (`ss -tlnp`), so a collision fails loudly instead of
   hijacking or killing. Costs one check, removes the remaining ambiguity.

---

## 6. Gates

| # | Gate |
|---|---|
| H1 | **Red first.** Two QEMUs running, one from a second checkout at a different base. Run a converted recipe to completion. Before the change, a pattern kill reaches the other; after, it must not. Prove the red fails on today's tree before trusting the green. |
| H2 | No orphan after normal exit, SIGINT, or SIGTERM — for every converted recipe, not just a sample. |
| H3 | After SIGKILL, the next run's pre-clean clears the orphan and starts cleanly. |
| H4 | `make test` green after every batch. Read `MAKE_TEST_EXIT` from the log, not the harness's exit code. |
| H5 | A deliberately failing step inside a converted single-shell recipe fails the recipe (§4). |
| H6 | `grep -c '^\t.*pkill' Makefile` → 0. Scoped to tab-indented recipe lines so it catches pattern kills in recipes and ignores the finding's filename cited in comments (a legitimate citation). Apply the same scoping to the 3 `.py` files — no `pkill` *invocation* remains; a citation in a comment is fine. |
| H7 | **Red first.** A deliberately-hung test (a recipe whose test invocation blocks forever) must fail its recipe **within `N` seconds**, leave **no** orphaned QEMU, and **not** hold the image lock. Prove the hang-to-20-min red on the pre-timeout recipe first, then the bounded-fail green after. `test-xhci` is a live instance of the hung case today. |
| H8 | Every converted recipe's test invocation carries `timeout $(T_<NAME>)` with a named budget. `grep -c 'python3 tests/' Makefile` equals the count of those lines also matching `timeout $(T_`. |
| H9 | A converted recipe must pass against a deliberately **slowed** guest **and** a deliberately **fast** start (§3c). The race is lost on the *fast* side, so a slow-only gate would have shipped green all week; both twins are required. |
| H10 | A converted recipe must **fail within its budget** when QEMU is prevented from starting at all (port already bound, or a bad `-drive`), proving `-daemonize`'s post-init return + `|| exit 1` still report a dead *launch* — rather than the test connecting to nothing and hanging on a guest that never came up. |

---

## 7. Verification traps already learned

Both cost a diagnosis cycle on 2026-09-30/10-01. Do not re-derive them:

- **`make -n test` is not a valid proxy for `make test`.** The corpus-absent
  gate shells out to `make <subtest>`; under `-n` every child exits 0 without
  running, which reads as the gate's own failure condition. It reports a red
  that does not exist.
- **The harness's exit code is not make's.** A trailing `tail` or `echo` in the
  wrapper returns 0 while `make test` exited 2. Capture `MAKE_TEST_EXIT` into
  the log and read the log.

---

## 8. What this does not fix

The image write lock is reduced, not eliminated. Traps mean a killed run no
longer leaves a QEMU holding `build/bmforth.img`, which was the observed
failure — but two *concurrently running* suites in the same working tree still
collide on that file regardless of ports or pidfiles. Separate worktrees have
separate `build/`, so the per-worktree discipline remains the answer there.

Worth one line in the finding once this lands, so the next reader knows which
half each fix bought.
