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

# Two-store model (TASK M4c): catalog-packed blocks are the CODE store;
# the reserved range below is the mutable DATA store (settings), written
# at runtime through the kernel block-write vector. The packer must never
# place vocabulary source inside it — on disk-boot topologies a settings
# save would otherwise clobber packed source (blocks share one medium).
SETTINGS_RESERVED = range(192, 208)   # 16 blocks: settings + headroom
SET_BLK = 199                         # settings.fth SET-BLK constant
HP_WRITE_CEILING = 910                # blocks 0-910 writable on HP (LBA < 2048)


def load_raw_payloads(specs):
    """Parse --raw NAME=path specs into catalog-placeable payloads.

    A raw payload is a BINARY blob that gets a catalog entry and a
    block slot, but is never interpreted -- the same shape as the
    *-form.fth data blocks, which are found by CATALOG-FIND and read
    by FORM-LOAD rather than THRU'd.

    It must NOT go through source_to_block(): that path opens in text
    mode, encodes ascii/errors='replace' (every byte >127 becomes
    '?'), splits on splitlines() (which breaks on \\r \\x0b \\x0c \\x1c
    \\x1d \\x1e \\x85 as well as \\n), then truncates at 64 and pads
    with spaces. A 512-byte VBR would be silently shredded. Hence the
    separate raw write below.
    """
    payloads = []
    for spec in specs:
        if '=' not in spec:
            print(f"Error: --raw expects NAME=path, got '{spec}'",
                  file=sys.stderr)
            sys.exit(1)
        name, path = spec.split('=', 1)
        if not os.path.isfile(path):
            print(f"Error: raw payload '{name}' not found at {path}",
                  file=sys.stderr)
            sys.exit(1)
        with open(path, 'rb') as f:
            data = f.read()
        if not data:
            print(f"Error: raw payload '{name}' ({path}) is empty.",
                  file=sys.stderr)
            sys.exit(1)
        nblocks = (len(data) + BLOCK_SIZE - 1) // BLOCK_SIZE
        payloads.append({
            'name': name,
            'filename': os.path.basename(path),
            'filepath': path,
            'data': data,
            'blocks_needed': nblocks,
            'raw': True,
        })
    return payloads


def place_vocab(next_block, num_blocks):
    """Start block for a vocab, skipping the reserved settings range.

    A vocab may not start inside, end inside, or span the range."""
    start = next_block
    end = start + num_blocks - 1
    if start < SETTINGS_RESERVED.stop and end >= SETTINGS_RESERVED.start:
        start = SETTINGS_RESERVED.stop
    return start


def check_reservation(vocabs, layout):
    """Build-failing invariants for the two-store layout.

    (1) No vocab occupies the reserved settings range (code store keeps
        out of the data store). NOTE: this is NOT 'packing stays below
        the HP write ceiling' — vocab sources above block 910 are legal
        code-store blocks, read from the RAM memdisk.
    (2) SET_BLK lies inside the reserved range AND at or below the HP
        write ceiling (the data store is reachable through the guard).
    """
    for v in vocabs:
        s = layout[v['name']]
        e = s + v['blocks_needed'] - 1
        if s < SETTINGS_RESERVED.stop and e >= SETTINGS_RESERVED.start:
            print(f"ERROR: {v['name']} (blocks {s}-{e}) overlaps reserved "
                  f"settings range {SETTINGS_RESERVED.start}-"
                  f"{SETTINGS_RESERVED.stop - 1}. Widen the reservation "
                  f"deliberately — never silently.", file=sys.stderr)
            sys.exit(1)
    if SET_BLK not in SETTINGS_RESERVED or SET_BLK > HP_WRITE_CEILING:
        print(f"ERROR: SET_BLK={SET_BLK} outside reserved range "
              f"{SETTINGS_RESERVED.start}-{SETTINGS_RESERVED.stop - 1} "
              f"or above write ceiling {HP_WRITE_CEILING}.",
              file=sys.stderr)
        sys.exit(1)


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

    args = sys.argv[1:]
    raw_specs = []
    positional = []
    i = 0
    while i < len(args):
        if args[i] == '--raw':
            if i + 1 >= len(args):
                print("Error: --raw requires NAME=path", file=sys.stderr)
                sys.exit(1)
            raw_specs.append(args[i + 1])
            i += 2
        else:
            positional.append(args[i])
            i += 1

    if len(positional) < 2:
        print(__doc__)
        sys.exit(1)

    disk_image = positional[0]
    vocab_dir = positional[1]
    payloads = load_raw_payloads(raw_specs)

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

    # Raw payloads are placed and catalogued EXACTLY like vocabs --
    # same place_vocab() skip, same check_reservation() build-fail.
    # They differ only at the write, which is byte-for-byte instead of
    # screen-formatted. Appending them past the layout instead would
    # let a payload land inside SETTINGS_RESERVED, where a runtime
    # settings save would silently overwrite the VBR template.
    #
    # NOT gated on HP_WRITE_CEILING, deliberately: that ceiling is a
    # WRITE constraint (see its comment, and check_reservation's
    # docstring -- "vocab sources above block 910 are legal code-store
    # blocks, read from the RAM memdisk"). A raw payload is read-only
    # data, so it is in the same class as vocab source. Gating it here
    # would fail the build on a condition that is not a defect.
    entries = vocabs + payloads

    # Build catalog blocks first to know how many we need
    # Temp layout with block 2 start — will adjust after
    temp_layout = {}
    temp_next = 2
    for v in entries:
        start = place_vocab(temp_next, v['blocks_needed'])
        temp_layout[v['name']] = start
        temp_next = start + v['blocks_needed']
    cat_blocks = build_catalog_blocks(entries, temp_layout)
    num_cat_blocks = len(cat_blocks)

    # Recompute layout: data starts after catalog blocks
    # Block 0 = reserved, blocks 1..N = catalog, then data
    data_start = 1 + num_cat_blocks
    layout = {}
    next_block = data_start
    for v in entries:
        start = place_vocab(next_block, v['blocks_needed'])
        layout[v['name']] = start
        next_block = start + v['blocks_needed']

    # Rebuild catalog with correct block numbers
    cat_blocks = build_catalog_blocks(entries, layout)

    # Two-store invariants — fail the BUILD, not the bench
    check_reservation(entries, layout)

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

        # Write raw payloads byte-for-byte. TAIL FILL IS ZERO, stated
        # here rather than inherited: vocab blocks pad with SPACES
        # (0x20) because they are Forth screens, and silently
        # inheriting that for binary would put 0x20 in the slack.
        # Harmless for a 512-byte VBR in a 1024-byte block -- nothing
        # reads past 512, and TPL-SUM only sums 512 -- which is
        # exactly why a wrong fill would be invisible HERE and wrong
        # in the next payload that is not block-aligned.
        for p in payloads:
            start = layout[p['name']]
            span = p['blocks_needed'] * BLOCK_SIZE
            padded = p['data'].ljust(span, b'\x00')
            assert len(padded) == span, (p['name'], len(padded), span)
            f.seek(start * BLOCK_SIZE)
            f.write(padded)

    # Report
    print(f"Vocabulary Catalog written to {disk_image}")
    print(f"  Block 0: (reserved)")
    for ci in range(num_cat_blocks):
        print(f"  Block {1 + ci}: VOCAB-CATALOG ({ci + 1}/{num_cat_blocks})")
    reservation_printed = False
    for v in vocabs:
        start = layout[v['name']]
        end = start + v['blocks_needed'] - 1
        if not reservation_printed and start >= SETTINGS_RESERVED.stop:
            print(f"  Blocks {SETTINGS_RESERVED.start}-"
                  f"{SETTINGS_RESERVED.stop - 1}: (reserved: settings, "
                  f"SET-BLK={SET_BLK})")
            reservation_printed = True
        if start == end:
            print(f"  Block {start}: {v['name']} ({v['filename']})")
        else:
            print(f"  Blocks {start}-{end}: {v['name']} ({v['filename']}, "
                  f"{v['blocks_needed']} blocks)")
    if not reservation_printed:
        print(f"  Blocks {SETTINGS_RESERVED.start}-"
              f"{SETTINGS_RESERVED.stop - 1}: (reserved: settings, "
              f"SET-BLK={SET_BLK})")
    for p in payloads:
        start = layout[p['name']]
        end = start + p['blocks_needed'] - 1
        span = 'Block %d' % start if start == end else \
            'Blocks %d-%d' % (start, end)
        print(f"  {span}: {p['name']} (RAW {len(p['data'])} bytes "
              f"from {p['filename']}, zero-filled to "
              f"{p['blocks_needed'] * BLOCK_SIZE})")
    print(f"  Total: {next_block} blocks used")


if __name__ == '__main__':
    main()
