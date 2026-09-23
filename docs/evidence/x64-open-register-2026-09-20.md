# x86 front end: the open register, 2026-09-20

**What this file is.** One place where every open finding in the x86
arc is read, replacing the `Open after (n)` / `Open after (a)` /
`Open after (o)` lines scattered through three closing sections. Those
lines are historical records of what was open at a moment and must not
be edited to stay current; this file is current and carries no history.

**Order of work (owner ruling, 2026-09-20): (aa) lands before (s).**
(s) repairs six forms sitting on an arm that mis-renders 219 opcodes.
Landing (s) first turns six reds green over a floor still wrong beneath
them and patches the two-byte map twice instead of building it once.
(s)'s pre-registration survives — the census, the address sequence, the
boundary sentence — but its differential figures are taken again after
(aa).

**Authority.** For anything with a red, `xfail_names[]` in
`tools/translator/tests/test_x86_decoder.c` is the list and this file
is a reading of it. `open_register_is_exactly_the_xfail_list` in that suite parses the
table below and fails the build if the two disagree, so this file
cannot drift (owner item 7). For a finding
with no red, this file is the only record, which is why each one
carries the **condition that mints it** rather than an intention.

## (aj) CLOSED 2026-09-22 — stage 1 of the identity consumer

**The report now carries its first instruction-derived field.** Every
other per-function field — the classification, `has_port_io`,
`has_mmio`, the HAL calls — is set from a matched entry in the import
table, which is 320 hardware functions across eight drivers and **zero**
resting on an instruction. This one is read out of the code:

```json
"mapped_regions_analysed": true,
"mapped_regions": [
  { "api": "MmMapIoSpaceEx",
    "call_site": "0x1C0012B58",
    "park_site": "0x1C0012B70",
    "park_indexed_displacement": "0xD0" }
]
```

**Every value matches the census and the hand-check byte for byte**, and
**the key name carries the claim**: that park is
`mov %rcx,0xd0(%rax,%rbx,8)`, a scaled-indexed array element, so
`park_offset` would overstate it and only
`park_indexed_displacement` is true. The test asserts the **key**, not
just the value, which is what stops the weaker statement passing as the
stronger one.

**The statement is a negative about the device, and that is the
result.** This driver maps a region, parks the base, and the only
identity-checked load of that slot reaches `MmUnmapIoSpace`; it drives
a **port-mapped** device. Against *0 of 320*, a proven negative is the
first entry of any kind.

**Two things the first implementation got wrong, both found by running
it:**

- It looked for a store whose source is the return register. The return
  is **copied first** (`mov %rax,%rcx`), so it reported *"not stored"*,
  which is **false** — it is stored, through one copy. Now a small
  def-use set follows the value.
- It stopped at the end of the call's basic block. The park sits past
  that boundary, so the walk now continues in program order.

**Gate: exactly one name.** `test_mmio_consumer` is back to an empty
expected-failure list.

## Open, with a red (14)

**The table is the whole list, across every suite.** Until 2026-09-21
the executable check compared it against `test_x86_decoder.c`'s
`xfail_names[]` alone, so a red registered anywhere else lived outside
the check and was carried in prose as "not in the table below". **Two
such reds appeared within a day**, which is a pattern rather than an
exception, and it is exactly the condition the trap-row work exists to
prevent: a list checked by nothing.

**The check now asserts the UNION** of `xfail_names[]` across all five
suites that carry one, parsed from their sources, with the suite count
asserted so a renamed suite cannot shrink the union silently. The
`suite` column says where each red lives.

| letter | red | suite | what is wrong |
|---|---|---|---|
| (d') | `x64_RED_rex_b_push_r12` | decoder | REX.B not applied to an opcode-embedded register |
| (f) | `x64_RED_byte_reg_sil_under_rex` | decoder | reg 4-7 at size 1 under REX is SPL/BPL/SIL/DIL |
| (g) | `x64_RED_truncated_imm32_refused` | decoder | immediate read past the code buffer |
| (g) | `x64_RED_truncated_disp32_refused` | decoder | displacement read past the code buffer |
| (p) | `x64_RED_p_movsxd_decoded` | decoder | `63` recognised, not just length-consumed |
| (p) | `x64_RED_p_imul_imm_decoded` | decoder | `69`/`6B` recognised |
| (r1) | `x64_RED_r1_push_iz_opsize16` | decoder | `66 68` Iz read at a fixed 4 bytes |
| (r2) | `x64_RED_r2_test_eax_iz_opsize16` | decoder | `66 A9` likewise |
| (r3) | `x64_RED_r3_test_ev_iz_opsize16` | decoder | `66 F7 /0` likewise |
| (u) | `x64_RED_u_0f_map_matches_oracle` | decoder | the hand-typed no-ModRM list vs the oracle |
| (v) | `x86_RED_v_addr_size_prefix_disp16` | decoder | legacy `67` makes mod=10 a disp16 |
| (y) | `x64_RED_y_lea_register_form_invalid` | decoder | `8D C0` LEA register form is #UD |
| (ab) | `x64_RED_ab_two_byte_arm_ignores_mandatory_prefix` | decoder | the arm never reads `66`/`F2`/`F3` |
| (t) | `unknown_0f_modrm_recovery` | decoder | `0F 0D C0` is #UD and is accepted |
| (aw) | `sem_RED_aw_movcr_write_set` | lifter | MOV_CR/MOV_DR lift with no dest, so the walk stops at a control-register move whose write set it could state |

## (s) CLOSED 2026-09-21 — and with it the decoder queue

**Three mechanisms, all derived from the pinned oracle rather than
typed:**

| mechanism | opcodes | what was wrong |
|---|---|---|
| a trailing `imm8` after the ModRM | `0F 70`, `C2`, `C4`, `C5` | the byte was never consumed, desynchronising the walk by one |
| no ModRM at all | `0F AA` RSM | the arm consumed one that is not in the encoding |
| a `mod` field the hardware **ignores** | `0F 20`–`23` | honouring `mod=10` read a `disp32` that is not in the stream, inventing four bytes |

Plus **`0F 78`**, handled with its mandatory prefix — `66` is EXTRQ and
`F2` is INSERTQ, both ModRM plus **two** `imm8`. That is a named,
deliberate overlap with (ab), which owns prefix blindness in general and
**stays red**, because its assertion is an inequality on a different
opcode.

**Gate: exactly the seven predicted names.** Every other prediction in
the pre-registration held:

| predicted | observed |
|---|---|
| (u) reports `wrong_opcodes=1: 0F0F` | **exactly that** — `checked=2065 wrong_rows=3` |
| both one-byte sweeps' disagreeing set unchanged | 4 opcodes each, unchanged |
| **14 of 16 inputs must not move at all** | **14 did not move** |
| storport moves by its one PEXTRW row | `nostart` 2 → 1, `undecoded` +1 |
| `operand_ok` and `score` unchanged | unchanged on all 16 |
| the fixture's `.text` walks to exactly 35 lines | **35**, from 37 |

**Missed starts: 18 → 12, and the residual is exactly the attribution
written when (o) closed** — (r3) 8, one per HP driver, and (r2) 4 on
8139too. The 6 (s) rows are gone: storport 1, fixture 5. **The fixture
now has zero missed starts.**

**One instrument repaired on the way, and it is named.** The
shipped-binary check asserted that unknown mnemonics were a minority,
which tripped at 17 of 35 — because after (aa)+(ac) the decoder says
`UNKNOWN` where it used to say `NOP`, and this fixture is a *reds*
fixture. The ratio had stopped measuring what it stood for. It is
replaced by the **exact line count**, which is derived from the
artefact rather than calibrated, is strictly stronger, and **hides no
mixed link**: that signature is checks 1 and 2, which are independent
of the mnemonic. The self-test gained a case for it and is 7 cases, 0
failures.

## (aa) and (ac) CLOSED 2026-09-21

**219 of 256 two-byte opcodes rendered as NOP.** All 18 assignment sites
in the two-byte arm now call `two_byte_nop_or_unknown()`, which returns
`NOP` only for the cells **the screen** calls a no-op, read per full
`(prefix, opcode, ModRM)` byte. Closed through an XPASS gate that fired
on **exactly the ten predicted names** across all 25 suites
(`fix-aa-ac-xpass-gate-2026-09-21.log`).

**Every pre-registered invariant held, checked against the artefact:**

| predicted | observed |
|---|---|
| `operand_ok` and `score` unchanged on all 16 | unchanged on all 16 |
| `mnemonic + opcount + undecoded` conserved, input for input | conserved on all 16 |
| `mnemonic` falls close to zero | ACPI 3,279 to 177; storport 2,327 to 115; pci 2,189 to 42 |
| `opcount` falls only by the non-exempt cells in it | falls by **exactly 2 on each of the eight HP drivers, 16 total** |
| `nostart`, `beyond_extent`, `invalid_at_start` unchanged | unchanged on all 16 |
| ten names flip, and no others | ten, and the 21 that must not flip did not |

**The 16 are the PREFETCHNTA rows** — two in every HP driver, the same
block-copy routine linked eight times — and they leave agreement
*correctly*: the oracle calls them NOP, which is **(ae)**, and the
screen names them. A fix that kept them in the agreement class would
have been agreeing with a wrong oracle.

**Verified still red on the same run**, each for its stated reason:
(t) `unknown_0f_modrm_recovery` asserts `INVALID` and this gives
`UNKNOWN`; (ab) is an inequality that two `UNKNOWN`s still satisfy;
(s)×7 and (u) are length-only and no length changed.

## (ad) CLOSED 2026-09-20

`ad_invalid_does_not_lift_to_nop` is green. The lifter carries
`UIR_INVALID`, and `UIR_UNSET` takes the enum's zero value so a
zero-initialised instruction no longer reads as a no-op. Closed through
an XPASS gate that fired on **exactly one name** across all 25 suites
(`fix-ad-xpass-gate-2026-09-20.log`).

**Predictions, all four checked against the artefact:**

| predicted | observed |
|---|---|
| no corpus figure moves | the 16 decoder dumps are **byte-identical** to the pre-fix baseline, so every differential column is unchanged by construction |
| exactly one XPASS | exactly one, and the decoder suite stayed `pass=85 xfail=30 fail=0 xpass=0` |
| `-t uir` changes one instruction in one input | `8139too.ko` prints **1** `invalid` at `.text+2721`, the predicted address; the other 15 inputs print **0** |
| nothing produces the sentinel | **0** `unset` lines in any of the 16 |
| (af) does not move | `8139too.ko` still prints **845** `nop` lines |
| (control for the check below) | this row has a bracketed first cell and a backticked second cell, `like_this`, and the register check must ignore it |

**The third reader class, enumerated before the line was written**
(owner's addition): sites that zero-initialise a `uir_instruction_t`
and use it without assigning `opcode`, and anything persisting or
comparing a *numeric* opcode. **Both are empty.** Every constructor
assigns on every path — including both lifters' `default:` arms — and
no golden file, serialised form or test compares `-t uir` output or a
literal opcode number. The measured `unset=0` is that enumeration's
confirmation from the artefact rather than from the source alone.

## The decoder queue's exit, ruled 2026-09-20

**The queue ends at (s), whatever it surfaces.** New findings are
lettered, counted and parked on this register; they do **not** enter
the queue. Only a defect that makes one of the four fixes **wrong** may
interrupt it. A defect that makes one **incomplete** is parked.

**The exit was a number: 18 reds.** (aa) 1, (ac) 9, (ad) 1, (s) 7.
**All eighteen are green. THE DECODER QUEUE IS CLOSED.**

What it cost and what it bought, in one line each: nine letters minted
((t), (ab), (aa), (ac), (ad), (ae), (af), (ag), (ah)), four rules
(29–32), eighteen reds closed, and the two-byte map went from reporting
219 of 256 opcodes as no-ops to reporting what it knows and refusing
what it does not.

**What starts now: the identity consumer** — which (ag) established is
**the back half of the pipeline**, not a pass, because
`src/codegen/codegen.c` is a 35-byte placeholder and
`src/optimize/optimize.c` a 30-byte one.

**Parked, and still parked** — they did not enter the queue and do not
now: (ai) 450 rows, (ab), (t), (u)'s `0F 0F`, (ae), (af), (ah), the
ARM64/RISC-V emitter join, (r1)–(r3), (p)×2, (d'), (f), (g)×2, (v),
(y), (q). When those sixteen are green
and the remainder is parked, the decoder queue is closed and the
identity consumer starts. A queue without an exit number ends when
someone gets tired.

## (af) CLOSED 2026-09-21

Seventeen identities the decoder names lifted to `UIR_NOP`. They now
lift to **`UIR_UNMODELLED`**, a third state distinct from `UIR_UNSET`
(nobody assigned) and `UIR_INVALID` (the decoder refused). **No
semantics invented**: `ADC`/`SBB` to `ADD`/`SUB` would drop the carry
and `ROL`/`ROR` to `SHL`/`SHR` would drop the wrap.

Gate fired on **exactly one name** across 26 suites. Decoder dumps
byte-identical on 16 of 16. `hardware_functions` **320 / 0
instruction-derived**, before and after — this fix makes the IR honest,
not read, which is (ag).

**One prediction missed, and the miss is recorded.** The `-t uir`
movement was predicted at 1,089 rows across 10 inputs and observed at
**1,116 across 15**: the prediction was counted in the decoder-dump
population while the lifter walks the translator's own function set.
Counting the same seventeen identities in the lifter's population gives
**1,116 against 1,116** — exact, so nothing over-maps.

**Still owed and still blocked:** the shipped-artefact assertion. The
fixture contains none of the seventeen, measured. (ad) has the
identical debt; **one fixture edit discharges both**, appending an
`SBB` and an `06` past the trailing `RSM` where they shift nothing.

## (af), PROMOTED to prerequisite 2026-09-21

The lifter's `default:` arm at `src/ir/uir.c:442` maps seventeen
modelled x86 identities to `UIR_NOP` — **1,089 corpus rows**: `SBB`
481, `SETcc` 469, `CBW` 52, `CDQ` 32, `LEAVE` 23, `ROR` 14, `ADC` 9,
`ROL` 9, and **zero each** for `CLD`, `LOOP`, `POPAD`, `PUSHAD`, `STD`
and the four `REP_` string forms.

**Parked on 2026-09-20, promoted today, and recorded as a promotion
rather than slipped in.** It is a **dependency of the identity
consumer**: a consumer that reads instruction identity must not read a
no-op where an `SBB` was. Pre-registered separately
(`fix-af-prereg-2026-09-21.md`) because 1,089 rows across 17 identities
is a larger change than (ad)'s single row, and because the fix adds a
**third state** — `UIR_UNMODELLED`, distinct from `UIR_UNSET` (nobody
assigned) and `UIR_INVALID` (the decoder refused) — rather than
inventing semantics for seventeen instructions.

## (ag), minted 2026-09-20: the IR is write-only with respect to instruction identity

**Not a decoder defect — the missing middle of the product, and what
actually bounds tier 2.**

`grep -rn "\.opcode\|->opcode" src/ --include=*.c`, whole tree: the
lifter produces **40 distinct opcodes** and **2 are ever tested by any
analysis** — `UIR_CALL` (`semantic.c:357`) and `UIR_INT`
(`semantic.c:478`). The analysis rests on call edges, interrupts and
operand patterns, never on instruction identity.

**Upgraded 2026-09-20, and the byte counts say something stronger than
the grep did.** "No consumer reads the opcode" and "there is no
consumer" are different claims that cost differently to fix:

| file | size | contents |
|---|---|---|
| `src/codegen/codegen.c` | **35 bytes** | `/* Placeholder - Code generator */` |
| `src/optimize/optimize.c` | **30 bytes** | a placeholder comment |
| `src/api/api_map.c` | **31 bytes** | a placeholder comment |
| `src/decoders/riscv_decoder.c` | **35 bytes** | a placeholder comment |

**Two of the four pipeline stages do not exist.** There is no generic
code generator and no optimizer; `src/codegen/forth_codegen.c` is the
only generator in the tree. Found because `-Wpedantic` calls an empty
translation unit a warning, so the build had been saying it on every
run.

**And the ARM64 half is dead as well**: `uir_lift_arm64_function()` —
287 lines — has **no caller** anywhere outside its own definition, and
its bridge struct is **not** layout-compatible with `a64_decoded_t`
(160 vs 128 bytes; `cc` at 152 vs 120), so it would break on the first
cast anyone wrote.

**Why this matters to the plan, now rather than in three weeks.** The
queue is decoder → consumer → tier 1. This makes "build the consumer"
**writing the back half of the pipeline**, not adding a pass. Same
order, much bigger middle step, and the scope is visible before the
queue arrives at it.

**(aa), (ac), (ad) and (s) together make the IR _true_. None of them
makes it _used_.** Every pre-registration in this arc therefore says
**"no product figure moves"** rather than leaving a reader to infer
analyzer improvement from a decoder repair.

**Minting condition for a red:** a named consumer exists that reads an
identity other than `UIR_CALL` or `UIR_INT`. Until then a red would
assert a feature, not a defect, and the count is the artefact: **2 of
40**.

## (ah), minted 2026-09-21: the multi-architecture statement, as built

**x86-64 only. ARM64 decodes and does not lift. RISC-V has no
decoder.** Its consequence belongs in the **brief**, not only here, so
it is written into `docs/FORTHOS_MULTIARCH_DESIGN.md` beside the Vision
section that promises "the same UBT pipeline — on any silicon", and
beside the tier ladder in
`finding-emission-and-tier1-2026-09-20.md`.

| | measured |
|---|---|
| ARM64 lifter callers | **0** (`uir_lift_arm64_function`, 287 lines) |
| ARM64 bridge vs its decoder struct | **128 vs 160 bytes**, `cc` at 120 vs 152 — would break on the first cast |
| ARM64 decoder coverage | 555 lines, **48.1%** — decoding for a lifter nobody calls |
| RISC-V decoder | **773-byte placeholder comment** |
| floored-division codegen, 3 architectures | **780 lines compiled by nothing** |

**Minting condition for a red:** a caller for the ARM64 lifter exists,
at which point the bridge's layout becomes assertable the way the x86
one now is. Until then a red would assert a feature.

## (ai), parked 2026-09-21: the comparer misreads a prefixed unknown

**Found by (aa)+(ac) and parked, not fixed, under the queue rule.**
`compare_operands.py:208` tests `om == '???'` to reach `undecoded`, but
`dump_starts` appends the decoded LOCK flag, so an unknown instruction
with a `LOCK` prefix prints `???.LOCK` and falls through to
`mnemonic` instead.

**450 rows** across the corpus — ACPI 161, usbxhci 111, storport 94,
HDAudBus 33, pci 31, HP serial 10, i8042prt 6, disk 2, nmap 1, ReactOS
serial 1. Before the fix they printed `NOP.LOCK` and were `mnemonic`
legitimately; now they are unknowns wearing a suffix.

**It breaks no pre-registered invariant** — conservation holds and the
score is unchanged either way — so it does not make (aa)+(ac) *wrong*,
only the classification *incomplete*, which is exactly the case the
queue rule parks. The repair is one predicate (`om.startswith('???')`)
and is **defect-revealing, not concealing**: it moves 450 rows from
`mnemonic` into `undecoded`, making the residual `mnemonic` class
smaller and more honest.

## A standing note, from (ad): when a corpus witness is itself a symptom

(ad)'s single corpus `INVALID` sits inside **(r2)'s desync run** and is
predicted to reach **0** when (r2) lands. **Any fix whose corpus
witness is a symptom of another open defect owes this note**, because
without it a vanished count reads as proof the fix worked, and the red
is the only durable instrument.

## (ae), minted 2026-09-20: the ORACLE is confidently wrong over `0F 18`-`0F 1F`

**The first case in the arc of the oracle being wrong rather than
silent.** Ghidra 12.1.2 names **every one** of the 96 blob cells in
`0F 18`–`0F 1F` `NOP`. Swept over the **full ModRM byte** — 4 prefixes
× 8 opcodes × 256 = **8,192 cells**,
`docs/evidence/x64-nop-range-full-modrm-2026-09-20.log` — objdump names
**2,276 of them**: `PREFETCHNTA`/`T0`/`T1`/`T2`, `PREFETCHIT0` and
`PREFETCHIT1`, the whole MPX family (`BNDLDX`, `BNDSTX`, `BNDMOV`,
`BNDCU`, `BNDCL`, `BNDCN`, `BNDMK`), `CLDEMOTE`, `RDSSPD`, `ENDBR32`
and `ENDBR64`.

**It is lettered so that every past use of "the oracle says NOP" in
this range is findable.** No assertion may rest on those cells: where
the oracle and the screen differ the row is a finding, and the
exemption in (aa)/(ac) is decided by **the screen, per full
(prefix, opcode, ModRM) byte**, never by the oracle.

**Why (ae) has no red:** the defect is in an instrument we do not own,
and the only assertion available is on a fix that is not written. The
same treatment as (q). **Minting condition:** the exemption predicate
exists in code, at which point a red asserts that it consults the
screen's per-cell verdict and not the oracle's opcode-level one.

**The granularity lesson, with its REASON and not only its fact.**
Probe granularity rose three times in this arc — opcode, opcode+mod,
then prefix+opcode+mod — each rise one notch behind a counterexample.
The full-ModRM sweep ends that, and the reason is why it is permanent
rather than a one-off:

`PREFETCHIT0` is `0F 18 /7` and `PREFETCHIT1` is `0F 18 /6`, and **the
only addressing either accepts is RIP-relative**. In 64-bit mode that
is `mod=00, rm=101` — one ModRM byte per instruction and no other.
`3d` is `mod=00 reg=111 rm=101`; `35` is `mod=00 reg=110 rm=101`.
`ENDBR32`/`ENDBR64` are `fb`/`fa`, likewise single bytes.

**A mod-class predicate cannot express a single ModRM byte**, and an
instruction whose encoding admits exactly one is not a corner case —
it is what happens whenever an opcode's operand form is fixed by the
architecture. So the sweep is over the full byte from here on, and the
exemption predicate reads the full byte.

## The control set has degraded, and the remaining one is named

`nmap_service.exe` carries 71 rows of the (ac) class, three of them
`ENDBR32`. **A control that contains the thing being fixed is an input
for that fix, not a control for it.**

**`beep.sys` is the only remaining true control for this class**: zero
(aa) rows, zero (ac) rows, zero exempt rows. One control is a control
until it isn't.

**What a second would take:** a binary that (1) is 32-bit PE, so it
exercises the same loader path, (2) contains no two-byte opcode in the
219-opcode NOP class, which `scripts/denominators.py` can check before
adoption, and (3) comes from a different build chain than beep.sys
(ReactOS), so the pair is not one toolchain twice. Until then, a
"controls unchanged" claim over this class rests on **one** input and
must say so.

## The refusal contract, stated once

Four tests assert that a refused encoding has length 1: `06`, `82`,
`60`/`61` and `8F /1`. **Neither instrument attests that length** —
objdump prints `(bad)` over 1 or 4 bytes, the oracle prints nothing —
so it is **this decoder's refusal policy**, registered once by
`x64_RED_n_invalid_walk_continues`:

> An encoding the decoder refuses has **length 1** and
> `x86_decode_range` **continues** at the next byte. The length is a
> resynchronisation choice, not a decode; a longer skip would drop
> bytes a later start may need, and a break would drop the rest of the
> section.

Four tests agreeing with each other is not attestation. The sweep
scores them in their own bucket for exactly that reason.

## Open, deferred, each with the condition that mints it

**(q) VEX / EVEX / REX2 unmodelled.** Measured zero on two
instruments: 0 occurrences by bytes over 576,115 objdump instructions
and 512,000 Ghidra starts, 16 of 16 inputs.
**Minting condition:** the first corpus input containing a VEX, EVEX or
REX2 encoding. Until then a red would have no number to move
(twenty-second rule), and the zero is recorded rather than the finding
closed, because the gap is real and the corpus is what is narrow.

**(t) the two-byte map has no INVALID.** Both instruments give the same
22 two-byte opcodes as invalid; the arm has no way to say so. **(t) now
has a red** — see the table above. Its first double-attested witness is
`0F 0D C0`, the register form of PREFETCH, which is Ghidra NONE and
objdump `(bad)` while its memory forms are 3 and 7. The rest of (t)
still waits on the generator run that produces the refusal list, and is
banked separately from (s) so it does not leave with it.

*(ab) was deferred here and is now minted; see the table above. The
deferral said its only measurable instance was `0F 78`, which was true
of the **length** half only. The identity half is 1,091 exposures, and
the red is an inequality between `0F AE C0` (invalid in both
instruments) and `F3 0F AE C0` (RDFSBASE, 4 bytes in both), so it needs
no instruction modelled and (aa) cannot close it.*

## (ac), minted 2026-09-20: the explicitly-cased half of the NOP class

219 of 256 two-byte opcodes render as `X86_INS_NOP`. **59 reach the
default arm — that is (aa). The other 160 are assigned NOP at 17
explicit `case` sites — that is (ac), and (aa) cannot close any of
them.** The split is the reason the two are separate letters rather
than one: a fix to the default arm leaves 160 opcodes rendering real
instructions as no-ops, and the eight reds above would stay red through
it. (aa)'s pre-registration must predict exactly that.

The eight reds were already in the suite as *passing* tests. Each named
a real instruction in its comment and then asserted it was a no-op.
They were written because someone hit those instructions, so they are
evidence of which opcodes matter, and each now carries its SDM mnemonic
as the pre-registered target.

## Not a defect letter, but owed and easy to lose
- **512,213 is withdrawn.** It was summed from Ghidra per-instruction
  files that lived in `$(BUILDDIR)` and a clean destroyed. No
  difference may be taken against it. The reproducible pair is
  576,115 and 512,000, printed together by
  `tools/translator/scripts/denominators.py`.
- **`0F 21`, `0F 22`, `0F 23` have zero corpus witnesses** (`0F 20` has
  218). Fixture v13 gives them one each, but those three rows sit
  behind the fixture's desync region and the flow-following oracle
  never reaches them, so they are **screen-only witnesses and the
  four-opcode claim is not double-attested**. The fixture is not
  re-edited for it now; when it next opens for (s) the rows move ahead
  of the desync region and become double-attested for free.

## The NOP class, whole

| | opcodes | corpus occurrences |
|---|---|---|
| (aa) the `default:` arm | **59** | **22** |
| (ac) the 17 explicit `case` sites | **160** | **22,012** |
| **total rendering as NOP** | **219 of 256** | **22,034 of 48,244** |

Computed as a set difference, not by eye. **Forty-six per cent of every
two-byte instruction in the corpus is currently reported as a no-op**,
and (aa) moves 22 of them. Both numbers, always (rule 29).

## Closed, for the boundary

(b), (c), (d), (d-k), (e), (h), (i), (k), (m), (n), (o), (w), (x), (z),
(a). Each closed through an XPASS gate whose log names the exact set of
names that moved.
