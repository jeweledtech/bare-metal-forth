# Claude Code Task: DISASM Vocabulary
# LMI-Style 32-bit In-System Disassembler

## Context

This task implements a block-loadable DISASM vocabulary that gives the
running ForthOS system the ability to examine live memory — decompiling
both native CODE words (x86 machine code) and colon definitions
(threaded word lists) directly at the Forth prompt.

Design source: LMI (Laboratory Microsystems Inc.) UR/Forth architectural
patterns, recovered via Forth community research. The key insight from
LMI: the disassembler detects word type via a header flag bit, then
routes to either an x86 decoder or a threaded decompiler. Both paths
share a common `(PC)` (print-cell) primitive that handles LIT correctly,
so SEE and DIS never diverge on literal display.

## Repository

`~/projects/bare-metal-forth`

Current state:
- Kernel: `src/kernel/forth.asm` — DTC, ESI=IP, EBP=RP, ESP=SP
- SEE word already in kernel — study it before writing (PRINT-CELL)
- VAR_LATEST: kernel variable holding link address of most recent word
- Flags byte layout (current): bit7=IMMEDIATE, bits4-0=NAME_LENGTH
- Block range 240-250 is free for DISASM

---

## Task 1: Kernel Change — IS_COLON Flag

**This is the only required kernel change. Everything else is pure Forth.**

In `src/kernel/forth.asm`, find the `:` (colon) word implementation —
the DEFWORD or DEFCODE that creates new dictionary entries. When a colon
definition is created, set bit 6 (0x40) of the flags/length byte in the
new word's header.

New flags byte layout:
```
Bit 7: IMMEDIATE  (1 = execute during compilation)
Bit 6: IS_COLON   (1 = colon definition)  ← NEW
Bit 5: RESERVED   (0 for now)
Bits 4-0: NAME_LENGTH (1-31 chars)
```

**Read forth.asm carefully before touching it.** Find:
1. Where `:` stores the flags byte for a new word
2. The exact NASM instruction that writes that byte
3. Add `OR` with `0x40` to set bit 6

Verify the change doesn't affect IMMEDIATE words — IMMEDIATE sets bit 7,
IS_COLON sets bit 6; they are independent and can both be set.

**After the kernel change, verify `make test` still passes (91/91) before
proceeding to Task 2.** A broken `:` breaks everything.

---

## Task 2: DISASM Vocabulary

File: `forth/dict/disasm.fth`
Block range: 240-250
Dependencies: None (uses kernel primitives only)

### Header format reference

Every dictionary entry:
```
[LINK: 4 bytes] → previous word's link address
[FLAGS: 1 byte] → bit7=IMMEDIATE bit6=IS_COLON bits4-0=NAMELEN
[NAME: variable] → NAMELEN bytes, no null terminator
[CFA: 4 bytes]  → in DTC, this IS the executable code address
[PFA: variable] → colon: threaded word addresses; CODE: not used
```

To navigate from LINK address to CFA:
```
link_addr + 4       → flags byte address
link_addr + 4 + 1   → name start
link_addr + 4 + 1 + NAMELEN → CFA address
```

NAMELEN = flags_byte AND 0x1F (low 5 bits)

### Word 1: `LINK>CFA`  ( link-addr -- cfa-addr )

Navigate from a word's link field address to its code field address.

```forth
: LINK>CFA ( link-addr -- cfa-addr )
  4 +           \ skip link field
  DUP C@ 1F AND \ get name length (low 5 bits)
  + 1+ ;        \ skip flags byte + name bytes
```

Verify: for a word with a 4-char name, LINK>CFA should advance
4 (link) + 1 (flags) + 4 (name) = 9 bytes. Check against a known
kernel word by examining its header manually.

### Word 2: `>NAME`  ( addr -- nfa|0 )

Given any address, find the dictionary entry that "owns" it by scanning
the linked list from LATEST backward. Returns the link-field address
(what we call nfa here) of the owning word, or 0 if not found.

Heuristic: word N owns addr if:
  addr >= CFA(word N)  AND  addr < CFA(word N-1)

```forth
VARIABLE >NAME-PREV  \ track previous CFA during scan

: >NAME ( addr -- nfa|0 )
  0 >NAME-PREV !
  LATEST @               \ start at most recent word
  BEGIN DUP WHILE        \ while link pointer non-null
    DUP LINK>CFA         \ get this word's CFA
    2 PICK OVER >= IF    \ addr >= this CFA?
      >NAME-PREV @ IF    \ and we have a next word?
        >NAME-PREV @ LINK>CFA
        3 PICK < IF      \ addr < next word's CFA?
          NIP NIP EXIT   \ return this link addr
        THEN
      ELSE               \ most recent word: addr >= CFA is enough
        NIP NIP EXIT
      THEN
    THEN
    DUP >NAME-PREV !     \ save as "previous" for next iteration
    @                    \ follow link to previous word
  REPEAT
  DROP DROP 0 ;          \ not found
```

**Note:** `LATEST` must exist as a kernel word returning the link-field
address of the most recent word. Verify the exact word name in forth.asm
— it may be `LATEST`, `VAR_LATEST @`, or similar. Use whatever the
kernel exposes.

### Word 3: `ID.`  ( nfa -- )

Print the name of a word given its link-field address.

```forth
: ID. ( nfa -- )
  DUP 0= IF DROP ." (unknown)" EXIT THEN
  4 +            \ skip link field
  DUP C@ 1F AND  \ name length (low 5 bits)
  SWAP 1+        \ advance past flags byte to name start
  SWAP TYPE ;    \ print name
```

### Word 4: `(PC)`  ( addr -- next-addr )

Print-Cell: the shared primitive used by both DECOMP and future SEE
integration. Reads one cell from addr. If it is the XT of LIT, prints
the following cell as a number and advances past both. Otherwise looks
up the XT as a word name and prints it.

```forth
: (PC) ( addr -- next-addr )
  DUP @                    \ fetch XT at this address
  ['] LIT = IF             \ is it LIT?
    4 + DUP @ .            \ skip LIT, print the literal value
    4 +                    \ advance past the literal
  ELSE
    DUP @ >NAME ID.        \ look up and print word name
    SPACE
    4 +                    \ advance to next cell
  THEN ;
```

**Read the existing SEE word in forth.asm before finalizing (PC).** The
kernel's SEE already handles LIT detection — use the same approach. If
SEE uses a different sentinel check, match it.

The XT of LIT is obtained at compile time with `['] LIT`. Verify this
works in your kernel before using it in (PC).

### Word 5: `DECOMP`  ( cfa -- )

Decompile a colon definition by walking its parameter field and printing
each threaded word using (PC), until EXIT is encountered.

```forth
: DECOMP ( cfa -- )
  ." : " DUP >NAME ID. CR
  4 +                      \ skip CFA to first PFA cell
  BEGIN
    DUP @ ['] EXIT = IF    \ stop at EXIT
      DROP EXIT
    THEN
    2 SPACES (PC)
  AGAIN ;
```

**Note:** `EXIT` and `UNNEST` may be the same word in your kernel, or
different names. Check forth.asm for the word that terminates colon
definition execution and use that XT as the sentinel.

### Word 6: `DIS-X86`  ( cfa -- )

Decode x86 machine code starting at cfa. This is the "Forth 80%" decoder
— handles only the instructions that actually appear in Forth CODE words.
Unknown opcodes print as `.BYTE xx`.

Implement as a table-driven loop. Each iteration:
1. Fetch byte at current address
2. Match against opcode table
3. Print mnemonic + operands
4. Advance by instruction length
5. Stop at RET (0xC3) or after a fixed maximum (e.g., 32 instructions)

**Minimum opcode set to handle:**

| Opcode | Mnemonic | Notes |
|--------|----------|-------|
| 0xAD | LODSD | No operands — standard NEXT prefix |
| 0xFF /4 | JMP [EAX] | ModR/M — standard NEXT suffix |
| 0x50-0x57 | PUSH reg | Register encoded in low 3 bits |
| 0x58-0x5F | POP reg | Register encoded in low 3 bits |
| 0x89 | MOV r/m,r | Requires ModR/M decode |
| 0x8B | MOV r,r/m | Requires ModR/M decode |
| 0x01 | ADD r/m,r | Requires ModR/M decode |
| 0x29 | SUB r/m,r | Requires ModR/M decode |
| 0x39 | CMP r/m,r | Requires ModR/M decode |
| 0xE9 | JMP rel32 | 4-byte relative offset follows |
| 0x74 | JZ rel8 | 1-byte relative offset follows |
| 0x75 | JNZ rel8 | 1-byte relative offset follows |
| 0xE8 | CALL rel32 | 4-byte relative offset follows |
| 0xC3 | RET | No operands — stop decoding |

**NEXT sequence detection:** If you see `0xAD` (LODSD) followed by
`0xFF 0xE0` (JMP EAX), print `NEXT` instead of the individual opcodes.
This is the DTC inner interpreter loop and naming it makes CODE words
dramatically more readable.

**ModR/M decoder:**

```forth
\ Register name table (EAX=0 through EDI=7)
CREATE REG-NAMES
  ," EAX" ," ECX" ," EDX" ," EBX"
  ," ESP" ," EBP" ," ESI" ," EDI"

: .REG32 ( n -- )
  7 AND 4 * REG-NAMES + 1+ 3 TYPE SPACE ;

VARIABLE MODRM-MOD
VARIABLE MODRM-REG
VARIABLE MODRM-RM

: DECODE-MODRM ( byte -- )
  DUP C0 AND 6 RSHIFT MODRM-MOD !
  DUP 38 AND 3 RSHIFT MODRM-REG !
      07 AND             MODRM-RM ! ;
```

**What NOT to handle:**
- FPU instructions (D8-DF)
- System instructions (LGDT, LIDT, LLDT)
- SSE/MMX instructions
- Segment override prefixes
- String instructions other than LODSD
- BCD instructions

For any unrecognized opcode: print `.BYTE ` followed by the hex value
and advance by 1.

### Word 7: `DIS`  ( addr -- )

Top-level dispatcher. Finds the owning word, checks IS_COLON (bit 6 of
flags), routes to DECOMP or DIS-X86.

```forth
: DIS ( addr -- )
  DUP >NAME            \ find owning word
  DUP 0= IF
    DROP ." Raw: " DIS-X86 EXIT
  THEN
  DUP ID. ."  is "
  4 + C@ 40 AND IF     \ check bit 6 (IS_COLON = 0x40)
    ." colon def:" CR
    LINK>CFA DECOMP
  ELSE
    ." native code:" CR
    LINK>CFA DIS-X86
  THEN ;
```

---

## Task 3: Block Storage and Makefile

After `disasm.fth` is written:

1. Verify all lines ≤ 64 chars:
```bash
awk 'length > 64 { print NR": "length": "$0 }' forth/dict/disasm.fth
```
Zero output required.

2. Add to `tools/write-catalog.py` or equivalent so `make write-catalog`
includes DISASM at blocks 240-250.

3. Rebuild and verify it loads:
```bash
make blocks && make write-catalog
# Boot QEMU, then:
# 240 250 THRU
# USING DISASM
# WORDS   ← should show DIS, DECOMP, >NAME, ID., (PC), etc.
```

---

## Task 4: Tests

Add `test_disasm.py` following the same serial automation pattern as
existing tests. Minimum assertions:

```python
# 1. DISASM vocab loads without ? errors
r = send('240 250 THRU')
assert '?' not in r

# 2. USING DISASM works
send('USING DISASM')
assert alive()

# 3. >NAME finds a known kernel word
# DUP is a kernel word — look up its CFA and verify >NAME finds it
r = send("' DUP >NAME ID.")
assert 'DUP' in r

# 4. DIS on a colon word shows threaded output (not raw hex)
# SQUARE is defined in the smoke test as : SQUARE DUP * ;
r = send(': SQUARE DUP * ;  ' + "' SQUARE DIS")
assert 'DUP' in r
assert '*' in r or 'STAR' in r  # kernel may name it either way

# 5. DIS on a CODE word shows x86 output (not colon decompilation)
# Use INB which is a CODE word
r = send("' INB DIS")
assert 'native code' in r.lower() or 'INB' in r

# 6. (PC) handles LIT correctly
# : LIT-TEST 42 ;  — should show  42  not the XT of LIT
r = send(': LIT-TEST 42 ; ' + "' LIT-TEST DECOMP")
assert '42' in r
assert 'LIT' not in r  # LIT itself should not appear, only the value
```

Add to `make test` via the test-vocabs target.

---

## Commit Message

```
Add DISASM vocabulary: LMI-style in-system disassembler

Kernel: Set IS_COLON flag (bit 6) in flags byte when ':' creates word.
Flags layout: bit7=IMMEDIATE bit6=IS_COLON bit5=RESERVED bits4-0=NAMELEN

DISASM vocabulary (blocks 240-250):
- LINK>CFA: navigate dictionary header to code field
- >NAME: find owning word for any address (closest-match scan)
- ID.: print word name from link-field address
- (PC): shared print-cell, LIT-aware, used by DECOMP and SEE
- DECOMP: walk colon definition parameter field to EXIT
- DIS-X86: table-driven x86 decoder for Forth 80% instruction set
- DIS: top-level dispatcher, routes by IS_COLON flag

NEXT sequence detection: LODSD + JMP EAX prints as "NEXT"
Unknown opcodes: .BYTE <hex>

Inspired by LMI UR/Forth DISASM architecture (Ray Duncan era).
F-PC ASM86.SEQ: https://github.com/uho/F-PC/tree/main/fpc/src.

make test: 91/91 → N/N
```

---

## What NOT To Do

- Do not implement the full x86 instruction set — handle only the
  opcodes that actually appear in Forth CODE words (listed above)
- Do not duplicate LIT detection logic from SEE — read SEE first,
  then share the approach in (PC)
- Do not use CODE/END-CODE in disasm.fth — pure Forth only
- Do not guess at kernel word names (LATEST, LIT, EXIT) — read
  forth.asm and use the exact names exposed as Forth words
- Do not break IS_COLON flag for IMMEDIATE words — they are
  independent bits; a word can be both IMMEDIATE and IS_COLON
- All lines ≤ 64 characters — verify with awk before commit
