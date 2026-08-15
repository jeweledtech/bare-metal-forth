#!/usr/bin/env python3
"""Parse the block catalog THE MACHINE READS, out of a built image.

One parser, three consumers: the G6 harness (block range for the
INSTALL THRU), the catalog completeness gate, and the runbook's
desk-side generator.  It exists because the alternative -- each
consumer re-deriving the layout -- is the drift-bug family, which
is not hypothetical here:

  * `tests/test_g6_chain.py` used to re-run write-catalog.py's
    PLACEMENT algorithm in a subprocess and trust the two agreed.
    That copy modelled vocabs only, while the writer had grown to
    lay out `vocabs + raw payloads`.
  * `catalog-resolver.fth` used to scan `4 CONSTANT CAT-NBLKS`
    blocks while the writer emitted `ceil(entries/15)`, by then 5.
    Four vocabs (X86-ASM, VIDEO, VGA-GRAPHICS, ZIP-READER) were
    unloadable and it presented as "not found", not as an error.

Both were a reader duplicating a number the writer derives.  So
this module derives everything from the artifact and hardcodes no
count: the scan ends where the `\\ VOCAB-CATALOG` header stops
appearing, because the first block past the catalog is vocab
source, whose line 0 is a `\\ ====` banner.  That is the same end
marker `CAT-HDR?` uses in Forth -- deliberately, so that a layout
this module can read is a layout the machine can read.

Catalog line format is `<NAME> <FIRST-BLOCK> <LAST-BLOCK>`,
inclusive on both ends, which is what `n m THRU` wants.
"""
import os

BLOCK_SIZE = 1024
LINE_LEN = 64
CATALOG_BLK = 1
HEADER = '\\ VOCAB-CATALOG'
DEFAULT_IMG = 'build/blocks.img'

# Fail-closed ceiling, mirroring CAT-MAXBLKS in catalog-resolver.fth.
# Not a count of catalog blocks -- a bound on how far a corrupt or
# truncated image can make us scan.
MAX_CATALOG_BLKS = 32


def read_catalog(path=DEFAULT_IMG):
    """Return {name: (first_block, last_block)} from a built image.

    Raises OSError if the image is unreadable and ValueError if the
    catalog is malformed.  Never returns a partial catalog silently:
    a caller asking "does every entry resolve?" must be able to tell
    "no entries" from "could not read".
    """
    with open(path, 'rb') as f:
        data = f.read()

    entries = {}
    blk = CATALOG_BLK
    while blk - CATALOG_BLK < MAX_CATALOG_BLKS:
        off = blk * BLOCK_SIZE
        raw = data[off:off + BLOCK_SIZE]
        if len(raw) < BLOCK_SIZE:
            break                       # ran off the end of the image
        text = raw.decode('ascii', errors='replace')
        lines = [text[i:i + LINE_LEN].rstrip()
                 for i in range(0, BLOCK_SIZE, LINE_LEN)]
        if lines[0] != HEADER:
            break                       # walked off the catalog
        for line in lines[1:]:
            parts = line.split()
            if not parts:
                continue
            if len(parts) != 3:
                raise ValueError(
                    f'{path} block {blk}: malformed catalog line '
                    f'{line!r} (want "<NAME> <FIRST> <LAST>")')
            name, first, last = parts
            entries[name] = (int(first), int(last))
        blk += 1
    else:
        raise ValueError(
            f'{path}: catalog header still present after '
            f'{MAX_CATALOG_BLKS} blocks -- refusing to scan further')

    if blk == CATALOG_BLK:
        raise ValueError(
            f'{path}: no catalog at block {CATALOG_BLK} '
            f'(want line 0 == {HEADER!r})')
    return entries


def read_catalog_detail(path=DEFAULT_IMG):
    """Like read_catalog, but {name: (first, last, catalog_block)}.

    The catalog block an entry sits on is what the CAT-NBLKS defect
    turned on: a reader that stopped short made the TAIL of the
    catalog unreachable, so which block an entry lives on is the
    difference between "found" and "silently not found".  Callers
    reporting a failure want it.
    """
    with open(path, 'rb') as f:
        data = f.read()
    out = {}
    blk = CATALOG_BLK
    while blk - CATALOG_BLK < MAX_CATALOG_BLKS:
        off = blk * BLOCK_SIZE
        raw = data[off:off + BLOCK_SIZE]
        if len(raw) < BLOCK_SIZE:
            break
        text = raw.decode('ascii', errors='replace')
        lines = [text[i:i + LINE_LEN].rstrip()
                 for i in range(0, BLOCK_SIZE, LINE_LEN)]
        if lines[0] != HEADER:
            break
        for line in lines[1:]:
            parts = line.split()
            if len(parts) == 3:
                out[parts[0]] = (int(parts[1]), int(parts[2]), blk)
        blk += 1
    return out


def vocab_blocks(name, path=DEFAULT_IMG):
    """Return (first, last) for one entry, or (None, None)."""
    try:
        return read_catalog(path).get(name, (None, None))
    except (OSError, ValueError):
        return None, None


if __name__ == '__main__':
    import sys
    img = os.environ.get('BLOCKS_IMG', DEFAULT_IMG)
    if len(sys.argv) > 1:
        first, last = vocab_blocks(sys.argv[1], img)
        if first is None:
            sys.exit(f'{sys.argv[1]}: not in catalog {img}')
        print(f'{first} {last} THRU')
    else:
        for n, (a, b) in sorted(read_catalog(img).items()):
            print(f'{n} {a} {b}')
