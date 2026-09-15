# Pre-registration: reds (d), (d'), (e) from the operand-differential histogram (2026-09-15)

Written BEFORE the tests were run. Outcome appended below the line.

## Where they came from

The operand differential's first run (superseded log
`operand-diff-2026-09-15-run1-superseded.log`) put `reg` as the
dominant mismatch class on every 64-bit input. A histogram of the reg
mismatches on i8042prt.sys (from the verbose comparer output):

| shape | count |
|---|---:|
| r8-r15 expected, low register decoded (REX.R on reg field / REX.B on register rm or opcode-embedded reg) | 3571 |
| E-register decoded, R-register expected (PUSH/POP default 64-bit operand size in long mode) | 296 |
| DH/BH/CH decoded, SIL/DIL/BPL expected (byte-register naming under any REX) | 132 |

The first two are named defects with no test. The XFAIL list is the
arc's to-do list and must be complete (owner ruling), so each gets a
red. The third is deferred: it is the same REX-application defect
surfacing in byte-register naming, and it will resolve or re-surface
when (d) is fixed; it is named here so it is not forgotten.

## Oracle (ground truth)

Fixture v3 `tests/data/x64_reds/x64_reds.elf` sha256
`b498dbee10fda14a2c22db8a7e4101e23f0a6783c52398335635a4ed8e57d31f`,
raw `.byte` directives at 0x401000, every byte 0x401000..0x401021
queried: `docs/evidence/x64-reds-v3-oracle-2026-09-15.log`. Layout
(imm64 last, so it desyncs nothing that is measured):

| @ | bytes | Ghidra START | len |
|---|---|---|---|
| 401000 | `49 8B 00` | `MOV RAX,qword ptr [R8]` | 3 |
| 401003 | `48 8D 05 10 00 00 00` | `LEA RAX,[0x40101a]` | 7 |
| 40100a | `4C 8B C0` | `MOV R8,RAX` | 3 |
| 40100d | `41 54` | `PUSH R12` | 2 |
| 40100f | `55` | `PUSH RBP` | 1 |
| 401010 | `48 C7 C0 FF FF FF FF` | `MOV RAX,-0x1` | 7 |
| 401017 | `48 B8 88 77 66 55 44 33 22 11` | `MOV RAX,0x1122334455667788` | 10 |
| 401021 | `C3` | `RET` | 1 |

The (a)/(b)/(c) tests keep their own addresses from the v1 oracle log
(`x64-reds-oracle-2026-09-15.log`); they are byte-level and unaffected
by the fixture reorder.

## Tests (added to test_x86_decoder.c and to xfail_names)

| test | asserts (after REX precondition where a REX is present) | predicted first failing assertion | why (x86_decoder.c) |
|---|---|---|---|
| `x64_RED_rex_r_reg_field_r8` | len 3, MOV, operands[0] REG reg==8, operands[1] REG reg==0 | "reg field: expected 8 (R8)" (reg = 0) | 0x8B path line 471-473 takes `reg` from ModRM bits only; REX.R never read |
| `x64_RED_rex_b_push_r12` | len 2, PUSH, operands[0] reg==12 (then size 8) | "opcode-embedded reg: expected 12 (R12)" (reg = 4) | 0x50-0x57 path line 217 `opcode - 0x50`; REX.B never read (the existing REX_B_PUSH_R8 test asserts detection only) |
| `x64_RED_push_default_size_64` | len 1, PUSH, operands[0] reg==5, size==8 | "operand size: expected 8 (64-bit default in long mode)" (size = 4) | line 218 `size = 4` unconditionally |

The sign-extension probe `48 C7 C0 FF FF FF FF` is NOT a red: reading
every REX.W-eligible imm32 path shows sign-extending reads, and the
operand differential shows the instruction operand-correct against
Ghidra after the width fix. No test is added for it (a green test
written after the fact proves nothing; owner may rule on a guard).

## Prediction

All three RED on the named assertion. Any GREEN: stop, the register is
wrong at that point.

---

## Outcome (appended after the run)

`make test-x86` → pass=48 xfail=6 fail=0 xpass=0 (tests=54), exit 0.
Log with input hashes: `docs/evidence/x64-reds-def-red-2026-09-15.log`.

| test | observed first failure | matches prediction |
|---|---|---|
| `x64_RED_rex_r_reg_field_r8` | `reg field: expected 8 (R8)` | yes |
| `x64_RED_rex_b_push_r12` | `opcode-embedded reg: expected 12 (R12)` | yes |
| `x64_RED_push_default_size_64` | `operand size: expected 8 (64-bit default in long mode)` | yes |

No green; no XPASS; the XFAIL list now has six names, each a defect the
operand differential is pre-registered to move on.
