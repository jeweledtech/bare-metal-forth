# Finding: ARM64 virt dispatch fault — 2026-07-07

## Context

Phase C.1 of the metacompiler: switching the ARM64
boot test from raspi3b (broken TCP serial) to QEMU
virt machine (reliable PL011). target-arm64.fth was
parameterized with board-config variables (A64- prefix),
VIRT-CONFIG/RASPI3B-CONFIG, and BUILD-ARM64-VIRT/
BUILD-ARM64-RASPI entry words.

## Observation table (original, 2026-07-07)

| Register | Value | Meaning |
|----------|-------|---------|
| PC | 0x0000000000000200 | EL1 sync vector (no handler) |
| ELR | 0x401A1FA4 | Faulting instruction (~648KB past 8KB image) |
| ESR | 0x2000000 | EC=0 Undefined Instruction, IL=1 (32-bit) |
| X25 (PSP) | 0x4013FFFC | Data stack init'd, one push each — |
| X26 (RSP) | 0x4014FFFC | consistent with fault inside single DOCOL nesting |
| X27 (IP) | 0x40101CB4 | Forth IP, offset 0x1CB4 in image |
| X3 | 0x09000000 | UART base — init completed |
| X0 | 0x00000090 | Working register |
| PSTATE | 0x3C5 | EL1h, FPU disabled |

Image: 8028 bytes at 0x40100000 (virt, past DTB).
Build: BUILD-ARM64-VIRT, 147 symbols.

## Resolution — three bugs (2026-07-09)

### Bug #33a: Backward branch address-space mix (FIXED)

**Root cause:** `A64-BCOND-BACK,` in arm64-asm.fth
subtracts `T-HERE @` (host address) from `dest`. Three
callers in target-arm64.fth (KEY line 920, EMIT line
935, CMOVE line 1101) passed `T-ADDR` (target address).
The subtraction crossed address spaces, producing a
~660KB forward branch instead of a small backward
branch. EMIT's `B.NE` jumped to `0x401A1FA4` — zeroed
RAM decoded as UDF — confirming the ELR nibble was
`0x401A1FA4`, not `0x40101FA4`.

The dichotomy from the original finding resolves as
**computed wild address** (address-space mixing in the
branch offset calculation), not a device-region read.

**Fix:** Changed three caller sites from `T-ADDR` to
`T-HERE @`. The assembler's host-addr contract was
correct all along — the original comment ("dest is
host addr in T-IMAGE") documented the truth.

**First fix attempt (wrong direction):** Changed
`A64-BCOND-BACK,` itself to use `T-ADDR`. This broke
at load time: ARM64-ASM compiles before META-COMPILER
is on the search chain, so `T-ADDR` is not visible
during ARM64-ASM's block loading (`T-ADDR ?` errors).
The contract mismatch was on the caller side.

**Verification:** Static byte-decode of all three
`B.cond` instructions in the rebuilt image confirmed
small negative imm19 values (KEY: -2, EMIT: -2,
CMOVE: -5 instructions back). `in_asm` trace on the
fixed image: zero exceptions, kernel sits in KEY
poll loop waiting for input. Private repo fa36980.

**Latent hazard:** thumb2-asm.fth `T2W-B-BACK,` has
the same contract (host-addr dest) but zero callers.
Warning comment added referencing bug #33 so the
future Cortex-M caller doesn't repeat this trap.

### Bug #33b: INTERPRET stack bug (FIXED)

**Root cause:** ARM64's `MC-INTERPRET-ARM64` had
`>R -ROT 2DROP R> SWAP` to clean up after FIND's
3-value return `(xt flg TRUE)`. The `-ROT 2DROP`
discarded `xt` instead of `(addr len)`, causing
`EXECUTE` to receive `TRUE` (-1) instead of the
word's CFA.

**Why x86 was green:** `target-x86.fth` line 1507
uses `T-ALIAS` to re-expose the kernel's native
assembly INTERPRET. The ARM64 target is the *first
consumer* of the Forth-coded INTERPRET. x86 B6b's
17/17 green never covered this code path.

**Fix:** Replaced with `DROP >R >R 2DROP R> R>`.
DROP discards TRUE; >R saves flg then xt (LIFO: xt
on top of R-stack); 2DROP removes addr,len; R>
restores xt then flg. No SWAP needed — LIFO pop
order is natural.

**Verification:** Decoded INTERPRET's compiled cell
stream from the image. Traced both the success path
`(addr len xt flg TRUE)` → `DROP >R >R 2DROP R> R>`
→ `(xt flg)` → `STATE @ 0BRANCH` → `DROP EXECUTE`
and the miss path (untouched: 0BRANCH skips the
entire new sequence). FIND flag convention confirmed:
-1 = IMMEDIATE, +1 = normal. Compile-mode branch
`-1 = IF EXECUTE ELSE , THEN` is correct sense.
Private repo fa36980.

### Bug #33c: DOT/NUMBER output (OPEN)

**Symptom:** DOT produces wrong output for every
value. Multi-digit NUMBER also broken.

**Constraint table (10 data points, deterministic):**

| Input n | Output | Sign | Digit 1 | Digit 2 |
|---------|--------|------|---------|---------|
| 0 | -81 | - | 8 | 1 |
| 1 | -71 | - | 7 | 1 |
| 2 | -61 | - | 6 | 1 |
| 3 | -51 | - | 5 | 1 |
| 4 | -41 | - | 4 | 1 |
| 5 | -31 | - | 3 | 1 |
| 6 | -21 | - | 2 | 1 |
| 7 | -11 | - | 1 | 1 |
| 8 | -01 | - | 0 | 1 |
| 9 | -91 | - | 9 | 1 |

Multi-digit NUMBER: `12 .` → `12 ?` (parse failure).
`48` also fails to parse (multi-digit).

**Constraints any correct theory must satisfy:**

1. Sign always negative (for non-negative inputs 0-9)
2. First digit = `(8-n) mod 10` as ASCII
3. Second digit always `1`
4. Exactly two digits regardless of input magnitude
5. Multi-digit input takes the `?` error path
6. Single-digit NUMBER "succeeds" (DOT runs, not `?`)
7. +1 input → +10 output (factor-of-10 relationship)

**What is NOT verified:** Single-digit NUMBER may
push garbage — DOT being broken means no verified
observation of NUMBER's actual output.

**Eliminated hypotheses:**

- **MUL Ra-field (MADD accumulate register):** All
  four MUL instructions in image have Ra=31 (WZR).
  Clean. Bit-checked, not eyeballed from disassembly.
- **Comparison word encoding:** All CSINC+SUB patterns
  correct for standard Forth TRUE(-1)/FALSE(0).
- **DOCON/sysvar addresses:** All six match expected
  SYSVARS+offset values.
- **ROT-depth in NUMBER accumulate:** If ROT couldn't
  reach the accumulator and multiplied `addr` instead,
  the result would be near `0x40120000 * 10` — a
  ten-digit number. Observed output is exactly three
  characters. **Fails retrodiction.** May contain a
  real ingredient (the compiled NUMBER body needs full
  hand-simulation against cells, not source), but does
  not explain the data as stated.

**Queued decisive experiments:**

1. **EMIT-bypass discriminator:**
   `8 8 + 8 + 8 + 8 + 8 + EMIT` (expect '0'). Uses
   only `+` and EMIT, no DOT, no multi-digit NUMBER.
   If it prints '0': arithmetic and single-digit
   NUMBER are clean, fault isolates to DOT's rendering
   path (plus multi-digit NUMBER as possibly separate
   issue). If it prints something else: decode which
   byte arrived; the delta from 48 names the corrupted
   quantity. Either branch, the next session opens
   with information instead of theory.
2. **Full hand-simulation of NUMBER's compiled cells:**
   Walk the actual cell stream in the image for input
   "0", tracing every stack operation against the real
   compiled body — not the source. The source-reading
   method has been wrong three times this week.

## Verification lessons (three-cornered)

Three independent instances of "green that didn't
cover what it appeared to" emerged from this arc:

1. **Banner-green ≠ interactive-green.** raspi3b's
   "boot verified" meant the kernel printed "ok" but
   never executed interactive Forth deep enough to hit
   the dispatch fault. The virt switch exposed this.

2. **Substring-green ≠ correct-green.** The test
   assertion `'7' in response` matched `-37`. The
   Phase 4 "3 4 + . = 7 PASS" was a false positive
   manufactured by the check, not the kernel.
   test_arm64_boot.py needs anchored/delimited
   matching before committing.

3. **Executed-green ≠ covered-green.** x86 B6b's
   17/17 interactive tests all passed, but the
   Forth-coded INTERPRET was never exercised: x86
   used `T-ALIAS` to the kernel's native assembly
   INTERPRET. The green was real but covered a
   different code path than it appeared to.

These three lessons apply directly to C.3 (Cortex-M)
first contact — each claim of "X works" must specify
which code path was actually executed.

## Phase C.1 gate status: NOT MET

The earlier green was the false positive. Interactive
Forth on ARM64 virt is not yet proven — EXECUTE works
(INTERPRET fix), EMIT/KEY work (backward-branch fix),
but no verified correct output from any dictionary
word due to DOT/NUMBER bug #33c.

## DTB collision (fixed earlier, 2026-07-07)

QEMU virt places DTB at 0x40000000-0x40100000.
Initial A64-ORG=0x40000000 caused ROM overlap error.
Fixed: A64-ORG=0x40100000 clears the DTB. Committed
to private repo as fbd17fa.

## Queued follow-ups

1. Fix DOT/NUMBER (next session, start with EMIT-
   bypass experiment)
2. Fix test_arm64_boot.py assertions before committing
3. VBAR_EL1 crash-reporting stub
4. Embed boundary assertion (oldest debt)
5. Floored-division semantics (ARM64 SDIV truncates;
   /MOD has correction code but untested)
