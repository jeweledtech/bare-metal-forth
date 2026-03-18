/* ============================================================================
 * Binary Format Detector
 * ============================================================================
 *
 * Classifies binary files by examining header bytes:
 *   - MZ + PE\0\0 signature → PE family (driver, DLL, EXE, .NET)
 *   - ELF magic → ELF
 *   - Small file with no recognized header → DOS .com
 *   - Otherwise → unknown
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#include "format_detect.h"
#include <string.h>

/* PE COFF characteristics flags */
#define IMAGE_FILE_SYSTEM   0x1000  /* System file (driver) */
#define IMAGE_FILE_DLL      0x2000  /* DLL file */

/* Read a little-endian uint16 from a byte pointer. */
static uint16_t read_u16(const uint8_t* p) {
    return (uint16_t)(p[0] | (p[1] << 8));
}

/* Read a little-endian uint32 from a byte pointer. */
static uint32_t read_u32(const uint8_t* p) {
    return (uint32_t)(p[0] | (p[1] << 8) | (p[2] << 16) | (p[3] << 24));
}

/* Check if filename ends with a given extension (case-insensitive). */
static bool has_extension(const char* filename, const char* ext) {
    if (!filename || !ext) return false;
    size_t flen = strlen(filename);
    size_t elen = strlen(ext);
    if (flen < elen) return false;
    const char* tail = filename + flen - elen;
    for (size_t i = 0; i < elen; i++) {
        char a = tail[i];
        char b = ext[i];
        if (a >= 'A' && a <= 'Z') a += 32;
        if (b >= 'A' && b <= 'Z') b += 32;
        if (a != b) return false;
    }
    return true;
}

format_info_t detect_format(const uint8_t* data, size_t size,
                            const char* filename) {
    format_info_t info = {BINFMT_UNKNOWN, false, false, "unknown"};

    if (!data || size < 2)
        return info;

    /* ---- ELF check: 0x7F 'E' 'L' 'F' ---- */
    if (size >= 4 && data[0] == 0x7F &&
        data[1] == 'E' && data[2] == 'L' && data[3] == 'F') {
        info.format = BINFMT_ELF;
        info.is_64bit = (size >= 5 && data[4] == 2);
        info.description = info.is_64bit ? "ELF64" : "ELF32";
        return info;
    }

    /* ---- MZ check → PE family ---- */
    if (data[0] == 0x4D && data[1] == 0x5A) {
        /* Need at least a DOS header (64 bytes) to read e_lfanew */
        if (size < 64) {
            /* Truncated MZ — could be a tiny .com wrapped in MZ stub */
            info.format = BINFMT_UNKNOWN;
            info.description = "truncated MZ";
            return info;
        }

        uint32_t e_lfanew = read_u32(data + 0x3C);

        /* Validate e_lfanew: must point inside the file with room for
         * PE signature (4) + COFF header (20) + optional header magic (2) */
        if (e_lfanew + 26 > size) {
            /* MZ but no valid PE — could be a DOS .exe (not PE) */
            info.format = BINFMT_UNKNOWN;
            info.description = "MZ (no PE)";
            return info;
        }

        uint32_t pe_sig = read_u32(data + e_lfanew);
        if (pe_sig != 0x00004550) {  /* "PE\0\0" */
            info.format = BINFMT_UNKNOWN;
            info.description = "MZ (bad PE sig)";
            return info;
        }

        /* COFF header starts at e_lfanew + 4 */
        const uint8_t* coff = data + e_lfanew + 4;
        uint16_t machine = read_u16(coff + 0);
        uint16_t characteristics = read_u16(coff + 18);

        /* Optional header magic (right after COFF header at offset 20) */
        uint16_t opt_size = read_u16(coff + 16);
        const uint8_t* opt_hdr = coff + 20;
        uint16_t opt_magic = 0;
        if (opt_size >= 2)
            opt_magic = read_u16(opt_hdr);

        info.is_64bit = (machine == 0x8664 || opt_magic == 0x20B);

        /* Check CLR data directory (entry 14) for .NET */
        bool has_clr = false;
        if (opt_magic == 0x10B && opt_size >= 128) {
            /* PE32: data dirs start at opt_hdr + 96 */
            uint32_t num_dirs = read_u32(opt_hdr + 92);
            if (num_dirs > 14) {
                const uint8_t* clr_dir = opt_hdr + 96 + 14 * 8;
                if (clr_dir + 8 <= data + size) {
                    uint32_t clr_rva = read_u32(clr_dir);
                    uint32_t clr_sz = read_u32(clr_dir + 4);
                    has_clr = (clr_rva != 0 && clr_sz != 0);
                }
            }
        } else if (opt_magic == 0x20B && opt_size >= 128) {
            /* PE32+: data dirs start at opt_hdr + 112 */
            uint32_t num_dirs = read_u32(opt_hdr + 108);
            if (num_dirs > 14) {
                const uint8_t* clr_dir = opt_hdr + 112 + 14 * 8;
                if (clr_dir + 8 <= data + size) {
                    uint32_t clr_rva = read_u32(clr_dir);
                    uint32_t clr_sz = read_u32(clr_dir + 4);
                    has_clr = (clr_rva != 0 && clr_sz != 0);
                }
            }
        }

        if (has_clr) {
            info.format = BINFMT_DOTNET;
            info.is_dotnet = true;
            info.description = info.is_64bit ? "PE32+ .NET" : "PE32 .NET";
            return info;
        }

        /* Classify PE by characteristics and filename extension */
        bool is_sys = (characteristics & IMAGE_FILE_SYSTEM) != 0;
        bool is_dll = (characteristics & IMAGE_FILE_DLL) != 0;

        /* Extension hint: .sys files are drivers even without SYSTEM flag */
        if (!is_sys && filename)
            is_sys = has_extension(filename, ".sys");

        if (is_sys) {
            info.format = BINFMT_PE_DRIVER;
            info.description = info.is_64bit ? "PE32+ driver" : "PE32 driver";
        } else if (is_dll) {
            info.format = BINFMT_PE_DLL;
            info.description = info.is_64bit ? "PE32+ DLL" : "PE32 DLL";
        } else {
            info.format = BINFMT_PE_EXE;
            info.description = info.is_64bit ? "PE32+ EXE" : "PE32 EXE";
        }
        return info;
    }

    /* ---- DOS .com: no header, flat binary, max 65280 bytes ---- */
    if (size <= 65280) {
        info.format = BINFMT_DOS_COM;
        info.description = "DOS COM";
        return info;
    }

    /* Too large for .com and no recognized header */
    return info;
}

const char* binfmt_name(binary_format_t fmt) {
    switch (fmt) {
        case BINFMT_UNKNOWN:    return "unknown";
        case BINFMT_PE_DRIVER:  return "PE driver";
        case BINFMT_PE_DLL:     return "PE DLL";
        case BINFMT_PE_EXE:    return "PE EXE";
        case BINFMT_DOS_COM:    return "DOS COM";
        case BINFMT_ELF:        return "ELF";
        case BINFMT_DOTNET:     return ".NET";
    }
    return "unknown";
}
