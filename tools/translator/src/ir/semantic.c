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
                           sem_result_t* result) {
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

        /* Check for port I/O from UIR analysis */
        sf->has_port_io = uf->has_port_io;

        /* Collect ports */
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

        /* Determine primary category */
        if (sf->has_port_io) {
            sf->primary_category = SEM_CAT_PORT_IO;
            sf->is_hardware = true;
        } else {
            sf->primary_category = SEM_CAT_UNKNOWN;
            sf->is_hardware = false;
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
