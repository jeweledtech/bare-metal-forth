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
instruction immediately before it. Over all 16 files (15 corpus inputs + the fixture = 16): **1109 nostart
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
is `int32_t`. The `-Wtype-limits` warning the (o) red raises at its
displacement comparison (`test_x86_decoder.c`, "comparison is always
true") is caused by that width and **retires with (o)'s `disp`
widening**, discharged by the fix that causes it, not carried as
loose debt. (o)'s address assertion therefore cannot be met by a
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

## Invariant for the (n) differential (governing form, owner ruling 2026-09-19)

*No instruction leaves `operand_ok`, and every class increase is fed
only from `nostart` or from the class the fix addresses, for rows
outside a desync run. Inside a run no class claim can be asserted at
all.* The exemption is available only when the run is **named**: its
start offset, its triggering instruction, and the defect that owns it
(as for ACPI `.text+0x69d3d`, MOVSXD, (n) in
`fix-em-acpi-69d4c-window-2026-09-18.log`). An unnamed run is not an
exemption; it is an unexplained regression wearing one. Any row that
leaves `operand_ok` in the (n) differential is therefore read from
bytes and either named or treated as a regression that stops the fix.

**Standing prediction, to be retired in the same act as (n) landing:**
ACPI `.text+0x69d4c` (`MOV RAX,qword ptr [RBX+0x58]`), `nostart`
since (m), returns to `operand_ok` when (n) fixes the `63` length
(the run's trigger at `+69d3d` is `4c 63 c0`). Its return is read from
the (n) differential's ACPI matrix (`nostart → ok` at that offset),
not inferred from the totals.

Input count, pinned: **15 corpus inputs + the fixture = 16** lines in
every `differential-all` log (8 HP drivers + 4 modules + 2 ReactOS +
nmap = 15; plus `x64_reds.elf`).

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

---

# Amendment 2026-09-19: A1 as ruled, against four conditions

Owner ruling 2026-09-19: **A1**, because (n) is named as a
length-recovery defect and the fix must repair recovery generally, not
remove today's triggers; A2 would close the length reds and the (p)
recognition reds in one act so neither movement could be attributed.
Four conditions attach. This amendment is the design against them.
Decoder state: private HEAD `bf97521` (post fix (m)); test-x86
pass=73 xfail=14. **No line in `src/` changes with this document.**

## Fixture v11 and the guard's oracle verdict (done with this amendment)

Fixture v11, sha256
`537a50cac8a9a2ece09d693c2812dbb4ae77fd8a7950725e72360558589e184b`
(`x64_reds.s`, built `as --64; ld -Ttext=0x401000`, Binutils 2.42; the
same command reproduces v10's `cfe59357...` from v10 source). Three
bytes inserted after (m) `8F 00` and before (n1) `63 C0`: `9C`,
`89 C0`, `9D`. The guard rows sit in the stretch the walker is still
synced through ((m) is fixed); the decoded two-byte MOV between them
makes a naive ModRM-consuming fix land mid-instruction (`9C` eats `89`,
`C0` then reads `9D` as ModRM mod=10 and pulls disp32 + imm8) instead
of re-syncing by luck on another one-byte opcode. Every v10 address
through `40102b` is unchanged; (n1)..(b) shift **+4**. The stale line
in the fixture source ("rows after (m) are unmeasurable until (m) is
fixed") was corrected in the same edit.

Oracle `x64-reds-v11-oracle-2026-09-19.log` (Ghidra 12.1.2 PUBLIC,
snap rev 47, InstrAt.java): all 26 rows START; the 12 predicted rows
matched the prediction written in the log header before the run:
`40102d PUSHFQ len=1`, `40102e MOV EAX,EAX len=2`, `401030 POPFQ
len=1`, `401031 MOVSXD len=2`, `401033 IMUL len=6`, `401039 IMUL
len=3`, `40103c FLD len=2`, `40103e ENTER len=4`, `401042 JRCXZ
0x00401044 len=2`, `401044 MOV EAX,[..] len=9`, `40104d MOV RAX,imm64
len=10`, `401057 RET len=1`. The six (n) reds, (o) and the two (p) reds
are relabelled to the v11 addresses in the test file (comment + address
argument only; bytes and assertions unchanged).

**Guards (negative control), verdict banked, to be written with the
fix commit:** `x64_GUARD_n_pushf_stays_len1` (`9C` at `40102d`:
instruction UNKNOWN, length 1) and `x64_GUARD_n_popf_stays_len1` (`9D`
at `401030`: UNKNOWN, length 1). Procedure, logged before the real fix:
apply a scratch that consumes a ModRM after every unknown opcode; both
guards must FAIL and `dump_starts` on v11 must lose the start at
`40102e` (the walk breaks at the guard byte, visibly); revert; then the
real fix, under which both guards PASS.

Differential prediction for the v11 fixture line: today (pre-(n))
`ghidra=26`, matched starts through `401031`, `401031` `undecoded`
(desync source), 8 rows `nostart` (`401033`..`401057`); after (n):
26/26 boundary, `undecoded` = the (p) set + guards (`63`, `69`, `6B`,
`D9`, `C8`, `E3`, `9C`, `9D` = 8), `nostart` 0, and the (o) row `401044`
measured at its own length only once (o) lands (before that it is the
one remaining desync source on the fixture: rows after it, `40104d`
and `401057`, stay `nostart` until (o)). Restated prediction: **after
(n) alone, v11 = 24 matched starts + 2 nostart behind (o)**; 26/26 is
the post-(o) number.

## Condition 1: table entries are rules, not integers

A flat 256-array of lengths is wrong on its face (`A9 id` 5 / `66 A9
iw` 3; `8B 00` 2 / `8B 80 xx xx xx xx` 6). The table is
`x86_opcode_table.h`, one entry per first byte, each entry:

```
{ status[mode], has_modrm, imm_kind }
  status   : VALID | INVALID | ESCAPE | PREFIX      (per mode: 64-bit, legacy)
  has_modrm: 0 | 1                                   (SIB/disp computed by decode_modrm)
  imm_kind : NONE | IB | IW | IZ | IW_IB | JB | JZ | AP | MOFFS | IMM_V | DIGIT
```

- `IZ` resolves through the decoder's existing `op_size`: 2 under
  `0x66`, else 4; **REX.W never widens `IZ`** (`48 69` / `48 C7` /
  `48 A9` keep imm32, sign-extended). `IMM_V` is `B8+r` only: 2 / 4 /
  8 (REX.W). `JZ` is `E8`/`E9`/`0F 8x`: rel32; its width under
  `0x66` in 64-bit mode is vendor-divergent, so the entry carries the
  oracle's modeled value labelled as such (see condition 2), never a
  hardware claim. `AP` (`9A`, `EA`) is 7 in legacy
  32-bit mode and INVALID in 64-bit. `MOFFS` is 8 in 64-bit (4 under
  `0x67`), 4 in legacy: the (o) row. `DIGIT` marks the opcodes whose
  immediate depends on ModRM.reg (`F6`, `F7`: `/0 /1` take IB / IZ,
  `/2-/7` none; `C6`, `C7`: `/0` takes IB / IZ, other digits INVALID
  except the `mod=11 /7` XABORT/XBEGIN forms which the generator
  records as it finds them) with an 8-entry sub-rule.
- Notation follows Intel SDM Vol. 2D, Appendix A.2 (Table A-2 one-byte
  opcode map; A.2.5 for `Eb Ev Gv Ib Iw Iz Jb Jz Ap`), cited per row
  class in the table header. The generated table is the derived
  artefact; the SDM section is the master (spec-first provenance);
  the hand check below records where they were compared.
- The table is consulted **only by the one-byte `default:` arm**. No
  decoded opcode's path changes, so the fix cannot alter a decoded
  instruction: that is what keeps (n) and (p) separately measurable.
- Worked entries for the survey's 17 real wrong-length opcodes:
  `63` VALID64 modrm NONE (`Gv,Ed`); `69` modrm IZ; `6B` modrm IB;
  `8C` `8E` modrm NONE; `8F` modrm NONE (DIGIT: `/0` only; decoded
  since (m), listed for the sweep); `C8` no-modrm IW_IB; `CA` IW;
  `D8`-`DF` modrm NONE (every x87 form, `mod=11` included, is opcode +
  ModRM); `E3` JB. Guards: `9C` `9D` no-modrm NONE. Invalid-in-64
  (SDM Table A-2 "i64" marks): `06 07 0E 16 17 1E 1F 27 2F 37 3F 82
  9A CE D4 D6 EA`, and `C4 C5 62` are legacy LES/LDS/BOUND (modrm)
  whose 64-bit meaning is a VEX/EVEX escape. `D5` is listed once, in
  the ESCAPE set of condition 4, not here (review correction
  2026-09-19: one byte cannot be in two sets in one mode): classically
  `AAD ib`, i64; APX repurposes it as the REX2 prefix. Whether Ghidra
  12.1.2 models REX2 is read off the generator run, and the row's
  64-bit status is set from that reading (ESCAPE if modeled, INVALID
  if not), stated in the table header. Legacy column for `D4` and
  `D5`: no-modrm + IB (AAM/AAD take an imm8), length 2, not 1.
- Mode scope: 64-bit and legacy 32-bit are generated and swept (both
  are in the corpus; x87 runs are on the 32-bit nmap control). 16-bit
  mode reuses the legacy table through `op_size`; that is an
  **assumption, not a verification**: the `.com` suite is its only
  control, and a 16-bit oracle sweep is owed if a 16-bit input ever
  enters the differential. The table is consulted in every mode; the
  one thing without an oracle behind it is the legacy status column
  applied to 16-bit, and it is named here so no reader mistakes it
  for a verified column.

## Condition 2: the consistency sweep is the gate, across prefixes

`x64_table_consistency_sweep`, a test in `test_x86_decoder.c`, under
`make test-x86` every run (the suite is the list). The survey harness
from the 09-18 log header, pointed at decoder-vs-table instead of
decoder-vs-objdump:

- Probes: first byte `00`-`FF` × prefix {none, `66`, `48`, `66 48`}
  (64-bit) and {none, `66`} (legacy) × ModRM byte {`00`, `80`}, zero
  padded to 16 bytes. ModRM `80` (mod=10, disp32) is the
  **bit-isolating control on `has_modrm`**: with ModRM `00` alone,
  "no ModRM + IW" and "ModRM + IB" both read 3, so a no-prefix,
  `00`-only sweep would pass the flat-array bug of condition 1 and a
  swapped has_modrm bit besides.
- Check: for every probe where the decoder returns instruction ≠
  UNKNOWN (**decoded rows**), decoder length == table length. Rows
  where the decoder returns UNKNOWN agree by construction after the
  fix (the `default:` arm consults the table) and are counted
  separately as **tautological**; prefix bytes, `0F`, and ESCAPE rows
  are **skipped with the reason printed** and counted. Three counts on
  the summary line: `checked=N tautological=M skipped=K`; a skip never
  reads as a pass, and `checked` is the denominator the decoder cannot
  inflate (fewer decoded opcodes = a smaller visible number). The
  deflation side has a floor (review correction 2026-09-19): the sweep
  asserts `checked >= N` with N pinned at its first-run value and
  raised by hand only; a later change that turns decoded opcodes into
  UNKNOWN would otherwise shrink the denominator and open the gate
  silently.
- **Permitted disagreements are named, each with its red attached,
  and the assertion is "the disagreeing set equals this list"**: an
  entry that stops disagreeing is a hard failure until it is removed
  by hand (the `xfail_names` discipline), so the list can only shrink
  with fixes. Pre-registered list for the first run, from reading the
  immediate-read sites today (`x86_decoder.c`):
  - **(o)** `A0`-`A3`: decoder 5, table 9 (64-bit). Red exists.
  - **(r1)** `68` PUSH Iz: `read_i32` unconditional (line 287);
    `66 68 iw` is 4 bytes, decoder reads 5. Both modes. Boundary with
    (e), named before either is touched: (e) owns the **stack slot**
    (`operands[0].size`, 64 / 16 under `0x66`); (r1) owns the **encoded
    immediate width** read from the stream. Same opcode, no overlap;
    (e)'s pre-reg already recorded "never changes an encoded immediate
    width" (`x86_decoder.c` fix-(e) comment).
  - **(r2)** `A9` TEST eAX,Iz: unconditional (line 609). Both modes.
  - **(r3)** `F7 /0` TEST Ev,Iz: unconditional (line 907). Both modes.
  - `E8`/`E9` under `66` in 64-bit: decoder reads rel32 (lines 818,
    828). **Not oracle-decidable, and the entry says so.** This is a
    vendor divergence: Intel forces the near-branch operand size to 64
    bits and ignores the prefix; AMD has honoured a 16-bit form. The
    oracle can only report what its disassembler models, so the table
    entry is written *"modeled as N by the oracle at pin 12.1.2; known
    vendor-divergent"* (N read from the generator run), the sweep
    compares the decoder to that modeled value, and no red claims a
    hardware truth here. If the modeled value differs from the
    decoder's 5, the row is fixed to the model and labelled as such;
    it is never counted as a length defect of the (r) kind.
  - Every other decoded Iz site already switches on `op_size` (`05`..
    `3D` line 420, `81` line 320, `B8+r` line 634, `C7` line 700).
  (r1)-(r3) become reds the same session the generator's oracle run
  prints their expected values (objdump screen today: `pushw $0x10` 4,
  `test $0x10,%ax` 4, `test $0x10,%ax` 5 with ModRM `C0`); they are
  not (n) and are not fixed with (n).
- Prediction for the sweep's first run (it runs on the unfixed decoder
  first, commit 2, and again as the (n) gate): **the disagreeing set
  is exactly {(o), (r1), (r2), (r3)}**, asserted as an exact set, never
  "at most four": an exact set fails when a fifth appears AND when one
  silently disappears, and a sweep introduced already-failing under a
  loose assertion is a sweep that gets loosened. `E8`/`E9` are not on
  the list because their table entry compares to the oracle's model,
  not to a hardware claim (next bullet). Anything else is a table or
  decoder defect that stops the fix until named.

## Condition 3: generate the table, don't type it

- `tools/ghidra/OpcodeLengths.java` (new, committed beside the table):
  imports a probe blob with `-processor x86:LE:64:default` (and
  `x86:LE:32:default`) via the raw BinaryLoader; for each 16-byte
  slot, `new DisassembleCommand(addr, null, /*followFlow*/ false)`
  then `getInstructionAt(addr)` → mnemonic, length, or NONE.
  `followFlow=false` is what keeps one slot's decode from marching
  into the next; the fixture route (InstrAt on flow-following
  analysis) is wrong for this because an invalid byte ends the flow,
  exactly as RETF did in the v10 draft.
- `tools/translator/scripts/gen_opcode_table.py`: builds the blob (256
  opcodes × [4 or 2 prefix sets × 2 ModRM] + 8 digit probes at
  no-prefix mod=00 = 4096 slots, 64 KiB, per mode), runs the script,
  fits the rule per opcode (`has_modrm = (len(80) − len(00) == 4)`,
  the constant being ModRM+disp32 minus bare ModRM, as in the
  condition-1 example `8B 00` = 2 / `8B 80 ..` = 6;
  imm kind from `len(00) − 1 − has_modrm` and the `66`/`48` deltas;
  DIGIT if the eight digit probes disagree; INVALID if NONE at
  no-prefix; ESCAPE/PREFIX from a hand list cited to SDM 2.1.1,
  2.2.1, 2.3.5 VEX, 2.7 EVEX, and the APX spec for `D5` REX2, each
  such row marked HAND). **If the fitted rule does not reproduce every
  probe length for an opcode, the generator refuses and prints the
  opcode; no table is written.** Predicted refusals on first run: 0;
  suspects if not 0: `F6 F7 C6 C7 FF 8F` (digit forms), `D8`-`DF`
  `mod=11` escapes.
- Header of the generated file: generator sha256, blob sha256, Ghidra
  version + snap revision, date, SDM citation. `make opcode-table-check`
  regenerates and diffs; a non-empty diff fails.
- Hand check recorded in the closing doc: the 17 + 2 wrong-length rows
  and the invalid set compared by eye against Table A-2; a
  disagreement between oracle and spec is a finding, never silently
  resolved toward either.

## Condition 4: the table must be able to refuse

- Statuses: **INVALID** (not an instruction in this mode: SDM i64
  marks) and **ESCAPE** (`C4 C5 62 D5` in 64-bit: a valid encoding
  whose length the one-byte table cannot give). ESCAPE is not (n):
  the decoder keeps today's behaviour on those bytes (UNKNOWN, length
  1) and the gap is named **(q) VEX/EVEX/REX2 unmodelled**. No red
  minted, on a **measured zero**, not an untaken count: over the 16
  banked Ghidra per-instruction files (512,213 starts) there are 0
  starts whose mnemonic is VEX/EVEX-encoded (mnemonics beginning `V`,
  plus the BMI2/mask set ANDN BLSR BLSI BLSMSK BZHI SHLX SHRX SARX
  MULX RORX PDEP PEXT BEXTR KMOV* KAND KOR; the only non-V hits were
  three TZCNT on nmap, legacy `F3 0F BC`). Instrument limit: the files
  carry mnemonics, not bytes, so this is a mnemonic screen, not a
  first-byte count; a positive control of the same grep shape returned
  31,404 MOV starts on pci.sys. Twenty-second rule: a (q) red would
  have no corpus number to move today. Recorded here so (q) is not
  mistaken for INVALID or for a length defect.
- Walker behaviour on INVALID, decided: `x86_decode_one` returns
  length 1 with `instruction = X86_INS_INVALID` (a linear sweep can
  only step one byte past a byte that is not an instruction);
  `x86_decode_range` **continues** (a `break` would drop the rest of
  a section, and data inside `.text` is common on this corpus). It is
  a result that says "not a result", which is the nineteenth rule's
  requirement, rather than a length that looks like one.
- `X86_INS_INVALID` is a header addition (enum + `ins_names` entry
  `"(invalid)"`). Readers of the instruction value, enumerated from
  source (rule 24): `x86_ins_name` (bounded by `X86_INS_COUNT`, gets
  the new name), `x86_print_decoded` (disasm target: prints the name),
  `uir.c` lifter `default:` → `UIR_NOP` (INVALID lifts as UNKNOWN does
  today; unchanged), `tests/dump_starts.c` `print_mnemonic` → prints
  `INVALID`, and `scripts/compare_operands.py` `classify`, where `???`
  → `undecoded` but `INVALID` would fall into `om != gm` → `mnemonic`,
  a wrong attribution. So the comparer gets one class,
  `invalid_at_start` (our INVALID at a Ghidra START), **prediction 0
  on all 16 inputs**; nonzero means the table calls a byte invalid
  that Ghidra decodes, and the 32-bit inputs are where a wrong mode
  column would fire first. Defect-revealing, not concealing: no row
  can move between existing classes because INVALID rows are, by the
  prediction, never at a Ghidra start.
- Reds (red today; the enum ships in the red-minting commit, the one
  header line before the fix, behaviour-neutral):
  - `x64_RED_n_invalid_06_refused`: `06` in 64-bit → INVALID, length 1.
  - `x64_RED_n_invalid_82_mode_split`: `82 C0 10` in 64-bit → INVALID,
    length 1; the same bytes in 32-bit → length 3, not INVALID
    (group-1 alias `ADD AL,0x10`). Bit-isolating control on the mode
    column; the 32-bit half is also red today (default arm, length 1).
  - `x64_RED_n_invalid_walk_continues`: `x86_decode_range` over
    `06 90` yields two instructions, the second NOP at offset 1.
  Expected values: SDM Table A-2 i64 marks + objdump `(bad)` screen
  today; Ghidra verdicts from the generator's oracle run **before the
  reds are minted**.

## Gate for the fix, restated with the additions

XPASS on exactly: `x64_RED_n_movsxd_length`, `_imul_imm32_length`,
`_imul_imm8_length`, `_x87_modrm_length`, `_enter_length`,
`_jrcxz_length`, `_invalid_06_refused`, `_invalid_82_mode_split`,
`_invalid_walk_continues` (9 names). Stay XFAIL: (a), (d'), (f), (g)×2,
(o), (p)×2, and (r1)-(r3) once minted. Guards PASS, and FAILED under
the logged scratch. Sweep PASS with the disagreeing set equal to its
pre-registered list. Then ONE differential: predictions of the 09-18
section stand (353 of 433 runs close; 9 TEST, 4 section-start, 2 INT,
1 PEXTRW do not; 63 MOV runs unpredicted; ReactOS controls 0 and
identical; nmap moves), plus: standing prediction ACPI `.text+0x69d4c`
`nostart → ok` read from its matrix; fixture v11 = 24 matched + 2
nostart behind (o); `invalid_at_start` = 0 on all 16; input count 15
corpus + fixture = 16.

## Commit order (private repo, each its own gate)

1. Fixture v11 + test address relabel (this amendment; no `src/`).
2. Generator + blob + generated table + sweep test; the sweep runs on
   the unfixed decoder (only decoded rows are checked) and its first
   disagreeing set is read and compared to the list above; (r1)-(r3)
   reds minted from the oracle run's values.
3. Header enum + the three INVALID reds + the two guards (guards
   PASS; scratch-fail log).
4. The fix: the `default:` arm consults the table. XPASS gate.
5. The differential.

Nothing after step 1 happens before the owner has read this.

---

# (s) two-byte map lengths and (t) two-byte INVALID, pre-registered 2026-09-19

Found by the gap the owner named at the A1 review: the one-byte map
had been surveyed, the `0F` map had not, and one of the runs this
document predicts will NOT close is a PEXTRW (`0F C5 /r ib`). Survey:
`x64-two-byte-opcode-survey-2026-09-19.log`, all 256 `0F xx` at
mandatory prefix {none, `66`, `F2`, `F3`} × ModRM {`00`, `80`, `C0`},
12 probes per opcode. Each widening changed the count: `C0` only found
5 opcodes; three ModRM forms found 9 (the four added are a mechanism
`C0` cannot see); the prefix dimension, which in the two-byte map
selects the instruction rather than a variant, found a fourth
mechanism (`0F 78`) and moved the Jcc-near forms into the
vendor-divergence entry. A one-form probe reports a floor as a count.

**Predicted corpus movement, written before any run: one run, maybe
zero.** This is a hardware-real, compiler-never fix of the REX.R-on-a-
group-digit kind, and the unit reds are its instrument. Counts, from
the 16 banked Ghidra files (mnemonic screen) and, for the CR/DR row,
from the bytes (objdump over the 8 HP drivers, ModRM read after
prefix/REX):

| mechanism | opcodes | decoder | true | corpus starts |
|---|---|---|---|---|
| trailing imm8 after ModRM, `0F` default arm reads ModRM only | `0F 70` PSHUFW, `0F C2` CMPPS, `0F C4` PINSRW, `0F C5` PEXTRW | 3 (7 at mod=10) | 4 (8) | PSHUFW 0, CMPPS/CMPEQPS 0, PINSRW 0, **PEXTRW 1** (storport) |
| no ModRM, arm consumes one | `0F AA` RSM | 3 | 2 | 0 |
| mod field ignored by hardware, decoder honours it as memory | `0F 20`-`0F 23` MOV CR/DR | 7 at mod=10 | 3 | 217 moves, **0 encoded with mod≠11** (compilers emit mod=11 because mod is ignored) |
| prefix selects a different-length instruction | `66 0F 78` EXTRQ ib ib, `F2 0F 78` INSERTQ ib ib | 4 | 6 | 0 `0F 78` of any form (bytes, 8 HP drivers) |
| vendor-divergent, NOT a defect claim | `66 0F 80`-`8F` Jcc near | 7 (rel32) | objdump models 5 (rel16) | 0 (bytes); entry written as "modeled as N by the oracle at pin 12.1.2; known vendor-divergent", same as `66 E8`/`E9` |

Prefixed forms of the imm8 family (`66`/`F2`/`F3 0F 70` PSHUFD/LW/HW,
`66 0F C2` CMPPD etc., `66 0F C4`/`C5` on xmm) are one short in every
prefix state too; corpus starts 0 for every one of them (mnemonic
screen over the 16 files; bytes over the 8 HP drivers agree).

So (s) moves at most the one PEXTRW run on storport; every other row
of its differential is predicted identical. The CR/DR row: the count
that matters is moves encoded with mod≠11, which is 0; the 217 is the
positive control that the byte scanner sees what the mnemonic screen
sees. Handled already and not
in (s): `0F A4`/`0F AC` (SHLD/SHRD ib), `0F BA` (group 8 ib),
`0F 71`-`73` (groups 12-14 ib), `0F 3A` (three-byte map, ib).

## Reds (fixture v12, sha256 `bf7a0e7c5d66bad452a9...` in `x64-reds-v12-oracle-2026-09-19.log`)

Rows appended after (o): every v11 address through `401044`
unchanged; (b) imm64 `40104d → 401060` and RET `401057 → 40106a`
(+19); RSM after the RET at `40106b`. Length only, as for (n).

| name | bytes | addr | Ghidra | asserts |
|---|---|---|---|---|
| `x64_RED_s_pshufw_imm8_length` (s1) | `0F 70 C0 00` | 40104d | `PSHUFW MM0,MM0,0x0` len=4 | length 4 |
| `x64_RED_s_cmpps_imm8_length` (s2) | `0F C2 C0 00` | 401051 | `CMPEQPS XMM0,XMM0` len=4 (Ghidra spells the imm-0 form by predicate) | length 4 |
| `x64_RED_s_pinsrw_imm8_length` (s3) | `0F C4 C0 00` | 401055 | `PINSRW MM0,EAX,0x0` len=4 | length 4 |
| `x64_RED_s_pextrw_imm8_length` (s4) | `0F C5 C0 00` | 401059 | `PEXTRW EAX,MM0,0x0` len=4 | length 4 |
| `x64_RED_s_mov_cr_mod_ignored` (s6) | `0F 20 80` | 40105d | `MOV RAX,CR0` len=3 | length 3 |
| (s5) RSM, `0F AA` | | 40106b | InstrAt: NONE by construction (after RET; RSM ends flow as RETF did) | **not minted yet**: verdict owed from the no-flow probe (`OpcodeLengths.java`, `DisassembleCommand followFlow=false`) at 40106b; objdump screen 2 |

Predicted first failure of s1-s4: `length: expected 4` with the
decoder returning 3; s6: `expected 3`, decoder 7. All five stay XFAIL
through (n): the one-byte table is consulted by the one-byte
`default:` arm only, so an (n) fix that closes any (s) red has changed
the two-byte arm and is wrong. Fix (s) is its own pre-reg: the same
rule-table treatment for the `0F` map (its `no_modrm` hand list at
`x86_decoder.c:1217` is the flat-array bug in miniature), generated
and swept the same way, after (n).

## (t) the two-byte map has no INVALID either

23 `0F` opcodes are objdump-invalid under all 12 probes (list in the
survey summary) and the decoder returns a length on every one.
This is a **ceiling**, not a floor (review correction 2026-09-19): the
count went 43 → 32 → 23 as the probe widened (one ModRM form, three
forms, three forms × four prefix states), and a wider probe can only
reclassify an opcode from invalid to valid, never back, so the true
invalid set is **≤ 23**. "Floor" would
license refusing real encodings, the direction that hurts. The number
was taken under zero digit and no mandatory prefix (`0F 71`-`73` are valid at digits 2/4/6, `0F BA`
at 4-7, `0F C7` at 1/6/7, `0F 3A` is the three-byte map, `0F B8`
POPCNT under `F3`, `0F D0`/`D6`/`E6` under `66`/`F2`/`F3`), not the
list. Banked separately from (s) for the table work: the `0F`
generator run resolves it with digit and mandatory-prefix probes, and
the walker's INVALID behaviour decided under condition 4 applies
unchanged. No red minted for (t) until the generator run gives the
list; recorded here so it does not leave with (s).

## (u) the two-byte no-ModRM hand list against the oracle, minted 2026-09-19

`x86_decoder.c:1217` (the `0F` default arm's `no_modrm` list) is a
hand-typed shadow of the two-byte map: named in prose above, given a
letter and a red tonight per the 09-18 ruling (a prose registry is one
more artefact to keep in sync; the suite is the list).

**Instrument: the no-flow probe, three attempts before it was one.**
`tools/ghidra/OpcodeLengths.java` (DisassembleCommand at each slot of a
raw probe blob) over `tests/data/x64_reds/probe0f_2026-09-19.bin`:
256 `0F xx` × prefix {none, `66`, `F2`, `F3`} × ModRM {`00`, `80`,
`C0`}, 3072 slots of 16 bytes. Attempt 1 (`followFlow=false`, no
range): 669 objdump-valid rows NONE, failures alternating by slot
parity; `followFlow=false` stops at branches only, fall-through ran
across slot boundaries. Attempt 2 (command restricted to the slot's
range): 436 NONE, all odd slots; an even slot's odd leftover `0x00`
straddled into the next slot's first byte. Attempt 3 (padding `0x90`,
always one byte, never a prefix, restriction kept): clean. Each
attempt's defect was caught by the objdump screen disagreeing with
the oracle on rows like SYSCALL and MOVUPS, which is what the screen
is for; recorded in the oracle log header before each rerun.
The objdump screen was then regenerated on the blob's exact bytes
(fourth survey pass) because the three-byte maps and 3DNow read the
padding byte as ModRM/suffix.

**Table:** `tests/data/x64_reds/oplen0f_2026-09-19.tsv`, generated by
`scripts/oplen_to_tsv.py` from the oracle log + blob + survey log
(rows accepted by address inside the run's own header range, never by
slot number: the fixture's RSM slot 0 had overwritten the blob's slot
0 in the first output). 3072 rows: **2065 double-attested** (Ghidra
and objdump print the same length), 1 length disagreement (`F3 0F AE
/0` mem: Ghidra RDFSBASE 4, objdump FXSAVE 8; the SDM requires mod=11
for RDFSBASE, so the oracle is lenient here), 47 Ghidra-only rows
(EMMS/WBINVD under a prefix, where the screen's lone-prefix rule
called objdump invalid; and MOVMSKPS/PEXTRW/EXTRQ/INSERTQ/BSF/BSR/
MASKMOVDQU/MOVDQ2Q/MOVQ2DQ/MOVNTI in memory forms the SDM forbids:
oracle leniency), 83 objdump-only rows (**no Ghidra model at pin
12.1.2** for: `0F 23` MOV DR,r, `0F 78`/`0F 79` bare VMREAD/VMWRITE,
`0F 01 C0` ENCLV, `66 0F 35` SYSEXIT, `0F A6`/`0F A7` VIA MONTMUL/
XSTORE, 3DNow rows objdump names, and **every `66 0F 80`-`8F` row**:
the vendor-divergent Jcc-near form is not modeled by the oracle at
all, so its table entry is "no oracle model; decoder keeps rel32; no
assertion", not "modeled as N"). Instrument disagreements are findings
for the spec, resolved per row with a HAND mark before any table row
is emitted from them; never folded either way.

**Red:** `x64_RED_u_0f_map_matches_oracle`: for every double-attested
row, decode the probe (padded `0x90` as in the blob) and require the
oracle's length; the checked count has a floor (`checked >= 2065`,
first-run value, raised by hand only) so the denominator cannot fall
silently. The failure message names the disagreeing opcodes.

**Denominator accounted (review 2026-09-19): every one of the 3072 rows
is in exactly one class, printed in the oracle log next to the floor.**

| rows | disposition |
|---|---|
| 2065 | double-attested: Ghidra and objdump print the same length; the red checks these |
| 1 | length disagreement (`F3 0F AE /0` mem: RDFSBASE 4 vs FXSAVE 8); finding for the spec |
| 47 | Ghidra-only (oracle leniency on forbidden memory forms; lone-prefix screen artefact on EMMS/WBINVD) |
| 83 | objdump-only (no Ghidra model at pin 12.1.2: `0F 23`, bare VMREAD/VMWRITE, ENCLV, `66` SYSEXIT, VIA, 3DNow rows, all `66` Jcc-near) |
| 264 | NONE in both: the 22 all-probe-invalid opcodes × 12 probes |
| 612 | NONE in both: an opcode valid elsewhere whose prefix/ModRM form does not exist (e.g. `F2 0F C5`) |
| 3072 | total |

2065 is the checked count, not "coverage": a third of the probe space
is legitimately unassertable and is listed as such rather than assumed.

**Pre-registered first failure: 9 opcodes {0F20 0F21 0F22 0F70 0F78
0FAA 0FC2 0FC4 0FC5}. Observed: `checked=2065 wrong_rows=61
wrong_opcodes=10: 0F0F 0F70 0FAA 0FC2 0FC4 0F20 0F21 0F22 0FC5
0F78`.** The miss is `0F 0F` (3DNow: an opcode *suffix* byte after the
ModRM, decoder 3 vs 4), which the `0x00`-padded screen had marked
invalid and the `0x90`-padded screen attests: a fifth mechanism, not
in (s), corpus starts 0 (mnemonic screen, positive control PEXTRW 1).
`0F 23` is absent from the set only because Ghidra has no model for
it; its (s6)-class row stays red by the fixture oracle, not by (u).

Two more (s) reds minted from the same table: `x64_RED_s_pextrw_xmm_
imm8_length` (`66 0F C5 C0 ib`, 5: the corpus PEXTRW on storport is
this xmm form, found by bytes, the mnemonic screen cannot see the
prefix; **twenty-fifth rule, docketed 2026-09-19:** a corpus count by
mnemonic says the instruction occurs, only a count by bytes says which
encoding occurs, and a red justified by a corpus count is written
against the encoding the byte count found) and `x64_RED_s_rsm_no_modrm_length` (`0F AA`, 2: no-flow
probe at fixture `40106b` and blob row `0FAA00` agree). Suite after
minting: pass=73 xfail=22 fail=0 xpass=0 (tests=95).

**Gate relation:** (u) closes when the `0F` arm is table-driven (the
(s) fix); (n) must leave it XFAIL (the one-byte table is consulted by
the one-byte arm only), so an (n) fix that moves (u) is wrong. When
(s) lands, (u) may XPASS in the same act; the gate names both, and
`0F 0F` (3DNow suffix) must be in the (s) pre-reg before then or (u)
stays red on it alone.

**(t) restated:** both instruments give the same 22 opcodes as invalid
under all 12 probes: `0F04 0F0A 0F0C 0F24 0F25 0F26 0F27 0F36 0F39
0F3A 0F3B 0F3C 0F3D 0F3E 0F3F 0F71 0F72 0F73 0F7A 0F7B 0FBA 0FC7`,
ceiling **≤ 22** (the `0x90` padding attests `0F 0F`, which the
`0x00` padding could not).

---

# Step 2 as built, 2026-09-19: generator, table, sweep

Commit 2 of the order. **No decoder line changes**; the table and its
length function exist beside the decoder and are included only by the
sweep.

## Instrument: one-byte blobs and the no-flow oracle

`scripts/gen_opcode_table.py blob --mode 64|32`: 16-byte slots, `0x90`
padded, form-major. 64-bit: prefix {none, `66`, `48`, `66 48`} × ModRM
{`00`, `80`} then digits 1-7 at mod=00 = 15 forms, 3840 slots. Legacy:
{none, `66`} × {`00`, `80`} + digits = 11 forms, 2816 slots. Oracle runs
`x64-one-byte-oplen-oracle-2026-09-19.log` and
`x86-32-one-byte-oplen-oracle-2026-09-19.log` (Ghidra 12.1.2, snap rev
47, `make ghidra-oplen`), objdump screens
`x64-one-byte-objdump-screen-2026-09-19.log` and `x86-32-…` over the
blobs' exact bytes; committed tables `oplen1_64_2026-09-19.tsv` and
`oplen1_32_2026-09-19.tsv` (five columns: probe, Ghidra length,
mnemonic, text, objdump length).

**Pinned predictions (log headers) vs observed.** (1) the seventeen
(n) lengths: all as predicted. (2) i64 set NONE in every form: as
predicted, plus `60`/`61` which I had left off the i64 list and the
oracle has NONE (finding (w) below). (3) `9C`/`9D` length 1: as
predicted. (4) `D5`: Ghidra NONE, objdump models REX2 → INVALID at this
pin with a HAND note. `66 E8`: modeled as **4** by both instruments;
`66 48 E8` is 7 (REX.W wins). (5) `C5` with a `0x90` payload: Ghidra
KMOVW 8, objdump NONE; ESCAPE by hand. (6) `A1` 9: as predicted. (7)
`B8`: 5 / 3 / 10 as predicted; **`66 48 B8` observed 11, predicted 10:
an arithmetic miss in the prediction (two prefix bytes), REX.W winning
as predicted.** (8) **refusals predicted 0, observed 5 on the first
fit**, every one an instrument or rule-expression defect and none a
table fact: `E8`/`E9` under `66 48` (the fitter let `66` beat REX.W for
Jz; oracle 7), `9A`/`EA` in 32-bit (the `Ap` kind from condition 1 was
never coded), and `48` in 32-bit (my screen's lone-prefix rule sniffed
bytes and called DEC EAX a prefix; the screen and the parser now take
the prefix count from the slot's form). Second fit: 0 refusals, table
written, `make opcode-table-check` regenerates it byte-identical.

**Dispositions (every row in one class).** 64-bit, 3840 rows:
double-attested 3307, length-disagree 2 (`66 48 9B` WAIT: Ghidra 3,
objdump 2), Ghidra-only 64 (JMPF `EA` in 64-bit, KMOVW via `C5`,
prefixed INC/ADC forms), objdump-only 70 (REX2 `D5` ×13, prefix-byte
"opcodes" under `66 48`), NONE-in-both 397. Legacy, 2816 rows:
double-attested 2726, Ghidra-only 59 (SALC `D6` ×11, prefixed INC/DEC),
objdump-only 5, NONE-in-both 26, no length disagreements.

## Table and length function

`src/decoders/x86_opcode_table.h`, GENERATED (header carries generator
sha256, both source table headers, SDM citation): per mode 256 entries
`{status, has_modrm, imm_kind, digit[8]}`. Kinds fitted: NONE IB IW
IW_IB IZ ID MOFFS IMM_V JZ_VD AP DIGIT; digit sub-rules came out as the
SDM says without being told (`F6` /0 /1 IB, `F7` /0 /1 IZ, `C7` /0 IZ
others INVALID, `8F` /0 only, `FF` /7 INVALID, x87 `D8`-`DF` all
digits). `src/decoders/x86_opcode_len.h`, hand-written: rule → length
under prefixes and ModRM (`0x66` shrinks Iz/Jz, REX.W overrides `0x66`
for both, MOFFS 8/4 by mode, IMM_V 2/4/8, AP 6/4); SIB and disp8
handled for the fix's benefit but asserted only on the generated forms.

## Sweep (condition 2), first run

`x64_table_consistency_sweep` and `x86_32_table_consistency_sweep` in
`test_x86_decoder.c`, every `make test-x86`. Rows the decoder decodes
are **checked** against `opt_length`; UNKNOWN rows are **tautological**;
PREFIX/ESCAPE rows and `66`-prefixed Jz rows are **skipped** with the
reason counted; a decoded row the table calls INVALID is a disagreement
of its own class. **Assertion: the disagreeing opcode set equals the
pre-registered set exactly**, and `checked >= floor`.

| mode | checked | tautological | skipped | wrong rows | disagreeing set (pre-registered = observed) |
|---|---|---|---|---|---|
| 64-bit | 1312 (floor) | 480 | 256 | 54 | {60 61 68 A0 A1 A2 A3 A9 F7} |
| legacy | 720 (floor) | 252 | 52 | 6 | {68 A9 F7} |

**This was a failed prediction, and it belongs beside the other two
(review correction 2026-09-19).** The 64-bit set registered before any
run was exactly {(o), (r1), (r2), (r3)}: four members. A preview
(decoder against the double-attested oracle rows, before the sweep
test existed) surfaced `60` and `61`, the set was amended to six
members, and *then* the first run of the sweep matched. Predicted 4,
observed 6; the additions are `60` and `61`, both (w). The same
preview surfaced the legacy `67` case, which lives outside the sweep
(PREFIX rows are skipped) as the unit red (v). A set that arrived by
amendment after a preview has different standing from one that
survived first contact, and only this record tells them apart later.
The `0F` skip means (s) does not appear, as required. Nothing else
decoded disagrees with the table in either mode. Suite: pass=75
xfail=23 fail=0 xpass=0 (tests=98).

**Condition 1 versus the generator, one example.** Condition 1's i64
list, a transcription of the SDM, omitted `60`/`61`; the generated
table found them (NONE in both instruments, every form). The generator
catching a transcription error is condition 3 justified by one
instance rather than in principle.

**`F6`/`F7` digit `/1` (review check 2026-09-19):** condition 1
registered "`/0 /1` take IB / IZ" (the undocumented TEST alias).
Three instruments, both modes: objdump `f6 c8 10` → `test $0x10,%al`
(3), `f7 c8 10 00 00 00` (6), `66 f7 c8 10 00` (5); the oracle's
digit-1 probe rows `F6 08` = 3 and `F7 08` = 6, double-attested; the
generated table's digit[1] = IB / IZ and `opt_length` returns 3 / 6 /
5. No oracle-versus-spec disagreement; the alias is in the table.
(The first objdump attempt of this check fed bytes with spaces between
them and read `f6 20` MUL; caught by the oracle rows disagreeing with
it, redone with exact bytes.)

## Two findings from the sweep preview, minted or scheduled

- **(v)** legacy mode: `67` makes ModRM mod=10 a disp16 (SDM Vol 2A
  2.1.5, Table 2-1); the decoder reads disp32 (`67 00 80 ..`: oracle
  5, double-attested; decoder 7). In 64-bit `67` selects 32-bit
  addressing and the ModRM form is unchanged, so it cannot fire there.
  Red `x86_RED_v_addr_size_prefix_disp16` minted (XFAIL). Corpus by
  bytes: 0 `67`-prefixed instructions in the three 32-bit inputs
  (control RET 147); predicted movement 0.
- **(w)** `60`/`61` decode as PUSHAD/POPAD in 64-bit mode (`x86_decoder.c`
  lines 270-271); both instruments say NONE (SDM i64). Red
  `x64_RED_w_pushad_invalid_64` asserts INVALID and ships with the
  INVALID batch (commit 3, the enum). Corpus by bytes: 0 `60`/`61` at
  instruction starts in the 8 HP drivers (control RET 6310); predicted
  movement 0. Until then the sweep carries 60/61 in its exact set.

## Order restated

Commit 2 done (this section). Commit 3: enum `X86_INS_INVALID`, reds
`x64_RED_n_invalid_06_refused`, `_82_mode_split`, `_walk_continues`,
`x64_RED_w_pushad_invalid_64`, guards `9C`/`9D` with the scratch-fail
log. Commit 4: the fix, XPASS on the nine (n) names + (w); the sweep's
exact set shrinks by hand to {68 A0 A1 A2 A3 A9 F7} / {68 A9 F7};
(r1)-(r3) reds minted from the table rows `66 68`, `66 A9`, `66 F7 00`
(4, 4, 5, double-attested) before commit 4 so they are on the list when
it lands. Commit 5: the differential.
