# TASK — HAL phase 0: discovery (SMBIOS, CPUID, ACPI), read-only (2026-10-12)

Owner, 2026-10-12: the binding layer's phase 0, read-only, no-plan flow.
Gates in QEMU on SeaBIOS and OVMF: SMBIOS manufacturer/product strings,
CPUID vendor and feature bits, the ACPI RSDP/RSDT/XSDT table list. No
writes anywhere. Pad cost reported. Commit without pushing. (ADAPTIVE-HAL:
machine identity for choosing a binding vocabulary needs SMBIOS; these are
the facts layers 1-2 read from firmware.)

## Design note

- **Where the firmware tables are depends on how the machine booted.**
  - Legacy BIOS: the SMBIOS entry point is found by scanning
    0xF0000-0xFFFFF on 16-byte boundaries for `_SM_` (2.x) or `_SM3_` (3.x),
    the ACPI RSDP by scanning the EBDA and then 0xE0000-0xFFFFF for
    `RSD PTR ` (shutdown.fth's scan; FIRMWARE-CONTRACT.md records that it is
    legacy-only).
  - UEFI: neither is in the legacy area. GRUB passes copies in the
    multiboot2 information: tag 13 (SMBIOS entry point), 14 (ACPI 1.0 RSDP),
    15 (ACPI 2.0+ RSDP). mb2_entry keeps them (the MBI can be overwritten
    once the kernel runs): up to 36 bytes of RSDP and 32 of SMBIOS entry
    point, in the kernel image, and reports them on serial. Kernel words
    `MB2-RSDP ( -- addr|0 )`, `MB2-SMBIOS ( -- addr|0 )` return the copy.
  - The discovery words take the multiboot2 copy when there is one, the
    legacy scan otherwise, and say which.
- **CPUID** needs a kernel primitive: `CPUID ( leaf subleaf -- eax ebx ecx
  edx )`. The rest is Forth.
- **The vocabularies** (block-loaded, public, CATEGORY system; nothing at
  boot needs them yet, so they cost no boot-stream pad):
  - `SMBIOS`: SMBIOS-EPS, SMBIOS. (version, table address and length),
    SYSTEM. (type 1: manufacturer, product), BIOS. (type 0: vendor,
    version); the structure walk follows the type/length/strings layout.
  - `CPUINFO` (a vocabulary named CPUID would shadow the kernel word):
    CPU-VENDOR. (leaf 0), CPU-FEATURES. (leaf 1 EDX/ECX: a named
    set of bits, 1 or 0 each), CPU-BRAND. (0x80000002-4 when present).
  - `ACPI`: ACPI-RSDP, ACPI. (revision, source), ACPI-TABLES (each table
    of the XSDT when the revision is 2 or later and the XSDT is below 4 GiB,
    else of the RSDT: signature, address, length; checksums verified).
- **No writes:** every word reads memory or executes CPUID. A table or
  structure above 4 GiB is reported as unreachable, not followed (this
  kernel is 32-bit without paging).

## Gates

test-uefi-boot, both legs, with QEMU told what to report:
`-smbios type=1,manufacturer=ForthGate,product=Phase0` and
`-cpu qemu64,vendor=ForthGateCPU` (values no firmware default can
produce, so a pass means the words read the machine):
- SYSTEM. prints `ForthGate` / `Phase0`;
- CPU-VENDOR. prints `ForthGateCPU`; CPU-FEATURES. reports PAE 1, SSE2 1,
  the hypervisor bit 1 and AVX 0 (qemu64's known set);
- ACPI-TABLES lists FACP and APIC with valid checksums, through the RSDT
  (SeaBIOS) or the XSDT (OVMF), and ACPI. names the source (legacy scan or
  the multiboot2 copy);
- DEPTH 0, and the boot report lines for the multiboot2 copies (OVMF).
Kernel pad cost reported; the vocabularies cost catalog blocks only.

## Results

Evidence: ~/forthos-evidence/2026-10-12-hal-discovery/ (predictions
written before each run, logs).

**Red** (b65d580, the new checks): the discovery checks failed as
predicted on both legs (`SMBIOS ?`, `CPUID ?`, `ACPI ?`; DEPTH 0 held).
Not predicted: U9 failed. With `-cpu qemu64,vendor=ForthGateCPU`, OVMF put
the xHCI's 64-bit BAR at 0x0800000000, not 0xC000000000 (OVMF sizes its
64-bit window from the CPU). PCI-TYPES printed that correctly; the fixed
constant in U9 was the wrong gate, so U9 now compares with QEMU's own
`info pci` BAR0 for the run (0xC000000000 stays the default-CPU
measurement on record).

**Green, one finding on the way:** GRUB 2.12 under OVMF passes the ACPI
RSDP (tag 15, 36 bytes) but **no SMBIOS tag** (13). It does pass the EFI
system table (tag 12), and the system table survives the hand-off, so
mb2_entry now keeps that pointer (MB2-EFI-ST) and SMBIOS looks the
SMBIOS 3 / 2 GUID up in its configuration table. Then all gates pass, two
runs, 56.6 s (T_UEFI_BOOT 100 -> 115: the gate gained the discovery
words, a re-measure of a changed test):

| check | OVMF (UEFI) | SeaBIOS (legacy) |
|---|---|---|
| boot report | B5 `ACPI RSDP bytes 00000024, SMBIOS entry point bytes 00000000, EFI system table 1F9EC018` | (no multiboot2) |
| SMBIOS | U10 `SMBIOS 2.x table at 1F987000 (EFI configuration table)`, `Manufacturer: ForthGate`, `Product: Phase0` | L10 `SMBIOS 3.x table at 000F5310 (legacy scan)`, same strings |
| CPUID | U11 `Vendor: ForthGateCPU`; FPU TSC MSR PAE APIC SSE SSE2 SSE3 1, X2APIC 0, AVX 0, HYPERVISOR 1 | L11 the same |
| ACPI | U12 `RSDP rev 02 ... (multiboot2 copy)`, `XSDT at 1FB7D0E8: 6 tables`, FACP, APIC ... all `ok` | L12 `RSDP rev 00 at 000F52D0 (legacy scan)`, `RSDT at 1FFE230E: 5 tables`, all `ok` |
| DEPTH 0 | U13 | L13 |

The values are the ones QEMU was told to report (`-smbios type=1,
manufacturer=ForthGate,product=Phase0`, `-cpu qemu64,vendor=ForthGateCPU`),
which no firmware default produces. Full make -k on this tree: all tests
passed (37 min). Not gated: BIOS. (type 0) and CPU-BRAND.

**Cost:** kernel pad 504 B (10,803 -> 10,299 B free: CPUID, the copies of
the RSDP and the SMBIOS entry point, the system table pointer, the report
line, MB2-RSDP / MB2-SMBIOS / MB2-EFI-ST). The three vocabularies are
block-loaded: catalog blocks only (ACPI 7, CPUINFO 5, SMBIOS 10 at the
first build).

**Not covered:** a 32-bit UEFI firmware (tag 11) has a different system
table layout; SMBIOS reads the 64-bit layout only. Writes: none anywhere.
