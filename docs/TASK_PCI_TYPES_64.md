# TASK — PCI-TYPES prints a 64-bit BAR in full (2026-10-12)

Owner, 2026-10-12: print the full base of a 64-bit BAR; flag a base above
4 GiB as unreachable, by name, instead of printing 00000000; gate on the
OVMF case; pad cost reported.

**Measured first** (~/forthos-evidence/2026-10-12-xhci-bar-ovmf/): under
OVMF the qemu-xhci BAR0 reads 0x00000004 (64-bit memory), BAR1 0x000000C0:
base 0xC0_0000_0000 (QEMU `info pci` agrees). PCI-TYPES masked the low
dword only and printed 00000000; it also lacked the space before MMIO.

**Change** (forth/dict/pci-enum.fth): `.BAR0 ( bus dev func -- )` reads
BAR0 raw; a 64-bit memory BAR (bits 2:0 = 100) reads BAR1 too, and a
nonzero high dword prints `0x<high><low>` and `(above 4 GiB: unreachable)`
(this kernel is 32-bit with no paging). Everything else prints as before.
PCI-TYPES calls it, with `SPACE ." MMIO" SPACE`. Reaching such a BAR (a
paging window, or moving the BAR below 4 GiB) waits for the ASUS's real
values and a plan (owner).

**Gate** (test-uefi-boot U9/L9): red, as predicted, both legs (`00 02
00MMIO 00000000` / `00 02 00MMIO FEBF0000`; my L9 pattern first assumed
00 03 00, but the replica has no NIC). Green, two runs: OVMF `USB host
(xHCI) at 00 02 00 MMIO 0xC000000000 (above 4 GiB: unreachable)`, SeaBIOS
`... MMIO FEBF0000`. test-pci-typing 18/18 (its pattern accepts both).
Pad cost 329 B (11,132 -> 10,803 B free).
