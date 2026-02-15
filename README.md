# Bare-Metal Forth

A bare-metal Forth-83 system built with the ship builder's mindset.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Overview

Bare-Metal Forth boots directly into a Forth-83 environment on x86 hardware. No Linux, no Windows, no abstraction layers — just Forth running on the machine. The dictionary *is* the system. Load a different dictionary, you have a different system.

This is not an operating system in the traditional sense. There is no kernel/user split, no syscall boundary, no permission model. You type a word, it executes. You define a word, it compiles. You poke a memory address, it changes. Everything between you and the hardware has been removed.

### Why?

> *"We build software the way ships are built: for critical systems where failure is not an option."*

## Quick Start

### Dependencies

```bash
# Ubuntu/Debian
sudo apt install nasm qemu-system-x86 make

# macOS (with Homebrew)
brew install nasm qemu

# Arch Linux
sudo pacman -S nasm qemu
```

### Build and Run

```bash
make run
```

You'll see:

```
Bare-Metal Forth v0.1 - Ship Builders System
Type WORDS to see available commands
ok 3 4 + .
7 ok _
```

### Try It

```forth
\ Basic arithmetic
10 20 + .          \ prints 30

\ Define a new word
: SQUARE  DUP * ;
5 SQUARE .         \ prints 25

\ Forth-83 floored division (not truncated!)
-7 3 / .           \ prints -3 (not -2)
-7 3 MOD .         \ prints 2 (not -1)

\ See what's available
WORDS
```

## Features

### What Works

- [x] x86 real mode -> protected mode boot
- [x] Direct-threaded Forth inner interpreter
- [x] 80+ word core vocabulary
- [x] Forth-83 compliant floored division
- [x] Interactive REPL with line editing
- [x] VGA text mode output (80x25)
- [x] Keyboard input via port I/O
- [x] Colon definitions (`: WORD ... ;`)
- [x] Constants, variables, CREATE/DOES>
- [x] Control flow: IF/ELSE/THEN, DO/LOOP, BEGIN/UNTIL/WHILE/REPEAT
- [x] Dictionary loading system (`USING` word)

### Core Vocabulary

| Stack | Arithmetic | Memory | I/O | Control | Compiler |
|-------|------------|--------|-----|---------|----------|
| DUP | + | @ | EMIT | IF | : |
| DROP | - | ! | KEY | ELSE | ; |
| SWAP | * | C@ | CR | THEN | IMMEDIATE |
| OVER | / | C! | SPACE | DO | ' |
| ROT | MOD | HERE | . | LOOP | EXECUTE |
| NIP | /MOD | ALLOT | WORDS | BEGIN | |
| TUCK | NEGATE | , | SEE | UNTIL | |
| 2DUP | ABS | FILL | .S | WHILE | |
| 2DROP | MIN MAX | MOVE | DUMP | REPEAT | |

### Forth-83 Division Semantics

This implementation uses **floored division** as required by Forth-83:

| Expression | Symmetric (most CPUs) | Floored (Forth-83) |
|------------|----------------------|-------------------|
| `-7 / 3` | -2 | **-3** |
| `-7 MOD 3` | -1 | **2** |
| `7 / -3` | -2 | **-3** |
| `7 MOD -3` | 1 | **-2** |

The remainder always has the same sign as the divisor.

## Architecture

### Memory Map

```
0x00000 - 0x003FF   Interrupt Vector Table
0x00400 - 0x004FF   BIOS Data Area
0x07C00 - 0x07DFF   Boot sector (512 bytes)
0x07E00 - 0x0FFFF   Kernel code
0x10000 - 0x1FFFF   Data stack (grows down)
0x20000 - 0x2FFFF   Return stack (grows down)
0x30000 - 0x4FFFF   Dictionary
0xB8000 - 0xB8F9F   VGA text buffer
```

### Register Conventions

| Register | Purpose |
|----------|---------|
| ESI | Forth instruction pointer (IP) |
| EBP | Return stack pointer |
| ESP | Data stack pointer |
| EAX | Working register / TOS cache |

### Threading Model

Direct-threaded code (DTC). Each word in the dictionary contains:
- Link to previous word (4 bytes)
- Flags + name length (1 byte)
- Name string (variable)
- Code field (4 bytes, points to machine code)
- Parameter field (variable)

## Project Structure

```
bare-metal-forth/
├── Makefile                    # Build system (NASM + QEMU)
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── src/
│   ├── boot/boot.asm           # Stage 1 bootloader (433 lines)
│   └── kernel/forth.asm        # Forth kernel (2552 lines)
├── docs/
│   ├── BUILD.md                # Build instructions
│   ├── ROADMAP.md              # Five-phase development plan
│   ├── ARCHITECTURE.md         # System internals
│   ├── MANIFESTO.md            # Ship builder's philosophy
│   ├── DRIVER_EXTRACTION.md    # Driver extraction system design
│   └── MODULE_MANIFEST.md      # XML module manifest design
├── forth/dict/
│   ├── dict_system.fth         # USING/dictionary loading system
│   ├── hardware.fth            # Hardware I/O primitives
│   └── rtl8139.fth             # Example: RTL8139 NIC driver
└── tools/
    ├── floored-division/       # Forth-83 division test suite + 3-arch codegen
    ├── translator/             # Universal binary translator (skeleton)
    └── driver-extract/         # Windows driver extraction framework
```

## Documentation

- [BUILD.md](docs/BUILD.md) - Build and run instructions
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) - System internals
- [ROADMAP.md](docs/ROADMAP.md) - Five-phase development plan
- [MANIFESTO.md](docs/MANIFESTO.md) - Project philosophy
- [DRIVER_EXTRACTION.md](docs/DRIVER_EXTRACTION.md) - Driver extraction system
- [MODULE_MANIFEST.md](docs/MODULE_MANIFEST.md) - XML module manifest design

## Roadmap

| Phase | Name | Focus | Status |
|-------|------|-------|--------|
| 0 | Genesis | Boot + core interpreter | Complete |
| 1 | Self-Hosting | File system, error handling | Next |
| 2 | Platform Dictionaries | Multi-CPU, USING system | Planned |
| 3 | UIR Integration | Binary translation to Forth | Planned |
| 4 | Ship Systems | Drivers, multitasking | Planned |
| 5 | Production | Hardening, compliance tests | Planned |

## Tools

### Floored Division Test Suite
Complete verification of Forth-83 floored division semantics with code generation for x86-64, ARM64, and RISC-V.

### Universal Binary Translator
Cross-architecture binary analysis toolkit. CLI framework works; decoder and code generation modules are stubs awaiting implementation.

### Driver Extraction Framework
Extracts hardware manipulation code from Windows drivers and generates portable Forth modules. Contains a 100+ entry Windows API recognition table mapping driver APIs to Forth equivalents.

## Contributing

We're seeking 2-3 committed collaborators. This isn't a project for casual contributors — we're looking for people who share the ship builder's mindset.

**Ideal backgrounds:**
- Space sciences / orbital mechanics
- Advanced physics / control systems
- Ship building / critical systems engineering
- Embedded systems / bare-metal programming

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

MIT License. See [LICENSE](LICENSE).

## Acknowledgments

- Charles Moore, inventor of Forth
- Henry Laxen and Mike Perry, creators of F83
- The Forth Interest Group (FIG)
- Forth2020 Forth programming language group - https://www.facebook.com/groups/forth2020
---

*Jolly Genius Inc. - Ship's Systems Software*
