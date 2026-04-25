# UBT LLM Validation Harness

Single-binary validation harness for LLM-based Windows driver classification.
Calls NVIDIA-hosted DeepSeek-V4-Pro via OpenAI-compatible API to classify
functions in a `.sys` kernel-mode driver.

## Purpose

Prove the prompt structure, JSON output schema, and validation pipeline work
end-to-end on **one binary** (i8042prt.sys) before scaling to the full corpus.

## Validated against i8042prt.sys

- Functions analyzed: 50 of 187 detected (`--max-functions 50`)
- JSON parse rate: 100%
- Schema-valid rate: 100%
- HARDWARE_IO functions found: 3
  - `func_1c0001260` — `in al, dx` thunk (READ_PORT_UCHAR wrapper, X64_INTRINSIC)
  - `func_1c0001280` — `out dx, al` thunk (WRITE_PORT_UCHAR wrapper, X64_INTRINSIC)
  - `func_1c0002b38` — port 0xD4 load (PS/2 auxiliary device write command)
- IRP_DISPATCH functions found: 3
- Total token spend: ~143K (input + output combined)
- Per-function p50 token spend: ~2K
- Per-function max: ~19K (a 572-instruction function)
- Model: `deepseek-ai/deepseek-v4-pro` via NVIDIA NIM

## Setup

```bash
pip install -r requirements.txt
export NVIDIA_API_KEY=nvapi-...
```

## Usage

```bash
# Default: analyze i8042prt.sys, first 50 functions
python3 ubt_llm_validate.py --binary tests/hp_i3/i8042prt.sys

# Or via Makefile from project root
make ubt-llm-validate
```

### Options

- `--binary PATH` — path to the .sys PE binary (default: test-binaries/i8042prt.sys)
- `--out DIR` — output directory (default: tools/ubt-llm/results/)
- `--max-functions N` — cap on functions to analyze (default: 50)

## Output

- `results/<binary>.json` — array of per-function classification objects
- `results/<binary>.diff.md` — human-readable diff report with token spend
- `results/<binary>.disasm.txt` — cached objdump disassembly
- `results/<binary>.cache.sqlite` — SHA256-keyed response cache (reruns skip cached)

## Architecture

1. **Disassembly**: `objdump -d -M intel` on the PE binary
2. **Function splitting**: Detects int3 (0xCC) padding between MSVC-compiled functions
3. **Classification**: One API call per function, temperature 0, max 1024 tokens
4. **Validation**: JSON parse + jsonschema validation against `schema/sys_driver.schema.json`
5. **Caching**: SHA256 of function text → SQLite cache (idempotent reruns)

## Design Decisions

- **objdump over radare2**: objdump handles PE32+ correctly and is universally available.
  PE binaries lack debug symbols, so functions are identified by int3 padding boundaries
  rather than `<symbol>:` headers.
- **Sequential, not parallel**: One binary, one call at a time. Concurrency belongs in
  the corpus-fanout task.
- **2-second rate limit + exponential backoff**: Courtesy pause between API calls, with
  retry on HTTP 429 (3s, 6s, 12s, 24s, 48s backoff, up to 5 retries).
- **No paid-tier content in prompts**: System prompt is generic driver analysis. User message
  is disassembly of a public Microsoft binary. Nothing proprietary touches the API.

## Known limitations

- **Token budget overshoot** — the 50K target assumed shorter average function size.
  Actual spend was ~143K for 50 functions. Mitigation is in TASK_UBT_LLM_PREFILTER.md.
- **Function splitter uses int3 padding boundaries**, not the .pdata RUNTIME_FUNCTION
  table. The .pdata approach would be more precise but the int3 method matched within
  ~10% of the .pdata count (187 vs ~200) and was sufficient for validation.
- **Trial-tier rate limits** required exponential-backoff retries. Production runs
  should use a paid endpoint or self-host.

## What this is not

This harness is a single-binary validator, not a corpus-fanout pipeline. It exists to
prove the prompt structure and JSON schema on a binary with known ground truth
(i8042prt.sys, MFT record 74,031 on the HP Win10 NTFS partition). Scaling to the full
~97K binary corpus requires concurrency, rate-limit handling, cost controls (see
TASK_UBT_LLM_PREFILTER.md), and a paid-tier endpoint decision. Do not point this script
at the corpus.
