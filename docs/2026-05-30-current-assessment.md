# ForthOS Current State Assessment

**Jolly Genius Inc. -- Ship's Systems Software**

May 30, 2026

---

## Executive Summary

ForthOS is a **working bare-metal Forth-83 operating system** that boots
on real hardware (HP 15-bs0xx), compiles code in real time, reads and
writes NTFS and FAT32 filesystems, renders GUI applications through a
generalized form engine, and rebuilds itself via a self-hosting
metacompiler. The Universal Binary Translator extracts hardware protocols
from Windows PE and Linux ELF binaries into Forth vocabularies, validated
end-to-end against real drivers on bare metal.

The system runs with zero OS dependencies -- no Linux, no Windows, no
HAL. Forth IS the system.

**Kernel:** 225 dictionary words, 130KB source (5,072 lines of x86
assembly), 112.5KB bootable image.

**Vocabularies:** 25 embedded at boot (full build), 18 in the free tier,
59 total .fth vocabulary files spanning hardware drivers, filesystems,
networking, GUI, assemblers, and cross-architecture targets.

**Tests:** 256 C test functions across 22 UBT suites, plus 55 Python
integration test scripts covering kernel, vocabs, and form engine.

**Hardware validated:** PXE boot and USB boot on HP 15-bs0xx. AHCI SATA,
RTL8168 gigabit Ethernet, PS/2 keyboard and mouse, VGA text and graphics
-- all running on real hardware, not just emulation.

---

## Repository Structure

| Component | Size | Description |
|---|---|---|
| **src/kernel/forth.asm** | 130,311 bytes | Complete bare-metal Forth kernel: DTC interpreter, compiler, block storage, vocabularies, ATA/AHCI, VGA, serial, PS/2, embedded vocab blob |
| **src/boot/boot.asm** | 8,948 bytes | Bootloader: real mode to protected mode, EDD/LBA disk loading, GRUB memdisk support |
| **forth/dict/** | 620KB, 59 files | Forth vocabularies: drivers, filesystems, networking, form engine, assemblers, metacompiler, cross-arch targets |
| **tools/translator/** | 3.3MB | Universal Binary Translator: PE+ELF loaders, x86+ARM64+CIL decoders, UIR lifter, semantic analyzer, Forth codegen, 22 test suites |
| **tools/floored-division/** | 88KB | Floored division package: x64, ARM64, RISC-V codegen + assembly primitives + tests |
| **tools/driver-extract/** | 56KB | Driver extraction library with PE/x86/UIR integration stubs pointing to translator |
| **tests/** | 55 files | Python integration tests: kernel smoke, control flow, vocabs, form engine, metacompiler, ARM64 boot |

120 files tracked in git.

---

## Requirements Scorecard

Assessed against the 14 original requirements from the project vision.

**Status key:**
- **WORKING** -- fully implemented and validated
- **WORKING (bounded)** -- implemented within a defined scope; boundary
  is a design decision, not a gap
- **PARTIAL** -- partially implemented with known open work

| # | Requirement | Design | Implementation | Evidence |
|---|---|---|---|---|
| 1 | OS Dev + Microprocessor Architecture | WORKING | WORKING | x86 decoder 37KB (~80 opcodes incl. IN/OUT); ARM64 decoder 31KB (full A64); boot.asm real-to-protected mode; ARM64 QEMU boot proven |
| 2 | Forth-83 Standard Compliance | WORKING | WORKING | Floored /MOD in kernel; 225 dictionary words; : ; IMMEDIATE [ ] LITERAL POSTPONE DOES> all working |
| 3 | Real-Time Compilation | WORKING | WORKING | DTC interpreter, STATE-aware compiler, compile LIT+n, control flow, live dictionary modification |
| 4 | Direct Memory/Register Access | WORKING | WORKING | @ ! C@ C! W@ W! INB INW INL OUTB OUTW OUTL -- all ring 0 assembly |
| 5 | HAL Bypass | WORKING | WORKING | Bare-metal boot. No HAL exists to bypass -- Forth IS the system. Direct port I/O, direct VGA writes, direct MMIO |
| 6 | No Linux/Windows/Apple Layer | WORKING | WORKING | boot.asm to protected mode to forth.asm. Zero OS dependencies. Pure NASM + QEMU for development; bare metal for deployment |
| 7 | Direct BIOS/CPU Communication | WORKING | WORKING (bounded) | ATA PIO, AHCI SATA, keyboard, mouse, serial, NIC -- all via direct port I/O and MMIO. BIOS INT 13h/EDD for boot. **Boundary:** UEFI is out of scope by design -- it is a firmware abstraction layer, contradicting the project thesis (DECISIONS.md, May 2026) |
| 8 | Transcode Table (UIR) | WORKING | WORKING | UIR (uir.h/uir.c). x86-to-UIR lifting works. ARM64 decoder complete. Floored div codegen for x64, ARM64, RISC-V |
| 9 | Dictionary-Based Platform Switching | WORKING | WORKING | VOCABULARY, USING, ALSO, PREVIOUS, ONLY, DEFINITIONS, ORDER. Search order with 8 slots. DOVOC runtime. 25 embedded vocabs |
| 10 | Direct Register Manipulation (GPU, NIC) | WORKING | WORKING | VGA-GRAPHICS (Bochs VBE, 640x480x32, LFB), GRAPHICS (Mode 13h, DAC), 3 NIC drivers (RTL8168, RTL8139, NE2000), AHCI SATA, PS/2 keyboard+mouse, PIT timer, PCI enumeration |
| 11 | Direct Memory Editing (Dangerous Mode) | WORKING | WORKING | Any address readable/writable via @ ! C@ C!. SP@ SP! for stack manipulation. Ring 0, no protection |
| 12 | Cross-CPU Binary Translation | WORKING | WORKING (bounded) | PE-to-x86/ARM64-to-UIR-to-Forth pipeline proven end-to-end. ELF loader and CIL decoder complete. 256 C tests across 22 suites. 18 real-world binaries validated. **Boundary:** UBT is a research instrument, not production source (DECISIONS.md, April 2026). C translator is frozen as a bootstrap artifact. RISC-V decoder deferred; Forth-hosted translation is the long-term direction |
| 13 | DLL Semantic Categorization | WORKING | WORKING | semantic.c: 100+ API entries classified (PORT_IO, MMIO, DMA, INTERRUPT, PCI_CONFIG vs IRP, PNP, POWER scaffolding). Import table analysis with HAL function signatures |
| 14 | .NET DLL Stripping | WORKING | WORKING (bounded) | CIL decoder (46KB): full IL instruction decoder with two-tier opcode table, CLR metadata parsing, MethodDef/TypeDef extraction. CIL semantic classifier with 100+ namespace entries. 20 tests. **Boundary:** shares the UBT's research-instrument status -- functional and validated, but the pipeline it serves is not the production path for driver creation |

11 of 14 fully WORKING. 3 WORKING within defined boundaries -- the
boundaries are design decisions documented in DECISIONS.md, not
unfinished work.

---

## What Works Right Now

### Bare-Metal Forth OS

The system boots from disk (PXE or USB), enters 32-bit protected mode,
initializes serial (COM1, 115200 baud), VGA text mode, PS/2 keyboard
and mouse, PCI bus enumeration, AHCI SATA controller, RTL8168 gigabit
Ethernet, NTFS and FAT32 filesystem drivers, and presents a Forth
prompt with a network console on UDP port 6666. You can define new words
with `: SQUARE DUP * ;` and they compile and execute in real time.

25 vocabularies are embedded and evaluated at boot. Block storage
reads/writes to ATA or AHCI disk with LRU buffer management. The
vocabulary system supports `USING` to load platform-specific
dictionaries.

### Form Engine and GUI Applications

A generalized form engine loads applications from `.def` panel
definitions. The engine provides 9 widget types (button, label, text,
list, checkbox, radio, group, separator, canvas), a `.def` parser,
event loop with focus management, and a widget name-to-XT registry.
D-word widget attributes control visibility and enabled state.

Three panel applications run on bare metal:
- **NOTEPAD** -- text editor with keyboard input and file I/O
- **HELLO-APP** -- form engine demonstration with interactive buttons
- **FILE-BROWSER** -- NTFS directory tree navigation

Three of eight planned milestones are complete. Milestone 4
(settings-dialog panel) is in progress.

### Metacompiler (Self-Hosting)

ForthOS rebuilds itself from its own blocks running inside the live
system. The metacompiler is target-agnostic: each new CPU needs a
~150-line `target-<arch>.fth` file. Proven on two architectures:

- **x86:** standalone bootable metacompiled kernel, full regression green
- **ARM64:** boots on QEMU raspi3b, 8,028 bytes, `ok` prompt proven

114 of 114 tests passing across 6 suites (verified by live
`make test-meta` run, 2026-05-30). One gap remains: VOCABULARY target
word (Gap #7) -- the metacompiled kernel cannot yet load vocabularies
from blocks. Gap #6 (S"/." target compilation) closed 2026-05-29.

### Universal Binary Translator

The UBT is a research instrument for extracting hardware protocols
from binaries when datasheets are unavailable. The C translator is
frozen as a finished bootstrap artifact -- it works and is validated,
but is not the production path for driver creation (see DECISIONS.md).

Pipeline: PE/ELF binary -> x86/ARM64/CIL decode -> UIR lift ->
semantic classification -> Forth vocabulary codegen. 256 tests across
22 suites. Validated end-to-end: `i8042prt.sys` -> translator ->
block image -> THRU -> `USING I8042PRT` -> real hardware reads on
bare metal.

18 real-world binaries validated (PE32, PE32+, ELF64, COM), including
8 HP Win10/11 x64 drivers via hybrid LLM validation.

### Filesystem Stack

| Layer | Capability |
|---|---|
| AHCI | SATA controller, MMIO, command slots, FIS transfer |
| NTFS | MFT walker (1.2M records on HP), attribute parsing, resident+non-resident data, directory traversal |
| FAT32 | Partition detection, cluster chains, LFN support (LFN display has known garble bug, cosmetic) |
| FILE-STREAM | Sequential file reading from NTFS, SHA-256 verified (i8042prt.sys, 118KB in 356ms on HP) |
| FILE-BROWSER | NTFS directory tree with count-sort rendering |
| FILE-EDITOR-CORE | Text editing engine with vectored I/O |

### Hardware Drivers

All drivers use kernel I/O words directly (INB/OUTB/INW/OUTW/INL/OUTL).
No abstraction layer.

| Driver | Hardware | Status |
|---|---|---|
| AHCI | SATA controller | Working on HP bare metal |
| RTL8168 | Gigabit Ethernet | Working: link-up, TX, UDP, net console. RX deferred (DECISIONS.md) |
| RTL8139 | 10/100 Ethernet | Working in QEMU |
| NE2000 | NE2000 NIC | Working in QEMU, full RX+TX |
| PS2-KEYBOARD | PS/2 keyboard | Working on HP bare metal |
| PS2-MOUSE | PS/2 mouse | Working, IRQ dispatch |
| PCI-ENUM | PCI bus | Working: device discovery, BAR reading |
| PIT-TIMER | i8254 timer | Working: delays, timing |
| SERIAL-16550 | UART COM1 | Working: 115200 baud |
| VGA-GRAPHICS | Bochs VBE | Working: 640x480x32, LFB |
| AUTO-DETECT | Zero-config | PXE: RTL8168, AHCI, xHCI detection |

### Cross-Architecture Targets

| Architecture | Status |
|---|---|
| x86 (native) | Full kernel, all tests pass, HP bare metal |
| ARM64 (A64) | QEMU raspi3b boot proven, 2009-line target file, 24/24 tests |
| Cortex-M33 (Thumb-2) | 2004-line target file, assembler tests passing |
| RISC-V | Floored division codegen only; decoder deferred (DECISIONS.md) |

### Open-Core Split

ForthOS ships as two images:
- **bmforth-free.img** -- kernel + 18 public vocabularies (form engine,
  input, discovery, 3 application panels, settings)
- **bmforth.img** -- full build, 25 embedded vocabularies (adds storage
  drivers, networking, file-streaming pipeline)

---

## Remaining Gaps and Decided Dispositions

### Open -- In Progress

| Gap | Status | Tracked In |
|---|---|---|
| Metacompiler Gap #7 (VOCABULARY target) | Unblocked (Gap #6 closed 2026-05-29); not yet started | Implicit |
| FAT32 LFN display | Garbled long filenames, cosmetic | ROADMAP.md |
| Milestone 4: Settings-dialog panel | Next form engine milestone | ROADMAP.md |

### Decided -- Out of Scope

| Item | Decision | Rationale |
|---|---|---|
| UEFI support | Out of scope, on purpose | UEFI is a firmware abstraction layer; "no HAL" is the project thesis. BIOS INT 13h/EDD by design. (DECISIONS.md, May 2026) |

### Decided -- Deferred by Design

| Item | Decision | Reopen Trigger |
|---|---|---|
| optimize.c (UBT) | Abandoned as bootstrap artifact | C translator is frozen; Forth-hosted translation is the long-term direction (DECISIONS.md, April 2026) |
| api_map.c (UBT) | Abandoned as bootstrap artifact | Same as above |
| RISC-V decoder (C) | Abandoned as bootstrap artifact | Same as above. RISC-V as a metacompiler target is a separate, live roadmap item |
| RTL8168 RX | Deferred -- serial covers all inbound | High-bandwidth inbound transfer to HP over Ethernet that serial cannot handle (DECISIONS.md, May 2026) |
| TCP/IP stack | Downstream of RTL8168 RX | Requires RX path first; raw UDP TX sufficient for current work |
| USB device stack | Not on critical path | USB boot works; Forth-level xHCI enumeration not needed for form-engine-first posture |

### Future -- Roadmap Items (Not Started)

| Item | When |
|---|---|
| Multi-arch targets (RISC-V, ARM64 on real metal, SPARC) | After metacompiler gaps close |
| Protocol debugging (USB-C, PCIe, NVMe forensics) | Phase 6 |
| Form engine milestones 5-8 | After Milestone 4 |

---

## Current Development Fronts

1. **Metacompiler Gap #7** -- VOCABULARY word in the target image.
   The metacompiled kernel currently zeros embed_size to sidestep
   vocab loading. Until VOCABULARY is emitted, the metacompiled
   kernel cannot load vocabularies from blocks and cannot replace
   the NASM-assembled kernel as a full self-host.

2. **Milestone 4: Settings-dialog panel** -- Next form engine milestone
   per FORM_ENGINE_ARCHITECTURE.md Section 8. Proof: a settings panel
   that persists user preferences across reboots.

---

## Architecture

```
+-----------------------------------------------------------+
|               APPLICATION PANELS                           |
|   NOTEPAD | FILE-BROWSER | HELLO-APP | SETTINGS (M4)      |
+-----------------------------------------------------------+
|               FORM ENGINE (3/8 milestones)                 |
|   UI-CORE | UI-PARSER | UI-EVENTS | GUI-HARVEST            |
|   9 widgets, .def parser, event loop, name registry        |
+-----------------------------------------------------------+
|               CONTENT ENGINES                              |
|   FILE-EDITOR-CORE | FILE-STREAM | DISK-SURVEY             |
+-----------------------------------------------------------+
|               STORAGE + FILESYSTEM                         |
|   AHCI | NTFS | FAT32 | Block storage (ATA PIO)            |
+-----------------------------------------------------------+
|               DISCOVERY + NETWORKING                       |
|   PCI-ENUM | PORT-MAPPER | ECHOPORT | AUTO-DETECT           |
|   RTL8168 (TX) | NE2000 (TX+RX) | Net console (UDP 6666)   |
+-----------------------------------------------------------+
|               INPUT                                        |
|   PS2-KEYBOARD | PS2-MOUSE | SERIAL-16550                  |
+-----------------------------------------------------------+
|               VOCABULARY SYSTEM (USING)                    |
|   Load only what you need, nothing else comes along        |
+-----------------------------------------------------------+
|               FORTH-83 KERNEL                              |
|   Interpreter | Compiler | Dictionary | Control Flow       |
|   225 words | DTC | ESI=IP, EBP=RSP, ESP=DSP               |
+-----------------------------------------------------------+
|               PRIMITIVES (ASSEMBLY)                        |
|   Stack | Arithmetic | Memory | INB/OUTB | IRQ             |
+-----------------------------------------------------------+
|               BOOTLOADER                                   |
|   Real Mode -> Protected Mode -> Load Kernel               |
|   PXE or USB boot, BIOS INT 13h/EDD                       |
+-----------------------------------------------------------+
|               BARE METAL                                   |
|   x86 hardware, no HAL, no OS layer                        |
+-----------------------------------------------------------+
```

---

## Memory Map (x86 Protected Mode)

```
0x00000 - 0x004FF       IVT + BIOS Data Area
0x00500 - 0x07BFF       Data stack (grows DOWN from 0x7C00)
0x07C00 - 0x07DFF       Boot sector (512 bytes)
0x07E00 - 0x23DFF       Kernel code + embedded vocab blob (~112KB)
0x21E00 - 0x27FFF       Return stack (24.5KB, grows DOWN from 0x28000)
0x28000 - 0x2804F       System variables
0x28100 - 0x291FF       TIB + block buffers
0x29400 - 0x29BFF       IDT (256 entries)
0x29C00 - 0x29C3F       ISR hook table (16 IRQ slots)
0x30000 - 0x7FFFF       Dictionary space (320KB)
0xB8000 - 0xB8F9F       VGA text buffer
0x100000+               Physical allocation pool (DMA buffers)
```

---

*This assessment was generated from live codebase observation on
2026-05-30. Numbers verified against primary sources (NASM source,
Makefile, git). For the living project status, see ROADMAP.md.
For architectural decisions and dispositions, see DECISIONS.md.
Previous assessment (February 2026) archived at
archive/2026-02-23-assessment.docx.*
