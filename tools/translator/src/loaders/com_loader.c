/* ============================================================================
 * DOS .com Loader
 * ============================================================================
 *
 * A .com file is a flat binary image with no header.  The entire file loads
 * at CS:0100 and executes from offset 0.  Maximum size is 65280 bytes
 * (0xFF00) — the segment minus the PSP.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include "com_loader.h"
#include <string.h>

int com_load(com_context_t* ctx, const uint8_t* data, size_t size) {
    if (!ctx || !data || size == 0)
        return -1;

    if (size > COM_MAX_SIZE)
        return -1;

    memset(ctx, 0, sizeof(*ctx));
    ctx->code = data;
    ctx->code_size = size;
    ctx->load_addr = COM_LOAD_ADDRESS;
    ctx->is_16bit = true;
    return 0;
}

void com_cleanup(com_context_t* ctx) {
    if (ctx)
        memset(ctx, 0, sizeof(*ctx));
}
