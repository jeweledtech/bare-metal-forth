# TASK: SHUTDOWN Word — ACPI S5 Power Off

**Status:** Tier 1 COMPLETE (QEMU 7/7). Tier 2 awaiting HP validation.

---

## Goal

A `SHUTDOWN` word that cleanly powers off the machine.
Required for the "boots, uses, shuts down" experience.

## Architecture

Two tiers, two commits:

### Tier 1 — QEMU i440FX (COMPLETE)

`QEMU-OFF` writes `0x2000` to port `0x604` (PM1a_CNT).
QEMU exits immediately. No ACPI table walk needed.

### Tier 2 — Real hardware via ACPI table walk

`ACPI-SHUTDOWN` performs:

1. **RSDP scan**: EBDA then `0xE0000-0xFFFFF`,
   16-byte aligned, `"RSD PTR "`, checksum-validated
2. **RSDT locate**: 4 bytes at RSDP+16
3. **FADT locate**: Walk RSDT entries for `"FACP"`
4. **DSDT locate**: 4 bytes at FADT+40
5. **`_S5_` scan**: Byte-pattern scan DSDT AML for
   `0x5F 0x53 0x35 0x5F`, parse PackageOp to
   extract SLP_TYPa (handles BytePrefix + bare
   ZeroOp/OneOp)
6. **PM1a_CNT**: 4 bytes at FADT+64
7. **SCI_EN handshake**: Read PM1a_CNT via INW,
   check bit 0. If clear, write ACPI_ENABLE
   (FADT+52) to SMI_CMD port (FADT+48), poll
   until SCI_EN sets (bounded timeout)
8. **Shutdown**: `(SLP_TYPa << 10) | SLP_EN` to
   PM1a_CNT via OUTW

### Failure modes (print and abort)

- RSDP not found: `." No RSDP" CR`
- RSDP checksum fail: `." RSDP checksum" CR`
- FADT not found: `." No FADT" CR`
- DSDT pointer zero: `." No DSDT" CR`
- `_S5_` not found: `." No _S5_" CR`
- SCI_EN timeout: warns but proceeds (safe on
  QEMU; may fail silently on hardware)
- Wrong SLP_TYP: machine stays on (safe failure)

## Usage

Block-load only (NOT embedded — embedding crossed a
memory boundary that broke META-COMPILER THRU loading):

    S" SHUTDOWN" LOAD-VOCAB
    USING SHUTDOWN
    SHUTDOWN

## Files

- `forth/dict/shutdown.fth` — SHUTDOWN vocabulary
- `tests/test_shutdown.py` — QEMU process exit test
- Catalog blocks 914–925 (auto-packed by write-catalog)

## QEMU Observations (2026-07-07)

- SeaBIOS SLP_TYPa = 0 (ZeroOp in `_S5_` package).
  DUMP-verified: `_S5_` at 0x7FE0BE3, bytes
  `5F 53 35 5F 12 06 04 00` — I+7 = 0x00 (bare
  ZeroOp, no BytePrefix). Correct parse, not
  lucky zero.
- RSDP found at `0xF5290`
- FADT at `0x7FE1B06`, DSDT at `0x7FE0040`
- PM1a_CNT port = `0x604` (matches QEMU shortcut)
- PM1a_CNT register reads 0 (SCI_EN not set)
- SMI_CMD = `0xB2`, ACPI_ENABLE = `0xF1`
- **QEMU honors SLP_EN writes without SCI_EN set.**
  This means QEMU CANNOT validate the ENSURE-ACPI
  path. The SCI_EN handshake gets its first real
  test on the HP.
- Tier 2 RSDP scan is legacy-BIOS-only. On UEFI
  USB boot, RSDP is in EFI config table, not
  scannable memory — clean "No RSDP" failure.

## HP Validation Checklist (Tier 2)

**Capture these over UDP console BEFORE issuing
SHUTDOWN — if the machine powers off, the console
evidence dies with it.**

- [ ] PXE boot, then block-load SHUTDOWN:
      `S" SHUTDOWN" LOAD-VOCAB`
- [ ] `USING SHUTDOWN`
- [ ] `HEX SCAN-RSDP .` — verify non-zero
- [ ] `FIND-S5 .` — record actual SLP_TYPa
      (HP will likely be nonzero, unlike QEMU's 0)
- [ ] `PM1A-PORT @ . SMI-PORT @ .` — record ports
- [ ] `PM1A-PORT @ INW .` — record SCI_EN state
- [ ] If SCI_EN=0: `ENSURE-ACPI` should print
      warning then proceed
- [ ] `SHUTDOWN` — machine must power off
- [ ] If machine stays on: SCI_EN handshake is
      the first suspect (QEMU never tested it)

## Bugs Found During Development

1. **AML-BYTE stack bug**: `C@` consumed address,
   `1+` operated on byte value not address.
   Fix: `DUP C@ 0A = IF 1+ C@ ELSE C@ THEN`.
2. **FIND-S5 offset bug**: Added PkgLength value
   to position (pkglen + I + 6), jumping past
   the package into garbage (returned 4 instead
   of 0). Fix: `DROP I 6 +` — PkgLength value is
   byte count, not position offset.
