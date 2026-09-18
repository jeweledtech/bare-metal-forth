# Pre-registration: second decoder fix, (c) REX.B on a memory base, with red (h) REX.X first (2026-09-18)

Written BEFORE any decoder line changes. Outcome below the line.

## Why (c) second

The `reg` class dominates every 64-bit input, but its three reds
split by mechanism site: (c) the ModRM rm/base and SIB base inside
`decode_modrm`; (d) the ModRM reg field, also inside `decode_modrm`
but a different output; (d') opcode-embedded registers in the
PUSH/POP/B8/XCHG paths, which the (d') red also ties to (e)'s size.
(c) is one function, one output field, decoder-only (the lifter copies
`base` as a number; no downstream table). Fixture row: `mem 1 → 0`.

## Red (h) first: REX.X on a SIB index (same-session rule)

`decode_modrm` extends the SIB index the same way it will extend the
base, so a fix for (c) written naturally would also apply REX.X, and a
defect fixed without a red is a defect nobody can count. Red written
now: fixture v5 (sha256
`9e790cdc8e7933645de622da6f8785c59c29b724cec0b0b37065b37c14c7d141`)
adds `4A 8B 04 00` before the imm64; oracle over every byte,
`docs/evidence/x64-reds-v5-oracle-2026-09-18.log`: `MOV RAX,qword ptr
[RAX + R8*0x1]` @40101a len 4. Test `x64_RED_rex_x_sib_index_r8`
asserts REX detected, len 4, MEM, base 0, **index 8**, scale 1.
Predicted first failure: `index: expected 8 (R8), REX.X not applied`
(index = 0 today: `decode_modrm` line 106 stores the raw 3-bit field).
XFAIL becomes nine names (eight after (b)'s removal, plus (h)); observed: `x64-reds-h-red-2026-09-18.log`, pass=49 xfail=9 fail=0 xpass=0 (tests=58), first failure `index: expected 8 (R8), REX.X not applied`, as predicted. The (c) fix is allowed to turn (h) green ONLY
through the XPASS gate, banked, then removal: one fix, two names,
both attributable, each with its own oracle line.

## The change (one function)

`decode_modrm`: when `dec->mode == X86_MODE_64` and a REX is present,
OR bit 3 into the rm/base register when REX.B (bit 0) is set, for both
the `rm != 4` base and the SIB base (`base != 5 || mod != 0` case), and
OR bit 3 into the SIB index when REX.X (bit 1) is set; the "no index"
test stays `index == 4` on the RAW field (RSP cannot be an index, R12
can). The `reg` output (REX.R) is NOT touched: that is (d). The
disp-only forms (`rm == 5 && mod == 0`, RIP-relative; SIB `base == 5
&& mod == 0`) are NOT touched: that is (a), except that SIB base 5 with
REX.B set means R13 and is still disp-only only when `mod == 0` (raw
field test; unchanged behaviour).

Note: `decode_modrm` has no access to `out->rex`; it receives the
decoder. The fix passes the REX byte in (a parameter, or a field on
`x86_decoder_t` set by `x86_decode_one` before the opcode switch).
Either way one file.

## Gate on the reds

Run 1: fix applied, names listed → `make test-x86` exits nonzero with
`XPASS` on BOTH `x64_RED_rex_b_base_r8` and `x64_RED_rex_x_sib_index_r8`
(pass=49 xfail=7 fail=0 xpass=2). Banked.
Run 2: both names removed → pass=51 xfail=7 fail=0 xpass=0 (tests=58).

## Fixture re-baseline (fixture v5 at the CURRENT decoder, before the fix)

The fixture changed (v4 → v5), so its "before" line is measured again
with the current (post-(b)) decoder before (c) is applied:
`operand-diff-fixture-v5-baseline-2026-09-18.log`. Predicted from the
v4 line plus one instruction: `ghidra=10 operand_ok=3 nostart=0 reg=4
mem=2 imm=0 addr=1` (the new instruction lands in `mem`: ours
`M:RAX,RAX,1,0x0` vs Ghidra `M:RAX,R8,1,0x0`).

## Fixture prediction after (c)

`mem 2 → 0` (both the base case and the index case), `operand_ok 3 →
5`; reg 4, addr 1 UNCHANGED. Two rows again, two instructions, both
named. Boundary line unchanged (no length changes).

## 14 inputs

- Controls IDENTICAL (no REX in 32-bit mode).
- No figure predicted for the eight drivers and four modules. The
  invariant from fix (b), applied: no instruction moves OUT of
  `operand_ok`; every class increase is fed only from `nostart`
  (which (c) does not change: no length changes, so `nostart` should
  be IDENTICAL on every input; any nostart movement means a length
  changed: stop). `mem` decreases; `reg`/`addr`/`imm` may not
  increase.
- 64-bit control: an input with zero memory operands whose base or
  index is R8..R15 would be one. Counted from the Ghidra dumps before
  the run: via-rng.ko 2, iTCO_wdt.ko 14, ne2k-pci.ko 70, 8139too.ko
  168, serial.sys 540, disk.sys 778, HDAudBus.sys 937, i8042prt.sys
  1205, pci.sys 3649, usbxhci.sys 4708, storport.sys 5200, ACPI.sys
  6379; the three PE32 controls 0. **No 64-bit control exists for (c)
  either.** Near-control: via-rng.ko (2 sites): its `mem` may fall by
  at most 2 and nothing else there may move.
- Fixture v5 baseline OBSERVED at the current decoder
  (`operand-diff-fixture-v5-baseline-2026-09-18.log`): `ghidra=10
  operand_ok=3 nostart=0 reg=4 mem=2 imm=0 addr=1`, exactly as
  predicted above; boundary 10/10, mid 0.

## Named alternatives

- Fixture `reg` moves: the fix leaked into the reg field (d); stop.
- Any `nostart` moves anywhere: a length changed; stop.
- Any control number moves; stop.
- A 64-bit `mem` count goes UP: REX.B applied where the raw field test
  should have kept a disp-only form (base 5 / mod 0); stop.

---
