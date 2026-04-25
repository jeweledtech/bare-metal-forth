# TASK: UBT LLM Heuristic Prefilter

## Purpose

Add a deterministic prefilter that runs before any LLM call. The
prefilter inspects each function's disassembly for hardware-I/O
signals; functions with no signal are auto-classified as OTHER without
calling the API, dramatically reducing token spend.

This is the cost-discipline gate for corpus fanout. We cannot point
the harness at ~97K binaries without it.

## Background

The i8042prt.sys validation run used 143K tokens for 50 functions
(~2.86K per function average). Of those 50 functions, only 3 contained
HARDWARE_IO. The other 47 paid full LLM cost to be classified as
OTHER, IRP_DISPATCH, or DRIVER_ENTRY — none of which require model
judgment to recognize at the level we currently use them.

A deterministic check for `in`/`out` instructions and HAL import
references would have routed those 47 functions to a $0 OTHER
classification, leaving only the 3 HARDWARE_IO candidates plus a small
review sample for the LLM.

## Success criteria

1. New module `tools/ubt-llm/prefilter.py` exposes
   `should_call_llm(function_text, pe_type) -> tuple[bool, str]`
   returning (call_llm_decision, reason).
2. Integration into `ubt_llm_validate.py`: any function where
   `should_call_llm` returns False is recorded with status
   `"prefiltered"`, classification `OTHER`, and zero token spend.
3. On i8042prt.sys with `--max-functions 50`, prefilter selects no
   more than 8-12 functions for LLM analysis (the 3 known
   HARDWARE_IO + a buffer for false positives).
4. The 3 known HARDWARE_IO functions MUST pass the prefilter (zero
   false negatives on hardware I/O). Verify against the cached
   results from the previous run.
5. New CLI flag `--no-prefilter` disables the gate for A/B testing.
6. Token spend on i8042prt.sys with prefilter enabled is under 30K.

## Heuristic rules

A function passes the prefilter (gets sent to the LLM) if ANY of:

- Contains `in al, dx`, `in ax, dx`, `in eax, dx` (any I/O port read).
- Contains `out dx, al`, `out dx, ax`, `out dx, eax` (any I/O port write).
- Contains `mov cr` or `mov ... cr0/cr2/cr3/cr4/cr8` (control register access).
- Contains `rdmsr` / `wrmsr` (MSR access).
- Calls a HAL import: any `call` to an address in the import table whose
  resolved name starts with `READ_PORT_`, `WRITE_PORT_`, `READ_REGISTER_`,
  `WRITE_REGISTER_`, `HalGet`, `HalSet`, `KeStallExecutionProcessor`.
- Function is under 6 instructions AND contains any `in`/`out`/`cr*`
  reference (catches intrinsic thunks before instruction-count filters).
- Contains references to known MMIO base ranges from PCI BAR mapping
  if available (defer this rule — implement only if BAR map is wired in).

A function fails the prefilter (auto-classified OTHER, no LLM call) if
NONE of the above match.

## Implementation notes

- The prefilter operates on the raw objdump output for one function.
  No AST, no decoder — string and regex matching is sufficient.
- For HAL import detection, parse the IAT once at startup
  (`objdump -p BINARY` produces the import table), build a set of HAL
  symbol names, then check each `call` instruction's target address
  against the IAT addresses. Cache the IAT per binary.
- Treat the prefilter as conservative: false positives (sending OTHER
  to the LLM) are cheap; false negatives (skipping HARDWARE_IO) are
  unacceptable. When in doubt, send to the LLM.

## What NOT to do

- Do not use the prefilter to assign class labels other than OTHER.
  The LLM is the source of truth for classification; the prefilter
  only decides whether to call the LLM.
- Do not skip the verification step. The 3 known HARDWARE_IO
  functions in i8042prt.sys are the ground-truth gate.
- Do not enable the prefilter by default until the verification step
  has shown zero false negatives on the i8042prt.sys cache. Default
  to `--prefilter` opt-in for the first run, then flip the default
  after validation.

## Verification

After implementation:

```bash
make ubt-llm-validate-prefilter  # new Makefile target
```

Compare output against the cached non-prefilter results from the
previous run. Specifically check:

- All 3 HARDWARE_IO functions still present in output.
- Total token spend reduced from 143K to under 30K.
- Per-function status distribution: report how many were
  `prefiltered` vs sent to LLM.

## Followup (do not do in this task)

- TASK_UBT_LLM_PROMPT_EXPANSION.md — port the other seven prompts
  (.dll, .exe, .com, .NET, .mui, .inf).
- TASK_UBT_LLM_CORPUS_FANOUT.md — async concurrency, full corpus run.
