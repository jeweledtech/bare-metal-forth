# TASK — HAL phase 0 additions: BIOS. gated, firmware addresses checked against the memory map (2026-10-12)

Owner, 2026-10-12 (rulings on PCI-TYPES and phase 0, item 3): one small
commit, red test first.
- Gate BIOS.: QEMU told a made-up SMBIOS type 0 vendor and version
  (`-smbios type=0,vendor=...,version=...`); BIOS. reads exactly those, on
  both legs.
- Before following the EFI system table, the configuration table, or the
  SMBIOS / ACPI table addresses, look each up in the multiboot2 memory map;
  print its memory type on the boot report line; refuse, by name, to
  follow an address in a range ForthOS owns (its windows, the module, the
  shadow). Gated on OVMF.
Follows docs/TASK_HAL_DISCOVERY.md.

## Design note

- **The map must outlive the MBI.** mb2_entry reads the memory map in place,
  and the module move may overwrite the MBI ("the map is not read again").
  The Forth words follow the addresses long after boot, so mb2_entry keeps a
  compact copy in the kernel before the move: each entry below 4 GiB as
  [base, end, type] (end exclusive, an entry crossing 4 GiB clipped, the
  same rule as mb2_window), adjacent entries of one type merged, at most 64
  (768 B). The boot report gives the count kept and the count dropped;
  an address in a dropped entry looks up as type 0 (not in the kept map),
  said as such, never guessed.
- **What ForthOS owns** is one table: the three windows (mb2_windows: low
  memory with the stacks, kernel and dictionary; the allocation pool; the
  screen shadow) followed by the module's final range (mb2_mod_start /
  mb2_mod_end move to sit right after the windows, so the table is four
  [lo, hi) pairs). On a BIOS boot the module pair is [0, 0): empty.
- **Kernel words** (read-only):
  - `MB2-MEMTYPE ( addr -- type )`: the multiboot2 type (1 available,
    2 reserved, 3 ACPI reclaimable, 4 ACPI NVS, 5 bad), 0 = not in the map.
  - `MB2-OWNED ( addr -- 0|n )`: 1-3 the window, 4 the module, 0 none.
  - `MB2-MMAP ( -- addr n )`: the kept copy (n = 0: no multiboot2 map).
- **The boot report line** gains the types of the two firmware addresses
  the kernel holds at boot: the EFI system table (tag 12) and the ACPI root
  table named by the RSDP copy (the XSDT when revision >= 2 and it lies
  below 4 GiB, else the RSDT: the rule ACPI-TABLES uses), and the map count:
  `MB2: ACPI RSDP bytes n, SMBIOS entry point bytes m, EFI system table t
  type T, ACPI root r type R, memory map k kept d dropped`. An owned address
  there reads `... (ForthOS memory)`. The kernel follows neither address
  at boot. The configuration table and the SMBIOS addresses are found only
  by following the system table, which only the Forth words do, so they
  are checked and typed there.
- **The follow check** is one word, in a small block-loaded vocabulary
  FWMEM (SMBIOS and ACPI each REQUIRE it: one definition, two users):
  `FW-FOLLOW? ( addr c-addr u -- flag )`.
  - Owned: prints `<name> at <addr>: ForthOS memory (<owner>), not
    followed` and returns 0; the caller does not follow it.
  - Else returns -1. When FW-SAY is on and a map exists it prints
    `<name> at <addr> type <T> (<type name>)`, so a report's type lines
    come from the check itself (evidence the check sits on the path, not
    only in the source).
  - Call sites: SM-EFI (`EFI system table`, `EFI configuration table`,
    `SMBIOS entry point`), SM-TABLE (`SMBIOS table`), ACPI-TABLES
    (`ACPI XSDT` / `ACPI RSDT`, then `ACPI table` for each entry). SMBIOS.
    and ACPI-TABLES turn FW-SAY on for their path (the per-table check in
    ACPI-TABLES stays quiet unless it refuses: one line per table would
    fill an iron screen). The copies GRUB passed (MB2-RSDP, MB2-SMBIOS)
    live in the kernel and are not checked (they are ForthOS memory by
    design); the legacy scans read fixed BIOS areas and are not checked.
  - With no multiboot2 map (a BIOS boot) the owned check still runs and
    nothing new prints: the SeaBIOS outputs are unchanged.
- **Address, not range:** the check looks up the address followed (the
  first byte). A table that starts outside ForthOS memory and runs into it
  is not caught; recorded, not built.
- No writes anywhere.

## Gates

test-uefi-boot, QEMU additionally told `-smbios type=0,vendor=ForthGateBIOS,
version=P0.1`:
- B5 (extended): the boot line carries `EFI system table t type T`, `ACPI
  root r type R`, and `memory map k kept d dropped`, k > 0, d = 0, neither
  address marked ForthOS memory.
- U14 (OVMF): SMBIOS. prints the path, each line from the check:
  `EFI system table at t type ...` (t = the boot line's), `EFI
  configuration table at ...`, `SMBIOS entry point at ...`, `SMBIOS table at
  ...` (= the table SMBIOS. names), each type a firmware type (2-4), and
  ACPI-TABLES prints `ACPI XSDT at r type R` (= the boot line's).
- U15 (OVMF): FW-FOLLOW? refuses, by name and owner, the module start
  (from the boot line: `module`), 0x7E00 (`window 1`), 0x100000
  (`window 2`), 0x80000 (`window 3`), each flag 0; the system table
  address passes (-1, silent with FW-SAY off). DEPTH 0.
- U16 / L14: BIOS. prints `BIOS vendor: ForthGateBIOS`, `BIOS version: P0.1`.
- Everything else in test-uefi-boot unchanged (U10/L10 SMBIOS text, U12/L12
  table rows, the SeaBIOS outputs).
Kernel pad cost reported.

## Results

Evidence: ~/forthos-evidence/2026-10-12-hal-fwmem/ (predictions written
before the red run, logs).

**Red** (018cf7d + the test change): every result as predicted. B5, U14,
U15 FAIL (no types on the boot line; no FWMEM). U16 and L14 PASS: BIOS.
already read type 0, and OVMF installs QEMU's type 0 (the named
alternative, OVMF keeping its own "EFI Development Kit II / OVMF", did not
happen). The SeaBIOS SMBIOS table moved F5310 -> F5320 (the type 0
structure QEMU now adds).

**Green**, two runs (61.2 s; 56.6 s before: about ten more prompt round
trips; T_UEFI_BOOT 115 unchanged, 1.9x):

| check | OVMF |
|---|---|
| B5 boot line | `EFI system table 1F9EC018 type 00000002, ACPI root 1FB7D0E8 type 00000003, memory map 00000014 kept 00000000 dropped` |
| U14 the check's own lines | EFI system table 1F9EC018 type 2 (reserved), EFI configuration table 1F9ECC98 type 2, SMBIOS entry point 1F988000 type 2, SMBIOS table 1F987000 type 2, ACPI XSDT 1FB7D0E8 type 3 (ACPI reclaimable) |
| U15 refusals | `Probe at 00400000: ForthOS memory (module), not followed` (and 7E00 window 1, 100000 window 2, 80000 window 3), flag 0 each; the system table -1, silent |
| U16 / L14 | `BIOS vendor: ForthGateBIOS`, `BIOS version: P0.1` |

The SeaBIOS outputs are unchanged apart from the new BIOS. check. OVMF's
map through GRUB: 20 entries after merging, none dropped (cap 64).

**Full make -k** (37 min): every target passed but test-pci-bar, and that
failure was mine, not the tree's: during the run I added a new vocabulary
file to forth/dict for the next task (moved out three minutes later), and
test-pci-bar computes PCI-BAR's placement by scanning forth/dict on the
host, so it loaded 1340-1346 against an image holding PCI-BAR at
1332-1338 (computed both ways). The image was never rebuilt (sha256
ece262b2 before and after). Rerun alone on the unchanged tree: 16/16.

**Cost:** kernel pad 1,304 B (10,299 -> 8,995 B free): the map copy (768 B
at 64 entries), the lookups, MB2-MEMTYPE / MB2-OWNED / MB2-MMAP, the report
fields. FWMEM is block-loaded (catalog blocks only).

**Not covered:** a table that starts outside ForthOS memory and runs into
it (the check is by address); a map with more than 64 entries after
merging is reported (dropped count), its tail looks up as type 0.

## The whole range, where the length is known (2026-10-13)

Owner, 2026-10-13: FW-FOLLOW? checks the whole range wherever the length is
known (the SMBIOS structure table's length, each ACPI table's header
length), not just the start; red first, a small commit; gate: a probe range
that starts in firmware memory and ends inside a ForthOS window is refused
by name.

**Design.**
- Kernel `MB2-OWNED-IN ( addr len -- 0|1-4 )`: the first owned range (the
  three windows, then the module, numbered as MB2-OWNED numbers them) that
  the bytes [addr, addr+len) overlap. len 0 is the address alone. The end
  saturates at 4 GiB, so a range never wraps to 0. Empty pairs (the module
  on a BIOS boot, [0, 0)) are skipped.
- FWMEM `FW-SPAN? ( addr len c-addr u -- flag )`: refused, by name and
  owner, when the range touches ForthOS memory; the refusal and the FW-SAY
  line give `start-last` when the length is known. `FW-FOLLOW?` is
  `FW-SPAN?` with len 0 (its output unchanged).
- SMBIOS: the structure table is checked as [SM-TAB, SM-TAB+SM-LEN).
- ACPI (`AC-SPAN?`): a table's start is checked first, silently (its
  header holds the length, read only once the start is allowed), then the
  whole table, header length at +4; used for the XSDT/RSDT and for every
  table they list.
- Not ranged: the EFI system table, configuration table and SMBIOS entry
  point (their lengths are read from them; the owner's list names the two
  above).

**Gates** (test-uefi-boot):
- U14 amended: the SMBIOS table line is `SMBIOS table at X-Y`, Y = X +
  SMBIOS.'s own len - 1; the XSDT line `ACPI XSDT at R-Y`, Y = R + its
  header length (read in the guest) - 1.
- U17 / L15: 0xFFF00 len 0x200 (last 0x1000FF, inside window 2) is refused,
  `Probe at 000FFF00-001000FF: ForthOS memory (window 2), not followed`,
  flag 0. Control: MB2-OWNED(0xFFF00) = 0 and its map type is not 1.
- U18 / L16: the same start with len 0x100 (ends 0xFFFFF) passes, silent;
  0xFFFFFF00 len 0x800 passes (saturates); FW-FOLLOW? at 0xFFF00 passes.

**Results.** Evidence: ~/forthos-evidence/2026-10-13-fw-span/.
- Red (image df5b1a1f): 44/49, U14 U17 U18 L15 L16 failing, as predicted
  (`FW-SPAN? ?`; start-only lines). FW-FOLLOW? at 0xFFF00 answered -1 on
  both legs: the start-only check let the range through.
- One miss: 0xFFF00's map type is 0 (not in the map) on both legs; I had
  predicted 2 on SeaBIOS. The SeaBIOS leg boots memdisk (L1, BOOT-MODE 1):
  no multiboot2 map, so every address types 0 there. So "firmware memory"
  at 0xFFF00 rests on the x86 BIOS ROM area, not on a map type; the control
  proves only "not ForthOS's, not available in the map".
- Green (image d0258de8): 49/49, two runs, 66.8 s (T_UEFI_BOOT 135, about
  twice; it was 115 for 56.6-61.2 s). OVMF: SMBIOS table 1F987000-1F987153
  (len 154), XSDT 1FB7D0E8-1FB7D13B (len 54).
- Kernel pad: 88 B (8,907 B free).
