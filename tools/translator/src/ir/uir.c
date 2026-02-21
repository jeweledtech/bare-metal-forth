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
