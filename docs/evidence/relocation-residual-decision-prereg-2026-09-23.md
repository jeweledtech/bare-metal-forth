# The relocatable-module residual: decision and pre-registration (2026-09-23)

**Written before the change.** (b), (c) and (p) each recorded this class
and moved on. Owner ruling: decide it now, as an item with a bound or as an
explicit exclusion printed in the differential's own output. Outcomes go
BELOW the line.

## Bound, measured first, across all 16 oracle inputs

**Only 4 inputs are relocatable** (`ET_REL`): the `.ko` modules
`8139too`, `iTCO_wdt`, `ne2k-pci` and `via-rng`, which are **4 distinct
binaries by sha256** (`d3780549`, `cd838455`, `8197408b`, `b24f0280`).
The other 12 are linked images, which both instruments load at the
preferred base. Measured on the post-(p) dumps.

**A row is relocation-bearing when the input's own relocation table puts a
relocation offset inside the row's bytes** (`readelf -rW`, the `.rela<sec>`
of the row's section). This is read from the binary, not inferred from our
output's shape.

- **895 relocation-bearing rows, and all 895 disagree with the oracle**
  (addr 664, imm 168, mem 24, nostart 39). **0 are in the 12 linked
  inputs.**
- **16 distinct encodings** (mnemonic × relocation type), led by
  `CALL`/`R_X86_64_PLT32` 500, `MOV`/`R_X86_64_32S` 194, `JMP`/`PLT32` 95
  and `MOV`/`R_X86_64_PC32` 50.

**Relocation is one of three mechanisms.** Split disjointly, the modules'
**6,523 rows** are:

| mechanism | rows | 8139too / iTCO_wdt / ne2k-pci / via-rng | what it is |
|---|---|---|---|
| ok | 4,503 | 2,771 / 698 / 908 / 126 | |
| **R**: a relocation inside the row | **856** | 607 / 103 / 126 / 20 | we do not apply relocations; the oracle does |
| **P**: section placement | **533** | 338 / 80 / 99 / 16 | we place each section at 0; Ghidra lays sections out from `0x100000`. Every one satisfies *ours + Ghidra's section base = Ghidra's*, **exactly**, with no relocation involved (branch targets inside the module) |
| **U**: a section we do not load | **221** | 51 / 49 / 51 / 70 | `.init.text`, `.exit.text` |
| **none of these** | **410** | 310 / 26 / 60 / 14 | **real decoder signal**: reg 345 (e.g. `push %r15` read as RDI, the open (d') REX.B red), undecoded 30 (CMOVcc), opcount 24 (`nop` with operand), mnemonic 7 (`rep stosq`, `outsw`), nostart 4 |

(R here is 856, not 895: the 39 relocation-bearing `nostart` rows are in
unloaded sections, so they are counted under U.)

**U is already outside the denominator, and nothing says so.** The
comparer iterates over *our* sections only (`compare_operands.py`,
`for sec in ob`), so the 221 rows in sections we do not load never enter
it. That is why the pinned denominator is **512,000**: 512,221 Ghidra rows
less these 221. It is the silent omission the ruling forbids, and it was
already in place.

## The decision: exclusion, per row by mechanism, printed by the comparer

**The bound is small, and it is entirely outside the product's target.**
The 1,610 load-model rows are 0.31% of 512,221, and all of them are in 4
relocatable test objects; 0 are in shipped, linked binaries. So applying
relocations is not taken as an item. The owner's preference and the
measurement agree, but the measurement is the reason.

**The exclusion cannot be the whole module, as offered.** Dropping the four
modules would drop the **410 rows that are real decoder signal**,
including the modules' witnesses of the open (d') red. That would conceal
defects (canonicalizer stopping rule). So the exclusion is per row, and
each mechanism is handled on its own terms:

- **R → a new class `reloc`, excluded from the denominator.** It applies
  only when mnemonic and operand count agree, and the mismatch is in an
  `addr`/`imm`/`mem` operand. A relocation-bearing row whose mnemonic,
  count or decode is wrong keeps that class. **Defect not hidden:** a
  wrong opcode, length or operand count on a relocated instruction.
  **Defect hidden, stated:** a wrong register inside a relocated memory
  operand's base or index would be classed `reloc`; the 24 `mem` rows are
  where that could live.
- **P → rebased, not excluded.** For an `ET_REL` input only, our `A:`
  operands are compared after adding Ghidra's section base, since we have
  no load address and Ghidra's is its own choice. Those rows stay in the
  denominator and are measured. **Defect not hidden:** a wrongly decoded
  branch displacement still disagrees after rebasing.
- **U → printed, as today excluded.** A line per unloaded section with its
  row count, and a total on `OPSUMMARY`.

**The printing is the point.** The per-input summary gains
`reloc_excluded=` and `unloaded=` fields, and an `EXCLUDED` line lists them
with the reason, so the exclusion is in the instrument's output and not in
a commit message or in this doc.

**How the comparer learns relocations:** `dump_starts` (a measurement tool,
not the product) prints one `#R <section> <offset> <type>` line per
relocation in an `ET_REL` input, and `# ... file_type=REL` in its header.
Every existing reader skips `#` lines, so no reader changes meaning.

## Predictions

| # | prediction |
|---|---|
| Q1 | the 12 linked inputs: **every existing count identical**; only the new fields appear, at `reloc_excluded=0 unloaded=0` |
| Q2 | control: `dump_starts`'s `#R` lines equal `readelf -rW`'s relocation entries for the loaded code sections, per module, **nonzero** |
| Q3 | **856** rows → `reloc` (607 / 103 / 126 / 20), leaving the denominator |
| Q4 | **533** rows → `ok` (338 / 80 / 99 / 16); **no row that was `ok` changes class** |
| Q5 | `unloaded` printed: **221** (51 / 49 / 51 / 70) |
| Q6 | the **410** keep their classes exactly (reg 345, undecoded 30, opcount 24, mnemonic 7, nostart 4) |
| Q7 | the alias-table hash is unchanged; `make test` unchanged (401 tests, 12 reds) |

---

## Outcome

*(below this line, from the artefact only)*
