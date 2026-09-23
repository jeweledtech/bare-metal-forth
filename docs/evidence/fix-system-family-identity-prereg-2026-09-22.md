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
