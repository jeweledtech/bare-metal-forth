# Task: ForthOS Metacompiler

## Vision

The metacompiler lets ForthOS rebuild itself. From the running x86 system, it compiles a NEW kernel image for the same architecture (self-rebuild) or for ARM64 (Raspberry Pi cross-compile). This is the "install files from a dictionary on a stick" concept — the running Forth OS is the master machine that builds kernels for any target.

## Repository

Location: `~/projects/forthos`
Extend: `forth/dict/meta-compiler.fth` (existing, 136 lines, 21 words)
Create: `forth/dict/target-x86.fth` (x86 target architecture definitions)
Create: `forth/dict/target-arm64.fth` (ARM64 target definitions, Phase C)

Reference: `~/taygeta/metacompiler-refs/METACOMPILER-SYNTHESIS.md` (798-line synthesis from 7 sources, complete word catalog with stack effects and execution contexts)

---

## Architecture

### Key Insight

**NO metacompiler words execute on the TARGET.** Every word either runs on the HOST (the running x86 Forth) or runs on the HOST but produces TARGET data structures. The target image contains only the final kernel — dictionary headers, machine code, threaded code, and data. The metacompiler itself is entirely ephemeral.

### Three Vocabularies

1. **META-COMPILER** (HOST vocabulary) — the metacompiler's own words. Runs on the x86 host during metacompilation. Contains T-CODE, T-COLON, T-IF, T-THEN, FORWARD, RESOLVE, etc.

2. **TARGET** (symbol vocabulary) — "twin" entries for every target word defined. Each twin is an IMMEDIATE word that, when encountered during target compilation (T-]), compiles its target CFA into the target image. The twins exist only during metacompilation.

3. **FORTH** — the normal host Forth. Always available as fallback via the kernel's find_ FORTH-fallback mechanism.

### Memory Model

```
HOST (running x86 Forth):
  T-IMAGE: 64KB CREATE'd buffer in host dictionary space
  T-ORG:   0x7E00 (where target loads on bare metal)
  T-HERE:  current write position in T-IMAGE

TARGET (being built):
  Dictionary at 0x30000 (relative to T-ORG)
  Stack at 0x7C00 (data), 0x20000 (return)
  Same memory map as current kernel
```

All target addresses are computed via: `T-HERE @ T-IMAGE - T-ORG @ +`

Our flat 32-bit model eliminates META86's three segments (SEG-C/SEG-X/SEG-Y) — one T-IMAGE replaces all three.

### No Kernel Changes Needed

The kernel's existing `find_` / `VAR_SEARCH_ORDER[]` / `ALSO` / `PREVIOUS` / `ONLY` / `DEFINITIONS` already implement the Appelman parallel-search machinery. The metacompiler just manages the search order through these existing words.

---

## Current State

### Existing Words (21 in meta-compiler.fth)

| Word | Category | What It Does |
|------|----------|-------------|
| T-IMAGE | Buffer | 64KB target image buffer |
| T-ORG | Variable | Target origin address (0x7E00) |
| T-SIZE | Variable | Target image size |
| T-LINK-VAR | Variable | Target dictionary chain pointer |
| T-HERE | Variable | Target compilation pointer |
| T-ADDR | Computed | Current target address |
| TH-ADDR | Temp | Header name address |
| TH-LEN | Temp | Header name length |
| TH-FLAGS | Temp | Header flags |
| T-HEADER | Builder | Build target dictionary header |
| T-CODE | Builder | Start CODE word (header + self-CFA) |
| END-CODE | Builder | End CODE word (emit NEXT) |
| DOCOL-ADDR | Variable | DOCOL target address |
| T-COLON | Builder | Start colon word (header + DOCOL CFA) |
| FREF-COUNT | Variable | Forward reference count |
| FREF-TBL | Buffer | Forward reference table (1KB) |
| META-OK | Variable | Build success flag |
| META-STATUS | Display | Show build status + size |
| META-SIZE | Query | Return target image size |
| META-INIT | Setup | Zero target, reset pointers |
| META-BUILD | Driver | Build demo kernel (3 words) |

### What META-BUILD Currently Does

Builds a 3-word demo kernel: EXIT (0xC3 = RET), DROP (POP EAX), DUP (PUSH EAX). Each as a CODE word with header + CFA + assembly + NEXT. Total ~60 bytes. Proves the framework works but doesn't produce a bootable kernel.

---

## Words Needed (~50 new words)

### Priority 0: Target Memory Primitives

These must be factored out first — T-HEADER currently does inline memory writes that should be T-C, and T-, calls.

```forth
: T-C, ( char -- )        \ Write byte to target, advance T-HERE
    T-HERE @ C! 1 T-HERE +! ;

: T-, ( n -- )             \ Write cell to target, advance T-HERE
    T-HERE @ ! 4 T-HERE +! ;

: T-C@ ( taddr -- char )  \ Read byte from target (target-relative addr)
    T-IMAGE + C@ ;

: T-@ ( taddr -- n )       \ Read cell from target
    T-IMAGE + @ ;

: T-C! ( char taddr -- )  \ Write byte to target at arbitrary position
    T-IMAGE + C! ;

: T-! ( n taddr -- )       \ Write cell to target at arbitrary position
    T-IMAGE + ! ;

: T-ALLOT ( n -- )         \ Reserve n bytes in target
    T-HERE +! ;

: T-ALIGN ( -- )           \ Align T-HERE to 4-byte boundary
    BEGIN T-ADDR 3 AND WHILE 0 T-C, REPEAT ;
```

NOTE: T-C, and T-, already exist as inline code in T-HEADER, T-CODE, T-COLON (writing directly to T-HERE). They must be factored out as standalone words and the existing code refactored to call them. The synthesis document confirms T-, is "PARTIAL — exists inline but not as standalone word."

### Priority 1: Context Switching

```forth
: IN-META ( -- )           \ Search: META-COMPILER + FORTH
    ONLY FORTH ALSO META-COMPILER DEFINITIONS ;

: IN-TARGET ( -- )         \ Search: TARGET vocabulary
    ONLY TARGET DEFINITIONS ;

: [FORTH] ( -- ) IMMEDIATE \ Switch to FORTH mid-definition
    POSTPONE FORTH ;

: [META] ( -- ) IMMEDIATE  \ Switch to META mid-definition
    POSTPONE META-COMPILER ;
```

### Priority 1: Forward References

```forth
FORWARD ( "name" -- )      \ Declare forward reference
RESOLVE ( target-addr "name" -- ) \ Patch forward references
T-FORWARD, ( "name" -- )   \ Compile forward ref into target
META-CHECK ( -- )           \ Report unresolved references
```

Each FREF-TBL entry: counted name (32 bytes) + chain head address (4 bytes) + resolved flag (4 bytes) = 40 bytes per entry. 1KB table = 25 entries max.

RESOLVE walks the chain in the target image: each unresolved cell points to the previous unresolved use. Patch each cell with the final address.

### Priority 1: Target Compilation State

```forth
VARIABLE T-STATE           \ 0=interpreting, -1=compiling target

: T-] ( -- )               \ Enter target compilation
    -1 T-STATE ! ;

: T-[ ( -- )               \ Exit target compilation
    0 T-STATE ! ;

: T-LITERAL ( n -- )       \ Compile literal into target colon def
    DOLIT-ADDR @ T-, T-, ;

: T-' ( "name" -- taddr )  \ Look up target word, return CFA
    ... find in TARGET vocab ... ;

: T-COMPILE, ( taddr -- )  \ Compile target address
    T-, ;

: T-; ( -- )               \ End target colon definition
    DOEXIT-ADDR @ T-, T-[ ;
```

Runtime address variables (set after each runtime is defined in target):
```forth
VARIABLE DOLIT-ADDR        \ LIT runtime
VARIABLE DOBRANCH-ADDR     \ BRANCH runtime
VARIABLE DO0BRANCH-ADDR    \ 0BRANCH runtime
VARIABLE DOEXIT-ADDR       \ EXIT runtime
VARIABLE DOCREATE-ADDR     \ DOCREATE runtime
VARIABLE DOCON-ADDR        \ DOCON runtime
VARIABLE DOVOC-ADDR        \ DOVOC runtime
```

### Priority 1: Defining Words

```forth
: T-VARIABLE ( "name" -- )
    0 T-HEADER
    DOCREATE-ADDR @ T-,    \ CFA = DOCREATE
    0 T-, ;                 \ reserve + zero one cell

: T-CONSTANT ( n "name" -- )
    0 T-HEADER
    DOCON-ADDR @ T-,        \ CFA = DOCON
    T-, ;                   \ compile constant value

: T-VOCABULARY ( "name" -- )
    0 T-HEADER
    DOVOC-ADDR @ T-,        \ CFA = DOVOC
    0 T-, ;                 \ thread table (1 cell, zeroed)

: T-IMMEDIATE ( -- )       \ Set IMMEDIATE flag on last target header
    T-LINK-VAR @            \ target addr of last link
    4 +                     \ flags+length byte offset
    DUP T-C@
    40 OR                   \ set bit 6
    SWAP T-C! ;
```

### Priority 1: Target Control Flow

These produce TARGET branch structures. Critical: BRANCH uses `add esi,[esi]` (offset = target - offset_cell), while DOLOOP uses `lodsd; add esi,eax` (offset = target - offset_cell - 4). This is our bug #12/#19 lesson.

```forth
: T-IF ( -- orig )
    DO0BRANCH-ADDR @ T-,
    T-ADDR                  \ save address of placeholder
    0 T-, ;                 \ placeholder offset

: T-THEN ( orig -- )
    T-ADDR OVER -           \ offset = here - orig
    SWAP T-! ;              \ patch placeholder

: T-ELSE ( orig1 -- orig2 )
    DOBRANCH-ADDR @ T-,
    T-ADDR 0 T-,            \ new placeholder
    SWAP T-THEN ;           \ resolve orig1

: T-BEGIN ( -- dest )
    T-ADDR ;                \ backward target

: T-UNTIL ( dest -- )
    DO0BRANCH-ADDR @ T-,
    T-ADDR - T-, ;          \ BRANCH offset (no lodsd)

: T-AGAIN ( dest -- )
    DOBRANCH-ADDR @ T-,
    T-ADDR - T-, ;

: T-DO ( -- do-sys )
    DODO-ADDR @ T-,
    T-ADDR ;                \ loop body start

: T-LOOP ( do-sys -- )
    DOLOOP-ADDR @ T-,
    T-ADDR 4 + -            \ DOLOOP offset (has lodsd!)
    T-, ;

: T-; ( -- )
    DOEXIT-ADDR @ T-, T-[ ;
```

### Priority 1: Twin Headers

When T-CODE or T-COLON defines a target word, a "twin" is created in the HOST's META-COMPILER vocabulary. The twin is an IMMEDIATE word whose runtime behavior is: if in target compilation state (T-STATE), compile its target CFA via T-,; otherwise, leave it on the stack.

```forth
: T-TWIN ( target-addr "name" -- )
    \ Create host-side CONSTANT with target addr
    CONSTANT IMMEDIATE ;
    \ (oversimplified — see synthesis Q5 §J)
```

The actual T-TWIN mechanism uses CREATE/DOES>:
```forth
: T-TWIN ( target-addr -- )
    CREATE , IMMEDIATE
    DOES> @
    T-STATE @ IF T-, ELSE THEN ;
```

T-CODE and T-COLON should call T-TWIN after building the target header.

### Priority 2: Build Control

```forth
: META-SAVE ( -- )          \ Save target image
    \ Write to block disk or dump to serial
    T-IMAGE META-SIZE TYPE ; \ (simplified)

: META-CHECK ( -- )         \ Verify forward refs
    FREF-COUNT @ 0 DO
        ... walk table, report unresolved ...
    LOOP ;
```

### Priority 2: Number Literal Helpers

```forth
: D# ( "number" -- n )     \ Parse decimal regardless of BASE
    BASE @ >R DECIMAL
    BL WORD NUMBER DROP
    R> BASE ! ;

: H# ( "number" -- n )     \ Parse hex regardless of BASE
    BASE @ >R HEX
    BL WORD NUMBER DROP
    R> BASE ! ;
```

---

## Target Architecture Abstraction

Each target architecture provides these constants/words:

### target-x86.fth

```forth
VOCABULARY TARGET-X86
TARGET-X86 DEFINITIONS

4 CONSTANT CELL-SIZE
0 CONSTANT ENDIAN           \ 0=little
7E00 CONSTANT TARGET-ORIGIN

\ NEXT pattern: lodsd; jmp [eax]
: EMIT-NEXT ( -- )
    AD T-C,                  \ lodsd
    FF T-C, 20 T-C, ;       \ jmp [eax]

\ DOCOL pattern: push esi via EBP, lea esi,[eax+4]
: EMIT-DOCOL ( -- )
    8D T-C, 6D T-C, FC T-C, \ lea ebp,[ebp-4]
    89 T-C, 75 T-C, 00 T-C, \ mov [ebp],esi
    8D T-C, 70 T-C, 04 T-C, \ lea esi,[eax+4]
    EMIT-NEXT ;

\ DOCON: push [eax+4]
: EMIT-DOCON ( -- )
    FF T-C, 70 T-C, 04 T-C, \ push dword [eax+4]
    EMIT-NEXT ;

\ DOCREATE: lea eax,[eax+4]; push eax
: EMIT-DOCREATE ( -- )
    8D T-C, 40 T-C, 04 T-C, \ lea eax,[eax+4]
    50 T-C,                  \ push eax
    EMIT-NEXT ;

\ EXIT: pop esi from return stack
: EMIT-EXIT ( -- )
    8B T-C, 75 T-C, 00 T-C, \ mov esi,[ebp]
    8D T-C, 6D T-C, 04 T-C, \ lea ebp,[ebp+4]
    EMIT-NEXT ;
```

### target-arm64.fth (Phase C)

```forth
VOCABULARY TARGET-ARM64
TARGET-ARM64 DEFINITIONS

8 CONSTANT CELL-SIZE         \ 64-bit cells
0 CONSTANT ENDIAN            \ little-endian
80000 CONSTANT TARGET-ORIGIN \ ARM kernel load address

\ ARM64 NEXT: ldr x0,[x28],#8; ldr x1,[x0]; br x1
\   x28 = IP, x0 = W (working), x1 = temp
: EMIT-NEXT ( -- )
    ... ARM64 instruction encoding ... ;
```

---

## Build Workflow

### Phase A: Self-Rebuild (x86 → x86)

```forth
USING META-COMPILER
USING TARGET-X86

META-COMPILE-X86            \ builds complete x86 kernel in T-IMAGE
META-CHECK                  \ verify all forward refs resolved
META-STATUS                 \ show image size
META-SAVE                   \ write to disk/blocks
```

META-COMPILE-X86 is the top-level build driver. It:
1. Calls META-INIT (zero T-IMAGE, reset pointers)
2. Defines all CODE primitives (EXIT, DUP, DROP, SWAP, OVER, ROT, +, -, *, /, etc.)
3. Sets DOCOL-ADDR after DOCOL is defined
4. Defines all high-level words (IF, THEN, DO, LOOP, :, ;, INTERPRET, etc.)
5. Defines system variables (STATE, HERE, LATEST, BASE, etc.)
6. Compiles cold_start entry point
7. Calls META-CHECK
8. Sets T-SIZE

### Phase B: Verification

The metacompiled x86 kernel should boot in QEMU:

```bash
# Extract target image to file
# (META-SAVE writes T-IMAGE to blocks, then extract)
make run-meta               # boot metacompiled kernel
```

Verification:
- Kernel boots to "ok" prompt
- `3 4 + .` → `7`
- `: SQUARE DUP * ; 5 SQUARE .` → `25`
- `WORDS` shows all expected words
- Behavioral match, not byte-for-byte match

### Phase C: Cross-Compile (x86 → ARM64)

```forth
USING META-COMPILER
USING TARGET-ARM64

META-COMPILE-ARM64          \ builds ARM64 kernel
META-SAVE                   \ write to SD card image
```

Test with `qemu-system-aarch64`.

---

## Implementation Phases

### Phase A: Complete HOST Vocabulary (~30 new words)

**Step A1: Factor out T-C, and T-,**
Extract from inline code in T-HEADER, T-CODE, T-COLON. Refactor existing words to call them. Test: META-BUILD still produces same 3-word demo.

**Step A2: Target memory access (7 words)**
T-C@, T-@, T-C!, T-!, T-ALLOT, T-ALIGN, and standalone T-C,/T-,.
Test: can read/write arbitrary positions in T-IMAGE.

**Step A3: Runtime address variables (7 variables)**
DOLIT-ADDR, DOBRANCH-ADDR, DO0BRANCH-ADDR, DOEXIT-ADDR, DOCREATE-ADDR, DOCON-ADDR, DOVOC-ADDR.
No test needed — just variable definitions.

**Step A4: Defining words (4 words)**
T-VARIABLE, T-CONSTANT, T-IMMEDIATE, T-CREATE.
Test: define a target VARIABLE and CONSTANT, inspect T-IMAGE.

**Step A5: Forward references (4 words)**
FORWARD, RESOLVE, T-FORWARD,, META-CHECK.
Test: declare forward ref, use it, resolve it, verify META-CHECK reports clean.

**Step A6: Target compilation state (6 words)**
T-STATE, T-], T-[, T-LITERAL, T-', T-COMPILE,.
Test: compile a simple colon definition with a literal.

**Step A7: Control flow (12 words)**
T-IF, T-THEN, T-ELSE, T-BEGIN, T-UNTIL, T-AGAIN, T-WHILE, T-REPEAT, T-DO, T-LOOP, T-+LOOP, T-;.
Test: compile IF/THEN, BEGIN/UNTIL into target, inspect branch offsets.

**Step A8: Twin headers + context switching (6 words)**
T-TWIN, IN-META, IN-TARGET, [FORTH], [META], D#/H#.
Test: define a CODE word, verify twin is created, verify twin compiles address when used in T-] mode.

### Phase B: x86 Self-Rebuild

**Step B1: Build EXIT + stack primitives (10 words)**
EXIT, DROP, DUP, SWAP, OVER, ROT, NIP, TUCK, DEPTH, ?DUP.
Test: inspect target image, verify code matches kernel.

**Step B2: Build arithmetic + logic (15 words)**
+, -, *, /, MOD, /MOD, NEGATE, ABS, MIN, MAX, AND, OR, XOR, INVERT, LSHIFT, RSHIFT.

**Step B3: Build memory access (10 words)**
@, !, C@, C!, W@, W!, +!, FILL, CMOVE, CMOVE>.

**Step B4: Build I/O + compiler (20 words)**
EMIT, KEY, CR, TYPE, ., INTERPRET, :, ;, CONSTANT, VARIABLE, etc.

**Step B5: Build cold_start + boot**
The entry point: INTERPRET in infinite loop. System variables. VGA init. Serial init.

**Step B6: Boot test**
Save image, boot in QEMU, verify "ok" prompt and basic operations.

### Phase C: ARM64 Cross-Compile

**Step C1: Write target-arm64.fth**
ARM64 instruction encoding for NEXT, DOCOL, DOCON, DOCREATE, EXIT.
Register conventions: X28=IP, X27=RSP, SP=DSP, X0=W.

**Step C2: Build ARM64 primitives**
Same word list as Phase B but with ARM64 assembly.

**Step C3: Boot test**
`qemu-system-aarch64` with the generated image.

---

## Critical Design Constraints

1. **HEX/DECIMAL are runtime, not IMMEDIATE.** Define all numeric constants outside colon definitions. The HEX/DECIMAL trap (bug #20) applies equally to metacompiler source.

2. **No forward references in Forth source.** Words must be defined before use. The metacompiler's own FORWARD/RESOLVE mechanism is for TARGET code, not for the metacompiler's own definitions.

3. **BRANCH vs DOLOOP offset difference.** BRANCH uses `add esi,[esi]` (offset = target - offset_cell). DOLOOP uses `lodsd; add esi,eax` (offset = target - offset_cell - 4). Bug #12/#19 lesson — T-UNTIL/T-AGAIN use BRANCH formula, T-LOOP uses DOLOOP formula.

4. **T-IMAGE is in host dictionary space.** CREATE'd buffer. All target addresses are relative to T-ORG (0x7E00). The host address is `T-IMAGE + (target_addr - T-ORG)`.

5. **Twin headers are IMMEDIATE.** When T-CODE or T-COLON creates a target word, the host twin must be IMMEDIATE so it compiles the target CFA during T-] mode.

6. **Our kernel lacks DODOES.** Only DOCOL, DOCON, DOCREATE, DOVOC exist as runtimes. Arbitrary CREATE...DOES> in the metacompiler is deferred — use special-case T-VARIABLE, T-CONSTANT, T-VOCABULARY instead.

---

## Testing Strategy

```bash
make test                   # existing tests must still pass
make test-vocabs            # META-COMPILER loads from blocks
```

Phase A testing (HOST vocabulary):
- META-BUILD still works (backward compatible)
- New words accessible via USING META-COMPILER
- T-C,/T-, write correct bytes to T-IMAGE
- Forward refs: FORWARD/RESOLVE cycle works
- Control flow: T-IF/T-THEN branch offsets correct

Phase B testing (self-rebuild):
- META-COMPILE-X86 completes without errors
- META-CHECK reports 0 unresolved
- META-SIZE matches expected kernel size (~33KB)
- Metacompiled kernel boots in QEMU
- Basic Forth operations work

---

## File Structure

```
forth/dict/
├── meta-compiler.fth       extend from 136 to ~600 lines
├── target-x86.fth          ~150 lines (x86 assembly patterns)
└── target-arm64.fth        ~150 lines (Phase C, ARM64 patterns)
```

The meta-compiler.fth stays as a block-loadable vocabulary. It is NOT embedded (too large, not needed at boot). Load sequence:

```forth
USING X86-ASM               \ assembler mnemonics
USING META-COMPILER          \ metacompiler words
```

---

## Reference Materials

- `~/taygeta/metacompiler-refs/METACOMPILER-SYNTHESIS.md` — complete word catalog with stack effects, execution contexts, and design rationale (798 lines, 7 sources)
- `~/taygeta/metacompiler-refs/sources/META86.SEQ` — Laxen & Perry F83 metacompiler (703 lines)
- `~/taygeta/metacompiler-refs/sources/metavocs.txt` — Appelman multi-vocabulary enhancement
- `docs/taygeta/eforth/EFORTH.SRC` — C.H. Ting eForth implementation
- `src/kernel/forth.asm` — the kernel being rebuilt (4,879 lines, the ground truth)
