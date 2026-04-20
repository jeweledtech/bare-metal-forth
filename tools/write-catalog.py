#!/usr/bin/env python3
"""
write-catalog.py — Build a vocabulary catalog block and write all .fth files to a block disk.

Scans a directory of .fth vocabulary files, computes block layout, writes a
catalog block (block 1), and writes each vocabulary to its assigned blocks.
Block 0 is reserved for boot info.

Block layout:
    Block 0:  (reserved)
    Block 1:  Vocabulary catalog
    Block 2+: Vocabulary files in alphabetical order

Catalog format (block 1):
    \\ VOCAB-CATALOG
    HARDWARE 2
    SERIAL-16550 5
    ...

Each line is: <VOCAB-NAME> <START-BLOCK>

The vocabulary name is extracted from the CATALOG: line in each .fth file.
If no CATALOG: line exists, the name is derived from the filename.


Usage:
    python3 tools/write-catalog.py <disk-image> <vocab-dir>

Examples:
    python3 tools/write-catalog.py build/blocks.img forth/dict/
"""

import sys
import os
import re

# Import block utilities from write-block.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from importlib.machinery import SourceFileLoader
write_block_mod = SourceFileLoader("write_block",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "write-block.py")).load_module()
lint_mod = SourceFileLoader("lint_forth",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "lint-forth.py")).load_module()

source_to_blocks = write_block_mod.source_to_blocks
source_to_block = write_block_mod.source_to_block
blocks_needed = write_block_mod.blocks_needed
BLOCK_SIZE = write_block_mod.BLOCK_SIZE


def extract_vocab_name(source_text, filename):
    """Extract vocabulary name from CATALOG: header or derive from filename."""
    match = re.search(r'\\?\s*CATALOG:\s*(\S+)', source_text)
    if match:
        return match.group(1)
    # Derive from filename: hardware.fth -> HARDWARE
    base = os.path.splitext(os.path.basename(filename))[0]
    return base.upper().replace('_', '-')


def scan_vocabs(vocab_dir):
    """Scan directory for .fth files and return vocab info list."""
    vocabs = []

    for fname in sorted(os.listdir(vocab_dir)):
        if not fname.endswith('.fth'):
            continue
        filepath = os.path.join(vocab_dir, fname)
        with open(filepath, 'r') as f:
            source = f.read()

        name = extract_vocab_name(source, fname)
        num_blocks = blocks_needed(source)

        vocabs.append({
            'name': name,
            'filename': fname,
            'filepath': filepath,
            'source': source,
            'blocks_needed': num_blocks,
        })

    return vocabs


LINES_PER_BLOCK = 16  # 16 lines of 64 chars per block
CATALOG_DATA_LINES = LINES_PER_BLOCK - 1  # line 0 is header


def build_catalog_blocks(vocabs, layout):
    """Build catalog as list of block texts (multi-block if needed)."""
    entries = []
    for v in vocabs:
        start_block = layout[v['name']]
        end_block = start_block + v['blocks_needed'] - 1
        entries.append(f"{v['name']} {start_block} {end_block}")

    blocks = []
    for i in range(0, len(entries), CATALOG_DATA_LINES):
        chunk = entries[i:i + CATALOG_DATA_LINES]
        lines = ['\\ VOCAB-CATALOG'] + chunk
        blocks.append('\n'.join(lines))
    return blocks


def build_catalog_text(vocabs, layout):
    """Build the catalog block content (legacy single-block)."""
    blocks = build_catalog_blocks(vocabs, layout)
    return blocks[0] if blocks else '\\ VOCAB-CATALOG'


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    disk_image = sys.argv[1]
    vocab_dir = sys.argv[2]

    if not os.path.isfile(disk_image):
        print(f"Error: disk image '{disk_image}' not found", file=sys.stderr)
        sys.exit(1)

    if not os.path.isdir(vocab_dir):
        print(f"Error: vocab directory '{vocab_dir}' not found", file=sys.stderr)
        sys.exit(1)

    # Scan vocabularies
    vocabs = scan_vocabs(vocab_dir)
    if not vocabs:
        print(f"No .fth files found in {vocab_dir}", file=sys.stderr)
        sys.exit(1)

    # Lint all vocabulary files before writing
    lint_errors = 0
    for v in vocabs:
        issues = lint_mod.lint_fth_file(v['filepath'])
        errors = [i for i in issues if i['level'] == 'ERROR']
        warns = [i for i in issues if i['level'] == 'WARN']
        for e in errors:
            print(lint_mod.format_issue(e))
        lint_errors += len(errors)
        if errors:
            print(f"  Lint FAILED: {v['filename']}")
        else:
            note = f" ({len(warns)} BASE note(s))" if warns else ""
            print(f"  Lint OK: {v['filename']}{note}")
    if lint_errors:
        print(f"\nAborting: {lint_errors} lint error(s). "
              f"Fix before writing catalog.")
        sys.exit(1)

    # Build catalog blocks first to know how many we need
    # Temp layout with block 2 start — will adjust after
    temp_layout = {}
    temp_next = 2
    for v in vocabs:
        temp_layout[v['name']] = temp_next
        temp_next += v['blocks_needed']
    cat_blocks = build_catalog_blocks(vocabs, temp_layout)
    num_cat_blocks = len(cat_blocks)

    # Recompute layout: data starts after catalog blocks
    # Block 0 = reserved, blocks 1..N = catalog, then data
    data_start = 1 + num_cat_blocks
    layout = {}
    next_block = data_start
    for v in vocabs:
        layout[v['name']] = next_block
        next_block += v['blocks_needed']

    # Rebuild catalog with correct block numbers
    cat_blocks = build_catalog_blocks(vocabs, layout)

    image_size = os.path.getsize(disk_image)
    needed_size = next_block * BLOCK_SIZE
    if needed_size > image_size:
        print(f"Error: need {next_block} blocks ({needed_size} bytes) "
              f"but image is {image_size} bytes", file=sys.stderr)
        sys.exit(1)

    with open(disk_image, 'r+b') as f:
        # Write catalog blocks starting at block 1
        for ci, cat_text in enumerate(cat_blocks):
            cat_data = source_to_block(cat_text)
            f.seek((1 + ci) * BLOCK_SIZE)
            f.write(cat_data)

        # Write each vocabulary at its assigned blocks
        for v in vocabs:
            start = layout[v['name']]
            block_list = source_to_blocks(v['source'])
            for i, block_data in enumerate(block_list):
                f.seek((start + i) * BLOCK_SIZE)
                f.write(block_data)

    # Report
    print(f"Vocabulary Catalog written to {disk_image}")
    print(f"  Block 0: (reserved)")
    for ci in range(num_cat_blocks):
        print(f"  Block {1 + ci}: VOCAB-CATALOG ({ci + 1}/{num_cat_blocks})")
    for v in vocabs:
        start = layout[v['name']]
        end = start + v['blocks_needed'] - 1
        if start == end:
            print(f"  Block {start}: {v['name']} ({v['filename']})")
        else:
            print(f"  Blocks {start}-{end}: {v['name']} ({v['filename']}, "
                  f"{v['blocks_needed']} blocks)")
    print(f"  Total: {next_block} blocks used")


if __name__ == '__main__':
    main()
