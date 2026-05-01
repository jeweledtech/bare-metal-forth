#!/usr/bin/env python3
"""Run hybrid (deterministic + LLM) validation on a single HP driver binary.

Produces a diff JSON with three buckets: agree, deterministic_only, llm_only.
Designed to be called in a loop over tests/hp_i3/*.sys.

Usage:
    python3 run_hybrid_hp.py --binary tests/hp_i3/i8042prt.sys \
        --out tests/fixtures/hp-hybrid-out/i8042prt.diff.json
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
TRANSLATOR_BIN = PROJECT_ROOT / "tools" / "translator" / "bin" / "translator"
VALIDATE_SCRIPT = SCRIPT_DIR / "ubt_llm_validate.py"
RESULTS_DIR = SCRIPT_DIR / "results"


def run_translator(binary: Path) -> dict:
    """Run deterministic translator, return result dict."""
    if not TRANSLATOR_BIN.exists():
        return {"exit_code": -1, "hw_function_count": 0, "functions": [],
                "error": "translator binary not found"}
    try:
        result = subprocess.run(
            [str(TRANSLATOR_BIN), "-t", "semantic-report", str(binary)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return {"exit_code": result.returncode, "hw_function_count": 0,
                    "functions": [], "error": result.stderr[:500]}
        report = json.loads(result.stdout)
        hw = report.get("hardware_functions", [])
        return {"exit_code": 0, "hw_function_count": len(hw), "functions": hw}
    except subprocess.TimeoutExpired:
        return {"exit_code": -2, "hw_function_count": 0, "functions": [],
                "error": "timeout"}
    except json.JSONDecodeError as e:
        return {"exit_code": 0, "hw_function_count": 0, "functions": [],
                "error": f"JSON parse error: {e}"}


def run_llm_validation(binary: Path) -> dict:
    """Run LLM validation with prefilter, return result dict.

    If NVIDIA_API_KEY is set, runs the full validation.
    If not set but cached results exist, reuses them.
    """
    basename = binary.name
    json_path = RESULTS_DIR / f"{basename}.json"

    # Try running the validation (may fail if no API key, but cached
    # results from a prior run will still be in the JSON file)
    env = os.environ.copy()
    result = None
    try:
        result = subprocess.run(
            [sys.executable, str(VALIDATE_SCRIPT),
             "--binary", str(binary), "--prefilter"],
            capture_output=True, text=True, timeout=1800, env=env,
        )
    except subprocess.TimeoutExpired:
        pass  # Fall through — check if partial results exist in JSON

    if not json_path.exists():
        rc = result.returncode if result else -1
        err = (result.stderr[:500] if result else "timeout or no result")
        return {"exit_code": rc, "hw_function_count": 0,
                "functions": [], "tokens_used": 0, "api_calls": 0,
                "cache_hits": 0, "prefilter_savings_pct": 0,
                "error": err}

    with open(json_path) as f:
        all_results = json.load(f)

    hw_funcs = [r for r in all_results
                if r.get("status") == "ok"
                and r.get("classification", {}).get("class") == "HARDWARE_IO"]
    prefiltered = sum(1 for r in all_results if r.get("status") == "prefiltered")
    ok = sum(1 for r in all_results if r.get("status") == "ok")
    cached = sum(1 for r in all_results if r.get("_from_cache"))
    total = len(all_results)
    pf_pct = round(prefiltered / total * 100) if total else 0

    # Extract token counts from stdout
    tokens = 0
    if result and result.stdout:
        for line in result.stdout.splitlines():
            if "total tokens" in line:
                parts = line.split(",")
                for p in parts:
                    if "total tokens" in p:
                        tokens = int(p.strip().split()[0].replace(",", ""))

    return {
        "exit_code": result.returncode,
        "hw_function_count": len(hw_funcs),
        "functions": hw_funcs,
        "tokens_used": tokens,
        "api_calls": ok,
        "cache_hits": cached,
        "prefilter_savings_pct": pf_pct,
    }


def normalize_addr(addr_str: str) -> str:
    """Normalize address to lowercase hex without 0x prefix."""
    return addr_str.lower().replace("0x", "").lstrip("0") or "0"


def compute_diff(det: dict, llm: dict) -> dict:
    """Compute agree/det-only/llm-only diff between translator and LLM."""
    det_addrs = {}
    for f in det.get("functions", []):
        addr = normalize_addr(f.get("address", f.get("name", "")))
        det_addrs[addr] = f

    llm_addrs = {}
    for f in llm.get("functions", []):
        name = f.get("function_name", "")
        addr = normalize_addr(name.replace("func_", ""))
        llm_addrs[addr] = f

    all_addrs = sorted(set(det_addrs) | set(llm_addrs))

    agree = []
    det_only = []
    llm_only = []

    for addr in all_addrs:
        d = det_addrs.get(addr)
        l = llm_addrs.get(addr)
        if d and l:
            agree.append({
                "address": f"0x{addr}",
                "det_class": d.get("classification", ""),
                "llm_class": l["classification"]["class"],
                "llm_port": l["classification"]["io"].get("port_or_mmio", ""),
            })
        elif d and not l:
            det_only.append({
                "address": f"0x{addr}",
                "det_class": d.get("classification", ""),
            })
        else:
            io = l["classification"]["io"]
            llm_only.append({
                "address": f"0x{addr}",
                "llm_class": l["classification"]["class"],
                "port": io.get("port_or_mmio", ""),
                "mechanism": io.get("mechanism", ""),
                "evidence": io.get("evidence", ""),
            })

    return {
        "agree_count": len(agree),
        "deterministic_only_count": len(det_only),
        "llm_only_count": len(llm_only),
        "agree": agree,
        "deterministic_only": det_only,
        "llm_only": llm_only,
    }


def main():
    parser = argparse.ArgumentParser(description="Hybrid HP driver validation")
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True,
                        help="Output diff JSON path")
    parser.add_argument("--log", type=Path, default=None,
                        help="Optional log file for subprocess output")
    args = parser.parse_args()

    if not args.binary.exists():
        print(f"ERROR: {args.binary} not found", file=sys.stderr)
        sys.exit(1)

    basename = args.binary.name
    size = args.binary.stat().st_size
    print(f"=== {basename} ({size:,} bytes) ===")

    # Determine PE format
    with open(args.binary, "rb") as f:
        data = f.read(min(1024, size))
    pe_type = "PE32+"
    if len(data) > 0x80:
        import struct
        pe_off = struct.unpack_from("<I", data, 0x3C)[0]
        if pe_off + 6 < len(data):
            magic_off = pe_off + 0x18
            if magic_off + 2 <= len(data):
                opt_magic = struct.unpack_from("<H", data, magic_off)[0]
                pe_type = "PE32+" if opt_magic == 0x20B else "PE32"

    # Step 1: Deterministic translator
    print(f"  [1/2] Deterministic translator...", end=" ", flush=True)
    det = run_translator(args.binary)
    if det["exit_code"] == 0:
        print(f"{det['hw_function_count']} HW functions")
    else:
        print(f"FAILED (exit {det['exit_code']})")

    # Step 2: LLM validation
    print(f"  [2/2] LLM validation (prefilter)...", end=" ", flush=True)
    llm = run_llm_validation(args.binary)
    if llm["hw_function_count"] > 0 or llm["exit_code"] == 0:
        print(f"{llm['hw_function_count']} HARDWARE_IO, "
              f"{llm['tokens_used']:,} tokens "
              f"({llm['cache_hits']} cached)")
    else:
        print(f"FAILED (exit {llm['exit_code']})")

    # Step 3: Compute diff
    diff = compute_diff(det, llm)
    print(f"  Diff: {diff['agree_count']} agree, "
          f"{diff['deterministic_only_count']} det-only, "
          f"{diff['llm_only_count']} LLM-only")

    # Step 4: Write output JSON
    output = {
        "driver": basename,
        "size_bytes": size,
        "format": pe_type,
        "deterministic": {
            "exit_code": det["exit_code"],
            "hw_function_count": det["hw_function_count"],
            "functions": [{"address": f.get("address", ""),
                          "name": f.get("name", ""),
                          "classification": f.get("classification", "")}
                         for f in det.get("functions", [])],
        },
        "llm": {
            "exit_code": llm["exit_code"],
            "tokens_used": llm.get("tokens_used", 0),
            "api_calls": llm.get("api_calls", 0),
            "cache_hits": llm.get("cache_hits", 0),
            "prefilter_savings_pct": llm.get("prefilter_savings_pct", 0),
            "hw_function_count": llm["hw_function_count"],
        },
        "diff": diff,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(output, f, indent=2)
    print(f"  Wrote: {args.out}")

    # Write log if requested
    if args.log:
        with open(args.log, "w") as f:
            f.write(f"Driver: {basename}\n")
            f.write(f"Det HW: {det['hw_function_count']}\n")
            f.write(f"LLM HW: {llm['hw_function_count']}\n")
            f.write(f"Agree: {diff['agree_count']}\n")
            f.write(f"Det-only: {diff['deterministic_only_count']}\n")
            f.write(f"LLM-only: {diff['llm_only_count']}\n")


if __name__ == "__main__":
    main()
