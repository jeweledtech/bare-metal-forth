# CR/DR operands in the decoder: pre-registration (2026-09-22)

**Written before the change.** This follows `(au)`, which named the family
and turned 220 differential rows from *undecoded* into operand mismatches.
Outcomes go BELOW the line, from the artefact only.

**Scope: the decoder's operands only.** The lifter carrying them (which is
what would move the 12 `mov %cr8` park stops) is the next item, with its own
reds and its own bound. The two bounds are kept separate below.

## The 220, split by direction (measured)

| in the 220 | rows | where |
|---|---|---|
| CR8 **reads** (`44 0F 20 …`) | 217 | the HP drivers |
| CR0 / DR0 **reads** | 2 | fixture only |
| CR0 **write** (`0F 22`) | 1 | fixture only |

**Three defects, read from `x86_decoder.c:1382–1392`, and they do not
separate the same way:**

1. **Typing: all 220.** The control or debug register is stored as an
   ordinary register number, so even `CR0` prints as `RAX`.
2. **REX.R ignored: the 217 CR8 reads.** The CR number is `modrm.reg`
   without REX.R, so `CR8` reads as 0.
3. **Operand order: the 1 fixture write.** `0F 22`/`23` (`MOV CRn/DRn, r`)
   take `0F 20`'s order, destination as source. **This has 0 rows among the
   16 differential inputs, but it is not enumeration-only:** the
   system-family census counts writes elsewhere in the corpus: `MOV CR8<-r`
   5 / 53 / 113 on Dell / ASUS older / ASUS newer, CR0/CR3/CR4 writes on ASUS
   newer, and 119 CR writes in the macOS kernel. The oracle does not cover
   those inputs.

A fourth defect, found on reading the same site: the operand size is fixed
at 8. The SDM makes it 64-bit in 64-bit mode and 32-bit otherwise. It has
**no measured rows** (no PE32 input carries a CR move) and is fixed at the
same site, labelled enumeration-only.

## The representation

Control and debug registers stay **register** operands, which is how Ghidra
types them (`R:CR8`). **The pinned register map**
(`operand-diff-prereg-2026-09-15.md`: 0–15 GPR, 16–19 SPL/BPL/SIL/DIL,
32 RIP) **is extended: 40–55 = CR0–CR15, 56–71 = DR0–DR15.**

**Readers of a register number, enumerated from source (rule 24):**
- `dump_starts.c reg_name()` and `x86_decoder.c x86_reg_name()`: return
  `?`/`???` above 15 today, and gain the CR/DR names in Ghidra's spelling.
- `uir.c reg_bits()` ignores numbers above 15.
- `semantic.c`'s walk guards `reg < 64`.
- The lifter carries **no** operand for `MOV_CR`/`MOV_DR` (unmodelled, no
  `dest`), so no UIR value changes.

## Bounds, kept separate

- **This item (decoder operands):** the **220** differential rows. Corpus
  CR/DR forms without an oracle (`system-family-census`: CR/DR moves 195 /
  3,378 / 5,453 / 4,038 on HP / Dell / ASUS older / ASUS newer; 40 in the
  macOS kexts and 243 in the kernel) are counted, not scored.
- **The next item (the lifter carrying them):** the **12** `mov %cr8` park
  stops in `mlx4_bus`. **This item cannot move them.**

## Predictions

| # | prediction |
|---|---|
| O1 | one XPASS, the operands red; no other test moves |
| O2 | differential: **all 220 go `reg` → `ok`** (217 + 2 + 1); **no other row changes class** |
| O3 | `-t uir` **byte-identical** on all 12 inputs (the lifter carries no operand here) |
| O4 | park outcomes **byte-identical** on all four machines; the 12 `mov %cr8` stops stay |
| O5 | suites green; tests +1; 14 reds |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `x86_decoder.c` `11b0919dce82680b` (before: `c6cb4cbae0d601d7`),
`dump_starts.c` `530dc7806ad05c1c`, `dump_starts` `a0b2c054139d65b6`,
`bin/translator` `2ee664f29db10b42`. The differential was taken against the
same banked, pinned oracle as `(au)`.

| # | predicted | observed |
|---|---|---|
| O1 | one XPASS | **exactly one**, `x64_RED_av_crdr_operands`: eight encodings, both directions, CR and DR, REX.R, REX.B and a 32-bit form |
| O2 | all 220 `reg` → `ok`; no other row changes class | **exactly that**: 220 rows `reg` → `ok` (Ghidra `MOV RAX, CR8` and ours `MOV RAX, CR8`), 0 other changes |
| O3 | `-t uir` byte-identical | **held**, 0 of 12 inputs differ |
| O4 | park outcomes byte-identical; the 12 `mov %cr8` stops stay | **held**: 0 changes on all four machines |
| O5 | suites green; tests +1; 14 reds | **held**: 397 tests across 27 suites, 14 reds; decoder pass 103 |

**What the 220 contained, now that each is resolved:** the typing defect
was in all of them. REX.R accounts for 217; the operand order and the
32-bit size are asserted by the red (1 fixture row, and 0 rows,
respectively). The order defect's corpus witnesses (the CR writes in the
census) lie outside the oracle's inputs and stay unscored.

**`(au)` and `(av)` together:** 224 differential rows went from *undecoded*
to *ok*: the whole system family present on the 16 oracle inputs. The next
item's bound is unchanged at 12: the lifter carrying the operand of an
unmodelled `MOV_CR`, which is the only way the `mov %cr8` park stops move.
