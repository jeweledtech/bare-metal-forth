#!/usr/bin/env python3
"""
write-block.py — Write Forth source into a block disk image.

Each Forth block is 1024 bytes. Traditional Forth screens are 16 lines x 64 chars,
padded with spaces. This tool reads a text file and writes it into a specific
block number in the disk image.

Usage:
    python3 tools/write-block.py <disk-image> <block#> <source-file>

Examples:
    python3 tools/write-block.py build/blocks.img 0 forth/dict/myfile.fth
    python3 tools/write-block.py build/blocks.img 1 -   # Read from stdin

The source file is converted to screen format:
- Lines longer than 64 chars are truncated
- Lines shorter than 64 chars are padded with spaces
- Missing lines (fewer than 16) are filled with spaces
- The result is exactly 1024 bytes written at offset block# * 1024
"""

import sys
import os

BLOCK_SIZE = 1024
SCREEN_LINES = 16
SCREEN_COLS = 64


def source_to_block(source_text):
    """Convert source text to a 1024-byte Forth block (16x64 screen format)."""
    lines = source_text.splitlines()

    block = bytearray(BLOCK_SIZE)
    offset = 0

    for i in range(SCREEN_LINES):
        if i < len(lines):
            line = lines[i]
            # Encode to bytes, truncate to 64 chars
            line_bytes = line.encode('ascii', errors='replace')[:SCREEN_COLS]
            # Write line and pad with spaces
            block[offset:offset + len(line_bytes)] = line_bytes
            for j in range(len(line_bytes), SCREEN_COLS):
                block[offset + j] = ord(' ')
        else:
            # Empty line: fill with spaces
            for j in range(SCREEN_COLS):
                block[offset + j] = ord(' ')
        offset += SCREEN_COLS

    return bytes(block)


def source_to_blocks(source_text):
    """Convert source text to one or more 1024-byte blocks.

    Long files are split across multiple blocks at 16-line boundaries.
    Returns a list of block byte strings.
    """
    lines = source_text.splitlines()
    blocks = []

    for chunk_start in range(0, max(len(lines), 1), SCREEN_LINES):
        chunk_lines = lines[chunk_start:chunk_start + SCREEN_LINES]
        # Pad to exactly SCREEN_LINES
        chunk_text = '\n'.join(chunk_lines)
        blocks.append(source_to_block(chunk_text))

    return blocks


def blocks_needed(source_text):
    """Return how many blocks a source file needs."""
    lines = source_text.splitlines()
    return max(1, (len(lines) + SCREEN_LINES - 1) // SCREEN_LINES)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    disk_image = sys.argv[1]
    block_num = int(sys.argv[2])

    if len(sys.argv) >= 4 and sys.argv[3] != '-':
        source_file = sys.argv[3]
        with open(source_file, 'r') as f:
            source_text = f.read()
    else:
        source_text = sys.stdin.read()

    # Validate
    if block_num < 0:
        print(f"Error: block number must be >= 0 (got {block_num})", file=sys.stderr)
        sys.exit(1)

    image_size = os.path.getsize(disk_image)
    offset = block_num * BLOCK_SIZE

    if offset + BLOCK_SIZE > image_size:
        print(f"Error: block {block_num} (offset {offset}) exceeds image size {image_size}",
              file=sys.stderr)
        sys.exit(1)

    # Convert to blocks (may span multiple blocks for long files)
    block_list = source_to_blocks(source_text)
    num_blocks = len(block_list)

    # Check all blocks fit
    last_offset = (block_num + num_blocks - 1) * BLOCK_SIZE + BLOCK_SIZE
    if last_offset > image_size:
        print(f"Error: blocks {block_num}-{block_num + num_blocks - 1} "
              f"exceed image size {image_size}", file=sys.stderr)
        sys.exit(1)

    with open(disk_image, 'r+b') as f:
        for i, block_data in enumerate(block_list):
            f.seek((block_num + i) * BLOCK_SIZE)
            f.write(block_data)

    # Summary
    lines = source_text.splitlines()
    if num_blocks == 1:
        print(f"Wrote block {block_num} to {disk_image}")
    else:
        print(f"Wrote blocks {block_num}-{block_num + num_blocks - 1} "
              f"({num_blocks} blocks) to {disk_image}")
    print(f"  Source: {len(lines)} lines, {len(source_text)} bytes")
    print(f"  Block offset: {offset} (0x{offset:X})")


if __name__ == '__main__':
    main()
