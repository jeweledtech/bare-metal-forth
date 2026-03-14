/* ============================================================================
 * UIR Lifter — x86 to Universal Intermediate Representation
 * ============================================================================
 *
 * Translates x86 decoded instructions into platform-independent UIR basic
 * blocks. The key transformation for driver extraction: x86 IN/OUT instructions
 * become UIR_PORT_IN/UIR_PORT_OUT with the port number preserved.
 *
 * Basic block construction:
 *   1. First pass: scan instructions, collect branch targets into a set
 *   2. Second pass: create blocks, splitting at branch targets and after
 *      any jump/call/ret
 *   3. Link blocks: resolve jump targets to block indices
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "uir.h"
#include "x86_decoder.h"
#include "arm64_decoder.h"

/* ---- Block builder helpers ---- */

static void block_init(uir_block_t* block, uint64_t address) {
    memset(block, 0, sizeof(*block));
    block->address = address;
    block->fall_through = -1;
    block->branch_target = -1;
    block->capacity = 16;
    block->instructions = malloc(block->capacity * sizeof(uir_instruction_t));
}

static void block_append(uir_block_t* block, const uir_instruction_t* ins) {
    if (block->count >= block->capacity) {
        block->capacity *= 2;
        block->instructions = realloc(block->instructions,
                                       block->capacity * sizeof(uir_instruction_t));
    }
    block->instructions[block->count++] = *ins;
}

/* ---- Branch target set (sorted array for binary search) ---- */

typedef struct {
    uint64_t* addrs;
    size_t count;
    size_t cap;
} target_set_t;

static void target_set_init(target_set_t* ts) {
    ts->cap = 32;
    ts->count = 0;
    ts->addrs = malloc(ts->cap * sizeof(uint64_t));
}

static void target_set_add(target_set_t* ts, uint64_t addr) {
    /* Check for duplicate */
    for (size_t i = 0; i < ts->count; i++) {
        if (ts->addrs[i] == addr) return;
    }
    if (ts->count >= ts->cap) {
        ts->cap *= 2;
        ts->addrs = realloc(ts->addrs, ts->cap * sizeof(uint64_t));
    }
    ts->addrs[ts->count++] = addr;
}

static bool target_set_contains(const target_set_t* ts, uint64_t addr) {
    for (size_t i = 0; i < ts->count; i++) {
        if (ts->addrs[i] == addr) return true;
    }
    return false;
}

static void target_set_free(target_set_t* ts) {
    free(ts->addrs);
}

/* ---- Port tracking ---- */

static void add_port(uint16_t** ports, size_t* count, size_t* cap, uint16_t port) {
    /* Check duplicate */
    for (size_t i = 0; i < *count; i++) {
        if ((*ports)[i] == port) return;
    }
    if (*count >= *cap) {
        *cap = (*cap == 0) ? 8 : *cap * 2;
        *ports = realloc(*ports, *cap * sizeof(uint16_t));
    }
    (*ports)[(*count)++] = port;
}

/* ---- x86 instruction classification ---- */

static bool is_terminator(int instruction) {
    return instruction == X86_INS_JMP ||
           instruction == X86_INS_RET;
}

/* ---- Operand conversion ---- */

static uir_operand_t convert_operand(const uir_x86_input_t* x86, int idx) {
    uir_operand_t op;
    memset(&op, 0, sizeof(op));

    if (idx >= (int)x86->operand_count) return op;

    switch (x86->operands[idx].type) {
    case X86_OP_NONE:
        op.type = UIR_OPERAND_NONE;
        break;
    case X86_OP_REG:
        op.type = UIR_OPERAND_REG;
        op.reg = x86->operands[idx].reg;
        op.size = x86->operands[idx].size;
        break;
    case X86_OP_MEM:
        op.type = UIR_OPERAND_MEM;
        op.reg = x86->operands[idx].base;
        op.index = x86->operands[idx].index;
        op.scale = x86->operands[idx].scale;
        op.disp = x86->operands[idx].disp;
        op.size = x86->operands[idx].size;
        break;
    case X86_OP_IMM:
        op.type = UIR_OPERAND_IMM;
        op.imm = x86->operands[idx].imm;
        op.size = x86->operands[idx].size;
        break;
    case X86_OP_REL:
        op.type = UIR_OPERAND_ADDR;
        op.imm = x86->operands[idx].imm;
        break;
    }
    return op;
}

/* ---- Lift one x86 instruction to UIR ---- */

static void lift_one(const uir_x86_input_t* x86, uir_instruction_t* uir,
                     uir_function_t* func) {
    memset(uir, 0, sizeof(*uir));
    uir->original_address = x86->address;

    switch (x86->instruction) {

    /* ---- Port I/O: the critical path ---- */
    case X86_INS_IN:
        uir->opcode = UIR_PORT_IN;
        uir->dest = convert_operand(x86, 0);   /* destination register (AL/EAX) */
        uir->src1 = convert_operand(x86, 1);   /* port: imm or DX register */
        uir->size = x86->operands[0].size;
        func->has_port_io = true;
        if (x86->operands[1].type == X86_OP_REG) {
            func->uses_dx_port = true;
        }
        break;

    case X86_INS_OUT:
        uir->opcode = UIR_PORT_OUT;
        uir->dest = convert_operand(x86, 0);   /* port: imm or DX register */
        uir->src1 = convert_operand(x86, 1);   /* source register (AL/EAX) */
        uir->size = x86->operands[1].size;
        func->has_port_io = true;
        if (x86->operands[0].type == X86_OP_REG) {
            func->uses_dx_port = true;
        }
        break;

    /* ---- Data movement ---- */
    case X86_INS_MOV:
        /* Distinguish LOAD, STORE, and MOV based on operand types */
        if (x86->operands[0].type == X86_OP_REG &&
            x86->operands[1].type == X86_OP_MEM) {
            /* MOV reg, [mem] → LOAD */
            uir->opcode = UIR_LOAD;
            uir->dest = convert_operand(x86, 0);
            uir->src1 = convert_operand(x86, 1);
            uir->size = x86->operands[0].size;
        } else if (x86->operands[0].type == X86_OP_MEM) {
            /* MOV [mem], reg/imm → STORE */
            uir->opcode = UIR_STORE;
            uir->dest = convert_operand(x86, 0);
            uir->src1 = convert_operand(x86, 1);
            uir->size = x86->operands[0].size;
        } else {
            /* MOV reg, reg or MOV reg, imm → MOV */
            uir->opcode = UIR_MOV;
            uir->dest = convert_operand(x86, 0);
            uir->src1 = convert_operand(x86, 1);
            uir->size = x86->operands[0].size;
        }
        break;

    case X86_INS_MOVZX:
        uir->opcode = UIR_MOVZX;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_MOVSX:
        uir->opcode = UIR_MOVSX;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_LEA:
        uir->opcode = UIR_LEA;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_PUSH:
        uir->opcode = UIR_PUSH;
        uir->src1 = convert_operand(x86, 0);
        uir->size = 4;
        break;

    case X86_INS_POP:
        uir->opcode = UIR_POP;
        uir->dest = convert_operand(x86, 0);
        uir->size = 4;
        break;

    case X86_INS_XCHG:
        /* Treat XCHG as MOV for simplification */
        uir->opcode = UIR_MOV;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    /* ---- Arithmetic ---- */
    case X86_INS_ADD:
        uir->opcode = UIR_ADD;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_SUB:
        uir->opcode = UIR_SUB;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_MUL:
        uir->opcode = UIR_MUL;
        uir->dest = convert_operand(x86, 0);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_IMUL:
        uir->opcode = UIR_IMUL;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_DIV:
        uir->opcode = UIR_DIV;
        uir->dest = convert_operand(x86, 0);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_IDIV:
        uir->opcode = UIR_IDIV;
        uir->dest = convert_operand(x86, 0);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_NEG:
        uir->opcode = UIR_NEG;
        uir->dest = convert_operand(x86, 0);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_INC:
        uir->opcode = UIR_INC;
        uir->dest = convert_operand(x86, 0);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_DEC:
        uir->opcode = UIR_DEC;
        uir->dest = convert_operand(x86, 0);
        uir->size = x86->operands[0].size;
        break;

    /* ---- Logic ---- */
    case X86_INS_AND:
        uir->opcode = UIR_AND;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_OR:
        uir->opcode = UIR_OR;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_XOR:
        uir->opcode = UIR_XOR;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_NOT:
        uir->opcode = UIR_NOT;
        uir->dest = convert_operand(x86, 0);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_SHL:
        uir->opcode = UIR_SHL;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_SHR:
        uir->opcode = UIR_SHR;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_SAR:
        uir->opcode = UIR_SAR;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    /* ---- Comparison ---- */
    case X86_INS_CMP:
        uir->opcode = UIR_CMP;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    case X86_INS_TEST:
        uir->opcode = UIR_TEST;
        uir->dest = convert_operand(x86, 0);
        uir->src1 = convert_operand(x86, 1);
        uir->size = x86->operands[0].size;
        break;

    /* ---- Control flow ---- */
    case X86_INS_JMP:
        uir->opcode = UIR_JMP;
        uir->dest = convert_operand(x86, 0);
        break;

    case X86_INS_JCC:
        uir->opcode = UIR_JCC;
        uir->cc = x86->cc;
        uir->dest = convert_operand(x86, 0);
        break;

    case X86_INS_CALL:
        uir->opcode = UIR_CALL;
        uir->dest = convert_operand(x86, 0);
        break;

    case X86_INS_RET:
        uir->opcode = UIR_RET;
        break;

    /* ---- System ---- */
    case X86_INS_CLI:
        uir->opcode = UIR_CLI;
        break;

    case X86_INS_STI:
        uir->opcode = UIR_STI;
        break;

    case X86_INS_HLT:
        uir->opcode = UIR_HLT;
        break;

    case X86_INS_NOP:
        uir->opcode = UIR_NOP;
        break;

    /* ---- Everything else maps to NOP for now ---- */
    default:
        uir->opcode = UIR_NOP;
        break;
    }
}

/* ---- Main lifter ---- */

uir_function_t* uir_lift_function(const uir_x86_input_t* insts, size_t count,
                                   uint64_t entry_address) {
    if (!insts || count == 0) return NULL;

    uir_function_t* func = calloc(1, sizeof(uir_function_t));
    if (!func) return NULL;
    func->entry_address = entry_address;

    /* Pass 1: collect branch targets */
    target_set_t targets;
    target_set_init(&targets);
    target_set_add(&targets, entry_address);  /* entry is always a block start */

    for (size_t i = 0; i < count; i++) {
        const uir_x86_input_t* x = &insts[i];

        if (x->instruction == X86_INS_JMP || x->instruction == X86_INS_JCC ||
            x->instruction == X86_INS_LOOP) {
            /* Branch target is a new block */
            if (x->operand_count > 0 &&
                (x->operands[0].type == X86_OP_REL ||
                 x->operands[0].type == X86_OP_IMM)) {
                target_set_add(&targets, (uint64_t)x->operands[0].imm);
            }

            /* Instruction after a branch starts a new block */
            if (i + 1 < count) {
                target_set_add(&targets, insts[i + 1].address);
            }
        }

        if (x->instruction == X86_INS_RET || x->instruction == X86_INS_HLT) {
            if (i + 1 < count) {
                target_set_add(&targets, insts[i + 1].address);
            }
        }
    }

    /* Pass 2: create blocks */
    size_t block_cap = 16;
    func->blocks = malloc(block_cap * sizeof(uir_block_t));
    func->block_count = 0;

    size_t port_read_cap = 0, port_write_cap = 0;

    /* Start the first block */
    uir_block_t* current = NULL;

    for (size_t i = 0; i < count; i++) {
        const uir_x86_input_t* x = &insts[i];

        /* Start a new block if this address is a branch target or first instruction */
        bool need_new_block = (current == NULL) ||
                              target_set_contains(&targets, x->address);

        if (need_new_block) {
            /* Grow block array if needed */
            if (func->block_count >= block_cap) {
                block_cap *= 2;
                func->blocks = realloc(func->blocks, block_cap * sizeof(uir_block_t));
            }

            current = &func->blocks[func->block_count];
            block_init(current, x->address);
            if (x->address == entry_address) {
                current->is_entry = true;
            }
            func->block_count++;
        }

        /* Lift instruction */
        uir_instruction_t uir_ins;
        lift_one(x, &uir_ins, func);
        block_append(current, &uir_ins);

        /* Track ports */
        if (uir_ins.opcode == UIR_PORT_IN && uir_ins.src1.type == UIR_OPERAND_IMM) {
            add_port(&func->ports_read, &func->ports_read_count,
                     &port_read_cap, (uint16_t)uir_ins.src1.imm);
        }
        if (uir_ins.opcode == UIR_PORT_OUT && uir_ins.dest.type == UIR_OPERAND_IMM) {
            add_port(&func->ports_written, &func->ports_written_count,
                     &port_write_cap, (uint16_t)uir_ins.dest.imm);
        }
    }

    /* Pass 3: link blocks (resolve fall-through and branch targets) */
    for (size_t b = 0; b < func->block_count; b++) {
        uir_block_t* blk = &func->blocks[b];
        if (blk->count == 0) continue;

        uir_instruction_t* last = &blk->instructions[blk->count - 1];

        /* Set fall-through to next block (unless terminated by JMP/RET) */
        if (!is_terminator(insts[0].instruction)) {  /* check UIR opcode */
            if (last->opcode != UIR_JMP && last->opcode != UIR_RET) {
                if (b + 1 < func->block_count) {
                    blk->fall_through = (int)(b + 1);
                }
            }
        }

        /* For JCC, fall-through is next block, branch_target is the target */
        if (last->opcode == UIR_JCC || last->opcode == UIR_JMP) {
            uint64_t target_addr = (uint64_t)last->dest.imm;
            for (size_t t = 0; t < func->block_count; t++) {
                if (func->blocks[t].address == target_addr) {
                    blk->branch_target = (int)t;
                    break;
                }
            }
            if (last->opcode == UIR_JCC && b + 1 < func->block_count) {
                blk->fall_through = (int)(b + 1);
            }
            if (last->opcode == UIR_JMP) {
                blk->fall_through = -1;  /* unconditional jumps don't fall through */
            }
        }
    }

    target_set_free(&targets);
    return func;
}

/* ---- Cleanup ---- */

void uir_free_function(uir_function_t* func) {
    if (!func) return;
    for (size_t i = 0; i < func->block_count; i++) {
        free(func->blocks[i].instructions);
    }
    free(func->blocks);
    free(func->ports_read);
    free(func->ports_written);
    free(func->sysregs_read);
    free(func->sysregs_written);
    free(func);
}

/* ---- Name table ---- */

static const char* opcode_names[] = {
    [UIR_NOP] = "nop",
    [UIR_MOV] = "mov", [UIR_LOAD] = "load", [UIR_STORE] = "store",
    [UIR_PUSH] = "push", [UIR_POP] = "pop",
    [UIR_LEA] = "lea", [UIR_MOVZX] = "movzx", [UIR_MOVSX] = "movsx",
    [UIR_ADD] = "add", [UIR_SUB] = "sub",
    [UIR_MUL] = "mul", [UIR_IMUL] = "imul",
    [UIR_DIV] = "div", [UIR_IDIV] = "idiv",
    [UIR_NEG] = "neg", [UIR_INC] = "inc", [UIR_DEC] = "dec",
    [UIR_AND] = "and", [UIR_OR] = "or", [UIR_XOR] = "xor",
    [UIR_NOT] = "not",
    [UIR_SHL] = "shl", [UIR_SHR] = "shr", [UIR_SAR] = "sar",
    [UIR_CMP] = "cmp", [UIR_TEST] = "test",
    [UIR_JMP] = "jmp", [UIR_JCC] = "jcc",
    [UIR_CALL] = "call", [UIR_RET] = "ret",
    [UIR_PORT_IN] = "port_in", [UIR_PORT_OUT] = "port_out",
    [UIR_CLI] = "cli", [UIR_STI] = "sti", [UIR_HLT] = "hlt",
    [UIR_SYSREG_READ] = "sysreg_read", [UIR_SYSREG_WRITE] = "sysreg_write",
    [UIR_BARRIER] = "barrier",
};

const char* uir_opcode_name(uir_opcode_t op) {
    if (op >= 0 && op < UIR_OPCODE_COUNT) return opcode_names[op];
    return "???";
}

/* ---- Print ---- */

static void print_uir_operand(const uir_operand_t* op, FILE* out) {
    switch (op->type) {
    case UIR_OPERAND_NONE:
        break;
    case UIR_OPERAND_REG:
        fprintf(out, "r%d", op->reg);
        break;
    case UIR_OPERAND_IMM:
        fprintf(out, "0x%llx", (unsigned long long)op->imm);
        break;
    case UIR_OPERAND_MEM:
        fprintf(out, "[");
        if (op->reg >= 0) fprintf(out, "r%d", op->reg);
        if (op->index >= 0) fprintf(out, "+r%d*%d", op->index, op->scale);
        if (op->disp != 0) fprintf(out, "%+d", op->disp);
        fprintf(out, "]");
        break;
    case UIR_OPERAND_ADDR:
        fprintf(out, "@0x%llx", (unsigned long long)op->imm);
        break;
    }
}

void uir_print_block(const uir_block_t* block, FILE* out) {
    fprintf(out, "  block_%llx:\n", (unsigned long long)block->address);
    for (size_t i = 0; i < block->count; i++) {
        const uir_instruction_t* ins = &block->instructions[i];
        fprintf(out, "    %08llx: %-10s",
                (unsigned long long)ins->original_address,
                uir_opcode_name(ins->opcode));

        if (ins->dest.type != UIR_OPERAND_NONE) {
            fprintf(out, " ");
            print_uir_operand(&ins->dest, out);
        }
        if (ins->src1.type != UIR_OPERAND_NONE) {
            fprintf(out, ", ");
            print_uir_operand(&ins->src1, out);
        }
        if (ins->src2.type != UIR_OPERAND_NONE) {
            fprintf(out, ", ");
            print_uir_operand(&ins->src2, out);
        }
        fprintf(out, "\n");
    }

    if (block->fall_through >= 0) {
        fprintf(out, "    -> fall_through: block_%d\n", block->fall_through);
    }
    if (block->branch_target >= 0) {
        fprintf(out, "    -> branch: block_%d\n", block->branch_target);
    }
}

void uir_print_function(const uir_function_t* func, FILE* out) {
    fprintf(out, "function @ 0x%llx (%zu blocks)\n",
            (unsigned long long)func->entry_address, func->block_count);

    if (func->has_port_io) {
        fprintf(out, "  PORT I/O: yes");
        if (func->ports_read_count > 0) {
            fprintf(out, " (reads:");
            for (size_t i = 0; i < func->ports_read_count; i++)
                fprintf(out, " 0x%X", func->ports_read[i]);
            fprintf(out, ")");
        }
        if (func->ports_written_count > 0) {
            fprintf(out, " (writes:");
            for (size_t i = 0; i < func->ports_written_count; i++)
                fprintf(out, " 0x%X", func->ports_written[i]);
            fprintf(out, ")");
        }
        fprintf(out, "\n");
    }

    for (size_t i = 0; i < func->block_count; i++) {
        uir_print_block(&func->blocks[i], out);
    }
}

/* ============================================================================
 * ARM64 Lifter
 * ============================================================================ */

/* Record a sysreg in a dynamic array (dedup) */
static void record_sysreg(uint16_t** arr, size_t* count, size_t* cap,
                           uint16_t encoding) {
    for (size_t i = 0; i < *count; i++) {
        if ((*arr)[i] == encoding) return;
    }
    if (*count >= *cap) {
        *cap = (*cap == 0) ? 8 : *cap * 2;
        *arr = realloc(*arr, *cap * sizeof(uint16_t));
    }
    (*arr)[(*count)++] = encoding;
}

static uir_instruction_t lift_arm64_one(const uir_arm64_input_t* in) {
    uir_instruction_t uir;
    memset(&uir, 0, sizeof(uir));
    uir.original_address = in->address;
    uir.size = in->is_64bit ? 8 : 4;

    /* Helper to make a register operand */
    #define REG_OP(idx) do { \
        uir_operand_t* _o = (idx == 0 ? &uir.dest : (idx == 1 ? &uir.src1 : &uir.src2)); \
        _o->type = UIR_OPERAND_REG; \
        _o->reg = in->operands[idx].reg; \
        _o->size = in->operands[idx].size; \
    } while(0)

    #define IMM_OP(dst_field, idx) do { \
        dst_field.type = UIR_OPERAND_IMM; \
        dst_field.imm = in->operands[idx].imm; \
    } while(0)

    /* Shared logic for three-operand ALU instructions (dest, src1, src2) */
    #define LIFT_THREE_OP() do { \
        REG_OP(0); \
        uir.src1.type = UIR_OPERAND_REG; \
        uir.src1.reg = in->operands[1].reg; \
        uir.src1.size = in->operands[1].size; \
        if (in->operand_count > 2) { \
            if (in->operands[2].type == A64_OP_IMM) { \
                IMM_OP(uir.src2, 2); \
            } else { \
                uir.src2.type = UIR_OPERAND_REG; \
                uir.src2.reg = in->operands[2].reg; \
                uir.src2.size = in->operands[2].size; \
            } \
        } \
    } while(0)

    switch (in->instruction) {
    case A64_INS_NOP:
        uir.opcode = UIR_NOP;
        break;

    case A64_INS_MOV:
    case A64_INS_MOVZ:
    case A64_INS_MOVK:
    case A64_INS_MOVN:
        uir.opcode = UIR_MOV;
        REG_OP(0);
        if (in->operands[1].type == A64_OP_REG) {
            uir.src1.type = UIR_OPERAND_REG;
            uir.src1.reg = in->operands[1].reg;
            uir.src1.size = in->operands[1].size;
        } else {
            IMM_OP(uir.src1, 1);
        }
        break;

    case A64_INS_ADD:
        uir.opcode = UIR_ADD;
        REG_OP(0);
        uir.src1.type = UIR_OPERAND_REG;
        uir.src1.reg = in->operands[1].reg;
        uir.src1.size = in->operands[1].size;
        if (in->operands[2].type == A64_OP_IMM) {
            IMM_OP(uir.src2, 2);
        } else {
            uir.src2.type = UIR_OPERAND_REG;
            uir.src2.reg = in->operands[2].reg;
            uir.src2.size = in->operands[2].size;
        }
        break;

    case A64_INS_SUB:
    case A64_INS_NEG:
        uir.opcode = UIR_SUB;
        REG_OP(0);
        uir.src1.type = UIR_OPERAND_REG;
        uir.src1.reg = in->operands[1].reg;
        uir.src1.size = in->operands[1].size;
        if (in->operand_count > 2) {
            if (in->operands[2].type == A64_OP_IMM) {
                IMM_OP(uir.src2, 2);
            } else {
                uir.src2.type = UIR_OPERAND_REG;
                uir.src2.reg = in->operands[2].reg;
                uir.src2.size = in->operands[2].size;
            }
        }
        break;

    case A64_INS_AND:
    case A64_INS_BIC:
        uir.opcode = UIR_AND;
        LIFT_THREE_OP();
        break;
    case A64_INS_ORR:
    case A64_INS_ORN:
        uir.opcode = UIR_OR;
        LIFT_THREE_OP();
        break;
    case A64_INS_EOR:
        uir.opcode = UIR_XOR;
        LIFT_THREE_OP();
        break;

    case A64_INS_LSL: uir.opcode = UIR_SHL; LIFT_THREE_OP(); break;
    case A64_INS_LSR: uir.opcode = UIR_SHR; LIFT_THREE_OP(); break;
    case A64_INS_ASR: uir.opcode = UIR_SAR; LIFT_THREE_OP(); break;

    case A64_INS_CMP:
    case A64_INS_CMN:
        uir.opcode = UIR_CMP;
        uir.dest.type = UIR_OPERAND_REG;
        uir.dest.reg = in->operands[0].reg;
        uir.dest.size = in->operands[0].size;
        if (in->operands[1].type == A64_OP_IMM) {
            IMM_OP(uir.src1, 1);
        } else {
            uir.src1.type = UIR_OPERAND_REG;
            uir.src1.reg = in->operands[1].reg;
            uir.src1.size = in->operands[1].size;
        }
        break;

    case A64_INS_TST:
        uir.opcode = UIR_TEST;
        uir.dest.type = UIR_OPERAND_REG;
        uir.dest.reg = in->operands[0].reg;
        uir.dest.size = in->operands[0].size;
        if (in->operands[1].type == A64_OP_IMM) {
            IMM_OP(uir.src1, 1);
        } else {
            uir.src1.type = UIR_OPERAND_REG;
            uir.src1.reg = in->operands[1].reg;
            uir.src1.size = in->operands[1].size;
        }
        break;

    case A64_INS_MUL:
    case A64_INS_MADD:
    case A64_INS_MSUB:
        uir.opcode = UIR_MUL;
        LIFT_THREE_OP();
        break;

    case A64_INS_SDIV:
        uir.opcode = UIR_IDIV;
        LIFT_THREE_OP();
        break;
    case A64_INS_UDIV:
        uir.opcode = UIR_DIV;
        LIFT_THREE_OP();
        break;

    case A64_INS_LDR:
    case A64_INS_LDRB:
    case A64_INS_LDRH:
    case A64_INS_LDRSB:
    case A64_INS_LDRSH:
    case A64_INS_LDRSW:
    case A64_INS_LDR_LITERAL:
        uir.opcode = UIR_LOAD;
        REG_OP(0);
        if (in->operands[1].type == A64_OP_MEM) {
            uir.src1.type = UIR_OPERAND_MEM;
            uir.src1.reg = in->operands[1].reg;
            uir.src1.disp = (int32_t)in->operands[1].imm;
            uir.src1.size = in->operands[1].size;
        } else {
            uir.src1.type = UIR_OPERAND_ADDR;
            uir.src1.imm = in->operands[1].imm;
        }
        break;

    case A64_INS_STR:
    case A64_INS_STRB:
    case A64_INS_STRH:
        uir.opcode = UIR_STORE;
        if (in->operands[1].type == A64_OP_MEM) {
            uir.dest.type = UIR_OPERAND_MEM;
            uir.dest.reg = in->operands[1].reg;
            uir.dest.disp = (int32_t)in->operands[1].imm;
            uir.dest.size = in->operands[1].size;
        }
        uir.src1.type = UIR_OPERAND_REG;
        uir.src1.reg = in->operands[0].reg;
        uir.src1.size = in->operands[0].size;
        break;

    case A64_INS_LDP:
        uir.opcode = UIR_LOAD;
        REG_OP(0);
        uir.src1.type = UIR_OPERAND_MEM;
        uir.src1.reg = in->operands[1].reg;
        uir.src1.disp = (int32_t)in->operands[1].imm;
        break;

    case A64_INS_STP:
        uir.opcode = UIR_STORE;
        uir.dest.type = UIR_OPERAND_MEM;
        uir.dest.reg = in->operands[1].reg;
        uir.dest.disp = (int32_t)in->operands[1].imm;
        uir.src1.type = UIR_OPERAND_REG;
        uir.src1.reg = in->operands[0].reg;
        break;

    case A64_INS_B:
        uir.opcode = UIR_JMP;
        uir.dest.type = UIR_OPERAND_ADDR;
        uir.dest.imm = in->operands[0].imm;
        break;

    case A64_INS_BL:
        uir.opcode = UIR_CALL;
        uir.dest.type = UIR_OPERAND_ADDR;
        uir.dest.imm = in->operands[0].imm;
        break;

    case A64_INS_BR:
        uir.opcode = UIR_JMP;
        REG_OP(0);
        break;

    case A64_INS_BLR:
        uir.opcode = UIR_CALL;
        REG_OP(0);
        break;

    case A64_INS_RET:
        uir.opcode = UIR_RET;
        break;

    case A64_INS_B_COND:
        uir.opcode = UIR_JCC;
        uir.cc = in->cc;
        uir.dest.type = UIR_OPERAND_ADDR;
        uir.dest.imm = in->operands[0].imm;
        break;

    case A64_INS_CBZ:
    case A64_INS_CBNZ:
    case A64_INS_TBZ:
    case A64_INS_TBNZ:
        uir.opcode = UIR_JCC;
        uir.cc = (in->instruction == A64_INS_CBZ || in->instruction == A64_INS_TBZ)
                  ? A64_CC_EQ : A64_CC_NE;
        /* Target is last operand */
        uir.dest.type = UIR_OPERAND_ADDR;
        uir.dest.imm = in->operands[in->operand_count - 1].imm;
        break;

    case A64_INS_MRS:
        uir.opcode = UIR_SYSREG_READ;
        REG_OP(0);
        uir.src1.type = UIR_OPERAND_IMM;
        uir.src1.imm = in->operands[1].sysreg_encoding;
        break;

    case A64_INS_MSR:
        uir.opcode = UIR_SYSREG_WRITE;
        uir.dest.type = UIR_OPERAND_IMM;
        uir.dest.imm = in->operands[0].sysreg_encoding;
        uir.src1.type = UIR_OPERAND_REG;
        uir.src1.reg = in->operands[1].reg;
        uir.src1.size = 8;
        break;

    case A64_INS_SVC:
    case A64_INS_HVC:
    case A64_INS_SMC:
        uir.opcode = UIR_CALL;
        IMM_OP(uir.dest, 0);
        break;

    case A64_INS_DMB:
    case A64_INS_DSB:
    case A64_INS_ISB:
        uir.opcode = UIR_BARRIER;
        if (in->operand_count > 0) {
            IMM_OP(uir.dest, 0);
        }
        break;

    case A64_INS_WFI:
        uir.opcode = UIR_HLT;
        break;

    default:
        uir.opcode = UIR_NOP;
        break;
    }

    #undef REG_OP
    #undef IMM_OP
    return uir;
}

uir_function_t* uir_lift_arm64_function(const uir_arm64_input_t* insts,
                                         size_t count,
                                         uint64_t entry_address) {
    if (count == 0) return NULL;

    /* Pass 1: collect branch targets */
    target_set_t targets;
    target_set_init(&targets);
    target_set_add(&targets, entry_address);

    for (size_t i = 0; i < count; i++) {
        int ins = insts[i].instruction;
        if (ins == A64_INS_B || ins == A64_INS_BL ||
            ins == A64_INS_B_COND || ins == A64_INS_CBZ ||
            ins == A64_INS_CBNZ || ins == A64_INS_TBZ ||
            ins == A64_INS_TBNZ) {
            /* Target address is in the last addr-type operand */
            for (int j = insts[i].operand_count - 1; j >= 0; j--) {
                if (insts[i].operands[j].type == A64_OP_ADDR) {
                    target_set_add(&targets, (uint64_t)insts[i].operands[j].imm);
                    break;
                }
            }
            /* Fall-through target (next instruction) */
            if (i + 1 < count) {
                target_set_add(&targets, insts[i + 1].address);
            }
        }
    }

    /* Sort targets */
    for (size_t i = 0; i < targets.count; i++) {
        for (size_t j = i + 1; j < targets.count; j++) {
            if (targets.addrs[j] < targets.addrs[i]) {
                uint64_t tmp = targets.addrs[i];
                targets.addrs[i] = targets.addrs[j];
                targets.addrs[j] = tmp;
            }
        }
    }

    /* Pass 2: create blocks and lift instructions */
    size_t block_cap = 16;
    size_t block_count = 0;
    uir_block_t* blocks = malloc(block_cap * sizeof(uir_block_t));

    /* Start first block */
    block_init(&blocks[0], insts[0].address);
    blocks[0].is_entry = (insts[0].address == entry_address);
    block_count = 1;

    for (size_t i = 0; i < count; i++) {
        uint64_t addr = insts[i].address;
        uir_block_t* cur = &blocks[block_count - 1];

        /* Check if this address starts a new block */
        if (i > 0 && target_set_contains(&targets, addr) &&
            cur->count > 0) {
            /* Start new block */
            if (block_count >= block_cap) {
                block_cap *= 2;
                blocks = realloc(blocks, block_cap * sizeof(uir_block_t));
            }
            block_init(&blocks[block_count], addr);
            blocks[block_count].is_entry = (addr == entry_address);
            block_count++;
            cur = &blocks[block_count - 1];
        }

        /* Lift and append */
        uir_instruction_t uir_ins = lift_arm64_one(&insts[i]);
        block_append(cur, &uir_ins);

        /* End block after branch/ret */
        int ins = insts[i].instruction;
        bool ends_block = (ins == A64_INS_B || ins == A64_INS_BR ||
                           ins == A64_INS_RET || ins == A64_INS_B_COND ||
                           ins == A64_INS_CBZ || ins == A64_INS_CBNZ ||
                           ins == A64_INS_TBZ || ins == A64_INS_TBNZ);
        if (ends_block && i + 1 < count) {
            if (block_count >= block_cap) {
                block_cap *= 2;
                blocks = realloc(blocks, block_cap * sizeof(uir_block_t));
            }
            block_init(&blocks[block_count], insts[i + 1].address);
            block_count++;
        }
    }

    /* Pass 3: link blocks */
    for (size_t i = 0; i < block_count; i++) {
        uir_block_t* b = &blocks[i];
        if (b->count == 0) continue;
        uir_instruction_t* last = &b->instructions[b->count - 1];

        if (last->opcode == UIR_JMP && last->dest.type == UIR_OPERAND_ADDR) {
            for (size_t j = 0; j < block_count; j++) {
                if (blocks[j].address == (uint64_t)last->dest.imm) {
                    b->branch_target = (int)j;
                    break;
                }
            }
        } else if (last->opcode == UIR_JCC && last->dest.type == UIR_OPERAND_ADDR) {
            for (size_t j = 0; j < block_count; j++) {
                if (blocks[j].address == (uint64_t)last->dest.imm) {
                    b->branch_target = (int)j;
                    break;
                }
            }
            if (i + 1 < block_count) {
                b->fall_through = (int)(i + 1);
            }
        } else if (last->opcode != UIR_RET) {
            if (i + 1 < block_count) {
                b->fall_through = (int)(i + 1);
            }
        }
    }

    /* Build function and collect sysreg summary */
    uir_function_t* func = calloc(1, sizeof(uir_function_t));
    func->blocks = blocks;
    func->block_count = block_count;
    func->entry_address = entry_address;

    size_t sr_cap = 0, sw_cap = 0;
    for (size_t i = 0; i < block_count; i++) {
        for (size_t j = 0; j < blocks[i].count; j++) {
            uir_instruction_t* ins = &blocks[i].instructions[j];
            if (ins->opcode == UIR_SYSREG_READ) {
                func->has_sysreg_io = true;
                record_sysreg(&func->sysregs_read,
                              &func->sysregs_read_count, &sr_cap,
                              (uint16_t)ins->src1.imm);
            } else if (ins->opcode == UIR_SYSREG_WRITE) {
                func->has_sysreg_io = true;
                record_sysreg(&func->sysregs_written,
                              &func->sysregs_written_count, &sw_cap,
                              (uint16_t)ins->dest.imm);
            }
        }
    }

    free(targets.addrs);
    return func;
}
