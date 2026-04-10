# Task: DISK-SURVEY Phase 2 — Archive Extraction + Deep Analysis

## Prerequisite
DISK-SURVEY Phase 1 complete (commit `5343877`): 14 binary extensions
across 7 consolidated counters, multi-partition NTFS walk, PE/ELF
classification via DRIVER-REPORT. Validated on HP 15-bs0xx with
1,195,006 MFT records and 69,354 binaries cataloged in ~90 minutes.

## Mission

Phase 1 catalogs everything **directly on the filesystem**. Phase 2
catalogs everything **packed inside archives** — so nothing on the
bare-metal machine remains uncovered. Every binary that could be
reverse-engineered through the UBT pipeline becomes visible to the
surveyor, whether it sits in `System32\drivers\` or is buried inside
a Windows Update .cab file.

This is the "leave nothing uncovered" guarantee.

## Why It Matters

Archives on a typical Windows 10/11 install contain thousands of
additional binaries invisible to a filesystem scan:

- **`.cab` files** — used EVERYWHERE in Windows
  - `C:\Windows\System32\DriverStore\FileRepository\` — driver packages
  - `C:\Windows\SoftwareDistribution\Download\` — Windows Update cache
  - `C:\Windows\Logs\CBS\` — Component-Based Servicing backups
  - Each .cab contains .sys, .dll, .exe, .cat, .inf files
- **`.msi` files** — installer packages
  - `C:\Windows\Installer\` — every installed application has one
  - MSI is an OLE2 Compound Document; binary tables point to actual files
- **`.zip` files** — general archives
  - Development tools, downloaded software, portable apps

On the HP laptop's 69,354 directly-visible binaries, Phase 2 likely
exposes another **50,000-200,000 binaries** inside archives.

## Architecture

### New vocabularies

Each archive format becomes its own loadable vocabulary, following
the existing driver vocab pattern (REQUIRES header, ALSO chain,
Forth primitives only).

#### `forth/dict/cab-extract.fth`
- Microsoft Cabinet format parser
- MSZIP (DEFLATE) and LZX decompression
- Directory header → file entry listing
- Streaming extraction into memory buffer for UBT analysis
- Reference: CAB File Format Specification (Microsoft public spec)
- Depends on: DEFLATE primitives (see zip-reader), HARDWARE

#### `forth/dict/msi-reader.fth`
- OLE2 Compound Document format parser
- FAT/minifat stream navigation
- MSI database schema: File table, Component table, Directory table
- Extract binary file listings without full decompression
- Reference: `[MS-CFB]` and `[MS-MSI]` public specs
- Depends on: CAB-EXTRACT (MSI often uses internal cabinets), HARDWARE

#### `forth/dict/zip-reader.fth`
- ZIP format parser (End of Central Directory → Central Directory)
- DEFLATE decompression (RFC 1951)
- Directory-only scan (no full decompression for listing)
- Reference: PKZIP APPNOTE.TXT
- Depends on: HARDWARE

**Shared primitive:** DEFLATE decompression (~200 lines in Forth).
Factor into `forth/dict/deflate.fth` so CAB, MSI, and ZIP all share it.

### Recursive DISK-SURVEY

Extend the existing SURVEYOR vocabulary with a second pass:

```forth
VOCABULARY SURVEYOR-DEEP
SURVEYOR-DEEP DEFINITIONS
ALSO SURVEYOR ALSO CAB-EXTRACT ALSO MSI-READER ALSO ZIP-READER

VARIABLE SV-NCAB       \ .cab files found
VARIABLE SV-NMSI       \ .msi files found
VARIABLE SV-NZIP       \ .zip files found
VARIABLE SV-ARCBIN     \ binaries found INSIDE archives

: DEEP-SURVEY ( -- )
  \ Pass 1: DISK-SURVEY (already works)
  \ Pass 2: re-walk MFT looking for .cab/.msi/.zip
  \ For each archive:
  \   - Open via appropriate vocab
  \   - Read directory headers only (don't decompress bodies)
  \   - Count binaries inside by extension
  \   - Add to SV-ARCBIN
  \ Print combined report
;
```

### Per-extension detailed stats

Add an optional `DISK-SURVEY-DETAIL` word that tracks all 14+
extensions individually AND counts by directory path bucket:

```forth
VARIABLE SV-NSYS-INDIV  \ separate from consolidated SV-NSYS
VARIABLE SV-NDRV-INDIV
VARIABLE SV-NDLL-INDIV
VARIABLE SV-NOCX-INDIV
... etc for all 14

VARIABLE SV-SYSTEM32    \ count in System32\
VARIABLE SV-WINSXS      \ count in WinSxS\ (side-by-side)
VARIABLE SV-DRIVERS     \ count in System32\drivers\
VARIABLE SV-PROGFILES   \ count in Program Files\
VARIABLE SV-PROGDATA    \ count in ProgramData\
VARIABLE SV-USERS       \ count in Users\

: DISK-SURVEY-DETAIL ( -- )
  \ Same as DISK-SURVEY but with per-extension + per-directory tallies
  \ Extracts parent directory path from MFT $FILE_NAME attribute
  \ Buckets by top-level directory
;
```

This gives researchers the ability to ask questions like "how many
drivers are in WinSxS vs System32\drivers?" or "are there more
ActiveX controls in Windows or in Program Files?"

## Implementation Order

1. **DEFLATE vocab** (~200 lines)
   Pure Forth DEFLATE decompression. Test fixture: compress known
   strings with Python `zlib`, decompress in ForthOS, verify match.

2. **ZIP-READER vocab** (~300 lines)
   Simplest archive format. End of Central Directory search, walk
   Central Directory entries, print filename + uncompressed size
   + method. Reuse DEFLATE for bodies (optional).

3. **CAB-EXTRACT vocab** (~400 lines)
   CAB format is cleanly documented. MSZIP is DEFLATE with a tiny
   wrapper. LZX is more complex — defer LZX support for Phase 2.1
   if not critical (most modern CABs use MSZIP).

4. **MSI-READER vocab** (~500 lines)
   OLE2 Compound Document parser is the heaviest lift. FAT/minifat
   navigation, directory stream parsing, stream extraction. The MSI
   database itself is just a collection of tables inside streams.

5. **SURVEYOR-DEEP + DEEP-SURVEY** (~200 lines)
   Recursive walk that reuses Phase 1 MFT iteration plus opens each
   archive via the matching vocab. Streams the directory listing,
   doesn't decompress bodies unless asked.

6. **DISK-SURVEY-DETAIL** (~150 lines)
   Per-extension + per-directory bucketing. Shares the MFT loop
   with DISK-SURVEY but uses different counters. Parses parent
   directory from MFT $INDEX attribute.

## Size Budget

Current state (post 5343877):
- Kernel: 58.4 KB / 64 KB
- Free: 5.6 KB

Phase 2 adds roughly:
- DEFLATE:         ~2 KB (compressed embedded size)
- ZIP-READER:      ~1.5 KB
- CAB-EXTRACT:     ~2.5 KB
- MSI-READER:      ~3 KB
- SURVEYOR-DEEP:   ~1.5 KB
- SURVEY-DETAIL:   ~1 KB
- **Total:**       ~11.5 KB

This EXCEEDS the 5.6 KB free space. Phase 2 vocabularies should
**not be embedded** — they load from blocks via `USING`. The block
disk already supports this (write-catalog.py writes all .fth files).

Loading pattern:
```forth
USING CAB-EXTRACT    \ loads from blocks on demand
USING MSI-READER
USING SURVEYOR-DEEP
DEEP-SURVEY
```

Only SURVEYOR (Phase 1) stays embedded so `DISK-SURVEY` works out
of the box. Phase 2 is opt-in for users who want the deep scan.

## Success Criteria

- [ ] DEFLATE round-trips test data (compressed by Python, decompressed in Forth)
- [ ] ZIP-READER lists all files in a test zip with correct names/sizes
- [ ] CAB-EXTRACT lists all files in a Windows Update .cab
- [ ] MSI-READER lists all files in a C:\Windows\Installer\*.msi
- [ ] DEEP-SURVEY on HP laptop finds 100K+ additional binaries inside archives
- [ ] DISK-SURVEY-DETAIL shows per-extension + per-directory breakdown
- [ ] Combined report:
  ```
  === DEEP Survey Summary ===
  Direct binaries:     69,354
  Archive containers:    N CAB / N MSI / N ZIP
  Archived binaries: 150,000+
  Total coverage:    220,000+
  ```

## Reference Materials

- **CAB format:** https://learn.microsoft.com/en-us/previous-versions/bb417343(v=msdn.10)
- **MSI format:** `[MS-CFB]` Compound File Binary File Format, `[MS-MSI]` Windows Installer
- **ZIP format:** PKZIP APPNOTE.TXT (public spec)
- **DEFLATE:** RFC 1951
- **Test fixtures:** Python `zipfile`, `zlib`, `cabarchive` libraries for generating round-trip test data

## Open Questions (resolve during planning)

1. **LZX support in CAB-EXTRACT:** Required for older Windows CABs? Or MSZIP-only sufficient for modern systems?
2. **Recursive extraction:** What about ZIPs inside MSIs inside CABs? How deep do we recurse?
3. **Memory budget for decompression:** PHYS-ALLOC a working buffer? How large? (Windows .cab files can be 100+ MB.)
4. **UBT integration:** Should DEEP-SURVEY pipe archive contents directly into the UBT translator, or just emit a listing that the user walks manually?
5. **Compressed MFT records:** NTFS supports attribute compression. Currently ignored by Phase 1. Relevant for Phase 2?

## Vision

Phase 1: "Plug into any machine, type `DISK-SURVEY`, get every binary on the filesystem."

Phase 2: "Plug into any machine, type `DEEP-SURVEY`, get every binary **anywhere** — filesystem + archives + update caches + driver store + installer packages. Nothing uncovered. Every single file that could be reverse-engineered is in the inventory."

Together with the UBT pipeline, this turns ForthOS into a complete bare-metal binary forensics platform — the thing you plug in when you need to know what's actually running on a machine, without trusting any OS to tell you.
