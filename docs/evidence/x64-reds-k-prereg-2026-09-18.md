# Pre-registration: red (k), REX.B on a register-direct rm (2026-09-18)

Written BEFORE the test was run. Outcome below the line.

## Where it came from

Fix (c) extends the ModRM rm when it names a memory BASE. The same rm
field, with mod = 3, names a REGISTER, and REX.B extends it the same
way (Intel SDM Vol 2A §2.2.1.2). That is a different output field
(`rm_op->reg`, not `base`), so (c) left it untouched on purpose, and
the same-session rule says it gets its red now, before any fix touches
that path. It is part of the `reg` class the differential reports
(with (d) REX.R and (d') opcode-embedded).

## Oracle

Fixture v7 (sha256
`d6e864caca43d9a9e7449ce7aee64f2f94c5d70075bb3467990b6e8892d3ae02`)
adds `49 8B C0` after (i); every byte queried,
`x64-reds-v7-oracle-2026-09-18.log`: `MOV RAX,R8` @401022 len 3.

## Test

`x64_RED_rex_b_rm_register_r8`: REX detected (precondition), len 3,
MOV, dest RAX, **operands[1].reg == 8**. Predicted first failure:
`rm register: expected 8 (R8), REX.B not applied` (reg = 0 today:
`decode_modrm` mod-3 path stores the raw rm). XFAIL becomes eight
names (seven after (c)'s three came off, plus (k)).

## Fixture re-baseline (v7 at the current, post-(c) decoder)

Predicted from the v6 post-(c) line plus one instruction:
`ghidra=12 operand_ok=6 reg=5 mem=0 addr=1 nostart=0` (the new
instruction lands in `reg`: ours `R:RAX` vs Ghidra `R:R8` on operand 1).

---

## Outcome (appended after the run)

Fixture v7 baseline at the post-(c) decoder
(`operand-diff-fixture-v7-baseline-2026-09-18.log`): `ghidra=12
operand_ok=6 reg=5 mem=0 addr=1 nostart=0`, as predicted (the new
instruction reads `R:RAX` vs `R:R8`, class reg).
`make test-x86` (`x64-reds-k-red-2026-09-18.log`): first failure `rm
register: expected 8 (R8), REX.B not applied`, as predicted; pass=53
xfail=8 fail=0 xpass=0 (tests=61). Eight names on the list: (a), (d),
(d'), (e), (f), (g) imm32, (g) disp32, (k).
