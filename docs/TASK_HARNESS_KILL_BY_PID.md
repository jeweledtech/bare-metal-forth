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
| `-daemonize` launches without `-pidfile` | 15 recipes (recount 2026-10-03; 17 counted launch lines, and test-vocabs/test-gui launch in a loop) | add `-pidfile` |
| Tracked `.py` files invoking `pkill -9 -f "[q]emu.*<port>"` (census 2026-10-02, `git ls-files '*.py' \| xargs grep -nE '^[^#]*pkill'`): `eviction_flush_test.py:25`, `iv_roundtrip_test.py:13`, `test_ahci_blk_reader.py:47`, `test_ahci_blk_writer.py:35`, `test_arm64_boot.py:125`, `test_asm_vocab.py:88,128,179`, `test_blk_writer_vector.py:27`, `test_carrier_write_safe.py:45,59,106`, `test_g6_chain.py:542`, `test_memdisk_blk_writer.py:39`, `test_ne2000_network.py:198,203`, `test_persist_quick.py:12`, `test_shutdown.py:24`, `test_survey_layouts.py:170,240,524`, `test_vbr_boot.py:168,200` (all under `tests/`) | 15 files, 23 sites | kill by the PID the script launched; where it holds a `Popen`, kill that handle in a `finally` (not verified per file — check each) |
| `TEST_PORT_BASE` | — | done (`65a5cdd`), no change |

Out of scope: the three translator corpus suites, anything under
`tools/translator/`, and `docs/CLAUDE.md` (already corrected).

---

## 3. The pattern — already proven

`test-firstboot` (merged at `661486c`) is the reference implementation. It was
verified across normal exit, SIGINT, SIGTERM and SIGKILL on 2026-09-29. Copy
its shape; do not invent a second one.

**Do not copy the kill helper from `661486c`.** Its `FB_KILL` (and the first
`QEMU_KILL` derived from it) ran `kill -9 $$(cat $$PIDF)` unchecked: a stale
pidfile whose PID has been reused kills an unrelated process (shown red on
2026-10-02: a decoy `sleep` was killed and the recipe still passed 13/13).
Use the `QEMU_KILL` in the `Makefile`, which kills only a `$(QEMU)` holding
this tree's pidfile open, and see its comment for the two cases it refuses.
The recipe shape below is unchanged:

```make
QEMU_KILL = ...   # see Makefile; never the bare kill -9 $$(cat $$PIDF)

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
3. **Pidfile under this tree's `build/`, and verify before killing.** The
   pidfile path alone does not confine the kill: the PID it names can die and
   be reused. `QEMU_KILL` kills only if `/proc/PID/exe` is `$(QEMU)` and the
   process holds `$(CURDIR)/<pidfile>` open (gate H11).
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
linear, so `set -e` holds there. For each of the 15 in batch 2, check for
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

**Sequencing (owner, 2026-10-02).** Batch 1 (steps 1 below, plus
`test-log-harness` and `test-log-harness-nic`) lands on its own. Batches 2–3
and the `.py` files wait until LOG-HARNESS Phase 2.5 is underway. H6 is the
gate for the whole task, not for a batch. From here on, every new recipe that
launches QEMU uses `QEMU_KILL` from the start; none adds a `pkill`.

1. **Helper + two recipes — DONE (`058ea52`).** Added `QEMU_KILL`; converted
   `test-xhci` and `test-pci-bar`. Both passed in a full run (before the
   pre-existing xHCI wedge); the conversion was exonerated by a differential
   probe (`test_xhci.py` hangs 3/3 against unmodified-arg QEMU — the hang is
   the test, not the recipe). Timeout (§3b) backfilled onto both so the
   pattern is uniform from the start. **Still owed: §3c (connect-before-boot)**
   — until it lands, a fast machine loses the banner race and both recipes
   fail (bounded by §3b, not hanging). Verification is blocked while another
   session runs tests in this worktree; finish in an exclusive worktree.
2. **The `-daemonize` fifteen.** These are the ones that can orphan. Batch of
   ~6, `make test` between.
   - **2a: DONE (`bd2aee7`, 2026-10-03).** test-smoke, test-loops,
     test-abort, test-dict-bounds, test-phys-alloc, test-pci-typing. All
     gates per recipe: H1 red 6/6 on `cd5998a` (decoy QEMUs from another
     tree killed), then green; H11; H2 (exit 0-1s after the signal); H3;
     H5 early and late; H8. H4 `make -k test`: MAKE_TEST_EXIT=2 with only the
     known reds (xhci, pci-bar, and the untracked-file suites in a worktree).
   - **`timeout --foreground` everywhere.** Without it, `timeout` puts the
     test in its own process group, so a Ctrl-C to make never reaches it and
     the recipe runs out its budget first. All converted recipes use
     `timeout --foreground $(T_<NAME>)`.
   - **2b: DONE (`cba87aa`).** test-squote-laydown, -backstop0, test-flush,
     test-file-stream, test-integration. Same gates, all green. test-flush
     (not in `make test`) already failed 8/17 before conversion and fails the
     same 9 checks after.
   - **2c: DONE.** test-vocabs, test-gui (loops), test-install, and test-meta's
     one recipe-level launch. Each loop fixture has its own pidfile
     (`$(BUILD)/<target>-<fixture>.pid`). The pre-clean and the trap walk the
     full `*_TESTS_ALL` list; `*_TESTS` may name a subset and a fixture keeps
     its port. Gates cover every QEMU in the loops: H2 on each of the 13
     fixtures plus SIGINT at fixture 4 of a full run; H3 SIGKILL at each
     fixture, cleared by a run of a *different* fixture. test-meta's other
     five QEMUs are started by its .py scripts and stay with step 4.
   - SIGINT reaches the test under `--foreground`, but five scripts swallow
     it some of the time (a bare `except:` around `recv` catches
     KeyboardInterrupt): smoke_test.py, test_file_stream_helpers.py,
     test_flush_stress.py, test_editor.py, test_x86_asm.py. The trap still
     cleans up; only promptness suffers. Fix belongs with step 4.
3. **The remaining recipes.** Not mechanical after all: only one started its
   QEMU in the recipe.
   - **3a: DONE.** test-ahci-write: `&` + pkill → -daemonize -pidfile, with the
     "private test absent" SKIPPED check first. (No "vocab absent" check:
     ahci.fth is embedded, so without it the image build fails first.)
   - **3b: DONE.** test-vbr, test-g6, test-block-reload, test-arm64-boot,
     test-cortexm. Their **scripts** start the QEMUs, so recipe and script
     change together. The recipe sets `QPIDDIR=$(BUILD)/<target>.d`, exports it
     as `QEMU_PIDDIR`, and runs `QEMU_KILL_DIR` (QEMU_KILL over every `*.pid`
     there) at pre-clean and from the trap. Each script passes `-pidfile` for
     every QEMU it starts and stops it with `tests/qemu_pid.py`'s
     `kill_pidfile`; no script pkills any more. test-g6 keeps its graceful
     monitor `quit` first. `QEMU_KILL`'s exe check widened to any
     `qemu-system-*` (aarch64/arm); the pidfile-held-open check is unchanged.
   - Remaining pkill: only test-meta's 22 lines (its .py scripts), step 4.
4. **The 15 `.py` files (§2 census).** Kill the PID each script launched (its
   `Popen` handle in a `finally`, where it holds one), drop the `pkill`.
   - **test-meta: DONE.** Its five script fixtures (test_meta_compile, _b6,
     _boot, _b6b, _does; all private) start their QEMUs with -pidfile via
     tests/qemu_pid.py and stop them with kill_pidfile (private 039150d).
     The recipe keeps one pidfile dir, build/test-meta.d (fixture 1's
     pidfile moved into it), swept at start, after every fixture, and from
     the trap. META_FIXTURES may name a subset; a fixture keeps its port.
     With this, **no recipe pkills**: `grep -c '^\t.*pkill' Makefile` → 0
     (the Makefile half of H6).
   - Still to do in step 4: the .py files outside any converted recipe
     (§2 census, less those converted in 3b and here).

**Order after step 4:** 4a, then 4c, then 4b (owner, 2026-10-04).

4a. **test-network fix** (its own small task). It crashes on a NameError
   (`blocks_b` in `start_qemu_pair`) about 5s in, so no NE2000 check has run
   (finding-test-network-crashes-nameerror-2026-10-04). The current crash is
   the failing case. Then fix it, then set the real `T_NETWORK` from a
   measured run (now 300, provisional).

4c. **Refuse to start on a bound port** (§5 step 5, now required). Every
   QEMU recipe checks its ports when it starts and fails loudly with the
   port number if one is taken. Skipping a busy base when TEST_PORT_BASE is
   chosen is optional, a convenience on top: a base that is clear when
   chosen can be taken by the time a test runs, because host services start
   and stop. Motivation: on 2026-10-03/04 seven candidate worktree names
   landed on five busy bases (5400 x2, 5600 x2, 3000, 4000, 8000; held by
   the container runtime and velociraptor.service)
   (finding-test-port-base-collides-host-service-2026-10-02).

4b. **After the .py step: replace fixed sleeps with bounded reads.** Most test
   scripts send a command, `time.sleep()` a fixed 1–2s, then read until a
   2–5s timeout, so each check costs ~3–5s whatever the guest does. That is
   why `make -k test` takes about 2h (measured 2026-10-04: test-install ~35
   min for 454 checks, vocabs ~14, gui ~12, firstboot ~11, g6 ~10,
   squote-laydown ~9.5). Use the `tests/serial.py` pattern: read until the
   guest answers `ok`, with an overall budget. Start with test-install.
   Each script keeps its check count and results; only the wait changes.

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
| H6 | `grep -c '^\t.*pkill' Makefile` → 0. Scoped to tab-indented recipe lines so it catches pattern kills in recipes and ignores the finding's filename cited in comments (a legitimate citation). Apply the same scoping to the 15 tracked `.py` files of §2 (`git ls-files '*.py' \| xargs grep -lE '^[^#]*pkill'` → empty) — no `pkill` *invocation* remains; a citation in a comment is fine. |
| H7 | **Red first.** A deliberately-hung test (a recipe whose test invocation blocks forever) must fail its recipe **within `N` seconds**, leave **no** orphaned QEMU, and **not** hold the image lock. Prove the hang-to-20-min red on the pre-timeout recipe first, then the bounded-fail green after. `test-xhci` is a live instance of the hung case today. |
| H8 | Every converted recipe's test invocation carries `timeout $(T_<NAME>)` with a named budget. `grep -c 'python3 tests/' Makefile` equals the count of those lines also matching `timeout $(T_`. |
| H9 | A converted recipe must pass against a deliberately **slowed** guest **and** a deliberately **fast** start (§3c). The race is lost on the *fast* side, so a slow-only gate would have shipped green all week; both twins are required. |
| H10 | A converted recipe must **fail within its budget** when QEMU is prevented from starting at all (port already bound, or a bad `-drive`), proving `-daemonize`'s post-init return + `|| exit 1` still report a dead *launch* — rather than the test connecting to nothing and hanging on a guest that never came up. |
| H11 | **Red first.** A live non-QEMU PID placed in a recipe's pidfile survives a run of that recipe. Start a decoy (`sleep 987 &`), write its PID into the pidfile, run the recipe: the decoy must still be alive, the recipe must pass, and the pidfile must be gone. Red on `64aee8e` (decoy killed, exit 137, recipe still 13/13); green after the guarded `QEMU_KILL`. |

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

Three more for the signal gates (H2/H3/H11), learned 2026-10-02/03:

- **Never take a kill target from a daemonized QEMU's parent PID.** After
  `-daemonize` its parent is the subreaper (`systemd --user`), not the recipe
  shell. Killing that parent takes down the user session. Start make under
  `setsid`, record its PID, check that PID's command line and process group,
  and signal that group.
- **`kill -0` succeeds on a zombie.** A QEMU killed a moment ago still exists
  until it is reaped, so an immediate `kill -0` reads "alive". Read the state
  in `/proc/PID/stat` (`Z`, or no such file, means dead), or wait first.
- **A signal harness must not delete a recipe's pidfile, and must wait for
  make to exit between cases.** Deleting a live pidfile (`/proc/PID/fd` then
  shows `<path> (deleted)`) blinds the guarded `QEMU_KILL`, and the QEMU is
  orphaned.
- **An unanchored pattern kill matches more than QEMUs.** `pkill -f
  "[q]emu.*<port>"` matched a harness shell whose argv held a heredoc that
  mentioned `qemu-system-i386` and then the port, and killed it. Write
  harness scripts to a file and run `bash <file>`; wait on an exact PID via
  `/proc/<pid>`, since `pgrep -f` also matches the shell running it.
- **One harness at a time, and a refused launch must stop what it started.**
  Two overlapping harnesses (a surviving script plus a rerun, or a launch
  that gave up but left its make running) share ports, image locks and
  pidfiles, and every result in the overlap is invalid.
- **Before every merge to master, list what the merge would delete:**
  `git diff --name-status master <branch> | grep '^D'`. Confirm none of
  it is an ignored file present on disk. A branch that untracks a
  private-owned file deletes the working copy when master is checked out
  and fast-forwarded (it happened to tests/test_ahci_write.py on
  2026-10-04). If any is, move master with `git fetch . <branch>:master`
  from the branch instead, then re-verify the files on disk.

---

## 8. What this does not fix

The image write lock is reduced, not eliminated. Traps mean a killed run no
longer leaves a QEMU holding `build/bmforth.img`, which was the observed
failure — but two *concurrently running* suites in the same working tree still
collide on that file regardless of ports or pidfiles. Separate worktrees have
separate `build/`, so the per-worktree discipline remains the answer there.

Worth one line in the finding once this lands, so the next reader knows which
half each fix bought.
