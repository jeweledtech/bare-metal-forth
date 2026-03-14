/* ============================================================================
 * CIL Semantic Classifier — .NET Method Classification
 * ============================================================================
 *
 * Classifies .NET methods as payload (hardware-relevant) or scaffolding
 * (security checks, remoting, enterprise services) using namespace-prefix
 * matching and instruction-level body analysis.
 *
 * The goal: strip security theater from .NET DLLs, keep functional payload.
 * Methods with high payload ratio get emitted as Forth words.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#ifndef CIL_SEMANTIC_H
#define CIL_SEMANTIC_H

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdio.h>
#include "cil_decoder.h"

/* ---- Method Classification ---- */

typedef enum {
    CIL_CLASS_UNKNOWN = 0,
    CIL_CLASS_PAYLOAD,          /* hardware/functional code — KEEP */
    CIL_CLASS_SECURITY,         /* System.Security.* — FILTER */
    CIL_CLASS_REMOTING,         /* System.Runtime.Remoting.* — FILTER */
    CIL_CLASS_ENTERPRISE,       /* System.EnterpriseServices.* — FILTER */
    CIL_CLASS_REFLECTION,       /* System.Reflection.* — ambiguous */
    CIL_CLASS_DIAGNOSTICS,      /* System.Diagnostics.* — FILTER */
} cil_method_class_t;

/* ---- Namespace Filter Table Entry ---- */

typedef struct {
    const char*         prefix;
    cil_method_class_t  classification;
    const char*         description;
} cil_ns_entry_t;

/* The built-in namespace filter table */
extern const cil_ns_entry_t CIL_NS_TABLE[];
extern const size_t CIL_NS_TABLE_SIZE;

/* ---- Per-Method Analysis Result ---- */

typedef struct {
    cil_method_class_t  classification;
    uint32_t    payload_insn_count;     /* non-scaffolding instructions */
    uint32_t    scaffold_insn_count;    /* call/callvirt to scaffolding */
    uint32_t    total_insn_count;
    float       payload_ratio;          /* payload / total; 1.0 if total == 0 */
    bool        has_ldsfld;             /* touches static field */
    bool        has_pinvoke_call;       /* calls unmanaged code (P/Invoke) */
} cil_method_analysis_t;

/* ---- Type Resolver Callback ---- */

/* Given a metadata token, return the fully-qualified type namespace.
 * E.g., token 0x0A000003 → "System.Security.Permissions"
 * Returns pointer into strings heap (not allocated). NULL if unresolvable. */
typedef const char* (*cil_type_resolver_t)(uint32_t token, void* userdata);

/* ---- API ---- */

/* Classify a single method by namespace and body analysis.
 * resolver is optional (NULL = less precise classification). */
void cil_classify_method(const cil_method_t* method,
                         cil_type_resolver_t resolver, void* resolver_data,
                         cil_method_analysis_t* out);

/* Classify an array of methods. Returns heap-allocated array. */
cil_method_analysis_t* cil_classify_methods(const cil_method_t* methods,
                                             size_t method_count,
                                             cil_type_resolver_t resolver,
                                             void* resolver_data);

/* Check if a classification is scaffolding (should be filtered) */
static inline bool cil_is_scaffolding(cil_method_class_t cls) {
    return cls >= CIL_CLASS_SECURITY && cls <= CIL_CLASS_DIAGNOSTICS;
}

/* Print classification report for one method */
void cil_print_method_analysis(const cil_method_t* method,
                                const cil_method_analysis_t* analysis,
                                FILE* out);

/* Default payload threshold: methods with payload_ratio >= this are kept */
#define CIL_DEFAULT_PAYLOAD_THRESHOLD 0.5f

#endif /* CIL_SEMANTIC_H */
