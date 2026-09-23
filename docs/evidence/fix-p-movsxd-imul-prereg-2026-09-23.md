# (p): MOVSXD and three-operand IMUL decoded: pre-registration (2026-09-23)

**Written before the change. Taken on its own merits** (owner ruling): (p)
is a registered pair of reds for a real decoder defect,
`x64_RED_p_movsxd_decoded` and `x64_RED_p_imul_imm_decoded`. Today `63`
(64-bit), `69` and `6B` fall to the one-byte table's default arm, which
consumes the right length and names nothing. **Stage 2's row 14 is a
consequence of this item, not a reason for it**: one of that row's two
blockers is the `imul` at `1c0022cc1`, and that row cannot flip before the
SSE item anyway.

## The change

- **`63` in 64-bit mode → a new identity `MOVSXD`** (SDM: `MOVSXD r, r/m32`;
  Ghidra prints `MOVSXD`, so no alias is added). Operand 0 is `reg` (+REX.R)
  at operand size; operand 1 is r/m at **32 bits**. **`63` in 32-bit mode is
  ARPL, which stays on the default arm**, out of scope (no 32-bit input
  carries it in the differential).
- **`69` / `6B` → the existing `IMUL` identity, three operands:** `reg` at
  operand size, r/m at operand size, and an immediate (`69`: imm32, or imm16
  under `66`; `6B`: imm8), sign-extended exactly as the `81`/`83` cases store
  theirs.
- **Lifter, rule 24:** `MOVSXD` lifts to **`UIR_MOVSX`** (dest = sign-extend
  src), the existing opcode with exactly MOVSXD's semantics. It is not
  unmodelled, because nothing is invented. Three-operand `IMUL` reaches the
  existing `IMUL` case (dest = op0, src1 = op1); `uir_writes()` already
  answers "writes dest" when `src1` is set. The immediate is not carried,
  and nothing reads it.

## Bounds, with distinct counts beside them (standing caution)

- **Differential** (16 inputs against the banked, pinned oracle; each
  input is a distinct binary): **577 `undecoded` rows**, IMUL
  r,r/m,imm **315 in 11 inputs** and MOVSXD **262 in 12 inputs**. The
  largest are usbxhci IMUL 110, ACPI MOVSXD 109 and storport IMUL 107. There
  are no undecoded IMUL rows in any other form.
- **Park census** (walks stopping at `63`/`69`/`6B` today): **0 / 0 / 1 / 1**.
  Both are `RTKVHD64.sys` (ASUS older `0x496E12`, ASUS newer `0x3B7C2A`):
  **one driver on two builds**.

## Predictions

| # | prediction |
|---|---|
| P1 | the two (p) reds XPASS, and the new lifter red (below) XPASS; nothing else moves |
| P2 | differential: the 577 rows leave `undecoded`. **No prediction that all reach `ok`**: the immediate's representation and the MOVSXD source width are compared by the oracle for the first time. Every row that does not reach `ok` is reported with its class. **No row outside the 577 changes class** |
| P3 | park census: only the 2 `RTKVHD64` sites can change; HP byte-identical |
| P4 | `-t uir`: line counts identical; changed lines are `unknown` → `movsx` / `imul` at these rows |
| P5 | suites green; 14 reds after (p)'s two close and the lifter red closes |

**The lifter red, `(ay)`:** a MOVSXD or three-operand IMUL writing a
register *other than* the one holding the base must not stop the walk (a
store of RAX after it parks). The existing `(al)` case `movsxd %ecx,%rax`
(writing the base's register must not park) is the guard in the other
direction.

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `x86_decoder.c` `42e4574409a15768`, `uir.c`
`015a8a96f76407b8`, `bin/translator` `a314e173a7ea818b`, `dump_starts`
`197a807d4d340953`. The differential was taken against the same banked,
pinned oracle before (`dump_starts` of the pre-fix tree) and after. Census
scripts are **v3**, unchanged against `SHA256SUMS`.

| # | predicted | observed |
|---|---|---|
| P1 | the two (p) reds and `(ay)` XPASS; nothing else moves | **held**: the gate fired on exactly `x64_RED_p_movsxd_decoded`, `x64_RED_p_imul_imm_decoded` and `sem_RED_ay_movsxd_imul3_write_only_dest`, and on nothing else. `(ay)` was red before the fix (both cases stopped the walk) |
| P2 | the 577 leave `undecoded`; not all need reach `ok`; no row outside changes class | **held.** 577 of 577 left `undecoded`: **574 → `ok`** (IMUL 315, MOVSXD 259) and **3 → `addr`**. **0 rows outside the 577 changed class** |
| P3 | only the 2 `RTKVHD64` sites can change; HP byte-identical | **held**: exactly those 2 changed, both **couldn't-tell → `none` (path)**. HP identical; site sets 12 / 172 / 171 / 184 unchanged |
| P4 | `-t uir` line counts identical; changed lines `unknown` → `movsx`/`imul` | **held**: line counts identical on all 12 inputs; **552 changed lines**, all of that kind, and 0 others. 552 is the 577 less the 25 rows in the four `.ko` modules, which are not UIR inputs. Per input, the counts equal the differential's row for row |
| P5 | suites green; **14** reds | suites green (401 tests across 27 suites), **but 12 reds, not 14.** The prediction was arithmetic, and wrong: 14 before (p), plus `(ay)` makes 15, and three closed. The register check (union across suites) prints 12 |

**The 3 `addr` rows are a class that already existed, not a MOVSXD
defect.** All three are in `8139too.ko`, a relocatable module. There,
`movslq 0x0(%rip),%rcx` carries `R_X86_64_PC32 .data+0x87c` on a zero
displacement (objdump `-r` at `0x2a38`). Ghidra applies the relocation,
and we print the unrelocated target, which is the next instruction's
address (`0x2a38 + 7 = 0x2a3f`). The pre-fix baseline has 813 `addr` rows
in that module; 475 of them have this signature, including 33 MOV and 4
MOVZX. This is the relocation residual that fixes (b) and (c) already
recorded. The three MOVSXD rows join it because they are now decoded.

**Why the two `RTKVHD64` sites become `none`, read from the bytes** at
ASUS older `0x496E12`, with IAT slots resolved by name:

1. `MmMapIoSpace` maps `0x10000` bytes, and the base goes to RBP.
2. `je` skips on NULL. The walk falls through, which is the non-NULL path.
3. A loop runs `movslq %esi,%rcx` / `add %rbp,%rcx` / `RtlCompareMemory`
   over the mapping, looking for a 0x18-byte signature, and reads a word
   through `0x18(%rdi,%rbp,1)`.
4. `mov %rbp,%rcx` / `MmUnmapIoSpace` releases the mapping, and the
   function returns.

The base is used as an address and released in the same function; it is
**never stored**. So `none` is the right answer here, and unlike the
`mlx4_bus` sites it was reached on the right side of the NULL check. The
`movslq` it used to stop at is the loop index. ASUS newer `0x3B7C2A` has
the same shape (`MmMapIoSpace` / `RtlCompareMemory` / `MmUnmapIoSpace`,
resolved at its own IAT slots). These are one driver on two builds.

**Readers of the identity field (rule 24):**
- The lifter's `MOVSX` case now also takes `MOVSXD`.
- `dump_starts` prints the name.
- The DX-port backward scan (`uir.c`, `MOV`/`MOVZX`/`MOVSX` into EDX) was
  **left unchanged**. It never matched these rows while they were
  `UNKNOWN`, so adding `MOVSXD` there would be a new port-attribution
  behaviour, not this fix. It is named here so it is not lost.

**Consequence for stage 2 (not a reason for this item):** the `imul` at
`1c0022cc1`, one of row 14's two blockers, now decodes. Row 14 still waits
on the SSE item.
