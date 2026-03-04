# Design: Four Major Features — ReactOS Validation, Drivers, Block Editor, Metacompiler

**Date:** 2026-03-04
**Status:** Approved for implementation
**Scope:** ReactOS real-world validation, six priority drivers, Vi-like block editor, self-hosting metacompiler

---

## Execution Order

Bottom-up — each layer builds on the previous:

1. ReactOS serial.sys validation (validates translator pipeline)
2. PIT Timer driver (foundation for timing/multitasking)
3. PS/2 Keyboard driver (proper input handling)
4. PS/2 Mouse driver (completes input subsystem)
5. PCI Bus enumeration (device discovery)
6. NE2000 Network driver (communication)
7. VGA Graphics driver (graphical output)
8. Block Editor (uses keyboard + VGA)
9. Metacompiler (capstone — uses everything)

---

## Feature 1: ReactOS serial.sys Real-World Validation

### Goal

Run a real Windows serial port driver through the translator pipeline and validate
that the output captures the same hardware semantics as the hand-written
serial-16550.fth reference vocabulary.

### Approach

The fetch script (`tools/translator/scripts/fetch-reactos-serial.sh`) and comparison
framework (`test_ghidra_compare.c`) already exist. This is pipeline validation.

### Steps

1. Download ReactOS serial.sys (GPL, real 16550 UART driver)
   - Use fetch script or manual ISO extraction
   - ReactOS drivers are native PE32, same format as our synthetic tests

2. Generate Ghidra fixture:
   - `make ghidra-fixtures DRIVER=serial.sys`
   - Produces JSON semantic report (ports, HAL calls, imports)

3. Run through translator pipeline:
   - `translator -t forth serial.sys`
   - Generates .fth vocabulary file

4. Compare against reference:
   - Automated: `make test-ghidra-compare` with real fixtures
   - Manual: diff generated .fth against serial-16550.fth

5. Fix pipeline issues:
   - Real drivers are larger — may hit untested x86 opcodes
   - May have HAL call patterns not in synthetic drivers
   - Each fix gets a regression test

### Success Criteria

- `make test-ghidra-compare` passes with real serial.sys fixtures
- Generated .fth contains recognizable UART register definitions
- Generated .fth contains port I/O words mapping to COM1 0x3F8-0x3FF
- No false negatives (translator finds everything Ghidra found)

---

## Feature 2: Priority Drivers (Six Forth Vocabularies)

### Common Pattern

Every driver follows the serial-16550.fth vocabulary structure:

```forth
VOCABULARY <DRIVER-NAME>
<DRIVER-NAME> DEFINITIONS
\ CATALOG: <DRIVER-NAME>
\ CATEGORY: <category>
\ PLATFORM: x86
\ REQUIRES: HARDWARE ( C@-PORT C!-PORT ... )
\ PORTS: <port-range>
\ IRQ: <irq-number>
HEX
<port-constants>
<register-offsets>
<base-variable-and-accessor>
<status-words>
<protocol-words>
FORTH DEFINITIONS
```

Each driver gets:
- A `.fth` file in `forth/dict/`
- Catalog header with REQUIRES dependencies
- Integration into `write-catalog.py`
- A QEMU-based regression test in `tests/`

### Platform Dictionary Schema (Extended)

```
\ CATALOG: <name>              Required. Vocabulary name.
\ CATEGORY: <category>         Required. serial|timer|keyboard|mouse|pci|network|video|system
\ PLATFORM: <platform>         Required. x86|arm64|riscv|all
\ SOURCE: <origin>             Required. hand-written|auto-extracted|metacompiled
\ SOURCE-BINARY: <file>        Optional. Original binary if auto-extracted.
\ VENDOR-ID: <hex>             Optional. PCI vendor ID.
\ DEVICE-ID: <hex>             Optional. PCI device ID.
\ PORTS: <range>               Optional. I/O port range (e.g., 0x3F8-0x3FF).
\ MMIO: <range>                Optional. Memory-mapped I/O range.
\ IRQ: <number>                Optional. Interrupt request line.
\ DMA: <channel>               Optional. DMA channel.
\ CONFIDENCE: <level>          Required. high|medium|low
\ REQUIRES: <vocab> ( words )  Required. One line per dependency.
```

### Driver 2a: PIT Timer (i8254)

**Category:** timer
**Ports:** 0x40-0x43
**IRQ:** 0

**Register constants:**
- PIT-CH0 (0x40) — Channel 0, connected to IRQ0
- PIT-CH1 (0x41) — Channel 1, memory refresh (not used)
- PIT-CH2 (0x42) — Channel 2, PC speaker
- PIT-CMD (0x43) — Command register

**Words:**
- `PIT-INIT ( hz -- )` — Set channel 0 frequency. Write mode 2 (rate generator)
  to command reg, then 16-bit divisor (1193182 / hz) to CH0 low/high bytes.
- `PIT-READ ( -- count )` — Latch and read current counter value.
- `TICK-COUNT ( -- u )` — Return current tick count (incremented by IRQ0 handler).
- `MS-WAIT ( ms -- )` — Blocking delay using tick count.
- `TICKS/SEC ( -- u )` — Current tick rate.

**IRQ0 handler:**
- Increment TICK-COUNT variable
- Send EOI to PIC (port 0x20, value 0x20)
- IRET

**PIC setup required:**
- Unmask IRQ0 in PIC master (port 0x21)
- The kernel's boot sequence should initialize PIC with standard ISA mapping
  (IRQ0 → INT 0x20)

**IDT integration:**
- Need IDT entry for INT 0x20 pointing to the timer ISR
- ISR saves/restores registers, calls Forth tick handler
- This is the first interrupt-driven driver — establishes the ISR pattern

### Driver 2b: PS/2 Keyboard (i8042)

**Category:** keyboard
**Ports:** 0x60 (data), 0x64 (status/command)
**IRQ:** 1

**Words:**
- `KB-INIT ( -- )` — Enable keyboard, set scan code set 2, enable IRQ1
- `KB-KEY ( -- char )` — Get next ASCII character from ring buffer (blocking)
- `KB-KEY? ( -- flag )` — True if key available in buffer
- `KB-SCAN ( -- scancode )` — Get raw scancode (non-blocking, 0 if empty)
- `KB-STATUS ( -- byte )` — Read i8042 status register
- `KB-LED! ( mask -- )` — Set keyboard LEDs (Num/Caps/Scroll Lock)

**Internal:**
- 16-byte ring buffer filled by IRQ1 handler
- Scancode-to-ASCII translation table (US layout)
- Modifier state tracking: shift (bit 0), ctrl (bit 1), alt (bit 2)
- Extended scancode handling (E0 prefix)

**IRQ1 handler:**
- Read scancode from port 0x60
- Translate to ASCII (with modifier state)
- Store in ring buffer if not full
- Send EOI to PIC

### Driver 2c: PS/2 Mouse (i8042 aux)

**Category:** mouse
**Ports:** 0x60 (data), 0x64 (status/command)
**IRQ:** 12

**Words:**
- `MOUSE-INIT ( -- )` — Enable auxiliary device, set sample rate, enable IRQ12
- `MOUSE-XY ( -- x y )` — Current accumulated position
- `MOUSE-BUTTONS ( -- mask )` — Button state (bit0=left, bit1=right, bit2=middle)
- `MOUSE-MOVED? ( -- flag )` — True if position changed since last read
- `MOUSE-RESET-DELTA ( -- )` — Clear movement accumulator
- `MOUSE-BOUNDS! ( xmax ymax -- )` — Set position clamp limits

**Internal:**
- 3-byte packet assembly (byte 0: buttons+signs, byte 1: dx, byte 2: dy)
- Sign extension from 9-bit to 32-bit (bit 4/5 of byte 0 are sign bits)
- Position accumulation with bounds clamping
- Packet state machine (waiting for byte 0, 1, or 2)

**i8042 auxiliary protocol:**
- Write 0xD4 to port 0x64, then data byte to port 0x60 (send to mouse)
- Read from port 0x60 after checking status bit 5 (aux data available)
- Init sequence: Reset (0xFF), Set Sample Rate (0xF3, rate), Enable (0xF4)

### Driver 2d: PCI Bus Enumeration

**Category:** pci
**Ports:** 0xCF8 (address), 0xCFC (data)
**IRQ:** none

Builds on existing PCI-READ/PCI-WRITE/PCI-SCAN from hardware.fth.

**Words:**
- `PCI-FIND-DEVICE ( vendor device -- bus dev func true | false )` — Find first
  device matching vendor:device ID. Scans all buses/devices/functions.
- `PCI-BAR@ ( bus dev func bar# -- addr )` — Read Base Address Register.
  Determines if memory-mapped or I/O-mapped, returns base address.
- `PCI-BAR-SIZE ( bus dev func bar# -- size )` — Determine BAR size by writing
  all-1s, reading back, masking type bits.
- `PCI-ENABLE ( bus dev func -- )` — Enable I/O and memory space in command register.
- `PCI-IRQ@ ( bus dev func -- irq )` — Read interrupt line register.
- `PCI-LIST ( -- )` — Print all discovered PCI devices with vendor:device IDs.
- `PCI-CLASS@ ( bus dev func -- class subclass )` — Read class/subclass codes.

**Device table:**
- Fixed-size table at compile time: 32 entries max
- Each entry: bus(1) dev(1) func(1) pad(1) vendor(2) device(2) class(1) subclass(1) irq(1) pad(1) = 12 bytes
- PCI-SCAN-ALL fills the table at boot
- PCI-FIND-DEVICE searches the table (fast) instead of re-scanning hardware

### Driver 2e: NE2000 Network (ne2k_pci)

**Category:** network
**PCI-ID:** 10EC:8029 (Realtek RTL8029, NE2000-compatible, QEMU default)
**Ports:** PCI BAR0 (I/O base, typically 0xC000+)
**IRQ:** PCI interrupt line (typically 11)

**Words:**
- `NE2K-INIT ( -- )` — Find device via PCI, read BAR0, reset, configure ring buffer,
  set MAC address, enable RX/TX.
- `NE2K-SEND ( addr len -- )` — Transmit Ethernet frame. Copy to NIC memory via
  remote DMA write, then trigger send.
- `NE2K-RECV ( addr -- len )` — Receive next packet from ring buffer. Returns 0
  if no packet available. Copies from NIC memory via remote DMA read.
- `NE2K-RECV? ( -- flag )` — True if packet available in receive ring.
- `NE2K-MAC@ ( addr -- )` — Copy 6-byte MAC address to addr.
- `NE2K-STATS ( -- )` — Print RX/TX counters.

**NE2000 register map (offsets from I/O base):**
- 0x00: Command register (page select, start/stop, DMA mode)
- 0x01-0x0F: Page 0 registers (PSTART, PSTOP, BNRY, ISR, etc.)
- Page 1: Physical address (PAR0-5), current page (CURR), multicast (MAR0-7)
- 0x10: Data port (remote DMA read/write)
- 0x1F: Reset port

**Remote DMA protocol:**
- Set RSAR (start address in NIC memory) and RBCR (byte count)
- Set command register for remote read or write
- Read/write data port (0x10) repeatedly
- Check ISR bit 6 (RDC) for completion

**Receive ring buffer:**
- NIC memory 0x4000-0xBFFF configured as ring
- BNRY = last page read by host, CURR = next page NIC writes to
- Each packet has 4-byte header: status, next_page, length_lo, length_hi

### Driver 2f: VGA Graphics (Bochs VBE)

**Category:** video
**Ports:** 0x01CE (VBE index), 0x01CF (VBE data)
**MMIO:** 0xE0000000 (LFB, linear framebuffer — via PCI BAR0 of VGA device)
**IRQ:** none

**Words:**
- `VGA-MODE! ( width height bpp -- )` — Set graphics mode via VBE registers.
  Disable VBE, set X/Y resolution and BPP, enable VBE with LFB.
- `VGA-TEXT ( -- )` — Return to 80x25 text mode (write 0 to VBE enable register).
- `VGA-PIXEL! ( color x y -- )` — Set pixel. Computes LFB offset = y*pitch + x*bpp/8.
- `VGA-LINE ( color x1 y1 x2 y2 -- )` — Bresenham line drawing.
- `VGA-RECT ( color x y w h -- )` — Filled rectangle.
- `VGA-CLEAR ( color -- )` — Fill entire framebuffer.
- `VGA-HLINE ( color x y len -- )` — Fast horizontal line (optimized: REP STOSD).
- `VGA-CHAR ( char color x y -- )` — Draw character using built-in 8x16 font bitmap.
- `VGA-STRING ( addr len color x y -- )` — Draw string.

**Bochs VBE register indices:**
- 0x00: VBE_DISPI_ID (read to verify VBE support)
- 0x01: XRES
- 0x02: YRES
- 0x03: BPP (8, 15, 16, 24, 32)
- 0x04: ENABLE (bit 0 = enable, bit 1 = LFB mode, bit 6 = no clear)
- 0x06: VIRT_WIDTH (for scrolling/double-buffering)
- 0x07: VIRT_HEIGHT
- 0x08: X_OFFSET (for page flipping)
- 0x09: Y_OFFSET

**Mode 13h fallback (320x200x256):**
- If VBE not available, fall back to legacy mode 13h via INT 10h (would need
  real-mode thunk or direct VGA register programming)
- Framebuffer at 0xA0000 (64KB window)

**LFB discovery:**
- PCI scan for VGA device (class 0x03, subclass 0x00)
- Read BAR0 for LFB base address (typically 0xE0000000 in QEMU)

---

## Feature 3: Block Editor (Vi-like)

### Architecture

A modal screen editor implemented as a Forth VOCABULARY, loaded from blocks.
Operates on one block at a time (16 lines x 64 chars). Uses VGA direct memory
writes for display and keyboard driver for input.

### Screen Layout

```
+------------------------------------------------------------------+
|Line 0: VOCABULARY SERIAL-16550                                    |
|Line 1: SERIAL-16550 DEFINITIONS                                  |
|Line 2: \ CATALOG: SERIAL-16550                                   |
|...                                                                |
|Line 15: FORTH DEFINITIONS                                        |
|                                                                    |
|-- Block 3 ---- Line 5, Col 12 ---- INSERT ---- [modified] -------|
|:                                                                   |
+------------------------------------------------------------------+
```

Lines 0-15: Block content (16 lines x 64 chars = 1024 bytes)
Line 16: Status bar (inverse video, attribute 0x70)
Line 17: Command line (for : commands and search)

### Modes

**COMMAND mode (default):**
- h/j/k/l — move cursor left/down/up/right
- 0 — beginning of line
- $ — end of line (last non-space character)
- w/b — word forward/backward
- gg — go to first line
- G — go to last line
- i — enter INSERT mode at cursor
- a — enter INSERT mode after cursor
- A — enter INSERT mode at end of line
- o — open line below (shift lines 14→15, 13→14, ..., cursor+1→cursor+2; blank cursor+1)
- O — open line above
- x — delete character at cursor
- dd — delete line (fill with spaces, shift lines up)
- yy — yank (copy) line to clipboard
- p — paste clipboard below current line
- P — paste above
- u — undo last change (single level)
- /pattern — search forward for pattern
- n — repeat last search
- :w — save (UPDATE + SAVE-BUFFERS)
- :q — quit (warn if modified)
- :wq — save and quit
- :e N — edit block N
- :n — next block
- :N — previous block (or :p)

**INSERT mode:**
- Typing inserts characters, shifting line right
- Backspace deletes character behind cursor
- ESC returns to COMMAND mode
- Characters beyond column 63 are rejected (beep)

### Key Data Structures

```forth
VARIABLE ED-BLK        \ Current block number
VARIABLE ED-ROW        \ Cursor row (0-15)
VARIABLE ED-COL        \ Cursor column (0-63)
VARIABLE ED-MODE       \ 0=command, 1=insert, 2=ex
VARIABLE ED-DIRTY      \ Modified flag
CREATE ED-YANK 64 ALLOT  \ Yanked line buffer
CREATE ED-SEARCH 64 ALLOT  \ Search pattern buffer
CREATE ED-UNDO 1024 ALLOT  \ Undo buffer (snapshot of block before last change)
```

### Entry Point

```forth
: EDIT ( blk# -- )
    ED-BLK !
    BLOCK DROP          \ Load block into buffer
    0 ED-ROW !  0 ED-COL !
    0 ED-MODE !  0 ED-DIRTY !
    ED-UNDO-SAVE        \ Save initial state for undo
    ED-REFRESH           \ Draw screen
    BEGIN ED-LOOP 0= UNTIL  \ Main loop until quit
;
```

### VGA Direct Access

The editor writes directly to VGA memory at 0xB8000:
- Each character cell = 2 bytes (char + attribute)
- Offset = (row * 80 + col) * 2
- Normal text: attribute 0x07 (white on black)
- Status bar: attribute 0x70 (black on white)
- Cursor line: attribute 0x0F (bright white on black)

### Dependencies

REQUIRES: HARDWARE (for direct VGA memory access)
REQUIRES: PS2-KEYBOARD (for KB-KEY, KB-SCAN)

---

## Feature 4: Metacompiler (Full Self-Hosting)

### Goal

The running Forth system compiles a new kernel from source blocks, producing a
binary image that is functionally equivalent to the NASM-assembled kernel.

### Architecture: Three Vocabulary Layers

**HOST vocabulary** — Normal Forth words that execute during meta-compilation.
Loops, conditionals, string handling, file I/O. These words run on the current
system and are NOT compiled into the target.

**TARGET vocabulary** — Represents the output binary. Each word in TARGET
corresponds to a word in the new kernel. `T-HERE` tracks the compilation pointer
in the target image. `T-,` compiles a cell. Creating a TARGET word records its
address in the target image.

**META vocabulary** — Cross-compiler words that bridge HOST and TARGET.
When you say `META: DUP`, META defines a word called DUP that:
- In compile state: compiles the TARGET address of DUP into the current definition
- In interpret state: executes the HOST version of DUP

### Memory Model

Target image built in extended memory (starting at 0x100000, 128KB buffer).
Target addresses start at 0x7E00 (matching the real kernel load address).

```
Host system memory:
  0x100000 - 0x11FFFF : Target image buffer (128KB)
  0x120000 - 0x120FFF : Target symbol table (4KB)
  0x121000 - 0x121FFF : Fixup list for forward references (4KB)

Target image layout (virtual addresses starting at 0x7E00):
  0x7E00 - 0x7EFF   : Kernel entry + NEXT macro
  0x7F00 - ...       : CODE words (assembly primitives)
  ...                : COLON definitions (threaded code)
  ...                : System variables
  0x28000            : Variable area (same as current kernel)
```

### x86 Assembler in Forth

Required for defining CODE words in the metacompiler. Minimal subset:

```forth
VOCABULARY X86-ASM
X86-ASM DEFINITIONS

\ Registers (encoded as ModR/M values)
0 CONSTANT %EAX   1 CONSTANT %ECX   2 CONSTANT %EDX   3 CONSTANT %EBX
4 CONSTANT %ESP   5 CONSTANT %EBP   6 CONSTANT %ESI   7 CONSTANT %EDI

\ Core instructions
: PUSH, ( reg -- )    $50 + T-C, ;
: POP, ( reg -- )     $58 + T-C, ;
: RET, ( -- )         $C3 T-C, ;
: NOP, ( -- )         $90 T-C, ;
: LODSD, ( -- )       $AD T-C, ;
: STOSD, ( -- )       $AB T-C, ;

\ MOV reg, reg
: MOV, ( src dst -- )  $89 T-C,  SWAP 3 LSHIFT OR $C0 OR T-C, ;

\ MOV reg, [reg]
: MOV[], ( src dst -- ) $8B T-C,  SWAP 3 LSHIFT OR T-C, ;

\ JMP [reg]
: JMP[], ( reg -- )   $FF T-C,  $20 OR T-C, ;

\ ADD, SUB, XOR, etc. with ModR/M encoding
: ADD, ( src dst -- )  $01 T-C,  SWAP 3 LSHIFT OR $C0 OR T-C, ;
: SUB, ( src dst -- )  $29 T-C,  SWAP 3 LSHIFT OR $C0 OR T-C, ;
: XOR, ( src dst -- )  $31 T-C,  SWAP 3 LSHIFT OR $C0 OR T-C, ;

\ Immediate operations
: ADD-IMM, ( imm32 dst -- ) $81 T-C,  $C0 OR T-C,  T-, ;
: MOV-IMM, ( imm32 dst -- ) $B8 + T-C,  T-, ;

FORTH DEFINITIONS
```

### META Defining Words

```forth
\ Define a CODE word in the target
: CODE: ( "name" -- )
    TARGET-CREATE          \ Create header in target dictionary
    T-HERE @ OVER T-!     \ CFA = current target address
    X86-ASM                \ Switch to assembler vocabulary
;
: END-CODE ( -- )
    FORTH                  \ Switch back
;

\ Define a COLON word in the target
: : ( "name" -- )
    TARGET-CREATE          \ Create header in target dictionary
    T-DOCOL T-,           \ Compile DOCOL address as CFA
    ]                      \ Enter compile state
;
: ; ( -- )
    T-EXIT T-,            \ Compile EXIT
    [                      \ Return to interpret state
; IMMEDIATE
```

### Two-Pass Compilation

**Pass 1:** Process all source blocks sequentially:
- CODE: words emit machine code directly (no forward reference issues)
- COLON definitions compile XTs — forward references get a placeholder (0)
  and are recorded in the fixup list
- All word addresses recorded in symbol table

**Pass 2:** Walk the fixup list:
- For each unresolved reference, look up the symbol table
- Patch the placeholder with the resolved address
- Verify no unresolved symbols remain

### Bootstrap Sequence

```forth
\ Load from blocks (assumes catalog-resolver is already loaded)
S" META-COMPILER" LOAD-VOCAB

\ Build new kernel
META-BUILD   ( -- )
\ Internally:
\   1. Initialize target image buffer
\   2. Process kernel source blocks (Pass 1)
\   3. Resolve forward references (Pass 2)
\   4. Verify target image integrity

\ Save to disk
META-SAVE    ( -- )
\ Writes target image to floppy/block storage

\ Verify
META-VERIFY  ( -- )
\ Boot new image in QEMU, run test suite, compare results
```

### What Gets Metacompiled

In order of compilation (dependencies resolved automatically):

1. Inner interpreter: NEXT, DOCOL, EXIT, LIT, BRANCH, 0BRANCH
2. Stack primitives: DROP, DUP, SWAP, OVER, ROT, ?DUP, DEPTH, etc.
3. Arithmetic: +, -, *, /, MOD, /MOD, NEGATE, ABS
4. Logic: AND, OR, XOR, INVERT
5. Comparison: =, <>, <, >, 0=, 0<, U<
6. Memory: @, !, C@, C!, +!, FILL, MOVE, CMOVE
7. I/O primitives: EMIT, KEY, TYPE, CR (serial + VGA)
8. Port I/O: INB, OUTB, INW, OUTW
9. Number formatting: ., .S, U., .R, <# # #S #> HOLD SIGN
10. Interpreter: WORD, FIND, EXECUTE, INTERPRET, NUMBER
11. Compiler: CREATE, :, ;, IMMEDIATE, LITERAL, COMPILE, [, ]
12. Control flow: IF, ELSE, THEN, BEGIN, UNTIL, WHILE, REPEAT, DO, LOOP, +LOOP
13. Defining words: VARIABLE, CONSTANT, DOES>
14. String: S", .", COUNT, TYPE
15. Block I/O: BLOCK, BUFFER, UPDATE, SAVE-BUFFERS, LOAD, THRU
16. ATA PIO: ata_read_sector, ata_write_sector
17. Dictionary: WORDS, SEE, FORGET, VOCABULARY, DEFINITIONS
18. System variables: STATE, HERE, LATEST, BASE, BLK, SCR

### Success Criteria

- `META-BUILD` completes without errors
- New kernel boots in QEMU
- New kernel passes all 34 existing automated tests
- Dictionary word count matches (178+)
- Block loading works (LOAD, THRU)
- Vocabulary system works (USING, ORDER)

---

## Architectural Gap: .NET CLR Support

### Current State

The PE loader handles native PE32/PE32+ only. No .NET detection exists.
DATA_DIR index 14 (COM_DESCRIPTOR) is not checked.

### Design: P/Invoke Extraction (Not Full IL Translation)

Most .NET assemblies that access hardware use P/Invoke to call native DLLs.
We extract these signatures rather than translating IL bytecode.

**Phase 1 (Detection):**
- Add DATA_DIR_CLR = 14 to pe_format.h
- Check for CLR header in PE loader
- Set `ctx->is_dotnet = true` flag
- Print warning: ".NET assembly detected, extracting P/Invoke signatures"

**Phase 2 (P/Invoke extraction):**
- Parse .NET metadata stream (#~ or #- heap)
- Read ImplMap table (P/Invoke declarations)
- For each P/Invoke: extract module name (DLL), function name, calling convention
- Feed these into the existing semantic analyzer as if they were IAT imports
- Generate Forth wrappers for the native functions

**Phase 3 (Future — full IL):**
- IL opcode decoder (200+ opcodes, stack-based like Forth)
- IL → UIR translation
- Type system handling (value types only — no GC objects)
- This is a large undertaking, deferred until P/Invoke extraction proves the concept

### Not In Scope

- Garbage collector
- Object system / vtable dispatch
- Exception handling (SEH → Forth CATCH/THROW mapping)
- Generics, reflection, delegates

---

## Architectural Gap: Bootstrap Path

### Self-Hosting First, Cross-Compilation Second

**Track A (this design):** Self-hosting metacompiler for x86.
The running Forth system rebuilds itself. Requires Forth-based x86 assembler.
This is the traditional Forth milestone and validates the architecture.

**Track B (future):** Host-side cross-compiler.
A C program (or Forth on the host) reads the same source blocks and produces
a kernel binary for a different target (ARM64, RISC-V). Reuses the UIR pipeline
already built in the translator. The cross-compiler shares source blocks with
the metacompiler — same Forth definitions, different code generators.

**Track C (future):** CPU transcode tables.
The OS detects its CPU at boot (CPUID for x86, device tree for ARM) and selects
the appropriate CODE word implementations. This requires Track B's cross-compiler
to pre-generate CODE words for each target, stored in separate block ranges.

The key insight: **Forth source blocks are architecture-neutral** (COLON definitions
are pure Forth). Only CODE words are architecture-specific. The metacompiler's
x86 assembler vocabulary gets swapped for an ARM64 assembler vocabulary to retarget.

---

## Testing Strategy

### Per-Driver Tests

Each driver vocabulary gets a QEMU regression test:
- Start QEMU with appropriate device configuration
- Load vocabulary via THRU
- Exercise key words
- Verify expected output on serial console

Example (PIT Timer):
```python
# tests/test_pit_timer.py
send("2 17 THRU")           # Load catalog-resolver + vocabs
send("USING PIT-TIMER")     # Load timer vocabulary
send("100 PIT-INIT")        # Set 100 Hz
send("TICK-COUNT . CR")     # Should print a number
wait(0.1)                   # Wait 100ms
send("TICK-COUNT . CR")     # Should be ~10 ticks later
```

### Block Editor Tests

- Interactive test: start QEMU, load editor, verify screen output
- Automated: send keystrokes via serial, verify block content changes

### Metacompiler Tests

- Build new kernel with META-BUILD
- Boot new kernel in separate QEMU instance
- Run full test suite against new kernel
- Compare test results with original kernel

---

## Dependency Graph

```
HARDWARE (exists)
    ├── PIT-TIMER
    │       └── (provides timing for all drivers)
    ├── PS2-KEYBOARD
    │       └── EDITOR (uses KB-KEY)
    ├── PS2-MOUSE
    ├── PCI-ENUM
    │       ├── NE2000-NET (uses PCI-FIND-DEVICE)
    │       └── VGA-GRAPHICS (uses PCI BAR for LFB)
    └── SERIAL-16550 (exists)

X86-ASM (new)
    └── META-COMPILER (uses assembler for CODE words)
            └── (rebuilds entire kernel)
```
