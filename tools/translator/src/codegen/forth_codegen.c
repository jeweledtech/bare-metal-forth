/* ============================================================================
 * Forth Code Generator
 * ============================================================================
 *
 * Generates complete Forth vocabulary source files from extracted driver
 * analysis results. Output follows the catalog header format and vocabulary
 * pattern established in forth/dict/serial-16550.fth.
 *
 * Output structure:
 *   1. Catalog header (structured comments with REQUIRES: lines)
 *   2. VOCABULARY <name> / <name> DEFINITIONS / HEX
 *   3. Register offset constants
 *   4. Base variable and accessor words
 *   5. Hardware function words (port read/write)
 *   6. FORTH DEFINITIONS / DECIMAL
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "forth_codegen.h"

/* ---- Dynamic string buffer ---- */

typedef struct {
    char*   data;
    size_t  len;
    size_t  cap;
} strbuf_t;

static void sb_init(strbuf_t* sb) {
    sb->cap = 4096;
    sb->len = 0;
    sb->data = malloc(sb->cap);
    sb->data[0] = '\0';
}

static void sb_ensure(strbuf_t* sb, size_t additional) {
    while (sb->len + additional + 1 > sb->cap) {
        sb->cap *= 2;
        sb->data = realloc(sb->data, sb->cap);
    }
}

static void sb_append(strbuf_t* sb, const char* str) {
    size_t slen = strlen(str);
    sb_ensure(sb, slen);
    memcpy(sb->data + sb->len, str, slen + 1);
    sb->len += slen;
}

static void sb_printf(strbuf_t* sb, const char* fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int needed = vsnprintf(NULL, 0, fmt, ap);
    va_end(ap);

    if (needed < 0) return;
    sb_ensure(sb, (size_t)needed);

    va_start(ap, fmt);
    vsnprintf(sb->data + sb->len, (size_t)needed + 1, fmt, ap);
    va_end(ap);
    sb->len += (size_t)needed;
}

/* ---- Port size to Forth word ---- */

static const char* read_word_for_size(uint8_t size) {
    switch (size) {
    case 1:  return "C@-PORT";
    case 2:  return "W@-PORT";
    case 4:  return "@-PORT";
    default: return "C@-PORT";
    }
}

static const char* write_word_for_size(uint8_t size) {
    switch (size) {
    case 1:  return "C!-PORT";
    case 2:  return "W!-PORT";
    case 4:  return "!-PORT";
    default: return "C!-PORT";
    }
}

/* ---- Generate catalog header ---- */

static void emit_catalog_header(strbuf_t* sb, const forth_codegen_opts_t* opts) {
    sb_append(sb, "\\ ====================================================================\n");
    sb_printf(sb, "\\ CATALOG: %s\n", opts->vocab_name);
    sb_printf(sb, "\\ CATEGORY: %s\n", opts->category ? opts->category : "unknown");
    sb_printf(sb, "\\ SOURCE: %s\n", opts->source_type ? opts->source_type : "unknown");
    sb_printf(sb, "\\ SOURCE-BINARY: %s\n", opts->source_binary ? opts->source_binary : "none");
    sb_printf(sb, "\\ VENDOR-ID: %s\n", opts->vendor_id ? opts->vendor_id : "none");
    sb_printf(sb, "\\ DEVICE-ID: %s\n", opts->device_id ? opts->device_id : "none");
    sb_printf(sb, "\\ PORTS: %s\n", opts->ports_desc ? opts->ports_desc : "none");
    sb_printf(sb, "\\ MMIO: %s\n", opts->mmio_desc ? opts->mmio_desc : "none");
    sb_printf(sb, "\\ CONFIDENCE: %s\n", opts->confidence ? opts->confidence : "low");

    /* REQUIRES: lines */
    if (opts->requires) {
        for (const forth_dependency_t* dep = opts->requires;
             dep->vocab_name != NULL; dep++) {
            sb_printf(sb, "\\ REQUIRES: %s ( ", dep->vocab_name);
            if (dep->words_used) {
                for (const char** w = dep->words_used; *w != NULL; w++) {
                    if (w != dep->words_used) sb_append(sb, " ");
                    sb_append(sb, *w);
                }
            }
            sb_append(sb, " )\n");
        }
    }

    sb_append(sb, "\\ ====================================================================\n\n");
}

/* ---- Generate vocabulary preamble ---- */

static void emit_vocabulary_preamble(strbuf_t* sb, const char* name) {
    sb_printf(sb, "VOCABULARY %s\n", name);
    sb_printf(sb, "%s DEFINITIONS\n", name);
    sb_append(sb, "HEX\n\n");
}

/* ---- Generate register constants ---- */

static void emit_register_constants(strbuf_t* sb, const uint16_t* offsets,
                                     size_t count) {
    if (count == 0) return;

    sb_append(sb, "\\ ---- Register Offsets (extracted from driver) ----\n");
    for (size_t i = 0; i < count; i++) {
        sb_printf(sb, "%02X CONSTANT REG-%02X\n", offsets[i], offsets[i]);
    }
    sb_append(sb, "\n");
}

/* ---- Generate base variable and accessors ---- */

static void emit_base_accessors(strbuf_t* sb, const char* name) {
    sb_append(sb, "\\ ---- Hardware Base ----\n");
    sb_printf(sb, "VARIABLE %s-BASE\n\n", name);
    sb_printf(sb, ": %s-REG  ( offset -- port )  %s-BASE @ + ;\n", name, name);
    sb_printf(sb, ": %s@     ( offset -- byte )  %s-REG C@-PORT ;\n", name, name);
    sb_printf(sb, ": %s!     ( byte offset -- )  %s-REG C!-PORT ;\n\n", name, name);
}

/* ---- Generate function word ---- */

static void emit_function(strbuf_t* sb, const forth_gen_function_t* func,
                           const char* vocab_name) {
    if (func->port_op_count == 0) {
        /* No port ops — just emit a stub */
        sb_printf(sb, ": %s  ( -- )  \\ extracted from 0x%llX\n",
                  func->name, (unsigned long long)func->address);
        sb_append(sb, ";\n\n");
        return;
    }

    /* Single port operation — emit a simple word */
    if (func->port_op_count == 1) {
        const forth_port_op_t* op = &func->port_ops[0];
        if (op->is_write) {
            sb_printf(sb, ": %s  ( value -- )\n", func->name);
            sb_printf(sb, "    %02X %s-REG %s\n",
                      op->port_offset, vocab_name, write_word_for_size(op->size));
        } else {
            sb_printf(sb, ": %s  ( -- value )\n", func->name);
            sb_printf(sb, "    %02X %s-REG %s\n",
                      op->port_offset, vocab_name, read_word_for_size(op->size));
        }
        sb_append(sb, ";\n\n");
        return;
    }

    /* Multiple port operations — emit sequentially */
    sb_printf(sb, ": %s  ( -- )  \\ %zu port operations\n",
              func->name, func->port_op_count);
    for (size_t i = 0; i < func->port_op_count; i++) {
        const forth_port_op_t* op = &func->port_ops[i];
        if (op->is_write) {
            sb_printf(sb, "    %02X %s-REG %s\n",
                      op->port_offset, vocab_name, write_word_for_size(op->size));
        } else {
            sb_printf(sb, "    %02X %s-REG %s\n",
                      op->port_offset, vocab_name, read_word_for_size(op->size));
        }
    }
    sb_append(sb, ";\n\n");
}

/* ---- Generate footer ---- */

static void emit_footer(strbuf_t* sb) {
    sb_append(sb, "FORTH DEFINITIONS\n");
    sb_append(sb, "DECIMAL\n");
}

/* ============================================================================
 * Public API
 * ============================================================================ */

char* forth_generate(const forth_codegen_input_t* input) {
    if (!input) return NULL;

    strbuf_t sb;
    sb_init(&sb);

    /* 1. Catalog header */
    emit_catalog_header(&sb, &input->opts);

    /* 2. Vocabulary preamble */
    emit_vocabulary_preamble(&sb, input->opts.vocab_name);

    /* 3. Register constants (if any) */
    emit_register_constants(&sb, input->port_offsets, input->port_offset_count);

    /* 4. Base variable and accessors (if we have any port operations) */
    bool has_ports = input->port_offset_count > 0;
    if (!has_ports) {
        /* Check functions for port ops */
        for (size_t i = 0; i < input->function_count && !has_ports; i++) {
            if (input->functions[i].port_op_count > 0) has_ports = true;
        }
    }
    if (has_ports) {
        emit_base_accessors(&sb, input->opts.vocab_name);
    }

    /* 5. Function words */
    if (input->function_count > 0) {
        sb_append(&sb, "\\ ---- Extracted Functions ----\n");
        for (size_t i = 0; i < input->function_count; i++) {
            emit_function(&sb, &input->functions[i], input->opts.vocab_name);
        }
    }

    /* 6. Footer */
    emit_footer(&sb);

    return sb.data;
}

char* forth_port_range_desc(uint16_t base_port, size_t register_count) {
    char* buf = malloc(32);
    if (!buf) return NULL;

    if (register_count <= 1) {
        snprintf(buf, 32, "0x%X", base_port);
    } else {
        snprintf(buf, 32, "0x%X-0x%X",
                 base_port, (unsigned)(base_port + register_count - 1));
    }
    return buf;
}

void forth_codegen_opts_init(forth_codegen_opts_t* opts) {
    memset(opts, 0, sizeof(*opts));
    opts->source_type = "extracted";
    opts->vendor_id = "none";
    opts->device_id = "none";
    opts->ports_desc = "none";
    opts->mmio_desc = "none";
    opts->confidence = "low";
}
