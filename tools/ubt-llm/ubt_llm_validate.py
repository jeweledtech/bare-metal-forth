#!/usr/bin/env python3
"""UBT LLM Validation Harness — single-binary classification via DeepSeek V4 Pro.

Calls NVIDIA-hosted DeepSeek-V4-Pro via OpenAI-compatible API to classify
functions in a Windows kernel-mode driver (.sys). Validates JSON output
against a strict schema and produces a diff report comparing LLM findings
with the existing translator's extracted hardware words.

Usage:
    export NVIDIA_API_KEY=nvapi-...
    python3 ubt_llm_validate.py --binary tests/hp_i3/i8042prt.sys
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import jsonschema
from openai import OpenAI
from tabulate import tabulate

import prefilter

SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = SCRIPT_DIR / "schema" / "sys_driver.schema.json"
SYSTEM_PROMPT_PATH = SCRIPT_DIR / "prompts" / "sys_driver.system.md"

# Minimum instruction count to skip thunks (lowered from 8 to catch
# PE32+ HAL wrappers like READ_PORT_UCHAR which are only 3-4 instructions)
MIN_INSTRUCTIONS = 3


def parse_args():
    p = argparse.ArgumentParser(description="UBT LLM Validation Harness")
    p.add_argument(
        "--binary",
        type=Path,
        default=Path.home() / "projects/forthos/test-binaries/i8042prt.sys",
        help="Path to the .sys binary to analyze",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=SCRIPT_DIR / "results",
        help="Output directory for results",
    )
    p.add_argument(
        "--model",
        default="deepseek-ai/deepseek-v4-pro",
        help="Model ID on NVIDIA NIM (default: deepseek-v4-pro, free tier)",
    )
    p.add_argument(
        "--max-functions",
        type=int,
        default=50,
        help="Maximum number of functions to analyze (cost control)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print prompts to stdout without making API calls",
    )
    filter_group = p.add_mutually_exclusive_group()
    filter_group.add_argument(
        "--prefilter",
        action="store_true",
        default=False,
        help="Enable heuristic prefilter to skip non-hardware functions",
    )
    filter_group.add_argument(
        "--no-prefilter",
        action="store_true",
        default=False,
        help="Explicitly disable prefilter (default behavior)",
    )
    return p.parse_args()


def verify_environment():
    """Check NVIDIA_API_KEY is set."""
    key = os.environ.get("NVIDIA_API_KEY")
    if not key:
        print(
            "ERROR: NVIDIA_API_KEY not set.\n"
            "  export NVIDIA_API_KEY=nvapi-...\n"
            "Get a key from https://build.nvidia.com/",
            file=sys.stderr,
        )
        sys.exit(2)
    return key


def verify_binary(path: Path) -> str:
    """Check binary exists and is a PE file. Returns PE type string."""
    if not path.exists():
        print(
            f"ERROR: Binary not found: {path}\n"
            "Copy i8042prt.sys from the HP NTFS image or specify --binary.",
            file=sys.stderr,
        )
        sys.exit(2)

    result = subprocess.run(["file", str(path)], capture_output=True, text=True)
    output = result.stdout.strip()
    if "PE32+" in output:
        return "PE32+"
    elif "PE32" in output:
        return "PE32"
    else:
        print(f"ERROR: Not a PE binary: {output}", file=sys.stderr)
        sys.exit(2)


def disassemble(binary: Path, out_dir: Path) -> str:
    """Run objdump and cache result. Returns disassembly text."""
    cache_path = out_dir / f"{binary.name}.disasm.txt"
    if cache_path.exists():
        print(f"  Using cached disassembly: {cache_path}")
        return cache_path.read_text()

    print(f"  Disassembling {binary.name} with objdump...")
    result = subprocess.run(
        ["objdump", "-d", "-M", "intel", str(binary)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # objdump warnings are OK (ignoring section flags), errors are not
        if not result.stdout.strip():
            print(f"ERROR: objdump failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(2)

    text = result.stdout
    cache_path.write_text(text)
    print(f"  Cached disassembly: {cache_path} ({len(text)} bytes)")
    return text


def split_functions(disasm_text: str) -> list[dict]:
    """Split disassembly into per-function chunks using int3 padding boundaries.

    MSVC-compiled PE binaries pad between functions with CC (int3) bytes.
    We detect runs of 3+ consecutive int3 instructions as function separators.
    Each function gets a synthetic name from its start address.
    """
    lines = disasm_text.split("\n")
    functions = []
    current_lines = []
    current_addr = None
    int3_run = 0

    for line in lines:
        # Match instruction lines: "   1c0001010:  48 89 5c 24 08  mov ..."
        m = re.match(r"\s+([0-9a-f]+):\s+cc\s+int3", line)
        if m:
            int3_run += 1
            continue

        # Non-int3 instruction line
        m_inst = re.match(r"\s+([0-9a-f]+):\s+([0-9a-f]{2}\s)", line)
        if m_inst:
            if int3_run >= 3 and current_lines:
                # End of previous function
                inst_count = sum(
                    1
                    for l in current_lines
                    if re.match(r"\s+[0-9a-f]+:\s+[0-9a-f]{2}", l)
                )
                if inst_count >= MIN_INSTRUCTIONS:
                    functions.append(
                        {
                            "name": f"func_{current_addr}",
                            "addr": current_addr,
                            "text": "\n".join(current_lines),
                            "inst_count": inst_count,
                        }
                    )
                current_lines = []
                current_addr = None

            int3_run = 0
            if current_addr is None:
                current_addr = m_inst.group(1)
            current_lines.append(line)
        elif line.strip() and not line.startswith("Disassembly"):
            # Section headers, etc. — start a new chunk
            if current_lines:
                inst_count = sum(
                    1
                    for l in current_lines
                    if re.match(r"\s+[0-9a-f]+:\s+[0-9a-f]{2}", l)
                )
                if inst_count >= MIN_INSTRUCTIONS:
                    functions.append(
                        {
                            "name": f"func_{current_addr}",
                            "addr": current_addr,
                            "text": "\n".join(current_lines),
                            "inst_count": inst_count,
                        }
                    )
                current_lines = []
                current_addr = None
            int3_run = 0

    # Last function
    if current_lines:
        inst_count = sum(
            1
            for l in current_lines
            if re.match(r"\s+[0-9a-f]+:\s+[0-9a-f]{2}", l)
        )
        if inst_count >= MIN_INSTRUCTIONS:
            functions.append(
                {
                    "name": f"func_{current_addr}",
                    "addr": current_addr,
                    "text": "\n".join(current_lines),
                    "inst_count": inst_count,
                }
            )

    return functions


def open_cache(out_dir: Path, basename: str) -> sqlite3.Connection:
    """Open or create the SQLite response cache."""
    db_path = out_dir / f"{basename}.cache.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS cache (
            sha256 TEXT PRIMARY KEY,
            response TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            status TEXT
        )"""
    )
    conn.commit()
    return conn


def cache_lookup(conn: sqlite3.Connection, sha: str):
    """Return cached (response_json, input_tokens, output_tokens, status) or None."""
    row = conn.execute(
        "SELECT response, input_tokens, output_tokens, status FROM cache WHERE sha256=?",
        (sha,),
    ).fetchone()
    if row:
        return json.loads(row[0]) if row[0] else None, row[1], row[2], row[3]
    return None


def cache_store(conn, sha, response_obj, input_tokens, output_tokens, status):
    conn.execute(
        "INSERT OR REPLACE INTO cache VALUES (?, ?, ?, ?, ?)",
        (
            sha,
            json.dumps(response_obj) if response_obj else None,
            input_tokens,
            output_tokens,
            status,
        ),
    )
    conn.commit()


def strip_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


MAX_RETRIES = 5
INITIAL_BACKOFF = 3  # seconds


def call_llm(
    client: OpenAI,
    model: str,
    system_prompt: str,
    function_text: str,
    pe_type: str,
) -> tuple[dict | None, int, int, str]:
    """Call DeepSeek V4 for one function. Returns (result, in_tok, out_tok, status).

    Retries on 429 (rate limit) with exponential backoff.
    """
    user_msg = f"Binary type: {pe_type}\n\n{function_text}"

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                max_tokens=1024,
                extra_body={
                    "chat_template_kwargs": {
                        "enable_thinking": True,
                        "thinking": True,
                    }
                },
            )
            break
        except Exception as e:
            err_str = str(e)
            if "429" in err_str and attempt < MAX_RETRIES - 1:
                wait = INITIAL_BACKOFF * (2 ** attempt)
                print(f"[429, retry in {wait}s] ", end="", flush=True)
                time.sleep(wait)
                continue
            print(f"    API error: {e}", file=sys.stderr)
            return None, 0, 0, "api_error"

    usage = response.usage
    in_tok = usage.prompt_tokens if usage else 0
    out_tok = usage.completion_tokens if usage else 0

    content = response.choices[0].message.content or ""
    content = strip_fences(content)

    try:
        obj = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"    JSON parse error: {e}", file=sys.stderr)
        print(f"    Raw response: {content[:200]}", file=sys.stderr)
        return None, in_tok, out_tok, "parse_error"

    return obj, in_tok, out_tok, "ok"


def validate_schema(obj: dict, schema: dict) -> bool:
    """Validate a classification object against the JSON schema."""
    try:
        jsonschema.validate(instance=obj, schema=schema)
        return True
    except jsonschema.ValidationError as e:
        print(f"    Schema validation error: {e.message}", file=sys.stderr)
        return False


def load_translator_report(project_root: Path, binary: Path) -> list[dict] | None:
    """Run the deterministic translator's semantic report on the same binary.

    Returns a list of hardware function dicts, or None if the translator
    binary isn't available.
    """
    translator_bin = project_root / "tools" / "translator" / "bin" / "translator"
    if not translator_bin.exists():
        return None
    try:
        result = subprocess.run(
            [str(translator_bin), "-t", "semantic-report", str(binary)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        report = json.loads(result.stdout)
        return report.get("hardware_functions", [])
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def write_diff_report(
    out_dir: Path,
    basename: str,
    results: list[dict],
    total_in_tokens: int,
    total_out_tokens: int,
    translator_hw: list[dict] | None,
    model_used: str,
):
    """Write the markdown diff report with translator comparison."""
    path = out_dir / f"{basename}.diff.md"

    ok_count = sum(1 for r in results if r["status"] == "ok")
    parse_err = sum(1 for r in results if r["status"] == "parse_error")
    schema_err = sum(1 for r in results if r["status"] == "schema_error")
    api_err = sum(1 for r in results if r["status"] == "api_error")
    pf_count = sum(1 for r in results if r["status"] == "prefiltered")
    total = len(results)
    llm_total = total - pf_count
    parse_rate = (ok_count + schema_err) / llm_total * 100 if llm_total else 0
    valid_rate = ok_count / llm_total * 100 if llm_total else 0

    lines = [
        f"# LLM Classification Report: {basename}",
        "",
        f"**Model:** `{model_used}`",
        "",
        "## Run Summary",
        "",
        f"- **Total functions:** {total}",
        f"- **Prefiltered (no LLM call):** {pf_count}",
        f"- **Sent to LLM:** {llm_total}",
        f"- **Successful classifications:** {ok_count}",
        f"- **Parse errors:** {parse_err}",
        f"- **Schema validation errors:** {schema_err}",
        f"- **API errors:** {api_err}",
        f"- **JSON parse rate (LLM only):** {parse_rate:.1f}%",
        f"- **Schema-valid rate (LLM only):** {valid_rate:.1f}%",
        "",
        "## Per-Function Classifications",
        "",
    ]

    # Build table
    table_rows = []
    for r in results:
        if r["status"] == "ok":
            c = r["classification"]
            table_rows.append(
                [
                    r["function_name"],
                    c.get("class", "?"),
                    c.get("io", {}).get("kind", "?"),
                    c.get("io", {}).get("port_or_mmio", ""),
                    c.get("io", {}).get("mechanism", "?"),
                ]
            )
        else:
            table_rows.append([r["function_name"], r["status"], "", "", ""])

    headers = ["Function", "Class", "IO Kind", "Port/MMIO", "Mechanism"]
    lines.append(tabulate(table_rows, headers=headers, tablefmt="github"))
    lines.append("")

    # Hardware IO summary
    hw_funcs = [
        r
        for r in results
        if r["status"] == "ok"
        and r["classification"].get("class") == "HARDWARE_IO"
    ]
    lines.append("## Hardware I/O Functions Found by LLM")
    lines.append("")
    if hw_funcs:
        for r in hw_funcs:
            c = r["classification"]
            io = c.get("io", {})
            lines.append(
                f"- **{r['function_name']}**: {io.get('kind')} "
                f"port={io.get('port_or_mmio')} "
                f"mechanism={io.get('mechanism')} "
                f"— {io.get('evidence', '')}"
            )
    else:
        lines.append("*No HARDWARE_IO functions detected.*")
    lines.append("")

    # Translator comparison — the core deliverable
    lines.append("## Translator Comparison")
    lines.append("")

    if translator_hw is not None:
        # Normalize addresses to lowercase for matching
        translator_addrs = {}
        for f in translator_hw:
            addr = f.get("address", "").lower().replace("0x", "")
            translator_addrs[addr] = f

        llm_addrs = {}
        for r in hw_funcs:
            # func_1c0001260 -> 1c0001260
            addr = r["function_name"].replace("func_", "")
            llm_addrs[addr] = r

        all_addrs = sorted(set(translator_addrs) | set(llm_addrs))

        lines.append(
            f"Deterministic translator found **{len(translator_hw)}** "
            f"hardware functions. LLM found **{len(hw_funcs)}** HARDWARE_IO."
        )
        lines.append("")

        # Side-by-side comparison table
        cmp_rows = []
        agree = 0
        llm_only = 0
        translator_only = 0
        for addr in all_addrs:
            t = translator_addrs.get(addr)
            l = llm_addrs.get(addr)
            t_name = t["name"] if t else ""
            t_class = t["classification"] if t else ""
            l_name = l["function_name"] if l else ""
            l_class = ""
            l_port = ""
            if l:
                c = l["classification"]
                l_class = c.get("class", "")
                l_port = c.get("io", {}).get("port_or_mmio", "") or ""
            if t and l:
                marker = "AGREE"
                agree += 1
            elif l and not t:
                marker = "LLM-only"
                llm_only += 1
            else:
                marker = "Translator-only"
                translator_only += 1
            cmp_rows.append(
                [f"0x{addr}", t_class, l_class, l_port, marker]
            )

        cmp_headers = ["Address", "Translator", "LLM", "Port", "Verdict"]
        lines.append(tabulate(cmp_rows, headers=cmp_headers, tablefmt="github"))
        lines.append("")
        lines.append(
            f"**Summary:** {agree} agree, "
            f"{llm_only} LLM-only, "
            f"{translator_only} translator-only"
        )
        lines.append("")

        # Qualitative analysis
        if llm_only > 0:
            lines.append(
                "### LLM-only findings"
            )
            lines.append("")
            lines.append(
                "These functions were classified HARDWARE_IO by the LLM but "
                "not detected by the deterministic translator's static analysis. "
                "This typically means indirect port I/O through wrapper calls "
                "that the translator cannot trace statically."
            )
            lines.append("")
            for addr in all_addrs:
                if addr in llm_addrs and addr not in translator_addrs:
                    r = llm_addrs[addr]
                    c = r["classification"]
                    io = c.get("io", {})
                    lines.append(
                        f"- **func_{addr}**: port={io.get('port_or_mmio')} "
                        f"mechanism={io.get('mechanism')} "
                        f"— {io.get('evidence', '')}"
                    )
            lines.append("")
    else:
        lines.append(
            "Translator binary not found at `tools/translator/bin/translator` "
            "— run `make -C tools/translator` to build, then re-run."
        )
    lines.append("")

    # Token spend
    total_tokens = total_in_tokens + total_out_tokens
    lines.append("## Token Spend")
    lines.append("")
    lines.append(f"- **Input tokens:** {total_in_tokens:,}")
    lines.append(f"- **Output tokens:** {total_out_tokens:,}")
    lines.append(f"- **Total tokens:** {total_tokens:,}")
    lines.append(f"- **Estimated cost:** trial tier (free)")
    lines.append("")
    if total_tokens > 50_000:
        lines.append(
            "**WARNING:** Total tokens exceed 50K target. "
            "Consider tightening chunking or reducing max-functions."
        )
    else:
        lines.append(
            f"Token spend is within the 50K target ({total_tokens:,}/50,000)."
        )
    lines.append("")

    path.write_text("\n".join(lines))
    print(f"\nDiff report written: {path}")


def main():
    args = parse_args()
    pe_type = verify_binary(args.binary)
    basename = args.binary.name

    use_prefilter = args.prefilter and not args.no_prefilter

    print(f"UBT LLM Validation Harness")
    print(f"  Binary: {args.binary} ({pe_type})")
    print(f"  Model:  {args.model} (NVIDIA NIM)")
    print(f"  Max functions: {args.max_functions}")
    print(f"  Prefilter: {'ON' if use_prefilter else 'OFF'}")
    print(f"  Dry run: {'YES' if args.dry_run else 'no'}")
    print()

    if not args.dry_run:
        api_key = verify_environment()
    else:
        api_key = None

    if use_prefilter:
        prefilter.init(args.binary, pe_type)

    # Ensure output dir
    args.out.mkdir(parents=True, exist_ok=True)

    # Step 1: Disassemble
    print("[1/5] Disassembly")
    disasm_text = disassemble(args.binary, args.out)

    # Step 2: Split into functions
    print("[2/5] Function splitting")
    functions = split_functions(disasm_text)
    print(f"  Found {len(functions)} functions (>= {MIN_INSTRUCTIONS} instructions)")
    functions = functions[: args.max_functions]
    print(f"  Processing {len(functions)} (capped at --max-functions)")
    print()

    # Step 3: Load schema and system prompt
    print("[3/5] Loading schema and prompt")
    schema = json.loads(SCHEMA_PATH.read_text())
    system_prompt = SYSTEM_PROMPT_PATH.read_text().strip()
    print(f"  Schema: {SCHEMA_PATH}")
    print(f"  Prompt: {SYSTEM_PROMPT_PATH}")
    print()

    # Step 4: Process functions
    print("[4/5] Classifying functions")
    client = None
    if not args.dry_run:
        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=api_key,
            timeout=60,
        )
    conn = open_cache(args.out, basename)

    results = []
    total_in_tokens = 0
    total_out_tokens = 0

    prefiltered_count = 0

    for i, func in enumerate(functions):
        sha = hashlib.sha256(func["text"].encode()).hexdigest()
        print(
            f"  [{i+1}/{len(functions)}] {func['name']} "
            f"({func['inst_count']} inst) ",
            end="",
            flush=True,
        )

        # Prefilter gate: skip LLM call for functions with no I/O signal
        if use_prefilter:
            send, reason = prefilter.should_call_llm(func["text"], pe_type)
            if not send:
                prefiltered_count += 1
                print(f"[prefiltered: {reason}]")
                results.append(
                    {
                        "function_name": func["name"],
                        "classification": {
                            "name": "",
                            "class": "OTHER",
                            "io": {
                                "kind": "NONE",
                                "port_or_mmio": None,
                                "mechanism": "NONE",
                                "evidence": f"prefiltered: {reason}",
                            },
                        },
                        "status": "prefiltered",
                    }
                )
                continue

        # Dry-run mode: print prompt and skip API call
        if args.dry_run:
            user_msg = f"Binary type: {pe_type}\n\n{func['text']}"
            print("[dry-run]")
            print(f"--- SYSTEM PROMPT ---\n{system_prompt[:200]}...")
            print(f"--- USER MESSAGE ({len(user_msg)} chars) ---")
            print(user_msg[:300] + "..." if len(user_msg) > 300 else user_msg)
            print("---")
            results.append(
                {
                    "function_name": func["name"],
                    "classification": None,
                    "status": "dry_run",
                }
            )
            continue

        # Check cache (only reuse successes, retry errors)
        cached = cache_lookup(conn, sha)
        if cached is not None:
            obj, in_tok, out_tok, status = cached
            if status in ("ok", "parse_error", "schema_error"):
                print(f"[cached: {status}]")
            else:
                # Retry api_error
                cached = None

        if cached is None:
            obj, in_tok, out_tok, status = call_llm(
                client, args.model, system_prompt, func["text"], pe_type
            )

            # Schema validation
            if status == "ok" and obj is not None:
                if not validate_schema(obj, schema):
                    status = "schema_error"

            cache_store(conn, sha, obj, in_tok, out_tok, status)
            print(f"[{status}, {in_tok}+{out_tok} tokens]")

            # Rate limiting courtesy — 2s between calls for trial tier
            if i < len(functions) - 1:
                time.sleep(2)

        total_in_tokens += in_tok
        total_out_tokens += out_tok

        results.append(
            {
                "function_name": func["name"],
                "classification": obj if status == "ok" else None,
                "status": status,
                "_from_cache": cached is not None,
            }
        )

    conn.close()
    print()

    # Step 5: Write outputs
    print("[5/5] Writing results")

    # JSON results
    json_path = args.out / f"{basename}.json"
    json_path.write_text(json.dumps(results, indent=2))
    print(f"  JSON results: {json_path}")

    # Diff report — compare LLM against deterministic translator
    project_root = SCRIPT_DIR.parent.parent
    translator_hw = load_translator_report(project_root, args.binary)
    if translator_hw is not None:
        print(f"  Translator found {len(translator_hw)} hardware functions")
    else:
        print("  Translator binary not available — skipping comparison")

    # Track which model produced the cached data. If all results are
    # cached, the model flag may differ from what actually ran. Read
    # the model from the cache DB if available, otherwise use the flag.
    model_used = args.model
    cached_count = sum(1 for r in results if r.get("_from_cache"))
    if cached_count == len([r for r in results if r["status"] == "ok"]):
        # All LLM results came from cache — note this in the report
        model_used = f"{args.model} (results from cache)"

    write_diff_report(
        args.out,
        basename,
        results,
        total_in_tokens,
        total_out_tokens,
        translator_hw,
        model_used,
    )

    # Summary
    ok = sum(1 for r in results if r["status"] == "ok")
    pf = sum(1 for r in results if r["status"] == "prefiltered")
    total = len(results)
    llm_sent = total - pf
    total_tokens = total_in_tokens + total_out_tokens
    print(f"\n  Summary: {ok}/{llm_sent} classified via LLM, "
          f"{pf} prefiltered, {total_tokens:,} total tokens")

    # Parse rate check excludes prefiltered functions
    if llm_sent and (ok / llm_sent) < 0.95:
        print(
            f"  WARNING: Parse rate {ok/llm_sent*100:.1f}% is below 95% target",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
