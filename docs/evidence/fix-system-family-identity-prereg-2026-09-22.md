# The decoder names the system-instruction family: pre-registration (2026-09-22)

**Written before the change. This reopens the decoder queue**, which closed
on 2026-09-21 at its exit number. The reason is the product's subject:
every instruction that *is* direct register access (control, debug and
model-specific registers, descriptor tables, VMX) decodes with **no
identity**. That is 100% of two-byte system forms on every machine
(`system-family-census-2026-09-22.md`). An instruction the decoder cannot
name cannot be lifted, and one that cannot be lifted cannot be emitted as a
Forth word.

**Scope, owner ruling: decoder identity only.** Operands are the next item,
with their own reds.

## The family: reused, not rebuilt

This is the list fixed from the SDM in `system-family-census-2026-09-22.md`,
**reused unchanged**:

- **Group 6** (`0F 00` /0–/5): SLDT, STR, LLDT, LTR, VERR, VERW.
- **Group 7** (`0F 01`), memory forms: SGDT, SIDT, LGDT, LIDT, SMSW (/4),
  LMSW (/6), INVLPG (/7). Register forms at fixed ModRM: VMCALL C1, VMLAUNCH
  C2, VMRESUME C3, VMXOFF C4, MONITOR C8, MWAIT C9, CLAC CA, STAC CB,
  XGETBV D0, XSETBV D1, VMFUNC D4, RDPKRU EE, WRPKRU EF, SWAPGS F8,
  RDTSCP F9; SMSW and LMSW in register form (/4, /6).
- `0F 05` SYSCALL, `06` CLTS, `07` SYSRET, `08` INVD, `09` WBINVD.
- **`0F 20`–`23` MOV to/from CR/DR**: two identities, `MOV_CR` and `MOV_DR`,
  printed with the SDM mnemonic `mov`.
- `0F 30` WRMSR, `31` RDTSC, `32` RDMSR, `33` RDPMC, `34` SYSENTER, `35`
  SYSEXIT, `37` GETSEC, `A2` CPUID, `AA` RSM.
- `0F 78` / `79` unprefixed: VMREAD / VMWRITE.
- **`0F C7`:** /6 memory VMPTRLD (bare), VMCLEAR (`66`), VMXON (`F3`);
  /7 memory VMPTRST; /6 register RDRAND; /7 register RDSEED (bare), RDPID
  (`F3`).

Encodings the family leaves out stay `UNKNOWN`: group 6 /6–/7, group 7
/5 memory, other `0F 01` register bytes, and other `0F C7` forms. **No
length changes**: every length is already asserted by `(s)`/`(u)`.

## Readers of the identity field (rule 24), enumerated from source

- **`uir.c`, the lifter.** Its `default:` lifts unlisted identities to
  `UIR_UNKNOWN` ("the decoder could not name"), which would become false for
  these the moment they are named. **So they are added to the lifter's
  `UIR_UNMODELLED` case (named, not translated) with no `dest`.** That keeps
  the UIR truthful. It is not operand work: no operand is carried.
- **`dump_starts.c` → `compare_operands.py`**, the differential. `???` rows
  are classed `undecoded`; named rows are compared by mnemonic (no alias
  is added, and the table hash is unchanged) and then by operand.
- **`semantic.c`** reads only CALL/PUSH/MOV, and **`translator.c`** copies
  the field. Neither can move.
- **Tests:** the sweep of `test_x86_decoder.c` for the family's opcodes
  finds only length assertions (`(s)` RSM, `(s6)` MOV CR mod=10). No test
  asserts `UNKNOWN` on a family form. `rule30_sweep.py` baseline banked.

## Bound, measured before the change

- **Differential** (16 inputs against the banked, pinned oracle in
  `measure/differential/`, re-run with the current `dump_starts`
  `516fc583`): **224 `undecoded` rows are family instructions**: 220 MOV
  CR/DR and 4 CPUID. They sit on the 8 HP drivers (ACPI 19, HDAudBus 10,
  disk 17, i8042prt 2, pci 21, serial 1, storport 69, usbxhci 82) plus 3 in
  the fixture; the modules and controls have 0.
- **Corpus, linear** (`system-family-census`): two-byte forms 195 / 5,375 /
  5,968 / 7,030 (HP / Dell / ASUS older / ASUS newer), 356 in the macOS kexts
  and 810 in the macOS kernel, all `UNKNOWN`.

## Predictions

| # | prediction |
|---|---|
| F1 | one XPASS: the red naming the family's encodings; no other test moves |
| F2 | differential: the 224 rows **leave `undecoded`**. The 4 CPUID become `ok`. **The 220 MOV CR/DR become operand mismatches, not `ok`**, because the decoder types the control register as a general register and ignores REX.R (so `CR8` reads as register 0), and gives `0F 22` the `0F 20` operand order (read from `x86_decoder.c:1382–1392`). That is defect-revealing and is the measure for the operand item. No row outside the 224 changes class |
| F3 | corpus re-count with the same census scripts: every listed form goes from 100% `UNKNOWN` to **0%**; forms outside the list stay `UNKNOWN` |
| F4 | `-t uir`: line counts identical; the only changed lines are `unknown` → `unmodelled` at family rows |
| F5 | park census: **outcomes byte-identical on all four machines** (an unmodelled instruction with no `dest` is exactly as unseen as an unknown one) |
| F6 | suites green; test total rises by the red; 14 reds after it closes |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `x86_decoder.c` `c6cb4cbae0d601d7` (before: `838d1581c9b4b109`),
`uir.c` `7f6b8fa6f6d0c471`, `dump_starts` `f0044f3d1ce312a0` (before:
`516fc583b77aebec`), `bin/translator` `9a70409c87694568`. The differential
was taken against the banked, pinned oracle in `measure/differential/`
before and after, so the change is isolated to the decoder.

| # | predicted | observed |
|---|---|---|
| F1 | one XPASS; no other test moves | **exactly one**, `x64_RED_au_system_family_named`; the decoder suite went from pass 101 / xfail 15 to pass 102 / xfail 14 |
| F2 | the 224 rows leave `undecoded`; 4 CPUID → `ok`; 220 MOV CR/DR → operand mismatch; nothing else changes class | **exactly that.** 224 rows changed class and no others: **220 `undecoded` → `reg`** (Ghidra `MOV RAX, CR8` against ours `MOV RAX, RAX`: the control register read as general register 0) and **4 → `ok`** (CPUID). The per-input split equals the bound row for row |
| F3 | every listed form goes to 0% UNKNOWN; forms outside the list stay UNKNOWN | **held.** Two-byte family rows (linear, same offsets in both runs): HP 195 → 0 UNKNOWN; Dell 5,392 → 17; ASUS older 5,985 → 17; ASUS newer 7,072 → 39; macOS kexts+kernel 1,170 → 0. **Every residual is an encoding outside the list**: `0F 01 D9`/`CC`/`CF`/`DC`/`FE`/`FF`, group 6 /6–/7 |
| F4 | `-t uir`: only `unknown` → `unmodelled` at family rows | **held**: line counts identical on all 12 inputs; 226 changed lines, 0 any other way |
| F5 | park outcomes byte-identical on all four machines | **held**: 0 outcome changes; site sets 12 / 172 / 171 / 184 unchanged |
| F6 | suites green; 14 reds | **held**: 396 tests across 27 suites, 14 reds, the union matching |

**rule-30 sweep:** its output is identical to the pre-change baseline apart
from the new test entering the denominator, where it is listed *not swept*.
The sweep reads one literal byte array per test, and `(au)` is
table-driven. **So the sweep cannot vouch for `(au)`'s 57 rows.** They were
checked against objdump (length 57 of 57; mnemonic 57 of 57, allowing for
AT&T's `sysretl`/`sysexitl` suffixes) before the red was written.

**For the next item (operands),** which is the measure of whether it is
worth taking: **220 differential rows** now read as `reg` mismatches, because
the CR/DR operand is carried as a general register without REX.R, and `0F 22`
takes `0F 20`'s operand order. The corpus's 12 `mov %cr8` park stops are
unchanged by this item, as predicted: an unmodelled instruction with no
`dest` is exactly as unseen as an unknown one.
