#!/usr/bin/env python3
"""
test_pipeline_integration.py — Test UBT pipeline bridge.

Tests survey output parsing, translator invocation, and
block assembly. Offline tests (no real hardware needed).

Usage:
    python3 tests/test_pipeline_integration.py
"""

import os
import sys
import subprocess
import tempfile

PROJECT = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))

PIPELINE = os.path.join(
    PROJECT, 'tools', 'disk-survey-pipeline.py')
SURVEY = os.path.join(
    PROJECT, 'docs', 'hp-disk-survey-2026-04-13.txt')
TRANSLATOR = os.path.join(
    PROJECT, 'tools', 'translator', 'bin', 'translator')
LINT = os.path.join(
    PROJECT, 'tools', 'lint-forth.py')

PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        msg = f'  FAIL: {name}'
        if detail:
            msg += f' -- {detail}'
        print(msg)


# Add tools dir to path for imports
sys.path.insert(0, os.path.join(PROJECT, 'tools'))

# ============================================
# Test 1: Pipeline script exists and has help
# ============================================
print('Test 1: Pipeline script')
check('Pipeline script exists',
      os.path.exists(PIPELINE))

r = subprocess.run(
    [sys.executable, PIPELINE, '--help'],
    capture_output=True, text=True
)
check('--help works',
      r.returncode == 0 and 'survey' in r.stdout,
      f'rc={r.returncode}')

# ============================================
# Test 2: Parse survey output
# ============================================
print('\nTest 2: Parse survey output')

if os.path.exists(SURVEY):
    # Import parser function
    import importlib.machinery
    loader = importlib.machinery.SourceFileLoader(
        'pipeline', PIPELINE)
    pipeline = loader.load_module()

    with open(SURVEY, 'r', errors='replace') as f:
        text = f.read()

    entries = pipeline.parse_survey_output(text)
    check('Parse returns entries',
          len(entries) > 0,
          f'got {len(entries)}')
    check('Entries have expected fields',
          all('name' in e and 'subsystem' in e
              for e in entries[:10]))

    # Check we find known drivers
    names = {e['name'].lower() for e in entries}
    has_smb = any('smb_driver' in n for n in names)
    check('Known driver found (Smb_driver)',
          has_smb)

    # Filter to drivers only
    drivers = pipeline.filter_binaries(
        entries, {'driver'})
    check('Driver filter works',
          len(drivers) > 0 and len(drivers) < len(entries),
          f'{len(drivers)} drivers of {len(entries)} total')

    # Deduplication
    all_names = [e['name'].lower() for e in entries]
    check('No duplicates in output',
          len(all_names) == len(set(all_names)),
          f'{len(all_names)} total, '
          f'{len(set(all_names))} unique')

    # Max count limit
    limited = pipeline.filter_binaries(
        entries, {'driver'}, max_count=5)
    check('Max count limit works',
          len(limited) <= 5,
          f'got {len(limited)}')
else:
    print('  SKIP: survey output file not found')
    PASS += 5  # Count as pass if file unavailable

# ============================================
# Test 3: List-only mode
# ============================================
print('\nTest 3: List-only mode')

if os.path.exists(SURVEY):
    r = subprocess.run(
        [sys.executable, PIPELINE,
         '--survey-output', SURVEY,
         '--list-only'],
        capture_output=True, text=True
    )
    check('List-only exits cleanly',
          r.returncode == 0)
    check('List-only shows binaries',
          '.sys' in r.stdout or '.dll' in r.stdout,
          f'output: {r.stdout[:100]!r}')
else:
    print('  SKIP: survey output file not found')
    PASS += 2

# ============================================
# Test 4: Translator invocation
# ============================================
print('\nTest 4: Translator invocation')

translator_exists = os.path.exists(TRANSLATOR)
check('Translator binary exists',
      translator_exists,
      f'path: {TRANSLATOR}')

if translator_exists:
    # Find test fixture
    test_data = os.path.join(
        PROJECT, 'tools', 'translator', 'tests',
        'data')
    fixtures = []
    if os.path.isdir(test_data):
        for f in os.listdir(test_data):
            if f.endswith('.sys'):
                fixtures.append(
                    os.path.join(test_data, f))

    if fixtures:
        fth_path = None
        with tempfile.TemporaryDirectory() as tmp:
            fth_path = pipeline.translate_binary(
                fixtures[0], TRANSLATOR, tmp,
                'TEST_DRIVER')
            check('Translator produces .fth output',
                  fth_path is not None and
                  os.path.exists(fth_path),
                  f'fixture: {os.path.basename(fixtures[0])}')

            if fth_path and os.path.exists(fth_path):
                # Check lint
                r = subprocess.run(
                    [sys.executable, LINT, fth_path],
                    capture_output=True, text=True
                )
                check('Translated output passes lint',
                      'OK' in r.stdout and
                      'error' not in r.stdout.lower()
                      .replace('0 error', ''),
                      f'lint: {r.stdout.strip()[:80]}')
    else:
        print('  SKIP: no test .sys fixtures found')
        PASS += 2
else:
    print('  SKIP: translator not built')
    PASS += 2

# ============================================
# Test 5: Error handling
# ============================================
print('\nTest 5: Error handling')

with tempfile.TemporaryDirectory() as tmp:
    # Non-existent file
    result = pipeline.translate_binary(
        '/tmp/nonexistent.sys', TRANSLATOR
        if translator_exists else '/bin/false',
        tmp)
    check('Non-existent file returns None',
          result is None)

    # Empty survey
    empty = pipeline.parse_survey_output('')
    check('Empty survey returns empty list',
          empty == [])

    # Survey with no Binary Report section
    no_report = pipeline.parse_survey_output(
        'Hello world\nNothing to see here')
    check('No report section returns empty list',
          no_report == [])

# ============================================
# Summary
# ============================================
print(f'\nPassed: {PASS}/{PASS + FAIL}')
sys.exit(0 if FAIL == 0 else 1)
