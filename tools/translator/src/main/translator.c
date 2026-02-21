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
                                    const uir_function_t* uir_func,
                                    const pe_context_t* pe) {
    forth_codegen_opts_t cg_opts;
    forth_codegen_opts_init(&cg_opts);
    cg_opts.vocab_name = "EXTRACTED";
    cg_opts.category = "driver";
    cg_opts.source_type = "extracted";
    cg_opts.confidence = sem->hw_function_count > 0 ? "medium" : "low";

    /* Build REQUIRES dependency from classified imports */
    const char* hw_words_buf[64];
    size_t hw_word_count = 0;
    for (size_t i = 0; i < sem->import_count && hw_word_count < 63; i++) {
        if (sem_is_hardware(sem->imports[i].category) && sem->imports[i].forth_equiv)
            hw_words_buf[hw_word_count++] = sem->imports[i].forth_equiv;
    }
    hw_words_buf[hw_word_count] = NULL;

    /* If the code has direct port I/O, add C@-PORT/C!-PORT as requirements */
    static const char* port_words[] = {"C@-PORT", "C!-PORT", NULL};
    forth_dependency_t deps[2] = {{NULL, NULL}, {NULL, NULL}};
    if (uir_func->has_port_io || hw_word_count > 0) {
        deps[0].vocab_name = "HARDWARE";
        deps[0].words_used = uir_func->has_port_io ? port_words : hw_words_buf;
        cg_opts.requires = deps;
    }

    /* Port range description */
    char* ports_desc = NULL;
    if (uir_func->ports_read_count > 0 || uir_func->ports_written_count > 0) {
        uint16_t min_port = 0xFFFF, max_port = 0;
        for (size_t i = 0; i < uir_func->ports_read_count; i++) {
            if (uir_func->ports_read[i] < min_port) min_port = uir_func->ports_read[i];
            if (uir_func->ports_read[i] > max_port) max_port = uir_func->ports_read[i];
        }
        for (size_t i = 0; i < uir_func->ports_written_count; i++) {
            if (uir_func->ports_written[i] < min_port) min_port = uir_func->ports_written[i];
            if (uir_func->ports_written[i] > max_port) max_port = uir_func->ports_written[i];
        }
        ports_desc = forth_port_range_desc(min_port, max_port - min_port + 1);
        cg_opts.ports_desc = ports_desc;
    }

    /* Build function entries from semantic results */
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

            /* Build port ops from UIR data */
            size_t total_ports = uir_func->ports_read_count
                                     + uir_func->ports_written_count;
            if (total_ports > 0) {
                gen_funcs[gi].port_ops = calloc(total_ports, sizeof(forth_port_op_t));
                size_t idx = 0;
                for (size_t p = 0; p < uir_func->ports_read_count; p++) {
                    gen_funcs[gi].port_ops[idx].port_offset = uir_func->ports_read[p];
                    gen_funcs[gi].port_ops[idx].size = 1;
                    gen_funcs[gi].port_ops[idx].is_write = false;
                    idx++;
                }
                for (size_t p = 0; p < uir_func->ports_written_count; p++) {
                    gen_funcs[gi].port_ops[idx].port_offset = uir_func->ports_written[p];
                    gen_funcs[gi].port_ops[idx].size = 1;
                    gen_funcs[gi].port_ops[idx].is_write = true;
                    idx++;
                }
                gen_funcs[gi].port_op_count = total_ports;
            }
            gi++;
        }
    }

    /* Collect unique port offsets */
    uint16_t port_offsets[256];
    size_t port_offset_count = 0;
    for (size_t i = 0; i < uir_func->ports_read_count && port_offset_count < 256; i++) {
        bool found = false;
        for (size_t j = 0; j < port_offset_count; j++)
            if (port_offsets[j] == uir_func->ports_read[i]) { found = true; break; }
        if (!found) port_offsets[port_offset_count++] = uir_func->ports_read[i];
    }
    for (size_t i = 0; i < uir_func->ports_written_count && port_offset_count < 256; i++) {
        bool found = false;
        for (size_t j = 0; j < port_offset_count; j++)
            if (port_offsets[j] == uir_func->ports_written[i]) { found = true; break; }
        if (!found) port_offsets[port_offset_count++] = uir_func->ports_written[i];
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
    for (size_t i = 0; i < gen_func_count; i++)
        free(gen_funcs[i].port_ops);
    free(gen_funcs);
    free(ports_desc);
    (void)pe;

    return output;
}

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

    result = translate_buffer(data, size, opts);

    free(data);
    return result;
}

translate_result_t translate_buffer(const uint8_t* data, size_t size,
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

    /* ---- Stage 3: Lift to UIR ---- */
    uir_x86_input_t* uir_input = convert_x86_to_uir_input(insts, inst_count);
    free(insts);

    if (!uir_input) {
        pe_cleanup(&pe);
        result.success = false;
        result.error_message = strdup("Out of memory during UIR conversion");
        return result;
    }

    uint64_t entry_addr = pe.image_base + pe.entry_point_rva;
    uir_function_t* uir_func = uir_lift_function(uir_input, inst_count, entry_addr);
    free(uir_input);

    if (!uir_func) {
        pe_cleanup(&pe);
        result.success = false;
        result.error_message = strdup("UIR lift failed");
        return result;
    }

    /* TARGET_UIR: print UIR and return */
    if (opts->target == TARGET_UIR) {
        char* buf = NULL;
        size_t buf_size = 0;
        FILE* mem = open_memstream(&buf, &buf_size);
        uir_print_function(uir_func, mem);
        fclose(mem);
        uir_free_function(uir_func);
        pe_cleanup(&pe);
        result.success = true;
        result.output = buf;
        result.output_size = buf_size;
        return result;
    }

    /* ---- Stage 4: Semantic analysis ---- */
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

    sem_uir_input_t sem_func_input;
    memset(&sem_func_input, 0, sizeof(sem_func_input));
    sem_func_input.func = uir_func;
    sem_func_input.entry_address = uir_func->entry_address;
    sem_func_input.has_port_io = uir_func->has_port_io;
    sem_func_input.ports_read = uir_func->ports_read;
    sem_func_input.ports_read_count = uir_func->ports_read_count;
    sem_func_input.ports_written = uir_func->ports_written;
    sem_func_input.ports_written_count = uir_func->ports_written_count;

    sem_analyze_functions(&sem_func_input, 1, &sem);

    /* ---- Stage 5: Generate output ---- */
    if (opts->target == TARGET_FORTH) {
        char* forth_output = generate_forth_output(&sem, uir_func, &pe);

        sem_cleanup(&sem);
        uir_free_function(uir_func);
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
    uir_free_function(uir_func);
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
