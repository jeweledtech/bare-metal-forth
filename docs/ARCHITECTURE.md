# Bare-Metal Forth Architecture

## Overview

Bare-Metal Forth is a minimal, direct-threaded Forth implementation that boots from bare metal on x86 hardware.

## Boot Process

### Stage 1: BIOS to Real Mode

1. BIOS loads boot sector (512 bytes) to `0x7C00`
2. Bootloader initializes segment registers
3. Loads kernel from disk to `0x7E00`
4. Sets up GDT for protected mode
5. Switches to protected mode
6. Jumps to kernel entry point

### Stage 2: Kernel Initialization

1. Initialize data stack at `0x10000`
2. Initialize return stack at `0x20000`
3. Initialize dictionary at `0x30000`
4. Set up VGA text mode
5. Initialize input buffer
6. Enter outer interpreter (QUIT)

## Memory Map

```
Address Range       Size      Purpose
─────────────────────────────────────────────────────────
0x00000 - 0x003FF   1 KB      Interrupt Vector Table
0x00400 - 0x004FF   256 B     BIOS Data Area
0x00500 - 0x07BFF   ~30 KB    Free (conventional memory)
0x07C00 - 0x07DFF   512 B     Boot sector
0x07E00 - 0x0FFFF   ~33 KB    Kernel code
0x10000 - 0x1FFFF   64 KB     Data stack (grows DOWN)
0x20000 - 0x2FFFF   64 KB     Return stack (grows DOWN)
0x30000 - 0x4FFFF   128 KB    Dictionary
0x50000 - 0x500FF   256 B     Input buffer (TIB)
0x50100 - 0x9FFFF   ~319 KB   Free (user programs)
0xA0000 - 0xBFFFF   128 KB    Video memory
  0xB8000 - 0xB8F9F 4000 B      VGA text buffer (80x25x2)
0xC0000 - 0xFFFFF   256 KB    ROM area
```

## Register Conventions

| Register | Forth Name | Purpose |
|----------|------------|---------|
| ESI | IP | Instruction pointer (next word to execute) |
| EBP | RP | Return stack pointer |
| ESP | SP | Data stack pointer |
| EAX | W | Working register, sometimes TOS |
| EBX | - | Scratch |
| ECX | - | Scratch |
| EDX | - | Scratch, I/O ports |
| EDI | - | Scratch |

## Threading Model

Bare-Metal Forth uses **Direct Threaded Code (DTC)**.

### Code Field

Each word's code field contains the address of machine code to execute:

- **Primitives**: Code field points to native x86 instructions
- **Colon definitions**: Code field points to `DOCOL` (enter interpreter)

### NEXT Macro

The inner interpreter:

```nasm
%macro NEXT 0
    lodsd           ; Load [ESI] into EAX, advance ESI by 4
    jmp [eax]       ; Jump to code field address
%endmacro
```

### DOCOL (Enter Colon Definition)

```nasm
DOCOL:
    sub ebp, 4      ; Make room on return stack
    mov [ebp], esi  ; Push current IP
    add eax, 4      ; Skip code field
    mov esi, eax    ; New IP = parameter field
    NEXT
```

### EXIT (Leave Colon Definition)

```nasm
EXIT:
    mov esi, [ebp]  ; Pop saved IP
    add ebp, 4      ; Adjust return stack
    NEXT
```

## Dictionary Structure

Each dictionary entry:

```
┌─────────────────────────────────────────────────────┐
│  Link field (4 bytes)                               │
│    Points to previous dictionary entry              │
├─────────────────────────────────────────────────────┤
│  Flags + Length (1 byte)                            │
│    Bit 7: IMMEDIATE flag                            │
│    Bit 6: HIDDEN flag                               │
│    Bits 0-5: Name length (0-63)                     │
├─────────────────────────────────────────────────────┤
│  Name (variable length)                             │
│    ASCII, not null-terminated                       │
├─────────────────────────────────────────────────────┤
│  Padding (0-3 bytes)                                │
│    Align to 4-byte boundary                         │
├─────────────────────────────────────────────────────┤
│  Code field (4 bytes)                               │
│    Address of machine code to execute               │
├─────────────────────────────────────────────────────┤
│  Parameter field (variable)                         │
│    For primitives: more machine code                │
│    For colon defs: list of word addresses           │
│    For CONSTANT: the constant value                 │
│    For VARIABLE: storage cell                       │
└─────────────────────────────────────────────────────┘
```

### Dictionary Variables

| Variable | Purpose |
|----------|---------|
| LATEST | Points to most recent dictionary entry |
| HERE | Points to next free dictionary location |
| STATE | 0 = interpreting, non-zero = compiling |
| BASE | Number base (default 10) |

## Stacks

### Data Stack

- Grows downward from `0x1FFFF`
- ESP points to top item
- Each cell is 4 bytes (32-bit)
- Stack operations: `PUSH` = `sub esp, 4; mov [esp], eax`

### Return Stack

- Grows downward from `0x2FFFF`
- EBP points to top item
- Used for:
  - Subroutine return addresses
  - Loop counters (DO/LOOP)
  - Temporary storage (>R, R>)

## I/O

### VGA Text Mode

- 80 columns × 25 rows
- 2 bytes per character (char + attribute)
- Base address: `0xB8000`
- Attribute byte: `BG_COLOR << 4 | FG_COLOR`

### Keyboard

- Direct port I/O to 8042 controller
- Port `0x60`: Data port
- Port `0x64`: Status port
- Blocking read: wait for status bit 0

## Forth-83 Division

Uses floored division, not symmetric:

```
  dividend = quotient × divisor + remainder
  
  where: sign(remainder) = sign(divisor)  OR  remainder = 0
```

Implementation adds correction after CPU's IDIV:

```nasm
; If remainder ≠ 0 AND sign(dividend) ≠ sign(divisor):
;   quotient  -= 1
;   remainder += divisor
```

## Word Categories

### Primitives (Assembly)

- Stack: DUP, DROP, SWAP, OVER, ROT, NIP, TUCK
- Arithmetic: +, -, *, /, MOD, /MOD
- Logic: AND, OR, XOR, INVERT
- Comparison: =, <, >, 0=, 0<
- Memory: @, !, C@, C!
- I/O: EMIT, KEY, CR

### High-Level (Forth)

- Control: IF, ELSE, THEN, DO, LOOP, BEGIN, UNTIL
- Defining: :, ;, CONSTANT, VARIABLE
- Interpreter: QUIT, INTERPRET, FIND

## Future Extensions

### Planned

1. Block storage (disk I/O)
2. Multitasking (round-robin)
3. Networking (NE2000 driver)
4. Graphics (VGA mode 13h)

### Architecture Ports

1. x86-64 (long mode)
2. ARM64 (AArch64)
3. RISC-V (RV64I)

Each port preserves the same Forth semantics with architecture-specific primitives.
