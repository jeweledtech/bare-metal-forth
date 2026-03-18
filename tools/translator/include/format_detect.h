/* ============================================================================
 * Binary Format Detector
 * ============================================================================
 *
 * Detects the format of a binary file from its header bytes.  Routes the
 * translator pipeline to the correct loader (PE, COM, ELF, .NET notice).
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef FORMAT_DETECT_H
#define FORMAT_DETECT_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

typedef enum {
    BINFMT_UNKNOWN = 0,
    BINFMT_PE_DRIVER,   /* .sys — kernel driver, HAL pattern */
    BINFMT_PE_DLL,      /* .dll — user-space, may have IAT or direct IN/OUT */
    BINFMT_PE_EXE,      /* .exe — user-space executable */
    BINFMT_DOS_COM,     /* .com — flat binary, origin 0x100 */
    BINFMT_ELF,         /* ELF binary (future) */
    BINFMT_DOTNET,      /* PE with CLR header — .NET assembly */
} binary_format_t;

typedef struct {
    binary_format_t format;
    bool            is_64bit;
    bool            is_dotnet;
    const char*     description;  /* human-readable, e.g. "PE32 DLL" */
} format_info_t;

/* Detect binary format from raw bytes.
 * Optionally pass the filename for extension-based hints (NULL ok). */
format_info_t detect_format(const uint8_t* data, size_t size,
                            const char* filename);

/* Return human-readable name for a format enum value. */
const char* binfmt_name(binary_format_t fmt);

#endif /* FORMAT_DETECT_H */
