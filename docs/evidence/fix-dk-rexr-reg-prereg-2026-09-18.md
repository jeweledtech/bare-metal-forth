# Pre-registration: third decoder fix, (d) REX.R on the ModRM reg field + (k) REX.B on the register-direct rm (2026-09-18)

Written BEFORE any decoder line changes. Outcome below the line.

## Why (d)+(k) third, together

Both live in `decode_modrm`, each on its own output line: (d) the
`*reg_out` value (REX.R, bit 2); (k) `rm_op->reg` when mod = 3 (REX.B,
bit 0). Neither has an escape case (Intel SDM Vol 2A §2.2.1.2: REX.R
and REX.B simply add bit 3 to the 3-bit field; the only REX special
cases are the SIB ones handled by (c) and the byte-register file (f)).
No length changes. One commit, two names, each with its own oracle
line and its own fixture row.

Out of scope, explicitly: opcode-embedded registers (d') live in the
PUSH/POP/B8/XCHG paths, not in `decode_modrm`, and (d') also asserts
the 64-bit PUSH size, so (e) precedes it. The byte-register file (f)
is a naming decision ((16..19) numbering) with its own red. (a) is
untouched. The reg field's byte-register naming under REX (DIL vs BH
in the fix-(c) example) stays (f)'s.

## The change (two lines in one function)

`decode_modrm`: `if (reg_out) *reg_out = reg | ((dec->rex & 4) ? 8 : 0);`
and, in the `mod == 3` branch, `rm_op->reg = rm | rex_b;` using the
`rex_b` already computed by (c). `dec->rex` is 0 in 32-bit mode and
cleared per instruction (guarded).

## Gate

Run 1: fix in, names listed → XPASS on `x64_RED_rex_r_reg_field_r8`
AND `x64_RED_rex_b_rm_register_r8`; pass=53 xfail=6 fail=0 xpass=2
(tests=61); the leak guard stays PASS. Banked.
Run 2: both names removed → pass=55 xfail=6 fail=0 xpass=0. Six
remain: (a), (d'), (e), (f), (g)×2.

## Fixture prediction (v7 baseline at the post-(c) decoder: `ghidra=12 operand_ok=6 reg=5 mem=0 addr=1 nostart=0`)

After (d)+(k): **reg 5 → 3, operand_ok 6 → 8**; addr 1, nostart 0
UNCHANGED; boundary 12/12 unchanged. The two instructions: `MOV R8,RAX`
(@40100a, (d)) and `MOV RAX,R8` (@401022, (k)). The three remaining
`reg` rows are `PUSH R12` (d'), `PUSH RBP` (e), `MOV AL,SIL` (f).

## 14 inputs

- Controls IDENTICAL (no REX in 32-bit mode).
- No figure predicted for the eight drivers and four modules.
- Invariant rev 2: no instruction leaves `operand_ok`; every class
  increase is fed only from `nostart` or from the class this fix
  addresses (`reg`). `nostart` IDENTICAL everywhere (no length change).
- 64-bit control: an input with zero r8-r15 REGISTER operands would be
  one. Counted from the Ghidra dumps: via-rng.ko 25, iTCO_wdt.ko 72,
  ne2k-pci.ko 245, 8139too.ko 930, disk.sys 2461, serial.sys 2932,
  i8042prt.sys 4182, HDAudBus.sys 5426, pci.sys 17385, usbxhci.sys
  17614, storport.sys 19003, ACPI.sys 31044; PE32 controls 0. **No
  64-bit control exists.** Those counts include (d') opcode-embedded
  sites (Ghidra's text cannot separate encodings), so `reg` will NOT
  fall to 0: the residue after this fix is (d') + (e) + (f) sites. The
  near-control is via-rng.ko (25 sites): its `reg` may fall by at most
  25 and nothing else there may move.
- Matrix on ACPI.sys after the run, from a pre-fix scratch decoder
  (the private head at that moment), and it must close.

## Named alternatives

- Fixture `addr` or `nostart` moves: leak into another path; stop.
- Any control number moves; stop.
- Fixture `reg` falls below 3 or above 3: a fix touched (d')/(e)/(f)
  or missed one of its two instructions; stop.
- An instruction leaves `operand_ok` anywhere: REX.R applied where the
  field was not a register (e.g. a group opcode using reg as an
  extension index: the group tables index by the RAW reg, and the fix
  must keep passing the raw value to those lookups; predicted first
  place this would show is `undecoded`/`mnemonic` rising). This is the
  load-bearing alternative: `decode_modrm`'s `reg_out` is used both as
  a register number AND as the /digit group selector (0x80-0x83, 0xC0/
  0xC1, 0xF6/0xF7, 0xFE/0xFF, 0x0F 0xBA...). REX.R must NOT be applied
  to the group selector. The fix therefore extends the value at the
  REGISTER-operand sites, not inside `decode_modrm`'s `*reg_out`, OR
  `decode_modrm` returns both the raw and the extended value. Decided
  before the line changes: **the group lookups keep the raw field**;
  the differential's `undecoded`/`mnemonic`/`opcount` classes must be
  IDENTICAL after the fix, and that is the check.

---
