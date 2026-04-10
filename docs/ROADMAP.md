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

## Phase 6: Protocol Debugging & Hardware Forensics -- PLANNED

Bare-metal, HAL-free architecture enables ForthOS as a hardware debugging
and protocol analysis platform — capabilities impossible from within
Windows/Linux because of mandatory abstraction layers.

**Prerequisite:** Phase 4 USB basic driver (required for Use Cases 1-2).

### Use Case 1: USB-C / DisplayPort Alt Mode Debugging

USB-C carries power + DP video + USB3 data simultaneously. DP Alt Mode
negotiation happens at the physical/link layer (SOP/SOP' PD messages,
AUX channel DPCD reads). Modern OS stacks give you the result, not the
wire. ForthOS gives you the wire.

**Existing foundation:** usbxhci.sys binary campaign (51 HW sequences
found via UBT pipeline), PCI-ENUM for controller discovery.

- [ ] XHCI vocabulary (xHCI host controller register-level access)
- [ ] USBC-PD vocabulary (USB Power Delivery protocol state machine)
- [ ] DP-AUX vocabulary (DisplayPort AUX channel, DPCD register access)
- [ ] Key words: AUX-READ, AUX-WRITE, DPCD@, PD-MSG-SEND, PD-MSG-RECV,
      LINK-STATUS, DP-CAPS

**Success metric:** Read DPCD register 0x0000 (receiver capability field)
from a connected monitor and display link rate + lane count from the
ForthOS prompt.

### Use Case 2: PCIe / Thunderbolt Device Enumeration

PCIe config space is directly readable via CF8/CFC port I/O (x86).
ForthOS already has PCI-SCAN in PCI-ENUM vocabulary. Thunderbolt adds a
tunneling layer. The goal is to walk the full PCIe tree including
capability structures and identify devices without any OS driver loaded.

**Existing foundation:** PCI-ENUM vocabulary (PCI-SCAN, PCI-FIND,
PCI-LIST, config space read/write — 8 word-level tests passing).

- [ ] PCI-TREE vocabulary (extends PCI-ENUM with capability chain walking,
      PCIe extended config space, link status reporting)
- [ ] TBT vocabulary (Thunderbolt router config registers, tunnel discovery)
- [ ] Key words: CAP-WALK, PCIE-LINK-STATUS, TBT-ROUTER@, LSPCI

**Success metric:** Boot to ForthOS on a Thunderbolt-equipped machine,
type `LSPCI`, get full device tree including tunneled PCIe endpoints.

### Use Case 3: NVMe / Storage Protocol Inspection

AHCI vocabulary is complete (DMA sector reads, MBR/GPT, NTFS scanning).
NVMe is the modern equivalent. Goal is to read NVMe identify
controller/namespace data and inspect submission/completion queues
directly — useful for drive firmware analysis or secure erase verification.

**Existing foundation:** AHCI vocabulary (DMA reads, Intel 8086:9D03
validated on HP 15-bs0xx), PHYS-ALLOC for DMA buffers, PCI-ENUM for
NVMe controller discovery.

- [ ] NVME vocabulary (NVMe admin queue, submission/completion queue MMIO)
- [ ] Key words: NVME-IDENTIFY, NVME-GETLOG, NVME-SANITIZE, SQ-DUMP,
      CQ-DUMP

**Success metric:** `NVME-IDENTIFY` prints controller serial, model, and
firmware revision from the ForthOS prompt without any OS driver.

### Use Case 4: Embedded/IoT Protocol Bridge (Flipper Zero style)

Devices like Flipper Zero debug protocols (IR, sub-GHz, NFC, iButton) by
running bare-metal firmware with direct GPIO/SPI/I2C access. ForthOS on
an RP2350B (picoZ80 platform) can do the same, with live Forth
compilation — write and execute protocol handlers interactively at the
prompt, not just flash firmware.

**Existing foundation:** Cross-compilation target infrastructure
(Phase 5), Forth's interactive REPL for live protocol exploration.

- [ ] SPI vocabulary (SPI master, maps to RP2350B hardware)
- [ ] I2C vocabulary (I2C master, bus scan, device read/write)
- [ ] GPIO vocabulary (pin set/get/toggle, direction control)
- [ ] IR-DECODE vocabulary (NEC/RC5/RC6 decode via timer capture)
- [ ] Key words: SPI-XFER, I2C-READ, I2C-WRITE, GPIO!, GPIO@, IR-RECV

**Success metric:** Capture and decode an IR remote code from the ForthOS
prompt on RP2350B hardware.

### Use Case 5: Driver Binary Forensics (extends UBT pipeline)

The UBT pipeline (commit 243b0f0) already translates Windows .sys
binaries to named Forth vocabularies. This use case adds a *forensic*
workflow: given an unknown binary (malware, firmware blob, proprietary
driver), use UBT to extract hardware sequences, name them semantically,
and build a ForthOS vocabulary that replicates only the hardware
behavior — stripping all OS scaffolding (IRP handling, PnP, registry,
security checks).

**Existing foundation:** Full UBT pipeline (PE/ELF/COM loaders, x86
decoder, UIR lifter, semantic analyzer, Forth codegen), 270 tests across
22 suites. Semantic categories already classify hardware vs. scaffolding
(`SEM_CAT_PORT_IO`, `SEM_CAT_MMIO`, `SEM_CAT_PCI_CONFIG`, etc.).
Real driver validation against 8 HP drivers + parport_pc.ko.

- [ ] `make forensic TARGET=x.sys` Makefile target (end-to-end forensic
      extraction with semantic report)
- [ ] TASK_FORENSIC_WORKFLOW.md documenting the full workflow:
      binary → UIR → semantic categorization → vocabulary generation →
      ForthOS load → hardware replay
- [ ] Vocabulary auto-naming from semantic category analysis
- [ ] Hardware replay verification mode (compare replayed I/O sequences
      against extracted sequences for correctness)
- [ ] Key words: BINARY-LOAD, HW-EXTRACT, VOCAB-GEN, HW-REPLAY

**Success metric:** Take an unknown `.sys` binary, run
`make forensic TARGET=x.sys`, get a loadable `.fth` vocabulary that
replays only the hardware I/O sequences from that driver.

### Use Case 6: DISK-SURVEY Phase 2 — Archive Extraction

Phase 1 (complete) catalogs every binary directly on the filesystem
via MFT walking and FAT32 directory traversal. Phase 2 goes deeper:
opens .cab, .msi, and .zip archives to catalog the binaries packed
inside them — driver packages in the Windows DriverStore, update
cabinets in SoftwareDistribution, installer packages in
C:\Windows\Installer. Together, Phase 1 + Phase 2 give complete
coverage of every reverse-engineerable binary on a machine, with
nothing uncovered.

**Existing foundation:** DISK-SURVEY vocabulary (commit 5343877):
14 binary extensions, 7 consolidated counters, multi-partition NTFS
walk, PE/ELF classification. Validated on HP 15-bs0xx: 1.2M MFT
records walked, 69,354 binaries cataloged in ~90 minutes.

- [ ] DEFLATE vocabulary (RFC 1951, ~200 lines, shared primitive)
- [ ] ZIP-READER vocabulary (End of Central Directory + Deflate)
- [ ] CAB-EXTRACT vocabulary (Microsoft Cabinet, MSZIP compression)
- [ ] MSI-READER vocabulary (OLE2 Compound Document + MSI schema)
- [ ] SURVEYOR-DEEP vocabulary (DEEP-SURVEY walks archives recursively)
- [ ] DISK-SURVEY-DETAIL (per-extension + per-directory bucketing)
- [ ] Key words: DEEP-SURVEY, CAB-LIST, MSI-LIST, ZIP-LIST,
      ARCHIVE-COUNT, DISK-SURVEY-DETAIL

**Success metric:** `DEEP-SURVEY` on HP laptop finds 100K+ additional
binaries inside .cab/.msi/.zip archives beyond the 69K directly-visible
files, producing a combined report:

```
Direct binaries:        69,354
Archive containers:     N CAB / N MSI / N ZIP
Archived binaries:     150,000+
Total coverage:        220,000+
```

Full task doc: `docs/TASK_DISK_SURVEY_PHASE2.md`

## Tested Hardware

| Platform | Status | Notes |
|----------|--------|-------|
| QEMU i386 | Primary dev/test | floppy boot, IDE blocks, NE2K networking |
| HP 15-bs0xx laptop | Validated | PXE boot, RTL8168, Intel AHCI (8086:9D03), NTFS read |
