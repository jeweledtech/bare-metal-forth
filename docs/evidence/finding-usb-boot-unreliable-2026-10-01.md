# FINDING — USB boot is unreliable, and it is the only path to 3 of 4 machines (2026-10-01)

The UEFI-2 trip passed, but the headline result is the delivery failure
underneath it: **the FORTHBOOT stick was not offered at F9 on the HP, and
the operator fell back to PXE.** That is the second occurrence of a USB
problem on this exact setup, and it blocks every machine PXE cannot reach.

## What happened

- **UEFI-2 trip, 2026-10-01.** The stick was written correctly — hash
  gate PASS, `/mnt/fb/forth.img` = `6fac2873…` = `build/combined.img`
  (`uefi2-iron-2026-10-01.log` l.6-8). But at the HP's F9 boot menu the
  stick was **not offered**; the trip proceeded over PXE instead
  (banner 14:38:03, after the `forth.img` push at 14:36:19 and the tftpd
  fetch at 14:37:52). So the stick was good; the machine would not boot
  it.
- **Ports tried:** ____ (operator to record which HP USB ports were
  tried at F9).

## Why this is the bigger result

Delivery, not the kernel, is the blocker for scaling past the HP:

- **3 of the 4 reference machines are Wi-Fi-only** — Dell (Wi-Fi 7
  BE201), Newer ASUS (Wi-Fi 6 AX201), Older ASUS (Wireless-AC 9560), per
  their `pci-bound.csv`. ForthOS has no 802.11 vocabulary, so **PXE
  cannot reach any of them.** USB is their *only* delivery path.
- USB just failed on the **HP — the one machine where USB has worked**
  (HDA-1/2/3 all booted from this stick). So the only path to the other
  three is the path that is now shown to be unreliable even where it
  used to work.
- It sits **upstream of two committed directions:** CARRIER-3
  (`usb-image-native`, a stick with no GRUB/memdisk) and the Creator
  (whose entire job is writing bootable USB sticks). Both are pointless
  if the HP — our most-tested machine — intermittently won't boot a
  correctly-written stick.

## This is a pattern, not a one-off

The HDA-3 addendum (2026-09-27) already flagged **this stick/port
combination as marginal**: the same `General UDisk` (`abcd:1234`, serial
`…668715`) flapped with `error -71` on the dev box and had to move ports,
and on the HP it did not show at one F9 port and booted from another.
Today it was not offered at F9 at all. **Two occurrences on the same
stick = a pattern**, not bench luck.

## Suspects, and what would disambiguate (none settled yet)

| suspect | for | against | discriminator |
|---|---|---|---|
| **The stick** (marginal hardware) | the `-71` flapping and port-dependence seen at HDA-3; cheap generic `UDisk` | it booted HDA-1/2/3 on this HP | write a **known-good spare stick** (owner already recommended one at HDA-3) and retry F9 |
| **The port / F9 enumeration** | port-dependent behavior at HDA-3 | — | try every HP USB port; note USB2 vs USB3 ports; watch whether F9 lists it after a longer wait |
| **The image layout** (`make-uefi-usb.sh` GPT + ESP + GRUB) | F9 may not enumerate the hybrid layout consistently | the same layout booted HDA-1/2/3 on this HP | compare a stick made by `make-uefi-usb.sh` vs the in-place file-copy refresh; check whether F9 lists it with/without a `UEFI:` prefix |

The trip did not capture enough to choose (no record of which ports, or
whether F9 listed it at all vs listed-but-failed). The next USB attempt
should record those explicitly.

## Recommendation

- **Provision a known-good spare stick** (standing recommendation since
  HDA-3) and make the stick/port a recorded variable on every trip card,
  not an afterthought.
- **Treat reliable USB delivery as a prerequisite** for CARRIER-3 and the
  Creator — neither should be built on a path that doesn't reliably boot
  the HP.
- Until then, **the non-HP machines are blocked** for any on-iron work;
  that gates UEFI-3's ASUS trip (which needs USB, since it has no wired
  NIC) as much as it gates carrier/Creator.

## Related

- `usb_boot_hp15` (the USB boot procedure), the HDA-3 card addendum
  (first occurrence), `TASK_REMOVE_BOOT_CARRIER.md` (CARRIER-3),
  `forthos-creator/docs/` (the Creator, which writes these sticks).
