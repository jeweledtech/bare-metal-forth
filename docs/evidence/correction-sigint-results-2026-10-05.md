# CORRECTION — SIGINT results in TASK_HARNESS_KILL_BY_PID (2026-10-05)

Every SIGINT gate in this task (H2, batch 1 to py-c) was run by a harness
script started as `bash <file>`, which launched make with
`setsid sh -c '... exec make <target>' &`. A background job of a
non-interactive bash starts with SIGINT and SIGQUIT ignored, and an ignored
signal stays ignored across exec. So in every gate run, make and the recipe
shell had SIGINT ignored. A terminal Ctrl-C does not look like that.

This doc records what f0fc329 said about it, why that over-corrected, what
each affected commit and finding claimed, and what stands after a SIGINT
sweep run with SIGINT deliverable (2026-10-05, branch
harness-killbypid-pyrest at `c4938d4`).

## Step 1: what f0fc329 said

A probe launched like the gate harness showed make with SigIgn `...06`
(SIGINT ignored), and a harness-style SIGINT to test-smoke's group did
nothing: the test ran to `Passed: 7/7`. The same target launched with
SIGINT reset to default stopped in 1s with `Error 130`. From that,
f0fc329's message and its §7 line said every earlier SIGINT gate "proved
nothing" and would be re-measured.

## Step 2: why that over-corrected

The conclusion covered every gate but came from one probe, on a target that
could not tell the two cases apart:

- test-smoke runs smoke_test.py, one of the five bare-`except:` scripts.
  A SIGINT that reaches it can be swallowed. "Ran to completion" fits
  "SIGINT ignored" and "SIGINT delivered and swallowed" equally well.
- `timeout` un-ignores SIGINT for its child. Measured from a `bash <file>`
  script with the gate-script launch shape:

  | Child | SigIgn | Python SIGINT handler |
  |---|---|---|
  | `exec python3 ...` | `...1006` (0x2 set) | `1` (SIG_IGN) |
  | `exec timeout --foreground 5 python3 ...` | `...1000` (0x2 clear) | `default_int_handler` |

  `timeout` (coreutils 9.4) catches SIGINT itself, and a caught disposition
  resets to default across exec. Every recipe from batch 2a on runs its
  test under `timeout --foreground`, so the old harness did deliver SIGINT
  to the test. 45 old SIGINT logs from batches 2a to py-a show a
  `KeyboardInterrupt` traceback, which Python can only raise if SIGINT was
  not ignored when it started.
- What the old harness really never exercised is make and the recipe shell
  receiving SIGINT, including the recipe's `trap ... INT`.

The discriminating check (the per-case logs) already existed when f0fc329
was written.

## One group SIGINT reaches the test twice

Measured with an isolated probe (no QEMU): one SIGINT to the group of
`timeout --foreground 10 python3 count.py` arrives at the child **twice**,
once directly and once forwarded by `timeout`. That holds under both
launches (SIG_DFL and the old SIG_IGN). Run directly, the child gets it
once (SIG_DFL) or not at all (SIG_IGN).

A script with a bare `except:` around `recv` can swallow one copy or both.
The shell runs its trap only after its foreground child exits, and make
waits for the test, so nothing cuts a swallowing test short. The sweep
shows both outcomes:

- The five py-d scripts before the fix, with SIGINT to the group aimed
  while the test was blocked in `poll`: the second copy escaped and all
  five exited in 0s.
- test-memdisk in the sweep (still a bare `except:`): both copies were
  swallowed and the test ran on 27s, to its own failure.

To test a script's own SIGINT handling, send one SIGINT to the test process
only, aimed while it is blocked in `poll`. Measured that way in py-d, all
five pre-fix scripts swallowed it and ran to completion (smoke 25s, flush
138s, file-stream 153s, editor 39s, x86_asm 47s). After
`except Exception:` (c4938d4), all five exit in 0s.

## The sweep

Harness: a local script, not committed; sha256 `63ba6e48dec493b6` for the
69-case run, `5740cbe711fe2423` for the control-2 run (adds control 2
and the corrected NOT RUN label). Rules:

- Each case is launched with SIGINT and SIGQUIT reset to default (what a
  terminal Ctrl-C finds), in its own session and process group.
- Before signalling, the case reads SigIgn of make (recipe cases) and of the
  test process, found by walking /proc from make, never by pattern. With
  the 0x2 bit set or unknown, the case is NOT RUN.
- The signal is aimed while the test is blocked in `poll`/`ppoll` (read from
  `/proc/PID/syscall`), the window where a bare `except:` swallows. All 64
  measured cases were aimed.
- One SIGINT goes to the group. The case records make's exit, the test's
  exit (polled separately, since make can die first), the test's cause of
  death from its log, and whether the role's QEMU and pidfile are gone.
- One harness at a time. A QEMU left from a case is killed by PID before
  the next case runs (none was).

Counts (from the table below, 70 rows):

| Outcome | Cases |
|---|---|
| Measured, SIGINT bit clear for make and test, QEMU and pidfile gone | 64 |
| — test died by `KeyboardInterrupt` | 59 |
| — test swallowed both copies, ran on (test-memdisk) | 1 |
| — script swallowed SIGINT, died when its QEMU died (`BrokenPipeError`) | 4 |
| NOT RUN: role never reached (test-cortexm boot-run, boot; finding 2026-10-04) | 2 |
| NOT RUN: no test process to signal (test-network crashes in ~5s; finding 2026-10-04) | 2 |
| Control 1 (make ignores SIGINT; recipe under `timeout`) | 1 |
| Control 2 (test starts with SIGINT ignored) | 1 |

No case left a QEMU or a pidfile.

**Control 1 is not a valid control.** It reproduces the old harness (make
SigIgn `...06`), but `timeout` un-ignores SIGINT for the test (`...1000`),
so the test died by `KeyboardInterrupt` in 0s. A recipe under `timeout`
cannot hold SIGINT ignored for its test. **Control 2 is valid:**
test_asm_vocab.py run directly with SIGINT ignored (SigIgn `...1006`),
signal aimed at `poll`. It ran to completion (`Passed: 45/45`, 198s) and
its `atexit` hook cleared the QEMU. So the sweep tells "ignored" from
"delivered".

**Six cases show a bare `except:` still swallowing SIGINT.** test-memdisk,
ahci_blk_reader, ahci_blk_writer, blk_writer_vector and persist_quick are
among 13 tracked scripts that still have the pattern. The other eight
(catalog_registry, dump, ne2000, pci_enum, pit_timer, ps2_keyboard,
ps2_mouse, vga_graphics) are not run by any converted recipe or by the
sweep. In every case the QEMU and pidfile were still cleared; the cost is
promptness, or that the script only dies when its QEMU does. Not fixed here.

### Per recipe and per role

| Case (recipe/role) | make SIGINT | test SIGINT | test exit | QEMU/pidfile | test died by | note |
|---|---|---|---|---|---|---|
| CONTROL-test-smoke-ignored | ign | clear | 0s | gone/gone | KeyboardInterrupt | control 1, **invalid as a control**: timeout un-ignores SIGINT for the test |
| test-log-harness | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-log-harness-nic | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-xhci | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-pci-bar | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-firstboot/lan | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-firstboot/offline | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-smoke | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-loops | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-abort | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-dict-bounds | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-phys-alloc | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-pci-typing | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-squote-laydown | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-squote-laydown-backstop0 | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-flush | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-file-stream | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-integration | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-vocabs/test_editor | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-vocabs/test_x86_asm | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-vocabs/test_driver_vocabs | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-vocabs/test_disasm | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-vocabs/test_port_mapper | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-vocabs/test_echoport | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-vocabs/test_catalog_complete | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-gui/test_stub_dispatch | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-gui/test_ui_core | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-gui/test_gui_harvest | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-gui/test_ui_parser | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-gui/test_ui_events | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-gui/test_fe_strip_cr | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-install | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-meta/metacompiler | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-meta/meta-compile | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-meta/meta-b6 | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-meta/meta-boot-builder | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-meta/meta-boot-booted | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-meta/meta-b6b-builder | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-meta/meta-b6b-booted | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-meta/meta-does-builder | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-meta/meta-does-booted | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-ahci-write | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-vbr | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-g6 | clear | clear | 13s | gone/gone | KeyboardInterrupt | KeyboardInterrupt at once; the second copy hit the system crash-report excepthook; exit at 13s (not traced further) |
| test-block-reload | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-arm64-boot/builder | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-arm64-boot/boot | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-cortexm/builder | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-cortexm/boot-run | — | — | — | — | — | NOT RUN: role QEMU never held build/test-cortexm.d/boot-run.pid; launcher exit 2 |
| test-cortexm/boot | — | — | — | — | — | NOT RUN: role QEMU never held build/test-cortexm.d/boot.pid; launcher exit 2 |
| test-carrier-write-safe | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-network/net-a | clear | ? | — | — | — | NOT RUN: no test process found: it ended before the signal (harness printed a wrong reason; relabelled run in control2.log) |
| test-network/net-b | clear | ? | — | — | — | NOT RUN: no test process found: it ended before the signal (harness printed a wrong reason; relabelled run in control2.log) |
| test-memdisk | clear | clear | 27s | gone/gone | no traceback | bare `except:` (2): both SIGINT copies swallowed; the test ran on and failed by itself ("no ok prompt"); make waited for it |
| test-survey/7500 | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-survey/7501 | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-survey/7502 | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-survey/7503 | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-survey/7504 | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| test-survey/7505 | clear | clear | 0s | gone/gone | KeyboardInterrupt |  |
| script/eviction_flush_test | — | clear | 0s | gone/gone | KeyboardInterrupt |  |
| script/iv_roundtrip_test | — | clear | 0s | gone/gone | KeyboardInterrupt |  |
| script/test_ahci_blk_reader | — | clear | 2s | gone/gone | BrokenPipeError | bare `except:` (2): SIGINT swallowed; died when its Popen QEMU (same group) died |
| script/test_ahci_blk_writer | — | clear | 2s | gone/gone | BrokenPipeError | bare `except:` (2): as above |
| script/test_asm_vocab | — | clear | 0s | gone/gone | KeyboardInterrupt |  |
| script/test_blk_writer_vector | — | clear | 2s | gone/gone | BrokenPipeError | bare `except:` (2): as above |
| script/test_persist_quick | — | clear | 2s | gone/gone | BrokenPipeError | bare `except:` (2): as above |
| script/test_shutdown | — | clear | 0s | gone/gone | KeyboardInterrupt |  |
| script/test_mft_bounds | — | clear | 0s | gone/gone | KeyboardInterrupt |  |
| CONTROL-script-asm_vocab-ignored | — | ign | 198s | gone/gone | no traceback; Passed: 45/45 | control 2: test starts with SIGINT ignored; ran to completion |

## Per commit and finding

"Old logs" means the marker in each case's SIGINT log from that batch's
gate run, counted per file.

| Commit / doc | Claimed | Old logs show | After the sweep |
|---|---|---|---|
| finding-harness-pkill-cross-worktree-2026-09-30.md (`FB_KILL`) | test-firstboot verified on normal exit, SIGINT, SIGTERM and SIGKILL (2026-09-29) | How that SIGINT was launched is not recorded; not checked here. | **Stands**: firstboot lan and offline, 0s by `KeyboardInterrupt`; nothing left. |
| 058ea52, 64aee8e (batch 1) | H2: no QEMU or pidfile left after SIGINT/SIGTERM | 4 SIGINT logs: test ran to completion (`Passed: 13/13`, 41s) or to its budget (`Error 124`, 88s). No signal reached the test (own process group; already recorded, the reason for `--foreground`). | **Stands**, and now shown under a deliverable SIGINT: log-harness, log-harness-nic, xhci, pci-bar exit in 0s by `KeyboardInterrupt`; nothing left. |
| bd2aee7 (2a, six recipes) | H2: make exits 0-1s after SIGINT; nothing left | 6/6 `KeyboardInterrupt` + `Error 130`. make/shell side not exercised. | **Stands.** 6/6 in 0s with make and test deliverable; nothing left. |
| cba87aa (2b, five recipes) | H2: nothing left; file-stream's SIGINT ran to completion | 4/5 `KeyboardInterrupt`; file-stream `Passed: 16/16` (bare `except:`). | **Stands.** 5/5 in 0s (file-stream after py-d); nothing left. |
| 17c912f (2c: 13 loop fixtures, install, meta fixture 1) | B1/B2/B3 clean | 11/13 `KeyboardInterrupt`; test_editor, test_x86_asm ran to completion (bare `except:`). B2 loops stopped at fixture 4; B3 `KeyboardInterrupt`. | **Stands.** 13 fixtures, test-install and meta fixture 1 all 0s; nothing left. Full-loop SIGINT (B2) not repeated. |
| 35c6fe6 (3a, ahci-write) | H2: make exits in 1s; nothing left | `KeyboardInterrupt` + `Error 130`. | **Stands.** 0s; nothing left. |
| 488d182 (3b: vbr, g6, block-reload, arm64 x2, cortexm builder) | H2 INT/TERM for every QEMU role | 6/6 `KeyboardInterrupt`. | **Stands.** 6/6 clean; g6 exits at 13s (see table). cortexm's ARM roles still unreached. |
| 9eacc8b (test-meta, 9 roles) | H2 SIGINT/SIGTERM for all 9 roles | 9/9 `KeyboardInterrupt`. | **Stands.** 9/9 in 0s; nothing left. |
| 939a7ce (py-a: carrier, memdisk, 6 survey roles, network) | H2 per role; network no window | 8/8 `KeyboardInterrupt`. | **Stands for "nothing left"**, 8/8. memdisk's script swallows SIGINT (27s, bare `except:`), which the old run did not show. network: NOT RUN (crash). |
| 3731373 (py-b, four scripts, run directly) | SIGINT/SIGTERM to the group: no QEMU left | Script had SIGINT ignored (no `timeout`); exits 3-14s by `BrokenPipeError`. | **"No QEMU left" stands.** With SIGINT deliverable: eviction_flush, iv_roundtrip 0s by `KeyboardInterrupt`; ahci_blk_reader, ahci_blk_writer swallow it and die at 2s when their QEMU does. |
| f0fc329 (py-c) | SIGINT not measured (harness invalid); asm_vocab real-style 2s | Over-corrected (steps 1-2 above). asm_vocab's real-style result was launched with SIG_DFL and stands. | **Stands for "nothing left"**: asm_vocab, shutdown, mft_bounds 0s by `KeyboardInterrupt`; blk_writer_vector, persist_quick swallow it and die at 2s with their QEMU. |
| finding-tests-swallow-sigint-2026-10-04.md | 3 slow/complete SIGINT cases; bare `except:` mechanism | The cases ran under `timeout --foreground`, so the test did get SIGINT. | **Mechanism confirmed** (py-d red: one SIGINT to the test, aimed at `poll`). Fixed for the five in c4938d4. Its times came from the old harness, but a group Ctrl-C can still be slowed by the pattern (test-memdisk, 27s). |

## The §7 trap line

f0fc329 added: "a harness started with setsid … & from a non-interactive
script inherits SIGINT/SIGQUIT as ignored; reset SIGINT to default and
check SigIgn before trusting any SIGINT result." That stands. Added with
this doc: `timeout` un-ignores SIGINT for its child, so under such a
harness the test still gets SIGINT while make and the recipe shell do not,
and a `KeyboardInterrupt` in the log proves delivery to the test only.
Under `timeout --foreground`, one group SIGINT reaches the test twice. To
test a script's own SIGINT handling, send one SIGINT to the test process
only, aimed while it is blocked in `poll`.
