# Pre-registration: fix (s), the two-byte opcode map (2026-09-20)

**This document supersedes the (s) section of
`x64-reds-n-prereg-2026-09-18.md`.** That section was written before
(a) and (o) landed; every figure in it is pre-(o)-generation and is
**not** carried forward. This is the miss recorded in (o)'s own
closeout — the right baseline named, numbers derived against the old
one carried anyway — and it was likelier to repeat here because the
prior document predates two fixes, not one. Everything below is
recomputed against **`operand-diff-fix-o-2026-09-20.log`** by name.

## 1. Population, pinned before any table

**16 of 16 inputs** (15 corpus + the fixture), the same list the
post-(o) differential ran, read from its `===` lines. Census by
**bytes** (objdump instruction starts, prefixes and REX skipped, escape
sequences counted in the byte stream — not mnemonics):

| | count |
|---|---|
| instructions examined | **576,115** |
| two-byte (`0F xx`) instructions | **48,241** (was 48,305; third amendment, item 7) |
| inputs | 16 of 16, none missing |

(An earlier pass of this census silently dropped four inputs and
collided the two `serial.sys` basenames; it printed "12 of 16", which
is why it printed its denominator.)

## 2. What (s) touches, by bytes, per input

| encoding | corpus total | where |
|---|---|---|
| `0F 70`/`C2`/`C4`/`C5` (imm8 after ModRM) | **5** | storport 1, fixture 4 |
| `0F 20`-`23` with mod≠11 (the defective form) | **1** | fixture 1 |
| `0F AA` RSM | **1** | fixture 1 |
| `0F 78` under `66`/`F2` | **0** | — |
| `0F 0F` 3DNow | **0** | — |

**The corpus movement of (s) is one row: storport's `66 0F C5` PEXTRW.**
Every other instance is in the fixture. The 218 `MOV CR/DR`
instructions in the corpus are **all** mod=11, the form the decoder
already gets right; the defective form occurs once, in the fixture,
where it was placed deliberately.

## 3. Proportionality, with the exception predicted from byte counts

**14 of the 16 inputs contain zero (s)-touched encodings** — all HP
drivers except storport, all four modules, both ReactOS controls, and
nmap. They must not move at all. Only storport (1) and the fixture (7)
may. This is the disk/HDAudBus assertion of (o) generalised: a fix that
moves an input containing none of the thing it fixes is doing something
else.

## 4. Readers, enumerated from source before a line changes

(s) changes what the two-byte map's length and status mean.
- **`src/decoders/x86_decoder.c:1042`** `case 0x0F:` — the two-byte
  arm itself, and its hand-typed `no_modrm` list at **1294–1313**,
  which is the flat-array bug in miniature and the thing (u) measures.
- **`x86_decode_range`** — the length walk; a wrong two-byte length
  desyncs everything behind it (the mechanism that produced the ten
  phantom port ops).
- **`src/ir/uir.c`** operand copy — carries `disp`/`imm` per operand;
  unchanged in meaning by (s), named so it is checked not assumed.
- **printers**: `x86_print_decoded` (`x86_decoder.c`) and the UIR
  operand printer — both already 64-bit after (o).
- **`scripts/fit_opcode_table.py:63,68`** — `0x0F` is a HAND `ESCAPE`
  row in both modes; if (s) makes the two-byte map table-driven, this
  is where its status is decided.
- **`scripts/gen_opcode_table.py`** — builds the one-byte blobs only;
  the two-byte blob was built ad hoc on 2026-09-19 and must become a
  generator target if (s) is table-driven.
- **consumers of the generated table**: `src/decoders/x86_opcode_len.h`
  and `tests/test_x86_decoder.c` — the only two files that include
  `x86_opcode_table.h` (grep, whole tree).

## 5. The disagreeing set, restated for THIS generation

Both sweeps assert, today, post-(o): **{`68`, `8D`, `A9`, `F7`}** =
(r1) `68`, (y) `8D`, (r2) `A9`, (r3) `F7` — in 64-bit and in legacy
alike. (o)'s `A0`-`A3` left by hand when it closed.

**(s)'s expected effect on both sets is the empty difference.** The
sweeps probe the **one-byte** map and skip `0F` as an `ESCAPE` row with
the reason counted, so a two-byte fix cannot move them. Either sweep's
set changing is a finding, not a success.

**The instrument (s) does move is (u)**,
`x64_RED_u_0f_map_matches_oracle`, which today reports
`checked=2065 wrong_rows=61 wrong_opcodes=10:`
`0F0F 0F70 0FAA 0FC2 0FC4 0F20 0F21 0F22 0FC5 0F78`. (s) as scoped
covers all ten. Predicted after (s): `wrong_rows=0`, `checked` ≥ 2065
(the floor), set empty.

## 6. Denominators

(u) already prints `checked=` and has a pinned floor. Any new two-byte
survey pass prints **probes run**, not only disagreements — the
2026-09-19 survey had to be widened twice (one ModRM form → three →
twelve, taking 5 "mechanisms" to 9), and a printed denominator would
have shown the first widening was needed without waiting for the
second.

## 7. Expected XPASS, red by red

**Flip (8):** `x64_RED_s_pshufw_imm8_length`,
`_s_cmpps_imm8_length`, `_s_pinsrw_imm8_length`,
`_s_pextrw_imm8_length`, `_s_pextrw_xmm_imm8_length`,
`_s_mov_cr_mod_ignored`, `_s_rsm_no_modrm_length`, and
`x64_RED_u_0f_map_matches_oracle`.

**Stay red (11):** (d') `_rex_b_push_r12`; (f) `_byte_reg_sil_under_rex`;
(g) `_truncated_imm32_refused`, `_truncated_disp32_refused`;
(p) `_p_movsxd_decoded`, `_p_imul_imm_decoded`; (r1) `_r1_push_iz_opsize16`;
(r2) `_r2_test_eax_iz_opsize16`; (r3) `_r3_test_ev_iz_opsize16`;
(v) `x86_RED_v_addr_size_prefix_disp16`; (y) `_y_lea_register_form_invalid`.

**Other suites:** `test-semantic` and `test-port-attestation` both
carry **0 registered** expected failures and must stay at 0; (z) is
closed and green and must remain so. No red on another list is
expected to move — which is itself the statement, since (z) moving
unannounced at (o) would have reported a correct fix as a hard failure.

## 8. Rule 28: the shipped-binary assertion (s) can fail

`test-shipped-binary` gains one: the fixture's `.text` is exactly
`0x6d` bytes, and a correct linear walk over it yields **exactly 32
instruction lines** — the 31 rows the flow-following oracle knows, plus
the `RSM` after the `RET` that a linear walk reaches and a
flow-follower does not. **The shipped binary emits 36 today**, because
the walk desyncs through the (s) tail. So the assertion fails now,
passes when (s) lands, and is derived from the pinned oracle rather
than from a run.

## 9. The boundary with (r1)–(r3), stated before either is written

> **(s) owns the two-byte escape: whether a `0F xx` form has a ModRM,
> what trails it, and what its `mod` field means. (r1)–(r3) own the
> encoded immediate width of ONE-byte `Iz` forms under `0x66`. No
> opcode is in both: (s)'s opcodes are all `0F`-escaped, (r)'s are all
> one-byte (`68`, `A9`, `F7`).**

The case that looks shared is **`66 0F 8x`**, a two-byte `Jcc` whose
`rel` width under `0x66` in long mode is **vendor-divergent** — Intel
forces 64-bit near-branch operand size and ignores the prefix, AMD has
honoured a 16-bit form, and the oracle reports only what its
disassembler models. It belongs to **neither** fix: it is already
recorded as the "no oracle model at pin 12.1.2, no assertion" entry,
Ghidra having no model for those rows at all. (s) must not claim it and
(r) must not claim it; if either fix moves `66 0F 8x`, that is a
finding.

## 10. (q), settled by bytes on this pass

**Measured zero, not an untaken count.** Over the full pinned
population — **576,115 instructions, 16 of 16 inputs** — counted three
independent ways:

| instrument | count |
|---|---|
| `C4`/`C5`/`62` at an instruction start (VEX2/VEX3/EVEX escapes) | **0** |
| `D5` at an instruction start (APX REX2) | **0** |
| mnemonics beginning `v` other than `verr`/`verw` | **0** |

AVX is absent from this corpus, and it is absent for a reason rather
than by luck: these are kernel-mode Windows drivers, where using the
vector unit requires explicit FPU-state management and is avoided. The
earlier mnemonic screen over the banked Ghidra files agreed (0 of
512,000 starts). **(q) stays unminted on a measured zero across every
input**, and the claim is now "0 of 576,115 by bytes", not "no count
taken". If a VEX-bearing input ever enters the corpus, (q) is minted
the same session.

---

# Amendment: nine holds answered (2026-09-20)

## 1. Seven census instances, six residual rows — the seventh is the RSM

Mapped instance by instance from the post-(o) differential's own rows:

| census instance | where | differential row |
|---|---|---|
| `66 0F C5` PEXTRW | storport | **`nostart`** |
| `0F 70` PSHUFW | fixture `+4d` | `mnemonic` (matched start, we emit NOP) |
| `0F C2` CMPPS | fixture `+51` | **`nostart`** |
| `0F C4` PINSRW | fixture `+55` | `mnemonic` (matched start) |
| `0F C5` PEXTRW | fixture `+59` | **`nostart`** |
| `0F 20 80` MOV CR | fixture `+5d` | **`nostart`** |
| `0F AA` RSM | fixture `+6b` | **no row of any class** |

Plus two rows dragged behind the CR/DR over-read: `+60` (imm64) and
`+6a` (RET), both `nostart`. So 6 `nostart` + 2 `mnemonic` = 8 affected
rows from 7 instances, and **the RSM produces nothing**: it sits after
the final `C3`, the flow-following oracle never reaches it, so it is
not a Ghidra row and cannot be `nostart`.

**Consequence, and it changes the standing of hold 3: the ONLY
instruments that can see the RSM row are the unit red
`x64_RED_s_rsm_no_modrm_length` and the rule-28 fixture assertion.**
That assertion is load-bearing, not incidental.

## 2. `0F 20`–`0F 23` ignore `mod` entirely — the scope sentence was wrong

Corrected. SDM Vol. 2B, *MOV — Move to/from Control Registers* and
*Debug Registers*: these forms are **always register-direct and the
ModRM `mod` field is ignored**. `0F 20 80` is three bytes — `mod=10`,
`reg=000` (CR0), `rm=000` (RAX) — and is **not** a displacement form at
all. Calling `mod≠11` "the defective form", as §2 of this document did,
invites a fix that adds memory-operand handling, which is wrong in the
opposite direction from the defect.

**The correct change is: for `0F 20`–`0F 23`, ignore `mod` and never
read a displacement.**

And the census proves how thin the guard is: **all 218 corpus
instances are `mod=11`**, the form already decoded correctly, so **no
instrument in the system would catch a fix that got this backwards
except the single fixture row** at `+5d` — which is exactly why that
row is in the fixture.

## 3. The rule-28 assertion is an ordered address sequence, not a count

Withdrawn and replaced. A count is reachable by a fix that deletes a
real row and adds a spurious one, and this fixture holds defects of
**both signs**: four missing trailing `imm8` bytes each split one
instruction into two (adding lines), while the CR/DR over-read consumes
following bytes (removing them). The net `36 → 32` is a gross mixture
already nearly cancelling. Rule 26's family: a matching count is not
matching rows.

**The assertion is the exact start addresses, in order** (31 oracle
rows plus the post-`RET` `RSM` a linear walk reaches):

```
401000 401003 40100a 40100d 40100f 401010 401017 40101a 40101e 401022
401025 401027 401029 40102b 40102d 40102e 401030 401031 401033 401039
40103c 40103e 401042 401044 40104d 401051 401055 401059 40105d 401060
40106a 40106b
```

## 4. The sweep prediction is insensitive by construction

Restated. If both sweeps probe the one-byte map and skip `0F` as an
`ESCAPE` row, then "the effect on the disagreeing set is the empty
difference" **cannot fail whatever (s) does**. It is not a satisfied
prediction; it is an **insensitive instrument**, recorded as such so it
is never cited as evidence that (s) behaved. **(u) is the only
load-bearing instrument for the two-byte map**, together with the two
fixture-only witnesses above.

## 5. The set restatement was a substitution of unchanged cardinality

Member by member, with the finding each maps to:

| member | finding | kind |
|---|---|---|
| `68` | (r1) PUSH `Iz` | encoded immediate width under `0x66` |
| `A9` | (r2) TEST eAX,`Iz` | encoded immediate width under `0x66` |
| `F7` | (r3) TEST Ev,`Iz` `/0 /1` | encoded immediate width under `0x66` |
| `8D` | **(y)** LEA register form | **invalid-form disagreement, not width** |

Originally pinned as {(o), (r1), (r2), (r3)} — four members, all
width-or-address-width. Today: (o) left, **(y) joined**, count
unchanged at four. **Two members changed while the cardinality did
not**, which is the event an exact set exists to catch and the one a
reader skims. The set is now **heterogeneous**: three immediate-width
members and one invalid-form member.

## 6. Module hashes: identical to the baseline

The differential log records `INPUT <sha256> <path>` per input, which
is what made this checkable. All four rebuilt modules hash **identical**
to the values `operand-diff-fix-o-2026-09-20.log` recorded:
`ne2k-pci.ko`, `8139too.ko`, `iTCO_wdt.ko`, `via-rng.ko`. The census
and its named baseline describe the same artifacts. **The four module
rows are therefore NOT provisional** — an earlier draft of this
sentence said "identical … so the rows are provisional", which
contradicted itself; if they match they are not provisional.

## 7. (u)'s tenth opcode, named — and one opcode in scope that (u) misses

(u)'s ten: `0F 0F`, `0F 70`, `0F AA`, `0F C2`, `0F C4`, `0F 20`,
`0F 21`, `0F 22`, `0F C5`, `0F 78`. **The tenth is `0F 0F`, 3DNow** —
an opcode *suffix* byte after the ModRM, zero corpus instances, carried
in this document's table as a zero row and easy to skim past. `0F 78`
is the same shape.

**And `0F 23` is in (s)'s scope but absent from (u)'s failing set**, for
a reason worth recording: Ghidra returns NONE for `0F 23 00` and
`0F 23 80` while objdump reads 3, so those rows are **not
double-attested** and (u) excludes them by design; only `0F 23 C0` is
checked, where both read 3 and we already agree. `0F 20`/`21`/`22` are
attested at 3 in all three forms, which is why they appear. So (s)
must fix `0F 23` **without** (u) being able to confirm it — the fixture
row and the unit red are again the only witnesses.

## 8. Two instruments, not three

Withdrawn. VEX/EVEX-by-bytes and REX2-by-bytes both read **my own byte
scan of one objdump run**, and AVX-by-mnemonic reads **the mnemonic
field of that same run**. Three categories, one failure mode — by the
standing boundary, they are one instrument, not three.

**The genuinely independent second instrument** is the mnemonic screen
over the **banked Ghidra per-instruction files** (0 VEX/EVEX-encoded
mnemonics of 512,000 starts, 2026-09-19). So (q)'s zero rests on
**two** instruments: objdump over 576,115 instructions in 16 of 16
inputs, and Ghidra over 512,000 starts in 16 files (512,213 withdrawn;
third amendment, item 3). That is still a
corpus-wide measured zero.

The kernel-mode FPU-state account is an **explanation, labelled as
such**, not a finding, and nothing rests on it.

## 9. The `0x66` handler is shared, and both fixes read it

Enumerated from source. There is **one** flag: `X86_PREFIX_OPSIZE`, set
at `x86_decoder.c:274`, consumed at **`:300`** (`op_size`) and
**`:313`** (`stack_size`, fix (e)'s D64 rule). The two-byte arm
(`:1042`–`:1340`) consults **no mandatory prefix at all** — grep for
`PREFIX_OPSIZE|REP|REPNE` in that range returns nothing.

So although no *opcode* is in both fixes, **the `0x66` handler is a
reader of both**: (r1)–(r3) change how that flag drives one-byte
immediate width, and (s) must make the two-byte arm consult the same
flag as a **mandatory prefix selector** — a different meaning for the
same bit. Rule 24 is therefore not discharged by the opcode
disjointness.

**The rule between them:** (r1)–(r3) may change *how `op_size` is
derived from the flag*; (s) may add a *separate* consumption of the
flag in the two-byte arm and must not alter `op_size` or `stack_size`.
Whichever lands second re-runs the other's reds, and neither redefines
the flag itself. storport's single row is `66 0F C5`, where the `0x66`
is a **mandatory prefix selecting the XMM form**, not an operand-size
override — so that row is (s)'s, not (r)'s, and it is the case that
makes the shared reader concrete rather than theoretical.

---

# Second amendment: nine items (2026-09-20)

## The mapping surfaced something larger than (s): the silent-NOP default

`0F 70` rendering as **NOP** is not a length defect. Enumerated from
source: the two-byte arm's `default:` (`x86_decoder.c:1290`–`1317`)
ends `out->instruction = X86_INS_NOP;`, and ~~30~~ **59 of 256
two-byte opcodes reach it** (corrected in the third amendment, item 2,
by a brace-depth parse; the 30 below omitted the arm's own `no_modrm`
list, which is not exempt from the `NOP` assignment). At runtime
**219 of 256** render as `NOP`. The 30 first counted: `02 03 04 0C 24
25 26 27 36 39 3B 3C 3D 3E 3F 50 78 79 7A 7B A6 A7 AA B8 B9 BB C4 C5
F0 FF`. An unknown opcode that
resolves to a no-op is rule 27 inside the decoder — zero-known and
zero-doing print the same — and downstream it is worse than a wrong
length: the analyzer reads a function it cannot decode as a function
that **does nothing**, a confident wrong answer where `UNKNOWN` would
be an honest one.

### (aa) minted: the two-byte default arm renders unhandled opcodes as NOP

**Count, by bytes over 16 of 16 inputs (48,241 two-byte instructions,
re-derived in the third amendment): 5 corpus instructions reach the
default arm, and all 5 are not NOPs.**

| instruction | input | in (s)'s scope? |
|---|---|---|
| `pextrw r10d,xmm0,0x4` @`1c00308bd` | storport | yes (`0F C5`) |
| `pinsrw mm0,eax,0x0` @`401055` | fixture | yes (`0F C4`) |
| `pextrw eax,mm0,0x0` @`401059` | fixture | yes (`0F C5`) |
| `rsm` @`40106b` | fixture | yes (`0F AA`) |
| **`xstore-rng` @`9d`** | **via-rng.ko** | **NO — `0F A7`** |

**That last row is the proof the hold asked for.** A real driver
instruction, in the corpus, silently rendered as a no-op, and **outside
(s)'s six forms**. (s) repairs six rows of an unbounded class; (aa) is
the class. Minted now, with its count, before (s) lands. Pass state:
an unhandled two-byte opcode is `X86_INS_UNKNOWN`, never `NOP`.

### (ab) minted: the two-byte arm is blind to mandatory prefixes

Measured on the same pass: **1,091 of 48,241 two-byte instructions
(2.3%) carry `66`, `F2` or `F3`** by objdump (ACPI 299, usbxhci 222,
pci 190, storport 187, HDAudBus 72, HP serial 35, i8042prt 28, disk
20, nmap 6, modules 32, controls 0). The earlier 1,155 of 48,305 came
from the Ghidra dumps a clean destroyed and does not reconcile; see
the third amendment, item 7. The arm consults **none** of them — the grep
over `x86_decoder.c:1042`–`1340` for `PREFIX_OPSIZE|REP|REPNE` returns
nothing. That is an upper bound on the affected class, not a defect
count: carrying `66` does not prove the opcode is prefix-selected. It
is minted now with its number so (s)-as-scoped is recorded as a patch
over a structural gap rather than discovered to be one three fixes
later.

**(ab) gets a recorded count, not a red, and the reason is stated.**
Its only currently-measurable instance is `0F 78`, whose length differs
by prefix — bare 3 (Ghidra NONE, objdump 3), `66` 6, `F2` 6, both
double-attested, ours 4 for each — and that opcode is already inside
(s)'s scope. A separate (ab) red would duplicate an (s) red rather than
distinguish the class, which is the mask the alias table taught us to
avoid. (ab) is therefore recorded with its measurement and minted as a
red when the two-byte map becomes table-driven and an instrument can
separate "the arm ignored the prefix" from "this opcode's length is
wrong" — the same treatment (q) received.

**(aa) IS minted as a red today**, because it is separable: `0F A7`
XSTORE is double-attested at length 3, **our length is already 3**, and
only the identity is wrong — so the assertion is on identity alone and
cannot be satisfied by any length fix. `x64_RED_aa_unhandled_two_byte_
is_not_nop` (private `4e3fd07`), red now, and **(s) cannot close it**:
`0F A7` is outside (s)'s six forms, which is the point.

## 3. 3DNow is dropped from (s)'s scope, with the reason named

`0F 0F` has **zero witnesses**: zero corpus instances and zero fixture
rows. An arm no instrument can exercise is worse than a deferred one
because it ships looking finished. Adding a fixture row would need the
same after-the-`C3` care the RSM needed and would shift every address
below it. **So 3DNow leaves (s)'s scope**, and the prediction changes
accordingly:

> **(u) after (s) is predicted to report `wrong_opcodes=1: 0F0F`, not
> an empty set.** It is not closed by (s) and is not expected to be.

## 4. One arm covers `0F 20`–`0F 23` — shown from source

`x86_decoder.c:1267–1268`: `case 0x20: case 0x21:` / `case 0x22: case
0x23:` fall into one body. The single fixture row at `+5d` therefore
exercises the arm that serves all four. (The `0F 23` caveat from the
first amendment stands: (u) cannot confirm it, because Ghidra returns
NONE for its memory-form probes.)

## 5. The `mnemonic` class enters the prediction with its denominator

**Before (s), post-(o): 11,048 `mnemonic` rows across 16 inputs** —
ACPI 3279, storport 2327, pci 2189, usbxhci 1699, HDAudBus 518,
i8042prt 341, disk 293, HP serial 286, nmap 76, 8139too 21, ne2k 8,
iTCO 5, via-rng 3, ReactOS serial 1, fixture 2, beep 0.

Predicted after (s): **fixture 2 → 0** (both `0F 70` and `0F C4` rows
stop rendering as NOP), and **storport's `nostart` + `mnemonic` sum
falls by exactly 1** (its single `66 0F C5`; which of the two columns
it leaves depends on where the walk stands, so the conserved quantity
is the sum). **Every other input's `mnemonic` count is unchanged** —
including via-rng's 3, which contains the `xstore-rng` row (aa) owns
and (s) does not.

## 6. The 32 addresses, derived twice

Independently derived from the bytes by a second instrument — objdump's
own linear walk over the fixture's `0x6d`-byte `.text` — giving **32
starts**, identical to the oracle-plus-`RSM` construction, address for
address. The two derivations agree, so the assertion does not inherit
an oracle gap; and the fixture's difference of exactly one row *is* the
`RSM`, which is the same fact hold 7 turns on.

## 7. The two denominators, accounted

| instrument | starts |
|---|---|
| objdump linear sweep, 16 of 16 inputs | **576,115** |
| Ghidra flow-following, summed from the post-(o) differential's `ghidra=` | **512,000** |
| difference | **64,115** |

**What the flow-following walk does not reach**, and why the difference
is spread across every input at roughly a tenth of it: data embedded in
executable sections, alignment and file padding, and code no flow
reaches — a linear sweep decodes all three, a flow-follower none of
them. **The fixture proves the mechanism in one row: 32 versus 31, and
the extra is exactly the `RSM` after the final `C3`.** (The earlier
figure of 512,213 came from the banked per-instruction files, which
carry sections the harness does not compare; 512,000 is the
harness-comparable population and is the one used here.)

## 9. The ordering rule, with the addition

> (r1)–(r3) may change how `op_size` derives from `X86_PREFIX_OPSIZE`;
> (s) adds a **separate** consumption of that flag in the two-byte arm
> and touches neither `op_size` nor `stack_size`; **whichever lands
> second re-runs the other's reds *and the differential*.**

The flag is shared and the reds are per-opcode, so a per-opcode red
cannot see a shared-flag regression. Only the differential can.

# Third amendment: seven items, and one correction that matters more (2026-09-20)

## 0. The structural item: measurement inputs are no longer build output

`clean` destroyed measurement inputs three times — the four fetched
modules, then the oracle dumps twice — and each loss surfaced only as a
zero in a later count. Rule 27 caught all three, which is the rule
working and is also not a cure. The cure:

- `DIFFDIR` moves from `$(BUILDDIR)/differential` to
  `measure/differential`. **A `clean` can no longer reach it.**
- `clean` now prints what survived: `measurement inputs PRESERVED in
  measure/: N oracle dumps, M modules`. Visible at the moment, not
  three days later as a zero.
- `clean-measure` is a separate target, never a dependency, and prints
  the inventory it is about to destroy plus the sentence "every corpus
  count is unreproducible until `make differential-all` has been
  re-run."
- `scripts/denominators.py` **refuses** on a missing input and names
  the target that restores it, rather than counting 12 of 16.

## 1. The (aa) red asserts the class property. Read back verbatim

```c
if (n != 3) FAIL("length: expected 3 (setup, not the defect under test)");
if (d.instruction == X86_INS_NOP)
    FAIL("0F A7 XSTORE renders as NOP; an unhandled opcode must not be "
         "NOP (UNKNOWN or INVALID both pass; the class property is the assertion)");
```

The assertion is **`!= X86_INS_NOP`**, not `== XSTORE`. It closes the
moment the default arm stops assigning `NOP`, on one line, without
implementing a single opcode. The failure text said "must be UNKNOWN",
which named a repair the assertion does not require; corrected above so
the message and the assertion say the same thing. Suite after the edit:
`pass=93 xfail=20 fail=0 xpass=0 (tests=113)`, 25 suites, `SMOKE PASS`.

## 2. "30 of 256" was wrong, and the real shape is worse

Remeasured two ways. **From source, by brace depth** rather than by eye:
the two-byte switch runs `x86_decoder.c:1046`–`1319` and **59** opcodes
fall through to its `default:`, not 30. The 29 I missed are exactly the
arm's own `no_modrm` list — which does not exempt them, it only skips
the ModRM fetch before assigning `NOP`. Among them: `SYSCALL`,
`SYSRET`, `SYSENTER`, `SYSEXIT`, `RDTSC`, `WRMSR`, `RDMSR`, `UD2`,
`PUSH FS`/`POP FS`, `PUSH GS`/`POP GS`, and all eight `BSWAP`.

**At runtime the figure is larger still: 219 of 256** two-byte opcodes
render as `X86_INS_NOP` in 64-bit mode. The probe holds **nothing**
constant in ModRM — all 64 register cells `C0`–`FF` plus `mod=00` and
`mod=10`, because for `0F 00/01/18/AE` the digit is opcode and for
`0F 20`–`23` the mod bits are ignored — and the answer is
ModRM-independent: **0** opcodes render NOP for some forms and not
others. `X86_INS_UNKNOWN` is 0 and `X86_INS_NOP` is not, so this is
assignment, not zero-initialisation. Of the 219, 59 arrive at the
`default:`; the other 160 are explicitly cased and assigned `NOP` at 17
separate sites.

**And one of those sites has a green test defending it:**

```c
TEST(cmovcc_0F44);              /* 0F 44 C1 = CMOVE EAX, ECX */
if (d.instruction != X86_INS_NOP) FAIL("should be NOP");
```

A conditional move — a data-flow instruction — is asserted to be a
no-op by a passing test. The suite currently enforces the behaviour
(aa) says is wrong. That test has to be inverted in the same act that
fixes the arm, and it is named here so the fix is not surprised by it.

### The 59 are three kinds and need three answers

| kind | count | answer |
|---|---|---|
| real instructions | **39** | decode, or `UNKNOWN` — never `NOP` |
| deliberate traps `0B` UD2, `B9` UD1, `FF` UD0 | **3** | `INVALID`; the analyzer must read "unreachable marker" |
| genuinely undefined remainder | **17** | `INVALID` |

Real: `02 03` LAR/LSL, `05 06 07` SYSCALL/CLTS/SYSRET, `08 09`
INVD/WBINVD, `0E` FEMMS, `30`–`35` MSR and SYSENTER/SYSEXIT, `37`
GETSEC, `50` MOVMSKPS, `77` EMMS, `78 79` VMREAD/VMWRITE, `A0 A1 A8 A9`
PUSH/POP FS and GS, `A6 A7` PadLock, `AA` RSM, `B8` POPCNT, `BB` BTC,
`C4 C5` PINSRW/PEXTRW, `C8`–`CF` BSWAP, `F0` LDDQU.
Undefined: `04 0A 0C 0F 24 25 26 27 36 39 3B 3C 3D 3E 3F 7A 7B`.
39 + 3 + 17 = 59, and the three lists are disjoint.

**The traps are the worst of the three.** `UD1`/`UD2`/`UD0` are what a
compiler emits to mark unreachable code. Read as `NOP`, an
unreachable-code marker becomes "nothing happens", and the analyzer
walks straight through it into data. `UNKNOWN`, `INVALID` and `NOP`
must not print the same — rule 27, one level down, inside the decoder.

## 3. The denominators, from one computation

`scripts/denominators.py`, banked at
`docs/evidence/x64-denominators-2026-09-20.log`:

| figure | value |
|---|---|
| objdump linear sweep, all executable sections, 16 inputs | **576,115** |
| Ghidra flow-following, harness-comparable | **512,000** |
| difference | **64,115** |

Both are computed in one run, with per-input rows, a `!= 16` refusal on
the row count and a zero refusal per input. `64,115` is arithmetically
right **against 512,000** and wrong against 512,213; which population a
difference is taken against was being carried in prose, which is how
both readings survived.

**The 213 is unaccounted and cannot now be accounted.** 512,213 was
summed from the banked Ghidra per-instruction files, which carry
sections the harness does not compare. Those files lived in
`$(BUILDDIR)` and a clean destroyed them, so the figure is not
re-derivable today and **no difference may be taken against it**. It is
withdrawn from the documents in favour of 512,000, which is. The (q)
sentence that read "Ghidra over 512,213 starts" now reads 512,000.

*The instrument's own first run printed 591,696.* `objdump` wraps any
instruction of 8 or more bytes onto a second line that also begins with
an address, and counting those counts long instructions twice — 15,581
of them. The counting rule is now in the script's docstring, and the
fixture's 32 is what proves it: 34 matching lines, 2 continuations.

## 4. `0F 78` bare is single-attested, and that is stated

| form | Ghidra | objdump |
|---|---|---|
| `0F 78` bare, all three ModRM forms | **NONE** | 3 |
| `66 0F 78` | EXTRQ len=6 | 6 |
| `F2 0F 78` | INSERTQ len=6 | 6 |
| `F3 0F 78` | NONE | — |

Only the `66` and `F2` rows are double-attested. By standing rule the
bare row settles nothing, and (ab)'s deferral leans on the prefixed
rows, which do. (aa)'s own row is clean: `0F A7` is `XSTORE len=3` in
the **register** form, which is the form the red uses; `mod=00` and
`mod=10` are NONE, and `F3 0F A7` is `XSTORE.REP len=4`.

## 5. (aa)'s blast radius, with its denominator

**5 instructions of 48,241 two-byte instructions**, over 576,115
instructions in 16 of 16 inputs. The severity is in the *kind* of
error, not the count: a driver instruction rendered as a no-op is a
confident wrong answer, and the class behind the 5 is 219 opcodes wide.
Both halves are stated so (aa) is not read later as a coverage crisis.

## 6. (ab)'s trigger condition is in the open register

`docs/evidence/x64-open-register-2026-09-20.md` now carries every open
letter and, for the two deferred findings (q) and (ab), the **condition
that mints them**. It replaces the "Open after (x)" lines scattered
across three closing sections, which are historical records and should
not be edited to stay current.

## 7. The three that were not visible

**Mandatory-prefix count for (ab) — restated, and it does not
reconcile.** Today, by objdump over the 16 pinned inputs: **1,091 of
48,241** two-byte instructions carry `66`, `F2` or `F3` (2.3%). The
banked figure was 1,155 of 48,305. Both differ by exactly 64, so the
64 rows the earlier population had were all prefix-carrying — but the
earlier count came from the Ghidra dumps the clean destroyed, so the
two **cannot be reconciled today** and the objdump figure is the one
that has an instrument behind it. (ab)'s claim is unchanged either way:
the arm consults zero of them.

**`0F 20`–`23`: one arm, one witness, three opcodes with none.**
Source shows a single arm at `x86_decoder.c:1267`–`1268`. Corpus
witnesses by bytes over all 16 inputs: `0F 20` **218**, `0F 21` **0**,
`0F 22` **0**, `0F 23` **0**. The fixture row `0f 20 80` witnesses
`0F 20` alone. That the arm covers the other three is read from source
and has **no witness in the corpus**; it is not a measured claim and is
not presented as one.

**The `mnemonic` class denominator: 11,048 rows**, summed over exactly
16 `OPSUMMARY` rows of the post-(o) differential with the row count
asserted against the pinned population before summing. Printed by the
same run as the two denominators above, so the three cannot drift apart
again.

# Fourth amendment: the scope ruling, two rules, seven items (2026-09-20)

## Scope ruling recorded: (aa) lands before (s)

(s) repairs six forms sitting on an arm that mis-renders 219 opcodes.
Landing (s) first turns six reds green over a floor still wrong beneath
them, and patches the two-byte map twice instead of building it once.
**(s) is re-baselined on a correct default arm and lands second.** This
pre-registration survives entire — the census, the address sequence,
the (s)/(r) boundary sentence — and **every differential figure in it
is taken again after (aa)**, because (aa) moves the identity of 219
opcodes and the `mnemonic` class cannot be assumed still to be 11,048.

## 1. `512,000` is not a cap, and here is the decomposition

The suspicion was right to raise: 2⁹ × 10³ exactly, from 16 irregular
addends. It survives.

**The oracle's own totals sum to 512,221**, not 512,000, taken from the
`INSTRSTARTS total=` line each Ghidra run prints — a different field
from the `ghidra=` the comparer reports. The 221 is **entirely in the
four Linux modules**, and every other input has delta 0:

| input | dumped | compared | delta |
|---|---|---|---|
| ne2k-pci.ko | 1,244 | 1,193 | 51 |
| 8139too.ko | 4,077 | 4,026 | 51 |
| iTCO_wdt.ko | 956 | 907 | 49 |
| via-rng.ko | 246 | 176 | 70 |
| the other 12 | — | — | **0** |

**Mechanism, confirmed on via-rng, written in the direction the numbers
run** (dumped is the larger side): **Ghidra dumps starts in all four
executable sections of an ELF kernel module** — `.text`, `.init.text`,
`.exit.text`, `.altinstr_replacement` — **while `dump_starts`, the
decoder side, emits `.text` alone.** `dump_starts` prints `# .text
decoded=178 covered=517 of 517 bytes`, and 517 is exactly `.text`'s
`0x205`. The comparer can only compare what both sides emit, so the
excess is on the oracle side and the exclusion is imposed by the
decoder side. Dumped > compared, always, and never the reverse.

**The two identical 51s** (ne2k-pci and 8139too) are worth one line:
both are PCI Ethernet drivers built from the same kernel tree, and
their `.init.text` is the probe/remove boilerplate the module macros
generate, so equal start counts there are plausible rather than
suspicious. It is stated, not relied on. `0x7b + 0x28 + 0x0f = 174` bytes of extra code in
via-rng, which is the right scale for 70 starts.

So 512,000 is **a natural count minus a named, localised exclusion**:
512,221 dumped, less 221 starts in module sections the decoder-side
dump does not emit. No row limit, no truncation, no harness maximum
exists in `compare_starts.py`, `compare_operands.py` or
`InstrStarts.java`. **64,115 stands.** The roundness is a coincidence,
and it is now a decomposed one.

*This also fixes the shape of the 512,213 question: the three figures
are 512,221 dumped, 512,000 compared, and 512,213 from files that no
longer exist. The withdrawal stands.*

## 2. (ab) is minted, and the deferral was understated

The deferral said (ab)'s only measurable instance was `0F 78`. **That
was true of the length half only.** The identity half is 1,091
exposures — every two-byte instruction carrying `66`, `F2` or `F3`
decodes to whatever the bare form decodes to — and it is the same
failure as (aa): right length, wrong instruction.

`x64_RED_ab_two_byte_arm_ignores_mandatory_prefix`, red today. The
witness needs **no instruction modelled**, which is what makes it
closable:

| probe | Ghidra | objdump | ours |
|---|---|---|---|
| `0F AE C0` | NONE | `(bad)` | NOP, len 3 |
| `F3 0F AE C0` | RDFSBASE len 4 | 4, `rdfsbase %eax` | NOP, len 4 |

One is invalid in both instruments and one is a valid four-byte
instruction in both, so any decoder that reads the prefix must give
them **different** answers. The assertion is that inequality.
**(aa) cannot close it**: making unhandled opcodes `UNKNOWN` leaves
both arms `UNKNOWN`, which is still the same answer. Outside (s)'s six
forms. Corpus witnesses for this exact encoding: **0** — the red is a
unit instrument, stated rather than implied.

## 3. `48,305 → 48,241` propagated, by enumeration not by assertion

`grep -rn "48,305\|48305" docs/ tools/translator/` returns **three
lines, all in this file**, and all three are already the corrected
form: the summary table carries 48,241 with the supersession noted, and
the two prose references name the superseded figure as superseded. No
other document, test, script or log carries it. The same grep for
`1,155` returns this file twice and four oracle logs where `1155` is a
slot number. The enumeration is the evidence; the correction was
already complete.

## 4. The objdump wrap, scoped

A continuation line carries **bytes and no mnemonic**. So:

- **At risk: line-counting denominators.** One figure was affected and
  it was mine, today, in the first run of `denominators.py`: 591,696
  instead of 576,115. No banked figure used line counting — 576,115
  itself is reproduced exactly by the mnemonic-anchored counter.
- **Not at risk: pattern-matched counts**, including the 218 CR/DR
  moves and (z)'s attested set, because the pattern is anchored on the
  mnemonic field a continuation line does not have.
- **A third class, which is the one worth naming:** a *raw byte-string
  grep* over objdump output would be at risk, because a continuation
  line is nothing but bytes and `66 a9` can appear inside the tail of a
  longer instruction.

So every corpus count a red depends on was re-taken with the
mnemonic-anchored parser:

| count | banked | today |
|---|---|---|
| (r1) `66 68` | 0 | **0** |
| (r2) `66 A9` | 1 | **1** |
| (r3) `66 F7 /0\|/1` | 8 | **8** |
| (s) `0F C4` / `0F C5` / `66 0F C5` | 1 / 2 / 1 | **1 / 2 / 1** |
| (aa) `0F A7` | 1 | **1** |
| (q) VEX / EVEX / REX2 | 0 / 0 / 0 | **0 / 0 / 0** |
| control `C3` RET | 6,457 | **6,458** |

Every red-bearing count reproduces. The control RET differs by one and
is **not** reconciled: it is a control, no red rests on it, and the
honest record is that it moved by one under a counter whose rule is now
written down while the earlier counter's rule is not.

## 5. The fixture gains the three missing witnesses: v13

`0F 20` had 218 corpus witnesses and `0F 21`, `0F 22`, `0F 23` had
zero, so "one arm covers all four" was source-read and witnessed once.
Three rows, nine bytes:

```
40105d: 0f 20 80    mov %cr0,%rax     (s6)  double-attested len 3
401060: 0f 21 80    mov %db0,%rax     (s6b) double-attested len 3
401063: 0f 22 80    mov %rax,%cr0     (s6c) double-attested len 3
401066: 0f 23 80    mov %rax,%db0     (s6d) objdump 3, Ghidra NONE
```

`0F 23` at `mod=10` is **single-attested** and is named as the weaker
row rather than folded in with the other three. The nine bytes shift
(b) to `401069`, RET to `401073` and the RSM to `401074`, exactly as
predicted before assembling; the new fixture is
`b19fcb6911e66fa66bdda105ee5e047f93fe4cafae85fbddb3fe7480dbaee9b4`.
`x64_RED_s_mov_cr_mod_ignored` now **walks all four opcodes**, so a fix
keyed on `0F 20` alone leaves it red.

## 6 and 7. The inversion, and the register made executable

**The nine defect-defending tests are neutralised now, not at (aa)'s
fix**, so no window exists in which the suite asserts both things. The
sweep rule 30 asks for was run over all 94 passing tests in the decoder
suite. Nine assert `X86_INS_NOP` for something that is not a NOP, and
each **names the real instruction in its own comment before asserting
it is a no-op**: `cmovcc_0F44` (CMOVE), `bt_rm_r_0FA3`,
`bt_rm_imm8_0FBA`, `cmpxchg_0FB1`, `xadd_0FC1`,
`unknown_0f_modrm_recovery` (PREFETCH), `desync_recovery_BT_then_IN`,
`three_byte_0F38` (PSHUFB), `three_byte_0F3A` (PALIGNR).

Each keeps its **length** assertion, which is the oracle-backed
content, and loses the identity clause, which was read off the product.
Three `X86_INS_NOP` assertions survive the sweep and all three are
correct: `0x90`, `0F 1F` multi-byte NOP, and the `0x90` that proves the
walk continues past an INVALID.

**The register is executable.**
`open_register_is_exactly_the_xfail_list` parses the register's red
rows and fails the build when they differ from `xfail_names[]` in
either direction, refusing on a zero parse. It earned itself
immediately: it failed the moment (ab) was minted and not yet listed.

Suite: `pass=94 xfail=21 fail=0 xpass=0 (tests=115)`.

# Fifth amendment: four items, and a letter the split forced (2026-09-20)

## 1. The nine gained a correct expectation, and a new letter came with it

Deleting a false assertion is not repairing it. Each of the nine keeps
its length assertion **and now asserts the class property**, with the
SDM mnemonic carried as the pre-registered target:

| test | instruction | authority |
|---|---|---|
| `cmovcc_0F44` | CMOVcc | `0F 44 /r`, SDM Vol 2A |
| `bt_rm_r_0FA3` | BT r/m,r | `0F A3 /r` |
| `bt_rm_imm8_0FBA` | BT r/m,imm8 | `0F BA /4 ib` |
| `cmpxchg_0FB1` | CMPXCHG | `0F B1 /r` |
| `xadd_0FC1` | XADD | `0F C1 /r` |
| `desync_recovery_BT_then_IN` | BT | `0F A3 /r` |
| `three_byte_0F38` | PSHUFB | `0F 38 00 /r`, Vol 2B |
| `three_byte_0F3A` | PALIGNR | `0F 3A 0F /r ib`, Vol 2B |

**The ninth is different and the sweep is why.** `unknown_0f_modrm_
recovery` decodes `0F 0D C0`, and that is not an unmodelled instruction
— it is **#UD**. Pinned oracle row `0F0DC0` is NONE, objdump prints
`prefetch (bad)`, while the memory forms are 3 and 7 in both
instruments. The test asserted length 3, which is what the fallback
does, for an encoding that has no length at all. It is now a **(t)**
red asserting refusal, and it is (t)'s first double-attested witness.

### (ac) minted: the explicitly-cased half of the NOP class

Converting the eight forced a boundary that had not been drawn.
**219 opcodes render as NOP. 59 reach the default arm and 160 do not —
they are assigned NOP at 17 explicit `case` sites.** All eight of the
converted tests are in the 160, verified as a set difference rather
than by inspection.

**So (aa) closes none of the eight.** A fix to the default arm leaves
160 opcodes still rendering real instructions as no-ops. That is (ac),
minted now with its count, and (aa)'s pre-registration must predict the
eight staying red through it rather than discovering it afterwards.

## 2. The sweep's predicate and denominator, stated — and it was widened

**What ran first was a NOP grep, which finds one symptom of rule 30,
not its class.** Stated plainly rather than implied.

**The widened predicate**, banked at
`docs/evidence/x64-rule30-sweep-2026-09-20.log`: for every *passing*
test that decodes a literal byte array and asserts a length,
disassemble those exact bytes **in the test's own mode** and compare.
An expectation read off the decoder disagrees with objdump; one taken
from the SDM or an oracle does not.

| | count |
|---|---|
| passing tests (the denominator) | **94** |
| swept by this predicate | **78** |
| length agrees with objdump | 77 |
| **length disagrees** | **1** — `unknown_0f_modrm_recovery` |
| not swept (no single literal array with a length assertion) | **16** |

The 16 are named individually in the log: the two table-consistency
sweeps, the guards, the walker tests, and the register test. **The one
disagreement is a real catch by predicate**, and it is the `0F 0D C0`
row above — found by the widened sweep, invisible to the NOP grep.

*A first attempt at this sweep mis-detected the mode on four tests and
reported five disagreements. Three were 64-bit tests read as 32-bit and
one was a 16-bit test. Corrected before the result was used; the mode
now comes from which helper the test calls.*

**The remainder, named rather than claimed:** this predicate checks
**lengths only**. An operand count, a register number or an immediate
copied from the decoder's own output is the same defect and this sweep
would not see it. The nine identity expectations were caught by
*symptom*, not by predicate. **No instrument covers the rest today**,
and that is the unswept remainder.

## 3. The stray one, accounted

The control `C3` count did not move under the parser change at all.
**The banked 6,457 was over the 15 corpus inputs; today's 6,458 is over
16, and the extra one is the fixture's own RET.** Per input: ACPI 1776,
storport 1347, pci 1265, usbxhci 1087, HDAudBus 295, serial 199,
i8042prt 195, disk 146, nmap 136, ReactOS serial 11, four modules 0,
beep 0, fixture 1 — and 6,458 − 1 = 6,457. Attributed by a named rule:
the denominator changed, not the counter.

## 4. Direction of the 221, fixed in place

Corrected above, in item 1 of the fourth amendment: Ghidra dumps all
four executable sections of an ELF module and `dump_starts` emits
`.text` alone, so dumped exceeds compared and the exclusion is imposed
by the decoder side. The two identical 51s get their line there too.

## Binding on (aa)'s pre-registration, recorded here so it cannot drift

The ten standing conditions apply unchanged, plus:

- **Rule 29: the prediction is stated over the opcode space as well as
  the corpus.** Both numbers, in the same sentence: occurrences out of
  48,241, and opcodes out of 219.
- **The expected-XPASS set names the nine converted tests
  individually**, and the prediction for eight of them is that they
  **do not move**, because they are (ac).

Suite: `pass=85 xfail=30 fail=0 xpass=0 (tests=115)`, 25 suites,
`SMOKE PASS`.
