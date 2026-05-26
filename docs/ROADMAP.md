# ForthOS Roadmap

## What's Done

The kernel is real and running on real hardware. Everything below marked ✅ is validated — not planned, not prototyped, not in a VM. Tested on an HP 15-bs0xx booted via PXE.

---

### Kernel & Interpreter ✅

- 222-word dictionary, 112KB bootable image (5,069 lines of assembly)
- Direct Threaded Code: ESI = instruction pointer, EBP = return stack pointer
- Forth-83 floored division (`-7 3 /` → `-3`, not `-2`)
- Full compiler: `:`, `;`, `IMMEDIATE`, `[`, `]`, `LITERAL`
- Control flow: `IF/ELSE/THEN`, `BEGIN/UNTIL/WHILE/REPEAT`, `DO/LOOP/+LOOP`
- Defining words: `VARIABLE`, `CONSTANT`, `CREATE`, `DOES>`
- Block storage: `BLOCK`, `BUFFER`, `UPDATE`, `SAVE-BUFFERS`, `FLUSH`, `LOAD`, `THRU`
- Vocabulary system: `VOCABULARY`, `ALSO`, `PREVIOUS`, `ONLY`, `DEFINITIONS`, `USING`
- Direct port I/O: `INB`, `INW`, `INL`, `OUTB`, `OUTW`, `OUTL`
- In-system x86 disassembler: `DIS`, `DECOMP`, `SEE`
- Network console: UDP port 6666, reliable on real hardware

### Self-Hosting: Metacompiler ✅

The metacompiler is complete. ForthOS rebuilds itself from its own blocks running inside the live system.

- Phase A: target memory, compilation state, forward refs, defining words, control flow
- Phase B3: `T-BINARY,` — copies kernel byte-for-byte, 64 spot-checks pass
- Phase B4: metacompiled kernel boots in QEMU, `3 4 + .` → `7`
- Phase B5: `CALL-ABS,` pattern — CODE words calling kernel helpers, 103 symbols
- Phase B6: full `INTERPRET` with control flow + colon defs + error handling
- Phase B6b: standalone bootable metacompiled kernel, full regression green
- ARM64 cross-compile: boots on QEMU raspi3b, 8,028 bytes — metacompiler proven on two architectures

This closes the traditional Forth self-hosting loop. NASM is no longer required on the target.

### Universal Binary Translator (UBT) ✅

End-to-end pipeline: `.sys` binary → translator → block image → `THRU` → `USING I8042PRT` → real hardware reads.

- 270 tests / 22 suites
- 18 real-world Windows binaries validated: PE32, PE32+, ELF64, COM
- HP Win10/11 x64 driver results: serial=17 HW accesses, storport=65, usbxhci=51, HDAudBus=10, pci=13, i8042=2
- Key finding: Win10/11 x64 drivers use compiler intrinsics (`__inbyte`/`__outbyte`), not HAL imports — instruction-level detection required for 64-bit analysis

### Completed Vocabularies ✅

25 vocabularies embedded at boot (full build), 18 in the free tier.

| Category | Vocabularies | Notes |
|---|---|---|
| Core utilities | HARDWARE, CATALOG-RESOLVER | IRQ, DPC, timing, dependency resolver |
| Discovery | PORT-MAPPER, ECHOPORT, PCI-ENUM | Port tracing, device enumeration |
| Diagnostics | DISASM, DISK-SURVEY | x86 disassembler, partition/driver inventory |
| Input | PS2-KEYBOARD, PS/2 Mouse | Keyboard + mouse with IRQ dispatch |
| Storage | AHCI, NTFS, FAT32 | SATA, MFT walker (1.2M records), EFI/GPT |
| Network | RTL8168, Network console | Gigabit NIC, UDP port 6666 |
| Boot config | AUTO-DETECT | PXE zero-config: RTL8168, AHCI, xHCI |
| Form engine | UI-CORE, UI-PARSER, UI-EVENTS, GUI-HARVEST | 9 widgets, `.def` parser, event loop, name registry |
| Content | FILE-EDITOR-CORE, FILE-STREAM | Editor engine (vectored I/O), NTFS streaming |
| Applications | NOTEPAD, HELLO-APP, FILE-BROWSER | Panel apps driven by form engine |
| UBT extract | I8042PRT | Extracted from real Windows driver via UBT |

### Form Engine ✅

Three milestones complete. Generalized form engine loads applications from `.def` panel definitions via FORM-LOAD / FORM-WIRE / FORM-RUN. D-word widget attributes (visible/enabled bit flags). File-browser panel renders NTFS directory contents as a navigable tree. See `docs/architecture/FORM_ENGINE_ARCHITECTURE.md` for the eight-milestone roadmap.

### Open-Core Split ✅

As of 2026-05-17, ForthOS ships as two images: `bmforth-free.img` (kernel + 18 public vocabularies) and `bmforth.img` (full build, 25 embedded vocabularies). The free tier includes the form engine, input, discovery, and three application panels. Paid packs add storage drivers, networking, and the file-streaming pipeline. See `docs/finding-2026-05-17-free-tier-also-deps.md` (architectural finding) and the README for tier details.

---

## In Progress

### FAT32 LFN Fix
Long filename entries show garbled output. The LFN attribute filter and chain assembly need tightening. Low priority — NTFS is the primary filesystem.

### Milestone 4: Settings-Dialog Panel
Next form engine milestone per `FORM_ENGINE_ARCHITECTURE.md` Section 8. Proof: a settings panel that persists user preferences across reboots.

---

## Next: Multi-Architecture Targets

The metacompiler is target-agnostic. Each new CPU needs roughly a 150-line `target-<arch>.fth` file.

**Tier 1** (next targets):
- RISC-V — QEMU first, then hardware
- ARM64 on real metal — Raspberry Pi 4/5 (QEMU boot proven, see Metacompiler section)
- x86 self-rebuild — already working

**Tier 2:**
- Cortex-M33 — picoZ80 RP2350B (second core, unused by Z80 emulation)
- SPARC/LEON3 — space-grade hardware
- PowerPC — industrial

**Tier 3:**
- MIPS, AVR, ESP32, x86-64

The pattern: write the `target-<arch>.fth` file, run the metacompiler, get a bootable image for that CPU. Same Forth source, different code generator back-end.

---

## Phase 6: Protocol Debugging & Hardware Forensics

Roadmap only — not started yet.

- USB-C / DisplayPort Alt Mode protocol analysis
- PCIe / Thunderbolt vocabulary extraction
- NVMe command vocabulary
- Embedded/IoT bridging (picoZ80 commercialization)
- Driver forensics: automated security audit of Windows driver port I/O sequences

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│               APPLICATION VOCABULARIES                   │
│     NTFS │ AHCI │ RTL8168 │ XHCI │ extracted drivers    │
├─────────────────────────────────────────────────────────┤
│               VOCABULARY SYSTEM (USING)                  │
│    load only what you need, nothing else comes along     │
├─────────────────────────────────────────────────────────┤
│                   FORTH-83 KERNEL                        │
│   Interpreter │ Compiler │ Dictionary │ Control Flow     │
├─────────────────────────────────────────────────────────┤
│                 PRIMITIVES (ASSEMBLY)                    │
│      Stack │ Arithmetic │ Memory │ INB/OUTB │ IRQ        │
├─────────────────────────────────────────────────────────┤
│                    BOOTLOADER                            │
│        Real Mode → Protected Mode → Load Kernel          │
├─────────────────────────────────────────────────────────┤
│                     BARE METAL                           │
│          x86 hardware, no HAL, no OS layer               │
└─────────────────────────────────────────────────────────┘
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

*"If it fits in kilobytes, it's not bloat — it's Forth."*
