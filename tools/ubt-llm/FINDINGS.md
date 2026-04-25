# UBT LLM Validation — Findings from i8042prt.sys Run

## 1. PE32+ HAL wrappers are 3-4 instruction thunks

The MSVC compiler inlines `READ_PORT_UCHAR` / `WRITE_PORT_UCHAR` (and
related HAL-equivalent intrinsics) as tiny standalone functions that
contain just the `in al, dx` or `out dx, al` instruction plus a `ret`.

In i8042prt.sys these were:
- `func_1c0001260` — 3 instructions, contains `in al, dx`
- `func_1c0001280` — 4 instructions, contains `out dx, al`

The original validation script filtered functions under 8 instructions
on the assumption they were thunks not worth analyzing. That filter
was wrong: for PE32+ drivers, **the hardware I/O surface lives entirely
in 3-4 instruction thunks**. Lowering `MIN_INSTRUCTIONS` to 3 captured
both port I/O wrappers without adding meaningful noise.

This generalizes: any 64-bit Windows driver compiled with `__inbyte` /
`__outbyte` / `__readcr*` / `__writecr*` intrinsics will exhibit the
same pattern. Import-table detection alone produces empty stubs because
HAL imports were replaced by intrinsics in the x64 ABI shift.

## 2. DeepSeek V4 Pro classification quality on real ground truth

Three findings on i8042prt.sys matched ground truth verifiable by hand:

- The two intrinsic-wrapper thunks were classified HARDWARE_IO with
  mechanism = X64_INTRINSIC. Correct.
- Port 0xD4 (PS/2 auxiliary device write command — documented behavior
  for an i8042 driver) was identified by backward-tracing `mov dl, 0xd4`
  to a subsequent `out dx, al`. Correct.
- IRP dispatch functions were classified IRP_DISPATCH. Plausible by
  function-pointer-table pattern; not independently verified.

The model also did not hallucinate hardware I/O on functions that had
none. 47 of 50 were classified OTHER or non-hardware categories, which
is consistent with i8042prt.sys mostly being IRP plumbing around a
narrow hardware surface.

## 3. Token budget overshoot

Target was 50K tokens for 50 functions. Actual was ~143K (2.86x over).
The single largest function (`func_1c0002d10`, 572 instructions) used
~19K tokens by itself.

This is the binding cost constraint for corpus fanout. Two mitigations
are reasonable:

- **Heuristic prefilter** (planned, see TASK_UBT_LLM_PREFILTER.md):
  skip the LLM call entirely for functions with no hardware I/O
  signal. Estimated 60-80% reduction.
- **Per-function input cap**: truncate functions over N tokens before
  sending. Risk: truncating a function in the middle of a hardware
  access section produces wrong classification. Lower priority.

## 4. Trial-tier rate limits

NVIDIA NIM trial endpoint returned HTTP 429 on roughly 17 of 50
sequential calls during the first run. Mitigation in the harness:
exponential backoff (3s, 6s, 12s, 24s, 48s) with up to 5 retries.

Cache discipline: only `ok` / `parse_error` / `schema_error` results
are cached. `api_error` results are retried on rerun.

## 5. Function-boundary detection: int3 padding vs .pdata

PE32+ binaries with stripped debug symbols have no named functions in
objdump output. Two ways to find function boundaries:

- **int3 (0xCC) padding** between functions — what we used. Simple,
  works with objdump output directly.
- **.pdata section** — contains RUNTIME_FUNCTION entries with start/end
  RVAs for every function. More precise.

The int3 method found 187 functions; .pdata had ~200 entries. The
~13-function gap is mostly leaf functions short enough to share a
padding boundary. For corpus fanout we should switch to .pdata as the
authoritative source.

## 6. The validation pattern itself is reusable

The system-prompt-plus-strict-JSON-schema-plus-validate-on-rehydration
pattern worked end-to-end. JSON parse rate was 100% with no fence
stripping needed. Schema validation caught zero violations. This means
the pattern is suitable for the other seven prompt classes (.dll, .exe,
.com, .NET, .mui, .inf) without structural changes — only the system
prompt and schema need to swap per file class.
