# Bare-Metal Forth Development Roadmap

## Vision

A bare-metal Forth-83 operating system for critical systems:
- Boots directly on x86 hardware with no OS layers
- Real-time compilation and execution
- Direct memory, port, and register access
- Cross-architecture binary translation for driver extraction

## Phase 0: Genesis -- COMPLETE

Core Forth-83 kernel on bare x86 hardware.

- [x] 512-byte bootloader (real mode to protected mode)
- [x] Direct-threaded code interpreter (NEXT/DOCOL/EXIT)
- [x] 177+ kernel words (stack, arithmetic, logic, memory, I/O, control flow)
- [x] Forth-83 floored division semantics
- [x] VGA text mode + keyboard + serial I/O
- [x] Colon definitions, CONSTANT, VARIABLE, CREATE/DOES>
- [x] IF/ELSE/THEN, BEGIN/UNTIL/WHILE/REPEAT, DO/LOOP/+LOOP
- [x] WORDS, SEE (decompiler), DUMP, .S

## Phase 1: Self-Hosting -- COMPLETE

Block storage, vocabularies, and source loading.

- [x] ATA PIO block driver with 4-buffer LRU cache
- [x] BLOCK, BUFFER, UPDATE, SAVE-BUFFERS, FLUSH
- [x] LOAD, LIST, THRU, --> (chain load)
- [x] Vocabulary/search-order system (8-slot)
- [x] VOCABULARY, DEFINITIONS, ALSO, PREVIOUS, ONLY, ORDER
- [x] USING syntax for vocabulary activation
- [x] Catalog resolver for automatic dependency loading
- [x] Block editor (Vi-style, 373 lines)
- [x] X86-ASM target assembler
- [x] META-COMPILER (two-pass bootstrap)

## Phase 2: Platform -- IN PROGRESS

Hardware drivers, networking, and real-hardware validation.

### Complete

- [x] Interrupt infrastructure (IDT, PIC remapping, ISR stubs)
- [x] IRQ management (IRQ-UNMASK, ISR hook table)
- [x] Physical memory allocator (PHYS-ALLOC, 1MB-4MB pool)
- [x] PCI bus enumeration (config space, BAR discovery)
- [x] RTL8168 gigabit NIC (PHY init, link negotiation, TX engine, UDP)
- [x] Network console (UDP output mirror, TxOK synchronous TX)
- [x] AHCI/SATA driver (DMA sector reads, MBR/GPT, NTFS scanning)
- [x] Embedded vocabulary system (6 vocabs compiled into kernel)
- [x] PXE network boot
- [x] In-system x86 disassembler (824 lines, dictionary-aware)
- [x] Port mapper (I/O port enumeration)
- [x] ECHOPORT (I/O call tracing)
- [x] NE2000 network driver (word-mode DMA, packet receive)
- [x] NET-DICT (raw Ethernet block transfer between instances)
- [x] RTL8139 100M NIC driver
- [x] SERIAL-16550 UART driver
- [x] PS/2 keyboard and mouse drivers
- [x] PIT timer driver
- [x] VGA graphics mode switching
- [x] Context serialization (MIRROR vocabulary)
- [x] Bare-metal validation on HP 15-bs0xx laptop

### Next

- [ ] AHCI write support (sector writes to SATA disk)
- [ ] FAT32 filesystem (read files, not just raw sectors)
- [ ] RTL8168 RX path (receive UDP packets, not just transmit)
- [ ] IRQ-driven keyboard (replace polling)
- [ ] Multi-sector DMA transfers

## Phase 3: Binary Translation -- IN PROGRESS

Universal Binary Translator for driver extraction.

### Complete

- [x] PE loader (PE32/PE32+, imports, exports, sections)
- [x] ELF loader (Linux kernel modules, userspace binaries)
- [x] COM loader (DOS flat binaries)
- [x] Format auto-detection (PE/ELF/COM)
- [x] x86 decoder (100+ instructions, ModR/M+SIB, two-byte opcodes)
- [x] ARM64 decoder (stub, structural)
- [x] RISC-V decoder (stub, structural)
- [x] CIL/.NET decoder (stub, structural)
- [x] UIR lifter (three-pass: targets, blocks, edges)
- [x] Semantic analyzer (100+ Windows driver APIs classified)
- [x] Forth code generator (parametric stack-effect words)
- [x] End-to-end pipeline: binary -> Forth vocabulary source
- [x] Ghidra validation framework (oracle comparison)
- [x] Real driver validation (serial.sys, i8042prt.sys, ACPI.sys, parport_pc.ko)
- [x] 270 tests across 22 suites, all passing

### Next

- [ ] MMIO detection (MmMapIoSpaceEx pattern recognition)
- [ ] Multi-function vocabulary merging
- [ ] Direct block-load of translated output

## Phase 4: Ship Systems -- PLANNED

- [ ] Cooperative multitasking (round-robin task switcher)
- [ ] Inter-task communication (mailboxes or channels)
- [ ] USB mass storage driver
- [ ] SD card reader support
- [ ] Framebuffer graphics (VESA/VBE)
- [ ] Sound (PC speaker, HDA basic)

## Phase 5: Production -- PLANNED

- [ ] Forth-83 compliance test suite
- [ ] Dictionary image save/restore
- [ ] Cross-compilation to ARM64 / RISC-V
- [ ] Hardened memory protection for critical deployments
- [ ] Documentation and training materials

## Tested Hardware

| Platform | Status | Notes |
|----------|--------|-------|
| QEMU i386 | Primary dev/test | floppy boot, IDE blocks, NE2K networking |
| HP 15-bs0xx laptop | Validated | PXE boot, RTL8168, Intel AHCI (8086:9D03), NTFS read |
