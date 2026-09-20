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

---

# Commit 3 as built, 2026-09-19: INVALID, its reds, the guards, the scratch

**Header.** `X86_INS_INVALID` added to the enum before `X86_INS_COUNT`
and `ins_names[X86_INS_INVALID] = "invalid"` (dump_starts prints it
upper-cased as INVALID; the disasm target prints "invalid"). No decode
path produces the value: the suite is unchanged in outcome by these
two lines (pass 77, xfail 27 after the mints below). The lifter's
`default:` still maps it to NOP, as UNKNOWN is today.

**Comparer.** `compare_operands.py`: class `invalid_at_start` (our
INVALID at a Ghidra START), inserted before the `???` test so it can
never fall into `mnemonic`; excluded from `mnem_ok`. **Prediction 0 on
all 16 inputs** when the differential runs after the fix.

**Reds minted (XFAIL), predicted first failure in brackets, all
observed as predicted:**
- `x64_RED_n_invalid_06_refused`: `06` → INVALID, length 1
  ["instruction: expected INVALID (UNKNOWN today)"].
- `x64_RED_n_invalid_82_mode_split`: `82 C0 10` 64-bit → INVALID, 1;
  32-bit → length 3, not INVALID ["64-bit: instruction: expected
  INVALID"; the 32-bit half is also red today, length 1].
- `x64_RED_n_invalid_walk_continues`: `x86_decode_range` over `06 90`
  → first INVALID length 1, second NOP at offset 1 ["first: expected
  INVALID length 1"]. The second clause is the walker decision: it
  holds today (the range loop already continues past UNKNOWN) and must
  still hold when INVALID exists, so a fix that `break`s on INVALID
  turns this red into a different failure, not a pass.
- `x64_RED_w_pushad_invalid_64`: `60`/`61` → INVALID ["60: expected
  INVALID (PUSHAD today)"].

**Guards written (PASS today):** `x64_GUARD_n_pushf_stays_len1` (`9C`
at `40102d`) and `x64_GUARD_n_popf_stays_len1` (`9D` at `401030`),
expected values from the v11 oracle (PUSHFQ/POPFQ len=1).

**Scratch-fail run** (`fix-n-guard-scratch-2026-09-19.log`): the
default arm temporarily consumed a ModRM after every unknown opcode;
the real file was saved first and restored byte-for-byte (sha256
`b9edaf32…` before and after, suite back to 77/27/0/0).

| predicted | observed |
|---|---|
| both guards FAIL | both FAIL ("length: expected 1") |
| n1 `63 C0` and n4 `D9 00` XPASS | XPASS |
| n2, n3, n5, **n6** stay XFAIL | n2, n3, n5 XFAIL; **n6 `E3 00` XPASS** |
| (u) unaffected | unaffected |
| fixture walk loses starts `40102e`, `401030` | loses `40102e`, `401030`, `401031` **and every later oracle start**: `9C` + fake ModRM `89` (mod=10) pulled a disp32, a 6-byte "instruction" at `40102d`, and the walk never re-synced on the fixture |

**The n6 miss is a defect in the red, repaired the same session:** a
rel8 of `00` and a bare ModRM `00` are both one byte, so the JRCXZ red
could not distinguish the naive fix from the real one (mask blindness:
a red verified only against a fixture sharing its blind spot). It now
also asserts `E3 80` → 2 (rel8 = 0x80; a ModRM-consuming fix reads
mod=10 and returns 6); oracle row `E380` = 2, double-attested. Red
again on the real decoder ("length: expected 2"). The same blindness
does not affect n1/n4 (they are ModRM-only and XPASS under the naive
fix by design, which is what makes the guards the discriminator) nor
n2/n3/n5 (immediates beyond one byte).

Suite after commit 3: pass=77 xfail=27 fail=0 xpass=0 (tests=104).
Remaining before the fix: (r1)-(r3) reds minted from the table rows
`66 68` (4), `66 A9` (4), `66 F7 00` (5), double-attested, so they are
on the list when the sweep's exact set is reduced by hand.

---

# Commit 4 pre-registration, 2026-09-19 (written before any decoder line)

Owner clearance 2026-09-19 with three items pre-registered here.

**Technique extracted (owner):** when two hypotheses agree on a length,
pick the operand that makes them disagree. The JRCXZ red's `E3 80`
clause, the sweep's ModRM `0x80` probe and the legacy `0x67` finding
are the same move.

## 1. The sweep's floors were pinned before INVALID existed

A row is `checked` when the decoder returns anything but UNKNOWN, and
after commit 4 INVALID is such a return, so rows cross from
`tautological` into `checked` and the pinned 1312 / 720 stop naming
the same quantity. Counted from the generated table: the 64-bit table
has **20 INVALID opcodes** (`06 07 0E 16 17 1E 1F 27 2F 37 3F 60 61
82 9A CE D4 D5 D6 EA`), × 4 prefix forms × 2 ModRM = 160 rows, of
which `60`/`61` (16 rows) are already `checked` today (decoded as
PUSHAD/POPAD). The legacy table has **0 INVALID opcodes** after the
correction below.

| mode | checked | tautological | skipped | wrong rows | set |
|---|---|---|---|---|---|
| 64-bit, predicted after commit 4 | **1456** (= 1312 + 160 − 16) | **336** (= 480 − 144) | 256 | **38** (= 54 − 16: A0-A3 × 8, and 68/A9/F7 under `66` × 2) | {68 A0 A1 A2 A3 A9 F7} |
| legacy, predicted after commit 4 | **720, unchanged** | **252, unchanged** | 52 | 6 | {68 A9 F7}, **unchanged** |

Floors re-pinned to 1456 / 720 in the same commit. The sweep's
agreement rule gains INVALID: decoder INVALID on a table-INVALID row
is agreement at length 1; decoder INVALID on a table-VALID row, or a
decoded return on a table-INVALID row, is a disagreement.

## 2. The legacy set does not change, and that is the finding

(v)'s `0x67` case is a unit red; the legacy probes are {none, `66`} ×
{`00`, `80`} and never carry `67`, so nothing in the legacy sweep
moves at commit 4: triple 720 / 252 / 52 and set {68 A9 F7} are
predicted **identical**. The 64-bit shrink is exactly `60`/`61`
leaving.

**Table correction found while counting (before commit 4):** legacy
`D6` had come out INVALID because the instruments disagree in every
form (Ghidra models SALC, objdump refuses), and the fitter had
resolved that silently toward INVALID, which condition 3 forbids. Now:
the fitter **refuses** any opcode where one instrument prints an
instruction and the other nothing in every form, and the spec decides
by a HAND row: legacy `D6` VALID one byte (SALC, undocumented but
implemented; refusing a real encoding is the direction that hurts),
64-bit `EA` INVALID (JMP Ap is i64; Ghidra models JMPF there, objdump
`(bad)`). Both rows carry the note. **Regenerated table diff, read
back:** two substantive changes (legacy `D6` INVALID → VALID; 64-bit
`EA` gains the HAND note, status unchanged) and, because the fitter's
INVALID note text changed from "NONE in every attested form" to "NONE
in every form, both instruments", a note-only change on the other 19
64-bit INVALID rows. Predicted "two rows only"; observed 2 substantive
+ 19 comment-only, the prediction having ignored that the note text
was part of the same edit. Table sha256 `903e2785…` (generator sha in
its header).

## 3. Commit 5's prediction splits two movements

(n) repairs reachability, not a mismatch class. Therefore, outside a
named desync run: **nothing leaves any class but `nostart`**, and two
increases are registered separately:
- **`undecoded` rises**, fed from `nostart`, by the directly fixed
  opcodes: a VALID table row consumes its bytes and stays UNKNOWN by
  design, so every `63`/`69`/`6B`/x87/`C8`/`E3` start that was inside
  a run lands in `undecoded`, not in `operand_ok`. Order of magnitude:
  one per closed run at least (353 (n)-attributable runs, each opened
  by such a trigger; 261 MOVSXD starts exist corpus-wide), plus any
  further (n) opcodes inside those runs.
- **`operand_ok` rises** only from the instructions the desyncs were
  hiding: the rows behind the triggers (the harness's 888 `nostart`
  rows minus the triggers themselves, minus rows behind the 9 TEST, 4
  section-start, 2 INT, 1 PEXTRW and 63 MOV runs, which are not
  predicted to move).
A large `undecoded` rise is therefore the fix working, not a
regression; a modest `operand_ok` rise is the same fix, not one that
underperformed. `invalid_at_start` = 0 on all 16. Standing prediction
ACPI `.text+0x69d4c` `nostart → ok`. Fixture v12 line: matched starts
through `40105d`? No: (o) at `401044` is still a desync source until
(o) lands, so v12 after (n) = the 24 v11-era starts through `401044`
plus... restated exactly: starts through `401042` matched, `401044`
matched at its own start but at length 5, then `401049`.. mid-(o)
rows: `40104d`, `401051`, `401055`, `401059`, `40105d`, `401060`,
`40106a` stay `nostart` behind (o) → **v12 after (n): 24 matched
(through `401044`), 7 `nostart` behind (o), of 31 Ghidra rows
(`40106b` RSM is NONE in the flow-following oracle and not a row)**.
[Arithmetic correction written 2026-09-19 while the differential was
running and before its log was read: a first draft said "25 matched of
32"; the v11 address list through `401044` has 24 entries and 24 + 7 =
31. The correction is on the record so the prediction and the reading
can be compared honestly; a re-sync by chance inside the 7 would count
as a miss, not folded.]

## The fix, as it will be written

The one-byte `default:` arm (and `60`/`61` in 64-bit mode, which route
to it) consults the generated table for the mode (16-bit uses the
legacy table through `op_size`): VALID → consume ModRM/SIB/disp via
`decode_modrm` when the rule has one, then the rule's immediate bytes
(operand-size-16 flag from `op_size`, REX.W from `rex`), instruction
stays UNKNOWN; an INVALID digit or INVALID status → `X86_INS_INVALID`
at length 1 (offset rewound to just past the opcode); PREFIX/ESCAPE →
today's behaviour (UNKNOWN, 1); a truncated immediate → return 0 with
the offset unchanged (the (g) pass state, applied here from the start).
Gate: XPASS on exactly `x64_RED_n_movsxd_length`, `_imul_imm32_length`,
`_imul_imm8_length`, `_x87_modrm_length`, `_enter_length`,
`_jrcxz_length`, `_invalid_06_refused`, `_invalid_82_mode_split`,
`_invalid_walk_continues`, `x64_RED_w_pushad_invalid_64` (10 names);
guards PASS; (r1)-(r3), (o), (p), (s), (u), (v), (a), (d'), (f), (g)
stay XFAIL; sweeps as in item 1. Predicted suite after the gate
clears: pass=87 xfail=20 fail=0 xpass=0 (tests=107).

---

# Commit 4 as built, 2026-09-19: the (n) fix

**The change.** `x86_decoder.c`: `table_default_arm()` (included
`x86_opcode_len.h`); the one-byte `default:` arm and `60`/`61` in
64-bit mode route through it. VALID: ModRM/SIB/disp via `decode_modrm`
when the rule has one, then the rule's immediate bytes (operand-size-16
from `op_size`, REX.W from `rex`); instruction stays UNKNOWN. INVALID
status or INVALID digit: `X86_INS_INVALID`, nothing after the opcode
(length = prefixes + 1; the reds use no prefixes). PREFIX/ESCAPE:
unchanged. Truncated immediate: return 0, offset rewound.

**Gate (`fix-n-xpass-gate-2026-09-19.log`), predicted = observed:**
XPASS on exactly the ten names, every other XFAIL held (20), guards
PASS, `pass=77 xfail=20 fail=0 xpass=10`; names removed by hand →
`pass=87 xfail=20 fail=0 xpass=0 (tests=107)`.

**Sweeps, predicted = observed:** 64-bit checked 1456, tautological
336, skipped 256, wrong rows 38, set {68 A0 A1 A2 A3 A9 F7}; legacy
720 / 252 / 52 / 6, set {68 A9 F7} unchanged. Floors re-pinned 1456 /
720.

**Full translator suite: one red, read from bytes, attributed, and it
is the fix working.** `rtl8139_hw_function_count` (Linux ELF driver
validation) expected ≥ 1 hardware function on 8139too.ko and got 0;
the pre-fix decoder (private 79189c2) gives 1. The one function's
evidence was two OUT decodes at `.text+1eb1` and `.text+1ef6`, both
**inside** a Ghidra MOVSXD (`+1eaf` and `+1ef4`), i.e. NO START: a
desync artefact of the usbxhci 2026-09-14 INS/OUTS shape. Named run:
first missed start `+1eb2`, trigger `+1eaf MOVSXD R12,R14D` (opcode
`63`, pre-fix length 2, post-fix 3), owning defect (n). Post-fix the
module's missed starts fall 11 → 4 of 4026 and the artefact is gone.
8139too is an MMIO driver; 0 port-I/O functions is the correct answer.
The expectation was corrected to `== 0` with the run written beside it
(rule 24: the readers of that field for this module are this test and
`rtl8139_named_function`, which passes either way). Same shape on
ne2k-pci: one OUTSB at `.text+59b` inside a MOVSXD at `+599` left
(port rows 71 → 70; the `≥ 10` expectation holds on the 70 real ones,
every one a Ghidra START); iTCO_wdt 33 → 33, all at starts. Module
missed starts: ne2k-pci 13 → 0, iTCO_wdt 8 → 0, via-rng 0 → 0. The
one INVALID row on 8139too (`.text+2721`) is not a Ghidra start:
`invalid_at_start` = 0 there, as predicted.

**Table correction in the same commit:** legacy `D6` VALID by hand
(SALC), 64-bit `EA` HAND note; the fitter now refuses an opcode where
the instruments disagree in every form.

Suite after commit 4 (full `make test`, read back): exit 0, every
suite passes (CIL 14/14, CIL semantic 6/6, ARM64 21/21, UIR 22/22,
semantic 37/37, call-graph 8/8, codegen 13/13, pipeline 5/5, 16550
6/6, Ghidra compare 4/4, i8042 7/7, serial 11/11, floppy 8/8, pci
7/7, beep 7/7, ELF drivers 12/12, and the rest at their full counts);
test-x86 `pass=87 xfail=20 fail=0 xpass=0 (tests=107)`. Decoder sha256
`efeaea0e…`, table `4dd9038c…`.

---

# Commit 5 as run, 2026-09-19: the differential, three misses, one stop

`operand-diff-fix-n-2026-09-19.log` (16 inputs, alias hash
`02101788edd2` unchanged; baseline `operand-diff-fix-e-2026-09-18.log`).

## What moved, against the registered split

| input | Ghidra | nostart b→n | operand_ok b→n | undecoded b→n | invalid_at_start |
|---|---|---|---|---|---|
| ACPI | 148921 | 191 → **36** | 122231 → 122373 | 988 → 989 | 0 |
| disk | 12335 | 11 → 1 | 10081 → 10089 | 55 → 55 | 0 |
| HDAudBus | 24214 | 50 → 1 | 18694 → 18740 | 88 → 88 | 0 |
| i8042prt | 19090 | 8 → 2 | 14373 → 14378 | 19 → 19 | 0 |
| pci | 86827 | 49 → 14 | 73087 → 73117 | 370 → 371 | 0 |
| serial (HP) | 13852 | 32 → 21 | 11609 → 11620 | 21 → 21 | 0 |
| storport | 98228 | 192 → 93 | 85041 → 85130 | 425 → 427 | 0 |
| usbxhci | 89234 | 177 → **2** | 72503 → 72658 | 588 → 588 | 0 |
| ne2k-pci | 1193 | 13 → 0 | 889 → 897 | 10 → 11 | 0 |
| 8139too | 4026 | 11 → 4 | 2758 → 2762 | 12 → 12 | 0 |
| iTCO_wdt | 907 | 8 → 0 | 690 → 696 | 2 → 2 | 0 |
| via-rng | 176 | 0 → 0 | 126 → 126 | 0 → 0 | 0 |
| ReactOS serial | 4220 | 0 → 0 | 4215 → 4215 | 1 → 1 | 0 |
| ReactOS beep | 447 | 0 → 0 | 447 → 447 | 0 → 0 | 0 |
| nmap (32-bit) | 8299 | 145 → 3 | 7885 → 7962 | 192 → 237 | **19** |
| fixture v12 | 31 | 8 → 6 | 11 → 12 | 1 → 8 | 0 |

`nostart` fell on every 64-bit input and on nmap; no class other than
`nostart` decreased on any input by totals; the two ReactOS controls
are identical to the baseline; `operand_ok` rose everywhere it could.
**Standing prediction confirmed:** ACPI `.text+0x69d4c` decodes as
`MOV RAX,[RBX+0x58]` length 4, matching Ghidra (no mismatch row; the
post-fix dump row read directly), and `+0x69d3d` is `undecoded` as
predicted.

## Three misses, each read from bytes

1. **`undecoded` barely rose (ACPI +1, pci +1, storport +2).** The
   commit-5 pre-registration predicted a rise of "one per closed run
   at least (353)". Wrong: the run *trigger* was already a matched
   start classed `undecoded` before the fix (the fixture's own v10
   outcome said so for `63 C0`); only the rows behind it were
   `nostart`. The 09-18 section had the right form ("by the count of
   (n) starts previously *inside* a run"), and the commit-5 text
   overstated it. Direction right, magnitude wrong; recorded.
2. **Fixture: 6 `nostart`, not 7.** A re-sync by chance, pre-stated
   as a miss: the desynced walk after (o) landed on `+55` (`0F C4 C0
   00` PINSRW), which the `0F` arm returns as NOP (class `mnemonic`).
   The other six rows behind (o) are `nostart` as predicted; 24
   matched through `+44`.
3. **`invalid_at_start` = 19 on nmap, predicted 0. This is the stop
   condition.** All 19 are x87 *register* forms: 13 FXCH (`D9 C8+i`),
   5 FCOMI (`DB F0+i`), 1 FNINIT (`DB E3`). Mechanism, read from the
   table and the bytes: the generator's digit probes were memory
   forms (mod=00), so `D9 /1`, `DB /4`, `DB /6` (and `DD /5`) came
   out INVALID because their *memory* forms are invalid, and the new
   default arm applies the digit rule regardless of mod, refusing
   valid register forms. Bytes: 20 such encodings in the corpus (13 +
   1 + 6 on nmap, `DD /5` 0; control 119 x87 register forms, 250 x87
   in all), 19 at attested starts. Walk behaviour at those rows is
   unchanged (length 1, as UNKNOWN was), so no new desync; the
   regression is the label: 19 rows **left `undecoded`** for
   `invalid_at_start`, which the totals masked (nmap `undecoded` rose
   45 net) and the per-row read found. A table that refuses a real
   encoding is the direction that hurts. Named **(x)**: digit validity
   is per mod class; owned by the generator (probe set) and the
   schema (one digit array), not by the decoder line.

**Corrective (x), pre-registered, not yet written.** A first draft
proposed seven register-form digit probes at `rm=000` and was refused
at the gate (owner, 2026-09-19): in the x87 register space the `rm`
bits are opcode (`D9 C8+i` FXCH ST(i); `DB E0`-`E4` five different
instructions, so `rm=000` reaches `DB E0`, not the `DB E3` FNINIT the
prediction named; `D9 D0` FNOP, `D9 D1`-`D7` undefined), a rule fitted
from 7 of 64 cells reproduces every cell it saw and the refusal check
has nothing to bite on, and `range(1, 8)` left digit 0 (`D8 C0` FADD
ST(0),ST(0)) unsampled by either probe set. As redesigned: the blob
(`--v2`) samples **all 64 register-form cells** `C0`-`FF` per opcode
with no prefix; the x87 register space `D8`-`DF` mod=11 is a **HAND
rule with its citation** (SDM Vol. 2A 3.1.1.3 / Vol. 2D Table A-2:
opcode + ModRM, length 2, always) that the probes confirm rather than
derive, lenient on undefined cells (a VALID length-2 on an undefined
sub-opcode walks correctly; an INVALID on a real instruction is (x)
itself); the fitter emits `digit[8]` for memory forms and
`digit_reg[8]` for register forms, with register-form validity per
digit taken as "any `rm` cell valid" and a refusal when the valid cells
of one digit disagree on length; the arm selects by `mod == 3`.

**Standing check, fourth instance of one class** (ModRM `00`-only hid
`has_modrm`; `C0`-only hid the memory forms; `E3 00` hid the JRCXZ
discrimination; `rm=000` hid the x87 opcode bits): **before running a
probe set, name the field it holds constant and say why that field
cannot carry information.** Written into the generator's header where
the next probe set gets written, and into the v2 oracle log headers.

**(n) does not close while (x) is open.** A fix whose own new instrument
measures a regression it introduced is not finished.
Reds from the nmap oracle rows (double-attested with objdump): `D9 C9`
FXCH 2, `DB E3` FNINIT 2, `DB F1` FCOMI 2, each asserting not INVALID
(red today: INVALID). Predicted movement: nmap `invalid_at_start` 19 →
0, those 19 rows back to `undecoded`, nothing else moves on any input;
the 64-bit sweep's `checked`/`tautological` unchanged (register-form
probes are not sweep forms). The (n) closing waits on (x).

## The rtl8139 expectation, answered

It was corrected to `== 0`, which coincides with the post-fix number,
and the owner's objection stands: a number this run produced is not a
basis. The defensible basis exists: Ghidra's own port-instruction
count on the banked per-instruction file is **0** for 8139too (and 0
via-rng, 70 ne2k-pci, 33 iTCO_wdt), and post-fix ours equal those
with every row at a Ghidra start. The suite cannot read the Ghidra
files (untracked build products), so the treatment per the 09-18
ruling: the function-level floors (`≥ 10` ne2k, `≥ 5` iTCO, `≥ 1`
rtl8139) are **suspended** under the condition the x86 XFAIL list is
empty, with the reason recorded at each; the two zeros are kept as
assertions against Ghidra's count (0 port instructions on those
inputs) and say so. The report's instruction-level `port_operations`
key is the field a future Ghidra-backed assertion would use.

## The four residual missed starts on rtl8139

One run: trigger `.text+271b TEST AX,0xc07f` (`66 A9 7F C0`, Ghidra
4, ours 6), missed `+271f +2725 +2728 +272c`, the INVALID row `+2721`
inside it. That is **(r2)** by name, and its one corpus instance;
(r2)'s red now carries the offset and the predicted movement (4 rows).

## (x) build pre-registration, 2026-09-19 (v2 oracle read, before any table or decoder line)

[A first append of this section was approved at the gate but never
reached the file: the shell's working directory had moved and the
redirect failed before the "appended" echo ran. Written by absolute
path now, read back with a count, with the owner's `C4` correction,
the rerun ruling, and the legacy sweep prediction that the `C4`
correction changes, all folded in.]

**v2 oracle runs read back against their headers** (`x64-one-byte-
oplen-oracle-v2-2026-09-19.log`, `x86-32-…-v2-…`; the first launch
had no blob because the generator took `--v2` as its output path,
noted in the headers, relaunched): rows 1-3840 / 1-2816 identical to
v1 in both modes; x87 register space `D8`-`DF` × `C0`-`FF`: 512 cells,
**356 defined at length 2 with 0 exceptions**, 156 undefined NONE
(`D9 D1`-`DF`, `D9 E2 E3 E6 E7 EF`, `DA E0`-`E8`, …), so the cited
hand rule is *confirmed* by every defined cell, not derived; `D9 C8+i`
FXCH, `DB E3` FNINIT, `DB F1` FCOMI, `DD E8+i` FUCOMP, `D8 C0` FADD all
2; `8F` register `/0` POP 2 and `/1`-`/7` NONE; `FF /7` NONE; `C6 F8`
XABORT 3 and `C7 F8` XBEGIN 6 (modeled); `F6`/`F7 /0 /1` TEST 3 / 6,
other digits 2; legacy `D4`/`D5` 2 on every cell (no ModRM).

**Legacy `C4`, `C5`, `62` register forms are ESCAPE by hand, all three
(owner correction).** `C5 C0 90…` probed as KMOVW 8 and `C4 C0 90 90`
probed NONE, but both readings are accidents of the `0x90` payload
(one a valid VEX2 body, the other an invalid VEX3 body): in 32-bit
mode `C4`/`C5` with mod=11 are the VEX3/VEX2 escapes and `62` the
EVEX escape (SDM Vol. 2A 2.3.5, 2.7), and `C4` is the form modern AVX
uses. Fitted from the probe, `C4`'s eight register cells would go
INVALID and refuse real code. `OPT_IMM_ESCAPE` on `digit_reg` means
"stop after the opcode, UNKNOWN": today's behaviour, the (q) gap, not
a length claim.

**Table schema:** entries gain `digit_reg[8]`; `opt_length` and the
arm select `digit_reg` when `mod == 3`. Fitter: x87 register space by
HAND (SDM Vol. 2A 3.1.1.3 and Vol. 2D Table A-2: opcode + ModRM,
length 2, lenient on undefined cells), confirmed against all 356
defined cells, refusing if any defined cell is not 2; every other
ModRM opcode's `digit_reg[d]` fitted from its 8 `rm` cells:
NONE/IB/IW/IZ from the double-attested length, INVALID only if all 8
cells are NONE in both instruments, ESCAPE by hand as above, refusal
if the attested cells of one digit disagree on length. Predicted
refusals: 0; suspects: `C6`/`C7` (digit 7 immediates), `8F`.

**Sweep gains a register-form probe (ModRM `C0`)** so `digit_reg` is
asserted, not just carried; a `mod == 3` row whose `digit_reg` is
ESCAPE is skipped with the reason counted. Prediction, recomputed
from the skip rule and the hand list: a prefix-form × opcode row's
decoded/UNKNOWN status is the same at `C0` as at `00`/`80` **except
the legacy `C4`/`C5`/`62` rows** (tautological at `00`/`80`: the
decoder returns UNKNOWN on LES/LDS/BOUND; ESCAPE, hence skipped, at
`C0`): 3 opcodes × 2 legacy prefix forms = **6 rows move from
tautological to skipped beyond the half**. 64-bit: checked 1456 →
**2184**, tautological 336 → **504**, skipped 256 → **384** (those
three are ESCAPE at every 64-bit form already). Legacy: checked 720 →
**1080**, tautological 252 → **372** (378 − 6), skipped 52 → **84** (78
+ 6). Disagreeing sets **unchanged** {68 A0 A1 A2 A3 A9 F7} / {68 A9
F7}. Any deviation is read from the row. Floors re-pinned to 2184 /
1080.

**Count reconciled from the artefacts:** by bytes over nmap, **20
encodings** (13 `D9 C8+i` FXCH, 1 `DB E3` FNINIT, 6 `DB F0+i` FCOMI);
by the comparer, **19 `invalid_at_start` rows**. The twentieth is
`DB F2` FCOMI at `.text+5720`: a Ghidra start our walk never reaches
(a `nostart` row inside a preceding desync), so it cannot be classed
`invalid_at_start` today and will be read again after (x).

**Reds** (each test owns its own FAIL/PASS; a shared helper only
returns a status): `x64_RED_x_fxch_register_form` (`D9 C9` 2),
`_fninit_register_form` (`DB E3` 2), `_fcomi_register_form` (`DB F1`
2), each asserted in **both** modes (the table is per mode, so
"mode-independent" is a claim only a 64-bit assertion tests; expected
values: nmap Ghidra starts for 32-bit, blob-v2 rows for 64-bit,
objdump agreeing on both); `x64_GUARD_x_fadd_st0_register_form` (`D8
C0` 2, digit 0 register form, unsampled by either v1 probe set, not
refused today: a guard, off the XFAIL list). Predicted first failures
of the three reds: "refused (INVALID)".

**Ruling on the rerun: the full sixteen.** Prediction: nmap
`invalid_at_start` 19 → 0 and those rows back to `undecoded` (237 →
256); **every other column of every other input identical to
`operand-diff-fix-n-2026-09-19.log`**; the fixture line identical. A
partial rerun would leave the load-bearing half of that prediction
unfalsifiable and the corpus table with two provenances.

## (x) as built, 2026-09-19

**Instrument, read back.** The v2 objdump screens were rebuilt to
derive their join key from the blob through the parser's own
`probe_key` (shared function; `--insn-width=16` is in the argv and the
argv is printed in the header), and the parser now **refuses a join
whose key set differs from the blob's.** That assertion fired on its
first run, on the v1 artefacts: the parser's key rule special-cased
`0x0F` for every layout (right for the two-byte blob, wrong for the
one-byte ones), so the 15 (64-bit) and 11 (legacy) opcode-`0F` rows of
the v1 tables had joined nothing and carried a vacuous NONE in the
objdump column. Regenerated; the diff is exactly those rows, the only
change the filled objdump cell (`0F` is a hand ESCAPE row, so no fit or
assertion depended on them). The v2 tables: 20224 and 19200 rows, full
key sets, 17371 double-attested in 64-bit.

**Fitter, predicted 0 refusals, observed 6, then 6, then 0.** First v2
fit: `8C /6`, `8E /6`, `8F /1` register forms in both modes,
"instruments disagree on every rm cell" (objdump prints a segment move
for the reserved sreg field, Ghidra nothing; for `8F` with reg≠0
objdump models AMD's XOP escape at 9 bytes). Second fit, after
hand-rowing those three: the same class one digit over (`8C /7`, `8E
/7`, `8F /5`). Third fit, after the reserved space was hand-rowed as a
set: 0. Hand rows, cited: `8C`/`8E` sreg fields 6 and 7 INVALID (SDM
Vol. 2A MOV: reserved, #UD); `8F /1`-`/7` register ESCAPE (POP r/m is
`/0` only on Intel, #UD; the bytes are AMD XOP, and refusing them is
the direction that hurts); legacy `C4`/`C5`/`62` register ESCAPE (owner
correction); x87 register space HAND, confirmed on all 356 defined
cells. The suspects list named `8F` and missed `8C`/`8E`: a miss.

**Gate (`fix-x-xpass-gate-2026-09-19.log`):** XPASS on exactly the
three (x) names; `x64_GUARD_x_fadd_st0_register_form` PASS; every
other XFAIL held. **Sweep counts, predicted = observed on all six:**
64-bit 2184 / 504 / 384, legacy 1080 / 372 / 84 (the six legacy
`C4`/`C5`/`62` rows exactly where the correction put them).

**Sweep sets, predicted unchanged, observed one new member in each
mode: a miss, read from the row.** `8D` at the `C0` form: `LEA` with a
register-form ModRM is #UD in every mode (SDM Vol. 2A LEA: the source
must be a memory operand; both instruments print nothing on `8D C0`),
the table says INVALID on every register cell, and the decoder's LEA
arm accepts it at length 2. Named **(y)**, red
`x64_RED_y_lea_register_form_invalid` minted (both modes), `8D` added
to both sets as an amended member (7 → 8, 3 → 4, recorded as failed
predictions). Corpus by bytes: 0 register-form LEAs among 39,243 LEA
instructions across the 16 inputs (control RET 6458). Suite after the
gate and the removal of the three names: pass=91 xfail=21 fail=0
xpass=0 (tests=112).

**Rerun: the full sixteen (owner ruling), prediction unchanged:** nmap
`invalid_at_start` 19 → 0, those rows to `undecoded` (237 → 256), the
`DB F2` at `.text+5720` read again; every other column of every other
input identical to `operand-diff-fix-n-2026-09-19.log`; fixture line
identical. Read back below.

## Rerun after (x), read back: (n) + (x) closing matrix

`operand-diff-fix-x-2026-09-19.log`, 16 inputs, alias hash unchanged.
**Fifteen inputs identical to `operand-diff-fix-n-2026-09-19.log` in
every column** (the load-bearing half of the prediction, tested by
running it). nmap, predicted vs observed:

| column | predicted | observed |
|---|---|---|
| invalid_at_start | 19 → 0 | **19 → 0** |
| undecoded | 237 → 256 | 237 → **257** |
| nostart | 3 → 3 | 3 → **0** |
| operand_ok | unchanged | 7962 → **7964** |

**One miss, read from the rows.** I had written that the walk
behaviour at the 19 rows was unchanged by (x) ("length 1, as UNKNOWN
was") so nothing else on nmap would move. Wrong: before (x) those
register forms were length 1 and desynced the walk behind them; after
(x) they are length 2, which is a *repair of reachability*, and the
three rows behind them closed: the twentieth FCOMI, `DB F2` at
`.text+5720`, is now a matched start classed `undecoded` (the +1 on
257), and two further rows returned to `operand_ok`. Direction right,
the mechanism I had pre-registered for (n) itself, and I failed to
apply it to (x). Recorded.

**(n) and (x) close together.** The (n) fix: unknown one-byte opcodes
consume the rule table's bytes; INVALID exists and the walker
continues; the sweep asserts the decoder against a generated table in
both modes with an exact disagreeing set; `invalid_at_start` = 0 on all
16. Missed starts across the corpus, before (n) → after (x): ACPI 191
→ 36, usbxhci 177 → 2, storport 192 → 93, pci 49 → 14, nmap 145 → 0,
the four modules 13/11/8/0 → 0/4/0/0, controls unchanged. The 4 on
8139too are (r2); the 36 on ACPI and the rest are the next reading.

Open after this: (o), (p)×2, (r1)-(r3), (s)×7, (u), (v), (y), (a),
(d'), (f), (g)×2. Suite pass=91 xfail=21 fail=0 xpass=0 (tests=112).

## Next reading (owner redirection: storport, not ACPI), 2026-09-19

**Correction to the headline first.** "786 → 149" was summed from the
eight rows my closing table showed; the table omitted disk (1),
HDAudBus (1), i8042prt (2), HP serial (21) and the fixture (6). Over
all sixteen harness inputs the residual after (x) is **180** missed
starts, and the fix-(e) baseline was **895**. Both figures are from
the OPSUMMARY lines; the partial pair is not wrong on its eight rows,
but it is not the corpus.

**Storport's 93, by run trigger** (same instrument that named (r2) on
rtl8139): 31 runs. 28 runs / 74 rows triggered by `MOV RAX,[0xfffff780
00000xxx]` (and one `MOV AL,[…]`): `48 A1 imm64`, Ghidra 10, ours 6.
That is **(o)** by name, and the addresses are KUSER_SHARED_DATA
(InterruptTime `+08`, SystemTime `+14`, `+320`), which storport reads
constantly and the other drivers rarely: the reason its ratio was out
of family. The rest: one `INT 0x29` run of 17 rows in INIT (a flow
terminator, `__fastfail`; not a length defect; the same run shape
gives HP serial its 17), one (r3) row, one (s) row.

**The whole residual, apportioned** (harness-comparable sections only;
the modules' 221 "section start" rows are the known non-harness
sections):

| defect | rows | runs | inputs |
|---|---|---|---|
| (o) moffs64 | **129** | 64 | ACPI 35, storport 74, pci 13, serial 3, i8042 1, usbxhci 1, fixture 2 |
| INT 0x29 flow | 34 | 2 | serial 17, storport 17 |
| (r3) `66 F7 /0` | 8 | 8 | one per HP driver |
| (s) `0F C4`/`C5` | 5 | 2 | storport 1, fixture 4 |
| (r2) `66 A9` | 4 | 1 | 8139too |
| total | 180 | 77 | |

**Cross-check by bytes (rule 25):** moffs encodings `A0`-`A3` in the
64-bit inputs = 63 (ACPI 22, storport 28, pci 9, serial 2, i8042 1,
usbxhci 1; modules 0; control RET 6310) + the fixture's 1 = **64 =
the number of (o) runs exactly**: every moffs instruction in the
corpus is a run trigger today. (r3) by bytes 8 = 8 runs, one per HP
driver. (r2) by bytes 1 = 1 run.

**Pre-registered for the (o) fix, written before it:** residual 180 →
**51** (129 rows leave `nostart`; the INT 34, (r3) 8, (s) 5, (r2) 4
stay); by input ACPI 36 → 1, storport 93 → 19, pci 14 → 1, serial 21 →
18, i8042 2 → 1, usbxhci 2 → 1, fixture 6 → 4; the `undecoded` column
does not move for (o) (the trigger is already a decoded MOV: `addr`
class) and the rows behind the triggers feed `operand_ok` and the
mismatch classes; the (o) row itself moves `addr → ok` on every
input (64 rows). The mechanism restated for (o) here so it travels
(refinement of 2026-09-19): a length repair moves the rows *behind*
the trigger, and the trigger's own class is a separate movement.
(o) is a `disp` widening: rule 24, readers of `disp` enumerated
before a line changes.

## Corrections to the reading (owner, 2026-09-19): the 51 split, the INT rows read

**Twenty-sixth rule, docketed:** a table inside a summary is a
selection until its row count matches the pinned population; count
the rows before summing them. The 786 → 149 was an eight-row sum
published as a sixteen-input figure; 895 → 180 is the number.

**180 → 51 = 34 parked + 17 owned.** The 34 `INT 0x29` rows are not a
decoder row and no red owns them, so they are parked with the
modules' 221 section-start rows on the same reasoning, read from the
artefacts on both drivers: Ghidra's INIT block is the section's
`SizeOfRawData` (serial 0x800, storport 0x200) and ours is its
`VirtualSize` (0x6b2, 0x72); Ghidra falls through `INT 0x29`
(`__fastfail`, which it does not model as terminating) into the
file-alignment zero padding and prints 17 `ADD byte ptr [RAX],AL`
rows (`00 00`) on each driver, every one at an offset past our last
byte (`+6b2`, `+72`). The mechanism is a **loader population
difference** (the PE loader carries the virtual extent, the oracle the
raw extent), the row class is padding, and it will not move for any
fix on the list; whether the harness should trim both sides to
`min(VirtualSize, SizeOfRawData)` is a harness question, filed, not a
decoder one. The 17 owned rows: (r3) 8, (s) 5, (r2) 4, each with a red
on the list. A future reading that sees a floor of 34 is reading the
padding, not a failure to close.

**(o), cleared on the usual terms. Readers of `x86_operand_t.disp`
(`int32_t`, `include/x86_decoder.h:162`), enumerated from source
before a line changes (rule 24):**
- copies across the bridge: `src/main/translator.c:150`,
  `tests/test_pipeline.c:185,283` (field-for-field into
  `uir_x86_input_t`, whose `disp` must widen with it), `src/ir/uir.c:127`
  (into the UIR operand, whose `disp` type is the next reader to
  enumerate);
- **one truncating reader: `src/ir/semantic.c:359`**, `call_target =
  (uint64_t)(uint32_t)ins->dest.disp`, the IAT-call resolver, which
  today folds a widened displacement back to 32 bits; the (a)
  RIP-relative fix already named the same site;
- readers that mask: `src/ir/uir.c:630,634` (port / struct
  displacement from the previous MOV, `uint16_t` mask and
  `struct_disp`), unaffected by width;
- printers: `src/ir/uir.c:723` (`%+d`, must become a 64-bit format),
  `tests/dump_starts.c:67,73,80` (already cast to `int64_t`),
  `x86_print_decoded` in the decoder;
- writers from `imm`: `src/ir/uir.c:971-1006` (`(int32_t)` casts of
  an immediate into `disp`: unchanged in meaning, casts to revisit);
- test fixtures that set or assert `disp`: `test_x86_decoder.c:422,
  435,530,740,1102`, `test_semantic.c:270,335,415,421`,
  `test_callgraph.c:72`.
The widening is `int32_t → int64_t` on `x86_operand_t.disp` and on the
bridge and UIR operand fields that copy it; every reader above is
touched or explicitly left; the `-Wtype-limits` warning at the (o)
red retires in the same commit. Pre-registered movement (previous
section): residual 180 → 51, (o) rows `addr → ok` on 64 rows, nothing
leaves any class but `nostart` and `addr`. The (o) red's expected
value: fixture v12 `401044` `MOV EAX,[0x1122334455667788]` length 9.

## The 17/17, read; the resolver, ruled (owner, 2026-09-19)

**17 on both drivers did not follow from the padding** (334 and 398
bytes would be 167 and 199 two-byte rows), and I had written it as if
it did. Read: no cap exists in the comparer, the dump tool or the
Ghidra dump script. Measured directly: a synthetic ELF with `INT
0x29` followed by 400 zero bytes gives **exactly 17 `ADD [RAX],AL`
rows** from Ghidra (flow-following analysis, the differential's own
script), the same 17 as on both drivers. The cap is the oracle's (a
run of identical instructions is cut at a fixed count, whatever the
padding's length; the option's name is not pinned here and does not
need to be: the number is measured). So the **34 parked rows are the
number of padding rows the oracle chooses to print, an oracle
artefact, not the padding**; 180 is the oracle's residual on its own
terms, the parked 34 will read 34 on every future run for the same
reason, and none of it is ours.

**`semantic.c:359`, ruled and minted.** The resolver takes any
memory-indirect call with no base and no index as an IAT site,
records an IAT edge unconditionally, and only then cross-references
imports, so an unmatched target still yields an edge: no refusal path
(nineteenth rule). Ruling: under (o) the site **keeps 32-bit
behaviour** (only moffs rows move; silent widening there would be an
unpredicted behavioural change to the IAT path), but not as a bare
cast: it asserts its input is a 32-bit IAT-slot site and refuses
otherwise; the decision to widen belongs to (a), which owns the site.
Red today, in the semantic suite (which now carries the same
XFAIL/XPASS discipline as the decoder suite):
`sem_RED_a_iat_resolver_refuses_non_iat_target` (a `call [abs]` whose
target matches no import must record no IAT edge; predicted first
failure "IAT edge recorded for a target that matches no import"). A
second red, for a widened `disp` that does not fit 32 bits, cannot be
expressed until the field widens and is minted in the (o) commit with
the refusal.

**Printer.** `uir.c:723` (`%+d`) widens in the same commit as the
field: a narrow format on a wide field truncates the record, which is
how a wrong number outlives its defect.

## Parked by rule; the resolver counted; (o) held (owner, 2026-09-19)

**Parked by rule, not by number.** The comparer gained the class
`beyond_extent`: a Ghidra start at an offset ≥ our block's size for
that section is a byte our loader never had (PE `VirtualSize` versus
`SizeOfRawData` padding) and is classed on its own, never `nostart`.
The figure now self-corrects under any oracle or pin change, like the
join key derived from the blob. Re-compared over the same banked
post-(x) dumps (no decoder change, no new Ghidra run;
`operand-diff-fix-x-reclass-2026-09-19.log`, prediction in its
header): HP serial `nostart` 21 → 4 with `beyond_extent` 17, storport
93 → 76 with 17, **every other column of every other input
identical**; residual now reads **146 owned + 34 by rule**. The 34 is
not a constant anyone carries; it is whatever the oracle prints past
our extent on the day.

**The resolver, counted by bytes across the corpus before any fix.**
Two instruments: objdump's memory-indirect CALLs with objdump's own
resolved targets against each image's IAT directory, and the report's
`summary.call_graph` block (built 2026-09-17 for this question,
`iat-xref-prereg-2026-09-17.md`, which measured one driver and derived
the rest).

| input | mem-indirect CALLs (bytes) | targets in IAT | IAT edges (report) | matched | unmatched |
|---|---|---|---|---|---|
| ACPI | 3724 | 3307 | 3724 | 0 | 3724 |
| HDAudBus | 713 | 391 | 713 | 0 | 713 |
| disk | 383 | 346 | 383 | 0 | 383 |
| i8042prt | 525 | 457 | 525 | 0 | 525 |
| pci | 2691 | 2423 | 2691 | 0 | 2691 |
| HP serial | 476 | 465 | 476 | 0 | 476 |
| storport | 2179 | 2031 | 2178 | 0 | 2178 |
| usbxhci | 2199 | 1294 | 2199 | 0 | 2199 |
| ReactOS serial (PE32) | 275 | 275 | 275 | 245 | 30 |
| ReactOS beep (PE32) | 43 | 43 | 43 | 28 | 15 |
| nmap (PE32) | 45 | 44 | 45 | 0 | 45 |
| total (11 of 11 PE inputs) | 13253 | 11076 | 13252 | 273 | 12979 |

**Reading.** On every 64-bit driver the resolver records an IAT edge
for every memory-indirect call (13,252 corpus-wide) and matches
**zero**, while by bytes 11,076 of those calls do target an IAT slot.
The mechanism is the one the 09-17 record named and measured on
i8042prt (523 edges, 0 slot hits: the raw disp32 of a RIP-relative
`FF 15` is compared as an absolute address against slots above 4
GiB): (a). On the 32-bit controls the mechanism works (245/275,
28/43; the unmatched there are imports outside the classifier's
vocabulary, as the 09-17 record found for nmap). So on the corpus the
semantic layer's IAT classification has been **100% false-negative on
64-bit inputs since it was written**, and its call graph carries
12,979 edges no import backs, with no refusal path. The 09-17 record
also settles the worse case: no confident wrong name is attributed
(every 64-bit target is below the slot range), so this is noise and
blindness, not misattribution.

**This is larger than (o), and (o) is held.** Under the owner's
instruction the widening does not start; the finding goes up for
re-ordering. The repair is the one the 09-17 record pre-registered
for (a): accept the RIP marker and resolve the target as instruction
address + length + disp; plus the refusal path minted today
(`sem_RED_a_iat_resolver_refuses_non_iat_target`). Predicted movement
for (a) on this table: matched on the 64-bit drivers rises from 0
toward the "targets in IAT" column (11,076 corpus-wide, less
classifier-vocabulary misses), and unmatched falls to the "not in
IAT" column (2,177: ACPI 417, usbxhci 905, …), which is then the
number the refusal path must account for, by bytes, before it is
called noise.

## The nmap zero explained, the 2,177 accounted, (a) scoped (2026-09-20)

**The nmap 0-of-45 is my table's error, not a second mechanism.** The
report carries two numbers the 09-17 record separated on purpose, and
I quoted one under the other's name:

| input | IAT edges | **slot hits** | classified | min slot | max target |
|---|---|---|---|---|---|
| ACPI | 3724 | **0** | 0 | 0x1C008C000 | 0xFFFFD336 |
| HDAudBus | 713 | **0** | 0 | 0x1C001A000 | 0xFFFFF23F |
| disk | 383 | **0** | 0 | 0x1C000A000 | 0xFFFFF141 |
| i8042prt | 525 | **0** | 0 | 0x1C0011000 | 0xFFFFF2A5 |
| pci | 2691 | **0** | 0 | 0x1C003A000 | 0xFFFFD6BA |
| HP serial | 476 | **0** | 0 | 0x1C000B000 | 0xFFFFF165 |
| storport | 2178 | **0** | 0 | 0x1C006E000 | 0xFFFFD1AF |
| usbxhci | 2199 | **0** | 0 | 0x1C0068000 | 0xFFFFD307 |
| ReactOS serial | 275 | **275** | 245 | 0x19100 | 0x191B4 |
| ReactOS beep | 43 | **43** | 28 | 0x140A0 | 0x140FC |
| nmap | 45 | **44** | 0 | 0x40E18C | 0x40E254 |

The cross-reference works on **every** 32-bit input: 362 slot hits of
363 calls. nmap's 0 is the *classifier's vocabulary*: it imports
ADVAPI32, KERNEL32, msvcrt and libssp (user-mode Win32 and CRT), and
the classifier's table is Windows *driver* APIs. The 09-17 record had
already found and named this on the same control, and had corrected
its own first revision for exactly this conflation ("counted only
CLASSIFIED matches and read 0 on the nmap control although its targets
lay inside its IAT range"). The fix did not travel to my reading of
the same instrument three days later. Corrected here: **the 64-bit
failure is at slot equality (a); the 32-bit gaps are classification
vocabulary, a separate question that (a) does not repair and must not
be credited with.**

**The 2,177 "not in IAT", accounted by bytes.** First, the instrument:
the IAT *data directory* is a summary field, so the slots were
re-derived from the import descriptors themselves (every FirstThunk
array walked to its null terminator) and targets tested for exact slot
equality. Same answer, 11,076 of 13,253, which retires the worry that
the directory understated the thunks. Then the remainder, read:

- **2,176 are Control Flow Guard dispatch calls.** On each 64-bit
  driver every non-slot target is *one distinct address*, and that
  address is exactly the load-config directory's
  `__guard_dispatch_icall_fptr` cell (offset 0x78): ACPI
  `0x1C008C8B0` ×417, usbxhci `0x1C00684A8` ×905, HDAudBus ×322, pci
  ×268, storport ×148, i8042prt ×68, disk ×37, HP serial ×11. The
  cell sits immediately past the IAT directory's end, which is why it
  reads as ".idata but not a thunk". These are not import calls and
  not noise: they are the CFG check before every indirect call, and
  their count is a measure of indirect-call density, not of anything
  wrong.
- **1 is an nmap call to `0x409054` in `.data`** (no load-config CFG
  cell on that image). One row, named, not yet read further.

So the corpus decomposes with nothing left over: **11,076 import
calls + 2,176 CFG dispatch + 1 = 13,253.**

**Consequences for (a)'s scope.** (a) repairs slot equality on 64-bit:
resolve a RIP-relative target as instruction address + length + disp
instead of the raw disp. Two things it must *not* do: credit itself
with the classification gaps (30 + 15 on the ReactOS controls, 44 on
nmap, all vocabulary), and refuse the CFG calls as unknown. The CFG
cell is readable from the load-config directory, so the resolver can
name that category rather than dropping it; the PE loader does not
expose it today, so the red for it is minted in (a)'s commit with the
plumbing (as the wide-`disp` refusal red is minted in (o)'s). The
refusal red already on the list covers the other half: a
memory-indirect call whose target is no import slot records no IAT
edge.

**(a) predicted movement, per class and per input, never a headline.**
Written before the fix:
- `summary.call_graph`, per 64-bit driver: `iat_slot_hits` 0 → the
  "hit_exact" column measured above (ACPI 3307, usbxhci 1294, pci
  2423, storport 2031, HP serial 465, i8042prt 457, disk 346,
  HDAudBus 391); `iat_edges` falls by the CFG count on each image once
  CFG is categorised (ACPI 3724 → 3307, usbxhci 2199 → 1294, …);
  `iat_matched_classified` rises to at most the slot hits and is
  capped by the classifier's driver-API vocabulary, so it is
  **predicted below** the hit column on every input and is not (a)'s
  measure.
- The 32-bit controls: **every column identical**. They are the
  control for (a) precisely because their slot equality already works.
- The operand differential: `addr` is the class (a) moves, and it is
  ≈40,856 rows corpus-wide against (o)'s 129. **The invariant is
  under real strain here and the exemption is named in advance:**
  repairing a RIP-relative target changes an operand *value*, so a row
  that is `operand_ok` today only because both sides printed the same
  wrong thing can move *out* of `operand_ok` — the `.text+0x69d4c`
  lesson at scale. Any such row is read from bytes and named, exactly
  as a desync-run exemption is; a row leaving `operand_ok` without a
  named cause stops the fix. Per-input per-class predictions are
  written when (a) is pre-registered; this paragraph fixes the form.
