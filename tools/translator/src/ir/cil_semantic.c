/* ============================================================================
 * CIL Semantic Classifier Implementation
 * ============================================================================
 *
 * Namespace-prefix table matching (like SEM_API_TABLE for Windows APIs)
 * plus instruction-level body analysis for payload ratio computation.
 *
 * Copyright (c) 2026 Jolly Genius Inc.
 * ============================================================================ */

#define _POSIX_C_SOURCE 200809L

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "cil_semantic.h"

/* ---- Namespace Filter Table ---- */

const cil_ns_entry_t CIL_NS_TABLE[] = {
    { "System.Security",
      CIL_CLASS_SECURITY,
      "CAS demands, permission checks, strong-name verification" },
    { "System.Runtime.Remoting",
      CIL_CLASS_REMOTING,
      "Remoting infrastructure, marshaling" },
    { "System.EnterpriseServices",
      CIL_CLASS_ENTERPRISE,
      "COM+ services, transactions" },
    { "System.Reflection.Emit",
      CIL_CLASS_REFLECTION,
      "Dynamic code generation" },
    { "System.Diagnostics.Trace",
      CIL_CLASS_DIAGNOSTICS,
      "Trace logging" },
    { "System.Diagnostics.EventLog",
      CIL_CLASS_DIAGNOSTICS,
      "Event log" },
    { "System.Diagnostics.Debug",
      CIL_CLASS_DIAGNOSTICS,
      "Debug assertions" },
    { "System.Runtime.InteropServices.ComTypes",
      CIL_CLASS_ENTERPRISE,
      "COM interop type definitions" },
};

const size_t CIL_NS_TABLE_SIZE =
    sizeof(CIL_NS_TABLE) / sizeof(CIL_NS_TABLE[0]);

/* ---- Namespace Classification ---- */

static cil_method_class_t classify_namespace(const char* ns) {
    if (!ns || ns[0] == '\0') return CIL_CLASS_UNKNOWN;

    for (size_t i = 0; i < CIL_NS_TABLE_SIZE; i++) {
        size_t prefix_len = strlen(CIL_NS_TABLE[i].prefix);
        if (strncmp(ns, CIL_NS_TABLE[i].prefix, prefix_len) == 0) {
            /* Match: exact or followed by '.' or end */
            char next = ns[prefix_len];
            if (next == '\0' || next == '.') {
                return CIL_NS_TABLE[i].classification;
            }
        }
    }
    return CIL_CLASS_UNKNOWN;
}

/* Check if an opcode is a call instruction */
static bool is_call_opcode(cil_opcode_t op) {
    return op == CIL_CALL || op == CIL_CALLVIRT ||
           op == CIL_NEWOBJ || op == CIL_CALLI;
}

/* ---- Method Classification ---- */

void cil_classify_method(const cil_method_t* method,
                         cil_type_resolver_t resolver, void* resolver_data,
                         cil_method_analysis_t* out) {
    memset(out, 0, sizeof(*out));

    /* Step 1: Classify by the method's own namespace */
    cil_method_class_t ns_class = classify_namespace(method->type_namespace);
    if (cil_is_scaffolding(ns_class)) {
        /* The entire type is scaffolding — classify the method accordingly */
        out->classification = ns_class;
    }

    /* Step 2: Walk instructions for body-level analysis */
    out->total_insn_count = (uint32_t)method->instruction_count;

    for (size_t i = 0; i < method->instruction_count; i++) {
        const cil_decoded_t* insn = &method->instructions[i];

        if (insn->opcode == CIL_LDSFLD || insn->opcode == CIL_STSFLD ||
            insn->opcode == CIL_LDSFLDA) {
            out->has_ldsfld = true;
        }

        if (is_call_opcode(insn->opcode) &&
            (insn->operand_type == CIL_OPERAND_TOKEN ||
             insn->operand_type == CIL_OPERAND_STRING)) {
            /* Try to resolve the call target's namespace */
            bool is_scaffold_call = false;

            if (resolver) {
                const char* target_ns = resolver(insn->operand.token,
                                                  resolver_data);
                if (target_ns) {
                    cil_method_class_t target_class =
                        classify_namespace(target_ns);
                    if (cil_is_scaffolding(target_class)) {
                        is_scaffold_call = true;
                    }
                }
            }

            if (is_scaffold_call) {
                out->scaffold_insn_count++;
            } else {
                out->payload_insn_count++;
            }
        } else {
            /* Non-call instruction — always payload */
            out->payload_insn_count++;
        }
    }

    /* Step 3: Compute payload ratio */
    if (out->total_insn_count == 0) {
        out->payload_ratio = 1.0f;
    } else {
        out->payload_ratio = (float)out->payload_insn_count /
                             (float)out->total_insn_count;
    }

    /* Step 4: Final classification */
    if (out->classification == CIL_CLASS_UNKNOWN) {
        /* Not pre-classified by namespace — use body analysis */
        if (out->scaffold_insn_count > 0 &&
            out->payload_ratio < CIL_DEFAULT_PAYLOAD_THRESHOLD) {
            out->classification = CIL_CLASS_SECURITY; /* generic scaffolding */
        } else {
            out->classification = CIL_CLASS_PAYLOAD;
        }
    }
}

cil_method_analysis_t* cil_classify_methods(const cil_method_t* methods,
                                             size_t method_count,
                                             cil_type_resolver_t resolver,
                                             void* resolver_data) {
    if (method_count == 0) return NULL;

    cil_method_analysis_t* results = calloc(method_count,
                                             sizeof(cil_method_analysis_t));
    if (!results) return NULL;

    for (size_t i = 0; i < method_count; i++) {
        cil_classify_method(&methods[i], resolver, resolver_data, &results[i]);
    }

    return results;
}

void cil_print_method_analysis(const cil_method_t* method,
                                const cil_method_analysis_t* analysis,
                                FILE* out) {
    const char* class_names[] = {
        [CIL_CLASS_UNKNOWN]    = "UNKNOWN",
        [CIL_CLASS_PAYLOAD]    = "PAYLOAD",
        [CIL_CLASS_SECURITY]   = "SECURITY",
        [CIL_CLASS_REMOTING]   = "REMOTING",
        [CIL_CLASS_ENTERPRISE] = "ENTERPRISE",
        [CIL_CLASS_REFLECTION] = "REFLECTION",
        [CIL_CLASS_DIAGNOSTICS]= "DIAGNOSTICS",
    };

    fprintf(out, "  %-40s %s  ratio=%.2f  (%u/%u insns)%s%s\n",
            method->name ? method->name : "<unnamed>",
            class_names[analysis->classification],
            analysis->payload_ratio,
            analysis->payload_insn_count,
            analysis->total_insn_count,
            analysis->has_ldsfld ? " [ldsfld]" : "",
            analysis->has_pinvoke_call ? " [P/Invoke]" : "");
}
