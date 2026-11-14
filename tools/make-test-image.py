#!/usr/bin/env python3
"""make-test-image.py - build the in-machine test image (TASK_FORTH_TEST_RUNNER).

test.img = the product image (combined.img), byte for byte, followed by
test blocks. The product part is never rewritten: the tool copies it and
appends. Blocks use the product's own layout (write-block.py: 16 lines of
64 characters per 1024-byte block).

The first test block is a generated banner. When the run reaches it,
it prints TEST-IMAGE and the first 8 hex digits of the product image's
sha256. The run starts with one top-level THRU over the banner and every
source block (printed by the build). The banner must not THRU the rest
itself: a nested LOAD resumes in a buffer the nested THRU has reused
(found 2026-11-13: STACK UNDERFLOW after the RESULT line). A wrong block
number shows up
as a missing or wrong banner, not as silent garbage (the RAM block path
has no upper bound).

Usage:
  make-test-image.py PRODUCT OUT [SOURCE.fth ...]   build, print first block
  make-test-image.py --verify PRODUCT OUT           re-read OUT from disk;
      exit 1 unless its first len(PRODUCT) bytes hash identical to PRODUCT

The first test block number is computed, never hard-coded:
  (len(PRODUCT) - HEADER) / 1024, HEADER = boot sector + padded kernel,
  read from src/kernel/forth.asm (COMBINED_HEADER_SIZE's two terms).
"""
import hashlib
import os
import re
import sys
from importlib.machinery import SourceFileLoader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WB = SourceFileLoader('write_block', os.path.join(ROOT, 'tools', 'write-block.py')).load_module()
BLOCK = WB.BLOCK_SIZE
NESTED_LOADS = {'LOAD', 'THRU', 'LOAD-VOCAB', 'RELOAD-VOCAB'}


def header_size():
    """BOOT_SECTOR_SIZE + KERNEL_PADDED_SIZE, from the kernel source."""
    src = open(os.path.join(ROOT, 'src', 'kernel', 'forth.asm')).read()
    vals = {}
    for name in ('BOOT_SECTOR_SIZE', 'KERNEL_PADDED_SIZE'):
        m = re.search(rf'^{name}\s+equ\s+(0x[0-9A-Fa-f]+|\d+)', src, re.M)
        if not m:
            sys.exit(f'make-test-image: {name} not found in forth.asm')
        vals[name] = int(m.group(1), 0)
    return vals['BOOT_SECTOR_SIZE'] + vals['KERNEL_PADDED_SIZE']


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def first_block(product_len):
    hdr = header_size()
    rest = product_len - hdr
    if rest < 0 or rest % BLOCK:
        sys.exit(f'make-test-image: product is {product_len} B; minus the '
                 f'{hdr} B header that is not a whole number of blocks')
    return rest // BLOCK


def build(product_path, out_path, sources):
    product = open(product_path, 'rb').read()
    first = first_block(len(product))
    tag = sha256(product)[:8]

    src_blocks = []
    for path in sources:
        text = open(path).read()
        # Block format cuts a line at 64 characters with no warning (how
        # a THEN once became THE): refuse instead of truncating.
        for n, ln in enumerate(text.splitlines(), 1):
            if len(ln) > WB.SCREEN_COLS:
                sys.exit(f'make-test-image: {path}:{n} is {len(ln)} '
                         f'characters; a block line holds 64')
            # A load started from block text resumes in a buffer the
            # nested load may have reused (kernel limitation, FUTURE-TODO
            # in the private repo). Test source never loads blocks; the
            # run is one top-level THRU. Comments count too, to keep the
            # check simple and strict.
            hit = NESTED_LOADS & {w.upper() for w in ln.split()}
            if hit:
                sys.exit(f'make-test-image: {path}:{n} uses '
                         f'{" ".join(sorted(hit))}; test source must '
                         f'not load blocks (nested-load limitation)')
        src_blocks += WB.source_to_blocks(text)
    lines = [
        '\\ TEST-IMAGE banner (tools/make-test-image.py, generated)',
        f': TI-BANNER ." TEST-IMAGE {tag}" CR ; TI-BANNER',
    ]
    for ln in lines:
        if len(ln) > WB.SCREEN_COLS:
            sys.exit(f'make-test-image: banner line over 64: {ln!r}')
    banner = WB.source_to_block('\n'.join(lines))

    tmp = out_path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(product)
        f.write(banner)
        for b in src_blocks:
            f.write(b)
    os.replace(tmp, out_path)
    print(f'test image: {out_path}')
    print(f'  product  {len(product)} B sha256 {sha256(product)}')
    print(f'  banner   TEST-IMAGE {tag}')
    print(f'  first test block {first}  (type: DECIMAL {first} {first + len(src_blocks)} THRU)')
    print(f'  source blocks {len(src_blocks)} ({first + 1}..{first + len(src_blocks)})'
          if src_blocks else '  source blocks 0')


def verify(product_path, out_path):
    product = open(product_path, 'rb').read()
    with open(out_path, 'rb') as f:
        head = f.read(len(product))
    want, got = sha256(product), sha256(head)
    if want != got:
        print(f'FAIL: test image product part differs from {product_path}\n'
              f'  product   {want}\n  test.img  {got} (first {len(product)} B)')
        sys.exit(1)
    print(f'OK: test image product part = {product_path} ({want[:16]})')


def main(argv):
    if len(argv) == 3 and argv[0] == '--verify':
        verify(argv[1], argv[2])
    elif len(argv) >= 2 and not argv[0].startswith('-'):
        build(argv[0], argv[1], argv[2:])
    else:
        sys.exit(__doc__)


if __name__ == '__main__':
    main(sys.argv[1:])
