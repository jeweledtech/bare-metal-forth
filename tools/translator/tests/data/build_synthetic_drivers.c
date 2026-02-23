/* ============================================================================
 * Synthetic Driver Builder — serial16550_synth.sys
 * ============================================================================
 *
 * Generates a synthetic Windows .sys PE32 binary for Ghidra validation testing.
 * The binary contains:
 *   - UART_INIT, UART_SEND, UART_RECV (hardware port I/O — should be KEPT)
 *   - DriverEntry (scaffolding — should be FILTERED by semantic analyzer)
 *   - HAL.dll imports: READ_PORT_UCHAR, WRITE_PORT_UCHAR (hardware)
 *   - ntoskrnl.exe import: IoCompleteRequest (scaffolding)
 *
 * Based on build_16550_pe() from test_16550_driver.c with additions for
 * scaffolding functions and imports to exercise the full translator pipeline.
 *
 * Usage: build_synthetic_drivers [output_directory]
 *        Writes serial16550_synth.sys to the given directory (default: .)
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "pe_format.h"

static uint8_t* build_serial16550_synth(size_t* out_size) {
    size_t file_size = 0xC00;  /* 3KB: headers + .text + .idata + .edata */
    uint8_t* buf = calloc(1, file_size);
    if (!buf) return NULL;

    /* ---- DOS header ---- */
    dos_header_t* dos = (dos_header_t*)buf;
    dos->e_magic = DOS_MAGIC;
    dos->e_lfanew = 0x40;

    /* ---- PE signature ---- */
    *(uint32_t*)(buf + 0x40) = PE_SIGNATURE;

    /* ---- COFF header ---- */
    coff_header_t* coff = (coff_header_t*)(buf + 0x44);
    coff->machine = COFF_MACHINE_I386;
    coff->number_of_sections = 3;  /* .text + .idata + .edata */
    coff->size_of_optional_header = 224;

    /* ---- PE32 Optional header ---- */
    pe32_optional_header_t* opt = (pe32_optional_header_t*)(buf + 0x58);
    opt->magic = PE_OPT_MAGIC_PE32;
    opt->address_of_entry_point = 0x1025;  /* DriverEntry */
    opt->image_base = 0x10000;
    opt->section_alignment = 0x1000;
    opt->file_alignment = 0x200;
    opt->size_of_image = 0x5000;
    opt->size_of_headers = 0x200;
    opt->number_of_rva_and_sizes = 16;

    /* ---- Data directories ---- */
    data_directory_t* dirs = (data_directory_t*)(buf + 0x58 + 96);
    /* Export table at RVA 0x3000 */
    dirs[DATA_DIR_EXPORT].virtual_address = 0x3000;
    dirs[DATA_DIR_EXPORT].size = 0x100;
    /* Import table at RVA 0x2000 */
    dirs[DATA_DIR_IMPORT].virtual_address = 0x2000;
    dirs[DATA_DIR_IMPORT].size = sizeof(import_descriptor_t) * 3;  /* 2 DLLs + null */

    /* ---- Section headers (at 0x138) ---- */

    /* .text */
    section_header_t* sec_text = (section_header_t*)(buf + 0x138);
    memcpy(sec_text->name, ".text\0\0\0", 8);
    sec_text->virtual_size = 0x2D;  /* updated after code generation */
    sec_text->virtual_address = 0x1000;
    sec_text->size_of_raw_data = 0x200;
    sec_text->pointer_to_raw_data = 0x200;
    sec_text->characteristics = SECTION_CNT_CODE | SECTION_MEM_EXECUTE
                                | SECTION_MEM_READ;

    /* .idata */
    section_header_t* sec_idata = (section_header_t*)(buf + 0x138 + 40);
    memcpy(sec_idata->name, ".idata\0\0", 8);
    sec_idata->virtual_size = 0x200;
    sec_idata->virtual_address = 0x2000;
    sec_idata->size_of_raw_data = 0x200;
    sec_idata->pointer_to_raw_data = 0x400;
    sec_idata->characteristics = SECTION_CNT_INITIALIZED_DATA | SECTION_MEM_READ;

    /* .edata */
    section_header_t* sec_edata = (section_header_t*)(buf + 0x138 + 80);
    memcpy(sec_edata->name, ".edata\0\0", 8);
    sec_edata->virtual_size = 0x200;
    sec_edata->virtual_address = 0x3000;
    sec_edata->size_of_raw_data = 0x200;
    sec_edata->pointer_to_raw_data = 0x600;
    sec_edata->characteristics = SECTION_CNT_INITIALIZED_DATA | SECTION_MEM_READ;

    /* ============================================================
     * .text code (at file offset 0x200)
     * ============================================================ */
    uint8_t* text = buf + 0x200;
    size_t off = 0;

    /* ---- UART_INIT (offset 0x00) ----
     * E6 F9    OUT 0xF9, AL   (IER = 0x3F9)
     * E6 FB    OUT 0xFB, AL   (LCR = 0x3FB)
     * E6 F8    OUT 0xF8, AL   (DLL = 0x3F8)
     * E6 FB    OUT 0xFB, AL   (LCR = 0x3FB)
     * E6 FA    OUT 0xFA, AL   (FCR = 0x3FA)
     * C3       RET
     */
    text[off++] = 0xE6; text[off++] = 0xF9;  /* OUT 0xF9, AL */
    text[off++] = 0xE6; text[off++] = 0xFB;  /* OUT 0xFB, AL */
    text[off++] = 0xE6; text[off++] = 0xF8;  /* OUT 0xF8, AL */
    text[off++] = 0xE6; text[off++] = 0xFB;  /* OUT 0xFB, AL */
    text[off++] = 0xE6; text[off++] = 0xFA;  /* OUT 0xFA, AL */
    text[off++] = 0xC3;                       /* RET */
    /* off = 0x0B */

    /* ---- UART_SEND (offset 0x0B) ----
     * 55             PUSH EBP
     * 89 E5          MOV EBP, ESP
     * E4 FD          IN AL, 0xFD   (LSR = 0x3FD)
     * A8 20          TEST AL, 0x20 (THRE bit)
     * 74 FA          JZ -6 (back to IN)
     * E6 F8          OUT 0xF8, AL  (THR)
     * 5D             POP EBP
     * C3             RET
     */
    text[off++] = 0x55;                       /* PUSH EBP */
    text[off++] = 0x89; text[off++] = 0xE5;  /* MOV EBP, ESP */
    text[off++] = 0xE4; text[off++] = 0xFD;  /* IN AL, 0xFD */
    text[off++] = 0xA8; text[off++] = 0x20;  /* TEST AL, 0x20 */
    text[off++] = 0x74; text[off++] = 0xFA;  /* JZ -6 (back to IN) */
    text[off++] = 0xE6; text[off++] = 0xF8;  /* OUT 0xF8, AL */
    text[off++] = 0x5D;                       /* POP EBP */
    text[off++] = 0xC3;                       /* RET */
    /* off = 0x19 */

    /* ---- UART_RECV (offset 0x19) ----
     * 55             PUSH EBP
     * 89 E5          MOV EBP, ESP
     * E4 FD          IN AL, 0xFD   (LSR)
     * A8 01          TEST AL, 0x01 (DR bit)
     * 74 FA          JZ -6 (back to IN)
     * E4 F8          IN AL, 0xF8   (RBR)
     * 5D             POP EBP
     * C3             RET
     */
    text[off++] = 0x55;                       /* PUSH EBP */
    text[off++] = 0x89; text[off++] = 0xE5;  /* MOV EBP, ESP */
    text[off++] = 0xE4; text[off++] = 0xFD;  /* IN AL, 0xFD */
    text[off++] = 0xA8; text[off++] = 0x01;  /* TEST AL, 0x01 */
    text[off++] = 0x74; text[off++] = 0xFA;  /* JZ -6 */
    text[off++] = 0xE4; text[off++] = 0xF8;  /* IN AL, 0xF8 */
    text[off++] = 0x5D;                       /* POP EBP */
    text[off++] = 0xC3;                       /* RET */
    /* off = 0x27 */

    /* ---- DriverEntry (offset 0x27) ---- SCAFFOLDING
     * B8 00 00 00 00   MOV EAX, 0  (STATUS_SUCCESS)
     * C3               RET
     */
    text[off++] = 0xB8;                       /* MOV EAX, imm32 */
    text[off++] = 0x00; text[off++] = 0x00;
    text[off++] = 0x00; text[off++] = 0x00;  /* 0x00000000 = STATUS_SUCCESS */
    text[off++] = 0xC3;                       /* RET */
    /* off = 0x2D */

    /* Update .text virtual size to actual code size */
    sec_text->virtual_size = (uint32_t)off;

    /* ============================================================
     * .idata — Import Table (at file offset 0x400, RVA 0x2000)
     * ============================================================
     *
     * Layout:
     *   0x400 (RVA 0x2000): import_descriptor[0] — HAL.dll
     *   0x414 (RVA 0x2014): import_descriptor[1] — ntoskrnl.exe
     *   0x428 (RVA 0x2028): import_descriptor[2] — null terminator
     *
     *   0x480 (RVA 0x2080): "HAL.dll"
     *   0x4A0 (RVA 0x20A0): HAL.dll ILT entries
     *   0x4C0 (RVA 0x20C0): HAL.dll IAT entries
     *   0x4E0 (RVA 0x20E0): Hint/Name "READ_PORT_UCHAR"
     *   0x4F8 (RVA 0x20F8): Hint/Name "WRITE_PORT_UCHAR"
     *
     *   0x520 (RVA 0x2120): "ntoskrnl.exe"
     *   0x530 (RVA 0x2130): ntoskrnl.exe ILT entries
     *   0x540 (RVA 0x2140): ntoskrnl.exe IAT entries
     *   0x550 (RVA 0x2150): Hint/Name "IoCompleteRequest"
     */
    import_descriptor_t* imp = (import_descriptor_t*)(buf + 0x400);

    /* HAL.dll imports */
    imp[0].name_rva = 0x2080;
    imp[0].import_lookup_table_rva = 0x20A0;
    imp[0].import_address_table_rva = 0x20C0;

    /* ntoskrnl.exe imports */
    imp[1].name_rva = 0x2120;
    imp[1].import_lookup_table_rva = 0x2130;
    imp[1].import_address_table_rva = 0x2140;

    /* imp[2] is already zero (null terminator) from calloc */

    /* HAL.dll name */
    strcpy((char*)(buf + 0x480), "HAL.dll");

    /* HAL.dll ILT entries: READ_PORT_UCHAR, WRITE_PORT_UCHAR */
    *(uint32_t*)(buf + 0x4A0) = 0x20E0;  /* hint/name for READ_PORT_UCHAR */
    *(uint32_t*)(buf + 0x4A4) = 0x20F8;  /* hint/name for WRITE_PORT_UCHAR */
    /* HAL.dll IAT entries (same) */
    *(uint32_t*)(buf + 0x4C0) = 0x20E0;
    *(uint32_t*)(buf + 0x4C4) = 0x20F8;

    /* HAL.dll Hint/Name entries */
    *(uint16_t*)(buf + 0x4E0) = 0;  /* hint */
    strcpy((char*)(buf + 0x4E2), "READ_PORT_UCHAR");
    *(uint16_t*)(buf + 0x4F8) = 0;  /* hint */
    strcpy((char*)(buf + 0x4FA), "WRITE_PORT_UCHAR");

    /* ntoskrnl.exe name */
    strcpy((char*)(buf + 0x520), "ntoskrnl.exe");

    /* ntoskrnl.exe ILT entries: IoCompleteRequest */
    *(uint32_t*)(buf + 0x530) = 0x2150;  /* hint/name for IoCompleteRequest */
    /* ntoskrnl.exe IAT entries (same) */
    *(uint32_t*)(buf + 0x540) = 0x2150;

    /* ntoskrnl.exe Hint/Name entry */
    *(uint16_t*)(buf + 0x550) = 0;  /* hint */
    strcpy((char*)(buf + 0x552), "IoCompleteRequest");

    /* ============================================================
     * .edata — Export Table (at file offset 0x600, RVA 0x3000)
     * ============================================================
     *
     * Layout (4 exports):
     *   0x600 (RVA 0x3000): Export directory (40 bytes)
     *   0x628 (RVA 0x3028): Export Address Table (4 x 4 = 16 bytes)
     *   0x638 (RVA 0x3038): Export Name Pointer Table (4 x 4 = 16 bytes)
     *   0x648 (RVA 0x3048): Export Ordinal Table (4 x 2 = 8 bytes)
     *   0x660 (RVA 0x3060): "serial16550_synth.sys"
     *   0x680 (RVA 0x3080): "DriverEntry"
     *   0x690 (RVA 0x3090): "UART_INIT"
     *   0x6A0 (RVA 0x30A0): "UART_RECV"
     *   0x6B0 (RVA 0x30B0): "UART_SEND"
     *
     * Note: Export names must be sorted alphabetically per PE spec.
     */
    uint8_t* edata = buf + 0x600;

    /* Export directory table */
    uint32_t* exp_dir = (uint32_t*)edata;
    exp_dir[0] = 0;                  /* Characteristics */
    exp_dir[1] = 0;                  /* TimeDateStamp */
    exp_dir[2] = 0;                  /* MajorVersion/MinorVersion */
    exp_dir[3] = 0x3060;             /* Name RVA -> "serial16550_synth.sys" */
    exp_dir[4] = 1;                  /* OrdinalBase */
    exp_dir[5] = 4;                  /* NumberOfFunctions */
    exp_dir[6] = 4;                  /* NumberOfNames */
    exp_dir[7] = 0x3028;             /* AddressOfFunctions RVA */
    exp_dir[8] = 0x3038;             /* AddressOfNames RVA */
    exp_dir[9] = 0x3048;             /* AddressOfNameOrdinals RVA */

    /* Export Address Table (at edata+0x28)
     * Ordinals map: 0=UART_INIT, 1=UART_SEND, 2=UART_RECV, 3=DriverEntry */
    uint32_t* eat = (uint32_t*)(edata + 0x28);
    eat[0] = 0x1000;   /* UART_INIT at text+0x00 */
    eat[1] = 0x100B;   /* UART_SEND at text+0x0B */
    eat[2] = 0x1018;   /* UART_RECV at text+0x18 */
    eat[3] = 0x1025;   /* DriverEntry at text+0x25 */

    /* Export Name Pointer Table (at edata+0x38)
     * Names sorted alphabetically: DriverEntry, UART_INIT, UART_RECV, UART_SEND */
    uint32_t* enpt = (uint32_t*)(edata + 0x38);
    enpt[0] = 0x3080;   /* -> "DriverEntry" */
    enpt[1] = 0x3090;   /* -> "UART_INIT" */
    enpt[2] = 0x30A0;   /* -> "UART_RECV" */
    enpt[3] = 0x30B0;   /* -> "UART_SEND" */

    /* Export Ordinal Table (at edata+0x48)
     * Maps sorted name index to EAT index */
    uint16_t* eot = (uint16_t*)(edata + 0x48);
    eot[0] = 3;   /* DriverEntry -> EAT[3] */
    eot[1] = 0;   /* UART_INIT -> EAT[0] */
    eot[2] = 2;   /* UART_RECV -> EAT[2] */
    eot[3] = 1;   /* UART_SEND -> EAT[1] */

    /* Strings */
    strcpy((char*)(edata + 0x60), "serial16550_synth.sys");
    strcpy((char*)(edata + 0x80), "DriverEntry");
    strcpy((char*)(edata + 0x90), "UART_INIT");
    strcpy((char*)(edata + 0xA0), "UART_RECV");
    strcpy((char*)(edata + 0xB0), "UART_SEND");

    *out_size = file_size;
    return buf;
}

int main(int argc, char* argv[]) {
    const char* outdir = ".";
    if (argc > 1) {
        outdir = argv[1];
    }

    /* Build the synthetic PE */
    size_t size = 0;
    uint8_t* pe = build_serial16550_synth(&size);
    if (!pe) {
        fprintf(stderr, "ERROR: Failed to allocate PE buffer\n");
        return 1;
    }

    /* Construct output path */
    char path[512];
    snprintf(path, sizeof(path), "%s/serial16550_synth.sys", outdir);

    /* Write to disk */
    FILE* f = fopen(path, "wb");
    if (!f) {
        fprintf(stderr, "ERROR: Cannot open %s for writing\n", path);
        free(pe);
        return 1;
    }
    size_t written = fwrite(pe, 1, size, f);
    fclose(f);
    free(pe);

    if (written != size) {
        fprintf(stderr, "ERROR: Short write (%zu of %zu bytes)\n", written, size);
        return 1;
    }

    printf("Generated %s (%zu bytes)\n", path, size);
    return 0;
}
