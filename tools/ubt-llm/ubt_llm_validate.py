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
        "--max-functions",
        type=int,
        default=50,
        help="Maximum number of functions to analyze (cost control)",
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
    system_prompt: str,
    function_text: str,
    pe_type: str,
) -> tuple[dict | None, int, int, str]:
    """Call DeepSeek V4 Pro for one function. Returns (result, in_tok, out_tok, status).

    Retries on 429 (rate limit) with exponential backoff.
    """
    user_msg = f"Binary type: {pe_type}\n\n{function_text}"

    for attempt in range(MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model="deepseek-ai/deepseek-v4-pro",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                max_tokens=1024,
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


def load_translator_extracted(project_root: Path) -> list[str] | None:
    """Load the translator's extracted hardware words for comparison, if available."""
    path = project_root / "translator" / "i8042prt-extracted.txt"
    if path.exists():
        return [l.strip() for l in path.read_text().splitlines() if l.strip()]
    return None


def write_diff_report(
    out_dir: Path,
    basename: str,
    results: list[dict],
    total_in_tokens: int,
    total_out_tokens: int,
    translator_words: list[str] | None,
):
    """Write the markdown diff report."""
    path = out_dir / f"{basename}.diff.md"

    ok_count = sum(1 for r in results if r["status"] == "ok")
    parse_err = sum(1 for r in results if r["status"] == "parse_error")
    schema_err = sum(1 for r in results if r["status"] == "schema_error")
    api_err = sum(1 for r in results if r["status"] == "api_error")
    total = len(results)
    parse_rate = (ok_count + schema_err) / total * 100 if total else 0
    valid_rate = ok_count / total * 100 if total else 0

    lines = [
        f"# LLM Classification Report: {basename}",
        "",
        "## Run Summary",
        "",
        f"- **Total functions analyzed:** {total}",
        f"- **Successful classifications:** {ok_count}",
        f"- **Parse errors:** {parse_err}",
        f"- **Schema validation errors:** {schema_err}",
        f"- **API errors:** {api_err}",
        f"- **JSON parse rate:** {parse_rate:.1f}%",
        f"- **Schema-valid rate:** {valid_rate:.1f}%",
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
    lines.append("## Hardware I/O Functions Found")
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

    # Translator comparison
    lines.append("## Translator Comparison")
    lines.append("")
    if translator_words:
        lines.append(
            "Existing translator extracted the following hardware words:"
        )
        lines.append("")
        for w in translator_words:
            lines.append(f"- `{w}`")
        lines.append("")
        lines.append(
            "Compare the HARDWARE_IO functions above against this list. "
            "Agreements and disagreements should be noted in a manual review."
        )
    else:
        lines.append(
            "No translator output available for diff "
            "(i8042prt-extracted.txt not found) — manual review only."
        )
    lines.append("")

    # Token spend
    total_tokens = total_in_tokens + total_out_tokens
    # NVIDIA trial pricing estimate (rough)
    est_cost = total_tokens * 0.0  # trial tier = free
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
    api_key = verify_environment()
    pe_type = verify_binary(args.binary)
    basename = args.binary.name

    print(f"UBT LLM Validation Harness")
    print(f"  Binary: {args.binary} ({pe_type})")
    print(f"  Model:  deepseek-ai/deepseek-v4-pro (NVIDIA NIM)")
    print(f"  Max functions: {args.max_functions}")
    print()

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
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=api_key,
    )
    conn = open_cache(args.out, basename)

    results = []
    total_in_tokens = 0
    total_out_tokens = 0

    for i, func in enumerate(functions):
        sha = hashlib.sha256(func["text"].encode()).hexdigest()
        print(
            f"  [{i+1}/{len(functions)}] {func['name']} "
            f"({func['inst_count']} inst) ",
            end="",
            flush=True,
        )

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
                client, system_prompt, func["text"], pe_type
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

    # Diff report
    project_root = SCRIPT_DIR.parent.parent
    translator_words = load_translator_extracted(project_root)
    write_diff_report(
        args.out,
        basename,
        results,
        total_in_tokens,
        total_out_tokens,
        translator_words,
    )

    # Summary
    ok = sum(1 for r in results if r["status"] == "ok")
    total = len(results)
    total_tokens = total_in_tokens + total_out_tokens
    print(f"\n  Summary: {ok}/{total} classified, {total_tokens:,} total tokens")

    if total and (ok / total) < 0.95:
        print(
            f"  WARNING: Parse rate {ok/total*100:.1f}% is below 95% target",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
