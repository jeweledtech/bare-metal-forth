# Result: what the x86 decoder suite does see (2026-09-20)

Three weeks of this arc have measured what the suite **cannot** see —
vacuous reds, a green test defending a defect, expectations read off
the product, an apparatus structurally incapable of seeing a corrupt
link. This is the first measurement of what it **does** see, and it is
recorded as a result rather than as a step in something else.

## The measurement

`tools/translator/scripts/rule30_sweep.py`, banked at
`docs/evidence/x64-rule30-sweep-2026-09-20.log`. For every **passing**
test that decodes a literal byte array, the test's own bytes are
disassembled in the test's own mode by a second instrument and the
assertion is compared. Reds are excluded: their expectation is the
oracle and they are meant to fail.

| predicate | swept | confirmed | disagrees |
|---|---|---|---|
| asserted **length** vs objdump | 65 of 85 | **65** | **0** |
| asserted **identity** vs objdump | 62 of 85 | **62** | **0** |

**127 expectations independently confirmed against a second
instrument.** Denominator printed, remainder named, alias table and
parsing contract both hashed into the log.

## What the sweeps found while confirming the rest

- **One real defect.** `0F 0D C0` is the register form of `PREFETCH`
  and is `#UD` — oracle NONE, screen `(bad)` — while its memory forms
  are 3 and 7 in both. A test asserted length 3 for an encoding that
  has no length. It is now a red under (t).
- **Nine identity expectations**, found earlier by symptom rather than
  by predicate, each naming a real instruction in its comment and then
  asserting it was a no-op. All nine converted.
- **Four rows that are neither.** `06`, `82`, `60`/`61` and `8F /1` are
  refused by *both* instruments, which therefore attest no length at
  all. The suite's "length stays 1" on those is this decoder's
  **refusal policy** — registered by
  `x64_RED_n_invalid_walk_continues` — and objdump's competing 1 or 4
  is objdump's own. A refusal is not a disagreement and the sweep
  scores it in its own bucket.

## The remainder, named rather than claimed

These predicates check the **length** and the **mnemonic**. An operand
count, a register number or an immediate copied from the decoder is the
same defect and neither predicate would see it. **No instrument covers
that today.** Sixteen tests are unswept on length and 23 on identity,
each listed with its reason in the log; six of them probe
redundant-prefix behaviour, which objdump cannot adjudicate because it
prints the prefix as its own pseudo-instruction, and those need the
pinned oracle instead.

## The suite's own denominator, added 2026-09-21

**Rule 27 applies to the suite as much as to any instrument.** "25
suites, 115 tests, all green" is a numerator; this is the denominator,
and it is a **different** measurement from the 127 above — line
coverage says which lines *ran*, not whether what ran was *asserted*.
Both are reported because neither implies the other.

`docs/evidence/x64-suite-coverage-2026-09-21.log`: whole tree rebuilt
with `--coverage` at `-O0`, `make test-all` run, `gcov` over every
`.gcda`, maximum per source taken (a file compiled into several test
binaries has several `.gcda`, and the union is what the suite reaches).

| | lines | executed |
|---|---|---|
| `x86_decoder.c` | 909 | **92.4%** |
| `semantic.c` | 728 | 84.3% |
| `elf_loader.c` | 282 | 83.0% |
| `forth_codegen.c` | 230 | 81.7% |
| `format_detect.c` | 101 | 78.2% |
| `pe_loader.c` | 323 | 74.6% |
| `cil_semantic.c` | 65 | 70.8% |
| `uir.c` | 797 | **51.2%** |
| `arm64_decoder.c` | 555 | **48.1%** |
| `translator.c` | 709 | 43.2% |
| `cil_decoder.c` | 472 | **27.3%** |
| **TOTAL over the measured tree** | **5,217** | **65.1%** |

**And the figure the table leaves out, stated rather than omitted.**
The 0% rows are two different things and the first draft of this
measurement conflated them:

- **Four empty placeholders** — `api_map.c`, `codegen.c`,
  `riscv_decoder.c`, `optimize.c` — have no executable line, so 0% is
  correct and complete.
- **780 lines under `src/codegen/floored_div/` are compiled by
  nothing.** They are real code for x64, ARM64 and RISC-V floored
  division; the build's `src/codegen/*.c` wildcard does not descend
  into that directory, and `test-floored-div` compiles only its own
  test file and **is not in `test-all`**, so it has never run in any
  suite invocation.

**The blended figure is an alarm, not a number to quote.** Counting those
780 lines as zero-covered prints *not measured* and *not executed* the
same way, which is the thing the coverage log itself says must not
happen. The two components stay visible instead: **65.1% over what is
built**, and **780 lines that were in no build at all**. The single
blended 56.6% is withdrawn as a quotable figure.

**Resolved the same day.** Those 780 lines were a byte-identical
duplicate of `tools/floored-division/`, and the translator target that
appeared to cover them compiled a file that had never existed there.
The duplicate is deleted and the target removed with the reason in
place. At the real home the same look found worse — the passing suite
tests the reference semantics and not one emitted byte, the committed
x64 harness was built by no target, `codegen-test` had never compiled,
and the ARM64 and RISC-V emitters had been read by no compiler ever.
`make -C tools/floored-division` now exercises **all nine emitters
across three architectures**: 9 exercised, 0 failures, first run.

**Why it was worth the detour.** Floored division is the defining
difference between Forth-83 and FIG-Forth, and Forth-83 is the standard
this project's brief names. Those were not leftovers from an
experiment; they are a language-conformance feature that had been
sitting dark.

**The profile against the queue, stated rather than argued.** The
decoder is the **best**-covered file in the tree at **92.4%**, and four
fixes are queued against it. `uir.c` at **51.2%** and `translator.c` at
**43.2%** are the **worst**, and they are exactly where the consumer
work lands. `arm64_decoder.c` at 48.1% is decoding for a lifter nobody
calls.

**The order stands as ruled** — the queue ends at (s), then the
consumer. But **the floor under the next phase is 51% and 43%**, and
that is worth knowing at its start rather than halfway through. Knowing
what is dead before writing the back half of the pipeline was worth one
command.

## Why it counts as a result

An expectation that agrees with a second instrument is not proof the
decoder is right — it is proof the *test* is not merely a snapshot of
the decoder. That is the property the thirtieth rule exists to protect,
and 127 of them now have it on the record with the exact predicate that
established it, so the number can be re-taken rather than re-asserted.
