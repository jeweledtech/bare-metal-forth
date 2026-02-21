/*
 * x86 Instruction Decoder - Redirect Header
 *
 * This header redirects to the full x86 decoder implementation
 * in tools/translator/include/x86_decoder.h.
 *
 * The stub had a 2-parameter x86_decoder_init(); the full version
 * takes 5 parameters. A compatibility wrapper is provided below.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 */

#ifndef DRV_X86_DECODER_COMPAT_H
#define DRV_X86_DECODER_COMPAT_H

#include "../translator/include/x86_decoder.h"

/* Backwards compatibility: the stub's 2-parameter init.
 * Sets code/size/base to defaults — caller must set them before decoding. */
static inline void x86_decoder_init_simple(x86_decoder_t* dec, x86_mode_t mode) {
    x86_decoder_init(dec, mode, NULL, 0, 0);
}

#endif /* DRV_X86_DECODER_COMPAT_H */
