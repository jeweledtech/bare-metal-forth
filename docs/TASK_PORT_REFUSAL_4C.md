# TASK 4c — refuse to start on a bound port (plan, 2026-10-05)

Branch `refuse-bound-port` from master `965a98b`. Queue position: after 4a,
before 4b (TASK_HARNESS_KILL_BY_PID §5). Required: every QEMU recipe
refuses to start when a port it needs is taken, and says which port.
Optional and **not** done here: skipping a busy TEST_PORT_BASE.

Motivation: on 2026-10-03/04 seven candidate worktree names landed on five
busy bases (finding-test-port-base-collides-host-service-2026-10-02). A
base that is clear when chosen can be taken by the time a test runs.

## 1. The probe, and the gate that proves it agrees with QEMU

`tools/ports_free.py` answers "would QEMU fail to listen on this port?" by
binding the way QEMU binds. Its rule is **not assumed**. Whether QEMU's
`tcp::PORT` binds IPv4 only, or IPv4 and IPv6 together, is unverified. So
the rule is derived from a measured table, and the table stays as a gate.

QEMU listen forms in use (counted from Makefile and tests/*.py,
2026-10-05): `tcp::P` (serial, some monitors), `tcp:127.0.0.1:P`
(monitors), `socket,listen=:P` (the NE2000 netdev).

**Gate P (probe agrees with QEMU).** For each listener kind holding a port:
nothing, `127.0.0.1`, `0.0.0.0`, `[::]` dual-stack, `[::]` v6-only, and a
port in TIME_WAIT. For each QEMU listen form, run the probe and a real QEMU
launch (`qemu-system-i386 -S -display none -daemonize -pidfile ...`, no
disk) against the same held port, and record both. The probe must give
QEMU's answer in **every** row. Any row where they differ is a red for the
probe. The table, with the QEMU version, goes in §6 and is re-run by a
committed script (`tools/ports_probe_gate.py`).

## 2. Where the check runs

In every QEMU recipe, **after** the pre-clean (`QEMU_KILL` /
`QEMU_KILL_DIR`), so this tree's own stale QEMU is killed first and never
counts as busy, and **before** any launch. It fails the recipe at once:
`PORT BUSY: <port> (<recipe> <role>)`, plus the holder from `ss -tlnp`
when visible, exit 1. Loop recipes (test-vocabs, test-gui, test-meta)
check each fixture's ports just before that fixture starts.

## 3. Ports come from a generated table, not a hand-kept one

`tools/port_inventory.py` derives every recipe's ports:

- **Recipe-launched QEMUs:** parsed from the recipe text (`-serial`,
  `-monitor`, `-netdev ... listen=` with `$(TEST_PORT_BASE)+N` or a
  `PORT=` variable).
- **Script-launched QEMUs:** parsed from the script's QEMU argument lists
  with Python's `ast`. A port expression must resolve to "the port the
  recipe passed in, plus a constant" (`PORT + 1`, `PORT_A + 100`,
  `PORT_BASE + 5`, ...).
- **Fails closed:** a listen address it cannot resolve is an error, not a
  skip.

The generated table is committed (`tools/qemu_ports.json`). Recipes call
the probe by recipe (and fixture) name; the probe reads the table, so no
recipe lists its ports by hand. **New check in `make test`:**
`test-port-inventory` regenerates the table and fails if it differs from
the committed one, i.e. when a recipe's ports no longer match what its
script uses.

## 4. The three scripts that never check that QEMU started

test_cortexm_boot.py, test_ne2000_network.py and test_memdisk_blk_writer.py
start QEMU with `subprocess.run(...)` or `Popen(...)` and never look at
whether it came up (found by grep, 2026-10-05). The recipe's check runs
before the launch, so a port can still be taken in between. In these
three, that gap becomes a hijack: the script connects to whatever holds
the port. Each must **fail at once, naming the port, if its QEMU did not
start**: check the launcher's exit status, and that the pidfile names a
live QEMU, before connecting.

## 5. Gates, in order

Predictions are written in §5a **before** the red runs.

1. **Gate P** (§1). Done first; reported before any recipe is edited.
2. **Red, on master's recipes**, one case per mechanism, with a plain Python
   listener (not QEMU) holding the port.
3. **Green: per-port refusal sweep.** For every recipe and every port in the
   table, hold that port, run the recipe: `PORT BUSY: <that port>`, non-zero
   exit, in ≤1s, no QEMU started.
4. **The three scripts (red case 3's green).** The same held port, with the
   recipe check bypassed so the launch is reached: fast, named failure, no
   hijack.
5. **Own orphan.** A stale QEMU from this tree holding the port is killed by
   the pre-clean; the run proceeds, no refusal.
6. **Teardown after a refusal.** No QEMU, no pidfile.
7. **test-port-inventory:** green on the tree; red when a script's port
   offset is changed by one and the table is not regenerated.
8. **Full `make -k test`:** only the known five red (xhci, pci-bar,
   doc-drift, translator, pipeline).

### 5a. Pre-registered predictions for the red (step 2)

| # | Mechanism | Case | Predicted on master |
|---|---|---|---|
| 1 | Recipe-launched `-daemonize` QEMU, serial | test-smoke, base+0 | QEMU fails to bind; recipe fails under `set -e` with QEMU's own error; the recipe does not name the port |
| 2 | Monitor port | test-firstboot, base+89 | as 1 |
| 3 | Script-launched QEMU, exit never checked | test-network +41 (B serial) and +140 (netdev); test-memdisk | **hijack**: the script connects to the foreign listener; slow or misleading failure, possibly running to its T_ budget |
| 4 | Loop fixture | test-vocabs, fixture k | as 1, at fixture k only |
| 5 | Script-derived port, exit checked by `-daemonize` | test-meta, meta-boot booted +84 | the script sees the launch fail; how it reports it is not predicted |

### 5b. Red outcomes (recorded 2026-10-05 after the run; §5a above is unchanged)

Branch HEAD `a3046bb`, recipes as on master. The holder was a plain IPv4
listener on 0.0.0.0 that accepted connections and recorded what it was
sent. Base 7800.

| # | Held port | make exit, time | What the holder received | Port named? | Prediction |
|---|---|---|---|---|---|
| 1 | smoke serial 7800 | 2, 34s, `Passed: 0/7` | 114 bytes: `WORDS\r1 2 + .\rS" hello" TYPE ...` (**hijack**) | no | **wrong**: QEMU did not fail; it started on `[::]` only (Gate P) |
| 2 | firstboot monitor 7889 | 2, 0s | nothing | yes, QEMU's error: `-monitor tcp:127.0.0.1:7889 ... Address already in use` | right for the failure; QEMU's own line names the port |
| 3a | network B serial 7841 | 2, 41s, `FAIL: Instance B alive` | `1 2 + .\r1 2 + .\r` (**hijack**) | no | right |
| 3b | network netdev 7940 | 2, 27s, `Could not connect to QEMU instances` | 1 connection, 0 bytes: A's QEMU never started (exit unchecked) and B's netdev connected to the holder | no | right (misleading failure) |
| 3c | memdisk serial 7865 | 2, 33s, `no ok prompt after PXE boot` | 2 connections (**hijack**) | no | right |
| 4 | vocabs fixture 2 (test_x86_asm) 7811 | 2, 114s, fixture 2 `Passed: 0/8` | `1798 1821 THRU\rUSING X86-ASM\rHEX HERE @ ...` (**hijack**) | no | **wrong** like 1; it did happen at fixture k only |
| 5 | meta-boot booted serial **7885** (+85) | 2, 673s, `Passed: 15/20` | `\r3 4 + .\r: SQ DUP * ; 5 SQ .\r1 IF 42 ELS...` (**hijack**) | no | **wrong**: the launch did not fail |

§5a row 5 says "+84"; in test_meta_boot.py +84 is the monitor and the
booted serial is +85, which is the port held here. No QEMU was left after
any case.

## 6. Gate P table (measured 2026-10-05)

QEMU 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18), port 7990, one QEMU per row
(`-S -display none -daemonize -pidfile`, no disk), killed by pidfile.
"Reaches" is observed: the gate connects to 127.0.0.1:P, as 90 of 91
connect sites in tests/*.py do, and checks with `ss -tnp` that QEMU owns
the accepted end. Probe at this run: one IPv4 bind on 0.0.0.0.

| Holder | QEMU form | QEMU starts? | QEMU bound / error | 127.0.0.1 reaches QEMU? | Probe: free? | = starts? | = reaches? |
|---|---|---|---|---|---|---|---|
| nothing | `tcp::P` | yes | 0.0.0.0:7990 [::]:7990 | yes | yes | yes | yes |
| nothing | `tcp:127.0.0.1:P` | yes | 127.0.0.1:7990 | yes | yes | yes | yes |
| nothing | `listen=:P` | yes | 0.0.0.0:7990 | yes | yes | yes | yes |
| 127.0.0.1 | `tcp::P` | yes | [::]:7990 | no | no | **no** | yes |
| 127.0.0.1 | `tcp:127.0.0.1:P` | no | -monitor tcp:127.0.0.1:7990,server=on,wait=off: Failed to find an avai | no | no | yes | yes |
| 127.0.0.1 | `listen=:P` | no | -netdev socket,id=n0,listen=:7990: can't bind ip=0.0.0.0 to socket: Ad | no | no | yes | yes |
| 0.0.0.0 | `tcp::P` | yes | [::]:7990 | no | no | **no** | yes |
| 0.0.0.0 | `tcp:127.0.0.1:P` | no | -monitor tcp:127.0.0.1:7990,server=on,wait=off: Failed to find an avai | no | no | yes | yes |
| 0.0.0.0 | `listen=:P` | no | -netdev socket,id=n0,listen=:7990: can't bind ip=0.0.0.0 to socket: Ad | no | no | yes | yes |
| [::] dual-stack | `tcp::P` | no | -serial tcp::7990,server=on,wait=off: could not connect serial device  | no | no | yes | yes |
| [::] dual-stack | `tcp:127.0.0.1:P` | no | -monitor tcp:127.0.0.1:7990,server=on,wait=off: Failed to find an avai | no | no | yes | yes |
| [::] dual-stack | `listen=:P` | no | -netdev socket,id=n0,listen=:7990: can't bind ip=0.0.0.0 to socket: Ad | no | no | yes | yes |
| [::] v6-only | `tcp::P` | yes | 0.0.0.0:7990 | yes | yes | yes | yes |
| [::] v6-only | `tcp:127.0.0.1:P` | yes | 127.0.0.1:7990 | yes | yes | yes | yes |
| [::] v6-only | `listen=:P` | yes | 0.0.0.0:7990 | yes | yes | yes | yes |
| TIME_WAIT | `tcp::P` | yes | 0.0.0.0:7990 [::]:7990 | yes | yes | yes | yes |
| TIME_WAIT | `tcp:127.0.0.1:P` | yes | 127.0.0.1:7990 | yes | yes | yes | yes |
| TIME_WAIT | `listen=:P` | yes | 0.0.0.0:7990 | yes | yes | yes | yes |

rows=18; probe = "QEMU starts" in 16 rows; probe = "127.0.0.1 reaches QEMU"
in **18** rows.

**What it shows.** For `tcp::P`, an IPv4 listener (127.0.0.1 or 0.0.0.0)
does not make QEMU fail. QEMU binds `[::]` alone, starts, and exits 0, and
a 127.0.0.1 connection goes to the other listener. So a recipe under
`set -e` sees success and the test talks to a stranger. Red case 1's
prediction (§5a: "QEMU fails to bind") is already contradicted for an
IPv4 holder; the red run records it.

**Criterion, owner's call.** §1 says the probe must give QEMU's answer in
every row. Read as "QEMU starts", the probe must say *free* in those two
rows, and the recipe proceeds into the hijack. Read as "the tests reach
QEMU", the probe agrees in all 18. The gate now exits non-zero on the
second reading; the table carries both.

## 6a. Gate results (2026-10-05/06, branch refuse-bound-port)

| Gate | Result |
|---|---|
| P, probe vs QEMU | Green after option (a): forms in use are `tcp:127.0.0.1:P` and `listen=:P`; 0 rows where QEMU starts but 127.0.0.1 does not reach it; the probe agrees with "reaches" in 18/18 rows. Red before (e127ecf): 2 hijack rows, `tcp::P`. |
| Red (§5a/§5b) | 7 cases on master's recipes; serial `tcp::P` and the unchecked scripts were hijacked (the holder received the tests' Forth commands). |
| Inventory | `tools/port_inventory.py`, committed table 31 recipes / 71 listen entries. `test-port-inventory` in `make test`; red on a moved offset (DRIFT), a `tcp::` serial put back (DRIFT + TCP-ANY), a literal port and a `%`-formatted address (UNRESOLVED), a recipe without its probe (UNGUARDED). |
| Refusal sweep | 71/71: `PORT BUSY: <port>`, exit in 0.1s, 0 bytes to the holder, no QEMU or pidfile left (this is also "teardown after a refusal"). |
| Race | First pass 62/71. Eight failures in **five scripts §4 did not list** (arm64-boot builder and boot, block-reload, carrier-write-safe, g6's pre-clean monitor `quit`, uefi2-gdt): the §4 list of three came from a grep that counted any `returncode`/`.wait(` in a file as checking the launch. All eight fixed with the same helpers; rerun all PASS. test-cortexm +62 is NOT REACHED (the test stops before its ARM phase, 1d74586). So §4 covers eight scripts, not three. |
| Own orphan | smoke, network (pidfile dir), vocabs fixture: the stale QEMU is cleared by the pre-clean, no refusal, the recipe runs (7/7, 46/52 as in 4a, 7/7). |
| Normal run, exempt recipe | test-arm64-boot 40/40 in 355s (batch-3b baseline 40/40, 354s). |
| Full `make -k test` | Only the known five red (xhci, pci-bar, doc-drift, translator, pipeline); MAKE_TEST_EXIT=2; no `PORT BUSY` and no "did not start" anywhere; tree `51ccbb0f`. |

### Owed (owner, 2026-10-06; neither blocks the merge)

1. **test-cortexm +62.** Its race case cannot be reached until cortexm's
   Phase 2 failure is fixed (the test stops at "No kernel to boot",
   1d74586), so the launch check on the ARM boot QEMU
   (`wait_started(..., 'ARM boot', ...)`) is unverified. Rerun that one case,
   `tools/ports_race_gate.py --mode race test-cortexm:+62`, when cortexm is
   fixed.
2. **test-log-harness-nic UDP +47/+48** (`-netdev dgram`) are outside the
   TCP probe. Left for the LOG-HARNESS validation pass to decide.

## 7. Overlaps (recorded, left as they are)

Several offsets are shared by two recipes in one tree. Harmless under a
serial `make test`; 4c correctly refuses if two of them ever run at once.
Separating them is not part of 4c (owner, 2026-10-05).

| Offset | Recipes |
|---|---|
| +50 | test-flush; test-arm64-boot (+50, +51, +52) |
| +60..+62 | test-cortexm |
| +84, +85 | test-firstboot (offline); test-meta meta-boot (+83 +1, +2) |
| +86..+88 | test-meta meta-b6b; test-pci-bar +87; test-firstboot (lan) +88 |
| +95, +96 | test-g6 (+95, +96); test-block-reload +95; test-pci-typing +96 |
| +98 | test-phys-alloc; test-squote-laydown |

(From the 2026-10-05 inventory read; `tools/port_inventory.py` prints the
authoritative list once it exists.)

## 8. Not in 4c

Skipping a busy base; scripts run directly with no recipe (no recipe to put
the check in); renumbering the overlaps.
