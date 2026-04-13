# ForthOS Roadmap

## What's Done

The kernel is real and running on real hardware. Everything below marked ✅ is validated — not planned, not prototyped, not in a VM. Tested on an HP 15-bs0xx booted via PXE.

---

### Kernel & Interpreter ✅

- 178-word dictionary, 66KB bootable image
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
- Phase B3: `T-BINARY,` — copies 66KB kernel byte-for-byte, 64 spot-checks pass
- Phase B4: metacompiled kernel boots in QEMU, `3 4 + .` → `7`
- Phase B5: `CALL-ABS,` pattern — CODE words calling kernel helpers, 103 symbols
- Phase B6: full `INTERPRET` with control flow + colon defs + error handling
- Phase B6b: standalone bootable metacompiled kernel, 66KB, full regression green

This closes the traditional Forth self-hosting loop. NASM is no longer required on the target.

### Universal Binary Translator (UBT) ✅

End-to-end pipeline: `.sys` binary → translator → block image → `THRU` → `USING I8042PRT` → real hardware reads.

- 258 tests / 22 suites
- 18 real-world Windows binaries validated: PE32, PE32+, ELF64, COM
- HP Win10/11 x64 driver results: serial=17 HW accesses, storport=65, usbxhci=51, HDAudBus=10, pci=13, i8042=2
- Key finding: Win10/11 x64 drivers use compiler intrinsics (`__inbyte`/`__outbyte`), not HAL imports — instruction-level detection required for 64-bit analysis

### Completed Vocabularies ✅

| Vocabulary | Blocks | Status |
|---|---|---|
| HARDWARE | 50–60 | IRQ, DPC, timing (`US-DELAY` via PIT Channel 2) |
| DISASM | 58–109 | LMI-style in-system x86 disassembler |
| PS/2 Mouse | — | Complete |
| AHCI | — | Working on HP hardware |
| NTFS | — | MFT walker, fragmented MFT, 9-run support, 1.2M records |
| FAT32 | — | EFI System Partition, GPT GUID auto-detect |
| AUTO-DETECT | — | PXE boot zero-config: RTL8168, AHCI, HD Graphics 620, xHCI |
| Network console | — | 100% reliable, UDP port 6666 |
| DISK-SURVEY | — | Partition map, driver inventory, PE/ELF detection |
| I8042PRT | 100–104 | Extracted from real Windows driver via UBT |

---

## In Progress

### ACPI.sys Investigation
The large ACPI binary causes a SIGSEGV in the translator. Known open item from the binary campaign. Needs large-binary handling in the PE loader.

### FAT32 LFN Fix
Long filename entries show garbled output. The 0x0F attribute filter may not be catching all LFN chain cases. Low priority — NTFS is the primary filesystem.

### DISK-SURVEY FAT32 Crash on HP
`DISK-SURVEY` crashes when walking the EFI partition directory tree on real hardware. Workaround: use `PARTITION-MAP` alone, then `HEX 8A800 NTFS-PROBE .` for the NTFS path. Root cause not yet isolated.

---

## Next: Multi-Architecture Targets

The metacompiler is target-agnostic. Each new CPU needs roughly a 150-line `target-<arch>.fth` file.

**Tier 1** (primary targets):
- ARM64 — Raspberry Pi 3B/4/5
- RISC-V — QEMU first, then hardware
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
0x00000000 - 0x00000FFF : Reserved (Real Mode IVT)
0x00007C00 - 0x00007DFF : Bootloader (512 bytes)  ← DATA_STACK_TOP
0x00007E00 - 0x0000FDFF : Forth Kernel (~66KB)
0x00010000 - 0x0001FFFF : Parameter Stack (64KB)
0x00020000 - 0x0002FFFF : Return Stack (64KB)
0x00029C00              : ISR_HOOK_TABLE (16 slots)
0x00030000 - 0x000BFFFF : Dictionary Space
0x000B8000 - 0x000BFFFF : VGA Text Buffer
0x000C0000 - 0x000FFFFF : ROM / Reserved
0x00100000+             : Extended Memory
```

---

*"If it fits in kilobytes, it's not bloat — it's Forth."*
