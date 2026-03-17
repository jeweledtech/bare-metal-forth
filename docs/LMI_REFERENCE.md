# LMI Reference — Laboratory Microsystems Inc.
# The Lineage of the ForthOS Assembler and Disassembler

## Status

The DISASM and ASM vocabularies are **pending implementation**.
Design is complete. See `CLAUDE_CODE_TASK_DISASM.md`.
Do not implement until Claude Code task is executed.

The LMI manual (physical copy) is held by the project mentor.
Recovery is an active archival goal. This document captures
everything recoverable from public sources in the meantime.

---

## The Lineage

```
1982  Ray Duncan publishes "FORTH 8086 Assembler"
      Dr. Dobb's Journal, Volume 7, page 94
      First structured x86 assembler embedded in Forth.
      Postfix notation, comma-suffix mnemonics, IF/THEN/ELSE
      backpatching using the Forth data stack at compile time.
      DDJ editor's note: "Ray's 8086 articles were so impressive
      that he was commissioned to write a regular column."

      ↓

      Laboratory Microsystems Inc. (LMI)
      4147 Beethoven Street, Los Angeles, CA 90066
      (213) 306-7412
      Hired Duncan. Extended the assembler into a full
      professional development environment: PC/Forth,
      UR/Forth. Customers: NASA JPL, Caltech, satellite
      systems, scientific instrumentation, defense labs.
      Standard package ($100, 1982): interpreter-compiler,
      virtual memory management, assembler, full screen
      editor, decompiler, demonstration programs, utilities.
      120-page manual (early), grew to ~500 pages (UR/Forth).

      ↓

      Project mentor worked directly with LMI's CEO and
      chief technical officer. Used LMI Forth on research
      equipment, instrumentation, satellite systems.
      Wrote MIRROR/LOOKINGGLASS (execution state serializer)
      patterned after VROOM mobile OS swap technique.

      ↓

      Windows 98 / HAL wall (late 1990s)
      LMI's CTO chose not to rewrite for Win98.
      "It would have been a major rewrite and it couldn't
      run under Windows because of the HAL. Since that
      destroys 90% of the power of Forth, he just retired."
      — Project mentor, 2026

      ↓

      Dr. C.H. Ting ports the Duncan/LMI assembler to
      LaForth (32-bit x86). Documents it as PASM in
      Chapter 10 of the LaForth manual. Available at:
      https://www.forth.org/Ting/LaForth/Chapter-10.pdf
      PASM = "Prefix ASseMbler" (Ting's own description:
      "based on the 8086 assembler published in Dr. Dobb's
      Journal, February 1982, by Ray Duncan")

      ↓

      Tom Zimmer incorporates compatible assembler into
      F-PC (Forth for IBM PC/XT/AT, DOS). Source in
      ASM86.SEQ, available at:
      https://github.com/uho/F-PC/tree/main/fpc/src
      Highest-fidelity open-source surviving implementation
      of the LMI assembler conventions.

      ↓

2026  This project (bare-metal-forth / ForthOS)
      Bare metal, no HAL, no OS layer, no Windows.
      The answer to the problem that ended LMI's run.
      DISASM and ASM vocabularies to be implemented
      following the Duncan/LMI/PASM architectural lineage.
```

---

## Why This Matters for the Project

The mentor's summary: **"That's why Forth needs to be the OS —
so it can grow and adapt to whatever it needs to be."**

LMI's customers needed direct hardware access because they
were building real-time scientific instruments where HAL
indirection was physically impossible. A telescope control
system or satellite instrument bus cannot tolerate an OS
deciding when you're allowed to talk to a port.

This project is architecturally the answer nobody had runway
to build at the time: not Forth layered on top of an OS, but
Forth as the OS. The vocabulary system — USING PCI-ENUM,
USING NE2000, USING I8042PRT — is exactly the "grow and adapt"
model. Load a vocabulary, gain a capability. Drop it, the
capability disappears. No reboot. No registry. No HAL.

The UBT pipeline that strips HAL scaffolding from Windows
drivers to recover the actual hardware protocol is directly
solving the same problem that ended LMI's commercial run —
just from the opposite direction.

---

## The LMI Assembler Architecture

### Confirmed from Primary Sources

**Source 1: LaForth Chapter 10 (PASM)**
URL: https://www.forth.org/Ting/LaForth/Chapter-10.pdf
Status: Fetched and read directly. Contains full PASM source.

**Source 2: F-PC ASM86.SEQ (Tom Zimmer)**
URL: https://github.com/uho/F-PC/tree/main/fpc/src
Status: Available on GitHub. Highest-fidelity open reference.

**Source 3: Forth Dimensions IV/2 (July/August 1982)**
URL: https://www.forth.org/fd/FD-V04N2.pdf
Status: Fetched. Contains original LMI product announcement
(page 2) and Robert Ackerman's "A Recursive Decompiler"
article (page 28) — the prototype for the DISASM logic.

### Naming Conventions

All confirmed from PASM source and community sources:

| Category | Convention | Example |
|---|---|---|
| Mnemonics | Comma suffix | `MOV,` `ADD,` `JMP,` `PUSH,` |
| Registers | No comma | `EAX` `EBX` `ESI` `EDI` |
| Condition codes | No comma | `0=` `0<>` `CS` `LT` |
| Entry/exit | No comma | `CODE` `END-CODE` `NEXT` |

### The NEXT Macro (32-bit DTC)

For Direct Threaded Code with ESI=IP (our system):

```forth
: NEXT ( -- )
    LODSD       \ EAX = [ESI], ESI + 4 -> ESI
    EAX JMP,    \ jump to code address in EAX
;
```

The 16-bit version (LODSW / AX JMP,) is in the PASM source.
The 32-bit version is confirmed by LaForth Chapter 10 and
by community consensus for DTC systems.

Machine code signature: `AD FF E0`
(`AD` = LODSD, `FF E0` = JMP EAX)
Any CODE word ending with this sequence is returning to the
Forth inner interpreter.

### Structured Control Flow (Backpatching)

LMI's key innovation: IF/ELSE/THEN compile x86 jump opcodes
using the Forth data stack to hold patch addresses.

```forth
: IF, ( condition-opcode -- patch-addr )
    C,              \ compile the Jcc opcode (e.g. 0x74 = JZ)
    HERE            \ push patch location onto stack
    0 C, ;          \ compile dummy 1-byte offset

: THEN, ( patch-addr -- )
    HERE OVER -     \ distance from patch to here
    1-              \ adjust for the offset byte itself
    SWAP C! ;       \ backpatch the real offset

: ELSE, ( patch-addr1 -- patch-addr2 )
    0EB IF,         \ compile unconditional JMP, get new patch
    SWAP THEN, ;    \ resolve original IF's jump to here
```

For 32-bit targets: use 6-byte near jump encoding
(`0F 8x [4-byte offset]`) to avoid the ±127 byte limit
of short jumps. THEN, calculates the correct distance
and writes 4 bytes instead of 1.

### Condition Code Words

| Word | x86 Opcode | Meaning |
|---|---|---|
| `0=` | `74` (JZ) | Zero / Equal |
| `0<>` | `75` (JNZ) | Not Zero / Not Equal |
| `CS` | `72` (JC) | Carry Set |
| `CC` | `73` (JNC) | Carry Clear |
| `<` | `7C` (JL) | Less Than (signed) |
| `>=` | `7D` (JGE) | Greater or Equal (signed) |
| `U<` | `72` (JB) | Below (unsigned) |
| `U>=` | `73` (JAE) | Above or Equal (unsigned) |

### The DISASM / DIS Word

LMI's "live prompt" disassembler. Key features:

1. **Dictionary-aware**: before printing an address, scans
   the Forth dictionary. If the address matches a word's
   code field, prints the word name instead of hex.

2. **Context-aware**: distinguishes CODE words (x86 machine
   code) from colon definitions (threaded word lists).
   Uses the IS_COLON flag (bit 6 of flags byte) — set by
   `:` at word creation time.

3. **LIT-aware**: when walking a colon definition and
   encountering the XT of LIT, prints the following cell
   as a number rather than looking it up as a word name.

4. **BRANCH-aware**: when encountering BRANCH or 0BRANCH,
   prints the branch target offset rather than treating it
   as an XT. This is what makes IF/ELSE/THEN readable.

Syntax (LMI convention): `addr DIS`
Alternative form: `addr len DIS` for a range.

---

## The Ackerman Recursive Decompiler (1982)

Robert D. Ackerman, "A Recursive Decompiler"
Forth Dimensions, Volume IV, Number 2, page 28 (July/August 1982)

This is the prototype for the DISASM threaded-mode decompiler.
Ackerman is the same person who wrote the letter on page 4 of
the same issue noting inconsistencies between fig-FORTH and
Brodie's documentation — he was a practicing Forth programmer,
not a theorist.

Key contributions confirmed from community references:
- Introduced the `(PC)` / (PRINT-CELL) pattern for walking
  threaded code cell by cell
- Explicit LIT detection: if `[addr] == XT(LIT)`, print
  `[addr+4]` as a number, advance past both
- Handles `BRANCH` and `0BRANCH` by printing the target
  offset rather than looking it up as a word
- The "recursive" in the name: when it encounters a call
  to a colon definition, it can recurse into it

This design is incorporated into the `(PC)` word in the
DISASM task document. The word name `(PC)` is preserved
as a direct tribute to Ackerman's original.

---

## MIRROR and LOOKINGGLASS

Designed and implemented by the project mentor, ca. 1990s.
Patterned after the VROOM mobile OS execution swap technique.

`MIRROR ( -- )`: Serialize complete execution state to ATA
blocks. Captures: parameter stack, return stack, dictionary
state, all variable values, instruction pointer.

`LOOKINGGLASS ( -- )`: Deserialize from ATA blocks back into
live execution. Resume execution exactly where MIRROR was
called. "Kept all the current variable data and the works."

Performance: Fast on spinning disk; expected to be "blinding
fast" on SSD given sub-millisecond block access times.

Use cases:
- Pause execution to run something else, resume later
- Preserve code or data across hardware swaps
- Checkpoint long-running computations
- Swap large code regions in/out when memory is constrained

Status: MIRROR and LOOKINGGLASS are implemented in
`forth/dict/mirror.fth`. They represent direct transfer of
the mentor's original LMI-era work into this project.

---

## What Remains in the Physical LMI Manual

The mentor has the physical LMI manual in storage. When
recovered, highest-priority items to extract:

1. Complete ASSEMBLER vocabulary word list with stack effects
2. The exact DISASM display format and word naming
3. Laboratory extension words (GPIB/IEEE-488, analog I/O,
   timer interrupt integration)
4. Any 32-bit or protected-mode extension documentation
5. The full MIRROR/LOOKINGGLASS specification if documented

**Do not implement the ASM vocabulary until the manual is
reviewed.** The PASM source and F-PC ASM86.SEQ are sufficient
reference for the DISASM vocabulary. The ASM vocabulary
(the assembler itself, not the disassembler) benefits from
seeing the full LMI word list before committing to naming.

---

## The GPU / Multi-Processor Extension

Mentor comment (2026): "With the GPUs and all of the
multi-threaded processors it is really amazing what can be done.
Extending it for the modern processor code set would be the
power tool beyond amazing."

LMI's customers used Forth for real-time data acquisition
across multiple instruments. The same pattern — distribute
work across devices by loading data into each device's port,
check completion, pull results back — applies to modern
GPU compute and multi-core processors.

The roadmap item: an ASM vocabulary that covers not just
x86 but CUDA PTX, ARM64, and RISC-V instruction sets,
using the same comma-suffix Forth-assembler conventions.
Each CPU/GPU becomes addressable as a Forth vocabulary.
`USING ARM64-ASM` targets ARM64. `USING PTX-ASM` targets
CUDA. The UBT's multi-architecture decoder infrastructure
is the foundation for this.

This is the long-game vision. The DISASM vocabulary is step
one. The full multi-architecture ASM vocabulary is Phase 4+.

---

## Key People

**Ray Duncan** — Author of the original 1982 DDJ 8086 Forth
assembler. LMI employee. Wrote the "16-Bit Software Toolbox"
column for DDJ through the mid-1980s. Co-author with Martin
Tracy of the FVG Standard Floating-Point Extension (DDJ
September 1984). Chaired ANS Forth standards meetings (1988).
His 1982 assembler is the ancestor of every structured Forth
assembler for x86.

**LMI CEO / CTO** — Known to the project mentor personally.
Made the deliberate decision not to rewrite LMI Forth for
Windows 98 HAL compatibility. Chose retirement over
architectural compromise. The correct call given the
constraints. This project is the answer he didn't have
time to build.

**Robert D. Ackerman** — Author of "A Recursive Decompiler"
(FD IV/2, 1982). Practicing Forth programmer in San Francisco.
His `(PC)` pattern is preserved in this project's DISASM
vocabulary as a direct design inheritance.

**Dr. C.H. Ting** — Ported the Duncan assembler to 32-bit
LaForth. Author of LaForth manual including Chapter 10
(PASM source). Also the Dr. Ting of the Taiwan Forth group
who appears in FD IV/2 letters. Connected multiple threads
of Forth history into documented 32-bit form.

**Tom Zimmer** — Author of F-PC. Incorporated LMI-compatible
assembler as ASM86.SEQ. F-PC source is the most accessible
surviving open-source implementation of the Duncan conventions.

**Project Mentor** — Direct connection to LMI (knew CEO and
CTO personally). Implemented MIRROR/LOOKINGGLASS. Has
physical LMI manual in storage. Primary living link between
LMI's institutional knowledge and this project.

---

## Primary Source: The Original Article (DDJ February 1982)

**"FORTH 8086 Assembler" by Ray Duncan**
Dr. Dobb's Journal, Number 64, February 1982, pages 14-46
Screens 6-47 (the complete assembler source listing)

Author's address on article: "Ray Duncan, c/o Laboratory Microsystems,
4147 Beethoven Street, Los Angeles, CA 90066"
He was LMI staff when he wrote it. The assembler was LMI's from day one.

### The 14 Instruction Groups

The assembler handles x86 instructions in 14 categories (Table I):

1. Single byte instructions (no operand)
2. Conditional branches and loops (1-byte offset)
3. String instructions: CMPS, LODS, MOVS, SCAS, STOS
4. PUSH and POP
5. Intersegment JMP/CALL ("JMP disp16" or "JMP reg/mem")
6. IN and OUT
7. Two-operand arithmetic/logical: ADC ADD AND CMP OR SBB SUB TEST XOR
8. Single-operand: DIV IDIV IMUL MUL NEG NOT
9. Shifts: RCL RCR ROL ROR SAL SAR SHL SHR
10. Simple two-byte instructions
11. INC and DEC
12. Various MOV instructions
13. Various XCHG instructions
14. TEST instruction

### Internal State Variables (Screen 7)

The assembler maintains operand state in these variables:

```
VOCABULARY ASSEMBLER IMMEDIATE
ASSEMBLER DEFINITIONS HEX

0 VARIABLE <#>    ( immediate data flag )
0 VARIABLE <TD>   ( destination addressing type )
0 VARIABLE <TS>   ( source addressing type )
0 VARIABLE <RD>   ( destination register )
0 VARIABLE <RS>   ( source register )
0 VARIABLE <W>    ( word/byte flag )
0 VARIABLE <WD>   ( destination word/byte flag )
0 VARIABLE <OD>   ( destination offset )
0 VARIABLE <OS>   ( source offset )
0 VARIABLE <SP>   ( local stack pointer )
```

### Internal Primitives (Table I from article)

| Primitive | Purpose |
|---|---|
| `?W` | Leave word/byte flag on stack |
| `?TD` | Leave dest addr type (0=direct 1=immed 2=REG8 3=REG16 4=indexed 5=SEGREG) |
| `?TS` | Leave source addr type (same encoding) |
| `?RD` | Leave dest register code (0-7) |
| `?RS` | Leave source register code (0-7) |
| `?OD` | Leave dest displacement |
| `?OS` | Leave source displacement |
| `?D` | Leave direction flag |
| `+W` | Merge word/byte flag into forming byte |
| `+D` | Merge direction flag |
| `+RD` | Merge dest register code |
| `+RS` | Merge source register code |
| `MOD1` | Set mod field to 01 (3F AND 40 OR) |
| `MOD2` | Set mod field to 10 (3F AND 80 OR) |
| `MOD3` | Set mod field to 11 (3F AND C0 OR) |
| `RESET` | Clear all assembler flags and modes |
| `OFFSET8,` | Calculate/store 8-bit branch offset (error if out of range) |
| `OFFSET16,` | Calculate/store 16-bit offset for JMP/CALL |
| `DISP,` | Calculate/store displacement for MEM/REG instructions |
| `DSET` | Check base-relative indexed addressing, set direction flag |
| `BYTE` | Force W flag to indicate byte mode |
| `WORD` | Force W flag to indicate word mode |
| `#` | Set immediate data flag |

### Addressing Mode Constants (Screen 20)

```forth
0 CONSTANT DIRECT
1 CONSTANT IMMED
2 CONSTANT REG8
3 CONSTANT REG16
4 CONSTANT INDEXED
5 CONSTANT SEGREG
```

### Structured Control Flow — Exact Original Source (Screen 45)

```forth
\ 8086 Assembler --- control structures

\ IF..ENDIF or IF..ELSE..ENDIF provides conditional
\ execution based on state of CPU Z flag

: IF     074 C, 0 C, HERE RESET      ( stores JZ )
: ELSE   0EB C, 0 C,                 ( stores JMP )
         HERE SWAP - DUP ABS 07F > 23 ?ERROR C, RESET
: ENDIF  DUP HERE SWAP - DUP ABS 07F > 23 ?ERROR
         SWAP 1- C! RESET            ( resolves branches )

\ BEGIN..UNTIL construct: controlled repetitive
\ execution, exit from loop if Z flag is false

: BEGIN  HERE RESET                  ( leaves address )
: UNTIL  074 C, HERE 1+ -            ( stores JZ )
         DUP ABS 07F > ?ERROR C, RESET
```

Note: ENDIF is used where modern Forth uses THEN. Both name the
word that resolves the forward branch.

### CODE/;CODE/NEXT Termination (Screen 47)

```forth
\ CODE, ;CODE, and NEXT delimit a code definition

: NEXT   0E9 C, NEXT-LINK OFFSET16, RESET
         ?EXEC ?CSP SMUDGE [COMPILE] FORTH ; IMMEDIATE

FORTH DEFINITIONS

: ;CODE  ?CSP COMPILE (;CODE) [COMPILE] [ ASSEMBLER
         RESET FORTH [COMPILE] ASSEMBLER ; IMMEDIATE
: CODE   ?EXEC !CSP CREATE ASSEMBLER RESET FORTH
         [COMPILE] ASSEMBLER ; IMMEDIATE
```

NEXT in the original is a JMP to NEXT-LINK (the inner interpreter
entry point), not inline LODSD/JMP EAX. The 32-bit DTC version
(LODSD + JMP EAX) is the architectural equivalent for our system.

### The CASE Statement Dependency (Screen 8)

The assembler's operand dispatch uses a CASE statement attributed
to Charles E. Eaker, Forth Dimensions Volume II, No. 3, page 37.
This is cited in the source, which means anyone building from
this assembler needs this CASE implementation or equivalent.

### Register Definitions (Screens 12-17)

Source registers use SREG :BUILD, destination registers use
DREG :BUILD. Both store (reg, type, w) triples.

8-bit source regs (Screen 12): AL CL DL BL AH CH DH BH
16-bit source regs (Screen 13): AX CX DX BX SP BP SI DI
Indexed source regs (Screen 14): [BX+SI] [SI+BX] [BX+DI]
  [DI+BX] [BP+SI] [SI+BP] [BP+DI] [DI+BP] [SI] [DI] [BP] [BX]
Segment source regs (Screen 15): ES CS SS DS

8-bit dest regs (Screen 16): AL, CL, DL, BL, AH, CH, DH, BH,
16-bit dest regs (Screen 17): AX, CX, DX, BX, SP, BP, SI, DI,

### What Is NOT Implemented (from article text)

The article explicitly documents these exclusions:
- ESC, INT, LDS, LES, SEG instructions
- Memory direct addressing with arithmetic/logical (ADD, OR)
  "all varieties of direct addressing involving the MOV
  instruction are supported"
- Absolute offset for conditional branches and calls
  (must supply the absolute address; assembler calculates
  the relative displacement)
- Intersegment "long" jumps and calls
- Some special-case machine code sequences (causes
  assembled code slightly longer in a few instances)

### Figures from Article

Figure 1 (page 16) — FAST10* example showing assembler usage:
```
CODE  FAST10*
AX    POP
BX, AX MOV
AX, AX ADD     ( * 2 )
AX, AX ADD     ( * 4 )
AX, BX ADD     ( * 5 )
AX, AX ADD     ( * 10 )
AX    PUSH
      NEXT
```

Figure 2 — PORT-WAIT (reads port, checks bit 2, loops):
```
CODE  PORT-WAIT
AL, 01 IN       ( read port #1 )
AL, # 02 TEST   ( check if bit 2 set )
       UNTIL
       NEXT
```

Figure 3 — PORT-WAIT with port number and bit mask from stack:
```
CODE  PORT-WAIT
DX    POP       ( port number )
BX    POP       ( bit mask )
      BEGIN
AX, DX IN       ( read port )
AX, BX TEST     ( check status bit )
      UNTIL
      NEXT
```

These figures are the canonical examples for writing CODE words
with this assembler. The PORT-WAIT figures are directly relevant
to our hardware vocabulary work.

### Addressing Syntax (from article)

Postfix notation. Operands precede mnemonic. Operands separated
by spaces. Destination operand precedes source operand.

```
AX, DX  MOV     ( copy DX into AX )
AX, # 0001 MOV  ( load value 0001 into AX )
0100, AX MOV    ( store AX contents to location 0100 )
AX, 4 [BX] MOV  ( load memory at BX+4 into AX )
```

Immediate values designated by `#` operator:
`AX, # 0001 MOV` loads value 0001 (not contents of address 0001)

---

## References

| Source | URL | Status |
|---|---|---|
| DDJ Vol 7 p.14-46 (Duncan original) | https://archive.org/details/dr_dobbs_journal_vol_07_201803/page/n69/mode/2up | **READ — full source captured above** |
| LaForth Chapter 10 (PASM, 32-bit port) | https://www.forth.org/Ting/LaForth/Chapter-10.pdf | Fetched |
| F-PC source (ASM86.SEQ) | https://github.com/uho/F-PC/tree/main/fpc/src | Available |
| FD IV/2 (Ackerman decompiler p.28) | https://www.forth.org/fd/FD-V04N2.pdf | Fetched (article confirmed, code not extracted) |
| FD V05N2 (Moore interview, Ray Duncan multi-tasker) | https://www.forth.org/fd/FD-V05N2.pdf | Fetched |
| FD V10N1 (ANS Forth committee, Ray Duncan chair) | https://www.forth.org/fd/FD-V10N1.pdf | Fetched |
| LMI physical manual | In mentor's storage | PENDING RECOVERY |
