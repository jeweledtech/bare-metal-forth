# FINDING — a USB stick was not offered at F9 on the HP (UEFI-2, 2026-10-01); device identity unestablished

The UEFI-2 trip passed, over PXE. The stick that was supposed to carry it
was **not offered at the HP's F9 boot menu**, and the operator fell back to
PXE. That is the observation. It is **not** yet a statement about the USB
boot path, because the physical device that failed at F9 has not been
identified or examined — and "a stick in unknown condition was not offered"
does not establish "the USB boot path is broken."

## What is observed

- **UEFI-2 trip, 2026-10-01.** A FORTHBOOT stick was written at the desk —
  hash gate PASS, `/mnt/fb/forth.img` = `6fac2873…` = `build/combined.img`
  (`uefi2-iron-2026-10-01.log`, correction note). At the HP's F9 menu the
  stick was **not offered**; the trip proceeded over PXE instead (DHCPACK
  14:37:52 to `ac:e2:d3:39:0f:40`, bootfile `grub/i386-pc/core.0`; banner
  14:38:03 — same log).
- **Ports tried at F9:** ____ (operator to record).

## What is NOT established — and must be, first

The physical device at the HP's F9 cannot be identified from the dev box,
though one of the three candidate descriptions has now been ruled out:

- **The 57.3 GB SanDisk is a distractor, now identified.** It is attached to
  the dev box as `/dev/sda` — SanDisk 3.2Gen1, 57.3 GB, partition labelled
  `TAILS` (a Tails install) — observed directly this session, and by a
  parallel session earlier. It was never written as FORTHBOOT, so it cannot
  be the stick at the HP's F9. The "three conflicting descriptions" are
  really this unrelated dev-box SanDisk plus **two** real candidates: the
  **120 MB** stick the owner reports, and the HDA-3 **General `UDisk`**
  (`abcd:1234`, serial `…668715`).
- **Neither remaining candidate could be examined here.** Only the SanDisk
  is attached; the 120 MB stick and the General UDisk are not, so their
  vendor:product, serial, and true capacity cannot be read, and which of the
  two was at the HP's F9 is unestablished.
- **120 MB may not be the real size.** A whole-disk image read as if it
  were the first partition, or a stick written with a small fixed-size
  image and never re-partitioned, both present as a small device. "120 MB"
  is a reading to explain at the bench, not a settled property of the
  hardware.

Until the device is identified and its state read on the bench, there is no
basis to name a cause.

## Why this is not (yet) a path-level finding

The USB boot path has **worked on this HP**: HDA-1, HDA-2, and HDA-3 all
booted ForthOS from a FORTHBOOT stick on this machine. One not-offered
event on an unidentified stick does not overturn that. The HDA-3 addendum
did flag a stick/port combination as marginal (`-71` flapping on the dev
box, port-dependence at F9), which is prior context worth running down — but
it is not confirmed to be the same stick, so "two occurrences = a pattern"
is not supported yet.

## Scope — what this does and does not block

- **It does not block the ASUS trips.** UEFI-3 on an ASUS needs a
  *known-good* stick regardless of what happened here; provisioning one is a
  desk-prep step, not a defect to be cleared first. An unidentified stick
  not showing at one machine's F9 says nothing about a known-good stick at
  the ASUS.
- **It does not make USB a failed prerequisite** for CARRIER-3
  (`usb-image-native`) or the Creator. Those depend on USB delivery
  working; nothing here shows it does not.

## Why it still matters

USB is the **only** delivery path to three of the four reference machines —
Dell (Wi-Fi 7 BE201), newer ASUS (Wi-Fi 6 AX201), older ASUS
(Wireless-AC 9560) are Wi-Fi-only per their `pci-bound.csv`, and ForthOS has
no 802.11 vocabulary, so PXE cannot reach them. That makes a **reliable,
identified** boot stick worth establishing as standing equipment. This is a
provisioning action, not a demonstrated fault.

## What would turn this into a finding (bench steps, in order)

1. **Identify the device** (the SanDisk is already ruled out — see above).
   Plug the stick that was at the HP into the dev box; record `lsusb`
   (vendor:product), `lsblk -o NAME,SIZE,TRAN,MODEL,SERIAL`, and
   `sudo fdisk -l`. Is it the 120 MB stick or the General UDisk, and is
   120 MB a real size or a small image on a larger device?
2. **Read its state.** Does it carry a valid FORTHBOOT layout and a
   `forth.img` = `build/combined.img`? Was it the HDA-3 `UDisk`, or a
   different device?
3. **Retry F9 deliberately.** On the HP, try every USB port, note USB2 vs
   USB3, and record whether F9 **lists it and it fails to boot** vs **never
   lists it** — a distinction this trip did not capture.
4. **Provision a known-good spare** (standing recommendation since HDA-3)
   and make stick-identity + port a recorded variable on every trip card.

Only after step 1–3 can a cause (the stick, the port/enumeration, or the
image layout) be named; none can be chosen now.

## Related

- `uefi2-iron-2026-10-01.log` (the trip; the correction note records the
  PXE fallback), `usb_boot_hp15` (the USB boot procedure), the HDA-3 card
  addendum (the marginal-stick/port note), `TASK_REMOVE_BOOT_CARRIER.md`
  (CARRIER-3), `forthos-creator/docs/` (the Creator, which writes sticks).
