# Driver Extraction Pipeline — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a working extraction pipeline that reads a PE (.sys/.dll) binary, decodes x86 instructions, lifts to UIR, categorizes hardware vs scaffolding, and generates a Forth vocabulary.

**Architecture:** Six pipeline components (PE loader → x86 decoder → UIR lifter → semantic analyzer → Forth codegen) plus a hand-written 16550 UART reference vocabulary. Each component reads the output of the previous one. All live under `tools/translator/`.

**Tech Stack:** C11, gcc, NASM (for Forth kernel), QEMU (for testing Forth vocabularies), Python (test harness)

---

## Task 1: PE Loader — Header Parsing

**Files:**
- Create: `tools/translator/include/pe_format.h` (PE structure definitions)
- Create: `tools/translator/include/pe_loader.h` (API, replaces driver-extract stub)
- Modify: `tools/translator/src/loaders/pe_loader.c` (replace placeholder)
- Create: `tools/translator/tests/test_pe_loader.c`

**Step 1: Write pe_format.h with PE structure definitions**

```c
/* tools/translator/include/pe_format.h
 * Raw PE/COFF structure definitions — matches the on-disk format byte-for-byte.
 * All fields are little-endian as specified by the PE format.
 */
#ifndef PE_FORMAT_H
#define PE_FORMAT_H

#include <stdint.h>

/* DOS Header (64 bytes) */
typedef struct {
    uint16_t e_magic;       /* 0x5A4D = "MZ" */
    uint16_t e_cblp;
    uint16_t e_cp;
    uint16_t e_crlc;
    uint16_t e_cparhdr;
    uint16_t e_minalloc;
    uint16_t e_maxalloc;
    uint16_t e_ss;
    uint16_t e_sp;
    uint16_t e_csum;
    uint16_t e_ip;
    uint16_t e_cs;
    uint16_t e_lfarlc;
    uint16_t e_ovno;
    uint16_t e_res[4];
    uint16_t e_oemid;
    uint16_t e_oeminfo;
    uint16_t e_res2[10];
    uint32_t e_lfanew;      /* Offset to PE signature */
} dos_header_t;

#define DOS_MAGIC 0x5A4D

/* COFF File Header (20 bytes) */
typedef struct {
    uint16_t machine;
    uint16_t number_of_sections;
    uint32_t time_date_stamp;
    uint32_t pointer_to_symbol_table;
    uint32_t number_of_symbols;
    uint16_t size_of_optional_header;
    uint16_t characteristics;
} coff_header_t;

#define COFF_MACHINE_I386   0x014C
#define COFF_MACHINE_AMD64  0x8664

/* Data Directory Entry */
typedef struct {
    uint32_t virtual_address;
    uint32_t size;
} data_directory_t;

#define DATA_DIR_EXPORT     0
#define DATA_DIR_IMPORT     1
#define DATA_DIR_RESOURCE   2
#define DATA_DIR_EXCEPTION  3
#define DATA_DIR_SECURITY   4
#define DATA_DIR_BASERELOC  5
#define DATA_DIR_DEBUG      6

/* PE32 Optional Header */
typedef struct {
    uint16_t magic;             /* 0x10B = PE32, 0x20B = PE32+ */
    uint8_t  major_linker_version;
    uint8_t  minor_linker_version;
    uint32_t size_of_code;
    uint32_t size_of_initialized_data;
    uint32_t size_of_uninitialized_data;
    uint32_t address_of_entry_point;
    uint32_t base_of_code;
    uint32_t base_of_data;      /* PE32 only */
    uint32_t image_base;
    uint32_t section_alignment;
    uint32_t file_alignment;
    uint16_t major_os_version;
    uint16_t minor_os_version;
    uint16_t major_image_version;
    uint16_t minor_image_version;
    uint16_t major_subsystem_version;
    uint16_t minor_subsystem_version;
    uint32_t win32_version_value;
    uint32_t size_of_image;
    uint32_t size_of_headers;
    uint32_t checksum;
    uint16_t subsystem;
    uint16_t dll_characteristics;
    uint32_t size_of_stack_reserve;
    uint32_t size_of_stack_commit;
    uint32_t size_of_heap_reserve;
    uint32_t size_of_heap_commit;
    uint32_t loader_flags;
    uint32_t number_of_rva_and_sizes;
    /* data_directory_t entries follow */
} pe32_optional_header_t;

/* PE32+ Optional Header (64-bit) */
typedef struct {
    uint16_t magic;             /* 0x20B */
    uint8_t  major_linker_version;
    uint8_t  minor_linker_version;
    uint32_t size_of_code;
    uint32_t size_of_initialized_data;
    uint32_t size_of_uninitialized_data;
    uint32_t address_of_entry_point;
    uint32_t base_of_code;
    /* No base_of_data in PE32+ */
    uint64_t image_base;
    uint32_t section_alignment;
    uint32_t file_alignment;
    uint16_t major_os_version;
    uint16_t minor_os_version;
    uint16_t major_image_version;
    uint16_t minor_image_version;
    uint16_t major_subsystem_version;
    uint16_t minor_subsystem_version;
    uint32_t win32_version_value;
    uint32_t size_of_image;
    uint32_t size_of_headers;
    uint32_t checksum;
    uint16_t subsystem;
    uint16_t dll_characteristics;
    uint64_t size_of_stack_reserve;
    uint64_t size_of_stack_commit;
    uint64_t size_of_heap_reserve;
    uint64_t size_of_heap_commit;
    uint32_t loader_flags;
    uint32_t number_of_rva_and_sizes;
    /* data_directory_t entries follow */
} pe32plus_optional_header_t;

#define PE_OPT_MAGIC_PE32      0x10B
#define PE_OPT_MAGIC_PE32PLUS  0x20B

/* Section Header (40 bytes) */
typedef struct {
    char     name[8];
    uint32_t virtual_size;
    uint32_t virtual_address;
    uint32_t size_of_raw_data;
    uint32_t pointer_to_raw_data;
    uint32_t pointer_to_relocations;
    uint32_t pointer_to_linenumbers;
    uint16_t number_of_relocations;
    uint16_t number_of_linenumbers;
    uint32_t characteristics;
} section_header_t;

#define SECTION_CNT_CODE                0x00000020
#define SECTION_CNT_INITIALIZED_DATA    0x00000040
#define SECTION_MEM_EXECUTE             0x20000000
#define SECTION_MEM_READ                0x40000000
#define SECTION_MEM_WRITE               0x80000000

/* Import Directory Entry */
typedef struct {
    uint32_t import_lookup_table_rva;   /* aka OriginalFirstThunk */
    uint32_t time_date_stamp;
    uint32_t forwarder_chain;
    uint32_t name_rva;                  /* RVA to DLL name string */
    uint32_t import_address_table_rva;  /* aka FirstThunk */
} import_descriptor_t;

/* Import Lookup Table Entry (PE32) */
#define IMPORT_ORDINAL_FLAG_32  0x80000000
#define IMPORT_ORDINAL_FLAG_64  0x8000000000000000ULL

/* Hint/Name Entry */
typedef struct {
    uint16_t hint;
    /* char name[] follows — null-terminated */
} hint_name_t;

/* Export Directory */
typedef struct {
    uint32_t characteristics;
    uint32_t time_date_stamp;
    uint16_t major_version;
    uint16_t minor_version;
    uint32_t name_rva;
    uint32_t ordinal_base;
    uint32_t number_of_functions;
    uint32_t number_of_names;
    uint32_t address_of_functions_rva;
    uint32_t address_of_names_rva;
    uint32_t address_of_name_ordinals_rva;
} export_directory_t;

#define PE_SIGNATURE 0x00004550  /* "PE\0\0" */

#endif /* PE_FORMAT_H */
```

**Step 2: Write pe_loader.h API header**

```c
/* tools/translator/include/pe_loader.h */
#ifndef PE_LOADER_H
#define PE_LOADER_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

/* Section info */
typedef struct {
    char        name[9];        /* null-terminated */
    uint32_t    virtual_size;
    uint32_t    virtual_address;
    uint32_t    raw_data_size;
    uint32_t    raw_data_offset;
    uint32_t    characteristics;
} pe_section_t;

/* Import entry */
typedef struct {
    char*       dll_name;       /* allocated string */
    char*       func_name;      /* allocated string (NULL if by ordinal) */
    uint16_t    ordinal;
    uint32_t    iat_rva;        /* RVA in Import Address Table */
} pe_import_t;

/* Export entry */
typedef struct {
    char*       name;           /* allocated string */
    uint32_t    ordinal;
    uint32_t    rva;            /* RVA of exported function */
} pe_export_t;

/* PE context — result of loading */
typedef struct {
    /* Raw file data (caller-owned, must outlive context) */
    const uint8_t*  data;
    size_t          data_size;

    /* PE headers */
    uint16_t    machine;        /* COFF_MACHINE_I386 or COFF_MACHINE_AMD64 */
    bool        is_64bit;       /* PE32+ flag */
    uint64_t    image_base;
    uint32_t    entry_point_rva;

    /* Sections */
    pe_section_t*   sections;
    size_t          section_count;

    /* Convenience: code section */
    const uint8_t*  text_data;      /* pointer into raw data */
    size_t          text_size;
    uint32_t        text_rva;

    /* Imports */
    pe_import_t*    imports;
    size_t          import_count;

    /* Exports */
    pe_export_t*    exports;
    size_t          export_count;
} pe_context_t;

/* Load PE from memory buffer. Returns 0 on success, -1 on error. */
int pe_load(pe_context_t* ctx, const uint8_t* data, size_t size);

/* Free all allocated memory in context. */
void pe_cleanup(pe_context_t* ctx);

/* Convert RVA to pointer within raw data. Returns NULL if out of bounds. */
const uint8_t* pe_rva_to_ptr(const pe_context_t* ctx, uint32_t rva);

/* Find a section by name (e.g. ".text"). Returns NULL if not found. */
const pe_section_t* pe_find_section(const pe_context_t* ctx, const char* name);

/* Find an import by function name. Returns NULL if not found. */
const pe_import_t* pe_find_import(const pe_context_t* ctx, const char* func_name);

/* Print PE summary to FILE (for debugging). */
void pe_print_info(const pe_context_t* ctx, FILE* out);

#endif /* PE_LOADER_H */
```

**Step 3: Write failing test**

```c
/* tools/translator/tests/test_pe_loader.c */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include "../include/pe_loader.h"
#include "../include/pe_format.h"

/* Build a minimal valid PE32 file in memory for testing.
 * Contains: DOS header, PE signature, COFF header, optional header,
 * one .text section with a single RET instruction, and a minimal import. */
static uint8_t* build_test_pe(size_t* out_size) {
    /* Layout:
     * 0x000: DOS header (64 bytes, e_lfanew = 0x40)
     * 0x040: PE signature (4 bytes)
     * 0x044: COFF header (20 bytes)
     * 0x058: Optional header PE32 (96 bytes + 16 data dir entries * 8 = 224)
     * 0x138: Section table: 1 entry (40 bytes)
     * 0x160: Padding to 0x200 (file alignment)
     * 0x200: .text section data: C3 (RET)
     */
    size_t file_size = 0x400;  /* enough room */
    uint8_t* buf = calloc(1, file_size);

    /* DOS header */
    dos_header_t* dos = (dos_header_t*)buf;
    dos->e_magic = DOS_MAGIC;
    dos->e_lfanew = 0x40;

    /* PE signature */
    *(uint32_t*)(buf + 0x40) = PE_SIGNATURE;

    /* COFF header */
    coff_header_t* coff = (coff_header_t*)(buf + 0x44);
    coff->machine = COFF_MACHINE_I386;
    coff->number_of_sections = 1;
    coff->size_of_optional_header = 224;  /* 96 + 16*8 */

    /* PE32 Optional header */
    pe32_optional_header_t* opt = (pe32_optional_header_t*)(buf + 0x58);
    opt->magic = PE_OPT_MAGIC_PE32;
    opt->address_of_entry_point = 0x1000;
    opt->image_base = 0x10000;
    opt->section_alignment = 0x1000;
    opt->file_alignment = 0x200;
    opt->size_of_image = 0x3000;
    opt->size_of_headers = 0x200;
    opt->number_of_rva_and_sizes = 16;

    /* Section header for .text */
    section_header_t* sec = (section_header_t*)(buf + 0x138);
    memcpy(sec->name, ".text\0\0\0", 8);
    sec->virtual_size = 1;
    sec->virtual_address = 0x1000;
    sec->size_of_raw_data = 0x200;
    sec->pointer_to_raw_data = 0x200;
    sec->characteristics = SECTION_CNT_CODE | SECTION_MEM_EXECUTE | SECTION_MEM_READ;

    /* .text data: single RET instruction */
    buf[0x200] = 0xC3;

    *out_size = file_size;
    return buf;
}

static int tests_run = 0;
static int tests_passed = 0;

#define TEST(name) do { \
    tests_run++; \
    printf("  TEST: %-40s ", #name); \
} while(0)

#define PASS() do { tests_passed++; printf("PASS\n"); } while(0)
#define FAIL(msg) do { printf("FAIL: %s\n", msg); } while(0)

static void test_load_minimal_pe(void) {
    TEST(load_minimal_pe);
    size_t size;
    uint8_t* data = build_test_pe(&size);

    pe_context_t ctx;
    int rc = pe_load(&ctx, data, size);
    if (rc != 0) { FAIL("pe_load returned error"); free(data); return; }
    if (ctx.machine != COFF_MACHINE_I386) { FAIL("wrong machine type"); goto out; }
    if (ctx.image_base != 0x10000) { FAIL("wrong image base"); goto out; }
    if (ctx.entry_point_rva != 0x1000) { FAIL("wrong entry point"); goto out; }
    if (ctx.section_count != 1) { FAIL("wrong section count"); goto out; }
    if (ctx.is_64bit) { FAIL("should be 32-bit"); goto out; }
    PASS();
out:
    pe_cleanup(&ctx);
    free(data);
}

static void test_find_text_section(void) {
    TEST(find_text_section);
    size_t size;
    uint8_t* data = build_test_pe(&size);

    pe_context_t ctx;
    pe_load(&ctx, data, size);

    if (ctx.text_data == NULL) { FAIL("text_data is NULL"); goto out; }
    if (ctx.text_size == 0) { FAIL("text_size is 0"); goto out; }
    if (ctx.text_data[0] != 0xC3) { FAIL("first byte should be RET (0xC3)"); goto out; }

    const pe_section_t* sec = pe_find_section(&ctx, ".text");
    if (sec == NULL) { FAIL("pe_find_section returned NULL"); goto out; }
    PASS();
out:
    pe_cleanup(&ctx);
    free(data);
}

static void test_rva_to_ptr(void) {
    TEST(rva_to_ptr);
    size_t size;
    uint8_t* data = build_test_pe(&size);

    pe_context_t ctx;
    pe_load(&ctx, data, size);

    const uint8_t* ptr = pe_rva_to_ptr(&ctx, 0x1000);
    if (ptr == NULL) { FAIL("rva_to_ptr returned NULL for .text RVA"); goto out; }
    if (*ptr != 0xC3) { FAIL("rva_to_ptr content wrong"); goto out; }

    const uint8_t* bad = pe_rva_to_ptr(&ctx, 0xFFFFFF);
    if (bad != NULL) { FAIL("rva_to_ptr should return NULL for bad RVA"); goto out; }
    PASS();
out:
    pe_cleanup(&ctx);
    free(data);
}

static void test_reject_invalid(void) {
    TEST(reject_invalid_data);
    pe_context_t ctx;

    /* Too small */
    uint8_t tiny[] = {0x4D, 0x5A};
    if (pe_load(&ctx, tiny, sizeof(tiny)) == 0) { FAIL("accepted too-small data"); return; }

    /* Wrong magic */
    uint8_t bad[256] = {0};
    bad[0] = 0xEE;
    if (pe_load(&ctx, bad, sizeof(bad)) == 0) { FAIL("accepted bad magic"); return; }

    PASS();
}

int main(void) {
    printf("PE Loader Tests\n");
    printf("===============\n");

    test_load_minimal_pe();
    test_find_text_section();
    test_rva_to_ptr();
    test_reject_invalid();

    printf("\nResults: %d/%d passed\n", tests_passed, tests_run);
    return tests_passed == tests_run ? 0 : 1;
}
```

**Step 4: Run test to verify it fails**

Run: `cd tools/translator && gcc -Wall -Wextra -std=c11 -Iinclude -o build/test_pe tests/test_pe_loader.c src/loaders/pe_loader.c && ./build/test_pe`
Expected: Linker errors for `pe_load`, `pe_cleanup`, etc. (not yet implemented)

**Step 5: Implement pe_loader.c**

Replace the placeholder in `tools/translator/src/loaders/pe_loader.c` with the full implementation:
- `pe_load()`: Parse DOS header → find PE sig → parse COFF → parse optional header (PE32 or PE32+) → parse sections → find .text → parse imports → parse exports
- `pe_rva_to_ptr()`: Walk sections, find which section contains the RVA, return `data + section.raw_data_offset + (rva - section.virtual_address)`
- `pe_find_section()`: Linear scan of sections by name
- `pe_find_import()`: Linear scan of imports by func_name
- `pe_cleanup()`: Free allocated imports, exports, sections
- `pe_print_info()`: Print machine type, sections, imports, exports

Key implementation detail for import parsing:
1. Get import directory RVA from data directory entry 1
2. Walk array of `import_descriptor_t` (terminated by all-zero entry)
3. For each DLL: resolve name string via RVA, then walk its Import Lookup Table
4. Each ILT entry: if high bit set → import by ordinal, else → RVA to hint/name entry

**Step 6: Run tests to verify they pass**

Run: `cd tools/translator && gcc -Wall -Wextra -std=c11 -Iinclude -o build/test_pe tests/test_pe_loader.c src/loaders/pe_loader.c && ./build/test_pe`
Expected: 4/4 PASS

**Step 7: Commit**

```bash
git add tools/translator/include/pe_format.h tools/translator/include/pe_loader.h \
        tools/translator/src/loaders/pe_loader.c tools/translator/tests/test_pe_loader.c
git commit -m "Implement PE loader: parse headers, sections, imports, exports"
```

---

## Task 2: x86 Decoder — Core Infrastructure

**Files:**
- Create: `tools/translator/include/x86_decoder.h` (full version, replaces driver-extract stub)
- Modify: `tools/translator/src/decoders/x86_decoder.c` (replace placeholder)
- Create: `tools/translator/tests/test_x86_decoder.c`

**Step 1: Write x86_decoder.h**

Must include:
- `x86_operand_type_t` enum: NONE, REG, MEM, IMM, REL
- `x86_operand_t` struct: type, size, reg, base, index, scale, disp, imm
- Extended `x86_decoded_t` struct: address, length, instruction, operand_count, operands[4], prefixes
- Extended `x86_instruction_t` enum: add LEA, NOP, CMP, TEST, NEG, NOT, MUL, IMUL, DIV, MOVZX, MOVSX, SETcc, LEAVE, all ALU ops (ADD, SUB, AND, OR, XOR, ADC, SBB), SHL, SHR, SAR
- `x86_register_t` enum: EAX, ECX, EDX, EBX, ESP, EBP, ESI, EDI (+ 8-bit, 16-bit names)
- `x86_decoder_t` struct: mode, code, code_size, base_address, offset
- API: `x86_decode_one()`, `x86_decode_range()`, `x86_decoder_init()`, `x86_print_decoded()`

**Step 2: Write failing tests for basic instructions**

```c
/* tools/translator/tests/test_x86_decoder.c */
/* Test: decode NOP (0x90), RET (0xC3), PUSH EAX (0x50), POP EAX (0x58) */
/* Test: decode MOV EAX, imm32 (0xB8 xx xx xx xx) */
/* Test: decode IN AL, imm8 (0xE4 xx) and OUT imm8, AL (0xE6 xx) */
/* Test: decode CALL rel32 (0xE8 xx xx xx xx) */
/* Test: decode JMP short (0xEB xx) */
/* Test: decode MOVZX (0x0F 0xB6 ModR/M) */
```

Each test builds a byte array, feeds it to `x86_decode_one()`, checks instruction type and operands.

**Step 3: Run tests to verify they fail**

Run: `cd tools/translator && gcc -Wall -Wextra -std=c11 -Iinclude -o build/test_x86 tests/test_x86_decoder.c src/decoders/x86_decoder.c && ./build/test_x86`
Expected: Linker errors or assertion failures

**Step 4: Implement x86_decoder.c**

Structure:
- `static int decode_modrm(x86_decoder_t* dec, x86_decoded_t* out, int operand_idx, int size)` — reads ModR/M byte, optional SIB, optional displacement. Fills operand struct.
- `static int read_imm(x86_decoder_t* dec, x86_decoded_t* out, int operand_idx, int size)` — reads immediate value.
- One-byte opcode dispatch table: `typedef int (*opcode_handler_t)(x86_decoder_t*, x86_decoded_t*)`. Array of 256 handlers.
- Two-byte (0x0F) sub-table: array of 256 handlers for 0x0F xx opcodes.
- `x86_decode_one()`: read prefix bytes (0x66, 0xF2, 0xF3, 0x40-0x4F REX), read opcode byte, dispatch to handler.

Key handlers to implement:
- 0x50-0x57: PUSH reg → `instruction = X86_INS_PUSH, operands[0] = {REG, 4, reg}`
- 0x58-0x5F: POP reg
- 0x80-0x83: Group 1 (ModR/M /r selects ADD/OR/ADC/SBB/AND/SUB/XOR/CMP)
- 0x88-0x8B: MOV r/m,r and MOV r,r/m (direction bit)
- 0xB0-0xBF: MOV reg, imm (register encoded in low 3 bits)
- 0xE4-0xE7: IN/OUT with immediate port
- 0xEC-0xEF: IN/OUT with DX
- 0xE8: CALL rel32
- 0xE9, 0xEB: JMP rel32, JMP rel8
- 0x70-0x7F: Jcc rel8
- 0xC3: RET
- 0xF6-0xF7: Group 3 (TEST/NOT/NEG/MUL/DIV)
- 0xFE-0xFF: Group 4/5 (INC/DEC/CALL/JMP indirect)
- 0x0F 0xB6/0xB7/0xBE/0xBF: MOVZX/MOVSX
- 0x0F 0x80-0x8F: Jcc rel32
- 0x0F 0x90-0x9F: SETcc

**Step 5: Run tests to verify they pass**

Run: same compile command
Expected: All tests pass

**Step 6: Commit**

```bash
git add tools/translator/include/x86_decoder.h tools/translator/src/decoders/x86_decoder.c \
        tools/translator/tests/test_x86_decoder.c
git commit -m "Implement x86 decoder: ~80 opcodes, ModR/M, SIB, two-byte table"
```

---

## Task 3: UIR Lifter

**Files:**
- Create: `tools/translator/include/uir.h` (full version with lifter API)
- Modify: `tools/translator/src/ir/uir.c` (replace placeholder)
- Create: `tools/translator/tests/test_uir.c`

**Step 1: Write uir.h**

Extend the existing stub with:
- Complete `uir_opcode_t` (add UIR_CMP, UIR_NEG, UIR_NOT, UIR_MOVZX, UIR_MOVSX, UIR_LEA, UIR_NOP, UIR_PUSH, UIR_POP)
- `uir_instruction_t`: opcode, dest, src1, src2, size, original_address
- `uir_block_t`: address, instructions[], count, next, branch, is_entry
- API: `uir_lift_function()`, `uir_free_blocks()`, `uir_print_block()`

**Step 2: Write failing tests**

Test UIR lifting of simple sequences:
- `IN AL, 0x60` → should produce `UIR_PORT_IN` with port=0x60, size=1
- `OUT 0x60, AL` → should produce `UIR_PORT_OUT` with port=0x60
- `MOV EAX, [EBX+4]` → should produce `UIR_LOAD`
- `CALL rel32` → should produce `UIR_CALL`
- Sequence with `Jcc` → should split into two basic blocks

**Step 3: Implement uir.c**

Key function: `uir_lift_function(const x86_decoded_t* insts, size_t count, uint64_t base)`
1. First pass: identify block boundaries (targets of jumps, after jumps)
2. Second pass: create blocks, translate each instruction:
   - IN/OUT → UIR_PORT_IN/OUT
   - MOV [mem], reg → UIR_STORE; MOV reg, [mem] → UIR_LOAD
   - ADD/SUB/AND/OR/XOR → corresponding UIR ops
   - CMP → UIR_CMP (implicit flag set)
   - CALL → UIR_CALL
   - RET → UIR_RET
   - Jcc → UIR_JZ/JNZ (set block's branch pointer)
   - JMP → UIR_JMP (set block's next pointer)
3. Link blocks: resolve jump targets to block pointers

**Step 4: Run tests, verify pass**

**Step 5: Commit**

```bash
git add tools/translator/include/uir.h tools/translator/src/ir/uir.c \
        tools/translator/tests/test_uir.c
git commit -m "Implement UIR lifter: x86 to platform-independent basic blocks"
```

---

## Task 4: Semantic Analyzer

**Files:**
- Create: `tools/translator/include/semantic.h`
- Modify: `tools/translator/src/ir/semantic.c` (replace placeholder)
- Create: `tools/translator/tests/test_semantic.c`

**Step 1: Write semantic.h**

```c
typedef struct {
    uint64_t        address;
    char*           name;           /* from exports, or "func_XXXX" */
    drv_category_t  primary_category;
    bool            has_port_io;
    bool            has_mmio;
    bool            has_timing;
    bool            has_pci;
    bool            has_scaffolding;
    size_t          hw_call_count;  /* # of hardware API calls */
    size_t          scaf_call_count; /* # of scaffolding API calls */
} sem_function_t;

typedef struct {
    sem_function_t* functions;
    size_t          function_count;
    size_t          hw_function_count;
    size_t          filtered_count;
} sem_result_t;
```

API:
- `int sem_classify_imports(pe_context_t* pe)` — tag each import with drv_category_t
- `int sem_analyze(pe_context_t* pe, uir_block_t* blocks, sem_result_t* result)` — discover functions, categorize
- `void sem_print_report(sem_result_t* result, FILE* out)` — summary
- `void sem_cleanup(sem_result_t* result)`

**Step 2: Write failing tests**

Test import classification: build a mock pe_context_t with imports like "READ_PORT_UCHAR" and "IoCompleteRequest", verify correct categorization.

**Step 3: Implement semantic.c**

- Import classification: loop imports, `strcmp` against `DRV_API_TABLE[].name`, store category
- Function discovery: look at CALL targets in UIR blocks, also export table entries
- Function categorization: walk each function's UIR blocks, check for PORT_IN/PORT_OUT opcodes and check CALL targets against classified imports
- Note: must link against `driver_extract.c` for `DRV_API_TABLE`. Or copy the table. Recommended: move the API table to a shared header or compile `driver_extract.c` as part of the translator.

**Step 4: Run tests, verify pass**

**Step 5: Commit**

```bash
git add tools/translator/include/semantic.h tools/translator/src/ir/semantic.c \
        tools/translator/tests/test_semantic.c
git commit -m "Implement semantic analyzer: classify imports, categorize functions"
```

---

## Task 5: Forth Code Generator

**Files:**
- Create: `tools/translator/src/codegen/forth_codegen.c`
- Create: `tools/translator/include/forth_codegen.h`
- Create: `tools/translator/tests/test_forth_codegen.c`

**Step 1: Write forth_codegen.h**

```c
/* Dependency entry: vocabulary name + list of words used from it */
typedef struct {
    const char* vocab_name;         /* e.g. "HARDWARE" */
    const char** words_used;        /* e.g. {"C@-PORT", "C!-PORT", NULL} */
} forth_dependency_t;

typedef struct {
    const char* vocab_name;         /* e.g. "SERIAL-16550" */
    const char* category;           /* e.g. "serial" */
    const char* source_type;        /* "extracted" or "hand-written" */
    const char* source_binary;      /* original filename or "none" */
    const char* vendor_id;          /* hex string or "none" */
    const char* device_id;          /* hex string or "none" */
    const char* ports_desc;         /* e.g. "0x3F8-0x3FF" */
    const char* mmio_desc;          /* e.g. "none" */
    const char* confidence;         /* "high", "medium", "low" */
    const forth_dependency_t* requires;  /* NULL-terminated array */
} forth_codegen_opts_t;

/* Generate complete Forth vocabulary from semantic analysis results */
char* forth_generate_vocabulary(const sem_result_t* sem,
                                 const pe_context_t* pe,
                                 const forth_codegen_opts_t* opts);
```

The codegen emits one `\ REQUIRES:` line per dependency entry:
```forth
\ REQUIRES: HARDWARE ( C@-PORT C!-PORT )
\ REQUIRES: TIMING ( MS-DELAY )
```

The `words_used` list is populated by the semantic analyzer: when it sees a
CALL to a classified import that maps to a Forth primitive, it records which
vocabulary provides that primitive and which word name it maps to.

**Step 2: Write failing tests**

Build a mock `sem_result_t` with one function that does port reads at offsets 0x00 and 0x05 from a base, verify the generated Forth contains:
- Catalog header comments with `\ REQUIRES:` lines
- `VOCABULARY` declaration
- `CONSTANT` definitions for register offsets
- `: WORD-NAME ... C@-PORT ;` definitions

**Step 3: Implement forth_codegen.c**

Output structure:
1. Catalog header block (structured comments)
2. `VOCABULARY <name>` / `<name> DEFINITIONS` / `HEX`
3. Register offset constants (from extracted port offsets)
4. Base variable and accessor word
5. For each hardware function: generate Forth word with port read/write operations
6. Init sequence (if detected)
7. `FORTH DEFINITIONS`

Reuse and refactor templates from `tools/driver-extract/driver_extract.c` (`drv_gen_port_read`, `drv_gen_poll_loop`, `drv_gen_init_sequence`).

**Step 4: Run tests, verify pass**

**Step 5: Commit**

```bash
git add tools/translator/include/forth_codegen.h tools/translator/src/codegen/forth_codegen.c \
        tools/translator/tests/test_forth_codegen.c
git commit -m "Implement Forth code generator with catalog-compatible output"
```

---

## Task 6: 16550 UART Reference Vocabulary

**Files:**
- Create: `forth/dict/serial-16550.fth`

**Step 1: Write the complete vocabulary from the 16550 datasheet**

This is written by hand, NOT by the extraction pipeline. It serves as the "known good" reference.

```forth
\ ====================================================================
\ CATALOG: SERIAL-16550
\ CATEGORY: serial
\ SOURCE: hand-written
\ SOURCE-BINARY: none
\ VENDOR-ID: none
\ DEVICE-ID: none
\ PORTS: 0x3F8-0x3FF
\ MMIO: none
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( C@-PORT C!-PORT )
\ ====================================================================

VOCABULARY SERIAL-16550
SERIAL-16550 DEFINITIONS
HEX

\ ---- Register Offsets (from 16550 datasheet) ----
00 CONSTANT RBR     \ Receive Buffer Register (read, DLAB=0)
00 CONSTANT THR     \ Transmit Holding Register (write, DLAB=0)
00 CONSTANT DLL     \ Divisor Latch Low (DLAB=1)
01 CONSTANT IER     \ Interrupt Enable Register (DLAB=0)
01 CONSTANT DLM     \ Divisor Latch High (DLAB=1)
02 CONSTANT IIR     \ Interrupt Identification Register (read)
02 CONSTANT FCR     \ FIFO Control Register (write)
03 CONSTANT LCR     \ Line Control Register
04 CONSTANT MCR     \ Modem Control Register
05 CONSTANT LSR     \ Line Status Register
06 CONSTANT MSR     \ Modem Status Register
07 CONSTANT SCR     \ Scratch Register

\ ---- LSR Bit Masks ----
01 CONSTANT LSR-DR      \ Data Ready
20 CONSTANT LSR-THRE    \ Transmitter Holding Register Empty
40 CONSTANT LSR-TEMT    \ Transmitter Empty
1E CONSTANT LSR-ERR     \ Error bits (OE+PE+FE+BI)

\ ---- LCR Bit Values ----
03 CONSTANT LCR-8N1     \ 8 data bits, no parity, 1 stop
80 CONSTANT LCR-DLAB    \ Divisor Latch Access Bit

\ ---- MCR Bit Values ----
01 CONSTANT MCR-DTR     \ Data Terminal Ready
02 CONSTANT MCR-RTS     \ Request to Send
08 CONSTANT MCR-OUT2    \ OUT2 (enables IRQ on PC)
0B CONSTANT MCR-NORMAL  \ DTR + RTS + OUT2

\ ---- FCR Bit Values ----
01 CONSTANT FCR-ENABLE  \ FIFO Enable
06 CONSTANT FCR-CLEAR   \ Clear both FIFOs
C0 CONSTANT FCR-TRIG14  \ 14-byte trigger level
C7 CONSTANT FCR-INIT    \ Enable + Clear + 14-byte trigger

\ ---- Baud Rate Divisors (115200 / desired baud) ----
0001 CONSTANT BAUD-115200
0002 CONSTANT BAUD-57600
0003 CONSTANT BAUD-38400
000C CONSTANT BAUD-9600
0018 CONSTANT BAUD-4800
0060 CONSTANT BAUD-1200

\ ---- Hardware Base ----
VARIABLE UART-BASE

: UART-REG  ( offset -- port )  UART-BASE @ + ;
: UART@     ( offset -- byte )  UART-REG C@-PORT ;
: UART!     ( byte offset -- )  UART-REG C!-PORT ;

\ ---- Status Words ----
: TX-READY?  ( -- flag )  LSR UART@ LSR-THRE AND 0<> ;
: RX-READY?  ( -- flag )  LSR UART@ LSR-DR AND 0<> ;
: TX-EMPTY?  ( -- flag )  LSR UART@ LSR-TEMT AND 0<> ;
: RX-ERROR?  ( -- flag )  LSR UART@ LSR-ERR AND 0<> ;

\ ---- I/O Words ----
: UART-EMIT  ( char -- )
    BEGIN TX-READY? UNTIL
    THR UART!
;

: UART-KEY  ( -- char )
    BEGIN RX-READY? UNTIL
    RBR UART@
;

: UART-KEY?  ( -- flag )
    RX-READY?
;

: UART-TYPE  ( addr len -- )
    0 ?DO
        DUP C@ UART-EMIT
        1+
    LOOP
    DROP
;

\ ---- Baud Rate ----
: UART-BAUD!  ( divisor -- )
    LCR UART@ LCR-DLAB OR LCR UART!     \ Set DLAB
    DUP FF AND DLL UART!                  \ Divisor low byte
    8 RSHIFT DLM UART!                    \ Divisor high byte
    LCR UART@ LCR-DLAB INVERT AND LCR UART!  \ Clear DLAB
;

\ ---- Initialization ----
: UART-INIT  ( port -- )
    UART-BASE !
    00 IER UART!                 \ Disable all interrupts
    LCR-DLAB LCR UART!          \ Enable DLAB
    BAUD-115200 DUP
    FF AND DLL UART!             \ Divisor low (115200 baud)
    8 RSHIFT DLM UART!          \ Divisor high
    LCR-8N1 LCR UART!           \ 8N1, DLAB off
    FCR-INIT FCR UART!          \ Enable FIFO, clear, 14-byte trigger
    MCR-NORMAL MCR UART!        \ DTR + RTS + OUT2
;

\ ---- Loopback Test ----
: UART-LOOPBACK-TEST  ( port -- flag )
    UART-BASE !
    \ Enable loopback mode (MCR bit 4)
    MCR UART@ 10 OR MCR UART!
    \ Send test byte
    A5 THR UART!
    \ Small delay
    10 0 DO LOOP
    \ Read back
    RBR UART@
    \ Disable loopback
    MCR UART@ 10 INVERT AND MCR UART!
    \ Check
    A5 =
;

FORTH DEFINITIONS
DECIMAL
```

**Step 2: Verify syntax is valid Forth**

Review the vocabulary manually — check stack comments, balanced control flow, all referenced words exist in HARDWARE dictionary. This is manual review, not automated.

**Step 3: Commit**

```bash
git add forth/dict/serial-16550.fth
git commit -m "Add hand-written 16550 UART reference vocabulary from datasheet"
```

---

## Task 7: Pipeline Integration

**Files:**
- Modify: `tools/translator/src/main/translator.c` (wire all components)
- Modify: `tools/translator/Makefile` (add new source files, test targets)
- Create: `tools/translator/tests/test_pipeline.c`

**Step 1: Update Makefile**

Add include path for new headers. Add test targets:
```makefile
test-pe:
    $(CC) $(CFLAGS_DEBUG) -o $(BUILDDIR)/test_pe tests/test_pe_loader.c src/loaders/pe_loader.c
    ./$(BUILDDIR)/test_pe

test-x86:
    $(CC) $(CFLAGS_DEBUG) -o $(BUILDDIR)/test_x86 tests/test_x86_decoder.c src/decoders/x86_decoder.c
    ./$(BUILDDIR)/test_x86

test-uir:
    $(CC) $(CFLAGS_DEBUG) -o $(BUILDDIR)/test_uir tests/test_uir.c src/ir/uir.c src/decoders/x86_decoder.c
    ./$(BUILDDIR)/test_uir

test-all: test-pe test-x86 test-uir $(TARGET)
    @echo "All tests passed"
```

**Step 2: Wire translate_buffer() in translator.c**

Replace the placeholder implementation with the real pipeline:
1. Detect PE magic → call `pe_load()`
2. Find .text section → init `x86_decoder_t`
3. `x86_decode_range()` → decoded instructions
4. `uir_lift_function()` → UIR blocks
5. If target == `TARGET_FORTH`: `sem_classify_imports()` → `sem_analyze()` → `forth_generate_vocabulary()`
6. If target == `TARGET_DISASM`: print decoded instructions
7. If target == `TARGET_UIR`: print UIR blocks

Add `-i` (print imports) and `-s` (print sections) support using `pe_print_info()`.

**Step 3: Write end-to-end test**

Create a test that:
1. Builds a synthetic PE with known code (IN/OUT instructions + a few MOVs)
2. Feeds it through the full pipeline with `-t forth`
3. Checks the output contains expected Forth words

**Step 4: Build and test everything**

Run: `cd tools/translator && make clean && make && make test-all`
Expected: All components build, all tests pass

**Step 5: Test with translator CLI**

Run: `./bin/translator -t disasm -v <some-test-binary>` to verify the CLI works end-to-end.

**Step 6: Commit**

```bash
git add tools/translator/src/main/translator.c tools/translator/Makefile \
        tools/translator/tests/test_pipeline.c
git commit -m "Wire extraction pipeline: PE -> x86 -> UIR -> semantic -> Forth"
```

---

## Task 8: Update Driver-Extract Headers

**Files:**
- Modify: `tools/driver-extract/pe_loader.h` (point to translator's full version)
- Modify: `tools/driver-extract/x86_decoder.h` (point to translator's full version)
- Modify: `tools/driver-extract/uir.h` (point to translator's full version)

**Step 1: Replace stub headers with includes**

Each stub header in `tools/driver-extract/` should become a thin redirect:
```c
/* pe_loader.h - Now lives in tools/translator/include/ */
#include "../translator/include/pe_loader.h"
```

This keeps `driver_extract.c` compiling while using the real implementations.

**Step 2: Verify driver-extract still builds**

Run: `cd tools/driver-extract && make clean && make`
Expected: Builds without errors

**Step 3: Commit**

```bash
git add tools/driver-extract/pe_loader.h tools/driver-extract/x86_decoder.h \
        tools/driver-extract/uir.h
git commit -m "Point driver-extract headers to translator's full implementations"
```

---

## Summary: Build Sequence

| Task | Component | Depends On | Estimated Complexity |
|------|-----------|-----------|---------------------|
| 1 | PE Loader | None | Medium (~400 lines) |
| 2 | x86 Decoder | None | Large (~800 lines) |
| 3 | UIR Lifter | Task 2 | Medium (~300 lines) |
| 4 | Semantic Analyzer | Task 1, 3 | Medium (~250 lines) |
| 5 | Forth Codegen | Task 4 | Medium (~300 lines) |
| 6 | 16550 Reference | None | Small (~100 lines) |
| 7 | Integration | Tasks 1-5 | Medium (~200 lines) |
| 8 | Header Cleanup | Task 7 | Small (~20 lines) |

Tasks 1, 2, and 6 can be done in parallel (no dependencies).
Tasks 3-5 are sequential (each needs the previous).
Tasks 7-8 are integration after all components exist.
