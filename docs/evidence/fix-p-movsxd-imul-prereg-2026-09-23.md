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
