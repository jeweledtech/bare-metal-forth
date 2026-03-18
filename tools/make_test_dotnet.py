#!/usr/bin/env python3
"""Generate minimal synthetic .NET PE for testing format detection."""

import os
import struct

def build_dotnet_pe():
    """Build a minimal PE32 with CLR data directory set (fake .NET assembly)."""
    buf = bytearray(0x400)

    # DOS header
    struct.pack_into('<H', buf, 0, 0x5A4D)   # e_magic = MZ
    struct.pack_into('<I', buf, 0x3C, 0x40)   # e_lfanew

    # PE signature
    struct.pack_into('<I', buf, 0x40, 0x4550)  # PE\0\0

    # COFF header at 0x44
    struct.pack_into('<H', buf, 0x44, 0x014C)  # Machine = i386
    struct.pack_into('<H', buf, 0x46, 1)       # NumberOfSections
    struct.pack_into('<H', buf, 0x54, 224)     # SizeOfOptionalHeader
    struct.pack_into('<H', buf, 0x56, 0x2000)  # Characteristics = IMAGE_FILE_DLL

    # PE32 Optional header at 0x58
    struct.pack_into('<H', buf, 0x58, 0x10B)   # Magic = PE32
    struct.pack_into('<I', buf, 0x74, 0x1000)  # AddressOfEntryPoint
    struct.pack_into('<I', buf, 0x7C, 0x10000) # ImageBase
    struct.pack_into('<I', buf, 0x80, 0x1000)  # SectionAlignment
    struct.pack_into('<I', buf, 0x84, 0x200)   # FileAlignment
    struct.pack_into('<I', buf, 0x90, 0x3000)  # SizeOfImage
    struct.pack_into('<I', buf, 0x94, 0x200)   # SizeOfHeaders
    struct.pack_into('<I', buf, 0xB4, 16)      # NumberOfRvaAndSizes

    # CLR data directory (entry 14) at opt_hdr + 96 + 14*8 = 0x58 + 96 + 112 = 0x58 + 208 = 0x128
    clr_offset = 0x58 + 96 + 14 * 8
    struct.pack_into('<I', buf, clr_offset, 0x2000)  # CLR RVA
    struct.pack_into('<I', buf, clr_offset + 4, 72)   # CLR Size

    # Section header (.text) at 0x138
    buf[0x138:0x140] = b'.text\x00\x00\x00'
    struct.pack_into('<I', buf, 0x140, 0x100)  # VirtualSize
    struct.pack_into('<I', buf, 0x144, 0x1000) # VirtualAddress
    struct.pack_into('<I', buf, 0x148, 0x200)  # SizeOfRawData
    struct.pack_into('<I', buf, 0x14C, 0x200)  # PointerToRawData
    struct.pack_into('<I', buf, 0x158, 0x60000020)  # CODE|EXEC|READ

    # .text content: RET
    buf[0x200] = 0xC3

    return bytes(buf)

outdir = os.path.join(os.path.dirname(__file__), '..', 'tests', 'fixtures')
os.makedirs(outdir, exist_ok=True)
outpath = os.path.join(outdir, 'test_dotnet.dll')
data = build_dotnet_pe()
with open(outpath, 'wb') as f:
    f.write(data)
print(f"Written {len(data)} bytes to {outpath}")
