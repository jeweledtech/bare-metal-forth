#!/usr/bin/env python3
"""
disk-survey-pipeline.py — Bridge from DISK-SURVEY output
to translated Forth vocabularies via the UBT translator.

Parses DISK-SURVEY/DRIVER-REPORT network console output,
extracts discovered binaries from a mounted NTFS partition,
runs the translator on each, and assembles the results
into a blocks image.

Usage:
    python3 tools/disk-survey-pipeline.py \
        --survey-output docs/hp-disk-survey-2026-04-13.txt \
        --mount-point /mnt/windows \
        --translator tools/translator/bin/translator \
        --output build/blocks-translated.img \
        [--filter-subsystem driver,native] \
        [--max-binaries 50]
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

# Subsystems considered hardware-relevant
DEFAULT_FILTER = {'driver', 'native'}

# Extensions we translate
BINARY_EXTS = {'.sys', '.dll', '.exe', '.efi', '.drv'}


def parse_survey_output(text):
    """Parse DRIVER-REPORT section of survey output.

    Looks for lines matching:
        filename.ext PE x86|AMD64 driver|GUI|console|native

    Returns list of dicts with keys:
        name, format, arch, subsystem, partition
    """
    results = []
    seen = set()
    partition = None
    in_report = False

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Track partition context
        m = re.match(r'^---\s+NTFS\s+P(\d+)\s+---', line)
        if m:
            partition = int(m.group(1))
            continue

        if 'Binary Report' in line:
            in_report = True
            continue

        if not in_report:
            continue

        # Match: filename PE arch subsystem
        m = re.match(
            r'^(\S+)\s+PE\s+(x86|AMD64|x86-64)\s+'
            r'(driver|GUI|console|native|sub\?)',
            line
        )
        if m:
            name = m.group(1)
            arch = m.group(2)
            subsys = m.group(3)

            # Deduplicate by filename
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)

            results.append({
                'name': name,
                'format': 'PE',
                'arch': arch,
                'subsystem': subsys,
                'partition': partition,
            })

    return results


def filter_binaries(entries, subsystems=None,
                    max_count=None):
    """Filter to interesting binaries."""
    if subsystems is None:
        subsystems = DEFAULT_FILTER

    filtered = [
        e for e in entries
        if e['subsystem'] in subsystems
    ]

    if max_count and len(filtered) > max_count:
        filtered = filtered[:max_count]

    return filtered


def find_binary(mount_point, filename):
    """Find a binary file under mount point.

    Searches common Windows paths first, then
    does a broader find.
    """
    # Common locations
    search_dirs = [
        'Windows/System32/drivers',
        'Windows/System32',
        'Windows/SysWOW64',
        'Windows/WinSxS',
        'Program Files',
        'Program Files (x86)',
    ]

    for d in search_dirs:
        full = os.path.join(mount_point, d)
        if not os.path.isdir(full):
            continue
        for root, dirs, files in os.walk(full):
            for f in files:
                if f.lower() == filename.lower():
                    return os.path.join(root, f)

    return None


def translate_binary(binary_path, translator_bin,
                     output_dir, vocab_name=None):
    """Run translator on a single binary.

    Returns path to .fth file or None on failure.
    """
    if vocab_name is None:
        base = os.path.splitext(
            os.path.basename(binary_path))[0]
        # Clean name for Forth vocabulary
        vocab_name = re.sub(r'[^A-Za-z0-9_-]', '_',
                            base).upper()

    out_path = os.path.join(output_dir,
                            f'{vocab_name}.fth')

    try:
        result = subprocess.run(
            [translator_bin, '-t', 'forth',
             '-n', vocab_name, binary_path],
            capture_output=True, text=True,
            timeout=60
        )
        if result.returncode != 0:
            print(f'  WARN: translator failed on '
                  f'{os.path.basename(binary_path)}: '
                  f'{result.stderr.strip()[:80]}')
            return None

        output = result.stdout
        if not output.strip():
            print(f'  WARN: empty output for '
                  f'{os.path.basename(binary_path)}')
            return None

        with open(out_path, 'w') as f:
            f.write(output)

        return out_path

    except subprocess.TimeoutExpired:
        print(f'  WARN: timeout on '
              f'{os.path.basename(binary_path)}')
        return None
    except Exception as e:
        print(f'  WARN: error on '
              f'{os.path.basename(binary_path)}: {e}')
        return None


def lint_fth(fth_path, lint_script=None):
    """Check a .fth file for 64-char line compliance."""
    if lint_script is None:
        lint_script = os.path.join(
            os.path.dirname(__file__), 'lint-forth.py')

    if not os.path.exists(lint_script):
        return True  # Skip if linter not found

    result = subprocess.run(
        [sys.executable, lint_script, fth_path],
        capture_output=True, text=True
    )
    return 'error' not in result.stdout.lower()


def assemble_blocks(fth_files, base_blocks,
                    output_image):
    """Append translated .fth files to blocks image.

    Copies base_blocks, writes translated vocabs.
    """
    # Copy base image
    shutil.copy2(base_blocks, output_image)

    # Use write-catalog.py's logic indirectly:
    # Create a temp directory with the translated files
    # and run write-catalog on the combined set
    write_catalog = os.path.join(
        os.path.dirname(__file__), 'write-catalog.py')

    if not os.path.exists(write_catalog):
        print('WARN: write-catalog.py not found')
        return False

    # Create temp dir with both existing and new vocabs
    dict_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'forth', 'dict')

    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy existing vocabs
        for f in os.listdir(dict_dir):
            if f.endswith('.fth'):
                shutil.copy2(
                    os.path.join(dict_dir, f),
                    os.path.join(tmpdir, f))

        # Copy translated vocabs
        for fth in fth_files:
            shutil.copy2(fth, tmpdir)

        # Run write-catalog
        result = subprocess.run(
            [sys.executable, write_catalog,
             output_image, tmpdir],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f'WARN: write-catalog failed: '
                  f'{result.stderr.strip()[:200]}')
            return False

        print(result.stdout[-200:])

    return True


def main():
    parser = argparse.ArgumentParser(
        description='DISK-SURVEY to UBT pipeline')
    parser.add_argument(
        '--survey-output', required=True,
        help='Path to DISK-SURVEY capture file')
    parser.add_argument(
        '--mount-point',
        help='Pre-mounted NTFS partition path')
    parser.add_argument(
        '--translator',
        default='tools/translator/bin/translator',
        help='Path to translator binary')
    parser.add_argument(
        '--blocks-base',
        default='build/blocks.img',
        help='Base blocks image to extend')
    parser.add_argument(
        '--output',
        default='build/blocks-translated.img',
        help='Output blocks image path')
    parser.add_argument(
        '--filter-subsystem',
        default='driver,native',
        help='Comma-separated subsystem filter')
    parser.add_argument(
        '--max-binaries', type=int,
        default=50,
        help='Max binaries to translate')
    parser.add_argument(
        '--list-only', action='store_true',
        help='Just parse and list, do not extract')

    args = parser.parse_args()

    # Parse survey output
    print(f'Parsing {args.survey_output}...')
    with open(args.survey_output, 'r',
              errors='replace') as f:
        text = f.read()

    entries = parse_survey_output(text)
    print(f'  Found {len(entries)} classified binaries')

    # Filter
    subsystems = set(
        args.filter_subsystem.split(','))
    filtered = filter_binaries(
        entries, subsystems, args.max_binaries)
    print(f'  {len(filtered)} after filter '
          f'({args.filter_subsystem})')

    if args.list_only:
        for e in filtered:
            print(f'  {e["name"]} '
                  f'{e["arch"]} {e["subsystem"]}')
        return

    if not args.mount_point:
        print('ERROR: --mount-point required')
        sys.exit(1)

    if not os.path.isdir(args.mount_point):
        print(f'ERROR: {args.mount_point} '
              f'not a directory')
        sys.exit(1)

    if not os.path.exists(args.translator):
        print(f'ERROR: translator not found: '
              f'{args.translator}')
        sys.exit(1)

    # Extract and translate
    translated = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, entry in enumerate(filtered):
            name = entry['name']
            print(f'[{i+1}/{len(filtered)}] '
                  f'{name}...',
                  end=' ', flush=True)

            # Find the binary
            path = find_binary(
                args.mount_point, name)
            if path is None:
                print('NOT FOUND')
                continue

            # Translate
            fth = translate_binary(
                path, args.translator, tmpdir)
            if fth is None:
                print('FAILED')
                continue

            # Lint
            if not lint_fth(fth):
                print('LINT FAIL')
                continue

            translated.append(fth)
            print('OK')

        print(f'\nTranslated {len(translated)} '
              f'of {len(filtered)} binaries')

        if not translated:
            print('Nothing to assemble')
            return

        # Assemble into blocks
        print(f'\nAssembling {args.output}...')
        ok = assemble_blocks(
            translated, args.blocks_base,
            args.output)
        if ok:
            print(f'Output: {args.output}')
            sz = os.path.getsize(args.output)
            print(f'Size: {sz:,} bytes')
        else:
            print('Assembly failed')
            sys.exit(1)

    print('\nPipeline complete.')


if __name__ == '__main__':
    main()
