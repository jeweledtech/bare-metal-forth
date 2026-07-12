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

## Verification of #33a/#33b — 2026-07-10

**Provenance:** All three ARM64 source files
(`target-arm64.fth`, `arm64-asm.fth`,
`thumb2-asm.fth`) are PRIVATE-OWNED and gitignored
in the public repo (`.gitignore:82-84`). Bug #33a
was introduced in the private copy; fix landed at
private repo fa36980; the public working-tree copies
carry the fix via sync.

**Static verification:** Fresh build via
BUILD-ARM64-VIRT (8032 bytes, 147 symbols, zero
unresolved). All three B.NE backward branches
decoded from the binary:

| Offset | Instruction | imm19 | Word |
|--------|-------------|-------|------|
| +0x0DAC | 0x54FFFFC1 | -2 | KEY |
| +0x0DF0 | 0x54FFFFC1 | -2 | EMIT |
| +0x1120 | 0x54FFFF61 | -5 | CMOVE |

All small negative offsets. No 648KB wild jumps.

**Dynamic verification:** ARM64 virt boots to `ok`
prompt over PL011 TCP serial. INTERPRET runs (colon
defs accepted). EMIT/KEY poll loops work (interactive
I/O functional). #33a and #33b are closed.

**Grep audit:** Zero instances of T-ADDR flowing
into any backward-branch emitter. `thumb2-asm.fth`
`T2W-B-BACK,` has zero callers and carries the
bug #33 warning comment.

**Test assertions fixed:** `test_arm64_boot.py`
Phase 4 checks now use `has_word()` with `\b`
anchors instead of bare `in` — eliminates the
`'7' in '-37'` false-positive pattern.

## EMIT-bypass experiment results — 2026-07-10

### Round 1: arithmetic via EMIT

**Single-digit NUMBER:** Correct. `0` through `9`
each push the expected integer (verified via EMIT:
`0 EMIT` → 0x00, `9 EMIT` → 0x09).

**Multi-digit NUMBER:** Completely broken. All
two-digit literals (`10`, `48`, `65`) fail to parse
(`?` error). This is separate from the stack bug.

**Arithmetic via EMIT (bypasses DOT entirely):**

| Expression | Expected | Got | Hex |
|-----------|----------|-----|-----|
| 1 1 + | 2 | 2 | 0x02 |
| 2 3 + | 5 | 4 | 0x04 |
| 5 3 - | 2 | -2 | 0xFE |
| 3 2 * | 6 | 2 | 0x02 |
| 8 DUP + | 16 | 16 | 0x10 |
| 8 8 + 8 + 8 + 8 + 8 + | 48 | 9 | 0x09 |

**Discriminating pair:** `2 3 +`=4 (fails) vs
`8 DUP +`=16 (works). Both execute `+` on two
cells. The only difference: in the failing case
both operands were pushed by INTERPRET's number
path; in the working case the second came from
DUP. If `+` were broken, `DUP +` would fail too.

### Round 2: TOS-overwrite discriminator

Hypothesis: INTERPRET's number-push path stores
at TOS without advancing SP. Consecutive literals
overwrite each other; primitives then read a stale
cell below SP.

| Test | Got | Healthy | Overwrite (stale=1) |
|------|-----|---------|---------------------|
| `2 3 DROP EMIT` | **0x01** | 0x02 | 0x01 ✓ |
| `7 DROP EMIT` | **0x01** | — | 0x01 ✓ |
| `5 DROP EMIT` | **0x01** | — | 0x01 ✓ |
| `9 DROP EMIT` | **0x01** | — | 0x01 ✓ |
| `2 3 SWAP DROP EMIT` | **0x03** | 0x03 | 0x03 ✓ |
| `2 3 OVER EMIT` | **0x01** | 0x02 | 0x01 ✓ |

Every row matches the overwrite theory. The stale
cell is consistently 1 across all tests.

**Confirmed: interpret-mode number pushes net zero
cells** — consecutive literals overwrite one slot
while primitive-pushed cells (DUP, OVER) occupy
their own. Leading mechanism: missing SP-advance
in MC-INTERPRET-ARM64's NUMBER-success path (#33b's
sibling branch); source inspection will confirm.

### Retrodiction of all earlier data

All six Round 1 results now have a single explanation:

- `2 3 +`=4: only one cell (3) pushed; `+` reads
  3 and stale(1) → 3+1=4 ✓
- `5 3 -`=0xFE: only one cell (3); `-` reads 3
  and stale(1) → 1-3=-2 ✓ (order preserved,
  NOS=stale is first operand)
- `3 2 *`=2: only one cell (2); `*` reads 2
  and stale(1) → 1*2=2 ✓
- `1 1 +`=2: stale(1) coincidentally equals the
  intended first operand ✓
- `8 DUP +`=16: DUP copies TOS without going
  through INTERPRET's number path — SP advances
  correctly, giving two real cells ✓
- Chain `8 8 + ...`=9: first `+` gets 8+stale(1)=9;
  then `8` overwrites 9 with 8; next `+` gets
  8+stale(1)=9 again; repeats ✓

The DOT constraint table is a consequence: DOT's
digit-extraction code is probably correct, but it
receives wrong input because the number it's
printing was computed via broken stack state.

### Next step

Inspect MC-INTERPRET-ARM64's number-success path
in target-arm64.fth — the sequence between NUMBER
returning and INTERPRET looping. The fix is likely
a missing SP-advance (EMIT-PUSH or equivalent)
before or after the store. Compare with the
FIND-success path that was fixed for #33b.

## WIP: deeper investigation — 2026-07-10

### Finding: INTERPRET stack leak identified

Source inspection of MC-INTERPRET-ARM64's NUMBER
path found the exact leak site. After FIND fails
(line 1851), it returns `(addr len FALSE)`,
preserving its input. The `2DUP` at line 1850 made
a copy for FIND; FIND preserved it on failure. After
`DROP` at line 1881 (removes FALSE), two copies of
`(addr len)` remain. The subsequent `2DUP` + NUMBER
+ `-ROT 2DROP` cleans only one copy — the other
leaks.

**Candidate fix:** Add `S" 2DROP" T-COMPILE-NAME`
between lines 1881 and 1882. Verified by stack trace
through both success and failure NUMBER paths.

**Retrodiction confirmed:** stale cell = 1 IS the
`len` field from the leaked `(WORD-BUF len)` pair —
all test inputs are single-digit words (len=1).

### Finding #33d: colon definition hangs INTERPRET

`: T7 7 EMIT ;` produces no `ok` after `;` — the
compile never returned to the interpreter loop.
Subsequent `T7` gets no echo at all, consistent
with a hung interpreter rather than a silently-
executing word. T7 may never have been defined.

**Evidence (leak-fixed image, SHA256 695abda...,
private commit 133e211):** compile output `b': T7
7 EMIT ;'` (echo only, no `ok`, no `?`), execute
output `b''` (no echo of "T7", no output). Leak
fix did NOT change this behavior.

"Colon defs don't execute" and "compile hangs
INTERPRET" are different bugs with different
suspects — the latter points at `;`'s return path
or the compile loop, not the colon runtime.
Discriminator queued: send `: T7 7 EMIT ;` then
`1 EMIT` on the same connection — if `1 EMIT`
produces nothing, interpreter is confirmed hung
at compile time.

### Finding: ALL comparison words inverted

Table below taken through contaminated instrument
(pre-leak-fix); inversion observation survives on
the fixed image (`5 0< → 0xFF`, `0 0= → 0x00`
post-fix) but individual rows require re-derivation.

Runtime probing (not source analysis) established:

| Test | Expected | Got |
|------|----------|-----|
| `5 0= EMIT` | FALSE(0) | 0x00 ✓ |
| `0 0= EMIT` | TRUE(-1) | **0x00** ✗ |
| `5 0< EMIT` | FALSE(0) | **0xFF** ✗ |
| `0 0< EMIT` | FALSE(0) | **0xFF** ✗ |
| `5 0> EMIT` | TRUE(-1) | **0x00** ✗ |
| `0 0> EMIT` | FALSE(0) | 0x00 ✓ |
| `5 NEGATE 0< EMIT` | TRUE(-1) | **0x00** ✗ |
| `5 NEG NEG 0< EMIT` | FALSE(0) | **0xFF** ✗ |

Every non-trivial comparison returns the opposite
of expected. DOT's `-31` for input 5 is explained:
DOT's `0<` returns TRUE for positive input, causing
NEGATE(5)=-5, then (DOTR) on the unsigned magnitude
produces `31`.

### Provenance verified — no stale artifact

Fresh hash-verified build reproduced the inversion
identically. The ?DUP "contradiction" dissolved:
`5 ?DUP EMIT` was non-discriminating (both paths
yield 0x05). The discriminating test `5 ?DUP DROP
EMIT` → 0x01 confirmed ?DUP IS broken (CMP W0,W0
never pushes), consistent with source. Source
matches runtime — no stale binary.

### QEMU CSINC exonerated

Self-contained probes with immediate operands
(no stack involvement), capstone-verified bodies,
hashed at boot:

| Probe | Operand | CSINC cond | Expected | Got |
|-------|---------|-----------|----------|-----|
| control | MOVZ #1 (no CSINC) | — | 0x01 | 0x01 ✓ |
| pos5 | MOVZ #5 | GE | 0x00 | 0x00 ✓ |
| neg5 | MOVN #4 (-5) | GE | 0x01 | 0x01 ✓ |
| zero | MOVZ #0 | GE | 0x00 | 0x00 ✓ |

CSINC executes spec-correct. All four comparison
words (`0=`, `0<>`, `0<`, `0>`) encode spec-correct
conditions — capstone independently renders them as
`cset eq`, `cset ne`, `cset lt`, `cset gt`.
The instruction and the encoding are both right.

### XOR removal RESCINDED

The earlier "remove `1 XOR` in `A64-CSET,`" fix
was two wrongs canceling. The emitter produces
spec-correct encodings, QEMU executes them to spec,
and the XOR is doing what the ARM manual says it
should. The "noxor patch" compensated for the real
bug (still unidentified) and would have broken the
emitter the instant the real bug was fixed.

**Anti-lesson:** a patch that makes symptoms
disappear is not a fix until the mechanism is
closed.

### Four-links verification (post-leak-fix image)

On the leak-fixed image (private commit 133e211),
all four links to dictionary `0<` verified clean:

1. **Bytes:** capstone decodes 0< body at +0x08D8
   as POP/CMP #0/CSET LT/NEG/PUSH/NEXT — correct.
2. **Dispatch:** marker patch (MOVZ #0x2A) at
   +0x08D8 prints 0x2A — execution reaches the
   right address.
3. **Input:** identity patch (POP→NOP→PUSH) prints
   0x05 — the word receives 5.
4. **CPU:** self-contained CSINC probe (immediate
   operands, no stack) returns spec-correct results.

Yet `5 0< EMIT` on the unpatched image returns
0xFF. All four links verified clean, result still
wrong. One of the verifications does not cover the
failing configuration.

**Gap identified:** byte-verification of 0<'s body
was never performed on the *unpatched, failing*
image at runtime. Every probe booted patched files.
The file bytes are trustworthy (deterministic build)
but memory-at-execution-time is unverified. If any
init pass, relocation, or self-modification writes
over dictionary code after load, the paradox
dissolves — and patched-body probes would never
see it because they'd get the same treatment.

### Stack leak contaminated earlier probes

The leak fix changed arithmetic probe results:
`2 3 + EMIT` was 0x04 (wrong), now 0x05 (correct).
`5 3 - EMIT` was 0xFE (wrong), now 0x02 (correct).
The earlier session's conclusion "arithmetic
primitives are internally correct" was false —
reached by reading contaminated instrumentation.
Any conclusion from stack-borne probes before the
leak fix requires re-derivation, not grandfathering.

`5 .` shifted from -31 to -30. The leak was inside
DOT's computation. Remaining wrongness should be
accounted for by: inverted comparisons (0<) +
broken ?DUP (?DUP never pushes, mangling the
digit loop's termination). Falsifiable prediction:
after the ?DUP fix and resolution of the (still-
unidentified) `0<` mechanism, `5 .` = `5`.

### Lesson: observation beat reasoning (updated)

Session scoreboard: five hypotheses killed by cheap
probes, zero killed by reasoning, two wrong fixes
stopped before commit. The `?DUP EMIT` non-
discriminating test, the all-zeros CSINC probe, and
the "QEMU is broken" claim each required one more
probe to correct. Static analysis found the leak
mechanism; runtime probes did everything else.

## Phase C.1 gate status: PARTIALLY MET

INTERPRET, EMIT, KEY work. #33a and #33b closed.
#33c characterized (stack leak + comparison
inversion) but blocked on provenance verification.
#33d (colon def execution) is a new gate failure.

## DTB collision (fixed earlier, 2026-07-07)

QEMU virt places DTB at 0x40000000-0x40100000.
Initial A64-ORG=0x40000000 caused ROM overlap error.
Fixed: A64-ORG=0x40100000 clears the DTB. Committed
to private repo as fbd17fa.

## Queued follow-ups (sequencing matters)

1. **Provenance reset** — clean rebuild, sha256
   source tree + image, boot by hash, re-run the
   six-probe comparison table. No analysis until
   source↔binary lineage is proven.
2. If mystery persists: **marker-patch** on 0< body
   (MOV W0,#0x2A / PUSH / NEXT). 0x2A output →
   that code IS what runs (check analysis scripts
   for host/target address mixing). 0xFF still →
   execution never reaches that code (hunt second
   emitter or T-ALIAS path).
3. **Full-body runtime dump** of 0< (all 5 insns
   after boot) compared word-for-word against image.
4. Fix stack leak (add 2DROP) — but NOT until
   provenance is clean.
5. Do NOT fix ?DUP until step 1 explains why
   runtime ?DUP currently works despite buggy source.
6. Fix multi-digit NUMBER (separate bug)
7. Investigate #33d (colon def execution failure)
8. VBAR_EL1 crash-reporting stub
9. Embed boundary assertion (oldest debt)
~~10. Fix test_arm64_boot.py assertions~~ Done
   2026-07-10: anchored regex matching

## Resolution: Bug #33c — CLOSED (2026-07-11)

**Fix:** Private commit `133e211` adds a `2DROP`
in MC-INTERPRET-ARM64 between the FIND-failure
DROP and the NUMBER 2DUP, removing the preserved
`(addr len)` pair that leaked one data-stack cell
per interpreted number. Same failure class as
the #33b FIND-success fix (stack cleanup after
the 2DUP'd token copy), different idiom.

**Hypothesis correction:** The pre-fix working
hypothesis was a missing SP-advance in emitted
ARM64 code. Inspection located the defect at the
Forth source level instead — a missing `2DROP`
stack cleanup. The SP-advance narrative was
reasoned and wrong in detail; the `2DROP`
mechanism is what the source and the probes show.
Recorded per observed-vs-reasoned discipline.

**Verification (2026-07-11):** Two independent
QEMU runs on kernel SHA256 `695abda725b363...`,
built from source byte-verified against `133e211`.
Probes 1–6 pass in both runs:

| # | Input | Expected | Observed | Establishes |
|---|-------|----------|----------|-------------|
| 1 | `7 EMIT` | 0x07 | 0x07 | single literal reaches stack |
| 2 | `5 7 EMIT EMIT` | 0x07 0x05 | 0x07 0x05 | distinct cells (core symptom) |
| 3 | `8 DUP + EMIT` | 0x10 | 0x10 | mixed primitive+literal |
| 4 | `2 3 DROP EMIT` | 0x02 | 0x02 | stale-cell question answered |
| 5 | `2 3 + EMIT` | 0x05 | 0x05 | continuity (133e211) |
| 6 | `5 3 - EMIT` | 0x02 | 0x02 | continuity (133e211) |

**Stale-cell question: answered.** The pre-fix
constant-1 was the leaked `len` field of the
`(addr len)` pair — all test inputs are single-
digit words (len=1). Post-fix, probe 4 observes
0x02. Confirmed from this session's observation,
not the commit message.

**Compile-mode LITERAL verdict: INCONCLUSIVE.**
Blocked by #33d — definition step produces no
`ok` and no `?`; execution of the defined word
is never reached. LITERAL itself is not tested
until #33d is resolved.

**Gates at close:** ARM64 interactive Phases 1–3,
14/14; x86 suite 192/192 across 16 suites
(baseline corrected from "190+" per CLAUDE.md;
`test-pipeline` excluded by design).

## Bug #33d — colon definition non-response (OPEN)

**Observed (2026-07-11, kernel `695abda7...`):**
`: T5 7 EMIT ;` echoed with no `ok` and no `?`
within the 3s response window; all subsequent
input returned nothing. Independently reproduced
in Phase 4 gate — `: SQ DUP * ;` shows the
identical signature and cascades five subsequent
test failures (internal session evidence,
untracked):

```
  FAIL: : SQ DUP * ; 7 SQ . = 49
  FAIL: IF true = 42
  FAIL: IF false = 99
  FAIL: DO/LOOP
  FAIL: Undefined word -> ?
  FAIL: HEX FF = 255
```

The non-response begins at the definition step.
Execution of the defined word is never reached.

**Open question:** dead interpreter vs. STATE
stuck in compile mode. If `;` is mishandled in
the compile-mode branch of MC-INTERPRET-ARM64,
subsequent input is silently consumed as compile
tokens rather than executed — no `ok` prints.
Observationally indistinguishable from a genuine
hang in this session's captures.

**Suspects (all in scope):**
1. The compile loop (`:` entering compile mode,
   WORD-loop token processing, STATE management)
2. The `;` return path (compiling EXIT, resetting
   STATE, returning to the interpreter loop)
3. STATE stuck in compile mode — `;` mishandled,
   subsequent input consumed as compile tokens

**First experiments for the fix arc:**
(a) After the non-response, send a bare `;` and
    a bare token, check for `ok` — cheap
    discriminator between dead and capturing.
(b) DUMP the definition's dictionary entry before
    any execution attempt — bytes before boot.

**Priority:** Ahead of multi-digit NUMBER. #33d
blocks Phase 4 close condition; multi-digit
NUMBER does not block it as hard. Decided
2026-07-11.

### Phase 4 number-I/O cluster (pre-registered)

Phase 4 gate failures include a cluster of 4
number-I/O failures with up to 3 distinguishable
threads:

**Thread A — multi-digit NUMBER input parsing:**
`10 1 - .` → `10 ?` — "10" is two digits, cannot
be parsed by single-digit-only NUMBER. Directly
observed.

**Thread B — DOT output formatting (single-digit
inputs):** `3 4 + .` → `70`; `6 7 * .` → `-40`.
Inputs are single-digit (probes 1–6 confirm
single-digit NUMBER works). The wrong output is
from DOT's formatting path, not input parsing.
Distinct from Thread A.

**Thread C — floored division:** `-7 3 / .` → `-1`.
Cross-ref: floored division is pre-registered
(tools/floored-division has codegen but ARM64 `/`
implementation status is unaudited). Observed `-1`
matches neither truncated division (-2) nor floored
division (-3). Unexplained — may be Thread B (DOT
misformatting a correct `-3`) or a genuine division
defect, or both. Not resolved by this session.

HYPOTHESIS (not observed): DOT's digit extraction
loop may share the division path, connecting
Threads B and C. Plausible but unverified — DOT
source not audited this session.

NOTE: Serial response attribution across sequential
probes in the Phase 4 capture is unreliable — a
stray `70` appears after the `10 ?` response, which
may be delayed output bleeding across probe
boundaries.

## Resolution: Bug #33d — CLOSED (2026-07-11)

### Localization chain

The defect was localized in three layers, each
moved by a specific experiment:

1. **Dispatch logic → `:`'s body.** Source audit
   found the compile-mode IMMEDIATE check correct,
   `;` correctly marked. E0 (NOOP, CR) proved
   EXECUTE→DOCOL works. E3b showed `:` partially
   wrote a header then SYSVARS zeroed — crash is
   inside `:`'s body, not the dispatch.

2. **`:`'s body → CMOVE primitive.** E3b dump:
   link/len/name written correctly, ALIGN's pads
   absent (name bytes intact), SYSVARS wiped 528+
   bytes contiguously. Pattern matches a runaway
   copy loop, not a wild jump.

3. **CMOVE → SUB/SUBS opcode.** Byte decode of the
   emitted kernel: CMOVE's loop decrement was
   `SUB W2,W2,#1` (opcode 0x51, no flag update).
   The `B.NE` loop-back consumed stale NZCV flags
   from unspecified upstream code.

### Mechanism

The count cannot terminate the loop. The behavior
is nondeterministic on upstream flag state:
- Stale NE=true (observed): loop runs until a
  store into unmapped memory raises an unhandled
  data abort. Source=WORD-BUF (0x40120200),
  dst=HERE (0x40101F64+). After the 2-byte name,
  WORD-BUF contains zeros → copies zeros through
  the dict area, through SYSVARS (zeroing STATE/
  HERE/LATEST/BASE/TIB/WORD-BUF), overwrites its
  own source region, continues until the abort.
- Stale NE=false (not observed): exits after one
  byte — silent short-copy, corrupted name, FIND
  never matches the word.

Note: CBZ (the zero-count guard) does NOT set
flags. The stale flags come from whatever flag-
setting instruction last ran upstream (inside
EXECUTE, DOCOL, or the caller's NEXT sequence).

### First-exercise path

No passing probe before this fix ever called CMOVE
at runtime on the ARM64 target. WORD parses byte-
by-byte into WORD-BUF (C!). The host's T-HEADER
builds target dictionary entries using C, in a
loop. CMOVE's first runtime invocation was `:`
copying the parsed name — the bug was latent from
build day.

### Class audit: branch-side completeness

Every `COND-* A64-BCOND` site in target-arm64.fth:

| Line | Context | Flag-setter | Sound? |
|------|---------|-------------|--------|
| 356 | ?DUP | CMP W,W | ✓ |
| 447 | ABS | CMP# W,0 | ✓ |
| 622 | /MOD floor | CMP# W,0 | ✓ |
| 640 | MOD floor | CMP# W,0 | ✓ |
| 655 | /MOD variant | CMP# W,0 | ✓ |
| 667 | MIN | CMP W,W | ✓ |
| 676 | MAX | CMP W,W | ✓ |
| 815 | (LOOP) | CMP W,W | ✓ |
| 923 | KEY poll | TST W,W | ✓ |
| 938 | EMIT poll | TST W,W | ✓ |
| 1106 | CMOVE loop | **SUB** | **BUG** |

CMOVE was the only site. All others use flag-
setting operations (CMP, CMP#, TST).

Audit caveat (lesson for the method): presence
of a flag-setter verifies the flags are fresh but
does not verify the branch *condition* is the
right one. Line 815's check passed this audit, but
#33e (below) reveals a DO/LOOP defect that this
frame cannot catch — a GE where LT is needed, or
a wrong offset, produces fresh-but-wrong branching.

### Two defects, same arc

**Defect 1 (crash cause):** `A64-SUB#,` → `A64-SUBS#,`
at CMOVE's loop decrement. Private commit `5f7366e`.

**Defect 2 (latent, masked by defect 1):** Missing
HERE-advance after CMOVE in `:`, `CREATE`, and
`CONSTANT`. After `C,` writes the length byte,
CMOVE copies the name but does not advance HERE.
ALIGN then pads from the un-advanced position,
overwriting name bytes with zeros. Three instances
of the same pattern found by class audit. Private
commit `d2b8098`.

### Byte evidence: Q2 header dump (post-fix)

After `: Q2 ;` on kernel `d80c62ed…`:
```
0x40102010: 0x40102000  link → previous ✓
0x40102014: 0x00325102  len=2 "Q2" pad=0x00 ✓
0x40102018: 0x40100100  CFA → DOCOL ✓
0x4010201C: 0x40100120  body[0] → EXIT ✓

SYSVARS: STATE=0 HERE=0x40102020 LATEST=0x40102010
         BASE=0xA — all intact ✓
```

### Verification probes

Broken kernel (`695abda7…`, pre-fix):
- `: T5 7 EMIT ;` → no `ok`, no `?` (E3b)
- `: Q1 ;` → SYSVARS zeroed (E3b)
- E2 revival → no response (dead, not capturing)

Fixed kernel (`d80c62ed…`, commits `5f7366e`+`d2b8098`):

| # | Probe | Expected | Observed |
|---|-------|----------|----------|
| 1 | `: T0 ;` | ok | ok ✓ |
| 2 | `: T5 7 EMIT ; T5` | 0x07 | 0x07 ✓ |
| 3 | `: SQ DUP * ; 7 SQ EMIT` | 0x31 | 0x31 ✓ |
| 4 | `: T0 ;` (redefine) | ok | ok ✓ |
| 5 | regression set | 0x07/0x05 | ✓ |
| 6 | `CREATE XX` | ok | ok ✓ |
| 7 | `5 CONSTANT FV` `FV EMIT` | 0x05 | 0x05 ✓ |
| 8 | Q2 header dump | well-formed | ✓ |

Synced re-verify (same hash, rebuilt from
committed private source): P2, P3, P6, P7 pass.

Gates: ARM64 Phases 1–3 14/14; x86 192/192.
Phase 4 improved 14/24 → 17/24 (3 cascade
failures flipped; 7 remain = Threads A/B/C + #33e).

### #33c LITERAL verdict — CONFIRMED WORKING

Probe 2 (`: T5 7 EMIT ; T5` → 0x07) exercises
the full compile-mode path: interpret `7` → STATE
is -1 → LITERAL called → compiles `LIT 7` into
definition → `;` executed → T5 called → DOCOL →
LIT pushes 7 → EMIT sends 0x07 → EXIT.

The INCONCLUSIVE verdict from the 2026-07-11
session (blocked by #33d) is now closed as
CONFIRMED WORKING. No separate LITERAL finding
needed.

### VBAR_EL1 promotion rationale

This bug cost three experiment rounds to localize
because the data abort was completely silent — no
register dump, no fault address, no exception
vector output. The VBAR_EL1 crash-reporting stub
(queued since the initial ARM64 port) would have
printed "DATA ABORT at 0x4014xxxx" as the first
line of evidence, collapsing the E0→E3→E3b→decode
chain into a single observation. Promoted from
polish to next-in-arc (ahead of DTB assertion).

## Bug #33e — DO/LOOP iterates once (OPEN)

**Observed (2026-07-11, kernel `d80c62ed…`):**
`5 0 DO 7 EMIT LOOP` produces one 0x07 byte then
`ok`. The interpreter is alive and responsive
after — `(LOOP)` exits on the first pass instead
of continuing for 5 iterations.

**Cascade-unmasking provenance:** This defect was
hidden behind #33d — the CMOVE crash killed the
interpreter before any DO/LOOP could execute. The
prior session's Phase 4 raw output showed "2" for
the DO/LOOP test, attributed to Thread B (DOT
formatting). The targeted probe (`7 EMIT` inside
the loop, no DOT) reveals a genuine control-flow
defect.

**Branch-side audit caveat:** The class audit
(above) checked line 815 — `(LOOP)`'s branch site
— and found `CMP W,W` preceding `COND-GE BCOND`.
The flag-setter IS present and correct. The defect
is therefore NOT the CMOVE-class "missing flags"
bug. Suspects:

1. **Backward-branch offset** — this target's prior
   bugs include address-mixing in backward-branch
   emitters (fa36980). A wrong offset exits the
   loop or branches to the wrong location.
2. **Condition sense / operand order** (leading
   hypothesis alongside #1) — `(LOOP)` increments
   index then branches back if not done. With
   `CMP index, limit` + `B.GE exit`: after first
   increment index=1, limit=5, 1 >= 5 is false →
   branch-back taken, loop continues. BUT if the
   operands are swapped (`CMP limit, index`) then
   5 >= 1 is true → exits after one iteration.
   **This matches the observed single-iteration
   behavior.** Must validate against the x86
   `(LOOP)`'s actual crossing semantics — this
   kernel's DO/LOOP stores (index limit) on the
   return stack and LEAVE sets I=LIMIT to force
   exit, so the correct test is `index >= limit`
   with index as first operand.
3. **Index increment** — if `(LOOP)` increments by
   the limit instead of by 1, or uses the wrong
   register, the index could jump past the limit
   on the first pass.

All three are hypotheses. The #33e audit must
decode `(LOOP)`'s emitted bytes (same method that
convicted CMOVE) before proposing a fix.

**Possible DOT entanglement:** DOT's digit
extraction loop uses division in a counted or
conditional loop. If that loop is `(LOOP)`-based,
#33e may be the shared root cause of Thread B
(wrong DOT output on single-digit inputs). Noted
as possibility; not claimed without DOT source
audit.

**Correction:** `HEX FF DECIMAL .` → `FF ?` was
previously categorized as a #33d cascade failure.
Re-categorized as Thread A (multi-digit NUMBER) —
"FF" is two hex digits, cannot be parsed by the
single-digit-only NUMBER implementation.

### Updated Phase 4 categorization (post #33d fix)

7 remaining failures on kernel `d80c62ed…`:

| Test | Output | Thread |
|------|--------|--------|
| `3 4 + .` = 7 | "70" | B (DOT) |
| `10 1 - .` = 9 | "10 ?" | A (multi-digit) |
| `6 7 * .` = 42 | "-40" | B (DOT) |
| `-7 3 / .` = -3 | "-1" | B/C (unexplained) |
| `7 SQ .` = 49 | "10" | B (DOT) |
| `5 0 DO I . LOOP` | "2" | **#33e** |
| `HEX FF .` = 255 | "FF ?" | A (multi-digit) |

Priority queue: **VBAR_EL1 stub → #33e (DO/LOOP) →
DTB assertion → multi-digit NUMBER.** Decided
2026-07-11 — pay the crash-reporting setup cost
before the next fix arc; every localization since
the ARM64 port has paid the silent-abort tax.
#33e is Phase 4 close-condition material AND may
resolve Thread B if DOT's loop is entangled;
DTB and NUMBER are functional items that don't
block the interactive gate.
