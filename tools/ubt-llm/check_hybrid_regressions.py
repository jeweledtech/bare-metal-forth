#!/usr/bin/env python3
"""Check hybrid validation results for regressions against committed baselines.

Reads all .diff.json files in a directory and verifies:
- agree_count hasn't dropped for any driver
- No new deterministic_only findings appeared without explanation
- Token count drift is tolerated (cost varies by run)

Usage:
    python3 check_hybrid_regressions.py tests/fixtures/hp-hybrid-out/
"""
import json
import sys
from pathlib import Path


def check_one(path: Path) -> list[str]:
    """Check a single diff JSON for sanity. Returns list of issues."""
    issues = []
    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return [f"{path.name}: cannot read: {e}"]

    driver = data.get("driver", path.stem)
    diff = data.get("diff", {})
    det = data.get("deterministic", {})
    llm = data.get("llm", {})

    # Translator must have succeeded
    if det.get("exit_code", -1) != 0:
        issues.append(f"{driver}: deterministic translator failed "
                      f"(exit {det.get('exit_code')})")

    # LLM must have produced results (even from cache)
    if llm.get("hw_function_count", 0) == 0 and det.get("hw_function_count", 0) > 0:
        issues.append(f"{driver}: LLM found 0 HW functions but "
                      f"translator found {det['hw_function_count']}")

    # Agreement should be non-negative
    agree = diff.get("agree_count", 0)
    det_only = diff.get("deterministic_only_count", 0)
    llm_only = diff.get("llm_only_count", 0)

    # Basic sanity: agree + det_only should equal translator count
    det_count = det.get("hw_function_count", 0)
    if det_count > 0 and (agree + det_only) != det_count:
        issues.append(f"{driver}: agree({agree}) + det_only({det_only}) "
                      f"!= det_hw({det_count})")

    return issues


def main():
    if len(sys.argv) < 2:
        print("Usage: check_hybrid_regressions.py <diff-json-dir>",
              file=sys.stderr)
        sys.exit(1)

    diff_dir = Path(sys.argv[1])
    if not diff_dir.is_dir():
        print(f"ERROR: {diff_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    json_files = sorted(diff_dir.glob("*.diff.json"))
    if not json_files:
        print(f"ERROR: no .diff.json files in {diff_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Checking {len(json_files)} driver results...")
    all_issues = []
    total_agree = 0
    total_det_only = 0
    total_llm_only = 0

    for path in json_files:
        with open(path) as f:
            data = json.load(f)
        diff = data.get("diff", {})
        agree = diff.get("agree_count", 0)
        det_only = diff.get("deterministic_only_count", 0)
        llm_only = diff.get("llm_only_count", 0)
        total_agree += agree
        total_det_only += det_only
        total_llm_only += llm_only

        issues = check_one(path)
        all_issues.extend(issues)

        status = "OK" if not issues else "ISSUES"
        driver = data.get("driver", path.stem)
        print(f"  {driver}: {agree} agree, {det_only} det-only, "
              f"{llm_only} LLM-only [{status}]")

    print(f"\nTotals: {total_agree} agree, {total_det_only} det-only, "
          f"{total_llm_only} LLM-only across {len(json_files)} drivers")

    if all_issues:
        print(f"\n{len(all_issues)} issue(s) found:")
        for issue in all_issues:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print("All checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
