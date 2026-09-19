# Pre-registration: (n) unknown one-byte opcode length recovery, and (o) moffs in 64-bit mode

Date: 2026-09-18. Written BEFORE the (m) fix, per the owner's ruling at
the fix-(e) review ("pre-register (n) before you write the (m) fix, or
the fix will eat its own evidence"). Decoder state: private HEAD
`558240a` (post fix (e)). Reds are red at this decoder; nothing in
`src/` changes in this document.

## What (m) turned out to be, and what it is not

Red `x64_RED_pop_rm_decoded` (`8F 00`) fails first on `length:
expected 2`, not on recognition. Mechanism, read from source
(`x86_decode_one`, one-byte `default:` arm): `out->instruction =
X86_INS_UNKNOWN; break;`, then `out->length = dec->offset - start`.
Nothing after the opcode is consumed, so every unknown one-byte opcode
reports `length = prefixes + 1` whatever its ModRM, SIB, displacement
or immediate bytes. The two-byte `0F xx` `default:` arm is different:
it consumes a ModRM unless the opcode is on a no-ModRM list. The
one-byte arm has no such fallback. The walk resumes inside the
instruction and stays desynchronised until it re-syncs by chance.

(m) stays "POP r/m (`8F /0`) is not decoded" (a recognition gap; its
red asserts POP, `[RAX]`, size 8). (n) is the length engine and is
independent of `8F`: fixing (m) cannot close a single (n) red below.

## Survey (instrument: objdump as a screen, Ghidra as the oracle)

`x64-unknown-opcode-survey-2026-09-18.log`: each first byte `00-FF`
followed by nine zero bytes, decoded in 64-bit mode, versus objdump's
first-instruction length. 64 one-byte opcodes decode as UNKNOWN; 19 of
them with the wrong length. Real set (17): `63 69 6B 8C 8E 8F C8 CA D8
D9 DA DB DC DD DE DF E3`. Excluded as artefacts of the objdump version
on zero-padded bytes: `C5` (VEX), `D5` (APX rex2). Unknown with the
correct length 1 (recognition gaps, not (n)): `9C 9D` PUSHF/POPF, `9B`,
`9E 9F`, `91-97` XCHG, `A6 A7 AC-AF` string ops, `CC CF D7 F1 F5 F8 F9`,
and the invalid-in-64-bit set (`06 07 0E 16 17 1E 1F 27 2F 37 3F 62
82 9A CE D4 D6 EA`, `C4`).

Found by the same survey, outside (n): `A0-A3` are decoded (MOV
moffs) with a 4-byte address; in 64-bit mode the moffs is 8 bytes
(Ghidra: `MOV EAX,[0x1122334455667788] len=9`). That is (o).

## Rule 22: the corpus number this repair moves

`nostart-run-attribution-2026-09-18.log` (per-instruction files of the
last differential run, decoder post (d)+(k)): a *run* is a maximal
sequence of Ghidra starts our walk misses; its trigger is the Ghidra
instruction immediately before it. Over all 15 inputs: **1109 nostart
rows in 433 runs; triggers IMUL 166, MOVSXD 121, x87 (`F*`) 66, MOV
63, TEST 9, section-start 4, INT 2, PEXTRW 1.** (n)-attributable
(IMUL + MOVSXD + x87): **353 of 433 runs.** Attribution is by
mnemonic (the files carry no bytes): IMUL runs are inferred to be
`69`/`6B` (the two-operand `0F AF` form is decoded); MOVSXD is `63`;
x87 is `D8-DF` (all on the 32-bit nmap control: 67 runs, 145 rows).
The 63 MOV runs are NOT attributed here (`8C`/`8E`, `A0-A3`, or
something else); they are the residual to read from bytes after (n).

The nine TEST runs and four section-start runs are not (n) and are
not predicted to move.

**Correction, same day, from reading the log back against the
summary log.** The attribution's per-input `nostart` totals equal the
`OPSUMMARY` totals of `operand-diff-fix-dk-2026-09-18.log` for every
PE input (ACPI 190, storport 192, usbxhci 177, nmap 145, ...) but NOT
for the four kernel modules (8139too 62 vs 11, ne2k-pci 64 vs 13,
iTCO_wdt 57 vs 8, via-rng 70 vs 0). Cause: the module Ghidra files
carry code sections our dump does not emit (the four `<section
start>` triggers are exactly those); the script counted every start in
such a section as a nostart row, the harness compares only sections
present on both sides. Effect: the **row** total 1109 is inflated by
those whole sections (the harness total is 888); the **run** counts
and the trigger tally are unaffected except for the four section-start
runs, which are not (n). The rule-22 number stands as runs: 353 of 433
(349 of 429 with the four section-start runs excluded).

## Reds (fixture v10, sha256 `cfe593571ed3014cb152165ab3f5ff62bddeb73e0a31ecaf9efa7962512ba3a9`; oracle `x64-reds-v10-oracle-2026-09-18.log`)

Rows appended AFTER `(m) 8F 00` so every v9 address is unchanged; a
first draft carried a `CA 10 00` RETF row, which ends the flow (Ghidra
left the three rows after it NONE), so it was removed: imm16 is
covered by ENTER. Each red decodes its own bytes at its own fixture
address and asserts the length the oracle printed. **Length only**:
(n) is measured on its own terms; whether the opcode is recognised is
a separate question (see (p) below) and a length-only fix must be
able to close these without recognising anything.

| name | bytes | addr | Ghidra | asserts |
|---|---|---|---|---|
| `x64_RED_n_movsxd_length` (n1) | `63 C0` | 40102d | `MOVSXD EAX,EAX` len=2 | length 2 |
| `x64_RED_n_imul_imm32_length` (n2) | `69 C0 10 00 00 00` | 40102f | `IMUL EAX,EAX,0x10` len=6 | length 6 |
| `x64_RED_n_imul_imm8_length` (n3) | `6B C0 10` | 401035 | `IMUL EAX,EAX,0x10` len=3 | length 3 |
| `x64_RED_n_x87_modrm_length` (n4) | `D9 00` | 401038 | `FLD float ptr [RAX]` len=2 | length 2 |
| `x64_RED_n_enter_length` (n5) | `C8 10 00 00` | 40103a | `ENTER 0x10,0x0` len=4 | length 4 |
| `x64_RED_n_jrcxz_length` (n6) | `E3 00` | 40103e | `JRCXZ 0x00401040` len=2 | length 2 |
| `x64_RED_o_moffs_64bit_address` (o) | `A1 88 77 66 55 44 33 22 11` | 401040 | `MOV EAX,[0x1122334455667788]` len=9 | length 9 and the memory operand's absolute address `0x1122334455667788` |

Length classes covered: ModRM only (n1, n4), ModRM + imm32 (n2),
ModRM + imm8 (n3), imm16 + imm8 (n5), rel8 (n6). `8C`/`8E` (ModRM
only) and `CA` (imm16) are the same classes as n1/n4 and n5 and get no
row. `x64_RED_pop_rm_decoded` (m) keeps its own row and its own
assertions.

Read from the header before the reds were written: `x86_operand_t.disp`
is `int32_t`. (o)'s address assertion therefore cannot be met by a
read-width change alone; the field must widen (or a second field must
carry the 64-bit absolute), which changes what `disp` means for every
reader (rule 24: readers enumerated from source before a line
changes). `X86_INS_MOVSXD` does not exist in the enum; `X86_INS_IMUL`
does. The (p) reds assert "not UNKNOWN" and operand shape, not an enum
value, so no header changes are needed to write them.

Predicted first failure of every (n) red at the current decoder:
`length: expected N` with the decoder returning 1. Predicted first
failure of (o): `length: expected 9` with the decoder returning 5.

### (p) recognition, recorded and NOT fixed with (n)

`63` MOVSXD and `69`/`6B` IMUL are corpus opcodes (261 MOVSXD starts;
166 IMUL runs) and stay UNKNOWN after a length-only (n) fix: on the
operand differential they will move from `nostart` to `undecoded`
(and the rows behind them from `nostart` to whatever they are). Two
recognition reds are minted now so that the move is on the list:
`x64_RED_p_movsxd_decoded` (`63 C0`: not UNKNOWN, two register
operands, destination size 4, source size 4 per Ghidra `EAX,EAX`) and
`x64_RED_p_imul_imm_decoded` (`69 C0 10 00 00 00`: not UNKNOWN, three
operands, immediate `0x10`). x87, ENTER and JRCXZ recognition is out
of scope and recorded here as such (no UIR meaning for x87; ENTER and
JRCXZ are rare on the corpus: 0 ENTER starts, 0 JRCXZ starts).

## Named alternatives for the fix (nothing chosen here)

- A1: a length-only table for the one-byte map (Intel SDM Vol 2D
  A.2, opcode map: which unknown opcodes take a ModRM, and which
  immediate width), consulted only by the `default:` arm. Cannot
  change any decoded instruction; closes (n1-n6) only.
- A2: decode the opcodes (MOVSXD, IMUL imm, x87 as a class, ENTER,
  JRCXZ). Closes (n) and (p) at once, but then a length assertion
  passing proves nothing about the recovery engine for the opcodes
  not decoded (`8C 8E CA` and the invalid set). A1 first, then (p),
  is the order that keeps the two measurable apart.
- Guard owed with either: an opcode that is unknown AND correctly
  length 1 today must stay length 1 (`9C` PUSHF: Ghidra verdict
  wanted before it is written; a scratch fix that consumes a ModRM
  for every unknown opcode must fail it).

## Predictions for the differential after an (n) fix (A1)

- `nostart` rows fall on every 64-bit input with IMUL/MOVSXD triggers
  and on nmap (x87); the 353 attributable runs close; the 9 TEST, 4
  section-start, 2 INT, 1 PEXTRW runs do not; the 63 MOV runs are
  unpredicted (unattributed).
- `undecoded` rises by the count of MOVSXD/IMUL-imm/x87 starts that
  were previously inside a run (fed from `nostart`, per the rev-2
  invariant: no instruction leaves `operand_ok`).
- Controls: nmap moves (x87 is on it), so nmap is NOT a control for
  (n); the two ReactOS 32-bit controls have 0 nostart today and must
  stay at 0 and identical.
- Fixture v10 after (m)+(n)+(o): boundary 23/23, mid 0.

## Order

(n) pre-registered here. Then (m) (own gate: XPASS on
`x64_RED_pop_rm_decoded` only; every (n)/(o)/(p) red stays XFAIL, which
is the proof that (m) did not eat (n)'s evidence). Then (n) as its own
fix with its own gate. (o) and (p) are separate fixes, each
pre-registered before a line changes. ONE differential after the batch
the owner approves.
