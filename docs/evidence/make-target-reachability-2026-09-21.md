# Every make target, and whether the suite reaches it (2026-09-21)

**Why this exists.** `test-floored-div` was the **third** broken-and-
unreachable target found by accident rather than by looking —
`test-network` broken since 08-30 and `test-arm64-boot` exempt were the
first two. One enumeration closes the class instead of finding the
fourth next week. It is the same generalisation the trap rows got, and
it was earned the same way.

**Method.** Parse each `Makefile` for rule targets and `.PHONY` names,
take the transitive closure from the suite root, and subtract. Two
trees, two roots: `tools/translator` from `test-all`, and the project
root from `test`.

**Every target is now exactly one of: reachable, exempt with a reason
stated, wired in, or deleted.** Nothing is left unclassified.

## `tools/translator` — 46 targets, 28 were reachable

**Wired in, 2026-09-21:**

| target | why it was owed |
|---|---|
| `opcode-table-check` | regenerates the committed opcode table and diffs it. It asserts the generated header still matches its generator, which is the whole point of generating it. Runs clean: *"opcode table: regenerates identically"* |
| `test-floored-division` | delegates to `tools/floored-division`. Wiring the new harness into **that package's** default target alone would have **moved the dark code, not lit it** — the real home would have inherited exactly the defect the duplicate had |

**Deleted:** `test-floored-div` — compiled a file that had never existed
in that tree, and was not in `test-all`, so it never ran and was never
seen to fail.

**Exempt, with the reason:**

- **Housekeeping** — `all`, `test` (alias for `test-all`), `clean`,
  `clean-measure`, `debug`, `dist`, `help`.
- **Needs the oracle** — `differential`, `differential-all`,
  `differential-modules`, `ghidra-check`, `ghidra-fixtures`,
  `ghidra-instr-at`, `ghidra-oplen`, `ghidra-oplen-elf`. Ghidra 12.1.2
  is not a build dependency and must not become one.
- **By ruling** — `test-hp-drivers`, suspended 2026-09-18 because its
  per-driver floors were calibrated on desync noise.
- **A tool, not a test** — `build-synth`, `opcode-table` (the
  generator; its *check* is now in the suite).

The classification is also written into the Makefile above `test-all`,
so it is maintained where the targets are.

## Project root — 59 targets, 30 were reachable from `test`

**The finding: `test-translator` is not reachable from `make test`.**
The whole UBT suite — 25 suites, 115 tests, everything this arc has
built — is invisible to the project's own test entry point. It runs
clean when invoked (`All tests passed`), so this is **owed, not dead**.

**Owed — runs clean today, simply not wired:**

| target | result when run |
|---|---|
| `test-translator` | **passes** — 25 suites |
| `test-pipeline` | **passes** — 16/16 |
| `check-sync` | **passes** — "all paid files in sync" |

**Exempt, needs QEMU and a built image** (each depends on `$(COMBINED)`
or a debug image and drives a serial console): `test-network`,
`test-arm64-boot`, `test-cortexm`, `test-meta`, `test-flush`,
`test-ahci-write`, `test-squote-laydown-backstop0`, and the `run*`
family. These are emulator trips, not unit tests; the standing ruling
is that QEMU is not a truth source, so they are deliberately outside a
green-in-seconds suite. **`test-network` is separately recorded as
broken since 2026-08-30** and is *dead-pending-repair*, not exempt.

**Exempt, outward-facing or destructive** — `pxe-push`,
`pxe-push-grub`, `pxe-setup`, `pxe-status`, `write-block`,
`write-catalog`, `iso`, `combined`, `backstop0`, `blocks`, `free`.
These write boot media or push to a network host. They must never be in
an automatic suite.

**Exempt, build and housekeeping** — `all`, `clean`, `debug`, `help`,
`print-embed-vocabs`, `check`, `check-kernel-size` (the last two are
build-time assertions that run as part of the image build).

**Not classified here** — `ubt-llm-validate`,
`ubt-llm-validate-prefilter`. They shell into `tools/ubt-llm` and call
a model; whether they belong in any automatic suite is a ruling, not a
measurement, and it is **owed to the owner** rather than decided here.

## What the audit is worth

Three targets in the project root run clean and are invisible to `make
test`, one of them being **the entire translator suite**. One target in
the translator tree was a phantom. The class is now enumerated rather
than sampled, and both Makefiles carry their classification inline, so
the fourth instance has nowhere to hide.
