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


## Prefilter Implementation — 2026-04-26

Commit a610734 adds a deterministic heuristic prefilter
(`tools/ubt-llm/prefilter.py`) that inspects each function's
disassembly for hardware-I/O signals before calling the LLM.
Functions with no signal are auto-classified as OTHER at zero token
cost.

### Validation results on i8042prt.sys (`--prefilter --max-functions 50`)

- **9 functions sent to LLM, 41 prefiltered** (82% reduction)
- **Token spend: 26,589** vs 143,298 unfiltered (~5.4x reduction,
  under the 30K target)
- **All 3 HARDWARE_IO functions caught with zero false negatives**
- 100% JSON parse rate and schema-valid rate on the 9 LLM-sent
  functions

### Rules that fired

| Rule | Hits | Functions |
|------|------|-----------|
| 1+2: `direct_io` | 2 | func_1c0001260 (`in al,dx` thunk), func_1c0001280 (`out dx,al` thunk) |
| 3: `cr_msr_access` | 1 | func_1c00048c4 (reads a control register — false positive, but conservative) |
| 4: `hal_import` | 2 | func_1c0004c28, func_1c0004e90 (both call KeStallExecutionProcessor at IAT 0x1c0011000) |
| 6: `port_load_call_pattern` | 4 | func_1c0002b38 (HARDWARE_IO), func_1c0001880 (IRP_DISPATCH), func_1c0001b80 (OTHER), func_1c000228c (OTHER) |
| 5: `short_io_thunk` | 0 | Redundant with rules 1-2 at current MIN_INSTRUCTIONS=3; included as safety net |

Rule 5 (MMIO BAR mapping) is deferred per spec.

### Key observations

**Rule 4 (hal_import) correctly retained KeStallExecution callers.**
i8042prt.sys imports only one HAL function: `KeStallExecutionProcessor`.
Two functions call it through the IAT.  These are hardware-adjacent
(busy-wait timing loops used alongside port I/O) and correctly sent to
the LLM for judgment rather than auto-classified.

**Rule 6 (port_load_call_pattern) is the critical PE32+ heuristic.**
func_1c0002b38 contains no inline `in`/`out` instructions — it calls
an intermediate dispatch wrapper (`0x1c000501c`) that routes to the
actual I/O thunks through unresolvable indirect function pointers.
Call-graph analysis cannot catch this statically.  The `mov dl,0xNN`
before `call` pattern catches the x64 ABI signature for passing a
port/command byte to `__outbyte` wrappers.  Verified at 6.4% false
positive rate on the 47 non-HARDWARE_IO functions (3/47 false
positives: func_1c0001880, func_1c0001b80, func_1c000228c).

**IAT parsing uses pefile, not objdump regex.**  `pefile.PE` gives
rebased IAT thunk addresses directly (e.g. `0x1c0011000`).  These
match the `# 0x...` address comments in objdump disassembly output
via string-contains on the full function text.

### Operational notes

- **Default is prefilter OFF.**  Opt-in via `--prefilter`.
  `--no-prefilter` explicitly disables for A/B testing.  Per spec,
  the default will flip to ON after further validation on additional
  binaries.
- **Module-level state caveat:** `prefilter.init()` stores IAT data
  in module-level variables.  Not safe for parallel-binary processing
  in the same process.  If corpus fanout needs concurrent binary
  analysis, refactor the state into a context object.
- **Makefile target:** `make ubt-llm-validate-prefilter` runs the
  harness with `--prefilter` against `tests/hp_i3/i8042prt.sys`.


## Format Router Implementation — 2026-04-28

Commit adds `tools/ubt-llm/router.py`: a deterministic magic-byte
router that classifies binaries by format and maps to prompt classes.
No LLM calls.  Uses `pefile` (fast_load) for PE parsing and raw byte
reads for NE/LE/LX/MZ-only/COM/INF detection.

### Distribution check on existing fixtures

```
$ find tools/translator/tests/data tests/hp_i3 tests/fixtures -type f \
    \! -name "*.json" \! -name "*.md" \! -name "*.c" \! -name ".gitignore" | \
    xargs python3 tools/ubt-llm/router.py | \
    python3 -c "import json,sys; from collections import Counter; \
    results=[json.loads(l) for l in sys.stdin]; \
    [print(f'  {f:12s}  {c}') for f,c in sorted(Counter(r['format'] for r in results).items(), key=lambda x:-x[1])]"

  PE32_PLUS     8
  PE32          6
  DOTNET        1
  COM           1
```

Prompt class distribution:

```
  sys_driver    13
  unknown       1
  dotnet        1
  com_dos       1
```

### Observations

- **All 8 HP i3 drivers** (Win10 x64) correctly route to PE32_PLUS /
  sys_driver.
- **All 5 translator test drivers** (ReactOS 32-bit) route to PE32 /
  sys_driver.  `serial16550_synth.sys` routes to PE32 / unknown because
  its synthetic headers have Subsystem=0 (intentionally minimal).
- **test_dotnet.dll** correctly detected via COR20 directory → dotnet.
- **test_port_access.com** (7 bytes, no MZ magic, .com extension) →
  COM / com_dos.
- **No PARSE_ERROR** on any real fixture.  The router handles all
  existing test binaries cleanly.
- **MUI false-positive averted**: Win10 drivers have MUI localization
  resources but also have executable `.text`/`PAGE`/`INIT` sections.
  The router requires BOTH the MUI resource AND no executable sections
  to classify as MUI.

### Test coverage (19/19)

Tests cover: PE32+, PE32, .NET, .COM, INF (synthetic), MZ-only
(synthetic), NE/LE/LX (synthetic), PARSE_ERROR, SHA256 determinism,
NATIVE-subsystem exe routing, negative MUI, and non-binary text files.

**Untested:** Real .mui file detection (positive case) — no fixture
available.  Negative test confirms regular drivers no longer
false-positive.  Re-validate when a real .mui binary becomes available.


## Deterministic Extractors Implementation — 2026-04-28

Three extractors added for formats where parsing is fully
deterministic (no LLM judgment needed):

- `extractors/inf.py` — Windows INF driver installation files
- `extractors/dotnet_meta.py` — .NET assembly metadata via `dnfile`
- `extractors/mui.py` — stub (NotImplementedError, no fixture)

### Validation against System.DirectoryServices.dll

Real .NET assembly (NuGet reference package, 126KB).  Ground-truth
numbers confirmed by manual inspection of dnfile table dumps:

| Field | Value |
|-------|-------|
| Assembly name | System.DirectoryServices |
| Version | 4.0.0.0 |
| Public key token | b03f5f7f11d50a3a |
| Referenced assemblies | 5 (netstandard 2.0, Security.AccessControl 5.0, Security.Principal.Windows 5.0, IO.FileSystem.AccessControl 5.0, Security.Permissions 5.0) |
| Public types | 141 (all in System.DirectoryServices namespace) |
| P/Invoke surface | 0 (reference assembly — ImplMap table absent) |
| Resource streams | 2 (FxResources...SR.resources, ILLink.Substitutions.xml) |
| has_escape_surface | **true** |

### Escape-surface detection mechanism

`has_escape_surface` is derived from **two independent sources**:

1. **AssemblyRef names** — if any referenced assembly's name starts
   with `System.Runtime.InteropServices`, `System.Reflection.Emit`,
   or `System.Diagnostics.Process`.
2. **TypeRef namespaces** — if any type reference's namespace starts
   with one of those same prefixes.

For System.DirectoryServices.dll: all 5 AssemblyRef `escape_surface`
flags are False (none of the referenced assemblies match), but
TypeRef scanning finds `System.Runtime.InteropServices.COMException`
which independently triggers the top-level flag.  This demonstrates
why both sources are needed — checking only AssemblyRefs produces a
false negative here.

### dnfile API quirks (documented in code, summarized here)

These are non-obvious patterns discovered during development that
affect anyone maintaining or extending the .NET extractor:

- **HeapItemString coercion**: Name fields are `HeapItemString`
  objects, not Python str.  Must call `str()` explicitly.
- **TypeNamespace (not Namespace)**: TypeDef/TypeRef attribute for
  namespace is `.TypeNamespace`.  `.Namespace` raises AttributeError
  with a "Did you mean?" hint — unusual for pefile-family libraries.
- **Flags.tdPublic**: TypeDef visibility is checked via bool attributes
  on `ClrTypeAttr` (e.g. `row.Flags.tdPublic`), not via bitmasking
  an integer.
- **PublicKey (not PublicKeyOrToken)**: Despite ECMA-335 naming the
  AssemblyRef column "PublicKeyOrToken", dnfile exposes it as
  `.PublicKey` with a `.value` attribute (bytes).
- **ImplMap/ModuleRef can be None**: When the metadata table doesn't
  exist in the assembly, `pe.net.mdtables.ImplMap` is None (not an
  empty table object).  Must check `is None` before iterating.
- **Public key token derivation**: .NET stores full public keys
  (128+ bytes) in the Assembly table.  Token = last 8 bytes of
  SHA-1(full_key), byte-reversed.  This matches GAC paths and
  `[InternalsVisibleTo]` attributes.

### MUI extractor — deferred

Stub raises `NotImplementedError` with a message directing to
`schema/mui.schema.json`.  The schema documents the expected output
shape (mui_signature, resource_inventory, string_table, message_table,
parent_binary) so the contract is clear for future implementation.

The router classifies MUI binaries correctly (MUI resource + no
executable sections), but calling the extractor will fail fast with
an informative error until a real `.mui` fixture is available for
validation.

### Test coverage (17/17 extractors + 19/19 router = 36/36 total)

| Suite | Tests | Fixture |
|-------|-------|---------|
| INF basic + schema | 2 | Synthetic Realtek-style tempfile |
| INF UTF-16LE encoding | 1 | Synthetic BOM tempfile |
| INF malformed/duplicate | 1 | Synthetic with duplicate keys |
| .NET assembly identity | 3 | System.DirectoryServices.dll |
| .NET assembly refs | 3 | System.DirectoryServices.dll |
| .NET public types | 2 | System.DirectoryServices.dll |
| .NET P/Invoke empty | 1 | System.DirectoryServices.dll |
| .NET escape surface | 1 | System.DirectoryServices.dll |
| .NET resources | 1 | System.DirectoryServices.dll |
| .NET schema validation | 1 | System.DirectoryServices.dll |
| MUI stub | 1 | (any path — verifies NotImplementedError) |

Router tests (19) documented in the "Format Router" section above.
