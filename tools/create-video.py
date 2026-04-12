#!/usr/bin/env python3
"""
create-video.py — Convert BMP sequence to ForthOS block format.

Reads a directory of 320x200 8bpp BMP files (numbered 0000.bmp,
0001.bmp, ...) and writes them as consecutive Forth blocks.

Each frame = 63 blocks (64,512 bytes: 64,000 pixels + 512 padding).
BMP rows are flipped (bottom-up in BMP → top-down in framebuffer).

Usage:
  python3 tools/create-video.py <bmp-dir> <blocks.img> <start-block>

Example:
  python3 tools/create-video.py frames/ build/blocks.img 500
"""
import sys
import os
import struct
import glob

FRAME_BLOCKS = 63
BLOCK_SIZE = 1024
FRAME_BYTES = 64000  # 320 * 200
BMP_HEADER_SIZE = 54


def read_bmp_pixels(path):
    """Read 320x200 8bpp BMP, return 64000 bytes top-down."""
    with open(path, 'rb') as f:
        header = f.read(BMP_HEADER_SIZE)
        if header[0:2] != b'BM':
            raise ValueError(f"{path}: not a BMP")
        pixel_offset = struct.unpack_from('<I', header, 10)[0]
        width = struct.unpack_from('<i', header, 18)[0]
        height = struct.unpack_from('<i', header, 22)[0]
        bpp = struct.unpack_from('<H', header, 28)[0]
        if abs(width) != 320 or abs(height) != 200:
            raise ValueError(
                f"{path}: must be 320x200 (got {width}x{height})")
        if bpp != 8:
            raise ValueError(
                f"{path}: must be 8bpp (got {bpp}bpp)")
        f.seek(pixel_offset)
        pixels = f.read(FRAME_BYTES)
        # BMP bottom-up → top-down flip
        rows = [pixels[i * 320:(i + 1) * 320] for i in range(200)]
        if height > 0:
            rows = list(reversed(rows))
        return b''.join(rows)


def write_frame(img_path, start_block, pixels):
    """Write one frame to blocks starting at start_block."""
    padded = pixels + b'\x00' * (
        FRAME_BLOCKS * BLOCK_SIZE - FRAME_BYTES)
    offset = start_block * BLOCK_SIZE
    with open(img_path, 'r+b') as f:
        f.seek(offset)
        f.write(padded)


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    bmp_dir = sys.argv[1]
    img_path = sys.argv[2]
    start_block = int(sys.argv[3])

    bmps = sorted(glob.glob(os.path.join(bmp_dir, '*.bmp')))
    if not bmps:
        print(f"No .bmp files in {bmp_dir}")
        sys.exit(1)

    img_size = os.path.getsize(img_path)
    written = 0

    for i, bmp_path in enumerate(bmps):
        blk = start_block + i * FRAME_BLOCKS
        end = (blk + FRAME_BLOCKS) * BLOCK_SIZE
        if end > img_size:
            print(f"Frame {i}: block {blk} exceeds image. Stop.")
            break
        pixels = read_bmp_pixels(bmp_path)
        write_frame(img_path, blk, pixels)
        print(f"  {i:4d}: {os.path.basename(bmp_path)}"
              f" → blocks {blk}-{blk + FRAME_BLOCKS - 1}")
        written += 1

    print(f"\n{written} frames → block {start_block}")
    print(f"In ForthOS:")
    print(f"  {start_block} VID-START !")
    print(f"  {start_block} {written} VIDEO-PLAY-15")


if __name__ == '__main__':
    main()
