/*
 * PE Loader - Redirect Header
 *
 * This header redirects to the full PE loader implementation
 * in tools/translator/include/pe_loader.h.
 *
 * The stub types (pe_image_t) are replaced by the full implementation
 * types (pe_context_t). A typedef preserves backwards compatibility
 * for code referencing pe_image_t.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 */

#ifndef DRV_PE_LOADER_COMPAT_H
#define DRV_PE_LOADER_COMPAT_H

#include "../translator/include/pe_loader.h"

/* Backwards compatibility: pe_image_t was the stub name for pe_context_t */
typedef pe_context_t pe_image_t;

#endif /* DRV_PE_LOADER_COMPAT_H */
