#!/usr/bin/env python3
"""
Validate UBT pipeline against a real Windows/Linux binary.

Usage: python3 tools/validate_real_binary.py <binary> [binary ...]

Runs the translator in multiple modes and checks output plausibility.
Does NOT require the binary to be a driver — works on any PE/ELF/COM.
"""

import subprocess
import sys
import os
import json
import re


TRANSLATOR = os.path.join(os.path.dirname(__file__),
                           'translator', 'bin', 'translator')


def run(args, **kwargs):
    return subprocess.run(args, capture_output=True, text=True, **kwargs)


def validate(binary_path):
    name = os.path.basename(binary_path)
    print(f"\n{'=' * 60}")
    print(f"  Validating: {name}")
    print(f"  Path: {binary_path}")
    print(f"{'=' * 60}")

    if not os.path.exists(binary_path):
        print(f"  ERROR: file not found")
        return False

    checks_pass = 0
    checks_total = 0

    def check(label, ok, detail=""):
        nonlocal checks_pass, checks_total
        checks_total += 1
        status = "PASS" if ok else "WARN"
        if ok:
            checks_pass += 1
        msg = f"  {status}: {label}"
        if detail:
            msg += f"  ({detail})"
        print(msg)
        return ok

    # 1. Disassembly
    r = run([TRANSLATOR, '-t', 'disasm', binary_path])
    check('Disassembly succeeds (exit 0)', r.returncode == 0,
          f"exit={r.returncode}" if r.returncode != 0 else
          f"{len(r.stdout)} bytes")
    if r.returncode != 0:
        print(f"    stderr: {r.stderr[:200]}")
        return False

    inst_count = r.stdout.count('\n')
    check('Instructions decoded', inst_count > 0,
          f"{inst_count} instructions")

    # 2. Semantic report
    r = run([TRANSLATOR, '-t', 'report', binary_path])
    check('Semantic report succeeds', r.returncode == 0)

    report = None
    if r.returncode == 0:
        try:
            report = json.loads(r.stdout)
            check('Report is valid JSON', True)
        except json.JSONDecodeError as e:
            check('Report is valid JSON', False, str(e))

    if report:
        s = report.get('summary', {})
        hw = s.get('hardware_functions', 0)
        scaf = s.get('scaffolding_functions', 0)
        pio = s.get('port_io_functions', 0)
        imports = s.get('total_imports', 0)
        total = s.get('total_functions', 0)

        check('Has functions', total > 0, f"{total} total")
        check('Hardware functions detected', hw > 0,
              f"{hw} hardware, {scaf} scaffolding")
        check('Port I/O functions', pio > 0, f"{pio} with port I/O")
        check('Imports classified', imports > 0,
              f"{imports} imports") if imports > 0 else None

        fmt = report.get('binary', {}).get('format', '?')
        mach = report.get('binary', {}).get('machine', '?')
        print(f"\n  Binary: {fmt} / {mach}")
        print(f"  Functions: {hw} hardware, {scaf} scaffolding, "
              f"{total} total")
        print(f"  Port I/O: {pio} functions")
        print(f"  Imports: {imports}")

    # 3. Forth codegen
    r = run([TRANSLATOR, '-t', 'forth', binary_path])
    check('Forth codegen succeeds', r.returncode == 0,
          f"{len(r.stdout)} bytes" if r.returncode == 0 else
          f"exit={r.returncode}")

    if r.returncode == 0 and r.stdout:
        forth = r.stdout
        has_port = bool(re.search(
            r'INB|OUTB|INW|OUTW|INL|OUTL|C@-PORT|C!-PORT|PORT', forth))
        has_vocab = 'VOCABULARY' in forth or 'CATALOG' in forth
        has_defs = 'CONSTANT' in forth or ': ' in forth

        check('Forth has port references', has_port)
        check('Forth has vocabulary header', has_vocab)
        check('Forth has definitions', has_defs)

        # Extract port constants
        ports = re.findall(
            r'([0-9A-Fa-f]+)\s+CONSTANT\s+(\S+)', forth)
        if ports:
            print(f"\n  Constants found:")
            for val, name in ports[:10]:
                print(f"    {val} CONSTANT {name}")
            if len(ports) > 10:
                print(f"    ... and {len(ports) - 10} more")

    # 4. Line length check (block-safe?)
    if r.returncode == 0 and r.stdout:
        long_lines = sum(1 for line in r.stdout.split('\n')
                         if len(line) > 64)
        check('All Forth lines <= 64 chars (block-safe)',
              long_lines == 0,
              f"{long_lines} long lines" if long_lines > 0 else "")

    print(f"\n  Result: {checks_pass}/{checks_total} checks passed")
    return checks_pass == checks_total


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <binary> [binary ...]")
        print(f"\nValidates the UBT pipeline on real binaries.")
        print(f"Translator: {TRANSLATOR}")
        sys.exit(1)

    if not os.path.exists(TRANSLATOR):
        print(f"Error: translator not found at {TRANSLATOR}")
        print(f"Run 'cd tools/translator && make' first.")
        sys.exit(1)

    results = [validate(p) for p in sys.argv[1:]]
    passed = sum(results)
    total = len(results)

    print(f"\n{'=' * 60}")
    print(f"  Overall: {passed}/{total} binaries fully validated")
    print(f"{'=' * 60}")
    sys.exit(0 if all(results) else 1)


if __name__ == '__main__':
    main()
