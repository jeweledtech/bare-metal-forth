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
| two-byte (`0F xx`) instructions | **48,305** |
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
512,213 starts). **(q) stays unminted on a measured zero across every
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
and its named baseline describe the same artifacts, and the four module
rows are **not** provisional.

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
mnemonics of 512,213 starts, 2026-09-19). So (q)'s zero rests on
**two** instruments: objdump over 576,115 instructions in 16 of 16
inputs, and Ghidra over 512,213 starts in 16 files. That is still a
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
