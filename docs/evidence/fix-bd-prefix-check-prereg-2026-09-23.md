# (bd) The mandatory prefix is consulted where it decides the instruction: pre-registration (2026-09-23)

**Written before the change.** Owner ruling: name WBNOINVD, ERETS and
ERETU, but **state the fix as the defect it is**. The defect is not "three
instructions are unnamed". It is that **the decoder does not consult the
mandatory prefix** where the prefix decides the instruction. The bound is
stated as that set, not as three instructions. The scope is taken because
direct system access is what ForthOS is for, **not** because a census
found volume. Outcomes go BELOW the line.

## The sweep (the bound, measured first)

**Every two-byte opcode the decoder decides** (all 256 except the `0F 38`
and `0F 3A` escapes, whose only named rows are the SSE table's, already
keyed by prefix) was decoded under **none / `66` / `F2` / `F3`**. It was
decoded by the shipped decoder and by objdump (binutils 2.42), with each
instruction in its own 16-byte slot. That is **73,152 slots**.

**The fields held constant, and why they cannot carry this information:**
- **REX is absent.** REX.W also selects names (CMPXCHG8B/16B), but it is
  a different field and outside this item.
- **ModRM** takes all 64 register forms and the 8 memory digits at mod=00,
  rm=000. Other memory encodings change length (SIB, displacement), not
  identity.
- **Segment prefixes** are not sampled.

A cell is flagged when we give a name under a prefix while objdump either
names a **different** instruction or refuses the form. objdump's own prefix
tokens and AT&T size suffixes are stripped, so a `movzbw`/`movzbl` pair is
the same instruction; the first pass counted those, and they were
withdrawn. **Every flag was then checked against SDM 325462-092's opcode
column**, where `NP` means 66/F2/F3 are not allowed and `NFx` means F2/F3
are not allowed. The SDM is the master; objdump is the pinned cross-check.

### The bound

**1. Wrong names: six instructions in four (prefix, opcode) pairs, 84
cells.** Each is SDM-attested:

| encoding | SDM | we print |
|---|---|---|
| `F3 0F 09` | WBNOINVD | `wbinvd` |
| `F2 0F 01 CA` | ERETS | `clac` |
| `F3 0F 01 CA` | ERETU | `clac` |
| `F3 0F 01 EE` | **CLUI** (UINTR) | `rdpkru` |
| `F3 0F 01 EF` | **STUI** (UINTR) | `wrpkru` |
| `F3 0F C7 /6`, register form | **SENDUIPI** (UINTR) | `rdrand` |

The ruling named three. **The sweep finds six**, and the three extra are
the user-interrupt instructions. That is the item paying for itself, as
the ruling anticipated.

**2. Named although the SDM forbids the prefix: five (prefix, opcode)
pairs, 166 cells.**

| encoding | SDM row | we print |
|---|---|---|
| `66 0F 01 CA` | CLAC is `NP 0F 01 CA` | `clac` |
| `66`/`F2 0F 01 EE` | RDPKRU is `NP 0F 01 EE` | `rdpkru` |
| `66`/`F2 0F 01 EF` | WRPKRU is `NP 0F 01 EF` | `wrpkru` |
| `F3 0F 78` / `F3 0F 79` (72 cells each) | VMREAD / VMWRITE are `NP 0F 78` / `NP 0F 79` | `vmread` / `vmwrite` |
| `F2 0F C7` /6 memory, and /6, /7 register (17 cells) | VMPTRLD `NP`; RDRAND and RDSEED `NFx` | `vmptrld`, `rdrand`, `rdseed` |

**3. Not claimed: the SDM does not forbid it and objdump refuses it.**
`66`/`F2 0F 09` (144 cells) print `wbinvd`. objdump calls both `(bad)`, but
the SDM's WBINVD row is `0F 09`, not `NP`. Without the SDM's word it is not
a defect, and it is recorded as a disagreement between the two
instruments.

**4. A different class the sweep surfaced: mod-validity, 24 cells.**
- `66 0F 71/72/73` (memory digits), `66 0F C5` and `66 0F D7` (memory
  forms) are named although their SDM operand is register-only (**U**).
- It is not a prefix defect. It is (ba)'s table naming a row regardless of
  ModRM.mod, and the same holds in reverse for its memory-only (**M**)
  rows.
- **It becomes its own red, `(bf)`, with its own bound, and is not fixed
  here.**

**Reach: 0 corpus rows for every form in 1 and 2**, from the bytes on the
post-(ba) sweep. That is a measured zero: the same scan read **760** rows
of these instructions (VMREAD 356, VMWRITE 361, WBINVD 14, RDRAND 12,
VMPTRLD 10, RDSEED 4, CLAC 3) and found none prefixed.

## The change

- **Consult the mandatory prefix at the prefix-deciding cells** in
  `system_identity()`:
  - `0F 09`: `F3` → WBNOINVD;
  - `0F 01 CA`: `F2` → ERETS, `F3` → ERETU, and `66` is not CLAC;
  - `0F 01 EE/EF`: `F3` → CLUI/STUI, and `66`/`F2` are not RDPKRU/WRPKRU;
  - `0F 78/79`: `F3` is not VMREAD/VMWRITE (66 and F2 already were);
  - `0F C7`: `F3` /6 register → SENDUIPI; `F2` is not VMPTRLD, RDRAND or
    RDSEED.
- **Six identities** are appended (WBNOINVD, ERETS, ERETU, CLUI, STUI,
  SENDUIPI). A form the SDM forbids becomes `UNKNOWN`, with no claim and
  its length unchanged. It does not become `INVALID`, whose length-1
  resync would move lengths.
- **The lifter** puts the six with the system family: `UIR_UNMODELLED`, no
  `dest`.
- **Not taken:** TESTUI (`F3 0F 01 ED`) and UIRET (`F3 0F 01 EC`) are
  unknown today, which is not a wrong answer. They join `(be-0)`.

## Predictions

| # | prediction |
|---|---|
| D1 | the new red `x64_RED_bd_mandatory_prefix_consulted` and the existing `x64_RED_bd_system_prefix_not_misnamed` XPASS **together**, and nothing else moves: `(au)` stays green, and the allowed prefixed forms keep their names (`66 0F C7 F0` RDRAND with a 16-bit operand, `66 0F C7 /6` memory VMCLEAR, `F3 0F C7 /6` memory VMXON, `F3 0F C7 /7` register RDPID) |
| D2 | re-running the sweep: sets 1 and 2 go to **0** flagged cells, set 3 (the SDM-silent `66`/`F2 0F 09`) is **unchanged**, and set 4 (mod-validity) is **unchanged** |
| D3 | corpus: no identity changes on any set (0 rows carry these forms, measured) |
| D4 | differential, `-t uir` and the park census are byte-identical |
| D5 | suites green; tests +2 (this red, and `(bf)`'s red, registered in the same step); reds 13 → 15 while open, then 13 once `(bd)`'s two close, with `(bf)` still open |

---

## Outcome

*(below this line, from the artefact only)*

**Inputs hashed:** `x86_decoder.c` `1581528af3b2d75a`, `x86_decoder.h`
`769c8c14c2772444`, `uir.c` `dad1e86551a44df6`, `bin/translator`
`0026f7588b9290cb`. The sweep is the same 73,152-slot blob and the same
objdump output, re-decoded by the new build.

| # | predicted | observed |
|---|---|---|
| D1 | both `(bd)` reds XPASS together; `(au)` green; allowed prefixed forms keep their names | **held**: the gate fired on exactly `x64_RED_bd_system_prefix_not_misnamed` and `x64_RED_bd_mandatory_prefix_consulted`; `(au)` PASS; RDRAND r16 (`66`), VMCLEAR, VMXON and RDPID are asserted inside the item's red and pass. `(bf)` stays red |
| D2 | sets 1 and 2 → 0; sets 3 and 4 unchanged | **held exactly**: wrong names **84 → 0**, NP/NFx-forbidden named **166 → 0**, SDM-silent `66`/`F2 0F 09` **144 → 144**, mod-validity **24 → 24**. Across all 73,152 slots, **250 names changed (= 84 + 166) and 0 lengths** |
| D3 | no corpus identity changes | **held**: the corpus sweep is byte-identical on all seven sets |
| D4 | differential, `-t uir`, park census byte-identical | **held**: 0 of 16 dumps, 0 of 12 UIR files, and 0 outcome changes over 539 park sites |
| D5 | tests +2; reds 13 → 15 → 13 | **held**: 409 tests across 27 suites, 13 reds (`(bf)` open) |

**The limit of the sweep, stated so it is not read as completeness.** It
flags a cell only where **objdump disagrees** with us under a prefix.
Where the SDM marks a row `NP` but objdump *also* accepts the prefixed form
as the same instruction, both instruments agree, and the sweep cannot see
it. **Verified to occur:** STAC is `NP 0F 01 CB` in the SDM, objdump prints
`data16 stac` for `66 0F 01 CB`, and we print `stac`. That witness is now
the red `(bg)`. Its full bound needs the SDM's NP/NFx column read for every
named row, not a differential, and is owed when `(bg)` is taken.

**Also recorded, not taken:** TESTUI (`F3 0F 01 ED`) and UIRET (`F3 0F 01
EC`) are UINTR instructions we leave unknown, which is not a wrong answer.
They join `(be-0)`.

### A lesson about scoping (owner, 2026-09-23)

**An item scoped by mechanism reaches defects that an item scoped by
instance cannot.** The red asked for three instructions, WBNOINVD, ERETS
and ERETU. The ruling restated the defect as its mechanism: *the mandatory
prefix is not consulted where it decides the instruction*. The bound was
then that set, and it found **six**. CLUI, STUI and SENDUIPI were being
printed as `rdpkru`, `wrpkru` and `rdrand`, and nobody had asked about
them. Five further (prefix, opcode) pairs were being named despite the
SDM's `NP`/`NFx`. An instance-scoped fix would have closed its three
names and left the check missing at every other cell.

### Where both instruments agree, only the specification adjudicates

`(bg)` is the **third** recorded case of two instruments agreeing, and the
agreement being wrong:
1. **The Mac one-byte system forms** (`system-family-census-2026-09-22.md`).
   objdump and our decoder "confirmed" `STI`/`CLI`/`HLT` in ring-3
   userland, because both linear sweeps misread the same data bytes the
   same way.
2. **The `0F 18`–`1F` defaulted NOPs** (the thirty-second rule, recorded
   in `compare_operands.py`). Ghidra and we agreed on NOP, and at least 19
   of those rows are wrong in **both** (PREFETCHNTA ×16, ENDBR32 ×3).
3. **`data16 stac`.** objdump and we both accept `66 0F 01 CB`; the SDM
   says STAC is `NP`.

**A differential cannot see a shared error.** The only thing that can
adjudicate is a source neither instrument derives from. That is why
`(bg)`'s bound must come from **the SDM's NP/NFx column read over every
named row**, and not from another differential. It is the clearest return
the banking has produced, and it arrived the same day.
