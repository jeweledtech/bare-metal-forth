# Pre-registration: fix (aa), the two-byte default arm's silent NOP (2026-09-20)

**Order.** The owner ruled (aa) ahead of (s) on 2026-09-20: (s) repairs
six forms sitting on an arm that mis-renders 219 opcodes, and landing
it first would patch the two-byte map twice instead of building it
once. (s)'s pre-registration survives entire and its differential
figures are re-taken after this fix.

Everything below is recomputed against
**`operand-diff-fix-o-2026-09-20.log`** by name, and against fixture
**v13** (`b19fcb6911e66fa66bdda105ee5e047f93fe4cafae85fbddb3fe7480dbaee9b4`).

## 0. What (aa) is, after two corrections to my own numbers

`x86_decoder.c:1316` ends the two-byte `default:` arm with
`out->instruction = X86_INS_NOP;`. An opcode the decoder does not model
is reported as an instruction that **does nothing** — a confident wrong
answer where `UNKNOWN` would be an honest one.

**Correction 1, already banked:** "30 of 256 reach the arm" was wrong;
**59** do. The 29 missed are the arm's own `no_modrm` list, which skips
the ModRM fetch and then assigns NOP like every other row.

**Correction 2, from this pre-registration:** "5 corpus instructions
reach the default arm" was counted over that wrong 30-set. Over the
correct 59-set the figure is **22**.

## 1. Population, pinned before any table

16 of 16 inputs, the list the post-(o) differential ran. Census by
bytes, `scripts/denominators.py`:

| | count |
|---|---|
| instructions examined | **576,115** |
| two-byte (`0F xx`) instructions | **48,244** |
| inputs | 16 of 16, none missing |

**The two-byte population moved from 48,241 to 48,244 and the reason is
named:** fixture v13 added three `0F 2x` rows. Three, exactly, and no
other input changed.

## 2. Rule 29: the prediction over the corpus AND over the opcode space

**(aa) moves 22 of 48,244 two-byte occurrences, and 59 of the 219
NOP-rendering opcodes leave the class.**

Both numbers, because they answer different questions. Twenty-two says
how often this bit these sixteen binaries. Fifty-nine of 219 says how
wide the hole is for the seventeenth, and 219 of 256 is the shape of
the map a translator is pointed at arbitrary code with.

Per input, by bytes:

| input | (aa) occurrences |
|---|---|
| storport.sys | 13 |
| fixture (v13) | 3 |
| ACPI.sys | 2 |
| pci.sys | 2 |
| ne2k-pci.ko | 1 |
| via-rng.ko | 1 |
| **the other ten inputs** | **0** |

## 3. Proportionality, with the asymmetry predicted in advance

**Ten of the sixteen inputs contain zero (aa)-touched encodings and
must not move at all**: disk, HDAudBus, i8042prt, HP serial, usbxhci,
8139too, iTCO_wdt, both ReactOS controls and nmap. An input that moves
while containing none of the thing being fixed is doing something else.

The six that may move are capped at their byte counts above, and
storport carries more than half of the corpus total on its own.

## 4. The predicted differential movement is exact, not a bound

A NOP-rendered instruction prints `nop` and the comparer classifies it
`mnemonic` (`nop vs <real>`). After the fix it prints `???` and is
classified `undecoded` — `compare_operands.py:208,211`. Both are
non-`ok` classes.

**So: `operand_ok` and the score are UNCHANGED on every input.
`mnemonic` falls by at most 22 and `undecoded` rises by the same
number, input for input.** Any other class moving is a finding.

**Lengths do not change.** The arm's ModRM consumption is untouched;
only the identity assignment changes. So `nostart`, `beyond_extent` and
`invalid_at_start` are unchanged on all 16 inputs. If a start moves,
the fix did something it was not asked to.

## 5. Readers, enumerated from source before a line changes — and one
of them is a new defect

`grep -rn "X86_INS_NOP" src/` over the whole tree, minus the two-byte
arm itself:

- **`x86_decoder.c:319, 1026, 1030–1038`** — one-byte NOP sites and the
  string-op arms. Untouched by (aa); named so they are checked.
- **`x86_decoder.c:1421`** — the printer's name table, `[X86_INS_NOP] =
  "nop"` and `[X86_INS_UNKNOWN] = "???"`. This is what makes the
  movement in §4 visible at all.
- **`src/ir/uir.c:437`** — `case X86_INS_NOP: uir->opcode = UIR_NOP;`

**And `src/ir/uir.c:442`, which is the finding: `default: uir->opcode =
UIR_NOP;`.** Everything the lifter does not model becomes a no-op in
the IR, so `UNKNOWN` and `NOP` are **already indistinguishable one
layer down**. **18 of the 56 x86 identities fall through it, and
`X86_INS_INVALID` is one of them** — an explicit refusal lifts to a
no-op.

### (ad) minted: the lifter collapses refusal into no-op

Minted now, with its count, **because (aa) alone does not reach the
analyzer**. The decoder will stop lying; the IR will carry the same
`UIR_NOP` it carries today. Any claim that (aa) improves downstream
analysis is false until (ad) lands, and this document makes no such
claim. Pass state: an unmodelled or invalid instruction is not a
`UIR_NOP`. **(ad) is not in (aa)'s scope** — (aa) is the decoder's
answer — and its red exists now: `ad_invalid_does_not_lift_to_nop` in
`test_uir.c`, which had no expected-failure plumbing until this red
needed it. It decodes `06` PUSH ES, asserts as *setup* that the decoder
says `INVALID`, and fails on the lifted opcode being `UIR_NOP`.

## 6. Denominators

Every figure above prints one. The corpus counts come from
`scripts/denominators.py` and the opcode-space counts from a probe that
sweeps **all 66 ModRM forms** — 64 register cells plus `mod=00` and
`mod=10` — because for `0F 00/01/18/AE` the digit is opcode and for
`0F 20`–`23` the mod bits are ignored. Result: 0 opcodes render NOP for
some forms and not others, so 219 is ModRM-independent.

## 7. Expected XPASS, red by red, over all 30

**Flip (1), and only one:** `x64_RED_aa_unhandled_two_byte_is_not_nop`.
`0F A7` is in the 59.

**Stay red (29).** The nine converted tests are named individually, as
required:

| red | why it must NOT move |
|---|---|
| `cmovcc_0F44` | `0F 44` is explicitly cased — (ac), not (aa) |
| `bt_rm_r_0FA3` | `0F A3` explicitly cased — (ac) |
| `bt_rm_imm8_0FBA` | `0F BA` explicitly cased — (ac) |
| `cmpxchg_0FB1` | `0F B1` explicitly cased — (ac) |
| `xadd_0FC1` | `0F C1` explicitly cased — (ac) |
| `desync_recovery_BT_then_IN` | `0F A3` explicitly cased — (ac) |
| `three_byte_0F38` | `0F 38` explicitly cased — (ac) |
| `three_byte_0F3A` | `0F 3A` explicitly cased — (ac) |
| `unknown_0f_modrm_recovery` | `0F 0D` explicitly cased — (t) |

**Any of those nine flipping means the fix widened past the default arm
without saying so.** That is the sharpest assertion in this document,
because the eight are 160 opcodes and 22,012 corpus occurrences of a
class (aa) is not allowed to touch.

The remaining 20 stay red for the ordinary reason: (d'), (f), (g)×2,
(p)×2, (r1)–(r3), (s)×7, (u), (v), (y), (ab). **(ab) in particular
cannot move**: `0F AE` is explicitly cased, and its red is an
*inequality* that `UNKNOWN == UNKNOWN` does not satisfy.

**Other suites:** `test-semantic` and `test-port-attestation` carry 0
registered expected failures and must stay at 0. **`test-uir` now
carries 1** — (ad), minted with this document — and it must stay red
through (aa), because (aa) never reaches the lifter.

## 8. Rule 28: the shipped-binary assertion (aa) can fail

**The fixture contains no NOP byte at all** — `grep -c 0x90` over
`x64_reds.s` returns 0 — so a correct decoder prints **zero** `nop`
lines for it. The shipped binary prints **three** today:

```
0040104d:  nop        0F 70 PSHUFW   -- (ac), stays
00401055:  nop        0F C4 PINSRW   -- (aa), must go
00401074:  nop        0F AA RSM      -- (aa), must go
```

**Assertion: after (aa), `bin/translator -t disasm` on the fixture
prints no `nop` at `00401055` or `00401074`, and still prints one at
`0040104d`.** It fails now, passes when (aa) lands, is derived from the
fixture's own bytes plus the pinned oracle rather than from a run, and
**the surviving row is the assertion's control** — a fix that silenced
all three went further than it was authorised to.

## 9. The boundaries, stated before a line is written

> **(aa) owns the two-byte `default:` arm and nothing else: 59 opcodes,
> the identity only, never the length.**
>
> **(ac) owns the 160 opcodes assigned NOP at the 17 explicit `case`
> sites.** 219 = 59 + 160, computed as a set difference, not by eye.
>
> **(ab) owns the arm's blindness to `66`/`F2`/`F3`.** Orthogonal to
> both: a prefix-aware arm is needed whichever half is fixed.
>
> **(s) owns two-byte lengths**, and (aa) changes none.
>
> **(t) owns the map's inability to refuse**, and (aa) produces
> `UNKNOWN`, not `INVALID`. If (aa)'s fix emits `INVALID` anywhere it
> has taken (t)'s work without (t)'s oracle list.
>
> **(ad) owns the lifter's `default: UIR_NOP`.** (aa) stops at the
> decoder boundary.

## 10. (q), unchanged and still blocking nothing here

Measured zero across the whole pinned population, three ways, 0 of
576,115. (aa) touches no VEX, EVEX or REX2 path, so (q)'s status is
unchanged by it and no figure in this document rests on it.

---

**State before the fix:** `pass=85 xfail=30 fail=0 xpass=0 (tests=115)`,
25 suites, `SMOKE PASS`. No line of (aa) is written.

---

# Amendment: the order changes, and the fix has an exemption it did not have (2026-09-20)

## The amended order: (ad) alone, then (aa) with (ac), then (s)

Recorded as ruled. **(ad) first** because its prediction is *nothing
moves*, which is a live test of the claim that the decoder almost never
emits `INVALID` today — and a false claim is far better found before
two larger fixes land than inside their movement. **(aa) with (ac)**
because they are one sentence with two mechanisms: an opcode we do not
model is not reported as doing nothing. Shipping (aa) alone repairs 22
occurrences and leaves 22,012 standing, with nothing downstream able to
tell which half it is reading. **(s) last**, re-baselined.

Everything in §§0–10 above stands except where this amendment restates
it. The expected-XPASS set in §7 was written for (aa) alone and is
**superseded**: with (ac) in the same act, the eight converted tests
are predicted to **flip**, not to stay red. The prediction that they
stay red belongs to the (aa)-alone ordering that no longer exists.

## The exemption, found while predicting the differential — 8 opcodes that must stay NOP

`0F 18`–`0F 1F` are **genuine multi-byte NOPs**: the pinned oracle
names all eight `NOP` in every ModRM form. They are inside the 219, in
(ac)'s explicitly-cased half, and today the decoder gets them **right**.

**They occur 11,047 times in the corpus** — ACPI 3,370, pci 2,480,
storport 2,067, usbxhci 1,317, i8042prt 472, HP serial 480, HDAudBus
406, disk 361, 8139too 64, iTCO_wdt 14, ne2k-pci 12, nmap 3, via-rng 1,
fixture **0**.

**A blanket fix that turned all 219 into `UNKNOWN` would move 11,047
rows out of `operand_ok` and the score would fall on nine inputs.** The
exemption is therefore part of the fix, not a detail of it, and it is
registered before a line is written rather than discovered as a score
regression afterwards.

### The class, restated with the exemption

| | opcodes | corpus occurrences |
|---|---|---|
| (aa) the `default:` arm | 59 | 19 corpus + 3 fixture |
| (ac) explicitly cased, **wrong** | **152** | **10,965** |
| (ac) explicitly cased, **genuinely NOP — exempt** | **8** | **11,047** |
| rendering as NOP, total | **219 of 256** | 22,034 |

**211 opcodes must leave the NOP class and 8 must stay.** That the
exempt eight are *half* of all the occurrences is the reason a corpus
count alone would have mis-sized this fix in both directions at once.

## 1. The `mnemonic` prediction, decided by reading the comparer rather than guessed

The proposal was to predict `mnemonic` stays at 11,048. **The source
rules that out before the run.** `compare_operands.py` returns
`'undecoded'` for `om == '???'` at line 208, **before** reaching the
mnemonic comparison at line 211. NOP and UNKNOWN are already treated
differently, by construction, and registering a prediction the source
falsifies would waste the check.

**What is registered instead is the conservation law underneath it,
which is exact, falsifiable and free:**

> **`mnemonic + undecoded` is invariant, input for input.** Every row
> that leaves `mnemonic` enters `undecoded` and nothing enters
> `mnemonic`. If the sum moves on any input, the comparer is doing
> something neither of us has read.

> **`operand_ok`, `nostart`, `beyond_extent`, `invalid_at_start` and
> the score are unchanged on all 16 inputs** — *provided the eight
> exempt opcodes keep their NOP*. **`operand_ok` falling by roughly
> 11,047 is the signature of a blanket fix**, and that is the control
> for the exemption above.

**Magnitude:** `mnemonic` is 11,048 today and the wrong-NOP occurrences
are 10,965. The two are close enough that most of the `mnemonic` class
is expected to *be* NOP rows, so `mnemonic` should fall a long way —
but the exact figure is whatever conservation gives, because only rows
our walk reached at a Ghidra start are classified at all, and the
per-row dumps that would settle it were destroyed by a clean.

## 2. The identity predicate has now been run, and it is clean

`docs/evidence/x64-rule30-identity-sweep-2026-09-20.log`. Same script,
different field: for every passing test asserting `instruction !=
X86_INS_X` on a literal byte array, disassemble those bytes in the
test's own mode and compare the mnemonic.

| | count |
|---|---|
| passing tests (denominator) | **85** |
| swept by the identity predicate | **55** |
| mnemonic agrees with objdump | **55** |
| **mnemonic disagrees** | **0** |
| not swept | 30 |

*The first run reported 8 disagreements and all 8 were instrument:
objdump prints a redundant prefix (`rex.W`, `data16`, `rep`) as its own
pseudo-instruction and the parser read that as the mnemonic. Corrected
before the result was used.* Six of the 30 unswept are unswept **for
that same reason** — they probe redundant-prefix behaviour, and objdump
refuses to join the prefix to the instruction, so the screen cannot
adjudicate them. Those six need the blob oracle, not objdump, and that
is named rather than counted as agreement. The alias table is hashed in
the log, because it is a score-moving knob.

## 3. The suite's first positive verdict

Three weeks of this arc have measured what the suite **cannot** see.
This is the first measurement of what it **does**.

| predicate | swept | confirmed | found |
|---|---|---|---|
| asserted length vs objdump | 78 of 94 | **77** | 1 (`0F 0D C0`, #UD) |
| asserted identity vs objdump | 55 of 85 | **55** | 0 |

**One hundred and thirty-two expectations independently confirmed
against a second instrument, and one real defect found.** The
unswept remainders are named in both logs. That is a result, and it is
said as one.

## 4. Corpus and fixture are separated at the instrument

`scripts/denominators.py` now reports them apart, because a fixture
edit moved a corpus figure and the fixture is an instrument and an
input at once.

| | corpus (15) | fixture | combined |
|---|---|---|---|
| objdump instructions | **576,083** | 35 | 576,118 |
| Ghidra starts | **511,969** | 31 *(pre-v13, stale)* | 512,000 |
| difference | **64,114** | — | contaminated |
| `mnemonic` class | **11,046** | 2 | 11,048 |

**The banked 576,115 has already become 576,118**, entirely because v13
added three rows — which is the demonstration rather than the
objection. The corpus-only figure cannot be moved by an instrument
change. The combined difference now mixes a v13 objdump count with a
v12 oracle count and is marked contaminated in the log until the
differential is re-run.

*The first run of the split printed a corpus difference of 64,083: it
subtracted the combined oracle count from the corpus objdump count.
Corrected, and the miss is recorded in the log's header.*

## 6. (ad)'s plumbing has its control, and the control fires

Deleting the call to the registered test:

```
Results: 22/22 passed (xfail=0 of 1 registered, xpass=0)
HARD FAILURE: xfail_names entry "ad_invalid_does_not_lift_to_nop" did not
  run (test deleted or renamed; the list and the suite disagree)
make: *** [Makefile:165: test-uir] Error 1
```

**`22/22 passed` and `xfail=0 of 1 registered` on the same line** is
exactly the shape the twenty-seventh rule was minted on: zero-failed
and zero-registered must not print the same, and here they do not. The
call was restored and the suite returns to `22/23 passed (xfail=1 of 1
registered, xpass=0)`.

---

# Second amendment: the exemption re-derived per cell, and it shrank (2026-09-20)

## The hold was right, and both counterexamples are in the corpus

**Exempting by opcode was wrong.** Re-derived per (prefix, opcode, mod)
cell against both instruments:

**`0F 18`–`0F 1F` is not a NOP range. It is a range that mostly
contains NOPs.** Screened with objdump over all 96 cells (4 prefixes ×
8 opcodes × 3 ModRM forms), **25 cells are named instructions**:
`PREFETCHNTA` (`0F 18` memory forms), the whole MPX family — `BNDLDX`,
`BNDSTX`, `BNDMOV`, `BNDCU`, `BNDCL`, `BNDCN`, `BNDMK` on `0F 1A`/`1B`
under each of the four prefixes — and `CLDEMOTE` (`0F 1C` memory
forms). It is `0F 0D C0`'s shape exactly: register form one thing,
memory forms another, four items after this arc found that.

**And the oracle says `NOP` to all 96.** Ghidra 12.1.2 names every one
of the 96 cells `NOP`. That is a **systematic instrument disagreement
across 25 cells**, recorded as a finding and folded neither way. The
screen names them; the oracle does not model them. No assertion rests
on those 25 cells.

**`F3 0F 1E FA` ENDBR64 was never probed at all**, because the blob
holds ModRM at `00`/`80`/`C0` and ENDBR is `FA`/`FB`. Exempting by
(prefix, opcode, mod) would still have swallowed it. **`0F 1E` needs
the full ModRM byte**, which makes it the first cell in the arc where
opcode-and-mod is not fine enough.

## "CET is probably absent" is exactly the phrasing rule 29 refuses, and it is false here

Measured, by bytes, over the pinned inputs: **3 `ENDBR32`** in
`nmap_service.exe` at `.text+401c70`, `+401ce0`, `+408c60`, ModRM `FB`
every time. Not older-driver code — the modern Debian-built PE32
control, which is in the corpus precisely so "the PE32 path works" is
not a coincidence. **The control input is what carries the
counterexample.**

Alongside them, **16 `PREFETCHNTA`**, two in every one of the eight HP
drivers, same operand `0x40(%rcx,%rdx,1)` each time: one block-copy
routine, linked eight times.

**19 real instructions were inside the exemption.** The 11,047 was an
upper bound and it shrank to **11,028**.

## The class, third and current statement — corpus and fixture apart

| | opcodes | corpus (15) | fixture |
|---|---|---|---|
| (aa) the `default:` arm | 59 | **19** | 3 |
| (ac) explicitly cased, **wrong** | 152 + the 19's cells | **10,978** | 6 |
| **exempt — genuinely NOP, decided per cell** | — | **11,028** | 0 |
| rendering as NOP | 219 of 256 | 22,025 | 9 |

**Leaving the NOP class: 10,997 corpus rows. Staying: 11,028.** The
exemption is now a per-cell predicate — *what the screen calls this
exact (prefix, opcode, ModRM) encoding* — not an opcode list, and for
`0F 1E` it reads the whole ModRM byte.

## Predictions revised, including one that breaks a standing assertion

- **`operand_ok` falls by 11,028 if the exemption is applied by opcode
  instead of per cell.** That remains the blanket-fix control.
- **`operand_ok` falls by 19 if the exemption is applied per cell but
  the 19 are not moved out of it** — a much quieter failure than the
  first, and the reason the per-cell derivation was worth doing.
- **`nmap_service.exe` moves by 3.** It is a **control**, and the
  standing assertion has been that controls do not move. That
  assertion is **restated here before the fix**: the 32-bit controls
  are controls for *mode* handling, not for the two-byte map, and nmap
  carries 71 (ac) rows of which 3 are ENDBR32. A control that contains
  the thing being fixed is an input for that fix. Saying so afterwards
  would have been a rationalisation.
- `beep.sys` contains **none** of the class and must not move at all.
  It is the remaining true control.

## No product figure moves, and that is stated rather than left to inference

**(aa) and (ac) improve no product figure.** Lettered **(ag)**: the
lifter produces 40 distinct opcodes and **2** are ever tested by any
analysis — `UIR_CALL` and `UIR_INT` — while `src/codegen/` and
`src/optimize/` dispatch on the opcode nowhere at all. Repairing the
identity of 211 opcodes therefore changes the differential and the
`-t uir` text, and changes **nothing** in `summary.call_graph`, the
port attestation or any generated output.

These two fixes make the IR **true**. They do not make it **used**.
Said here in those words so no reader infers analyzer improvement from
a decoder repair.

## Thirty-first rule, recorded against the desk that minted it

> **A prediction about what an instrument will report is a claim about
> that instrument's source, and is read there before it is registered.**

The `mnemonic`-stays-at-11,048 prediction was unfalsifiable because
`compare_operands.py` routes `'???'` to `undecoded` before it ever
compares mnemonics. Rule 24 requires a fix's readers enumerated from
source; this is the same requirement pointed forward at predictions.

---

# Third amendment: the headline split, and the rule's premise measured (2026-09-20)

## The split is built, the differential re-run, and the answer is zero

**Required before (aa) lands, and done before (aa) is written.**

`dump_starts` now emits a fifth header token per instruction: **`D`**
when the NOP came from the two-byte arm — which assigns NOP to 219 of
256 opcodes without deciding anything — and **`.`** otherwise. There is
no two-byte opcode for which this decoder *decided* NOP on evidence, so
"NOP after an `0F` escape" is exactly the defaulted set.
`compare_operands.py` reports `ok_defaulted`, `ok_decided` and a second
headline `decided=` beside the old `score=`, and prints
`DUMP_PREDATES_SPLIT=n` if handed a dump banked before today rather
than silently scoring it as fully decided.

Re-ran `differential-all` over all 16 inputs, oracle re-pinned at
Ghidra 12.1.2 snap 47,
`docs/evidence/operand-diff-decided-split-2026-09-20.log`:

| | value |
|---|---|
| Ghidra starts | 512,000 |
| `operand_ok` | **464,911** |
| `ok_defaulted` | **0** |
| `score` | 90.8% |
| `decided` | **90.8%** |

**`ok_defaulted = 0` on every one of the sixteen inputs.** The headline
is not inflated by the NOP class, and the arc's number survives the
check unchanged: the eight HP drivers still run 89.4% to 91.8%.

## Why the premise did not hold — read from the comparer's own output

The rule's reasoning was that Ghidra names those cells `NOP`, we render
them NOP, and so the rows score as agreement. **They do not, and the
comparer says why.** Ghidra decorates a multi-byte NOP with operands —
`NOP dword ptr [RAX + RAX*0x1]` — and we print a bare `NOP`. Those rows
fail on **operand count**, not on mnemonic, so they were never in the
agreement class.

Measured on `i8042prt` before the full run: of **787** rows our dump
flags defaulted, **447 land in `opcount`** (the genuine multi-byte
NOPs, where only the operands differ) and **340 in `mnemonic`** (the
wrong ones, where Ghidra says `BT`, `MOVUPS`, and so on). **Zero in
`ok`.**

**This is the thirty-first rule applied to the thirty-second.** Rule 32
is itself a prediction about what a comparer will report, and reading
the comparer settles it: the split was worth building and the number it
produces is zero.

## The instrument is kept anyway, and here is what it is for

A zero that was reasoned is an assurance; a zero that was measured is
evidence, and only the second can be re-taken. The split stays wired
into every differential run because it is also the tripwire for a
future canonicaliser change that starts folding a bare `NOP` into a
decorated one — which would silently move 11,028 rows into the
agreement class and raise the headline by about two points for no
reason at all. That is precisely the move the canonicaliser stopping
rule exists to catch, and now an instrument catches it rather than a
reader.

## Two corrections this run settles

- **The fixture's oracle row is no longer stale.** Re-run against v13
  (`b19fcb69…`), Ghidra still reports **31** starts and the row is
  identical: `score=45.2%`. The three new `0F 2x` rows sit behind the
  fixture's desync region in the flow-following walk, exactly as the
  fixture's own comment predicts, so they are instrumented by their
  unit test at their own address and not by the differential.
- **Corpus Ghidra stays 511,969** and the corpus difference stays
  **64,114**.

---

# Fourth amendment: the predictions sharpened before a line is written (2026-09-21)

**The earlier phrasing — "`operand_ok` falls by 19" — was ambiguous and
is withdrawn.** It was reasoned, not measured. Rule 31 says a
prediction about what an instrument will report is a claim about that
instrument's source, so the comparer was read and the corpus measured
first.

## What the comparer does with a NOP row, measured over all 16 inputs

Every row our dump flags `D` (a NOP the two-byte arm produced), by the
class `compare_operands.py` puts it in:

| class | rows |
|---|---|
| `ok` | **0** |
| `mnemonic` | 10,964 |
| `opcount` | 10,870 |
| anything else | **0** |

**Not one NOP row is in the agreement class, on any of the sixteen
inputs.** The reason is in the comparer's own output: Ghidra decorates
a multi-byte NOP with operands (`NOP dword ptr [RAX + RAX*0x1]`) and we
print a bare `NOP`, so even the rows where both instruments say NOP
fail on operand **count**.

## So the predictions are these, and they are exact

1. **`operand_ok` is UNCHANGED on all 16 inputs, and so is `score`.**
   No NOP row is in it, so no NOP row can leave it. **A score that
   moves at all means the fix changed something it was not asked to.**
2. **`mnemonic + opcount + undecoded` is conserved, input for input.**
   Every row that stops being NOP becomes `???` and lands in
   `undecoded`; nothing enters `mnemonic` or `opcount`.
3. **`mnemonic` falls close to zero.** Its 10,964 rows are exactly
   "Ghidra named something, we said NOP". All of them are non-exempt by
   construction, so all of them move.
4. **`opcount` falls only by the non-exempt cells inside it** — the 19
   real instructions the screen names in `0F 18`–`0F 1F` (16
   `PREFETCHNTA`, 3 `ENDBR32`) plus any other cell where Ghidra says NOP
   and the screen says otherwise. **The bulk of `opcount` stays**,
   because those rows are the genuine multi-byte NOPs the exemption
   keeps.
5. **`nostart`, `beyond_extent` and `invalid_at_start` are unchanged on
   all 16.** The fix changes an identity assignment and touches no
   operand consumption, so no length and no start can move.
6. **No product figure moves** — (ag): nothing reads instruction
   identity but `UIR_CALL` and `UIR_INT`, and neither is produced here.

## Expected XPASS: exactly 9 names

**Flip:** `x64_RED_aa_unhandled_two_byte_is_not_nop` (`0F A7`, in the
59) and the eight (ac) reds — `cmovcc_0F44`, `bt_rm_r_0FA3`,
`bt_rm_imm8_0FBA`, `cmpxchg_0FB1`, `xadd_0FC1`,
`desync_recovery_BT_then_IN`, `three_byte_0F38`, `three_byte_0F3A`.

**Must NOT flip, and each for a stated reason:**

- `unknown_0f_modrm_recovery` — (t). It asserts `INVALID`, and this fix
  produces `UNKNOWN`. **If it flips, the fix has taken (t)'s work
  without (t)'s oracle list.**
- `x64_RED_ab_two_byte_arm_ignores_mandatory_prefix` — (ab). Its
  assertion is an *inequality* between bare `0F AE C0` and
  `F3 0F AE C0`; both become `UNKNOWN`, which is still equal.
- The seven (s) reds and (u) — length only, and no length changes.
- (d'), (f), (g)×2, (p)×2, (r1)–(r3), (v), (y) — untouched sites.

## The exemption predicate, and how it will be checked

The exemption is **the screen's verdict, per full (prefix, opcode,
ModRM) byte**, for `0F 18`–`0F 1F` only. Everything else in the 219
becomes `UNKNOWN`.

**It is not asserted by reading the code.** The banked 8,192-cell sweep
(`x64-nop-range-full-modrm-2026-09-20.log`) is the oracle for it, and a
new test will drive the decoder over **all 8,192 cells** and require
its NOP/not-NOP verdict to match that log **cell for cell**. A
predicate that agrees on 8,191 is a predicate with a bug.

## Rule 28: the shipped-binary assertion

The fixture contains **no NOP byte**, and the shipped binary prints
**three** `nop` lines today: `0040104d` (`0F 70`, (ac)), `00401055`
(`0F C4`, (aa)) and `00401074` (`0F AA`, (aa)). **After this fix it
must print zero**, because all three opcodes are outside `0F 18`–`0F 1F`
and none is exempt. The earlier form of this assertion — "two go, one
stays" — was written for (aa) landing alone and is **superseded**.
