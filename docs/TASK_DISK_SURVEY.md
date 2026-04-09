# Task: Full-Disk Survey — Walk ALL Partitions, Catalog ALL Binaries

## Prerequisite: Metacompiler Phase B complete

## Context

- NTFS walker works (1.2M MFT records, finds files by name)
- FAT32 reader works (EFI partition, directory navigation)
- AHCI reads any sector on the disk
- GPT parser finds all partitions
- UBT pipeline classifies PE/ELF/COM binaries (270 tests)
- All output streams to dev machine via network console

## Goal

One word — `DISK-SURVEY` — that scans the entire drive,
finds every binary on every partition, classifies them, and
produces a full hardware capability report for the machine.

## Vocabulary: forth/dict/surveyor.fth

### 1. PARTITION-MAP ( -- )

Read GPT, identify each partition's type:
- NTFS (Windows data)
- FAT32 (EFI System, recovery)
- ext4 (Linux, Android) — future, detect but skip
- Linux swap — skip

Print: `P1: NTFS 457GB, P2: FAT32 256MB (EFI), ...`

### 2. NTFS-WALK-DIR ( dir-record# -- )

Given an MFT record for a directory, enumerate its
contents via $INDEX_ROOT and $INDEX_ALLOCATION.
This is the MFT directory walk (not linear scan).
For each entry: print name, size, record number.

### 3. NTFS-FIND-EXT ( ext-addr ext-len -- count )

Linear MFT scan for all files matching extension.
Extensions to search: `.sys .dll .exe .com .ko .efi`
For each match: store record# and name in a results
table. Print progress dots. Return count found.

### 4. FAT32-WALK ( cluster -- )

Recursive directory walk of entire FAT32 tree.
For each file: check extension, add to results if
it's a binary (.efi, .exe, .dll, .com).
Follow subdirectories recursively (limit depth to 8).
Print each file with full path.

### 5. FAT32-FIND-EXT ( ext-addr ext-len -- count )

Walk entire FAT32 directory tree, find all files
matching extension. Handles 8.3 names.

### 6. SURVEY-RESULTS table

```forth
CREATE SURVEY-TBL 4000 ALLOT  ( room for ~250 entries )
```

Each entry: partition#(1) + type(1) + record/cluster(4)
+ size(4) + name(22) = 32 bytes

```forth
VARIABLE SURVEY-N
```

### 7. CLASSIFY-ENTRY ( index -- )

Read the file at survey entry, examine first 2 bytes:
- `4D 5A` (MZ) = PE binary (.sys/.dll/.exe/.efi)
  Read PE header: machine type, subsystem, sections
  Print: `PE x86-64, 10 sections, driver` or
         `PE x86, GUI app` etc.
- `7F 45` (ELF) = Linux binary (.ko, executable)
  Print: `ELF x86-64, kernel module` etc.
- Direct code (no header) = COM file
  Print: `COM flat binary, N bytes`

### 8. DISK-SURVEY ( -- )

The main word. Full automated scan:

a) `PARTITION-MAP` — identify all partitions

b) For each NTFS partition:
   - `NTFS-INIT` on that partition
   - `NTFS-FIND-EXT` for .sys .dll .exe .com
   - Store results in SURVEY-TBL

c) For each FAT32 partition:
   - `FAT32-INIT` on that partition
   - `FAT32-FIND-EXT` for .efi .exe .dll
   - Store results in SURVEY-TBL

d) Print summary report:
```
=== Disk Survey ===
Partitions: 4 (2 NTFS, 1 FAT32, 1 Recovery)
NTFS P3: 847 .sys, 3241 .dll, 156 .exe
FAT32 P1: 3 .efi
Total: 4247 binaries found
```

e) For each .sys file found:
   `CLASSIFY-ENTRY` — read header, print type

f) Print hardware driver report:
```
=== Hardware Drivers ===
i8042prt.sys    PE x86-64  PS/2 keyboard
serial.sys      PE x86-64  Serial port
storport.sys    PE x86-64  Storage
USBXHCI.sys     PE x86-64  USB controller
HDAudBus.sys    PE x86-64  Audio
e1i65x64.sys    PE x86-64  Intel NIC
... N drivers, M with port I/O
```

### 9. DRIVER-REPORT ( -- )

Shorter version: just scan .sys files on NTFS,
classify each one, print the driver summary.
Skips .dll/.exe/.efi for a quick hardware audit.

## Integration

- Add to embedded vocabs in Makefile (after fat32.fth)
- `REQUIRES: NTFS FAT32 AHCI HARDWARE`
- The NTFS and FAT32 vocabs may need minor extensions:
  - NTFS needs `NTFS-REINIT` to switch between partitions
  - FAT32 needs `FAT32-REINIT` similarly
  - Both need to support being called with a specific
    partition LBA rather than auto-detecting

## Network Console Output

Everything streams to dev machine. The full disk survey
might take 20-30 minutes (1.2M MFT records per NTFS
partition) but prints progress throughout.

For the dev machine, capture to file:
```
nc -u -l 6666 | tee disk-survey.txt
```

## Test on HP Hardware

```forth
USING SURVEYOR
DISK-SURVEY
```

Should show all 4 GPT partitions, find hundreds of
.sys drivers, classify them by PE header, and produce
the hardware driver report.

## Future: ext4 Support

The ext4 reader for Linux partitions would be a follow-on.
Detect the partition type GUID in the GPT, flag it as
`Linux ext4 -- not yet supported`, and skip it. When the
ext4 vocabulary is built later, it slots right in and the
survey automatically covers Linux installations and Android.

## Vision

This turns ForthOS into a complete bare-metal disk forensics
and hardware reverse-engineering platform. Plug into any
machine, run `DISK-SURVEY`, and get a full inventory of every
binary on every partition — NTFS, FAT32, everything the GPT
exposes. Then the UBT pipeline can chew through all of them
and emit Forth vocabularies.
