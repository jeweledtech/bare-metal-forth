# ForthOS Multi-Architecture Port Design
# Target Platforms: ARM64, RISC-V, MIPS, PowerPC, SPARC, MCUs

## Vision

ForthOS boots on any processor family. The same Forth-83 semantics,
the same vocabularies, the same UBT pipeline — on any silicon.
Plug into any device, run auto-detect, explore hardware from inside.

This is exactly how Forth conquered embedded systems in the 1980s-90s:
the language is so close to the machine that porting it is mostly
rewriting the inner interpreter loop and CODE words in the new ISA.
Everything written in Forth (vocabularies, tools, UBT) ports for free.

---

## Architecture Strategy

### The Portable Core

Everything written in Forth-83 is already portable:
- All vocabularies (PORT-MAPPER, PCI-ENUM, ECHOPORT, RTL8168, AHCI)
- The UBT pipeline's Forth output
- AUTO-DETECT
- Network console

### What needs porting per architecture

Only the kernel primitives need rewriting:
1. NEXT macro (inner interpreter dispatch)
2. CODE words (arithmetic, memory, I/O)
3. Boot sequence (hardware init, stack setup)
4. Interrupt handling

For each new architecture, create:
- `src/kernel/forth-[arch].asm` — kernel in target assembly
- `src/boot/boot-[arch].asm` — bootloader for target
- `cpu/[arch].fth` — architecture vocabulary (register access, etc.)

---

## Target Architectures

### 1. ARM64 (AArch64)
**Hardware:** Raspberry Pi 3B, Pi 4, Pi 5, Apple M1/M2 Macs,
              most Android phones, AWS Graviton servers

**DTC inner interpreter in ARM64:**
```asm
; x27 = instruction pointer (ESI equivalent)
; x26 = return stack pointer (EBP equivalent)  
; x25 = data stack pointer (ESP equivalent)

.macro NEXT
    ldr x0, [x27], #8    ; load XT, advance IP
    ldr x1, [x0]         ; load code field
    br  x1               ; jump to code
.endm
```

**Boot path (Raspberry Pi):**
- Pi firmware loads kernel8.img at 0x80000 (Pi 3) or 0x200000 (Pi 5)
- No BIOS/UEFI — firmware sets up basic hardware, jumps to kernel
- UART at 0x3F201000 (Pi 3) / 0xFE201000 (Pi 4/5) for serial console
- PCI on Pi 4/5 via PCIe root complex at 0x600000000

**Key differences from x86:**
- Memory-mapped everything (no IN/OUT instructions)
- MMIO words replace INB/OUTB: `MMIO@` `MMIO!` `MMIOB@` `MMIOB!`
- Cache coherency matters for DMA (need cache flush before DMA)
- Interrupts via GIC (Generic Interrupt Controller) not 8259 PIC

**Deliverables:**
- `src/kernel/forth-arm64.asm`
- `src/boot/boot-arm64.asm` (Pi-specific, no BIOS)
- `cpu/arm64.fth` — ARM64 register access, MMIO primitives
- `forth/dict/bcm2835.fth` — Broadcom Pi 3 peripheral vocabulary
- `forth/dict/bcm2711.fth` — Broadcom Pi 4 peripheral vocabulary

---

### 2. RISC-V (RV64GC)
**Hardware:** SiFive HiFive boards, StarFive VisionFive 2,
              Milk-V Pioneer (64-core RISC-V workstation),
              RISC-V embedded (ESP32-C3, ESP32-C6)

**DTC inner interpreter in RISC-V:**
```asm
# s10 = instruction pointer
# s11 = return stack pointer
# sp  = data stack pointer

.macro NEXT
    ld   t0, 0(s10)      # load XT
    addi s10, s10, 8     # advance IP
    ld   t1, 0(t0)       # load code field
    jr   t1              # dispatch
.endmacro
```

**Key advantages of RISC-V:**
- Completely open ISA — no license fees
- Growing ecosystem (Linux, u-boot)
- The UBT RISC-V decoder already exists (10KB, complete RV64I/M)
- Floored division codegen already written

**Boot path:**
- OpenSBI (RISC-V firmware) + U-Boot
- Or direct bare metal on embedded targets
- UART at platform-specific MMIO addresses

**Deliverables:**
- `src/kernel/forth-riscv64.asm`
- `src/boot/boot-riscv64.asm`
- `cpu/riscv64.fth`

---

### 3. MIPS (MIPS32/MIPS64)
**Hardware:** OpenWRT routers (Atheros, MediaTek),
              PlayStation 1/2 (MIPS R3000/R5900),
              N64 (MIPS R4300), old SGI workstations,
              MIPS Creator CI20 dev board

**Why MIPS matters:**
- Billions of routers run MIPS
- Huge legacy embedded deployment
- Simple RISC ISA, easy to port

**DTC inner interpreter in MIPS:**
```asm
# $s6 = instruction pointer
# $s7 = return stack pointer
# $sp = data stack pointer

.macro NEXT
    lw   $t0, 0($s6)     # load XT
    addiu $s6, $s6, 4    # advance IP (32-bit cells)
    lw   $t1, 0($t0)     # load code field
    jr   $t1             # dispatch
    nop                  # branch delay slot
.endmacro
```

**Deliverables:**
- `src/kernel/forth-mips32.asm`
- `cpu/mips.fth`

---

### 4. PowerPC (PPC32/PPC64)
**Hardware:** Apple G4/G5 Macs (pre-Intel),
              IBM POWER servers,
              Nintendo GameCube/Wii/Wii U,
              Many embedded industrial systems (Freescale/NXP)

**Why PowerPC matters:**
- Apple used it until 2006 — lots of vintage hardware
- IBM POWER is still major in enterprise
- GameCube/Wii are popular dev targets

**DTC inner interpreter in PPC:**
```asm
# r27 = instruction pointer
# r26 = return stack pointer
# r1  = data stack pointer

.macro NEXT
    lwzu r3, 4(r27)      # load XT, advance IP
    lwz  r0, 0(r3)       # load code field
    mtctr r0
    bctr                 # dispatch via CTR
.endmacro
```

**Deliverables:**
- `src/kernel/forth-ppc32.asm`
- `cpu/powerpc.fth`

---

### 5. SPARC (SPARC V8/V9)
**Hardware:** Sun/Oracle SPARC workstations and servers,
              LEON3/LEON4 (used in space systems — ESA satellites),
              OpenSPARC T1/T2

**Why SPARC matters for this project:**
- LEON3/LEON4 is THE processor for European space missions
- The project's "ship builder's manifesto" — SPARC is literal spacecraft
- ESA uses LEON3 for satellite attitude control, comms, payloads
- ForthOS on SPARC = Forth on space hardware (original use case)

**SPARC register windows make Forth interesting:**
- SPARC has register windows (SAVE/RESTORE)
- The return stack maps naturally to register windows
- Potential for extremely fast Forth on SPARC

**Deliverables:**
- `src/kernel/forth-sparc.asm`
- `cpu/sparc.fth`
- `forth/dict/leon.fth` — LEON3/4 peripheral vocabulary

---

### 6. x86-64 (Long Mode)
**Hardware:** Modern PCs, servers, cloud instances

**Why x86-64 matters:**
- Native 64-bit addresses and cells
- Access to full memory above 4GB
- Modern PC hardware often requires 64-bit for UEFI boot

**DTC inner interpreter in x86-64:**
```asm
; rsi = instruction pointer
; rbp = return stack pointer
; rsp = data stack pointer

.macro NEXT
    lodsq                    ; load XT into rax (8 bytes)
    jmp [rax]                ; dispatch through code field
.endmacro
```

**Key differences from x86-32:**
- 8-byte cells (CELL-SIZE = 8)
- REX prefixes for 64-bit operands
- Different calling convention (no BIOS — UEFI or direct)
- `lodsq` instead of `lodsd`

**Deliverables:**
- `src/kernel/forth-x86-64.asm`
- `src/boot/boot-x86-64.asm` (UEFI or multiboot2)

---

### 7. Microcontrollers (MCUs)

#### AVR (Arduino Uno, Mega, ATmega series)
- 8-bit, Harvard architecture
- 2KB-32KB RAM
- ForthOS variant: eForth or FlashForth style
- Direct port I/O (PORTB, DDRD, etc.)
- `forth/dict/avr.fth`

#### ARM Cortex-M (STM32, nRF52, RP2040, RP2350B)
- 32-bit ARM Thumb-2 instruction set
- Raspberry Pi Pico uses RP2040 (dual Cortex-M0+)
- **picoZ80 board uses RP2350B** (dual Cortex-M33) — ForthOS runs
  on the second core alongside Z80 emulation. UBT ROM vocabulary
  packs serve as commercial differentiator for this platform.
- Most popular MCU family today
- Thumb-2 instead of AArch64 (16/32-bit mixed encoding)
- `src/kernel/forth-cortexm.asm`
- `forth/dict/stm32.fth`, `forth/dict/rp2040.fth`, `forth/dict/rp2350b.fth`

#### ESP32 (Xtensa LX6/LX7, RISC-V C3/C6)
- WiFi + Bluetooth built in
- ESP32-C3/C6 are RISC-V — use the RISC-V port
- ESP32 original is Xtensa — needs Xtensa port
- `forth/dict/esp32.fth`

#### PIC (Microchip PIC series)
- 8/16/32-bit variants
- Huge industrial deployment
- `src/kernel/forth-pic.asm`

---

## Implementation Roadmap

### Tier 1 — Primary Targets

### Phase 1: ARM64 (Raspberry Pi 3B/4/5)
**Priority:** HIGH — most accessible hardware, huge community
**Effort:** Medium — ARM64 is well-documented, Pi has great docs
**Status:** ARM64 UBT decoder exists, floored div codegen exists
**Task:** Write `TASK_ARM64_PORT.md`

### Phase 2: RISC-V (SiFive/StarFive boards)
**Priority:** HIGH — open ISA, growing fast, UBT decoder exists
**Effort:** Low — RISC-V is the cleanest ISA to implement
**Status:** RISC-V decoder and codegen already in UBT pipeline
**Task:** Write `TASK_RISCV_PORT.md`

### Tier 2 — Secondary Targets

### Phase 3: ARM Cortex-M33 (picoZ80 / RP2350B)
**Priority:** HIGH — picoZ80 commercial target, billions of MCU devices
**Effort:** Low — Thumb-2 is simpler than full ARM64
**Status:** picoZ80 board identified as deployment target. RP2350B
second core runs ForthOS alongside Z80 emulation.
**Task:** Write `TASK_CORTEXM_PORT.md`

### Phase 4: SPARC/LEON3 (space systems)
**Priority:** HIGH for space applications — the "ship builder" use case
**Effort:** Medium — LEON3 is well-documented, register windows add complexity
**Status:** LEON3/LEON4 used by ESA for satellite systems
**Task:** Write `TASK_SPARC_PORT.md`

### Phase 5: PowerPC
**Priority:** MEDIUM — vintage Apple, IBM POWER, embedded industrial
**Effort:** Medium — big-endian, CTR-based dispatch
**Task:** Write `TASK_PPC_PORT.md`

### Tier 3 — Future Targets

### Phase 6: MIPS
**Priority:** MEDIUM — routers, legacy embedded
**Effort:** Low — simple RISC ISA, branch delay slots
**Task:** Write `TASK_MIPS_PORT.md`

### Phase 7: x86-64 (Long Mode)
**Priority:** MEDIUM — modern PCs, 64-bit address space
**Effort:** Low — close to existing x86-32, mainly REX prefixes + 8-byte cells
**Task:** Write `TASK_X86_64_PORT.md`

### Phase 8: MCUs (AVR, ESP32, PIC)
**Priority:** MEDIUM — massive deployment, IoT use cases
**Effort:** Variable — AVR is simple, ESP32 WiFi is complex
**Note:** ESP32-C3/C6 are RISC-V — they reuse the Phase 2 port
**Task:** Write per-MCU task docs

---

## Cross-Architecture Build System

The Makefile needs a TARGET variable:

```makefile
TARGET ?= x86        # default
# TARGET = arm64
# TARGET = riscv64
# TARGET = cortexm
# TARGET = mips32
# TARGET = ppc32
# TARGET = sparc

KERNEL_SRC = src/kernel/forth-$(TARGET).asm
BOOT_SRC   = src/boot/boot-$(TARGET).asm
```

Build for Pi:
```bash
make TARGET=arm64
```

Build for RP2040:
```bash
make TARGET=cortexm MCU=rp2040
```

---

## The Universal Vocabulary Layer

All architecture-specific words hide behind a common interface:

```forth
\ These work on ALL architectures:
MMIO@    ( addr -- val )    \ read 32-bit MMIO register
MMIO!    ( val addr -- )    \ write 32-bit MMIO register
MMIOB@   ( addr -- byte )   \ read 8-bit MMIO register
MMIOB!   ( byte addr -- )   \ write 8-bit MMIO register

\ On x86 these use IN/OUT instructions
\ On ARM/RISC-V/MIPS/PPC these use regular memory loads/stores
\ The vocabulary source is identical across all architectures
```

This means PORT-MAPPER, PCI-ENUM, AHCI, RTL8168 vocabularies
work on ALL architectures with zero changes — just recompile
for the target.

---

## Immediate Next Steps

1. **AHCI vocabulary** (current task — x86) 
2. **AUTO-DETECT vocabulary** (x86 auto-discovery)
3. **ARM64 kernel port** (Raspberry Pi 3B first target)
4. **RISC-V kernel port** (SiFive or StarFive board)
5. **Cortex-M port** (Raspberry Pi Pico — cheap, accessible)

The Pi Pico costs $4 and has two cores. ForthOS on a $4 chip
talking to the dev machine over USB serial — that's the MCU
entry point.
