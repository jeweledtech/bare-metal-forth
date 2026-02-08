# Bare-Metal Forth Development Roadmap

## Vision

Build a bare-metal Forth-83 operating system that:
- Boots directly on x86 hardware (no Linux/Windows/macOS layers)
- Provides real-time compilation and execution
- Enables direct memory and register manipulation
- Supports cross-architecture binary translation via UIR

---

## Phase 0: Genesis (CURRENT - 95% Complete)

**Status: Implementation Complete, Testing Pending**

### Bootloader ✅
- [x] 16-bit real mode startup
- [x] A20 gate enable
- [x] Protected mode transition
- [x] GDT setup (code, data segments)
- [x] Kernel loading (64 sectors, 32KB)
- [x] Jump to 32-bit kernel

### Forth Kernel ✅
- [x] Direct Threaded Code (DTC) interpreter
- [x] NEXT, DOCOL, EXIT primitives
- [x] Dual stack architecture (parameter + return)
- [x] Dictionary with linked word headers
- [x] Name lookup with case-insensitive compare

### Core Words ✅
- [x] Stack: DROP DUP SWAP OVER ROT ?DUP 2DUP 2DROP 2SWAP 2OVER NIP TUCK PICK ROLL DEPTH
- [x] Arithmetic: + - * / MOD /MOD NEGATE ABS MIN MAX 1+ 1- 2* 2/ */MOD
- [x] Comparison: = <> < > <= >= 0= 0< 0> U< U>
- [x] Logic: AND OR XOR INVERT
- [x] Memory: @ ! C@ C! +! 2@ 2! FILL MOVE CMOVE CMOVE>
- [x] Return Stack: >R R> R@ 2>R 2R> 2R@

### Forth-83 Floored Division ✅
- [x] Correct semantics: -7 / 3 = -3, remainder = 2
- [x] Applied to: / MOD /MOD */MOD
- [x] Multi-architecture codegen for division primitives

### I/O ✅
- [x] VGA text mode (80x25)
- [x] Keyboard input (scancode translation)
- [x] KEY EMIT CR SPACE SPACES TYPE
- [x] Cursor tracking and scrolling

### Compiler Infrastructure ✅
- [x] : (colon) and ; (semicolon)
- [x] IMMEDIATE word marking
- [x] [ ] state switching
- [x] LITERAL and LIT
- [x] ' (tick) and EXECUTE
- [x] FIND and word lookup

### Control Flow ✅
- [x] IF ELSE THEN
- [x] BEGIN UNTIL WHILE REPEAT AGAIN
- [x] DO LOOP +LOOP I J LEAVE
- [x] RECURSE

### Defining Words ✅
- [x] VARIABLE CONSTANT
- [x] CREATE DOES>
- [x] ALLOT ,

### String Words ✅
- [x] S" string literals
- [x] ." print strings
- [x] COUNT TYPE

### Utility Words ✅
- [x] WORDS (list dictionary)
- [x] SEE (decompiler)
- [x] . .S (stack display)
- [x] HEX DECIMAL
- [x] DUMP (memory dump)

### Build System ✅
- [x] Makefile with assembly targets
- [x] QEMU test targets
- [x] Debug configuration

### Pending
- [ ] Build and boot test
- [ ] Fix any runtime issues

---

## Phase 1: Self-Hosting (Target: +2 months)

### Text Interpreter Enhancement
- [ ] Line editor with history
- [ ] ACCEPT for input
- [ ] QUERY
- [ ] EVALUATE for string execution
- [ ] ABORT" error handling

### File System
- [ ] ATA/AHCI disk driver
- [ ] Simple block-based storage
- [ ] BLOCK BUFFER UPDATE SAVE-BUFFERS
- [ ] Source file loading (INCLUDE)

### Dictionary Management
- [ ] FORGET (remove words)
- [ ] MARKER (save/restore dictionary state)
- [ ] VOCABULARY (multiple wordlists)
- [ ] ORDER DEFINITIONS

### Error Handling
- [ ] ABORT ABORT"
- [ ] CATCH THROW
- [ ] Stack underflow/overflow detection

---

## Phase 2: Platform Dictionaries (Target: +4 months)

### CPU-Specific Dictionaries
- [ ] cpu/x86.fth (32-bit primitives)
- [ ] cpu/x86-64.fth (64-bit extension)
- [ ] cpu/arm64.fth (ARM64 primitives)
- [ ] cpu/riscv64.fth (RISC-V primitives)

### OS-Mode Dictionaries
- [ ] os/bare.fth (direct hardware access)
- [ ] os/linux.fth (syscall wrappers)
- [ ] os/windows.fth (API translation)

### Hardware Abstraction
- [ ] Register access words (EAX@ EAX! etc.)
- [ ] Port I/O (INB OUTB INW OUTW)
- [ ] Memory-mapped I/O
- [ ] Interrupt handlers

---

## Phase 3: UIR Integration (Target: +6 months)

### Binary Translation
- [ ] Load PE/ELF files from Forth
- [ ] Disassemble to UIR
- [ ] UIR to Forth threaded code
- [ ] Execute translated code

### Semantic Analysis
- [ ] API pattern recognition
- [ ] Function boundary detection
- [ ] Control flow reconstruction
- [ ] Call graph analysis

### Cross-Platform Support
- [ ] x86 → ARM64 translation
- [ ] x86 → RISC-V translation
- [ ] DLL import resolution
- [ ] API mapping tables

---

## Phase 4: Ship Systems (Target: +12 months)

### Device Drivers
- [ ] Serial port (RS-232)
- [ ] USB (basic)
- [ ] Network (Ethernet)
- [ ] Storage (NVMe)

### System Services
- [ ] Timer/scheduling
- [ ] Memory management
- [ ] Task switching (cooperative)
- [ ] Inter-process communication

### Reliability Features
- [ ] Watchdog timer
- [ ] Error logging
- [ ] State checkpointing
- [ ] Graceful degradation

---

## Phase 5: Production (Target: +24 months)

### Hardening
- [ ] Memory protection (optional)
- [ ] Stack canaries
- [ ] Bounds checking mode
- [ ] Audit logging

### Documentation
- [ ] Complete word glossary
- [ ] System internals guide
- [ ] Hardware interface manual
- [ ] Mission adaptation guide

### Validation
- [ ] Forth-83 compliance suite
- [ ] Hardware compatibility testing
- [ ] Long-duration stress tests
- [ ] Fault injection testing

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                         │
│            Ship Systems │ Analysis Tools │ Utilities         │
├─────────────────────────────────────────────────────────────┤
│                    PLATFORM DICTIONARIES                     │
│         cpu/x86.fth │ os/bare.fth │ api-map.fth             │
├─────────────────────────────────────────────────────────────┤
│                      FORTH KERNEL                            │
│    Interpreter │ Compiler │ Dictionary │ Control Flow        │
├─────────────────────────────────────────────────────────────┤
│                        PRIMITIVES                            │
│      Stack │ Arithmetic │ Memory │ I/O │ System             │
├─────────────────────────────────────────────────────────────┤
│                       BOOTLOADER                             │
│    Real Mode → Protected Mode → Load Kernel → Start         │
├─────────────────────────────────────────────────────────────┤
│                      BARE METAL                              │
│              x86 │ ARM64 │ RISC-V Hardware                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Memory Map (x86 Protected Mode)

```
0x00000000 - 0x00000FFF : Reserved (Real Mode IVT)
0x00007C00 - 0x00007DFF : Bootloader (512 bytes)
0x00007E00 - 0x0000FDFF : Forth Kernel (~32KB)
0x00010000 - 0x0001FFFF : Parameter Stack (64KB)
0x00020000 - 0x0002FFFF : Return Stack (64KB)
0x00030000 - 0x000BFFFF : Dictionary Space (576KB)
0x000B8000 - 0x000B8FFF : VGA Text Buffer
0x000C0000 - 0x000FFFFF : ROM/Reserved
0x00100000 - ????????   : Extended Memory (available)
```

---

## Success Metrics

### Phase 0 (Genesis)
- [ ] Boots to Forth prompt
- [ ] Can define and execute new words
- [ ] Basic arithmetic and stack operations work
- [ ] Can display text and read keyboard

### Phase 1 (Self-Hosting)
- [ ] Can save/load source files
- [ ] Can rebuild itself from source
- [ ] Error recovery without reboot

### Phase 2 (Platform Dictionaries)
- [ ] Same source runs on multiple CPUs
- [ ] Direct hardware access from Forth
- [ ] Platform-specific optimizations

### Phase 3 (UIR Integration)
- [ ] Can load and analyze Windows DLLs
- [ ] Can translate x86 code to other architectures
- [ ] Semantic analysis identifies code purpose

### Phase 4 (Ship Systems)
- [ ] Runs continuously for 30+ days
- [ ] Handles hardware faults gracefully
- [ ] Supports multiple input/output devices

### Phase 5 (Production)
- [ ] Passes Forth-83 compliance tests
- [ ] Complete documentation
- [ ] Ready for mission deployment

---

*"Build systems worthy of the void."*
