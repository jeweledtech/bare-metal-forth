#!/usr/bin/env python3
"""Sparse ~1 TB HP-mirror GPT fixture for the G6 chain harness.

Geometry transcribed from the 2026-08-01 HP recon
(docs/TASK_INSTALL_BOOT_ENTRY.md): protective MBR, disk sig
8C9B2FB7, NO boot code; ESP extent [2048, 534527]; five-partition
shape. Sparse writes only -- the file is ~1 TB logical, a few MB
physical.

build(path) writes the image. Run as a script to build AND
self-verify (parse-back with recomputed CRCs).
"""
import os
import struct
import sys
import uuid
import zlib

SECTOR = 512
TOTAL = 1953525168          # 512-byte sectors, ~931 GiB (HP 1TB)
MBR_SIG = 0x8C9B2FB7        # recon R8
ENTRIES = 128
ENT_SIZE = 128
ARR_SECS = ENTRIES * ENT_SIZE // SECTOR   # 32
FIRST_USABLE = 34
LAST_USABLE = TOTAL - 34
DISK_GUID = uuid.UUID('6a5e28c1-7d02-4f61-9c33-0d54b1c0a9e2')

T_ESP = uuid.UUID('c12a7328-f81f-11d2-ba4b-00a0c93ec93b')
T_MSR = uuid.UUID('e3c9e316-0b5c-4db8-817d-f92df00215ae')
T_NTFS = uuid.UUID('ebd0a0a2-b9e5-4433-87c0-68b6b72699c7')
T_RECOV = uuid.UUID('de94bba4-06d1-4d40-a16a-bfd50179d6ac')

# (type, unique, first, last, name) -- starts anchored to recon
# (0x800, 0x82800, 0x8A800); later ends are plausible fills.
PARTS = [
    (T_ESP, uuid.UUID('11111111-1111-4111-8111-111111111111'),
     2048, 534527, 'EFI system partition'),
    (T_MSR, uuid.UUID('22222222-2222-4222-8222-222222222222'),
     535552, 567295, 'Microsoft reserved'),
    (T_NTFS, uuid.UUID('33333333-3333-4333-8333-333333333333'),
     567296, 1848778751, 'Windows'),
    (T_RECOV, uuid.UUID('44444444-4444-4444-8444-444444444444'),
     1848778752, 1850875903, 'Recovery'),
    (T_NTFS, uuid.UUID('55555555-5555-4555-8555-555555555555'),
     1850875904, 1953523711, 'Data'),
]


def entry_array():
    arr = bytearray(ENTRIES * ENT_SIZE)
    for i, (t, u, first, last, name) in enumerate(PARTS):
        off = i * ENT_SIZE
        arr[off:off + 16] = t.bytes_le
        arr[off + 16:off + 32] = u.bytes_le
        arr[off + 32:off + 40] = struct.pack('<Q', first)
        arr[off + 40:off + 48] = struct.pack('<Q', last)
        # attrs 0 at +48
        n = name.encode('utf-16-le')[:71]
        arr[off + 56:off + 56 + len(n)] = n
    return bytes(arr)


def header(current, backup, arr_lba, arr_crc):
    h = bytearray(92)
    h[0:8] = b'EFI PART'
    h[8:12] = struct.pack('<I', 0x00010000)
    h[12:16] = struct.pack('<I', 92)
    # +16 header CRC: zero during compute
    h[24:32] = struct.pack('<Q', current)
    h[32:40] = struct.pack('<Q', backup)
    h[40:48] = struct.pack('<Q', FIRST_USABLE)
    h[48:56] = struct.pack('<Q', LAST_USABLE)
    h[56:72] = DISK_GUID.bytes_le
    h[72:80] = struct.pack('<Q', arr_lba)
    h[80:84] = struct.pack('<I', ENTRIES)
    h[84:88] = struct.pack('<I', ENT_SIZE)
    h[88:92] = struct.pack('<I', arr_crc)
    h[16:20] = struct.pack('<I', zlib.crc32(bytes(h)))
    return bytes(h) + b'\x00' * (SECTOR - 92)


def protective_mbr():
    m = bytearray(SECTOR)
    # 0x000-0x1BD zero: NO boot code (recon R8)
    m[0x1B8:0x1BC] = struct.pack('<I', MBR_SIG)
    e = 0x1BE
    m[e] = 0x00                          # status
    m[e + 1:e + 4] = b'\x00\x02\x00'     # CHS first
    m[e + 4] = 0xEE                      # protective type
    m[e + 5:e + 8] = b'\xff\xff\xff'     # CHS last
    m[e + 8:e + 12] = struct.pack('<I', 1)
    m[e + 12:e + 16] = struct.pack(
        '<I', min(TOTAL - 1, 0xFFFFFFFF))
    m[510:512] = b'\x55\xaa'
    return bytes(m)


def build(path):
    arr = entry_array()
    crc = zlib.crc32(arr)
    with open(path, 'wb') as f:
        f.truncate(TOTAL * SECTOR)       # sparse
        f.seek(0)
        f.write(protective_mbr())
        f.write(header(1, TOTAL - 1, 2, crc))          # LBA 1
        f.write(arr)                                   # LBA 2-33
        f.seek((TOTAL - 33) * SECTOR)
        f.write(arr)                     # backup array
        f.write(header(TOTAL - 1, 1, TOTAL - 33, crc))
    return path


def verify(path):
    """Independent parse-back; returns (fail strings, checks run).

    The denominator is checks PERFORMED, not a constant: a bad
    header sig skips that header's three dependent checks, so a
    fixed denominator could print nonsense like 'Passed: -2/8'
    on a badly broken fixture and look like a harness bug.
    Healthy run = 4 MBR-side + 4 per header x 2 = 12.
    """
    fails = []
    ran = 0
    with open(path, 'rb') as f:
        ran += 1
        if os.fstat(f.fileno()).st_size != TOTAL * SECTOR:
            fails.append('size')
        mbr = f.read(SECTOR)
        ran += 1
        if mbr[:0x1B8] != b'\x00' * 0x1B8:
            fails.append('boot code not zero')
        ran += 1
        if struct.unpack('<I', mbr[0x1B8:0x1BC])[0] != MBR_SIG:
            fails.append('disk sig')
        ran += 1
        if mbr[0x1BE + 4] != 0xEE or mbr[510:] != b'\x55\xaa':
            fails.append('protective entry / 55AA')
        for lba, alt, arr_lba in (
                (1, TOTAL - 1, 2), (TOTAL - 1, 1, TOTAL - 33)):
            f.seek(lba * SECTOR)
            h = f.read(SECTOR)[:92]
            ran += 1
            if h[:8] != b'EFI PART':
                fails.append(f'sig @{lba}')
                continue
            claimed = struct.unpack('<I', h[16:20])[0]
            z = bytearray(h)
            z[16:20] = b'\x00' * 4
            ran += 1
            if zlib.crc32(bytes(z)) != claimed:
                fails.append(f'header CRC @{lba}')
            ran += 1
            if struct.unpack('<Q', h[32:40])[0] != alt:
                fails.append(f'alternate LBA @{lba}')
            f.seek(arr_lba * SECTOR)
            arr = f.read(ENTRIES * ENT_SIZE)
            ran += 1
            if zlib.crc32(arr) != struct.unpack(
                    '<I', h[88:92])[0]:
                fails.append(f'array CRC @{lba}')
    return fails, ran


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else \
        'build/g6-disk.img'
    build(path)
    fails, ran = verify(path)
    for x in fails:
        print(f'  FAIL: {x}')
    print(f'fixture: {path} '
          f'({os.path.getsize(path)} logical bytes)')
    print(f'Passed: {ran - len(fails)}/{ran}')
    sys.exit(1 if fails else 0)
