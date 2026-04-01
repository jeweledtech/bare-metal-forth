# Bare-Metal Forth

A bare-metal Forth-83 operating system for x86 hardware. No Linux, no Windows, no abstraction layers. Boots directly into a Forth environment with full hardware access.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## What This Is

Bare-Metal Forth boots on real x86 hardware and gives you a Forth-83 REPL with direct access to every port, register, and memory address on the machine. The dictionary *is* the system. Load `USING AHCI` and you have a SATA disk driver. Load `USING RTL8168` and you have gigabit networking. Omit what you don't need.

This is not a toy. It runs on real hardware (tested on HP 15-bs0xx laptops), reads NTFS partitions from SATA disks, and streams a network console over UDP at gigabit speeds. The kernel is 4,879 lines of x86 assembly. Build time is under a second.

### Proven on Real Hardware

- **SATA disk access** via AHCI (DMA reads, MBR/GPT parsing, NTFS partition scanning)
- **Gigabit Ethernet** via RTL8168 (full NIC init, PHY auto-negotiate, UDP transmit)
- **Network console** mirroring all output to a dev machine over UDP
- **PCI bus enumeration** with BAR discovery and bus master enable
- **PXE network boot** for rapid development cycles

## Quick Start

### Dependencies

```bash
# Ubuntu/Debian
sudo apt install nasm qemu-system-x86 make python3

# Arch Linux
sudo pacman -S nasm qemu python

# macOS
brew install nasm qemu python
```

### Build and Run

```bash
make          # builds in <1 second
make run      # boots in QEMU
```

You'll see:

```
Bare-Metal Forth v0.1
ok 3 4 + .
7 ok
```

### Try It

```forth
\ Arithmetic
10 20 + .                    \ 30

\ Define words on the fly
: SQUARE  DUP * ;
7 SQUARE .                   \ 49

\ Forth-83 floored division
-7 3 / .                     \ -3 (not -2)
-7 3 MOD .                   \ 2

\ Direct hardware access
HEX 3F8 INB .               \ read COM1 status
B8000 @ .                    \ read VGA text buffer
CF8 INL .                    \ read PCI config register

\ See what's loaded
WORDS
ORDER
```

## Vocabularies

The system is organized into loadable vocabularies. Six are embedded in the kernel and available immediately at boot. The rest load from block storage.

### Embedded (available at boot)

| Vocabulary | What It Does |
|-----------|--------------|
| **HARDWARE** | Physical memory allocator, millisecond delays, MMIO helpers, IRQ management, DPC queue |
| **PCI-ENUM** | PCI bus scan, config space read/write, BAR discovery, vendor/device lookup, bus master enable |
| **RTL8168** | Realtek RTL8168/8111 gigabit NIC: PHY init, MAC read, link negotiation, TX engine, UDP transmit, network console |
| **AHCI** | SATA disk driver: AHCI controller init, DMA sector reads, MBR/GPT/NTFS parsing, hex sector dump |
| **PORT-MAPPER** | I/O port discovery and enumeration for unknown hardware |
| **ECHOPORT** | I/O port tracing: logs all INB/OUTB/INW/OUTW/INL/OUTL calls for reverse engineering |

### Block-loadable

| Vocabulary | Lines | What It Does |
|-----------|-------|--------------|
| **EDITOR** | 373 | Vi-style block editor with cursor movement, insert/replace modes |
| **X86-ASM** | 228 | Target assembler: NOP, PUSH, POP, MOV, RET, register constants |
| **META-COMPILER** | 136 | Two-pass Forth metacompiler for bootstrapping |
| **DISASM** | 824 | In-system x86 disassembler with dictionary-aware decompilation |
| **MIRROR** | 313 | Context serialization and dictionary reflection |
| **CATALOG-RESOLVER** | 248 | Automatic vocabulary dependency resolution from block catalog |
| **NE2000** | 340 | NE2000/NE2K PCI network driver (word-mode DMA, promiscuous receive) |
| **NET-DICT** | 229 | Raw Ethernet block transfer between two Forth instances |
| **RTL8139** | 293 | Realtek RTL8139 100M NIC driver |
| **SERIAL-16550** | 184 | 16550 UART serial port driver |
| **PS2-KEYBOARD** | 216 | PS/2 keyboard with scancode translation |
| **PS2-MOUSE** | 110 | PS/2 mouse with packet decoding |
| **PIT-TIMER** | 80 | 8254 Programmable Interval Timer |
| **VGA-GRAPHICS** | 141 | VGA mode switching and graphics primitives |

Usage:

```forth
\ Load from blocks
0 5 THRU                     \ load blocks 0-5
USING EDITOR                 \ add EDITOR to search order
USING DISASM                 \ add DISASM to search order
ORDER                        \ show: DISASM EDITOR FORTH
```

## Network Console

Mirror all Forth output to a dev machine over UDP. Every character printed on the VGA screen also arrives on your laptop via gigabit Ethernet.

```forth
\ On the Forth machine
USING RTL8168
RTL8168-INIT                 \ finds NIC, reads MAC, negotiates link
NET-CONSOLE-ON               \ start mirroring output to UDP

\ On the dev machine
nc -u -l 6666                \ all Forth output appears here
```

The network console is fully synchronous: each UDP packet waits for the NIC's TxOK interrupt status before returning, so no output is lost even during rapid-fire dumps like `0 SECTOR.` (32 lines of hex output).

## SATA Disk Access

Read any sector from a SATA disk via AHCI DMA:

```forth
USING AHCI
AHCI-INIT                   \ discovers AHCI controller via PCI, finds drive

0 SECTOR.                   \ hex dump of MBR (shows 55 AA at bytes 510-511)
MBR.                        \ parsed partition table
GPT.                        \ GPT partition entries
NTFS-FIND                   \ scan all partitions for NTFS filesystems
800 NTFS-DUMP               \ parse NTFS boot sector at LBA 0x800

\ Diagnostics
AHCI-DIAG                   \ show DMA buffer addresses and port register state
0 SECTOR-DBG.               \ read with full command table dump
```

## Architecture

### Memory Map

```
0x00000-0x004FF     IVT + BIOS Data Area
0x00500-0x07BFF     Data stack (grows down from 0x7C00)
0x07C00             Boot sector (512 bytes)
0x07E00-0x17DFF     Kernel (64KB)
0x17E00-0x1FFFF     Embedded vocabularies
0x20000             Return stack top (grows down)
0x28000-0x28050     System variables (STATE, HERE, LATEST, BASE, BLK, search order)
0x28060-0x28098     Block buffer headers (4 slots x 12 bytes)
0x28100-0x281FF     Terminal Input Buffer (256 bytes)
0x28200-0x291FF     Block buffers (4 x 1KB)
0x29400-0x29BFF     IDT (256 entries)
0x29C00-0x29C3F     ISR hook table (16 IRQ slots)
0x30000-0x7FFFF     Dictionary (320KB)
0xB8000             VGA text buffer (80x25)
0x100000+           DMA buffers (PHYS-ALLOC, below 4MB)
```

### Registers

| Register | Purpose |
|----------|---------|
| ESI | Forth instruction pointer (IP) |
| EBP | Return stack pointer |
| ESP | Data stack pointer |
| EAX | Working register |

### Threading

Direct-threaded code (DTC). The inner interpreter is two instructions:

```nasm
NEXT:
    lodsd           ; EAX = [ESI], ESI += 4
    jmp [eax]       ; jump through code field
```

### Core Word Count

The kernel provides 177+ primitive words implemented in x86 assembly:

| Category | Words |
|----------|-------|
| Stack | DUP DROP SWAP OVER ROT NIP TUCK 2DUP 2DROP 2OVER PICK DEPTH |
| Arithmetic | + - * / MOD /MOD NEGATE ABS MIN MAX 1+ 1- |
| Logic | AND OR XOR INVERT LSHIFT RSHIFT |
| Comparison | = <> < > 0= 0< U< |
| Memory | @ ! C@ C! W@ W! +! FILL CMOVE CMOVE> |
| I/O | EMIT KEY CR SPACE TYPE . .S .R U. WORDS SEE DUMP |
| Port I/O | INB INW INL OUTB OUTW OUTL |
| Control | IF ELSE THEN DO LOOP +LOOP I J BEGIN UNTIL WHILE REPEAT |
| Defining | : ; CONSTANT VARIABLE CREATE DOES> ALLOT IMMEDIATE |
| Blocks | BLOCK BUFFER UPDATE SAVE-BUFFERS FLUSH LOAD LIST THRU |
| Vocabularies | VOCABULARY DEFINITIONS ALSO PREVIOUS ONLY ORDER USING |
| Network | NET-CON-ON NET-CON-OFF NET-FLUSH |

## Block Storage

Forth source code is stored in 1KB blocks on an IDE disk. Each block is 16 lines of 64 characters.

```bash
make blocks                  # create 1MB block disk
make write-catalog           # populate with all vocabularies
make run-blocks              # boot with block disk attached
```

```forth
1 LIST                       \ display vocabulary catalog
2 28 THRU                    \ load AHCI vocabulary from blocks
USING AHCI
AHCI-INIT
```

## Universal Binary Translator

A companion tool that extracts hardware-manipulation code from compiled binaries (Windows drivers, Linux kernel modules, DOS executables) and translates it to Forth vocabulary source.

```bash
cd tools/translator
make
./bin/translator -t forth driver.sys    # generates Forth vocabulary
```

### Pipeline

```
Binary (PE/ELF/COM) --> x86 Decoder --> UIR Lifter --> Semantic Analyzer --> Forth Codegen
```

- **Format detection**: PE32/PE32+ (Windows), ELF (Linux), COM (DOS)
- **x86 decoder**: 100+ instruction types, ModR/M+SIB, two-byte opcodes
- **UIR lifter**: Three-pass basic block construction with branch target resolution
- **Semantic analyzer**: 100+ Windows driver API entries classified (PORT_IO, MMIO, DMA, TIMING, INTERRUPT). Filters scaffolding, keeps hardware protocol
- **Forth codegen**: Generates vocabulary source with catalog headers, register constants, and parametric stack-effect words

### Real-World Validation

Validated against real Windows drivers from a production HP laptop:

| Driver | Hardware Functions | Port I/O Operations |
|--------|-------------------|---------------------|
| serial.sys | 31 | IN/OUT to COM ports |
| i8042prt.sys | 9 | PS/2 controller (0x60/0x64) |
| ACPI.sys | 21 | ACPI register access |
| parport_pc.ko (Linux) | 76 | Parallel port (0x0A-0xE8) |

The `parport_pc.ko` extraction is the gold standard: 76 named hardware functions with port I/O, all extracted correctly from a real Linux kernel module.

## Testing

```bash
make test                    # run all tests (smoke, loops, vocabs, integration)
make test-smoke              # basic arithmetic and control flow (5 tests)
make test-loops              # BEGIN/WHILE/REPEAT/UNTIL (5 tests)
make test-integration        # vocabulary loading + word execution (16 tests)
make test-vocabs             # all block-loadable vocabularies (35+ tests)
make test-network            # NE2000 two-instance network transfer (52 tests)
```

The translator has its own test suite:

```bash
cd tools/translator
make test                    # 270 tests across 22 suites
```

## Boot Methods

| Method | Command | Use Case |
|--------|---------|----------|
| QEMU floppy | `make run` | Development and testing |
| QEMU + blocks | `make run-blocks` | Testing block-loadable vocabularies |
| PXE network | `make pxe-push` | Rapid iteration on real hardware |
| Bootable ISO | `make iso` | Distribution |
| GDB debug | `make debug` | Kernel debugging on port 1234 |

### PXE Boot (Real Hardware)

For development on a real machine (tested on HP 15-bs0xx):

```bash
make pxe-setup               # configure TFTP/DHCP (one-time)
make pxe-push                # deploy current build
# boot laptop from network (F12/F9)
```

## Project Structure

```
bare-metal-forth/
├── src/
│   ├── boot/boot.asm              bootloader (278 lines, 512 bytes)
│   └── kernel/forth.asm           Forth kernel (4,879 lines, 64KB)
├── forth/dict/                    22 vocabulary source files (6,246 lines)
│   ├── ahci.fth                   SATA disk driver
│   ├── rtl8168.fth                gigabit NIC driver
│   ├── pci-enum.fth               PCI bus enumeration
│   ├── disasm.fth                 in-system disassembler
│   └── ...                        18 more vocabularies
├── tools/
│   ├── translator/                Universal Binary Translator (24K+ lines)
│   │   ├── src/loaders/           PE, ELF, COM parsers
│   │   ├── src/decoders/          x86, ARM64, RISC-V, CIL decoders
│   │   ├── src/ir/                UIR lifter + semantic analyzer
│   │   ├── src/codegen/           Forth code generator
│   │   └── tests/                 22 test suites (270 tests)
│   ├── embed-vocabs.py            compile vocabularies into kernel
│   ├── write-catalog.py           build block catalog from .fth files
│   └── write-block.py             write Forth source to block images
├── tests/                         Forth integration tests (56 files)
├── docs/
│   ├── ARCHITECTURE.md            system internals
│   ├── BUILD.md                   build and run instructions
│   └── ROADMAP.md                 development plan
├── Makefile                       build system (294 lines)
└── README.md
```

## Development Status

| Area | Status |
|------|--------|
| Kernel + interpreter | Complete (177+ words, all control flow, blocks, vocabularies) |
| Block storage | Complete (ATA PIO, 4-buffer LRU cache, LOAD/THRU) |
| Vocabulary system | Complete (search order, USING, catalog resolver) |
| Embedded vocabs | Complete (6 vocabs compiled into kernel) |
| AHCI/SATA | Working (DMA reads, MBR/GPT, NTFS scanning) |
| RTL8168 GbE | Working (full init, UDP TX, network console) |
| PCI enumeration | Working (config space, BAR discovery, bus master) |
| Network console | Working (synchronous UDP, TxOK-based completion) |
| PXE boot | Working (tested on HP 15-bs0xx) |
| Binary translator | Working (PE/ELF/COM, 270 tests, real driver validation) |
| Block editor | Working (Vi-style, block-loadable) |
| In-system disassembler | Working (x86 decode, dictionary-aware) |

## Contributing

We're seeking 2-3 committed engineers. This is infrastructure for critical systems, not a weekend project.

**What we need:**
- Embedded systems / bare-metal programming experience
- Firmware or driver development background
- Familiarity with x86 architecture at the register level
- Interest in Forth or willingness to learn it deeply

**What's here for you:**
- A working bare-metal OS you can boot on real hardware today
- Direct hardware access with no OS abstraction layers
- A binary translator that can extract driver code from Windows/Linux binaries
- A codebase small enough to understand completely (the entire kernel is one file)

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

MIT License. See [LICENSE](LICENSE).

## Acknowledgments

- Charles Moore, inventor of Forth
- Henry Laxen and Mike Perry, creators of F83
- Paul McDowell, for stimulating my interest in ship-building technology
- The Forth Interest Group (FIG)
- Forth2020 Forth programming language group - https://www.facebook.com/groups/forth2020

---

*Jolly Genius Inc. - Ship's Systems Software*
