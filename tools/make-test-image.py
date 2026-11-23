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

A suite that needs a block-loaded vocabulary says so with a line
`\\ PRELOAD: NAME`. Test text may not load it (see NESTED_LOADS), so the
build puts `S" NAME" LOAD-VOCAB` in front of the start line, which is
typed at the prompt, not read from a block. The start line is printed
and written to OUT.start; the launcher and the card carry exactly that.
A typed line holds at most TIB_SIZE - 1 characters (src/kernel/forth.asm;
255): a longer one is cut where the kernel stops reading. When the start
line fits it is one line, as it always was. When it does not, OUT.start
holds several lines, typed in order, each after the guest's `ok`: the
LOAD-VOCABs (as many to a line as fit), then the SETUPs, then the THRU.
Any one line still over the limit is refused, and nothing is built.

A suite whose vocabulary needs one word run before its cases (one that
reads blocks, which block text may not) says `\\ SETUP: NAME WORD`. The
build puts `ALSO NAME WORD PREVIOUS` on the start line after the
LOAD-VOCABs. NAME uses PRELOAD's characters (A-Z, 0-9, -); WORD may be
any printable characters with no lowercase letters (so FONTS-OK? is a
word). Refused: either name outside its set, a WORD that loads blocks,
a second SETUP for one NAME, and a NAME no PRELOAD line names.

A suite that reads a file in the machine says `\\ PAYLOAD: NAME WORD FILE`
(FILE relative to the test source's own folder). The build writes the
file's bytes, as they are, into raw blocks after the source blocks (each
file from a fresh block, the last padded with zeros), and puts
`ALSO NAME DECIMAL blk len WORD PREVIOUS` in the SETUP group of the start
line, in the order the lines appear: WORD ( blk len -- ) copies them
where the suite reads them. THRU never covers these blocks. NAME and WORD
are checked as SETUP's are; FILE must exist. With no PAYLOAD line the
image and the start line are exactly as they were.

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
PRELOAD = re.compile(r'^\\ PRELOAD: ([A-Z0-9-]+)\s*$')
VOCAB_NAME = re.compile(r'^[A-Z0-9-]+$')          # PRELOAD's set
SETUP_WORD = re.compile(r'^[\x21-\x7e]+$')        # printable, no space


def line_limit():
    """The longest line the prompt reads: TIB_SIZE - 1, from the kernel."""
    src = open(os.path.join(ROOT, 'src', 'kernel', 'forth.asm')).read()
    m = re.search(r'^TIB_SIZE\s+equ\s+(\d+)', src, re.M)
    if not m:
        sys.exit('make-test-image: TIB_SIZE not found in forth.asm')
    return int(m.group(1)) - 1


def start_lines(loads, setups, thru, limit):
    """The typed lines: one if it fits, else loads, setups, thru."""
    one = ' '.join(loads + setups + [thru])
    if len(one) <= limit:
        return [one]
    lines = []
    for group in (loads, setups, [thru]):
        cur = ''
        for piece in group:
            if cur and len(cur) + 1 + len(piece) > limit:
                lines.append(cur)
                cur = piece
            else:
                cur = f'{cur} {piece}' if cur else piece
        if cur:
            lines.append(cur)
    return lines


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
    preloads = []
    setups = {}                 # vocabulary -> word, in first-seen order
    payloads = []               # (vocabulary, word, file), in order
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
            # SETUP: a word run once at the prompt, from the start line,
            # before the suites (it may read blocks, which block text may
            # not: the buffer holding the text could be reused).
            if ln.startswith('\\ SETUP:'):
                toks = ln[len('\\ SETUP:'):].split()
                where = f'make-test-image: {path}:{n} SETUP'
                if len(toks) != 2:
                    sys.exit(f'{where} wants two names, a vocabulary and '
                             f'a word; got {len(toks)}')
                v, w = toks
                if not VOCAB_NAME.match(v):
                    sys.exit(f'{where} vocabulary name {v!r} rejected: '
                             f'only A-Z, 0-9 and - (the PRELOAD set)')
                if not SETUP_WORD.match(w) or w != w.upper():
                    sys.exit(f'{where} word {w!r} rejected: printable '
                             f'characters only, no lowercase letters')
                if w in NESTED_LOADS:
                    sys.exit(f'{where} word {w} rejected: it loads blocks')
                if v in setups:
                    sys.exit(f'{where} for {v} rejected: a second SETUP '
                             f'for one vocabulary ({setups[v]} came first)')
                setups[v] = w
                continue
            if ln.startswith('\\ PAYLOAD:'):
                toks = ln[len('\\ PAYLOAD:'):].split()
                where = f'make-test-image: {path}:{n} PAYLOAD'
                if len(toks) != 3:
                    sys.exit(f'{where} wants a vocabulary, a word and a '
                             f'file; got {len(toks)}')
                v, w, fn = toks
                if not VOCAB_NAME.match(v):
                    sys.exit(f'{where} vocabulary name {v!r} rejected: '
                             f'only A-Z, 0-9 and - (the PRELOAD set)')
                if not SETUP_WORD.match(w) or w != w.upper():
                    sys.exit(f'{where} word {w!r} rejected: printable '
                             f'characters only, no lowercase letters')
                if w in NESTED_LOADS:
                    sys.exit(f'{where} word {w} rejected: it loads blocks')
                fp = os.path.join(os.path.dirname(os.path.abspath(path)), fn)
                if not os.path.isfile(fp):
                    sys.exit(f'{where} file {fn} not found ({fp})')
                payloads.append((v, w, fp))
                continue
            m = PRELOAD.match(ln)
            if m and m.group(1) not in preloads:
                preloads.append(m.group(1))
            elif ln.startswith('\\ PRELOAD:') and not m:
                sys.exit(f'make-test-image: {path}:{n} PRELOAD wants one '
                         f'uppercase vocabulary name')
            hit = NESTED_LOADS & {w.upper() for w in ln.split()}
            if hit:
                sys.exit(f'make-test-image: {path}:{n} uses '
                         f'{" ".join(sorted(hit))}; test source must '
                         f'not load blocks (nested-load limitation)')
        src_blocks += WB.source_to_blocks(text)
    for v in setups:
        if v not in preloads:
            sys.exit(f'make-test-image: SETUP names {v}, which no PRELOAD '
                     f'line loads')
    pay_blocks, pay_pieces = [], []
    blk = first + 1 + len(src_blocks)
    for v, w, fp in payloads:
        if v not in preloads:
            sys.exit(f'make-test-image: PAYLOAD names {v}, which no '
                     f'PRELOAD line loads')
        data = open(fp, 'rb').read()
        nb = (len(data) + BLOCK - 1) // BLOCK
        pay_blocks.append(data + bytes(nb * BLOCK - len(data)))
        pay_pieces.append(f'ALSO {v} DECIMAL {blk} {len(data)} {w} PREVIOUS')
        blk += nb
    lines = [
        '\\ TEST-IMAGE banner (tools/make-test-image.py, generated)',
        f': TI-BANNER ." TEST-IMAGE {tag}" CR ; TI-BANNER',
    ]
    for ln in lines:
        if len(ln) > WB.SCREEN_COLS:
            sys.exit(f'make-test-image: banner line over 64: {ln!r}')
    banner = WB.source_to_block('\n'.join(lines))

    limit = line_limit()
    starts = start_lines([f'S" {v}" LOAD-VOCAB' for v in preloads],
                         [f'ALSO {v} {w} PREVIOUS' for v, w in setups.items()]
                         + pay_pieces,
                         f'DECIMAL {first} {first + len(src_blocks)} THRU', limit)
    for ln in starts:
        if len(ln) > limit:
            sys.exit(f'make-test-image: a typed line is {len(ln)} characters, '
                     f'over the prompt\'s {limit} (TIB_SIZE - 1); nothing '
                     f'built: {ln[:60]}...')

    tmp = out_path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(product)
        f.write(banner)
        for b in src_blocks:
            f.write(b)
        for b in pay_blocks:
            f.write(b)
    os.replace(tmp, out_path)
    last = first + len(src_blocks)
    with open(out_path + '.start', 'w') as f:
        f.write('\n'.join(starts) + '\n')
    print(f'test image: {out_path}')
    print(f'  product  {len(product)} B sha256 {sha256(product)}')
    print(f'  banner   TEST-IMAGE {tag}')
    print(f'  first test block {first}')
    if len(starts) == 1:
        print(f'  start line: {starts[0]}')
    else:
        print(f'  start lines: {len(starts)}, each typed after ok '
              f'(one is over {limit} characters)')
        for ln in starts:
            print(f'  start line: {ln}')
    print(f'  source blocks {len(src_blocks)} ({first + 1}..{first + len(src_blocks)})'
          if src_blocks else '  source blocks 0')
    for (v, w, fp), piece in zip(payloads, pay_pieces):
        print(f'  payload {os.path.basename(fp)}: {piece}')


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
