/* ============================================================================
 * Semantic Analyzer — Function Classification
 * ============================================================================
 *
 * Classifies Windows driver imports and UIR functions as hardware-relevant
 * or scaffolding. The API recognition table is a copy of the one from
 * tools/driver-extract/driver_extract.c, using the translator's own category
 * enum to avoid a build dependency on that directory.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "semantic.h"
#include "uir.h"
#include "x86_decoder.h"

/* ============================================================================
 * Windows Driver API Recognition Table
 *
 * Mirrors DRV_API_TABLE from driver_extract.c. Maintained separately to
 * keep the translator self-contained. If the driver-extract table grows,
 * sync this table too.
 * ============================================================================ */

const sem_api_entry_t SEM_API_TABLE[] = {
    /* ---- PORT I/O (HAL.DLL) — KEEP ---- */
    {"READ_PORT_UCHAR",         SEM_CAT_PORT_IO, "C@-PORT",    "Read byte from port"},
    {"READ_PORT_USHORT",        SEM_CAT_PORT_IO, "W@-PORT",    "Read word from port"},
    {"READ_PORT_ULONG",         SEM_CAT_PORT_IO, "@-PORT",     "Read dword from port"},
    {"WRITE_PORT_UCHAR",        SEM_CAT_PORT_IO, "C!-PORT",    "Write byte to port"},
    {"WRITE_PORT_USHORT",       SEM_CAT_PORT_IO, "W!-PORT",    "Write word to port"},
    {"WRITE_PORT_ULONG",        SEM_CAT_PORT_IO, "!-PORT",     "Write dword to port"},
    {"READ_PORT_BUFFER_UCHAR",  SEM_CAT_PORT_IO, "C@N-PORT",   "Read N bytes from port"},
    {"READ_PORT_BUFFER_USHORT", SEM_CAT_PORT_IO, "W@N-PORT",   "Read N words from port"},
    {"READ_PORT_BUFFER_ULONG",  SEM_CAT_PORT_IO, "@N-PORT",    "Read N dwords from port"},
    {"WRITE_PORT_BUFFER_UCHAR", SEM_CAT_PORT_IO, "C!N-PORT",   "Write N bytes to port"},
    {"WRITE_PORT_BUFFER_USHORT",SEM_CAT_PORT_IO, "W!N-PORT",   "Write N words to port"},
    {"WRITE_PORT_BUFFER_ULONG", SEM_CAT_PORT_IO, "!N-PORT",    "Write N dwords to port"},

    /* ---- MMIO — KEEP ---- */
    {"READ_REGISTER_UCHAR",     SEM_CAT_MMIO, "C@-MMIO",    "Read byte from MMIO"},
    {"READ_REGISTER_USHORT",    SEM_CAT_MMIO, "W@-MMIO",    "Read word from MMIO"},
    {"READ_REGISTER_ULONG",     SEM_CAT_MMIO, "@-MMIO",     "Read dword from MMIO"},
    {"READ_REGISTER_ULONG64",   SEM_CAT_MMIO, "D@-MMIO",    "Read qword from MMIO"},
    {"WRITE_REGISTER_UCHAR",    SEM_CAT_MMIO, "C!-MMIO",    "Write byte to MMIO"},
    {"WRITE_REGISTER_USHORT",   SEM_CAT_MMIO, "W!-MMIO",    "Write word to MMIO"},
    {"WRITE_REGISTER_ULONG",    SEM_CAT_MMIO, "!-MMIO",     "Write dword to MMIO"},
    {"WRITE_REGISTER_ULONG64",  SEM_CAT_MMIO, "D!-MMIO",    "Write qword to MMIO"},
    {"MmMapIoSpace",            SEM_CAT_MMIO, "MAP-PHYS",   "Map physical to virtual"},
    {"MmUnmapIoSpace",          SEM_CAT_MMIO, "UNMAP-PHYS", "Unmap MMIO region"},

    /* ---- TIMING — KEEP ---- */
    {"KeStallExecutionProcessor", SEM_CAT_TIMING, "US-DELAY",   "Busy-wait microseconds"},
    {"KeDelayExecutionThread",    SEM_CAT_TIMING, "MS-DELAY",   "Sleep milliseconds"},
    {"KeQueryPerformanceCounter", SEM_CAT_TIMING, "PERF-COUNT", "Read perf counter"},
    {"KeQuerySystemTime",         SEM_CAT_TIMING, "SYS-TIME",   "Get system time"},

    /* ---- DMA — KEEP ---- */
    {"IoAllocateMdl",                   SEM_CAT_DMA, "DMA-MDL",      "Allocate MDL"},
    {"IoFreeMdl",                       SEM_CAT_DMA, "DMA-FREE-MDL", "Free MDL"},
    {"MmBuildMdlForNonPagedPool",       SEM_CAT_DMA, "DMA-BUILD",    "Build MDL"},
    {"MmGetPhysicalAddress",            SEM_CAT_DMA, "VIRT>PHYS",    "Get physical address"},
    {"MmAllocateContiguousMemory",      SEM_CAT_DMA, "DMA-ALLOC",    "Allocate contiguous"},
    {"MmFreeContiguousMemory",          SEM_CAT_DMA, "DMA-FREE",     "Free contiguous"},
    {"IoGetDmaAdapter",                 SEM_CAT_DMA, "DMA-ADAPTER",  "Get DMA adapter"},
    {"AllocateCommonBuffer",            SEM_CAT_DMA, "DMA-BUFFER",   "Allocate DMA buffer"},
    {"FreeCommonBuffer",                SEM_CAT_DMA, "DMA-UNBUFFER", "Free DMA buffer"},
    {"MapTransfer",                     SEM_CAT_DMA, "DMA-MAP",      "Map for DMA"},
    {"FlushAdapterBuffers",             SEM_CAT_DMA, "DMA-FLUSH",    "Flush DMA"},

    /* ---- INTERRUPT — KEEP ---- */
    {"IoConnectInterrupt",      SEM_CAT_INTERRUPT, "IRQ-CONNECT",   "Connect ISR"},
    {"IoDisconnectInterrupt",   SEM_CAT_INTERRUPT, "IRQ-DISCONNECT", "Disconnect ISR"},
    {"KeSynchronizeExecution",  SEM_CAT_INTERRUPT, "IRQ-SYNC",      "Sync with ISR"},
    {"IoRequestDpc",            SEM_CAT_INTERRUPT, "DPC-REQUEST",   "Request DPC"},
    {"KeInsertQueueDpc",        SEM_CAT_INTERRUPT, "DPC-QUEUE",     "Queue DPC"},

    /* ---- PCI CONFIG — KEEP ---- */
    {"HalGetBusData",           SEM_CAT_PCI_CONFIG, "PCI-READ",    "Read PCI config"},
    {"HalGetBusDataByOffset",   SEM_CAT_PCI_CONFIG, "PCI-READ@",   "Read PCI at offset"},
    {"HalSetBusData",           SEM_CAT_PCI_CONFIG, "PCI-WRITE",   "Write PCI config"},
    {"HalSetBusDataByOffset",   SEM_CAT_PCI_CONFIG, "PCI-WRITE@",  "Write PCI at offset"},

    /* ---- IRP — FILTER ---- */
    {"IoCompleteRequest",       SEM_CAT_IRP, NULL, "Complete IRP"},
    {"IoCallDriver",            SEM_CAT_IRP, NULL, "Call lower driver"},
    {"IoSkipCurrentIrpStackLocation", SEM_CAT_IRP, NULL, "Skip IRP stack"},
    {"IoCopyCurrentIrpStackLocationToNext", SEM_CAT_IRP, NULL, "Copy IRP stack"},
    {"IoGetCurrentIrpStackLocation", SEM_CAT_IRP, NULL, "Get IRP stack"},
    {"IoMarkIrpPending",        SEM_CAT_IRP, NULL, "Mark IRP pending"},
    {"IoSetCompletionRoutine",  SEM_CAT_IRP, NULL, "Set completion"},
    {"IoAllocateIrp",           SEM_CAT_IRP, NULL, "Allocate IRP"},
    {"IoFreeIrp",               SEM_CAT_IRP, NULL, "Free IRP"},
    {"IoBuildDeviceIoControlRequest", SEM_CAT_IRP, NULL, "Build IOCTL IRP"},
    {"IoBuildSynchronousFsdRequest",  SEM_CAT_IRP, NULL, "Build sync IRP"},

    /* ---- PnP — FILTER ---- */
    {"IoRegisterDeviceInterface", SEM_CAT_PNP, NULL, "Register interface"},
    {"IoSetDeviceInterfaceState", SEM_CAT_PNP, NULL, "Set interface state"},
    {"IoOpenDeviceRegistryKey",   SEM_CAT_PNP, NULL, "Open device registry"},
    {"IoGetDeviceProperty",       SEM_CAT_PNP, NULL, "Get device property"},
    {"IoInvalidateDeviceRelations", SEM_CAT_PNP, NULL, "Invalidate relations"},
    {"IoReportTargetDeviceChange", SEM_CAT_PNP, NULL, "Report device change"},

    /* ---- POWER — FILTER ---- */
    {"PoRequestPowerIrp",       SEM_CAT_POWER, NULL, "Request power IRP"},
    {"PoSetPowerState",         SEM_CAT_POWER, NULL, "Set power state"},
    {"PoCallDriver",            SEM_CAT_POWER, NULL, "Call power driver"},
    {"PoStartNextPowerIrp",     SEM_CAT_POWER, NULL, "Start next power IRP"},
    {"PoRegisterDeviceForIdleDetection", SEM_CAT_POWER, NULL, "Register idle"},

    /* ---- MEMORY MGR — FILTER ---- */
    {"ExAllocatePool",          SEM_CAT_MEMORY_MGR, NULL, "Allocate pool"},
    {"ExAllocatePoolWithTag",   SEM_CAT_MEMORY_MGR, NULL, "Allocate tagged pool"},
    {"ExFreePool",              SEM_CAT_MEMORY_MGR, NULL, "Free pool"},
    {"ExFreePoolWithTag",       SEM_CAT_MEMORY_MGR, NULL, "Free tagged pool"},
    {"MmProbeAndLockPages",     SEM_CAT_MEMORY_MGR, NULL, "Lock pages"},
    {"MmUnlockPages",           SEM_CAT_MEMORY_MGR, NULL, "Unlock pages"},

    /* ---- SYNC — FILTER ---- */
    {"KeInitializeSpinLock",    SEM_CAT_SYNC, NULL, "Init spinlock"},
    {"KeAcquireSpinLock",       SEM_CAT_SYNC, NULL, "Acquire spinlock"},
    {"KeReleaseSpinLock",       SEM_CAT_SYNC, NULL, "Release spinlock"},
    {"KeAcquireSpinLockAtDpcLevel", SEM_CAT_SYNC, NULL, "Acquire at DPC"},
    {"KeReleaseSpinLockFromDpcLevel", SEM_CAT_SYNC, NULL, "Release from DPC"},
    {"KeInitializeEvent",       SEM_CAT_SYNC, NULL, "Init event"},
    {"KeSetEvent",              SEM_CAT_SYNC, NULL, "Set event"},
    {"KeClearEvent",            SEM_CAT_SYNC, NULL, "Clear event"},
    {"KeWaitForSingleObject",   SEM_CAT_SYNC, NULL, "Wait single"},
    {"KeWaitForMultipleObjects", SEM_CAT_SYNC, NULL, "Wait multiple"},
    {"ExAcquireFastMutex",      SEM_CAT_SYNC, NULL, "Acquire fast mutex"},
    {"ExReleaseFastMutex",      SEM_CAT_SYNC, NULL, "Release fast mutex"},

    /* ---- REGISTRY — FILTER ---- */
    {"ZwOpenKey",               SEM_CAT_REGISTRY, NULL, "Open reg key"},
    {"ZwCreateKey",             SEM_CAT_REGISTRY, NULL, "Create reg key"},
    {"ZwQueryValueKey",         SEM_CAT_REGISTRY, NULL, "Query reg value"},
    {"ZwSetValueKey",           SEM_CAT_REGISTRY, NULL, "Set reg value"},
    {"ZwClose",                 SEM_CAT_REGISTRY, NULL, "Close handle"},

    /* ---- STRING — FILTER ---- */
    {"RtlInitUnicodeString",    SEM_CAT_STRING, NULL, "Init unicode string"},
    {"RtlCopyUnicodeString",    SEM_CAT_STRING, NULL, "Copy unicode string"},
    {"RtlCompareUnicodeString", SEM_CAT_STRING, NULL, "Compare unicode"},
    {"RtlAnsiStringToUnicodeString", SEM_CAT_STRING, NULL, "ANSI to unicode"},
    {"RtlUnicodeStringToAnsiString", SEM_CAT_STRING, NULL, "Unicode to ANSI"},

    /* End sentinel */
    {NULL, SEM_CAT_UNKNOWN, NULL, NULL}
};

const size_t SEM_API_TABLE_SIZE =
    sizeof(SEM_API_TABLE) / sizeof(SEM_API_TABLE[0]) - 1;

/* ============================================================================
 * Import Classification
 * ============================================================================ */

sem_category_t sem_classify_import(const char* func_name,
                                    const char** forth_equiv) {
    if (forth_equiv) *forth_equiv = NULL;

    for (size_t i = 0; i < SEM_API_TABLE_SIZE; i++) {
        if (strcmp(SEM_API_TABLE[i].name, func_name) == 0) {
            if (forth_equiv) *forth_equiv = SEM_API_TABLE[i].forth_equiv;
            return SEM_API_TABLE[i].category;
        }
    }
    return SEM_CAT_UNKNOWN;
}

int sem_classify_imports(const sem_pe_import_t* pe_imports, size_t pe_import_count,
                          sem_result_t* result) {
    if (!pe_imports || pe_import_count == 0) return 0;

    result->imports = calloc(pe_import_count, sizeof(sem_import_t));
    if (!result->imports) return -1;
    result->import_count = pe_import_count;

    for (size_t i = 0; i < pe_import_count; i++) {
        sem_import_t* imp = &result->imports[i];
        imp->dll_name = strdup(pe_imports[i].dll_name);
        imp->func_name = strdup(pe_imports[i].func_name);
        imp->iat_rva = pe_imports[i].iat_rva;
        imp->category = sem_classify_import(pe_imports[i].func_name,
                                             &imp->forth_equiv);
    }

    return 0;
}

/* ============================================================================
 * Function Analysis
 * ============================================================================ */

int sem_analyze_functions(const sem_uir_input_t* uir_funcs, size_t uir_func_count,
                           uint64_t image_base, sem_result_t* result) {
    if (!uir_funcs || uir_func_count == 0) return 0;

    result->functions = calloc(uir_func_count, sizeof(sem_function_t));
    if (!result->functions) return -1;
    result->function_count = uir_func_count;

    result->hw_function_count = 0;
    result->filtered_count = 0;

    for (size_t i = 0; i < uir_func_count; i++) {
        const sem_uir_input_t* uf = &uir_funcs[i];
        sem_function_t* sf = &result->functions[i];

        sf->address = uf->entry_address;
        sf->name = uf->name ? strdup(uf->name) : NULL;
        if (!sf->name) {
            /* Generate a synthetic name */
            char buf[32];
            snprintf(buf, sizeof(buf), "func_%llX",
                     (unsigned long long)uf->entry_address);
            sf->name = strdup(buf);
        }

        /* Check for port I/O from UIR analysis (direct IN/OUT instructions) */
        sf->has_port_io = uf->has_port_io;

        /* Collect ports from direct IN/OUT */
        size_t total_ports = uf->ports_read_count + uf->ports_written_count;
        if (total_ports > 0) {
            sf->ports = malloc(total_ports * sizeof(uint16_t));
            sf->port_count = 0;
            for (size_t p = 0; p < uf->ports_read_count; p++) {
                /* Deduplicate */
                bool dup = false;
                for (size_t q = 0; q < sf->port_count; q++) {
                    if (sf->ports[q] == uf->ports_read[p]) { dup = true; break; }
                }
                if (!dup) sf->ports[sf->port_count++] = uf->ports_read[p];
            }
            for (size_t p = 0; p < uf->ports_written_count; p++) {
                bool dup = false;
                for (size_t q = 0; q < sf->port_count; q++) {
                    if (sf->ports[q] == uf->ports_written[p]) { dup = true; break; }
                }
                if (!dup) sf->ports[sf->port_count++] = uf->ports_written[p];
            }
        }

        /* Check for calls to hardware HAL imports via IAT.
         * Walk UIR blocks looking for CALL instructions with memory-indirect
         * operands (call dword [addr]) where addr matches image_base + iat_rva
         * of a classified hardware import. */
        const uir_function_t* uir_func = (const uir_function_t*)uf->func;
        if (uir_func && result->imports && result->import_count > 0) {
            for (size_t b = 0; b < uir_func->block_count; b++) {
                const uir_block_t* blk = &uir_func->blocks[b];
                for (size_t j = 0; j < blk->count; j++) {
                    const uir_instruction_t* ins = &blk->instructions[j];
                    if (ins->opcode != UIR_CALL) continue;
                    if (ins->dest.type != UIR_OPERAND_MEM) continue;

                    /* Memory-indirect call with no base/index = call [absolute_addr] */
                    if (ins->dest.reg >= 0 || ins->dest.index >= 0) continue;
                    uint64_t call_target = (uint64_t)(uint32_t)ins->dest.disp;

                    /* Cross-reference against classified imports */
                    for (size_t k = 0; k < result->import_count; k++) {
                        uint64_t iat_abs = image_base + result->imports[k].iat_rva;
                        if (call_target != iat_abs) continue;
                        sem_category_t cat = result->imports[k].category;
                        if (sem_is_hardware(cat)) {
                            sf->is_hardware = true;
                            sf->hw_call_count++;
                            if (cat == SEM_CAT_PORT_IO) sf->has_port_io = true;
                            else if (cat == SEM_CAT_MMIO) sf->has_mmio = true;
                            else if (cat == SEM_CAT_TIMING) sf->has_timing = true;
                            else if (cat == SEM_CAT_PCI_CONFIG) sf->has_pci = true;
                            if (sf->primary_category == SEM_CAT_UNKNOWN)
                                sf->primary_category = cat;
                        } else if (sem_is_scaffolding(cat)) {
                            sf->has_scaffolding = true;
                            sf->scaf_call_count++;
                        }
                        break;
                    }
                }
            }
        }

        /* Determine primary category from direct port I/O if not already set */
        if (sf->has_port_io && sf->primary_category == SEM_CAT_UNKNOWN) {
            sf->primary_category = SEM_CAT_PORT_IO;
            sf->is_hardware = true;
        }

        /* Count hw/scaffolding */
        if (sf->is_hardware) {
            result->hw_function_count++;
        } else {
            result->filtered_count++;
        }
    }

    return 0;
}

/* ============================================================================
 * Function Boundary Discovery
 * ============================================================================ */

/* Compare for qsort */
static int cmp_u64(const void* a, const void* b) {
    uint64_t va = *(const uint64_t*)a;
    uint64_t vb = *(const uint64_t*)b;
    if (va < vb) return -1;
    if (va > vb) return 1;
    return 0;
}

int sem_discover_functions(const void* decoded_insts, size_t inst_count,
                           uint64_t text_base, uint64_t text_end,
                           const sem_pe_export_t* exports, size_t export_count,
                           sem_function_map_t* result) {
    const x86_decoded_t* insts = (const x86_decoded_t*)decoded_insts;
    if (!insts || inst_count == 0 || !result) return -1;

    memset(result, 0, sizeof(*result));

    /* Collect candidate entry points (max: exports + calls + prologues) */
    size_t max_entries = export_count + inst_count + 1;
    uint64_t* entry_points = malloc(max_entries * sizeof(uint64_t));
    size_t ep_count = 0;

    /* 1. PE export addresses */
    for (size_t i = 0; i < export_count; i++) {
        if (exports[i].address >= text_base && exports[i].address < text_end)
            entry_points[ep_count++] = exports[i].address;
    }

    /* 2. CALL targets within .text */
    for (size_t i = 0; i < inst_count; i++) {
        if (insts[i].instruction == X86_INS_CALL &&
            insts[i].operand_count > 0 &&
            (insts[i].operands[0].type == X86_OP_REL ||
             insts[i].operands[0].type == X86_OP_IMM)) {
            uint64_t target;
            if (insts[i].operands[0].type == X86_OP_REL)
                target = insts[i].address + insts[i].length + insts[i].operands[0].imm;
            else
                target = (uint64_t)insts[i].operands[0].imm;
            if (target >= text_base && target < text_end)
                entry_points[ep_count++] = target;
        }
    }

    /* 3. Function prologue patterns: push ebp; mov ebp, esp */
    for (size_t i = 0; i + 1 < inst_count; i++) {
        if (insts[i].instruction == X86_INS_PUSH &&
            insts[i].operand_count > 0 &&
            insts[i].operands[0].type == X86_OP_REG &&
            insts[i].operands[0].reg == X86_REG_EBP &&
            insts[i+1].instruction == X86_INS_MOV &&
            insts[i+1].operand_count >= 2 &&
            insts[i+1].operands[0].type == X86_OP_REG &&
            insts[i+1].operands[0].reg == X86_REG_EBP &&
            insts[i+1].operands[1].type == X86_OP_REG &&
            insts[i+1].operands[1].reg == X86_REG_ESP) {
            entry_points[ep_count++] = insts[i].address;
        }
    }

    /* Always include the text base address as a function start */
    entry_points[ep_count++] = text_base;

    /* Sort and deduplicate */
    qsort(entry_points, ep_count, sizeof(uint64_t), cmp_u64);
    size_t unique = 0;
    for (size_t i = 0; i < ep_count; i++) {
        if (unique == 0 || entry_points[i] != entry_points[unique - 1])
            entry_points[unique++] = entry_points[i];
    }
    ep_count = unique;

    /* Build function boundaries from sorted entry points */
    result->entries = calloc(ep_count, sizeof(sem_func_boundary_t));
    result->count = ep_count;

    for (size_t f = 0; f < ep_count; f++) {
        result->entries[f].start_address = entry_points[f];

        /* Find the instruction index for this entry point */
        result->entries[f].inst_start = inst_count; /* sentinel */
        for (size_t i = 0; i < inst_count; i++) {
            if (insts[i].address == entry_points[f]) {
                result->entries[f].inst_start = i;
                break;
            }
            /* If address is past this entry point, use nearest instruction */
            if (insts[i].address > entry_points[f]) {
                result->entries[f].inst_start = i;
                result->entries[f].start_address = insts[i].address;
                break;
            }
        }

        /* Compute inst_count: runs until next entry point's inst_start */
        size_t next_start;
        if (f + 1 < ep_count) {
            next_start = inst_count; /* sentinel */
            for (size_t i = result->entries[f].inst_start; i < inst_count; i++) {
                if (insts[i].address >= entry_points[f + 1]) {
                    next_start = i;
                    break;
                }
            }
        } else {
            next_start = inst_count;
        }
        result->entries[f].inst_count = next_start - result->entries[f].inst_start;

        /* Look up export name */
        result->entries[f].name = NULL;
        for (size_t e = 0; e < export_count; e++) {
            if (exports[e].address == entry_points[f]) {
                result->entries[f].name = exports[e].name;
                break;
            }
        }
    }

    free(entry_points);

    /* Remove entries with zero instructions */
    size_t valid = 0;
    for (size_t i = 0; i < result->count; i++) {
        if (result->entries[i].inst_count > 0) {
            if (valid != i)
                result->entries[valid] = result->entries[i];
            valid++;
        }
    }
    result->count = valid;

    return 0;
}

void sem_function_map_free(sem_function_map_t* map) {
    if (map->entries) {
        free(map->entries);
        map->entries = NULL;
    }
    map->count = 0;
}

/* ============================================================================
 * Report
 * ============================================================================ */

void sem_print_report(const sem_result_t* result, FILE* out) {
    fprintf(out, "Semantic Analysis Report\n");
    fprintf(out, "========================\n\n");

    /* Imports summary */
    if (result->import_count > 0) {
        size_t hw_imports = 0, scaf_imports = 0;
        for (size_t i = 0; i < result->import_count; i++) {
            if (sem_is_hardware(result->imports[i].category)) hw_imports++;
            else if (sem_is_scaffolding(result->imports[i].category)) scaf_imports++;
        }
        fprintf(out, "Imports: %zu total, %zu hardware, %zu scaffolding, %zu unknown\n",
                result->import_count, hw_imports, scaf_imports,
                result->import_count - hw_imports - scaf_imports);

        fprintf(out, "\n  Hardware APIs:\n");
        for (size_t i = 0; i < result->import_count; i++) {
            if (sem_is_hardware(result->imports[i].category)) {
                fprintf(out, "    %-35s -> %s\n",
                        result->imports[i].func_name,
                        result->imports[i].forth_equiv ? result->imports[i].forth_equiv : "?");
            }
        }

        fprintf(out, "\n  Scaffolding APIs (filtered):\n");
        for (size_t i = 0; i < result->import_count; i++) {
            if (sem_is_scaffolding(result->imports[i].category)) {
                fprintf(out, "    %s\n", result->imports[i].func_name);
            }
        }
    }

    /* Functions summary */
    fprintf(out, "\nFunctions: %zu total, %zu hardware, %zu filtered\n",
            result->function_count, result->hw_function_count,
            result->filtered_count);

    for (size_t i = 0; i < result->function_count; i++) {
        const sem_function_t* f = &result->functions[i];
        fprintf(out, "  %s @ 0x%llX: %s",
                f->name, (unsigned long long)f->address,
                f->is_hardware ? "HARDWARE" : "scaffolding");
        if (f->port_count > 0) {
            fprintf(out, " (ports:");
            for (size_t p = 0; p < f->port_count; p++)
                fprintf(out, " 0x%X", f->ports[p]);
            fprintf(out, ")");
        }
        fprintf(out, "\n");
    }
}

/* ============================================================================
 * Cleanup
 * ============================================================================ */

void sem_cleanup(sem_result_t* result) {
    if (result->imports) {
        for (size_t i = 0; i < result->import_count; i++) {
            free(result->imports[i].dll_name);
            free(result->imports[i].func_name);
        }
        free(result->imports);
    }
    if (result->functions) {
        for (size_t i = 0; i < result->function_count; i++) {
            free(result->functions[i].name);
            free(result->functions[i].ports);
        }
        free(result->functions);
    }
    memset(result, 0, sizeof(*result));
}
