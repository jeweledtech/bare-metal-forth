/* ============================================================================
 * Universal Binary Translator - Main Entry Point
 * ============================================================================
 *
 * Usage: translator <binary> [options]
 *
 * Options:
 *   -t TARGET   Output target (disasm, uir, forth, c, x64, arm64, riscv64)
 *   -o FILE     Output file (default: stdout)
 *   -f FUNC     Extract specific function
 *   -n NAME     Vocabulary name for Forth output (default: derive from filename)
 *   -b ADDR     Base address for raw binaries
 *   -a          Print binary analysis
 *   -S          Enable semantic analysis
 *   -s          Print sections
 *   -i          Print imports
 *   -e          Print exports
 *   -y          Print symbols
 *   -v          Verbose output
 *   -O LEVEL    Optimization level (0-3)
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdbool.h>

#include "translator.h"
#include "pe_loader.h"
#include "format_detect.h"
#include "com_loader.h"
#include "x86_decoder.h"
#include "uir.h"
#include "semantic.h"
#include "forth_codegen.h"

/* ============================================================================
 * Version
 * ============================================================================ */

const char* translator_version(void) {
    static char version[32];
    snprintf(version, sizeof(version), "%d.%d.%d",
             TRANSLATOR_VERSION_MAJOR,
             TRANSLATOR_VERSION_MINOR,
             TRANSLATOR_VERSION_PATCH);
    return version;
}

/* ============================================================================
 * Option Parsing
 * ============================================================================ */

static void print_usage(const char* program) {
    fprintf(stderr, "Universal Binary Translator v%s\n", translator_version());
    fprintf(stderr, "Copyright (c) 2026 Jolly Genius Inc.\n\n");
    fprintf(stderr, "Usage: %s <binary> [options]\n\n", program);
    fprintf(stderr, "Options:\n");
    fprintf(stderr, "  -t TARGET   Output target: disasm, uir, forth, c, x64, arm64, riscv64\n");
    fprintf(stderr, "  -o FILE     Output file (default: stdout)\n");
    fprintf(stderr, "  -f FUNC     Extract specific function\n");
    fprintf(stderr, "  -n NAME     Vocabulary name for Forth output (default: derived from filename)\n");
    fprintf(stderr, "  -b ADDR     Base address for raw binaries (hex)\n");
    fprintf(stderr, "  -a          Print binary analysis\n");
    fprintf(stderr, "  -S          Enable semantic analysis\n");
    fprintf(stderr, "  -s          Print sections\n");
    fprintf(stderr, "  -i          Print imports\n");
    fprintf(stderr, "  -e          Print exports\n");
    fprintf(stderr, "  -y          Print symbols\n");
    fprintf(stderr, "  -v          Verbose output\n");
    fprintf(stderr, "  -O LEVEL    Optimization level (0-3)\n");
    fprintf(stderr, "  -h          Show this help\n");
}

static target_t parse_target(const char* str) {
    if (strcmp(str, "disasm") == 0) return TARGET_DISASM;
    if (strcmp(str, "uir") == 0) return TARGET_UIR;
    if (strcmp(str, "forth") == 0) return TARGET_FORTH;
    if (strcmp(str, "c") == 0) return TARGET_C;
    if (strcmp(str, "x64") == 0) return TARGET_X64;
    if (strcmp(str, "arm64") == 0) return TARGET_ARM64;
    if (strcmp(str, "riscv64") == 0) return TARGET_RISCV64;
    return TARGET_DISASM;  /* Default */
}

/* ============================================================================
 * Vocabulary name derivation
 * ============================================================================ */

/* Derive a vocabulary name from a filename.
 * "serial.sys" -> "SERIAL", "my-driver.sys" -> "MY-DRIVER"
 * Caller must free the returned string. */
static char* derive_vocab_name(const char* filename) {
    if (!filename) return strdup("EXTRACTED");

    /* Find basename: skip directory separators */
    const char* base = filename;
    for (const char* p = filename; *p; p++) {
        if (*p == '/' || *p == '\\') base = p + 1;
    }

    /* Strip extension */
    size_t len = strlen(base);
    const char* dot = strrchr(base, '.');
    if (dot && dot > base) len = (size_t)(dot - base);

    char* name = malloc(len + 1);
    for (size_t i = 0; i < len; i++) {
        char c = base[i];
        if (c >= 'a' && c <= 'z')
            name[i] = c - 'a' + 'A';  /* uppercase */
        else if (c == '_')
            name[i] = '-';  /* Forth convention: hyphens */
        else
            name[i] = c;
    }
    name[len] = '\0';
    return name;
}

/* ============================================================================
 * x86_decoded_t to uir_x86_input_t conversion
 * ============================================================================ */

static uir_x86_input_t* convert_x86_to_uir_input(const x86_decoded_t* insts,
                                                    size_t count) {
    uir_x86_input_t* out = malloc(count * sizeof(uir_x86_input_t));
    if (!out) return NULL;

    for (size_t i = 0; i < count; i++) {
        out[i].address = insts[i].address;
        out[i].length = insts[i].length;
        out[i].instruction = (int)insts[i].instruction;
        out[i].operand_count = insts[i].operand_count;
        for (int j = 0; j < 4; j++) {
            out[i].operands[j].type  = (int)insts[i].operands[j].type;
            out[i].operands[j].size  = insts[i].operands[j].size;
            out[i].operands[j].reg   = insts[i].operands[j].reg;
            out[i].operands[j].base  = insts[i].operands[j].base;
            out[i].operands[j].index = insts[i].operands[j].index;
            out[i].operands[j].scale = insts[i].operands[j].scale;
            out[i].operands[j].disp  = insts[i].operands[j].disp;
            out[i].operands[j].imm   = insts[i].operands[j].imm;
        }
        out[i].prefixes = insts[i].prefixes;
        out[i].cc = (int)insts[i].cc;
    }
    return out;
}

/* ============================================================================
 * Forth codegen from semantic + UIR results
 * ============================================================================ */

static char* generate_forth_output(const sem_result_t* sem,
                                    const uir_function_t** uir_funcs,
                                    size_t uir_func_count,
                                    const pe_context_t* pe,
                                    const translate_options_t* opts) {
    /* Determine vocabulary name */
    char* derived_name = NULL;
    const char* vname;
    if (opts->vocab_name) {
        vname = opts->vocab_name;
    } else {
        derived_name = derive_vocab_name(opts->input_filename);
        vname = derived_name;
    }

    forth_codegen_opts_t cg_opts;
    forth_codegen_opts_init(&cg_opts);
    cg_opts.vocab_name = vname;
    cg_opts.category = "driver";
    cg_opts.source_type = "extracted";
    cg_opts.source_binary = opts->input_filename;
    cg_opts.confidence = sem->hw_function_count > 0 ? "medium" : "low";

    /* Build REQUIRES dependency from classified imports */
    const char* hw_words_buf[64];
    size_t hw_word_count = 0;
    for (size_t i = 0; i < sem->import_count && hw_word_count < 63; i++) {
        if (sem_is_hardware(sem->imports[i].category) && sem->imports[i].forth_equiv)
            hw_words_buf[hw_word_count++] = sem->imports[i].forth_equiv;
    }
    hw_words_buf[hw_word_count] = NULL;

    /* Check if any UIR function has port I/O */
    bool any_port_io = false;
    for (size_t f = 0; f < uir_func_count; f++) {
        if (uir_funcs[f]->has_port_io) { any_port_io = true; break; }
    }

    /* If the code has direct port I/O, add C@-PORT/C!-PORT as requirements */
    static const char* port_words[] = {"C@-PORT", "C!-PORT", NULL};
    forth_dependency_t deps[2] = {{NULL, NULL}, {NULL, NULL}};
    if (any_port_io || hw_word_count > 0) {
        deps[0].vocab_name = "HARDWARE";
        deps[0].words_used = any_port_io ? port_words : hw_words_buf;
        cg_opts.requires = deps;
    }

    /* Collect unique port offsets across ALL UIR functions */
    uint16_t port_offsets[256];
    size_t port_offset_count = 0;

    for (size_t f = 0; f < uir_func_count; f++) {
        const uir_function_t* uf = uir_funcs[f];
        for (size_t i = 0; i < uf->ports_read_count && port_offset_count < 256; i++) {
            bool found = false;
            for (size_t j = 0; j < port_offset_count; j++)
                if (port_offsets[j] == uf->ports_read[i]) { found = true; break; }
            if (!found) port_offsets[port_offset_count++] = uf->ports_read[i];
        }
        for (size_t i = 0; i < uf->ports_written_count && port_offset_count < 256; i++) {
            bool found = false;
            for (size_t j = 0; j < port_offset_count; j++)
                if (port_offsets[j] == uf->ports_written[i]) { found = true; break; }
            if (!found) port_offsets[port_offset_count++] = uf->ports_written[i];
        }
    }

    /* Port range description */
    char* ports_desc = NULL;
    if (port_offset_count > 0) {
        uint16_t min_port = 0xFFFF, max_port = 0;
        for (size_t i = 0; i < port_offset_count; i++) {
            if (port_offsets[i] < min_port) min_port = port_offsets[i];
            if (port_offsets[i] > max_port) max_port = port_offsets[i];
        }
        ports_desc = forth_port_range_desc(min_port, max_port - min_port + 1);
        cg_opts.ports_desc = ports_desc;
    }

    /* Build function entries from semantic results, with port ops from matched UIR */
    forth_gen_function_t* gen_funcs = NULL;
    size_t gen_func_count = 0;

    for (size_t fi = 0; fi < sem->function_count; fi++) {
        if (!sem->functions[fi].is_hardware) continue;
        gen_func_count++;
    }

    if (gen_func_count > 0) {
        gen_funcs = calloc(gen_func_count, sizeof(forth_gen_function_t));
        size_t gi = 0;
        for (size_t fi = 0; fi < sem->function_count; fi++) {
            if (!sem->functions[fi].is_hardware) continue;
            gen_funcs[gi].name = sem->functions[fi].name
                                     ? sem->functions[fi].name : "HW-FUNC";
            gen_funcs[gi].address = sem->functions[fi].address;

            /* Find the matching UIR function by address */
            const uir_function_t* matched_uir = NULL;
            for (size_t u = 0; u < uir_func_count; u++) {
                if (uir_funcs[u]->entry_address == sem->functions[fi].address) {
                    matched_uir = uir_funcs[u];
                    break;
                }
            }

            /* Build port ops from matched UIR data */
            if (matched_uir) {
                size_t total_ports = matched_uir->ports_read_count
                                         + matched_uir->ports_written_count;
                if (total_ports > 0) {
                    gen_funcs[gi].port_ops = calloc(total_ports, sizeof(forth_port_op_t));
                    size_t idx = 0;
                    for (size_t p = 0; p < matched_uir->ports_read_count; p++) {
                        gen_funcs[gi].port_ops[idx].port_offset = matched_uir->ports_read[p];
                        gen_funcs[gi].port_ops[idx].size = 1;
                        gen_funcs[gi].port_ops[idx].is_write = false;
                        idx++;
                    }
                    for (size_t p = 0; p < matched_uir->ports_written_count; p++) {
                        gen_funcs[gi].port_ops[idx].port_offset = matched_uir->ports_written[p];
                        gen_funcs[gi].port_ops[idx].size = 1;
                        gen_funcs[gi].port_ops[idx].is_write = true;
                        idx++;
                    }
                    gen_funcs[gi].port_op_count = total_ports;
                }
            }
            /* Copy HAL call data from semantic analysis */
            const sem_function_t* sf = &sem->functions[fi];
            if (sf->hal_call_count > 0) {
                gen_funcs[gi].hal_calls = calloc(sf->hal_call_count,
                                                  sizeof(forth_hal_call_t));
                gen_funcs[gi].hal_call_count = sf->hal_call_count;
                for (size_t h = 0; h < sf->hal_call_count; h++) {
                    gen_funcs[gi].hal_calls[h].forth_word = sf->hal_calls[h].forth_equiv;
                    gen_funcs[gi].hal_calls[h].arg_count = sf->hal_calls[h].arg_count;
                    gen_funcs[gi].hal_calls[h].ret_count = sf->hal_calls[h].ret_count;
                }
            }
            gi++;
        }
    }

    forth_codegen_input_t cg_input;
    memset(&cg_input, 0, sizeof(cg_input));
    cg_input.opts = cg_opts;
    cg_input.functions = gen_funcs;
    cg_input.function_count = gen_func_count;
    cg_input.port_offsets = port_offsets;
    cg_input.port_offset_count = port_offset_count;

    char* output = forth_generate(&cg_input);

    /* Cleanup local allocations */
    for (size_t i = 0; i < gen_func_count; i++) {
        free(gen_funcs[i].port_ops);
        free(gen_funcs[i].hal_calls);
    }
    free(gen_funcs);
    free(ports_desc);
    free(derived_name);
    (void)pe;

    return output;
}

/* ============================================================================
 * .NET notice stub
 * ============================================================================ */

static translate_result_t translate_dotnet_notice(const char* filename) {
    translate_result_t result = {0};
    char buf[256];
    snprintf(buf, sizeof(buf),
             "\\ .NET assembly detected: %s\n"
             "\\ IL translation not yet supported.\n"
             "\\ Use native decompiler (ILSpy, dnSpy) for analysis.\n",
             filename ? filename : "(unknown)");
    result.success = true;
    result.output = strdup(buf);
    result.output_size = strlen(result.output);
    return result;
}

/* ============================================================================
 * DOS .com translation path
 * ============================================================================ */

static translate_result_t translate_com(const com_context_t* com,
                                         const translate_options_t* opts) {
    translate_result_t result = {0};

    /* ---- Stage 2: Decode x86 instructions ---- */
    x86_decoder_t dec;
    x86_decoder_init(&dec, X86_MODE_32, com->code, com->code_size,
                     com->load_addr);
    size_t inst_count = 0;
    x86_decoded_t* insts = x86_decode_range(&dec, &inst_count);
    if (!insts || inst_count == 0) {
        result.success = false;
        result.error_message = strdup("No instructions decoded from COM file");
        return result;
    }

    /* TARGET_DISASM: print decoded instructions and return */
    if (opts->target == TARGET_DISASM) {
        char* buf = NULL;
        size_t buf_size = 0;
        FILE* mem = open_memstream(&buf, &buf_size);
        for (size_t i = 0; i < inst_count; i++)
            x86_print_decoded(&insts[i], mem);
        fclose(mem);
        free(insts);
        result.success = true;
        result.output = buf;
        result.output_size = buf_size;
        return result;
    }

    /* ---- Stage 3: Treat entire COM as one function ---- */
    uint64_t text_base = com->load_addr;
    uint64_t text_end = text_base + com->code_size;

    /* ---- Stage 4: Lift to UIR ---- */
    uir_x86_input_t* uir_input = convert_x86_to_uir_input(insts, inst_count);
    free(insts);

    if (!uir_input) {
        result.success = false;
        result.error_message = strdup("Out of memory during UIR conversion");
        return result;
    }

    uir_function_t* uf = uir_lift_function(uir_input, inst_count, text_base);
    free(uir_input);

    if (!uf) {
        result.success = false;
        result.error_message = strdup("UIR lift failed for COM file");
        return result;
    }

    uir_function_t* uir_funcs[1] = {uf};

    /* TARGET_UIR: print UIR and return */
    if (opts->target == TARGET_UIR) {
        char* buf = NULL;
        size_t buf_size = 0;
        FILE* mem = open_memstream(&buf, &buf_size);
        uir_print_function(uf, mem);
        fclose(mem);
        uir_free_function(uf);
        result.success = true;
        result.output = buf;
        result.output_size = buf_size;
        return result;
    }

    /* ---- Stage 5: Semantic analysis (no imports for COM) ---- */
    sem_result_t sem;
    memset(&sem, 0, sizeof(sem));

    sem_uir_input_t sem_func_input;
    memset(&sem_func_input, 0, sizeof(sem_func_input));
    sem_func_input.func = uf;
    sem_func_input.entry_address = uf->entry_address;
    sem_func_input.has_port_io = uf->has_port_io;
    sem_func_input.ports_read = uf->ports_read;
    sem_func_input.ports_read_count = uf->ports_read_count;
    sem_func_input.ports_written = uf->ports_written;
    sem_func_input.ports_written_count = uf->ports_written_count;

    sem_analyze_functions(&sem_func_input, 1, text_base, &sem);

    /* ---- Stage 6: Generate Forth output ---- */
    if (opts->target == TARGET_FORTH) {
        char* forth_output = generate_forth_output(&sem,
            (const uir_function_t**)uir_funcs, 1, NULL, opts);

        sem_cleanup(&sem);
        uir_free_function(uf);

        if (!forth_output) {
            result.success = false;
            result.error_message = strdup("Forth code generation failed");
            return result;
        }

        result.success = true;
        result.output = forth_output;
        result.output_size = strlen(forth_output);
        return result;
    }

    /* Unsupported target */
    sem_cleanup(&sem);
    uir_free_function(uf);
    result.success = false;
    result.error_message = strdup("Unsupported output target for COM files");
    return result;

    (void)text_end;
}

/* ============================================================================
 * PE translation path (extracted from translate_buffer)
 * ============================================================================ */

static translate_result_t translate_pe(const uint8_t* data, size_t size,
                                        const translate_options_t* opts);

/* ============================================================================
 * API Implementation
 * ============================================================================ */

void translate_options_init(translate_options_t* opts) {
    opts->target = TARGET_DISASM;
    opts->source_arch = ARCH_UNKNOWN;
    opts->base_address = 0;
    opts->optimize_level = 1;
    opts->semantic_analysis = false;
    opts->verbose = false;
    opts->forth83_division = true;  /* Default to Forth-83 semantics */
    opts->function_name = NULL;
    opts->vocab_name = NULL;
    opts->input_filename = NULL;
}

translate_result_t translate_file(const char* filename,
                                   const translate_options_t* opts) {
    translate_result_t result = {0};

    FILE* f = fopen(filename, "rb");
    if (!f) {
        result.success = false;
        result.error_message = strdup("Failed to open file");
        return result;
    }

    fseek(f, 0, SEEK_END);
    size_t size = (size_t)ftell(f);
    fseek(f, 0, SEEK_SET);

    uint8_t* data = malloc(size);
    if (!data) {
        fclose(f);
        result.success = false;
        result.error_message = strdup("Out of memory");
        return result;
    }

    if (fread(data, 1, size, f) != size) {
        free(data);
        fclose(f);
        result.success = false;
        result.error_message = strdup("Failed to read file");
        return result;
    }
    fclose(f);

    /* Set input filename if not already set */
    translate_options_t local_opts = *opts;
    if (!local_opts.input_filename)
        local_opts.input_filename = filename;

    result = translate_buffer(data, size, &local_opts);

    free(data);
    return result;
}

translate_result_t translate_buffer(const uint8_t* data, size_t size,
                                     const translate_options_t* opts) {
    translate_result_t result = {0};

    /* ---- Stage 0: Detect format ---- */
    format_info_t fmt = detect_format(data, size, opts->input_filename);

    switch (fmt.format) {
        case BINFMT_DOS_COM: {
            com_context_t com;
            if (com_load(&com, data, size) != 0) {
                result.success = false;
                result.error_message = strdup("Failed to load .com file");
                return result;
            }
            return translate_com(&com, opts);
        }

        case BINFMT_DOTNET:
            return translate_dotnet_notice(opts->input_filename);

        case BINFMT_PE_DRIVER:
        case BINFMT_PE_DLL:
        case BINFMT_PE_EXE:
            return translate_pe(data, size, opts);

        case BINFMT_ELF:
            result.success = false;
            result.error_message = strdup("ELF format not yet supported");
            return result;

        default:
            result.success = false;
            result.error_message = strdup("Unknown binary format");
            return result;
    }
}

/* ============================================================================
 * PE translation path (original pipeline)
 * ============================================================================ */

static translate_result_t translate_pe(const uint8_t* data, size_t size,
                                        const translate_options_t* opts) {
    translate_result_t result = {0};

    /* ---- Stage 1: Load PE ---- */
    pe_context_t pe;
    memset(&pe, 0, sizeof(pe));
    if (pe_load(&pe, data, size) != 0) {
        result.success = false;
        result.error_message = strdup("Not a valid PE file");
        return result;
    }

    if (!pe.text_data || pe.text_size == 0) {
        pe_cleanup(&pe);
        result.success = false;
        result.error_message = strdup("No .text section found in PE");
        return result;
    }

    /* ---- Stage 2: Decode x86 instructions ---- */
    x86_decoder_t dec;
    x86_decoder_init(&dec, X86_MODE_32, pe.text_data, pe.text_size,
                     pe.image_base + pe.text_rva);
    size_t inst_count = 0;
    x86_decoded_t* insts = x86_decode_range(&dec, &inst_count);
    if (!insts || inst_count == 0) {
        pe_cleanup(&pe);
        result.success = false;
        result.error_message = strdup("No instructions decoded from .text section");
        return result;
    }

    /* TARGET_DISASM: print decoded instructions and return */
    if (opts->target == TARGET_DISASM) {
        char* buf = NULL;
        size_t buf_size = 0;
        FILE* mem = open_memstream(&buf, &buf_size);
        for (size_t i = 0; i < inst_count; i++)
            x86_print_decoded(&insts[i], mem);
        fclose(mem);
        free(insts);
        pe_cleanup(&pe);
        result.success = true;
        result.output = buf;
        result.output_size = buf_size;
        return result;
    }

    /* ---- Stage 3: Discover function boundaries ---- */
    uint64_t text_base = pe.image_base + pe.text_rva;
    uint64_t text_end = text_base + pe.text_size;

    /* Build PE export info for function discovery */
    sem_pe_export_t* pe_exports = NULL;
    if (pe.export_count > 0) {
        pe_exports = malloc(pe.export_count * sizeof(sem_pe_export_t));
        for (size_t i = 0; i < pe.export_count; i++) {
            pe_exports[i].address = pe.image_base + pe.exports[i].rva;
            pe_exports[i].name = pe.exports[i].name;
        }
    }

    sem_function_map_t func_map;
    sem_discover_functions(insts, inst_count, text_base, text_end,
                          pe_exports, pe.export_count, &func_map);
    free(pe_exports);

    /* If no functions discovered, treat entire .text as one function */
    if (func_map.count == 0) {
        func_map.entries = calloc(1, sizeof(sem_func_boundary_t));
        func_map.entries[0].start_address = text_base;
        func_map.entries[0].inst_start = 0;
        func_map.entries[0].inst_count = inst_count;
        func_map.count = 1;
    }

    /* ---- Stage 4: Lift each function to UIR ---- */
    uir_x86_input_t* uir_input = convert_x86_to_uir_input(insts, inst_count);
    free(insts);

    if (!uir_input) {
        sem_function_map_free(&func_map);
        pe_cleanup(&pe);
        result.success = false;
        result.error_message = strdup("Out of memory during UIR conversion");
        return result;
    }

    uir_function_t** uir_funcs = calloc(func_map.count, sizeof(uir_function_t*));
    size_t uir_func_count = 0;

    for (size_t f = 0; f < func_map.count; f++) {
        sem_func_boundary_t* fb = &func_map.entries[f];
        if (fb->inst_count == 0) continue;

        uir_function_t* uf = uir_lift_function(
            uir_input + fb->inst_start,
            fb->inst_count,
            fb->start_address);

        if (uf) {
            uir_funcs[uir_func_count++] = uf;
        }
    }
    free(uir_input);

    if (uir_func_count == 0) {
        free(uir_funcs);
        sem_function_map_free(&func_map);
        pe_cleanup(&pe);
        result.success = false;
        result.error_message = strdup("UIR lift failed for all functions");
        return result;
    }

    /* TARGET_UIR: print all UIR functions and return */
    if (opts->target == TARGET_UIR) {
        char* buf = NULL;
        size_t buf_size = 0;
        FILE* mem = open_memstream(&buf, &buf_size);
        for (size_t f = 0; f < uir_func_count; f++) {
            if (f > 0) fprintf(mem, "\n");
            uir_print_function(uir_funcs[f], mem);
        }
        fclose(mem);
        for (size_t f = 0; f < uir_func_count; f++)
            uir_free_function(uir_funcs[f]);
        free(uir_funcs);
        sem_function_map_free(&func_map);
        pe_cleanup(&pe);
        result.success = true;
        result.output = buf;
        result.output_size = buf_size;
        return result;
    }

    /* ---- Stage 5: Semantic analysis ---- */
    sem_pe_import_t* sem_imports = NULL;
    if (pe.import_count > 0) {
        sem_imports = malloc(pe.import_count * sizeof(sem_pe_import_t));
        for (size_t i = 0; i < pe.import_count; i++) {
            sem_imports[i].dll_name = pe.imports[i].dll_name;
            sem_imports[i].func_name = pe.imports[i].func_name;
            sem_imports[i].iat_rva = pe.imports[i].iat_rva;
        }
    }

    sem_result_t sem;
    memset(&sem, 0, sizeof(sem));
    if (pe.import_count > 0)
        sem_classify_imports(sem_imports, pe.import_count, &sem);
    free(sem_imports);

    /* Analyze each UIR function */
    sem_uir_input_t* sem_func_inputs = calloc(uir_func_count, sizeof(sem_uir_input_t));
    for (size_t f = 0; f < uir_func_count; f++) {
        sem_func_inputs[f].func = uir_funcs[f];
        sem_func_inputs[f].entry_address = uir_funcs[f]->entry_address;
        sem_func_inputs[f].has_port_io = uir_funcs[f]->has_port_io;
        sem_func_inputs[f].ports_read = uir_funcs[f]->ports_read;
        sem_func_inputs[f].ports_read_count = uir_funcs[f]->ports_read_count;
        sem_func_inputs[f].ports_written = uir_funcs[f]->ports_written;
        sem_func_inputs[f].ports_written_count = uir_funcs[f]->ports_written_count;

        /* Try to find export name for this function */
        for (size_t b = 0; b < func_map.count; b++) {
            if (func_map.entries[b].start_address == uir_funcs[f]->entry_address) {
                sem_func_inputs[f].name = func_map.entries[b].name;
                break;
            }
        }
    }
    sem_analyze_functions(sem_func_inputs, uir_func_count, pe.image_base, &sem);
    free(sem_func_inputs);

    /* ---- Stage 6: Generate output ---- */
    if (opts->target == TARGET_FORTH) {
        char* forth_output = generate_forth_output(&sem,
            (const uir_function_t**)uir_funcs, uir_func_count, &pe, opts);

        sem_cleanup(&sem);
        for (size_t f = 0; f < uir_func_count; f++)
            uir_free_function(uir_funcs[f]);
        free(uir_funcs);
        sem_function_map_free(&func_map);
        pe_cleanup(&pe);

        if (!forth_output) {
            result.success = false;
            result.error_message = strdup("Forth code generation failed");
            return result;
        }

        result.success = true;
        result.output = forth_output;
        result.output_size = strlen(forth_output);
        return result;
    }

    /* Unsupported target */
    sem_cleanup(&sem);
    for (size_t f = 0; f < uir_func_count; f++)
        uir_free_function(uir_funcs[f]);
    free(uir_funcs);
    sem_function_map_free(&func_map);
    pe_cleanup(&pe);
    result.success = false;
    result.error_message = strdup("Unsupported output target");
    return result;
}

void translate_result_free(translate_result_t* result) {
    if (result->output) {
        free(result->output);
        result->output = NULL;
    }
    if (result->error_message) {
        free(result->error_message);
        result->error_message = NULL;
    }
}

/* ============================================================================
 * Main
 * ============================================================================ */

#ifndef TRANSLATOR_NO_MAIN
int main(int argc, char** argv) {
    if (argc < 2) {
        print_usage(argv[0]);
        return 1;
    }

    /* Parse options */
    translate_options_t opts;
    translate_options_init(&opts);

    const char* input_file = NULL;
    const char* output_file = NULL;
    bool print_analysis = false;
    bool print_sections = false;
    bool print_imports = false;
    bool print_exports = false;
    bool print_symbols = false;

    for (int i = 1; i < argc; i++) {
        if (argv[i][0] == '-') {
            switch (argv[i][1]) {
                case 't':
                    if (i + 1 < argc)
                        opts.target = parse_target(argv[++i]);
                    break;
                case 'o':
                    if (i + 1 < argc)
                        output_file = argv[++i];
                    break;
                case 'f':
                    if (i + 1 < argc)
                        opts.function_name = argv[++i];
                    break;
                case 'n':
                    if (i + 1 < argc)
                        opts.vocab_name = argv[++i];
                    break;
                case 'b':
                    if (i + 1 < argc)
                        opts.base_address = strtoull(argv[++i], NULL, 16);
                    break;
                case 'a': print_analysis = true; break;
                case 'S': opts.semantic_analysis = true; break;
                case 's': print_sections = true; break;
                case 'i': print_imports = true; break;
                case 'e': print_exports = true; break;
                case 'y': print_symbols = true; break;
                case 'v': opts.verbose = true; break;
                case 'O':
                    if (i + 1 < argc)
                        opts.optimize_level = atoi(argv[++i]);
                    break;
                case 'h':
                    print_usage(argv[0]);
                    return 0;
                default:
                    fprintf(stderr, "Unknown option: %s\n", argv[i]);
                    return 1;
            }
        } else {
            input_file = argv[i];
        }
    }

    if (!input_file) {
        fprintf(stderr, "Error: No input file specified\n");
        print_usage(argv[0]);
        return 1;
    }

    /* Handle PE info printing flags (-a, -s, -i, -e) */
    if (print_analysis || print_sections || print_imports || print_exports) {
        FILE* f = fopen(input_file, "rb");
        if (f) {
            fseek(f, 0, SEEK_END);
            size_t fsize = (size_t)ftell(f);
            fseek(f, 0, SEEK_SET);
            uint8_t* fdata = malloc(fsize);
            if (fdata && fread(fdata, 1, fsize, f) == fsize) {
                pe_context_t pe;
                memset(&pe, 0, sizeof(pe));
                if (pe_load(&pe, fdata, fsize) == 0) {
                    if (print_analysis || print_sections || print_imports
                        || print_exports) {
                        pe_print_info(&pe, stderr);
                    }
                    pe_cleanup(&pe);
                } else {
                    fprintf(stderr, "Warning: Not a PE file, info flags ignored\n");
                }
            }
            free(fdata);
            fclose(f);
        }
    }
    (void)print_symbols;  /* symbols not yet implemented */

    /* Translate */
    if (opts.verbose)
        fprintf(stderr, "Translating: %s\n", input_file);

    translate_result_t result = translate_file(input_file, &opts);

    if (!result.success) {
        fprintf(stderr, "Error: %s\n",
                result.error_message ? result.error_message : "Unknown error");
        translate_result_free(&result);
        return 1;
    }

    /* Output */
    FILE* out = stdout;
    if (output_file) {
        out = fopen(output_file, "w");
        if (!out) {
            fprintf(stderr, "Error: Cannot open output file: %s\n", output_file);
            translate_result_free(&result);
            return 1;
        }
    }

    fwrite(result.output, 1, result.output_size, out);

    if (output_file)
        fclose(out);

    translate_result_free(&result);
    return 0;
}
#endif /* TRANSLATOR_NO_MAIN */
