# Driver Extraction Pipeline — Design Document

**Date:** 2026-02-21
**Status:** Design
**Scope:** Phase A (pipeline), with Phase B/C vision documented

## Strategy

Three phases to build the driver extraction and cataloging system:

- **Phase A** — Make the extraction pipeline real. Implement PE loader, x86 decoder, UIR lifter, semantic analyzer, and Forth code generator. Validate end-to-end with 16550 UART serial port as the reference device.
- **Phase B** — Feed a real Windows serial port driver (`.sys` file) through the pipeline. Compare extracted Forth vocabulary against the hand-written 16550 reference. Iterate until the outputs are recognizably equivalent.
- **Phase C** — Build the device catalog framework. Index all extracted and hand-written vocabularies. Enable discovery and loading via `USING`.

**This document covers Phase A implementation plus the catalog schema (documentation only, shapes Phase A codegen output format).**

---

## Pipeline Architecture

```
Input (.sys/.dll)
      │
      ▼
┌──────────────┐
│  PE Loader   │  Parse PE/COFF headers, find .text section,
│  pe_loader.c │  resolve import table (DLL names + function names)
└──────┬───────┘
       │  code bytes + import map
       ▼
┌──────────────┐
│  x86 Decoder │  Decode instructions to structured form.
│  x86_decoder │  ~80 opcodes: MOV, IN/OUT, CALL, RET, JMP/Jcc,
│  .c          │  PUSH/POP, CMP/TEST, ALU, MOVZX/MOVSX, SETcc.
└──────┬───────┘
       │  decoded instruction stream
       ▼
┌──────────────┐
│  UIR Lifter  │  Translate x86 instructions to platform-independent
│  uir.c       │  UIR basic blocks. IN/OUT → UIR_PORT_IN/OUT,
│              │  MOV → UIR_LOAD/STORE, CALL → UIR_CALL, etc.
└──────┬───────┘
       │  UIR basic blocks
       ▼
┌──────────────┐
│  Semantic    │  Match import calls against DRV_API_TABLE (100+
│  Analyzer    │  entries). Tag functions as hardware / scaffolding /
│  semantic.c  │  hybrid. Filter out Windows-only code paths.
└──────┬───────┘
       │  categorized hardware sequences
       ▼
┌──────────────┐
│  Forth       │  Generate Forth vocabulary from extracted hardware
│  Codegen     │  sequences. Emit catalog-compatible header metadata,
│  codegen.c   │  register constants, port words, init sequences.
└──────────────┘
       │
       ▼
  Output (.fth vocabulary)
```

---

## Component 1: PE Loader

**File:** `tools/translator/src/loaders/pe_loader.c`

**Responsibilities:**
- Parse DOS stub header — read `e_lfanew` at offset 0x3C to find PE signature
- Validate PE signature (`PE\0\0` at `e_lfanew`)
- Parse COFF File Header — machine type (0x14C = i386, 0x8664 = AMD64), number of sections, characteristics
- Parse Optional Header — image base, entry point address, size of image, data directory array
- Parse Section Table — for each section: name, virtual address, virtual size, raw data pointer, raw data size. Find `.text` (code), `.data`, `.rdata` (read-only data including import names)
- Parse Import Directory (data directory entry 1) — walk import descriptor array, resolve each DLL's name and its imported function names/ordinals
- Parse Export Directory (data directory entry 0) — for DLLs, resolve exported function names and RVAs
- Provide RVA-to-file-offset translation

**Does NOT need:** relocations, resources, TLS, debug info, certificates, delay imports, COM+ headers.

**Key types:**
```c
typedef struct {
    char        name[8];
    uint32_t    virtual_size;
    uint32_t    virtual_address;    /* RVA */
    uint32_t    raw_data_size;
    uint32_t    raw_data_offset;    /* file offset */
    uint32_t    characteristics;
} pe_section_t;

typedef struct {
    char*       dll_name;
    char*       func_name;
    uint32_t    rva;                /* RVA of IAT entry */
    uint16_t    ordinal;            /* if imported by ordinal */
} pe_import_t;

typedef struct {
    /* File data */
    const uint8_t*  data;
    size_t          data_size;

    /* PE headers */
    uint16_t    machine;            /* 0x14C or 0x8664 */
    uint32_t    image_base;
    uint32_t    entry_point_rva;

    /* Sections */
    pe_section_t*   sections;
    size_t          section_count;

    /* Code section (convenience pointer) */
    const uint8_t*  text_data;
    size_t          text_size;
    uint32_t        text_rva;

    /* Imports */
    pe_import_t*    imports;
    size_t          import_count;
} pe_context_t;
```

**API:**
```c
int pe_load(pe_context_t* ctx, const uint8_t* data, size_t size);
void pe_cleanup(pe_context_t* ctx);
const uint8_t* pe_rva_to_ptr(pe_context_t* ctx, uint32_t rva);
pe_import_t* pe_find_import(pe_context_t* ctx, const char* func_name);
```

---

## Component 2: x86 Decoder

**File:** `tools/translator/src/decoders/x86_decoder.c`

**Approach:** Extend the existing header types. Table-driven one-byte opcode dispatch + two-byte (0x0F) table for driver-relevant instructions. ModR/M + SIB decoding for all memory operand forms.

### Opcode Coverage

**One-byte opcodes (implementation required):**

| Range | Instruction | Purpose |
|-------|-------------|---------|
| 0x00-0x05 | ADD r/m,r / ADD r,r/m / ADD AL,imm / ADD EAX,imm | ALU |
| 0x08-0x0D | OR | ALU |
| 0x20-0x25 | AND | ALU |
| 0x28-0x2D | SUB | ALU |
| 0x30-0x35 | XOR | ALU |
| 0x38-0x3D | CMP | Compare |
| 0x50-0x57 | PUSH reg | Stack |
| 0x58-0x5F | POP reg | Stack |
| 0x68, 0x6A | PUSH imm32, PUSH imm8 | Stack |
| 0x70-0x7F | Jcc short | Branches |
| 0x80-0x83 | Group 1: ALU r/m, imm | ALU immediate |
| 0x84-0x85 | TEST r/m, r | Test |
| 0x88-0x8B | MOV r/m,r / MOV r,r/m | Data move |
| 0x8D | LEA r, m | Address calc |
| 0x90 | NOP | - |
| 0xA0-0xA3 | MOV AL/EAX, moffs / MOV moffs, AL/EAX | Memory move |
| 0xA8-0xA9 | TEST AL,imm / TEST EAX,imm | Test |
| 0xB0-0xBF | MOV reg, imm | Immediate load |
| 0xC3 | RET | Return |
| 0xC6-0xC7 | MOV r/m, imm (Group 11) | Store immediate |
| 0xC9 | LEAVE | Stack frame |
| 0xE4-0xE7 | IN AL,imm8 / IN EAX,imm8 / OUT imm8,AL / OUT imm8,EAX | Port I/O fixed |
| 0xE8 | CALL rel32 | Call |
| 0xE9 | JMP rel32 | Jump |
| 0xEB | JMP rel8 | Short jump |
| 0xEC-0xEF | IN AL,DX / IN EAX,DX / OUT DX,AL / OUT DX,EAX | Port I/O DX |
| 0xF6-0xF7 | Group 3: TEST/NOT/NEG/MUL/DIV | Unary ALU |
| 0xFE-0xFF | Group 4/5: INC/DEC/CALL/JMP indirect | Indirect control |
| 0xFA, 0xFB | CLI, STI | Interrupt control |
| 0xF4 | HLT | Halt |

**Two-byte opcodes (0x0F prefix):**

| Opcode | Instruction | Purpose |
|--------|-------------|---------|
| 0x0F 0x80-0x8F | Jcc near (rel32) | Long conditional jumps |
| 0x0F 0x90-0x9F | SETcc r/m8 | Conditional byte set |
| 0x0F 0xB6 | MOVZX r, r/m8 | Zero-extend byte (critical for driver port reads) |
| 0x0F 0xB7 | MOVZX r, r/m16 | Zero-extend word |
| 0x0F 0xBE | MOVSX r, r/m8 | Sign-extend byte |
| 0x0F 0xBF | MOVSX r, r/m16 | Sign-extend word |
| 0x0F 0xAF | IMUL r, r/m | Multiply |

### ModR/M Decoding

```
ModR/M byte: [mod(2)][reg(3)][rm(3)]
  mod=00: [rm] (memory, no displacement)
  mod=01: [rm]+disp8
  mod=10: [rm]+disp32
  mod=11: register direct
  rm=100: SIB byte follows (scale-index-base)
  rm=101 + mod=00: disp32 (absolute address, or RIP-relative in 64-bit)
```

**Key types (extending existing header):**
```c
/* Operand types */
typedef enum {
    OPERAND_NONE,
    OPERAND_REG,        /* Register */
    OPERAND_MEM,        /* Memory [base + index*scale + disp] */
    OPERAND_IMM,        /* Immediate value */
    OPERAND_REL,        /* Relative offset (for jumps/calls) */
} x86_operand_type_t;

typedef struct {
    x86_operand_type_t type;
    uint8_t     size;       /* 1, 2, 4, 8 */
    uint8_t     reg;        /* register number */
    uint8_t     base;       /* base register (for memory) */
    uint8_t     index;      /* index register (for SIB) */
    uint8_t     scale;      /* scale factor (1,2,4,8) */
    int32_t     disp;       /* displacement */
    int64_t     imm;        /* immediate value */
} x86_operand_t;

/* Extended decoded instruction */
typedef struct {
    uint64_t            address;
    uint8_t             length;
    x86_instruction_t   instruction;
    uint8_t             operand_count;
    x86_operand_t       operands[4];
    uint8_t             prefix_count;
    uint8_t             prefixes[4];    /* REX, 66, F2, F3 */
} x86_decoded_t;
```

**API:**
```c
/* Decode one instruction, advance offset, return bytes consumed (0 = error) */
int x86_decode_one(x86_decoder_t* dec, x86_decoded_t* out);

/* Decode all instructions in a range */
int x86_decode_range(x86_decoder_t* dec, uint64_t start, size_t len,
                     x86_decoded_t** out, size_t* count);
```

---

## Component 3: UIR Lifter

**File:** `tools/translator/src/ir/uir.c`

Translates decoded x86 instructions into UIR basic blocks.

### Lifting Rules

| x86 Instruction | UIR Opcode | Notes |
|-----------------|------------|-------|
| `IN AL/EAX, imm8` | `UIR_PORT_IN` | operand1=port, size=1 or 4 |
| `IN AL/EAX, DX` | `UIR_PORT_IN` | operand1=DX (dynamic), size=1 or 4 |
| `OUT imm8, AL/EAX` | `UIR_PORT_OUT` | operand1=port, operand2=value |
| `OUT DX, AL/EAX` | `UIR_PORT_OUT` | operand1=DX, operand2=value |
| `MOV reg, [mem]` | `UIR_LOAD` | operand1=address |
| `MOV [mem], reg` | `UIR_STORE` | operand1=address, operand2=value |
| `ADD/SUB/AND/OR/XOR` | `UIR_ADD/SUB/AND/OR/XOR` | Standard ALU |
| `CALL target` | `UIR_CALL` | operand1=target address |
| `RET` | `UIR_RET` | |
| `JMP target` | `UIR_JMP` | operand1=target |
| `Jcc target` | `UIR_JZ/UIR_JNZ` | Based on condition |
| `CMP/TEST` | `UIR_SUB/UIR_AND` | Sets flags (implicit) |
| `MOVZX` | `UIR_LOAD` + zero-extend | size field tracks source width |

### Basic Block Construction

1. Linear scan of decoded instructions
2. Split block at: branch targets, after unconditional jumps, after CALLs, after RET
3. Link blocks: fall-through → `next`, branch → `branch`
4. Result: linked list of `uir_block_t`

**API:**
```c
/* Lift decoded instructions to UIR blocks */
uir_block_t* uir_lift_function(const x86_decoded_t* instructions, size_t count,
                                uint64_t base_address);

/* Free UIR block chain */
void uir_free_blocks(uir_block_t* head);

/* Print UIR for debugging */
void uir_print_block(const uir_block_t* block, FILE* out);
```

---

## Component 4: Semantic Analyzer

**File:** `tools/translator/src/ir/semantic.c`

### Responsibilities

1. **Import Classification** — Walk the PE import table. For each imported function, look it up in `DRV_API_TABLE` (from `driver_extract.c`). Tag with `drv_category_t`.

2. **Function Discovery** — Identify function boundaries in `.text` section:
   - Entry point from PE header
   - Targets of CALL instructions
   - Export table entries
   - Heuristic: sequences starting after RET/INT3 padding

3. **Function Categorization** — For each discovered function:
   - If it contains `IN`/`OUT` instructions → hardware (PORT_IO)
   - If it calls `READ_PORT_*`/`WRITE_PORT_*` → hardware (PORT_IO)
   - If it calls `READ_REGISTER_*`/`WRITE_REGISTER_*` → hardware (MMIO)
   - If it calls `KeStallExecutionProcessor` → hardware (TIMING)
   - If it calls `HalGetBusData` → hardware (PCI_CONFIG)
   - If it only calls IRP/PNP/POWER/SYNC APIs → scaffolding (FILTERED)
   - If it mixes both → hybrid (extract hardware paths)

4. **Sequence Extraction** — For hardware functions, extract the sequence of hardware operations:
   - Port reads/writes with port numbers and data sizes
   - Polling loops (read-test-branch patterns)
   - Initialization sequences (write-delay-write patterns)
   - Register access patterns (base+offset addressing)

**Key type:**
```c
typedef struct {
    uint64_t        address;        /* Function start address */
    const char*     name;           /* From exports/imports, or generated */
    drv_category_t  category;       /* Primary category */
    bool            has_port_io;
    bool            has_mmio;
    bool            has_timing;
    bool            has_scaffolding;
    drv_hw_sequence_t** sequences;  /* Extracted hardware ops */
    size_t          sequence_count;
} sem_function_t;
```

**API:**
```c
/* Classify all imports */
int sem_classify_imports(pe_context_t* pe, const drv_api_entry_t* table,
                         size_t table_size);

/* Discover and categorize functions */
int sem_analyze_functions(pe_context_t* pe, uir_block_t* blocks,
                          sem_function_t** functions, size_t* count);
```

---

## Component 5: Forth Code Generator

**File:** `tools/translator/src/codegen/forth_codegen.c`
(New file — the existing `codegen.c` stub and `driver_extract.c` templates will be refactored into this.)

### Output Format

Generated vocabularies follow the catalog schema (see Section 8) to be catalog-compatible from day one.

**Example output for a serial port driver:**
```forth
\ ====================================================================
\ CATALOG: SERIAL-16550
\ CATEGORY: serial
\ SOURCE: extracted
\ SOURCE-BINARY: serial.sys
\ VENDOR-ID: none
\ DEVICE-ID: none
\ PORTS: 0x3F8-0x3FF
\ MMIO: none
\ CONFIDENCE: high
\ DEPENDS: HARDWARE
\ ====================================================================

VOCABULARY SERIAL-16550
SERIAL-16550 DEFINITIONS
HEX

\ ---- Register Offsets ----
00 CONSTANT RBR     \ Receive Buffer Register (read)
00 CONSTANT THR     \ Transmit Holding Register (write)
01 CONSTANT IER     \ Interrupt Enable Register
02 CONSTANT IIR     \ Interrupt Identification Register (read)
02 CONSTANT FCR     \ FIFO Control Register (write)
03 CONSTANT LCR     \ Line Control Register
04 CONSTANT MCR     \ Modem Control Register
05 CONSTANT LSR     \ Line Status Register
06 CONSTANT MSR     \ Modem Status Register
07 CONSTANT SCR     \ Scratch Register

\ ---- Hardware Base ----
VARIABLE UART-BASE

: UART-REG  ( offset -- port )  UART-BASE @ + ;
: UART@     ( offset -- byte )  UART-REG C@-PORT ;
: UART!     ( byte offset -- )  UART-REG C!-PORT ;

\ ---- Status Words ----
: TX-READY?  ( -- flag )  LSR UART@ 20 AND 0<> ;
: RX-READY?  ( -- flag )  LSR UART@ 01 AND 0<> ;

\ ---- I/O Words ----
: UART-EMIT  ( char -- )
    BEGIN TX-READY? UNTIL
    THR UART!
;

: UART-KEY  ( -- char )
    BEGIN RX-READY? UNTIL
    RBR UART@
;

\ ---- Initialization ----
: UART-INIT  ( port -- )
    UART-BASE !
    00 IER UART!           \ Disable interrupts
    80 LCR UART!           \ Enable DLAB
    01 RBR UART!           \ Baud divisor low (115200)
    00 IER UART!           \ Baud divisor high
    03 LCR UART!           \ 8N1, DLAB off
    C7 FCR UART!           \ Enable FIFO, clear, 14-byte threshold
    0B MCR UART!           \ DTR + RTS + OUT2
;

FORTH DEFINITIONS
```

### Catalog Header Format

Every generated vocabulary starts with a structured comment block that tools can parse:
```
\ CATALOG: <vocabulary-name>
\ CATEGORY: <device-category>
\ SOURCE: extracted | hand-written | hybrid
\ SOURCE-BINARY: <original-filename> | none
\ VENDOR-ID: <hex> | none
\ DEVICE-ID: <hex> | none
\ PORTS: <range> | none
\ MMIO: <range> | none
\ CONFIDENCE: high | medium | low
\ DEPENDS: <space-separated-vocabulary-names>
```

This is parseable by simple text tools (grep/sed/Python) without requiring an XML or JSON parser on the host side.

---

## Component 6: 16550 UART Reference Vocabulary

**File:** `forth/dict/serial-16550.fth`

Hand-written from the 16550 UART datasheet. This serves as the "known good" reference output for Phase B validation. The full vocabulary is shown in the Component 5 example output above — that IS the reference.

**Why 16550 UART?**
- Already used by Bare-Metal Forth for serial I/O (COM1 at 0x3F8)
- Available in QEMU
- Tiny register set (8 registers, all port I/O)
- Public, well-documented hardware spec
- Simple enough to validate by hand comparison

---

## 7. Integration: Wiring the Pipeline

**File:** `tools/translator/src/main/translator.c` (extend existing)

The existing `translate_buffer()` function currently returns a placeholder string. It will be replaced with:

```c
translate_result_t translate_buffer(const uint8_t* data, size_t size,
                                     const translate_options_t* opts) {
    /* 1. Detect format and load */
    pe_context_t pe;
    if (pe_load(&pe, data, size) != 0) {
        return error("Failed to parse PE file");
    }

    /* 2. Decode instructions */
    x86_decoder_t dec;
    x86_decoder_init(&dec, pe.machine == 0x8664 ? X86_MODE_64 : X86_MODE_32);
    dec.code = pe.text_data;
    dec.code_size = pe.text_size;
    dec.base_address = pe.image_base + pe.text_rva;

    x86_decoded_t* instructions;
    size_t inst_count;
    x86_decode_range(&dec, dec.base_address, pe.text_size,
                     &instructions, &inst_count);

    /* 3. Lift to UIR */
    uir_block_t* blocks = uir_lift_function(instructions, inst_count,
                                             dec.base_address);

    /* 4. Semantic analysis (if target is Forth) */
    if (opts->target == TARGET_FORTH) {
        sem_classify_imports(&pe, DRV_API_TABLE, DRV_API_TABLE_SIZE);
        sem_function_t* functions;
        size_t func_count;
        sem_analyze_functions(&pe, blocks, &functions, &func_count);

        /* 5. Generate Forth vocabulary */
        char* forth = forth_codegen(functions, func_count, &pe);
        // ... return result
    }
    // ... other targets (disasm, UIR dump, etc.)
}
```

---

## 8. Device Catalog Schema (Documentation Only — Phase C)

This schema shapes the Forth codegen output format in Phase A. The catalog infrastructure itself is built in Phase C.

### Device Category Taxonomy

```
DEVICE-CATEGORIES
├── SERIAL          Serial ports (UART, RS-232, RS-485)
│   ├── SERIAL-16550        16550 UART (PC standard)
│   ├── SERIAL-PL011        ARM PrimeCell UART
│   └── SERIAL-NS16750      National Semi enhanced UART
│
├── TIMER           System timers
│   ├── TIMER-PIT-8254      i8254 Programmable Interval Timer
│   ├── TIMER-HPET          High Precision Event Timer
│   └── TIMER-LAPIC         Local APIC timer
│
├── INPUT           Input devices
│   ├── INPUT-PS2-KBD       PS/2 keyboard (i8042)
│   ├── INPUT-PS2-MOUSE     PS/2 mouse (i8042 aux)
│   └── INPUT-USB-HID       USB HID devices
│
├── DISK            Storage controllers
│   ├── DISK-ATA-PIO        ATA PIO mode (already in kernel)
│   ├── DISK-AHCI           AHCI/SATA
│   ├── DISK-NVME           NVMe
│   └── DISK-USB-MASS       USB mass storage
│
├── VIDEO           Display adapters
│   ├── VIDEO-VGA-TEXT      VGA text mode (already in kernel)
│   ├── VIDEO-VGA-GFX      VGA graphics modes
│   ├── VIDEO-BOCHS-VBE    Bochs VBE extensions (QEMU)
│   └── VIDEO-SVGA         SVGA modes
│
├── NETWORK         Network interfaces
│   ├── NET-NE2000          NE2000 / RTL8029
│   ├── NET-RTL8139         RealTek RTL8139
│   ├── NET-E1000           Intel E1000/E1000E
│   └── NET-VIRTIO          VirtIO network (QEMU)
│
├── BUS             Bus controllers
│   ├── BUS-PCI             PCI configuration (0xCF8/0xCFC)
│   ├── BUS-PCIE            PCIe extended config
│   ├── BUS-USB-EHCI        USB 2.0 EHCI host
│   ├── BUS-USB-XHCI        USB 3.0 xHCI host
│   └── BUS-ISA             ISA bus
│
├── AUDIO           Sound devices
│   ├── AUDIO-SB16          Sound Blaster 16
│   ├── AUDIO-AC97          AC97 codec
│   └── AUDIO-HDA           Intel HD Audio
│
├── DMA             DMA controllers
│   ├── DMA-ISA-8237        i8237 DMA (ISA)
│   └── DMA-BUS-MASTER      PCI bus mastering DMA
│
└── SYSTEM          System-level hardware
    ├── SYS-PIC-8259        i8259 PIC
    ├── SYS-APIC            I/O APIC
    ├── SYS-CMOS-RTC        CMOS/RTC (port 0x70-0x71)
    └── SYS-ACPI            ACPI tables
```

### Vocabulary Naming Convention

Pattern: `<CATEGORY>-<DEVICE>[-<VARIANT>]`

Examples:
- `SERIAL-16550` — standard 16550 UART
- `DISK-ATA-PIO` — ATA in PIO mode
- `VIDEO-VGA-TEXT` — VGA text-only
- `NET-RTL8139` — RTL8139 NIC
- `BUS-PCI` — PCI bus enumeration

### Catalog Entry Metadata

Each vocabulary carries this metadata in its header comment block:

| Field | Type | Description |
|-------|------|-------------|
| `CATALOG` | string | Vocabulary name (must match `VOCABULARY` declaration) |
| `CATEGORY` | enum | One of the taxonomy categories above |
| `SOURCE` | enum | `extracted` (from binary), `hand-written` (from spec), `hybrid` |
| `SOURCE-BINARY` | string | Original filename if extracted, `none` if hand-written |
| `VENDOR-ID` | hex | PCI vendor ID if applicable, `none` otherwise |
| `DEVICE-ID` | hex | PCI device ID if applicable, `none` otherwise |
| `PORTS` | string | I/O port range(s) used, e.g. `0x3F8-0x3FF` |
| `MMIO` | string | MMIO address range(s) used, `none` if port I/O only |
| `CONFIDENCE` | enum | `high` (verified), `medium` (plausible), `low` (needs review) |
| `DEPENDS` | string | Space-separated list of required vocabularies |

### Discovery Pattern

Phase C will implement:
```forth
\ List all available vocabularies in a category
CATALOG-LIST-SERIAL      \ prints: SERIAL-16550, SERIAL-PL011, ...
CATALOG-LIST-NETWORK     \ prints: NET-NE2000, NET-RTL8139, ...

\ Auto-detect from PCI scan
CATALOG-AUTO-DETECT      \ scans PCI bus, matches vendor:device IDs
                         \ prints: Found NET-RTL8139 at bus 0 dev 2

\ Load by name (same as existing USING)
USING SERIAL-16550
USING NET-RTL8139
```

The discovery words are Phase C scope. Phase A only ensures the generated vocabularies carry the metadata that makes discovery possible.

---

## 9. File Layout

New and modified files:

```
tools/translator/
  src/
    loaders/
      pe_loader.c          ← NEW (replace placeholder)
    decoders/
      x86_decoder.c        ← NEW (replace placeholder)
    ir/
      uir.c                ← NEW (replace placeholder)
      semantic.c           ← NEW (replace placeholder)
    codegen/
      forth_codegen.c      ← NEW
    main/
      translator.c         ← MODIFY (wire pipeline)
  include/
    translator.h           ← MODIFY (add pe/decoder types)
    pe_loader.h            ← NEW
    x86_decoder.h          ← NEW (full version, replaces driver-extract stub)
    uir.h                  ← NEW (full version, replaces driver-extract stub)
    semantic.h             ← NEW
  tests/
    test_pe_loader.c       ← NEW
    test_x86_decoder.c     ← NEW
    test_uir_lifter.c      ← NEW
    test_pipeline.c        ← NEW (end-to-end)
  Makefile                 ← MODIFY

forth/dict/
  serial-16550.fth         ← NEW (hand-written reference)

tools/driver-extract/
  (existing code stays — will be refactored to use translator pipeline in Phase B)
```

---

## 10. Build Order

Components can be built and tested incrementally:

1. **PE Loader** — testable standalone with any `.sys` or `.dll` file. Print sections, imports, exports.
2. **x86 Decoder** — testable with raw byte sequences. Decode and print mnemonics.
3. **UIR Lifter** — testable on decoder output. Print UIR blocks.
4. **Semantic Analyzer** — testable on UIR + import data. Print function categories.
5. **Forth Codegen** — testable on semantic output. Generate and verify Forth source.
6. **16550 Reference** — write in parallel with above. Can test on running Bare-Metal Forth.
7. **Integration** — wire all components through `translate_buffer()`. End-to-end test.

Each component has clear inputs and outputs, so they can be developed and tested independently before integration.

---

## 11. Success Criteria

**Phase A is complete when:**
1. `translator -t forth serial.sys` produces a valid Forth vocabulary
2. The hand-written `serial-16550.fth` loads and runs on Bare-Metal Forth in QEMU
3. The generated vocabulary's register addresses, port operations, and init sequence are recognizably the same as the hand-written reference
4. Each pipeline component has at least basic tests

**Phase B validation (follow-up):**
- The extracted vocabulary, when loaded on Bare-Metal Forth, can actually communicate over the serial port

**Phase C catalog (follow-up):**
- `CATALOG-LIST-*` words work
- `CATALOG-AUTO-DETECT` matches PCI devices to vocabularies
- 10+ vocabularies cataloged across at least 3 device categories
