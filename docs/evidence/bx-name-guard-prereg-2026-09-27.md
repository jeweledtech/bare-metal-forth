# (bx) The name guard: pre-registration (2026-09-27)

Written before any code for (bx) and before either corpus scan. The
outcome goes **below**, and nothing above the Outcome line is edited
after the first run.

**The letter** (register, minted 2026-09-25 in
`base-at-accessors-2026-09-25.md`):
- **The limit.** `word_` copies at most 31 characters (`cmp ecx, 31`)
  and silently splits a longer token.
- **The defect.** The translator does not check the names it emits.
- **Owner ruling (2026-09-25):** a generator-side guard. Every name the
  translator emits must be ≤ 31 characters, checked across the corpus,
  and **refused rather than emitted** when it is not.

## What the source already says (read, not run)

`derive_vocab_name` (`translator.c`) upper-cases the file's basename,
strips the **last** extension and maps `_` to `-`. **It never
truncates.**

Applying that rule to the 1,322 distinct kernel drivers
(`kdrv-2026-09-26.json`) gives **7** whose derived vocabulary name is
longer than 31:

| set | file | derived length |
|---|---|---|
| Dell, Older ASUS, Newer ASUS | Microsoft.Bluetooth.Legacy.LEEnumerator.sys | 39 |
| Dell, Older ASUS, Newer ASUS | Microsoft.Bluetooth.AvrcpTransport.sys | 34 |
| Newer ASUS | mfencbdc.sys.{9D862F87-…}.deleteme | 51 |

**No driver's derived name is 22–31 long.** So no accessor
(`<V>-R<park>+<off>-<fetch>`, V + ≤ 10) and no port word (`<V>-BASE`,
V + 5) can pass 31 on a name that is itself ≤ 31.

## What gets built

**One guard, in `generate_forth_output` (`translator.c`).** It runs
after `forth_generate` and after `-f`'s cut, over the **final** text.

**What it checks.** Every line that defines a name:
- `: NAME`
- `VARIABLE NAME`
- `VOCABULARY NAME`
- `<n> CONSTANT NAME`

These are every defining form the codegen writes today (l.200–579 of
`forth_codegen.c`).

**What happens over 31.** The first NAME longer than 31 fails the
translation (`success = false`) with:

`(bx) emitted name <NAME> is <N> characters; the Forth parser takes 31.
Nothing was emitted. Name the vocabulary with -n.`

The guard never truncates or shortens, and it never changes an output
it accepts.

**Out of scope.** The `{`, `}` and `.` characters in the `.deleteme`
driver's derived name are a different question (token legality, not
length). They are named here and not taken.

## The red, registered before the code

**`bx_RED_overlong_name_refused`** (`test_mmio_consumer.c`, HP
HDAudBus.sys, full output). The accessor `<V>-R58+14-W@` is V + 10, so
`-n` controls the longest emitted name exactly.

| leg | input | today | after |
|---|---|---|---|
| (a) boundary accept | `-n` of 21 characters → longest name 31 | emitted | emitted, byte-identical (the guard accepts 31) |
| (b) boundary refuse | `-n` of 22 characters → longest name 32 | **emitted with a 32-character name** | **refused**, the message names the 32-character accessor |
| (c) corpus witness | Dell `Microsoft.Bluetooth.Legacy.LEEnumerator.sys`, no `-n` | **emitted** (`VOCABULARY` + 39) | **refused**, the message names the 39-character vocabulary |
| (d) the remedy | the same driver with `-n BTLE` | emitted | emitted |

**Red today:** legs (b) and (c). **Green today and after:** legs (a) and
(d). They are controls: a guard that refused everything would fail (a)
and (d).

The register gains (bx) with this red. The union goes 12 → 13 at the red
commit and back to 12 at the fix.

## The corpus scans

**Instrument:** `~/corpus/tools-2026-09-27/name_scan.py`. It runs
`bin/translator <path> -t forth -S` on each of the 1,322 distinct
drivers, the same argv as (bt)'s. For each driver it records:
- whether the translation succeeded;
- the sha256 of its output;
- every defined name longer than 31, found by the same four forms.

The scan runs **before** the guard (on the red build) and **after** the
fix.

**Predictions.**

**S1, before:** exactly the **7** drivers in the table above emit a name
longer than 31. Every such name contains that driver's derived
vocabulary name, and no other driver emits one.
- *Alternative named:* a name longer than 31 that does not contain the
  vocabulary name, from a codegen path the source reading missed.

**S2, after:** exactly those 7 are refused, and the other 1,315 succeed.
- *Alternative named:* a driver that failed before, for a reason other
  than (bx), still fails. That is recorded and is not a regression.

**S3, after:** every driver that succeeded before and is not among the 7
has a **byte-identical** output hash. The guard changes nothing it
accepts.

## Must not move

| # | what | check |
|---|---|---|
| M1 | translator: 428 existing tests pass | `make test`; the census becomes 429 (R added, named here) |
| M2 | the 10 (bt) drivers' outputs | covered by S3 |
| M3 | public `make test` | green (the translator is private; public tests do not run it except `test-translator`) |

**Named move:** the 7 drivers go from "emitted with an over-long name"
to "refused". That is the letter.

---

## Outcome

(written after the runs; nothing above this line changes)
