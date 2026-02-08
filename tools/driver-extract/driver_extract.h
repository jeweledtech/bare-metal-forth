/*
 * Driver Extraction Tool
 * 
 * Extracts hardware manipulation code from Windows drivers (.sys files)
 * and generates portable Forth modules.
 * 
 * The key insight: drivers contain two kinds of code:
 * 1. Windows kernel scaffolding (IRP handling, PnP, power management)
 * 2. Hardware protocol code (port I/O, MMIO, timing)
 * 
 * We extract #2 and replace #1 with our own primitives.
 */

#ifndef DRIVER_EXTRACT_H
#define DRIVER_EXTRACT_H

#include <stdint.h>
#include <stddef.h>
#include "uir.h"
#include "x86_decoder.h"
#include "pe_loader.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================
 * Driver API Categories
 * ============================================================================ */

typedef enum {
    DRV_CAT_UNKNOWN     = 0,
    
    /* Hardware Access - THESE ARE WHAT WE WANT */
    DRV_CAT_PORT_IO     = 0x10,     /* IN/OUT instructions, port functions */
    DRV_CAT_MMIO        = 0x11,     /* Memory-mapped I/O */
    DRV_CAT_DMA         = 0x12,     /* DMA buffer operations */
    DRV_CAT_INTERRUPT   = 0x13,     /* Interrupt handling */
    DRV_CAT_TIMING      = 0x14,     /* Delays and timing */
    DRV_CAT_PCI_CONFIG  = 0x15,     /* PCI configuration space */
    
    /* Windows Scaffolding - FILTER THESE OUT */
    DRV_CAT_IRP         = 0x80,     /* IRP handling */
    DRV_CAT_PNP         = 0x81,     /* Plug and Play */
    DRV_CAT_POWER       = 0x82,     /* Power management */
    DRV_CAT_WMI         = 0x83,     /* WMI */
    DRV_CAT_REGISTRY    = 0x84,     /* Registry access */
    DRV_CAT_MEMORY_MGR  = 0x85,     /* Memory manager calls */
    DRV_CAT_SYNC        = 0x86,     /* Synchronization primitives */
    DRV_CAT_STRING      = 0x87,     /* String/Unicode operations */
    
    /* Hybrid - Need Translation */
    DRV_CAT_OBJECT      = 0xC0,     /* Object manager */
    DRV_CAT_IO_MGR      = 0xC1,     /* I/O manager (some parts useful) */
} drv_category_t;

/* ============================================================================
 * Windows Driver API Recognition Table
 * ============================================================================ */

typedef struct {
    const char*     name;           /* Windows API function name */
    drv_category_t  category;       /* Category */
    const char*     forth_equiv;    /* Forth equivalent (NULL if filtered) */
    const char*     description;    /* Human-readable description */
} drv_api_entry_t;

/* The master API table - populated in driver_extract.c */
extern const drv_api_entry_t DRV_API_TABLE[];
extern const size_t DRV_API_TABLE_SIZE;

/* ============================================================================
 * Extracted Hardware Sequence
 * ============================================================================ */

typedef struct {
    uint64_t        original_addr;  /* Address in original driver */
    drv_category_t  category;       /* Type of hardware access */
    
    /* For PORT I/O */
    uint16_t        port;           /* Port number (if known statically) */
    uint8_t         port_size;      /* 1, 2, or 4 bytes */
    int             is_write;       /* 1=write, 0=read */
    
    /* For MMIO */
    uint64_t        mmio_base;      /* MMIO base address (if known) */
    uint32_t        mmio_offset;    /* Offset from base */
    
    /* For timing */
    uint32_t        delay_us;       /* Microsecond delay */
    
    /* The UIR representation */
    uir_block_t*    uir_block;
    
} drv_hw_sequence_t;

/* ============================================================================
 * Driver Module (Output)
 * ============================================================================ */

typedef struct {
    char*           name;               /* Module name (e.g., "RTL8139") */
    char*           description;        /* Human description */
    char*           vendor;             /* Hardware vendor */
    uint16_t        vendor_id;          /* PCI vendor ID */
    uint16_t        device_id;          /* PCI device ID */
    
    /* Extracted sequences */
    drv_hw_sequence_t** sequences;
    size_t          sequence_count;
    
    /* Generated Forth code */
    char*           forth_source;       /* Complete Forth module source */
    
    /* Required base ports/addresses */
    uint16_t*       required_ports;     /* List of I/O ports used */
    size_t          port_count;
    uint64_t*       required_mmio;      /* List of MMIO regions used */
    size_t          mmio_count;
    
    /* Module dependencies */
    const char**    dependencies;       /* Other modules needed */
    size_t          dep_count;
    
} drv_module_t;

/* ============================================================================
 * Extraction Context
 * ============================================================================ */

typedef struct {
    /* Input */
    const uint8_t*  driver_data;        /* Raw .sys file data */
    size_t          driver_size;
    const char*     driver_path;
    
    /* PE parsing results */
    uint64_t        image_base;
    uint64_t        entry_point;
    
    /* Import analysis */
    struct {
        const char* dll_name;
        const char* func_name;
        uint64_t    address;
        drv_category_t category;
    }* imports;
    size_t          import_count;
    
    /* Decoder */
    x86_decoder_t   decoder;
    
    /* Output */
    drv_module_t*   module;
    
    /* Statistics */
    size_t          total_functions;
    size_t          hw_functions;       /* Functions with hardware access */
    size_t          filtered_functions; /* Functions filtered out */
    
} drv_extract_ctx_t;

/* ============================================================================
 * API Functions
 * ============================================================================ */

/* Initialize extraction context */
int drv_extract_init(drv_extract_ctx_t* ctx);
void drv_extract_cleanup(drv_extract_ctx_t* ctx);

/* Load driver file */
int drv_load_sys(drv_extract_ctx_t* ctx, const char* path);
int drv_load_mem(drv_extract_ctx_t* ctx, const uint8_t* data, size_t size);

/* Analyze driver imports */
int drv_analyze_imports(drv_extract_ctx_t* ctx);

/* Extract hardware sequences */
int drv_extract_hw_sequences(drv_extract_ctx_t* ctx);

/* Recognize instruction patterns */
drv_category_t drv_categorize_instruction(const x86_decoded_t* ins);
drv_category_t drv_categorize_call(drv_extract_ctx_t* ctx, uint64_t target);

/* Generate Forth module */
char* drv_generate_forth(drv_extract_ctx_t* ctx);

/* Generate module header */
char* drv_generate_header(drv_module_t* mod);

/* Write output files */
int drv_write_module(drv_module_t* mod, const char* output_dir);

/* ============================================================================
 * Pattern Recognition
 * ============================================================================ */

/*
 * Recognize common driver patterns and extract the hardware protocol.
 */

/* Detect initialization sequence */
typedef struct {
    uint16_t        port;
    uint8_t         value;
    uint32_t        delay_after_us;
} drv_init_step_t;

int drv_recognize_init_sequence(drv_extract_ctx_t* ctx, 
                                 uint64_t func_addr,
                                 drv_init_step_t** steps,
                                 size_t* step_count);

/* Detect register read/write pattern */
typedef struct {
    const char*     name;           /* Register name if known */
    uint32_t        offset;         /* Offset from base */
    uint8_t         size;           /* Size in bytes */
    int             is_write;
    uint32_t        mask;           /* Bit mask (0xFFFFFFFF if all bits) */
} drv_register_access_t;

int drv_recognize_register_access(drv_extract_ctx_t* ctx,
                                   uint64_t addr,
                                   drv_register_access_t* access);

/* Detect polling loop */
typedef struct {
    uint16_t        port;           /* Port to poll */
    uint32_t        offset;         /* Or MMIO offset */
    uint8_t         mask;           /* Bits to check */
    uint8_t         expected;       /* Expected value */
    uint32_t        timeout_us;     /* Timeout in microseconds */
} drv_poll_pattern_t;

int drv_recognize_poll_loop(drv_extract_ctx_t* ctx,
                             uint64_t addr,
                             drv_poll_pattern_t* pattern);

/* ============================================================================
 * Forth Code Generation Templates
 * ============================================================================ */

/*
 * Templates for generating Forth code from recognized patterns.
 */

/* Generate port read word */
char* drv_gen_port_read(uint16_t port, uint8_t size, const char* name);

/* Generate port write word */
char* drv_gen_port_write(uint16_t port, uint8_t size, const char* name);

/* Generate MMIO read word */
char* drv_gen_mmio_read(uint32_t offset, uint8_t size, const char* name);

/* Generate MMIO write word */
char* drv_gen_mmio_write(uint32_t offset, uint8_t size, const char* name);

/* Generate delay word */
char* drv_gen_delay(uint32_t microseconds, const char* name);

/* Generate polling loop word */
char* drv_gen_poll_loop(const drv_poll_pattern_t* pattern, const char* name);

/* Generate initialization sequence */
char* drv_gen_init_sequence(const drv_init_step_t* steps, 
                            size_t count,
                            const char* name);

#ifdef __cplusplus
}
#endif

#endif /* DRIVER_EXTRACT_H */
