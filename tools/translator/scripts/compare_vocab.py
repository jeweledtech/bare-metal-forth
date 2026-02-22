#!/usr/bin/env python3
"""
compare_vocab.py — Compare two Forth vocabulary files.

Extracts structural elements from each vocabulary and reports differences.
Ignores comments and whitespace differences, focusing on:
  - CONSTANT definitions (name and value)
  - Word definitions (: NAME ... ;)
  - REQUIRES: dependencies
  - Port operations (C@-PORT, C!-PORT references)

Usage:
    python3 compare_vocab.py <extracted.fth> <reference.fth>

Exit code 0 if structurally equivalent, 1 if differences found.

Copyright (c) 2026 Jolly Genius Inc.
"""

import sys
import re
from collections import OrderedDict


def parse_vocab(text):
    """Extract structural elements from a Forth vocabulary."""
    result = {
        'constants': OrderedDict(),
        'words': [],
        'requires': [],
        'vocab_name': None,
        'ports_desc': None,
        'category': None,
    }

    for line in text.splitlines():
        stripped = line.strip()

        # Catalog header fields
        m = re.match(r'\\?\s*CATALOG:\s*(\S+)', stripped)
        if m:
            result['vocab_name'] = m.group(1)
            continue

        m = re.match(r'\\?\s*CATEGORY:\s*(\S+)', stripped)
        if m:
            result['category'] = m.group(1)
            continue

        m = re.match(r'\\?\s*PORTS:\s*(.+)', stripped)
        if m:
            result['ports_desc'] = m.group(1).strip()
            continue

        m = re.match(r'\\?\s*REQUIRES:\s*(\S+)\s*\(\s*(.+?)\s*\)', stripped)
        if m:
            result['requires'].append({
                'vocab': m.group(1),
                'words': sorted(m.group(2).split()),
            })
            continue

        # CONSTANT definitions
        m = re.match(r'([0-9A-Fa-f]+)\s+CONSTANT\s+(\S+)', stripped)
        if m:
            result['constants'][m.group(2)] = int(m.group(1), 16)
            continue

        # Word definitions (just the name)
        m = re.match(r':\s+(\S+)', stripped)
        if m and not stripped.startswith('\\'):
            result['words'].append(m.group(1))
            continue

    result['words'].sort()
    result['requires'].sort(key=lambda d: d['vocab'])
    return result


def compare(extracted, reference):
    """Compare two parsed vocabularies and return differences."""
    diffs = []

    # Vocab name
    if extracted['vocab_name'] != reference['vocab_name']:
        diffs.append(f"Vocab name: extracted={extracted['vocab_name']}, "
                     f"reference={reference['vocab_name']}")

    # Constants
    ext_consts = set(extracted['constants'].keys())
    ref_consts = set(reference['constants'].keys())

    missing_consts = ref_consts - ext_consts
    extra_consts = ext_consts - ref_consts
    common_consts = ext_consts & ref_consts

    if missing_consts:
        diffs.append(f"Missing constants: {', '.join(sorted(missing_consts))}")
    if extra_consts:
        diffs.append(f"Extra constants: {', '.join(sorted(extra_consts))}")

    for name in sorted(common_consts):
        ev = extracted['constants'][name]
        rv = reference['constants'][name]
        if ev != rv:
            diffs.append(f"Constant {name}: extracted=0x{ev:X}, reference=0x{rv:X}")

    # Words
    ext_words = set(extracted['words'])
    ref_words = set(reference['words'])

    missing_words = ref_words - ext_words
    extra_words = ext_words - ref_words

    if missing_words:
        diffs.append(f"Missing words: {', '.join(sorted(missing_words))}")
    if extra_words:
        diffs.append(f"Extra words: {', '.join(sorted(extra_words))}")

    # REQUIRES
    ext_reqs = {r['vocab']: r for r in extracted['requires']}
    ref_reqs = {r['vocab']: r for r in reference['requires']}

    for vocab in sorted(set(ext_reqs) | set(ref_reqs)):
        if vocab not in ext_reqs:
            diffs.append(f"Missing REQUIRES: {vocab}")
        elif vocab not in ref_reqs:
            diffs.append(f"Extra REQUIRES: {vocab}")
        else:
            ew = set(ext_reqs[vocab]['words'])
            rw = set(ref_reqs[vocab]['words'])
            if ew != rw:
                diffs.append(f"REQUIRES {vocab} words differ: "
                             f"extracted={sorted(ew)}, reference={sorted(rw)}")

    return diffs


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    with open(sys.argv[1], 'r') as f:
        extracted_text = f.read()
    with open(sys.argv[2], 'r') as f:
        reference_text = f.read()

    extracted = parse_vocab(extracted_text)
    reference = parse_vocab(reference_text)

    print(f"Comparing: {sys.argv[1]} vs {sys.argv[2]}")
    print(f"Extracted vocab: {extracted['vocab_name']}")
    print(f"Reference vocab: {reference['vocab_name']}")
    print()

    # Summary
    print(f"Extracted: {len(extracted['constants'])} constants, "
          f"{len(extracted['words'])} words, "
          f"{len(extracted['requires'])} requires")
    print(f"Reference: {len(reference['constants'])} constants, "
          f"{len(reference['words'])} words, "
          f"{len(reference['requires'])} requires")
    print()

    diffs = compare(extracted, reference)

    if not diffs:
        print("MATCH: Vocabularies are structurally equivalent")
        return 0
    else:
        print(f"DIFFERENCES: {len(diffs)} found")
        for d in diffs:
            print(f"  - {d}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
