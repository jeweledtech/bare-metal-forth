#!/usr/bin/env python3
"""
End-to-end tests for UBT binary expansion:
- DOS .com file → Forth vocabulary with port constants
- .NET assembly → graceful notice, exit 0
- PE driver → still works (no regression)
"""

import subprocess
import sys
import os

TRANSLATOR = os.path.join(os.path.dirname(__file__),
                          '..', 'tools', 'translator', 'bin', 'translator')
FIXTURES = os.path.join(os.path.dirname(__file__), 'fixtures')

tests_run = 0
tests_passed = 0

def run_translator(args):
    """Run the translator binary and return (stdout, stderr, returncode)."""
    cmd = [TRANSLATOR] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.stdout, result.stderr, result.returncode

def test(name, fn):
    global tests_run, tests_passed
    tests_run += 1
    try:
        fn()
        tests_passed += 1
        print(f"  TEST: {name:50s} PASS")
    except AssertionError as e:
        print(f"  TEST: {name:50s} FAIL: {e}")
    except Exception as e:
        print(f"  TEST: {name:50s} ERROR: {e}")

# ============================================================================
# COM file tests
# ============================================================================

def test_com_produces_forth():
    """COM file produces Forth output with port constants."""
    com_file = os.path.join(FIXTURES, 'test_port_access.com')
    stdout, stderr, rc = run_translator(['-t', 'forth', com_file])
    assert rc == 0, f"translator failed: {stderr}"
    assert len(stdout) > 0, "empty output"

def test_com_has_port_60():
    """COM output contains port 0x60 as a constant."""
    com_file = os.path.join(FIXTURES, 'test_port_access.com')
    stdout, _, rc = run_translator(['-t', 'forth', com_file])
    assert rc == 0
    # Port 60 should appear as a CONSTANT definition
    assert '60 CONSTANT' in stdout or 'CONSTANT REG-60' in stdout, \
        "port 0x60 constant not found in output"

def test_com_has_port_61():
    """COM output contains port 0x61 as a constant."""
    com_file = os.path.join(FIXTURES, 'test_port_access.com')
    stdout, _, rc = run_translator(['-t', 'forth', com_file])
    assert rc == 0
    assert '61 CONSTANT' in stdout or 'CONSTANT REG-61' in stdout, \
        "port 0x61 constant not found in output"

def test_com_has_vocabulary():
    """COM output has VOCABULARY and DEFINITIONS header."""
    com_file = os.path.join(FIXTURES, 'test_port_access.com')
    stdout, _, rc = run_translator(['-t', 'forth', com_file])
    assert rc == 0
    assert 'VOCABULARY' in stdout, "missing VOCABULARY"
    assert 'DEFINITIONS' in stdout, "missing DEFINITIONS"

def test_com_has_requires():
    """COM output has REQUIRES: HARDWARE dependency."""
    com_file = os.path.join(FIXTURES, 'test_port_access.com')
    stdout, _, rc = run_translator(['-t', 'forth', com_file])
    assert rc == 0
    assert 'REQUIRES: HARDWARE' in stdout, "missing REQUIRES: HARDWARE"

def test_com_disasm():
    """COM file produces disassembly output."""
    com_file = os.path.join(FIXTURES, 'test_port_access.com')
    stdout, _, rc = run_translator(['-t', 'disasm', com_file])
    assert rc == 0
    assert 'IN' in stdout.upper() or 'in' in stdout, "no IN instruction in disasm"

# ============================================================================
# .NET tests
# ============================================================================

def test_dotnet_notice():
    """.NET assembly produces notice, not crash."""
    dll_file = os.path.join(FIXTURES, 'test_dotnet.dll')
    stdout, stderr, rc = run_translator(['-t', 'forth', dll_file])
    assert rc == 0, f"translator crashed on .NET: {stderr}"
    assert '.NET' in stdout, "missing .NET notice in output"

def test_dotnet_no_forth_vocab():
    """.NET assembly does NOT produce Forth vocabulary."""
    dll_file = os.path.join(FIXTURES, 'test_dotnet.dll')
    stdout, _, rc = run_translator(['-t', 'forth', dll_file])
    assert rc == 0
    assert 'VOCABULARY' not in stdout, \
        ".NET should not produce VOCABULARY definition"

# ============================================================================
# PE regression tests
# ============================================================================

def test_pe_driver_still_works():
    """PE driver (.sys) still works through new format dispatch."""
    sys_file = os.path.join(os.path.dirname(__file__), '..',
                            'tools', 'translator', 'tests', 'data',
                            'i8042prt.sys')
    if not os.path.exists(sys_file):
        raise AssertionError("i8042prt.sys not found — skip")
    stdout, stderr, rc = run_translator(['-t', 'forth', sys_file])
    assert rc == 0, f"PE driver failed: {stderr}"
    assert 'VOCABULARY' in stdout, "PE driver should produce vocabulary"
    assert 'I8042PRT' in stdout, "expected I8042PRT vocabulary name"

# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    print("UBT Expansion End-to-End Tests")
    print("==============================")

    # Check translator exists
    if not os.path.exists(TRANSLATOR):
        print(f"ERROR: translator not found at {TRANSLATOR}")
        print("Run: cd tools/translator && make")
        sys.exit(1)

    test("com_produces_forth", test_com_produces_forth)
    test("com_has_port_60", test_com_has_port_60)
    test("com_has_port_61", test_com_has_port_61)
    test("com_has_vocabulary", test_com_has_vocabulary)
    test("com_has_requires", test_com_has_requires)
    test("com_disasm", test_com_disasm)
    test("dotnet_notice", test_dotnet_notice)
    test("dotnet_no_forth_vocab", test_dotnet_no_forth_vocab)
    test("pe_driver_still_works", test_pe_driver_still_works)

    print(f"\nResults: {tests_passed}/{tests_run} passed")
    sys.exit(0 if tests_passed == tests_run else 1)
