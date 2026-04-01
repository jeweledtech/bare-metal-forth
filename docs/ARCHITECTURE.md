# Bare-Metal Forth Architecture

## Overview

Bare-Metal Forth is a direct-threaded Forth-83 system that boots from bare metal on x86 hardware. The entire kernel is one assembly file (4,879 lines). It runs in 32-bit protected mode with no paging, giving identity-mapped physical memory access suitable for DMA.

## Boot Process

### Stage 1: BIOS to Protected Mode

1. BIOS loads boot sector (512 bytes) to `0x7C00`
2. Bootloader initializes segment registers
3. Enables A20 gate
4. Loads kernel (128 sectors = 64KB) from disk to `0x7E00`
5. Sets up GDT (flat model: code and data segments spanning full 4GB)
6. Switches to protected mode (CR0 bit 0, no paging)
7. Far jumps to kernel entry point

### Stage 2: Kernel Initialization

1. Set up data stack at `0x7C00` (grows down into conventional memory)
2. Set up return stack at `0x20000` (grows down)
3. Initialize dictionary pointer at `0x30000`
4. Set up IDT at `0x29400` (256 entries) and remap PIC (IRQs 0x20-0x2F)
5. Install ISR stubs for timer (IRQ0), keyboard (IRQ1), mouse (IRQ12)
6. Initialize VGA text mode and serial port (COM1)
7. Evaluate embedded vocabulary blob (6 vocabularies compiled into kernel)
8. Enter outer interpreter (cold_start: INTERPRET, BRANCH, -8)

## Memory Map

```
Address Range           Size        Purpose
────────────────────────────────────────────────────────────────
0x00000 - 0x004FF       1.25 KB     IVT + BIOS Data Area
0x00500 - 0x07BFF       ~30 KB      Data stack (grows DOWN from 0x7C00)
0x07C00 - 0x07DFF       512 B       Boot sector
0x07E00 - 0x17DFF       64 KB       Kernel code (4,879 lines of x86 asm)
0x17E00 - 0x1FFFF       ~33 KB      Embedded vocabulary blob (NUL-terminated)
0x20000                              Return stack top (grows DOWN)
0x28000 - 0x2804F       80 B        System variables
0x28060 - 0x28097       56 B        Block buffer headers (4 x 12 bytes)
0x28100 - 0x281FF       256 B       Terminal Input Buffer (TIB)
0x28200 - 0x291FF       4 KB        Block buffers (4 x 1 KB)
0x29200                              Block buffer guard byte (NUL)
0x29400 - 0x29BFF       2 KB        IDT (256 x 8-byte entries)
0x29C00 - 0x29C3F       64 B        ISR hook table (16 IRQ dispatch slots)
0x30000 - 0x7FFFF       320 KB      Dictionary space
0xB8000 - 0xB8F9F       4000 B      VGA text buffer (80 x 25 x 2 bytes)
0x100000 - 0x3FFFFF     3 MB        Physical allocation pool (DMA buffers)
```

### System Variables (0x28000)

| Offset | Name | Purpose |
|--------|------|---------|
| 0x28000 | STATE | 0 = interpreting, non-zero = compiling |
| 0x28004 | HERE | Next free dictionary address |
| 0x28008 | LATEST | Most recent dictionary entry |
| 0x2800C | BASE | Number base (default 10) |
| 0x28010 | TIB | Terminal Input Buffer address |
| 0x28014 | TOIN | Current parse offset into TIB |
| 0x28018 | BLK | Block being loaded (0 = keyboard) |
| 0x2801C | SCR | Last block listed |
| 0x28020 | SEARCH_ORDER | 8-cell vocabulary search order |
| 0x28040 | SEARCH_DEPTH | Active search order depth (1-8) |
| 0x28044 | CURRENT | Vocabulary receiving new definitions |
| 0x28048 | FORTH_LATEST | FORTH vocabulary's latest word |
| 0x2804C | BLOCK_LOADING | Block load state flag |

## Register Conventions

| Register | Forth Name | Purpose |
|----------|------------|---------|
| ESI | IP | Instruction pointer (next cell to execute) |
| EBP | RP | Return stack pointer (grows down) |
| ESP | SP | Data stack pointer (grows down) |
| EAX | W | Working register |
| EBX | - | Scratch |
| ECX | - | Scratch / loop counter |
| EDX | - | Scratch / I/O port number |
| EDI | - | Scratch |

## Threading Model

Direct-threaded code (DTC). Each compiled word contains addresses of code fields (execution tokens). The inner interpreter:

```nasm
%macro NEXT 0
    lodsd           ; EAX = [ESI], ESI += 4
    jmp [eax]       ; jump through code field
%endmacro
```

### Runtime Behaviors

| Runtime | Code Field Points To | Behavior |
|---------|---------------------|----------|
| Primitives | Native x86 code | Execute directly, end with NEXT |
| DOCOL | Colon definition entry | Push IP, set IP to parameter field |
| EXIT | Colon definition exit | Pop IP from return stack |
| DOCON | Constant | Push value from parameter field |
| DOVAR | Variable | Push address of parameter field |
| DOCREATE | CREATE'd word | Push address of data field |
| DODOES | DOES> word | Push data address, enter DOES> code |

### DOCOL / EXIT

```nasm
DOCOL:                          EXIT:
    sub ebp, 4                      mov esi, [ebp]    ; pop IP
    mov [ebp], esi   ; push IP      add ebp, 4
    add eax, 4       ; skip CFA     NEXT
    mov esi, eax     ; enter body
    NEXT
```

## Dictionary Structure

```
┌──────────────────────────────────────┐
│  Link field (4 bytes)                │  → previous entry (or 0)
├──────────────────────────────────────┤
│  Flags + Length (1 byte)             │  bit 7: IMMEDIATE
│                                      │  bit 6: HIDDEN
│                                      │  bits 0-5: name length
├──────────────────────────────────────┤
│  Name (variable, padded to 4-byte)   │
├──────────────────────────────────────┤
│  Code field (4 bytes)                │  → native code address
├──────────────────────────────────────┤
│  Parameter field (variable)          │  body of the word
└──────────────────────────────────────┘
```

## Vocabulary System

- 8-slot search order (`SEARCH_ORDER[0..7]`)
- Each slot holds the address of a vocabulary's LATEST cell
- `find_` walks the search order, then falls back to FORTH (prevents core words from becoming invisible)
- `ALSO` duplicates the top of the search order
- `PREVIOUS` removes the top entry
- `USING <vocab>` = `ALSO` + execute vocabulary word
- `VOCABULARY` creates a new vocabulary with its own LATEST chain

## Embedded Vocabularies

Six vocabularies are compiled directly into the kernel binary by `tools/embed-vocabs.py`. The tool strips comments, collapses whitespace, and produces a NUL-terminated ASCII blob. At boot, the kernel evaluates this blob through INTERPRET before entering the interactive REPL.

Embedded vocabs: HARDWARE, PORT-MAPPER, ECHOPORT, PCI-ENUM, RTL8168, AHCI.

## Block Storage

- Each block = 1 KB = 16 lines x 64 characters (space-padded, no newlines)
- ATA PIO driver reads/writes IDE slave disk
- 4-slot LRU buffer cache: each header = `[block#:4][flags:4][age:4]`
- Flags: bit 0 = valid, bit 1 = dirty
- LOAD redirects the interpreter to read from a block buffer
- THRU uses DO/LOOP to load a range of blocks

## Interrupt Infrastructure

- IDT at `0x29400` with 256 entries
- PIC remapped: IRQ 0-7 → INT 0x20-0x27, IRQ 8-15 → INT 0x28-0x2F
- Hardcoded ISRs: timer (IRQ0), keyboard (IRQ1), mouse (IRQ12)
- ISR hook table at `0x29C00` (16 slots) for Forth-level IRQ dispatch
- `IRQ-UNMASK` kernel word unmasks specific IRQ in PIC

## Network Console

`print_char` is the single output path for all text. It:
1. Sends character to serial port (COM1)
2. Buffers character in `net_buf` (256 bytes) if net console is enabled
3. On LF or buffer full: calls `net_flush` to transmit UDP packet
4. Renders character on VGA screen

`net_flush` builds an Ethernet+IP+UDP frame in the RTL8168 TX buffer, computes IP checksum, triggers TX, then polls the ISR TxOK bit to confirm the frame is on the wire before returning.

## Physical Memory Allocation

`PHYS-ALLOC` is a bump allocator for DMA buffers:
- Pool: 0x100000 (1MB) to 0x400000 (4MB)
- Returns page-aligned (4KB) physical addresses
- No paging means virtual = physical (identity-mapped)
- Used by AHCI (command list, FIS, command table, sector buffer) and RTL8168 (TX descriptor, TX buffer)

## Forth-83 Division

Uses floored division (not symmetric/truncated):

```
  dividend = quotient x divisor + remainder
  sign(remainder) = sign(divisor)  OR  remainder = 0
```

After x86 IDIV (which gives symmetric result), correction is applied:
```nasm
; If remainder != 0 AND sign(remainder) != sign(divisor):
;   quotient  -= 1
;   remainder += divisor
```
