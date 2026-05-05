# TASK: LLM Prompt Refinement — CR8/Control Register Exclusion

**Status:** Queued (after whitepaper ships)
**Priority:** Medium
**Estimated effort:** 30 minutes implementation + re-run time
**Depends on:** REPORT_HYBRID_HP_VALIDATION.md (completed)

---

## Problem

The hybrid UBT-LLM validation (2026-05-05) found 6 false positives across
3 drivers (HDAudBus, pci, usbxhci) where `mov rax/r12, cr8` (IRQL
reads) were classified as `HARDWARE_IO`. CR8 is the x86-64 Task Priority
Register — a CPU control register for interrupt synchronization, not
device I/O. The LLM prompt defines `HARDWARE_IO` broadly enough that
privileged control-register accesses qualify under a generous reading.

## Fix

### 1. Add negative examples to system prompt

**File:** `tools/ubt-llm/system_prompt.txt` (or wherever the prompt lives)

Add to the `HARDWARE_IO` definition:

> **Not HARDWARE_IO:** Accesses to CPU control registers (CR0, CR3, CR4,
> CR8) are CPU-level operations, not device I/O. CR8 reads/writes
> (`mov rax, cr8` / `mov cr8, rax`) are IRQL management
> (KeRaiseIrql/KeLowerIrql). CR3 writes are page-table switches. CR0
> writes are CPU mode changes. Classify these as `OTHER` or a new
> `CPU_CONTROL` class, not `HARDWARE_IO`.

### 2. Optionally add CPU_CONTROL class to taxonomy

Add to the JSON schema's classification enum:

- `CPU_CONTROL` — privileged instructions that modify CPU state (CR0/CR3/
  CR4/CR8, MSR reads/writes via RDMSR/WRMSR, CPUID). Distinct from
  device I/O.

This is optional — classifying CR8 as `OTHER` also works. `CPU_CONTROL`
is more informative for analysis but adds a taxonomy change that the
downstream pipeline would need to handle.

### 3. Consider MSR coverage

`RDMSR`/`WRMSR` (read/write Model-Specific Registers) have the same
ambiguity. Some MSRs are device-related (APIC base, performance counters),
most are CPU configuration. The prompt should note this distinction.

## Validation

1. Re-run the 8-driver HP corpus against the refined prompt.
2. Verify: 0 CR8 false positives (was 6).
3. Verify: i8042prt `0xD4` finding still classified as `HARDWARE_IO`.
4. Verify: serial.sys agreement count unchanged (14/14).
5. Document as "v2 validation" appendix or follow-up post.

## Scope cuts

- ~~Do NOT re-run before whitepaper ships.~~ The current report frames
  the CR8 gap honestly as a "characterized prompt gap" — this is
  actually more publishable than a clean sweep.
- Do NOT change the prefilter. Prefilter coverage is a separate concern.
- Do NOT add interprocedural analysis to the deterministic translator.
  That's a separate task with different complexity.
