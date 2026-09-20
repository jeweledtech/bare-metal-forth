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
