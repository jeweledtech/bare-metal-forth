# (bf) SSE rows named only in the ModRM forms the SDM allows: pre-registration (2026-09-23)

**Written before the change.** Owner ruling: the full bound is derived from
**the SDM's operand column**, not from the 24 cells (bd)'s prefix sweep
happened to expose. This is a spec-read item, not a sweep item. Outcomes go
BELOW the line.

## The bound, read from SDM 325462-092

For each of the 270 family keys, the legacy instruction form was read off
its Vol. 2 page, and its r/m operand classified as follows:
- **both forms**, if written as a register-or-memory alternative
  (`xmm2/m128`, `r/m32`);
- **memory only**, if written as a bare `m64`/`m128`/`mem`;
- **register only**, if the form names no memory operand.

**All 270 keys had a form read.** Three parser artefacts were corrected by
reading the text:
- **Split forms:** MOVSS/MOVSD `F3`/`F2 0F 10`, and `0F 12`/`0F 16`, have a
  separate register row and memory row, so both forms are valid.
- **Wrapped lines:** the seven SHA rows wrap `xmm2/m128` onto the next line,
  so they are both forms.
- **Prose collision:** PTEST collided with the prose words `AND`/`NOT`;
  its form is `xmm2/m128`, both forms.

| class | keys | instructions |
|---|---|---|
| **register only (U)** | **10 keys, 17 names** | MOVMSKPS/PD (`0F 50`); `66 0F 71`/`72`/`73` shift groups (PSRLW, PSRAW, PSLLW, PSRLD, PSRAD, PSLLD, PSRLQ, PSRLDQ, PSLLQ, PSLLDQ); PEXTRW (`66 0F C5`); PMOVMSKB (`66 0F D7`); MASKMOVDQU (`66 0F F7`); MOVDQ2Q/MOVQ2DQ (`F2`/`F3 0F D6`) |
| **memory only (M)** | **11 keys** | MOVLPS/MOVHPS stores (`0F 13`, `0F 17`); MOVLPD/MOVHPD (`66 0F 12/13/16/17`); MOVNTPS/PD (`0F 2B`, `66 0F 2B`); MOVNTDQ (`66 0F E7`); MOVNTDQA (`66 0F 38 2A`); LDDQU (`F2 0F F0`) |

- **The table's recalled operand codes match the SDM exactly**: its `U`/`N`
  rows equal the 10 register-only keys, and its `M` rows equal the 11
  memory-only keys, with 0 differences either way.
- **The shipped decoder names all 28 excluded forms** (17 register-only
  names in memory form, 11 memory-only in register form): **28 of 28**.
- **objdump (binutils 2.42) refuses all 28** as well. The bound is **28**,
  where the prefix sweep saw 24.
- **Reach: 0 corpus rows, a measured zero.** The same scan of the
  post-(bd) sweep counts **13,481** valid-form rows of the same 21 keys.

## The change

The generator carries a **ModRM constraint** per row, derived from its
SDM-checked operand codes: `U`/`N` → register form only, `M` → memory form
only. `sse_identity()` returns **UNKNOWN** for a row met in its excluded
form, with the length unchanged, following (bd)'s precedent: no claim, and
not INVALID with its length-1 resync. Rows whose names split by form
(`0F 12`/`0F 16`) are unaffected.

## Predictions

| # | prediction |
|---|---|
| F1 | the `(bf)` red, **widened before the fix from its 10 cases to all 28 SDM-derived excluded forms**, XPASSes; nothing else moves (`(ba)`'s 283 encodings use only allowed forms and stay green) |
| F2 | across the 73,152-slot prefix sweep, exactly the `66`-prefixed mod-validity cells change name (the 24 seen by (bd)), and 0 lengths change |
| F3 | corpus sweep byte-identical (0 rows, measured) |
| F4 | differential, `-t uir` and park census byte-identical |
| F5 | suites green; tests unchanged (the red is widened, not added); reds 14 → 13 |

---

## Outcome

*(below this line, from the artefact only)*
