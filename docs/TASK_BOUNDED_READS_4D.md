# TASK 4d — the rest of the suite's reads end at the prompt (2026-10-12)

Owner, 2026-10-12: switch test-pci-bar to the prompt-terminated read, then
every other test still reading with a fixed wait where the
one-command-at-a-time assumption holds; report the suite time before and
after. Follows 4b (docs/TASK_BOUNDED_READS_4B.md): same helper, same gates.

## Design note

- **Scope.** Every script `make test` runs whose command read is a fixed
  sleep and then a read to a quiet gap (2 s, 3 s or 5 s), 13 scripts:
  test_phys_alloc, test_pci_typing, test_file_stream_helpers,
  test_memdisk_blk_writer, test_dict_bounds, test_abort,
  test_full_integration, test_log_harness, test_log_harness_nic,
  test_begin_while, smoke_test, test_carrier_write_safe, test_block_reload.
  test_xhci and test_pci_bar went first (4f8bd5e, f3b387b). Boot captures
  (test_vbr_boot, test_uefi_boot) read boot output, not command replies,
  and stay as they are. Reads that already end at the prompt
  (test_phys_alloc's send_timed) are untouched.
- **Change.** Only the body of each script's `send`/`cmd` changes, to
  `serial.send_until_prompt`, with the budget `max(15, 5 x wait)` (test_g6's
  form). Call sites, check names and counts don't change.
- **Exceptions** (4b §3d): a command whose output arrives after its prompt
  keeps a fixed wait, listed below with the transcript line that shows it.
  Found by G1, not guessed. test_log_harness_nic (a host-side network peer)
  is the likeliest place for one.

## Gates per script (4b §4)

G1 every reply identical (old `send` traced through a one-off copy, not
committed); G2 the same PASS/FAIL per check; G3 every read ends at the
prompt, except listed exceptions; G4 time before and after (n=2 after);
G5 one aimed SIGINT ends the test in 0-1 s. Each limit is reset to about
twice the measured time.

## Suite time before

3,239 s (2026-10-12, master f3b387b plus nothing): 2,559 s from a traced
`make test` up to test-interp-abort, where `--trace` broke that recipe's
sub-make output (an instrument fault, not a regression), plus 680 s for
the remaining ten targets timed one by one.

## Results

Evidence: ~/forthos-evidence/2026-10-12-suite-time/ (4d/<name>/ holds each
script's before/after logs, traces, G1-diffs.json and report.json).

### Suite time

| `make test` | Wall time |
|---|---|
| 10-12 morning: xhci fast, pci-bar slow, the 13 slow | 3,398 s (56m38s) |
| before the 13 (pci-bar fast) | 3,239 s |
| after (everything here) | 2,213 s (36m53s) |

-1,026 s for the 13 against -986 s measured target by target. Against the
morning run: -1,185 s, -35%. The after run's only red was check-sync (the
two private-owned scripts not yet committed there), cleared by
forthos-vocabularies 8614182; every test target passed. Before this task,
test-xhci never passed inside its limit, so a green `make test` had no
earlier wall time to compare against.

What is left: test-install 338 s, test-g6 276 s, test-xhci 238 s,
test-log-restore 211 s, test-firstboot 159 s, test-survey 149 s,
test-vocabs 132 s -- all already read to the prompt (4b, or written that
way). Where their remaining time goes (guest work, boot waits, monitor,
keystrokes) has not been broken down.

### test-xhci and test-pci-bar (first, 4f8bd5e and f3b387b)

- **test-xhci:** 319/319 in 3m58s, Phase 12 included. Before: 20+ minutes
  (386 reads at >= 3 s); the old 120 s limit never measured a pass, and the
  cut-off read as a Phase 12 hang. No phase is red. T_XHCI 120 -> 480.
- **test-pci-bar:** 16/16 in 24.2 s, was 223.2 s (64 reads at ~3.3 s plus a
  THRU). The 10-08 "jump" was never one: the pre-10-02 send() had the same
  settle and 2 s gap, and the 90 s limit (10-02, 07580f5) bounded a hang
  and never measured a pass; no record shows a pass under 90 s. Finding
  closed. T_PCI_BAR 450 -> 50.
- **G1 for both** (old send traced from the commit before each change):
  pci-bar 64/64 replies identical (old run 223.2 s again, at T_PCI_BAR=450
  for that measurement only; the first attempt hit the new 50 s limit, my
  error). xhci 603/629 identical, old run 2,384 s (passed, at T_XHCI=2400
  for that measurement only); the 26 others are all `DECIMAL PSUM .`, the
  checksum of physical page 0, constant within a run and different between
  runs: two runs of the new code also differ (-1140161070, -1140156154), so
  it is boot-time state in page 0, not the read.

### The 13 scripts

| Target | Before (s) | After (s, n=2) | Speedup | G1 identical | G3 by prompt |
|---|---|---|---|---|---|
| test-smoke | 33.6 | 11.2, 11.2 | 3.00x | 8/8 | 8/8 |
| test-loops | 48.1 | 17.3, 17.3 | 2.77x | 10/10 | 10/10 |
| test-abort | 95.6 | 21.7, 21.7 | 4.41x | 23/23 | 23/23 |
| test-dict-bounds | 113.1 | 23.6, 23.7 | 4.80x | 29/29 | 29/29 |
| test-phys-alloc | 181.9 | 30.7, 30.6 | 5.93x | 43/43 | 43/43 |
| test-pci-typing | 171.7 | 30.2, 30.3 | 5.68x | 49/49 | 49/49 |
| test-integration | 90.1 | 20.7, 20.7 | 4.36x | 20/20 | 20/20 |
| test-file-stream | 161.3 | 28.3, 28.3 | 5.70x | 60/60 | 60/60 |
| test-log-harness | 47.6 | 11.9, 11.9 | 4.00x | 7/10, note 1 | 10/10 |
| test-log-harness-nic | 65.6 | 15.3, 15.3 | 4.30x | 3/5, note 1 | 5/5 |
| test-memdisk | 122.3 | 15.9, 15.9 | 7.69x | 23/23 | 23/23 |
| test-carrier-write-safe | 37.2 | 6.1, 6.1 | 6.06x | 9/9 | 9/9 |
| test-block-reload | 63.6 | 12.4, 12.4 | 5.12x | 19/19 | 19/19 |
| **total** | **1,231.8** | **245.3** | **5.02x** | | |

- **G2:** every target, the same checks with the same PASS/FAIL before and
  after, all passing (block-reload 12/12 read from its `[PASS]` lines; the
  one "FAIL" in carrier's log is the guest's own `BLOCK WRITE FAIL 199`,
  the refusal that test provokes).
- **G5:** one SIGINT aimed at each of the 13 and at test-xhci and
  test-pci-bar: all 15 died by KeyboardInterrupt in 0-1 s, no QEMU or
  pidfile left (G5-sigint.log).
- **Exceptions (4b §3d): none.** test_log_harness_nic's peer reply arrives
  before the prompt.
- **Limits** reset to about 2x the after time.

Note 1: the differing replies differ only in the log records' timestamp
(`T=`, timer ticks since boot), lower because each command arrives sooner;
every other byte, including the dumped block, is equal.

test_log_harness.py and test_log_harness_nic.py are private-owned (ignored
here); their change is committed in forthos-vocabularies and copied here.
