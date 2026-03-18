#!/usr/bin/env python3
"""Generate minimal COM file with known port I/O for testing."""

import os
import sys

# COM file: loads at 0x100
# IN AL, 0x60     ; E4 60 — read keyboard port
# OUT 0x61, AL    ; E6 61 — write speaker port
# IN AL, DX       ; EC    — read variable port
# OUT DX, AL      ; EE    — write variable port
# RET             ; C3

code = bytes([
    0xE4, 0x60,   # IN AL, 0x60
    0xE6, 0x61,   # OUT 0x61, AL
    0xEC,         # IN AL, DX
    0xEE,         # OUT DX, AL
    0xC3,         # RET
])

outdir = os.path.join(os.path.dirname(__file__), '..', 'tests', 'fixtures')
os.makedirs(outdir, exist_ok=True)
outpath = os.path.join(outdir, 'test_port_access.com')
with open(outpath, 'wb') as f:
    f.write(code)
print(f"Written {len(code)} bytes to {outpath}")
