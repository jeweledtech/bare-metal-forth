# A differential class for assembler pseudo-op spelling: pre-registration (2026-09-23)

**Written before the change.** Owner ruling: our spelling is correct and
the disagreement is not a defect. The SDM defines `CMPPS` as the
instruction with an imm8 predicate, and `CMPEQPS` as an *assembler
pseudo-op*. We print the instruction and keep the predicate as data, which
is also the product's shape: one Forth word plus a literal, not eight
words. So the row is neither renamed nor aliased. It is **classified**, the
same move as the relocation residual: a class with its count printed,
excluded from the denominator, and stated. Outcomes go BELOW the line.

## The class, closed and enumerated before it is used

**Membership is a (key, imm8) pair, not a mnemonic pattern.** A row is in
the class only when our mnemonic is the base instruction, our imm8 operand
selects an alias the SDM defines, and the oracle's mnemonic is **exactly**
that alias:

| base (key) | imm8 | the SDM's pseudo-op |
|---|---|---|
| `CMPPS` (`0F C2`), `CMPPD` (`66 0F C2`), `CMPSS` (`F3 0F C2`), `CMPSD` (`F2 0F C2`) | 0–7 | `CMP` + `EQ`, `LT`, `LE`, `UNORD`, `NEQ`, `NLT`, `NLE`, `ORD` + `PS`/`PD`/`SS`/`SD` |
| `PCLMULQDQ` (`66 0F 3A 44`) | `00`, `01`, `10`, `11` | `PCLMULLQLQDQ`, `PCLMULHQLQDQ`, `PCLMULLQHQDQ`, `PCLMULHQHQDQ` |

That is **36 (key, imm8) pairs**. The compare predicates 8–31 exist only
under VEX, which is outside the family ((q)), so they are not in the set.

**This is the third thing fixed from the SDM's structure with no copy on
disk**, after the system family and the SSE family. The banking debt on
the register now has three dependents. Still not blocking.

**Three guards, so the class cannot become a dumping ground:**
1. **The other operands must still agree.** Operands are compared apart
   from our imm8, which the pseudo-op folds into its name. A wrong register
   on an aliased row stays `mnemonic`.
2. **A base-instruction row whose oracle mnemonic differs, but is not the
   enumerated alias for its imm8**, is a real defect surfacing. It stays
   `mnemonic`, and it is counted as `pseudo_op_unlisted=` and printed per
   row.
3. The pseudo-op table is hashed and printed with every result, as the
   alias table is. It is a separate table, so the alias hash does not move.

## Reach (measured on the post-(ba) corpus sweep)

Every alias-bearing row in the corpus uses an aliased imm8. There are **0**
compare rows with imm8 ≥ 8 and **0** PCLMULQDQ rows outside
`00`/`01`/`10`/`11`.

| set | CMPPS/PD/SS/SD rows (distinct binaries) | PCLMULQDQ rows (distinct binaries) |
|---|---|---|
| HP | 0 | 0 |
| Dell | 0 | 175 (2) |
| ASUS (older) | 0 | 60 (2) |
| ASUS (newer) | 0 | 174 (2) |
| Mac userland | **380** (cmppd 163 in 10, cmpsd 150 in 22, cmpss 52 in 11, cmpps 15 in 3) | 0 |
| macOS dexts | 0 | 0 |
| macOS kernel collection | **383** (cmpsd 134 in 23, cmpss 125 in 9, cmpps 94 in 4, cmppd 30 in 4) | 188 (2) |

**The compare predicates are entirely macOS (763 rows, 0 in any Windows
set).** That is the second measurable difference between how clang and
MSVC use the same ISA. **The PCLMULQDQ aliases are not:** Windows carries
409 rows, in two binaries per machine.

**Correction:** I reported the reach as "763 rows, all macOS" for the class
as a whole. That holds for the `0F C2` compares only. The class as
enumerated reaches 1,360 corpus rows, and 409 of them are on Windows.

**On the oracle's 16 inputs** there is exactly **one** such row: the
fixture's `0F C2 C0 00` (Ghidra `CMPEQPS`, ours `CMPPS … I:0x0`). No oracle
input carries PCLMULQDQ, so **Ghidra's spelling of the PCLMULQDQ aliases is
unobserved**. If it differs from the SDM's, guard 2 reports it rather than
absorbing it.

## Predictions

| # | prediction |
|---|---|
| C1 | exactly **1** row moves, `mnemonic` → `pseudo_op`, on the fixture; `pseudo_op_excluded=1` there and 0 on the other 15 inputs |
| C2 | `pseudo_op_unlisted=0` on all 16 inputs |
| C3 | every other count identical on all 16; alias hash `02101788edd2` unchanged; only the new fields appear |
| C4 | controls, run through the comparer on constructed dump pairs: (a) ours `CMPPS … I:0x1` vs oracle `CMPLTPS` → `pseudo_op`; (b) ours `CMPPS … I:0x0` vs oracle `CMPLTPS` → `mnemonic`, `unlisted=1`; (c) ours `CMPPS XMM1 … I:0x0` vs oracle `CMPEQPS XMM0 …` → `mnemonic`, not absorbed; (d) ours `PCLMULQDQ … I:0x11` vs oracle `PCLMULHQHQDQ` → `pseudo_op` |
| C5 | `make test` unchanged: 403 tests, 12 reds |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `compare_operands.py` `5ec8fc7bf8493de6`; pseudo-op
table `pseudo_sha256` `6ceb47ffeefb` (36 pairs), printed on every `OPD`
header line. The "before" is the committed comparer on the same post-(ba)
dumps, so only the comparer differs.

| # | predicted | observed |
|---|---|---|
| C1 | exactly 1 row `mnemonic` → `pseudo_op`, on the fixture | **held**: `x64_reds.elf` `mnemonic` 1 → 0, `pseudo_op_excluded=1`, and the `EXCLUDED … pseudo_op rows=1` line prints; 0 on the other 15 inputs |
| C2 | `pseudo_op_unlisted=0` on all 16 | **held** |
| C3 | every other count identical; alias hash unchanged | **held after one correction made before commit.** The first build moved `mnem_ok` 22 → 23 on the fixture: the pseudo-op check ran before the `mnem_ok` count, so an excluded row whose two spellings differ was counted as a mnemonic agreement. That is a figure the prediction said would not move. `pseudo_op` is now kept out of `mnem_ok`, and the re-run moves only `mnemonic` 1 → 0, `denominator` 31 → 30 and the scores that follow from it (64.5% → 66.7% on the 31-row fixture). The alias hash is `02101788edd2` before and after |
| C4 | the four controls | **held, row for row**: (a) `pseudo_op`; (b) `mnemonic` plus a `PSEUDO-OP UNLISTED` line; (c) `mnemonic`, a register disagreement not absorbed; (d) `pseudo_op`. `OPSUMMARY` reads `mnemonic=2 pseudo_op_excluded=2 pseudo_op_unlisted=1`. The control inputs are banked with the translator, in `measure/pseudo-op-controls/`, with the expected rows in a README, so the check can be re-run rather than recalled |
| C5 | `make test` unchanged | **held**: 403 tests across 27 suites, 12 reds |

**The corpus-wide figure is unchanged by construction.** The class only
re-labels a row the comparer already called `mnemonic`, and the oracle has
exactly one. What it buys is the next time: 1,360 corpus rows (763 compares
on macOS, 597 PCLMULQDQ, 409 of them on Windows) would each have read as a
defect the day an oracle input carries them. Now each will read as
`pseudo_op` if it matches the SDM table, and as `UNLISTED` if it does not.
