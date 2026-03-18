/* ============================================================================
 * DOS .com Loader
 * ============================================================================
 *
 * Loads DOS .com flat binary files.  A .com file has no header — the entire
 * file IS the code+data, loaded at virtual address 0x100 (COM origin).
 * Files are 16-bit real mode x86 and limited to 65280 bytes.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef COM_LOADER_H
#define COM_LOADER_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#define COM_LOAD_ADDRESS  0x0100   /* CS:0100 — standard COM origin */
#define COM_MAX_SIZE      65280    /* 0xFF00 — max .com file size */

typedef struct {
    const uint8_t*  code;       /* points into caller's data buffer */
    size_t          code_size;  /* entire file = code + data */
    uint32_t        load_addr;  /* always COM_LOAD_ADDRESS */
    bool            is_16bit;   /* always true for COM */
} com_context_t;

/* Load a .com file from a memory buffer.
 * Returns 0 on success, -1 on error (too large, NULL data). */
int com_load(com_context_t* ctx, const uint8_t* data, size_t size);

/* No-op cleanup (COM loader doesn't allocate). */
void com_cleanup(com_context_t* ctx);

#endif /* COM_LOADER_H */
