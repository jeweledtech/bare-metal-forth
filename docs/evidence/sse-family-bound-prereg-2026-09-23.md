# The SSE family: bound, and pre-registration of the decoder item (2026-09-23)

**Written before any SSE code exists.** Owner ruling: the item's
justification is the corpus, not stage 2; the family is fixed from the SDM
before counting; the bound is stated with distinct encodings and distinct
binaries by sha256 beside it; XMM is represented from the CR/DR template.

**Stage 2's fourteen rows are a consequence of this item, not a reason for
it.** They are banked in `stage2-row-targets-prereg-2026-09-23.md`, and none
of the figures below counts them.

## 1. The family, fixed before counting

**Definition:** the legacy-encoded (non-VEX) entries of the SDM Vol. 2
Appendix A opcode maps (Table A-3, two-byte `0F xx`; Table A-4, `0F 38 xx`;
Table A-5, `0F 3A xx`) **whose operand codes include V, U or W**, the
addressing methods that select an XMM register (A.2.1). The mandatory
prefix (none / `66` / `F3` / `F2`) is part of the key, because the same
opcode is MMX with no prefix and XMM under `66`.

**270 keys: 188 two-byte, 57 in `0F 38`, 25 in `0F 3A`.** They are held as
data in one table, `sse_family.py`, which the census and the differential
both read.

**Out, by the same definition:**
- MMX-only entries (P/Q/N operands and no V/U/W);
- `0F AE` (LDMXCSR/STMXCSR, FXSAVE, the fences: no XMM operand);
- MOVNTI, POPCNT/TZCNT/LZCNT, MOVBE/CRC32, and INVEPT/INVVPID/INVPCID;
- everything VEX/EVEX-encoded ((q), measured zero).

**Provenance gap, stated:** no SDM copy is banked in this workspace. The
table was written from the maps' structure, so every hit is
**cross-checked against objdump (binutils 2.42, pinned)** at the same
offset. A row counts only where objdump puts an instruction whose mnemonic
begins with the table's SDM mnemonic there.
- **43 of 1,260,897 hits were not confirmed**, and they are printed, not
  dropped. The example read for each of the 12 keys shows one of two
  shapes: objdump splitting off a REX that does not immediately precede
  the opcode (5 keys, 32 rows), or no objdump boundary at that offset
  (7 keys, 11 rows).
- **In none did objdump name a different instruction.**
- Banking the SDM section and citing it entry by entry is owed before the
  table is treated as more than cross-checked.

## 2. The bound: corpus

**Method:** the census's own method (`system-family-census-2026-09-22.md`).
- The same extracted code sections are swept linearly by the shipped
  decoder (`x86_decoder.c` `42e45744`, the post-(p) build).
- Family membership is read from the bytes (rule 25). A row counts only
  where objdump confirms it.
- Scripts live outside every repository, in `~/corpus/tools-2026-09-23/`:
  `sse_family.py` `46797032`, `sse_sweep.c` `09fc8700`, `sse_agg.py`
  `6a6f1146`, with the UNKNOWN totals from the existing `decode_rate2.c`
  `20f5a027`.

**The shipped decoder names none of it: 100% `UNKNOWN` in every set, and
its length equals objdump's on all 1,260,854 confirmed rows.** So this item
is identity and operands, not lengths.

| set | inputs | SSE-family rows | distinct keys (of 270) | distinct binaries with any (sha256) | share of UNKNOWN | share of UNKNOWN excluding `int3` |
|---|---|---|---|---|---|---|
| HP | 8 | 3,856 | 23 | 8 | 7.5% | **60.5%** |
| Dell | 446 | 201,283 | 100 | 431 | 9.5% | **62.3%** |
| ASUS (older) | 455 | 207,055 | 128 | 438 | 11.2% | **64.0%** |
| ASUS (newer) | 505 | 227,886 | 108 | 490 | 9.3% | **57.4%** |
| Mac userland | 621 | 436,147 | 183 | 352 | **63.8%** | 63.8% |
| macOS dexts | 17 | 7,244 | 89 | 11 | 58.7% | 58.7% |
| macOS kernel collection | 400 | 177,383 | 178 | 99 | 39.3% | 39.3% |

**Across machines (the standing caution: shared drivers are not
independent sites):**

| pool | raw rows | rows counted once per distinct binary | distinct binaries (sha256) | distinct keys |
|---|---|---|---|---|
| Windows, 4 machines | 640,080 | 628,526 | 1,326 | 139 |
| macOS (userland + dexts + KC) | 620,774 | 619,061 | 462 | 205 |
| **all** | **1,260,854** | **1,247,587** | **1,788** | **217 of 270** |

The Windows sets' dominant UNKNOWN is `int3` padding, so their share is
stated with and without it. Once padding is set aside, **the SSE family is
the majority of what this decoder cannot name on every Windows machine and
on the Mac**. For the KC, the kernel collection's kext binaries are
identified by the sha256 of their extracted `__text`, since they are not
separate files.

## 3. The bound: the differential (the oracle's 16 inputs)

**7,301 rows are in the family by their bytes, and all 7,301 are
`undecoded`.**
- That is **58.0% of the 12,585 undecoded rows**.
- They lie in **9 distinct binaries**: the 8 HP drivers (ACPI 2,070,
  storport 1,570, pci 1,552, usbxhci 1,111, HDAudBus 364, i8042prt 225,
  serial 206, disk 202) and the fixture (1).
- They span **31 of 270 keys**, led by `0F 11` 3,134, `0F 10` 1,455, `0F 57`
  1,393, `F3 0F 7F` 383, `0F 29` 210, and `F2 0F 10`/`11` 203 each.
- The four Linux modules and the PE32 controls have **0**.

**The two figures quoted for this item were `movups` alone:**
- **4,589 is Ghidra's `MOVUPS` among the undecoded differential rows**,
  unchanged by (p). MOVUPS plus MOVAPS is 4,927. The family is 7,301.
- **24.5% was `movups` alone among the Mac userland's unknowns**
  (179,576 of 733,017, measured before (au) and (p)). The family's share
  now is 63.8% (436,147 of 683,800).

Neither is used below. Both understated the family.

## 4. The bound: the product

- **Park census:** of the **47** couldn't-tell walks (0 / 16 / 17 / 14),
  **2** stop at a family instruction. Both are `movsd` (`F2 0F 10`) in
  `IPMIDrv.sys`: one driver on two builds.
- **Stage 2:** the 14 banked rows, a consequence (see above).

Small, and stated as small. **The item's size comes from sections 2 and 3,
not from here.**

## 5. XMM, from the CR/DR template

This is derived from `fix-crdr-operands-prereg-2026-09-22.md`, re-read
against source now:

- **The pinned register map is extended: 72–87 = XMM0–XMM15**, spelled as
  Ghidra spells them (`XMM0`). CR is 40–55 and DR is 56–71.
- **MMX is not added:** the 8 family keys that carry an MMX operand
  (`0F 2A`/`2C`/`2D` without `F2`/`F3`, and `F3`/`F2 0F D6`) have **0
  corpus rows**. They are named with their SDM operands when they occur,
  and are enumeration-only until then.
- **Readers of a register number, enumerated from source (rule 24):**
  - `dump_starts.c reg_name()` and `x86_reg_name()` gain the names;
  - `uir.c reg_bits()` returns 0 above 15 (`uir.c:838`), so an XMM
    destination is *seen, writes no general register*;
  - every `holds[]`/`released[]` index in `semantic.c` is a constant or
    guarded `>= 0 && < 64` (lines 467, 496, 576, 578, 582, 591–592). XMM
    numbers are ≥ 72, so they can neither alias a tracked register nor
    index past the arrays.
- **A limit, named and not built:** a base spilled through an XMM register
  (`movq %rax,%xmm0` … `movq %xmm0,%rcx`) would be lost by the walk. That
  is a missed park, not a false one.

## 6. The item, as proposed (the staging is for ruling)

1. **Decoder: identity and operands together**, for all 270 keys. XMM is
   typed on the extended map; operand order and size come from the
   table's SDM operand codes. **I propose one item, not (au)'s split into
   identity then operands.** Identity alone would move the 7,301 rows
   from `undecoded` to `opcount` (named, no operands). That is churn which
   the operand half then undoes, and nothing is learned in between that the
   bound above does not already say. Two reds (identity; operands), one
   gate.
2. **Lifter:** the family → `UIR_UNMODELLED`, carrying operand 0 as `dest`
   only where it is the complete register write set, under the existing
   (as) contract. So `movups (%rbx),%xmm0` is *seen, no general register*,
   and `movups %xmm0,0x28(%rdi)` is a memory `dest`. **This is what flips
   stage 2's rows**, and it gets its own red and bound.
3. **Stage 2** flips to exactly the banked rows, with nothing else moving.

## 7. Predictions for step 1 (the decoder item)

| # | prediction |
|---|---|
| S1 | the two reds XPASS, and nothing else moves |
| S2 | differential: **all 7,301 rows leave `undecoded`, and no row outside them changes class**. **No prediction that all reach `ok`.** Ghidra's spelling of compare predicates (`CMPPS` imm8 vs `CMPLTPS`), `MOVD`/`MOVQ` under REX.W, and memory-operand forms are compared for the first time. Every row that does not reach `ok` is reported with its class |
| S3 | corpus re-count with the same scripts: the family goes from 100% `UNKNOWN` to **0%** on every set, lengths still equal to objdump's on every row, and the 43 unconfirmed rows unchanged |
| S4 | `-t uir`: line counts identical; the only changed lines are `unknown` → `unmodelled` at family rows (a named instruction with no lifter case stays unmodelled until step 2) |
| S5 | park census: **outcomes identical on all four machines**. Step 1 carries no `dest`, so the 2 `IPMIDrv` stops stay |
| S6 | suites green; the tests rise by the two reds; the register stays at 12 once they close |

---

## Outcome

*(below this line, from the artefact only)*
