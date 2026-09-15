# Pre-registration: three 64-bit decoder reds (2026-09-15)

Written BEFORE the tests were run. Outcome section is appended below
the line after the run; nothing above the line is edited afterwards.

## Oracle (ground truth, not desk-derived)

Fixture: `tools/translator/tests/data/x64_reds/x64_reds.elf`
sha256 `04af6123fef32d03ee99b4c43ef03bd6523e3018ef380d34a08cd7c2266bed3e`
(raw `.byte` directives, linked at 0x401000; the assembler contributed
no encoding opinion). Oracle run: `make ghidra-instr-at` over every
byte 0x401000..0x401014, log `docs/evidence/x64-reds-oracle-2026-09-15.log`.
Ghidra 12.1.2 (snap rev 47, pinned in tools/translator/Makefile).

| seq | bytes | Ghidra START line |
|---|---|---|
| a | `48 8D 05 10 00 00 00` @401000 | `LEA RAX,[0x401017]` len=7 |
| b | `48 B8 88 77 66 55 44 33 22 11` @401007 | `MOV RAX,0x1122334455667788` len=10 |
| c | `49 8B 00` @401011 | `MOV RAX,qword ptr [R8]` len=3 |

Every byte between two STARTs reported MID of the preceding START, so the
lengths are Ghidra's, not counted by hand.

The ELF64 is oracle-only: it exists so Ghidra has something to import.
The tests feed the bytes straight to the decoder. ELF is not under test;
the defects were found in PE32+ and the decoder is format-agnostic.

## Tests (tools/translator/tests/test_x86_decoder.c, `make test-x86`)

Suite before: 48/48. Suite after adding three: 51 tests run.

Each test asserts its preconditions first (REX detected via `d.rex != 0`;
test a also `d.address == 0x401000`), so a red fires for the applied
defect and not for a broken setup. The predicted failures below are all
applied-result assertions, past the preconditions.

| test | asserts | predicted first failing assertion | why (decoder read, src/decoders/x86_decoder.c) |
|---|---|---|---|
| `x64_RED_lea_rip_relative` | len 7, LEA, MEM, base is a RIP marker (not -1, not a GPR 0..15), addr+len+disp == 0x401017 | "base is -1: disp32 taken as absolute, RIP not applied" | `decode_modrm` line 115: `rm==5 && mod==0` → disp32, `base` stays -1; no mode check |
| `x64_RED_mov_rax_imm64_len10` | len 10 first, then MOV, reg RAX size 8, imm == 0x1122334455667788 | "length: expected 10" (decoder returns 6) | line 581-584: op_size 8 falls to `read_u32`; 4 bytes under-read |
| `x64_RED_rex_b_base_r8` | len 3, MOV, MEM, base == 8 (R8), dest reg RAX | "base: expected 8 (R8), decoded as its low-8 counterpart" (base = 0) | `decode_modrm` never reads `out->rex`; `base = rm` = 0 |

Pass state for test a's `base`: the fix introduces `X86_REG_RIP = 16`
in include/x86_decoder.h (outside the GPR range 0..15, which the fix
will also widen to r8-r15) and `decode_modrm` sets `base = X86_REG_RIP`
for mod=00 rm=101 in 64-bit mode. Today no value of `base` passes; the
test is red by defect, and the named constant is what makes it passable.

## Prediction

All three RED. Named alternative: any one GREEN means the 2026-09-15
finding "there is no x86-64 front end" is wrong at that point, and the
register is corrected before anything else (owner's stop condition).

No decoder fix follows; the reds stay red.

---

## Outcome (appended after the run)

`make test-x86` → 48/51. Log with input hashes:
`docs/evidence/x64-reds-red-2026-09-15.log`.

| test | observed first failure | matches prediction |
|---|---|---|
| `x64_RED_lea_rip_relative` | `base is -1: disp32 taken as absolute, RIP not applied` | yes |
| `x64_RED_mov_rax_imm64_len10` | `length: expected 10` | yes |
| `x64_RED_rex_b_base_r8` | `base: expected 8 (R8), decoded as its low-8 counterpart` | yes |

All three preconditions (REX detected, address populated) held: every
red fired past its setup checks, on the applied-result assertion. No
green; the stop condition did not fire; the 2026-09-15 finding stands
at these three points. No decoder change made.

~~Side effect, flagged not fixed: `make test` in tools/translator chains
`test-x86` first and halts on its nonzero exit, so the later suites in
that chain do not run while the reds are red. Owner's call whether the
chain should continue past a known-red suite.~~
Resolved 2026-09-15 (owner ruling: XFAIL, not continue-past-failures).
The three names are listed in `xfail_names` in test_x86_decoder.c; the
suite reports pass / xfail / fail / xpass as separate numbers and never
one total; an XFAIL that passes is XPASS and a hard failure (exit 1),
and a listed name that produces no XFAIL (test deleted or renamed) is
a hard failure naming the entry, so neither a green red nor a vanished
red can leave the suite green; the stop condition is enforced by the
harness. The list is the arc's
to-do list: one name comes off per fix, visibly. Gate red-tested first
(a passing test listed as XFAIL exits 1), then `make test-x86` →
pass=48 xfail=3 fail=0 xpass=0, then the full chain runs to completion.
Log: `docs/evidence/x64-reds-xfail-2026-09-15.log`.
