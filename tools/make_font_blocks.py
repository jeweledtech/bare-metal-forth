#!/usr/bin/env python3
"""The UEFI console font, built from the installed Terminus Font package
(SIL Open Font License 1.1; the font file is never committed).

  python3 tools/make_font_blocks.py <out.bin> [psf.gz]
  python3 tools/make_font_blocks.py --license <out.txt>

Writes the bytes for the reserved font blocks (write-catalog.py
FONT_RESERVED): a 16-byte header, then one 16-byte glyph per character
(8 x 16, one byte per row, bit 7 = leftmost pixel) for FIRST..LAST:

  +0  'FNT1'
  +4  first char (u8), char count (u8), glyph height (u8), glyph width (u8)
  +8  8 bytes 0
  +16 glyphs

Glyphs are picked by the font's Unicode table, not by position.  Under the
OFL a converted subset is a Modified Version: it must not be called
"Terminus Font", and the license travels with it (the stick carries it).
--license writes the font's copyright and the OFL text (from the same
package's copyright file) for the stick and the netboot tree.
Exit 2 if the package is absent: the caller decides what that means.
"""
import gzip
import struct
import sys

PSF = '/usr/share/consolefonts/Lat15-Terminus16.psf.gz'
COPYRIGHT = '/usr/share/doc/console-setup/copyright.fonts.gz'
NOTICE = """\
The ForthOS UEFI console font (blocks 536-537 of forth.img) is derived
from Terminus Font: the 8x16 printable-ASCII glyphs, converted to a raw
bitmap. It is a Modified Version under the license below and is not
Terminus Font.

"""
FIRST, LAST = 0x20, 0x7E
HEIGHT = 16


def glyphs_by_unicode(path):
    d = gzip.open(path).read()
    if d[:2] != b'\x36\x04':
        sys.exit(f'{path}: not a PSF1 font')
    mode, size = d[2], d[3]
    if size != HEIGHT or not mode & 0x02:
        sys.exit(f'{path}: want 8x{HEIGHT} with a Unicode table (mode {mode}, size {size})')
    n = 512 if mode & 0x01 else 256
    glyphs = [d[4 + i * size:4 + (i + 1) * size] for i in range(n)]
    table, pos = {}, 4 + n * size
    for i in range(n):
        while True:
            cp = struct.unpack_from('<H', d, pos)[0]
            pos += 2
            if cp == 0xFFFF:
                break
            if cp != 0xFFFE:
                table.setdefault(cp, i)
    return glyphs, table


def write_license(out):
    try:
        text = gzip.open(COPYRIGHT).read().decode('utf-8')
    except FileNotFoundError:
        print(f'make_font_blocks: {COPYRIGHT} absent', file=sys.stderr)
        sys.exit(2)
    i = text.find('Terminus Font is licensed under')
    j = text.find('\n== ', i)
    if i < 0 or j < 0 or 'SIL OPEN FONT LICENSE' not in text[i:j]:
        sys.exit(f'{COPYRIGHT}: Terminus Font license section not found')
    open(out, 'w').write(NOTICE + text[i:j].rstrip() + '\n')


def main():
    if sys.argv[1] == '--license':
        write_license(sys.argv[2])
        return
    out = sys.argv[1]
    path = sys.argv[2] if len(sys.argv) > 2 else PSF
    try:
        glyphs, table = glyphs_by_unicode(path)
    except FileNotFoundError:
        print(f'make_font_blocks: {path} absent (install console-setup-linux); '
              'the UEFI console will have no font', file=sys.stderr)
        sys.exit(2)
    missing = [hex(c) for c in range(FIRST, LAST + 1) if c not in table]
    if missing:
        sys.exit(f'{path}: no glyph for {missing}')
    body = b''.join(glyphs[table[c]] for c in range(FIRST, LAST + 1))
    head = b'FNT1' + bytes([FIRST, LAST - FIRST + 1, HEIGHT, 8]) + bytes(8)
    open(out, 'wb').write(head + body)


main()
