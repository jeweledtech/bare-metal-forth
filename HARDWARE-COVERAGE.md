# ForthOS Hardware Coverage

This document tracks ForthOS coverage of physical hardware,
organized by the six hardware domains every operating system
must ultimately reach: system, processing, memory, storage,
networking, and human interface.

ForthOS covers hardware with vocabularies, not driver stacks.
Each vocabulary is a set of Forth words that address device
registers directly. There is no HAL, no device model, no VFS,
and no abstraction layer between a word and the silicon it
touches. Omissions of intermediate layers found in other
operating systems are deliberate and recorded in the
Non-Goals section below.

Corrected against the repo 2026-09-29 (was last touched 2026-07-14, and
had gone stale enough to misbrief a design pass): PCI enumeration, the
NIC vocabularies, and xHCI USB HID are shipped, not planned.

Status legend:

- **COVERED** — vocabulary exists, tested, HP bare-metal validated
- **PARTIAL** — vocabulary exists; scope or validation incomplete
- **PLANNED** — on the roadmap, dependency order noted
- **EXCLUDED** — deliberate non-goal (see Non-Goals)

---

## 1. System

| Capability | Status | Notes |
|---|---|---|
| BIOS boot / bare-metal load | COVERED | Boots directly from firmware; no host OS |
| ACPI (shutdown, AML parsing) | PARTIAL | SHUTDOWN word complete on QEMU (SCI_EN handshake, `_S5_` package); HP bench validation pending |
| PCI enumeration | COVERED | `pci-enum.fth` (embedded) + `pci-bar.fth`; class search HP bare-metal validated (HDA-1/2/3, 2026-09) |
| Power management beyond S5 | PLANNED | After PCI |

## 2. Processing

| Capability | Status | Notes |
|---|---|---|
| CPU bring-up (x86) | COVERED | NASM kernel, direct instruction-set targeting |
| Interrupt handling | PARTIAL | Sufficient for keyboard and timer operation; APIC-depth work not yet scoped |
| Timers | PARTIAL | Operational for current workloads |
| ARM64 target | PARTIAL | Metacompiler Phase C in progress; QEMU virt machine, exception vector stub in place |
| SMP / multicore | EXCLUDED | See Non-Goals |

## 3. Memory

| Capability | Status | Notes |
|---|---|---|
| Physical memory access | COVERED | Direct address read/write is a core system capability |
| Block storage buffers | COVERED | Forth block model (1024-byte blocks) |
| MMU / paging / virtual memory | EXCLUDED | See Non-Goals |

## 4. Storage

| Capability | Status | Notes |
|---|---|---|
| AHCI (SATA controller) | COVERED | Direct controller programming |
| NTFS read | COVERED | Full MFT walker; validated against 1.2M-record fragmented MFT on reference hardware |
| FAT32 read | COVERED | Reads EFI System Partition; LFN display polish pending |
| File browser / editor over real filesystems | COVERED | HP bare-metal validated |
| NVMe | PLANNED | After PCI enumeration; required for NVMe-only modern laptops |
| USB mass storage | PLANNED | After USB core (see Human Interface) |

## 5. Networking

| Capability | Status | Notes |
|---|---|---|
| UDP console (development) | COVERED | Network console on reference platform |
| NIC vocabulary | COVERED | `rtl8168.fth` (HP bare-metal validated — carries the net console), `rtl8139.fth`, `ne2000.fth` (QEMU) |
| Protocol words (ARP/IP/UDP as vocabulary) | PARTIAL | `UDP-SEND`/`NET-SEND` exist (fixed addressing; the net console's TX path). No receive/ARP resolution as vocabulary yet |
| DHCP | PLANNED | Missing. Addressing is fixed today; no lease client |
| 802.11 / WPA2 | PLANNED | Missing entirely. Three of four reference machines are Wi-Fi-only; needs an 802.11 MAC vocabulary, WPA2, and a vendor firmware blob (a licensing question, not only an engineering one) |
| Full socket stack | EXCLUDED | See Non-Goals |

## 6. Human Interface

| Capability | Status | Notes |
|---|---|---|
| PS/2 keyboard (i8042) | COVERED | HP bare-metal validated |
| VGA text and graphics | COVERED | Editor, file browser, forms render on real hardware |
| USB core + USB HID | PARTIAL | xHCI vocabulary + HID keyboard (`HID-POLL`, `xhci.fth`); QEMU-proven and exercised on the HP through the xHCI iron cards. HID-on-iron validation scope not yet closed |
| Audio | PLANNED | Low priority |

---

## Dependency-ordered gap list

PCI enumeration, the NIC vocabularies, and USB core + HID are done
(the 2026-07 version of this chain listed all three as open — that was
the stale brief). The remaining gaps:

1. **NVMe** — storage on NVMe-only machines (the Dell, and the newer
   ASUS behind Intel VMD). Depends on PCI (met).
2. **USB mass storage** — on the xHCI core (met).
3. **DHCP** — a lease client over the existing UDP TX path.
4. **802.11 / WPA2** — the largest gap; three of four reference
   machines are Wi-Fi-only. Blocked on a firmware-blob licensing
   question as much as on code.

Everything else in this document is either covered or excluded
by design.

## Non-Goals

The following appear in conventional kernel architectures and
are deliberately absent from ForthOS. They are policies about
how software is permitted to reach hardware, not facts about
the hardware itself.

- **HAL / device model / driver framework.** Vocabularies
  address registers directly. There is no registration layer.
- **Virtual File System.** Filesystem vocabularies (NTFS,
  FAT32) expose their own words. There is no unifying
  abstraction above them.
- **MMU-based virtual memory.** ForthOS runs against physical
  addresses. Memory safety is discipline (assertions, loud
  failures), not translation hardware.
- **Scheduler / preemptive multitasking / SMP.** One machine,
  one dictionary, one thread of control.
- **Socket abstraction.** Network words will talk to the NIC
  and to packets, not to a sockets API.

These exclusions are the product. A capability listed as
EXCLUDED is not missing; it is the layer ForthOS demonstrates
you do not need.
