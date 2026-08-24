# G6 iron session notes — 2026-08-21

Session spans 2026-08-21 (steps 1–2), 2026-08-22 (G4, install,
verification), and 2026-08-23 (chainload G6(a), post-install disk/
NVRAM verification, Windows 4(b)); filename reflects start date.

Companion evidence: `docs/EVIDENCE_G6_NETCON.log` (net-console transcript,
listener up across boots; timestamps separate instances).
Runbook: `tools/pxe/RUNBOOK-G6.md`. Green commit: `50af824`.

## Step 1 — push (desk, pre-session)

```
step 1 (desk)  2026-08-21 ~11:11 PDT  PASS
  make grub-net && make pxe-push-grub
  forth.img MD5 7b8147b2839d1b78a0ab4740ae68543b  (== combined.img)
  Deployed OK: our-files hash a5d5cf8c6d68b1822967dd125aa185d5
  listener hash gate: PASS (deployed sha256 55a1ac9e... == build)
  forth.img 2,212,352 bytes (load-time tell)
```

## Step 2 — cutover + leg B

```
leg B (iron)  2026-08-21 12:03:46 PDT  PASS
  cutover: /etc/forthos-pxe-dnsmasq.conf
           dhcp-boot=grub/i386-pc/core.0,,10.42.0.1
           forthos-pxe.service restarted 12:02:10
  GRUB menu rendered, timed out to entry 0 (memdisk)
  banner + ok on VGA; transcript in docs/EVIDENCE_G6_NETCON.log
  rollback: dhcp-boot=pxelinux.0,,10.42.0.1 + restart unit
```

First run of this loader chain on the machine. Boot at 12:03:46 is
unambiguously post-cutover (restart 12:02:10).

## Bag / recovery posture

```
Windows recovery media:  SKIPPED -- Windows 10 install is expendable
  (out of manufacturer support for years), operator decision
  2026-08-21. Rollback ladder available: H.1-H.3 via Ubuntu live
  stick; H.4 waived.
Windows boots pre-install:  YES (confirmed by operator 2026-08-21,
  before any write) -- gate 4(b) baseline established.
```

## Linux-EFI stick (rebuilt 2026-08-22)

```
The March FORTHBOOT stick had no UEFI/Linux path (legacy GRUB+memdisk
only -- by design, see tools/make-uefi-usb.sh: its UEFI leg is a stub
menu saying CSM is required; the "enable CSM" message was the script
working as designed, not a fault); it was wiped and will be rebuilt
post-session from tools/make-uefi-usb.sh with build/combined.img
(NOT the bmforth.img default).
Replacement: SanDisk 57.3GB, dd of ubuntu-24.04.4-desktop-amd64.iso.
On-stick sha256 3a4c9877... == ISO == Canonical published sum.
UEFI-boot this stick on the HP for G4 baseline + H.1-H.3 bench.

OWED: until that rebuild, there is no stick that demonstrably boots
  ForthOS via USB. The USB delivery path is a peer of PXE (repo users
  will use it), and it was iron-proven on the March stick; it is now
  unverified until rebuilt and booted once on the HP.
```

## G4 baseline (before any write)

```
G4 baseline:  CAPTURED 2026-08-22 09:01, before any write
  transcript: docs/evidence/g4-baseline-2026-08-22.txt (verbatim,
              via nc over PXE LAN; original /tmp/g4-baseline.txt)
  photos:     4016.jpg, 4017.jpg (screen, primary record)
  boot mode:  UEFI (BootCurrent 0004 = UEFI USB / Ubuntu stick)
  BootOrder:  2001,0001,3001,0002,0000,0003,2002,2004   <- H.1 restore line
  Boot0001*   Windows Boot Manager
              HD(1,GPT,62b09d32-865b-401b-b27b-c3cf19094f7f,0x800,0x82000)
              \EFI\Microsoft\Boot\bootmgfw.efi
  cross-check: ESP 0x800/0x82000 = base 2048 len 532480 -- matches the
              R7 values sec. 3d expects from the live PARTITION-MAP
  internal disk: WDC WD10JPVX-60JC3T1 (Boot0000, legacy BBS entry)
  uncontaminated: BootCurrent 0004 is NOT in BootOrder -- the F9 stick
              boot was one-time and did not perturb the persistent
              order; the act of capturing did not change the measurement
```

## Step 3 — install (record as you go)

```
step 3 (iron)  2026-08-22 09:32-09:34 PDT  PASS (all gates -1, DEPTH 0)
  PARTITION-MAP: 5 partitions (P1 FAT32 00000800, P2 Unknown 00082800,
    P3 NTFS 0008A800, P4 Recovery 72916000, P5 NTFS 72B00000)
  MAP-TRUSTED? -1   (first read printed 0 -- operator had skipped
    PARTITION-MAP; re-typed from runbook, flag set correctly)
  OWN-BASE  34       (first read printed "22" -- hex; see below)
  OWN-LEN   549      (intended 225; typed under hex -> 0x225; see below)
  FS-SLOT   5
  DEPTH probe between MAKE-OWN-ENT and ADD-PARTITION: 1 (entry only)
  ADD-PARTITION -1 (first write, 09:33:57), ADD-BOOT-ENTRY -1, DEPTH 0
```

Evidence note: the net console garbles command echoes under load --
this transcript contains three artifacts ("USING IN  STALL",
"MAP-TRUSTED/   ? .", "ADD-A   PARTITION ."). Cosmetic (known
phantom-echo finding, 2026-08-11): every step was validated by its
PRINTED RESULT, not its echoed command, several via independent
probes. The operator did not type nonsense.

Resolution (verified on iron before reboot, all read-only):
```
GPT header (LBA 1, decimal, flag-checked read): entries 128,
  size 128, FirstUsableLBA 34 -- classical layout, 128*128/512+2=34
OWN-BASE 34 (= FirstUsableLBA, correct), OWN-LEN 549 (intended 225)
  cause: PARTITION-MAP leaves BASE=16 -- measured directly,
  BASE @ DECIMAL . -> 16 at 09:41:23.
  PARTITION-MAP is the SECOND WORD found to leave BASE=16
  (after AHCI-INIT). This is the THIRD documented SITE where
  sticky BASE bites: the INSTALL THRU (2026-08-06, root-caused
  08-20), the 2048 ESP-BASE ! -> 8264 hazard (documented, not
  yet hit), and now 225 FREE-EXTENT -> 549 (hit, on iron).
  Harmless this run (slack only, no overlap):
  partition claims 34-582, all inside the 34-2047 pre-ESP gap;
  VBR bakes only start LBA (35); load count fixed at 224 in
  template; ABE-FITS? needs >=225, got 549.
  FIX OWED: DECIMAL immediately after PARTITION-MAP in RUNBOOK
  3e and in the harness; base-transparent PARTITION-MAP alongside
  the deferred AHCI-INIT fix. Note: harness is accidentally
  immune -- val() sends "DECIMAL 225 FREE-EXTENT ." as one line,
  so only a live operator could hit this.
VBR at LBA 34: 55AA confirmed. P6 present, type Unknown
  (= surveyor not recognizing FOS-TYPE-GUID -- canonical GUID
  written). 6 partitions listed, P6 base 00000022 hex = 34.
```

## Step 4 — G6

```
(a) chainload:  PASS 2026-08-23 07:36:55 (EVIDENCE_G6_NETCON.log)
    HEX 28098 @ .  DECIMAL  ->  0   (chainloaded, not memdisk)
    memdisk counter-reading, same cell, same iron: 37BB7000 at
      2026-08-22 09:45 on the still-running memdisk instance --
      the discriminator provably distinguishes the legs on iron
    load-time tell: memdisk hauls 2,212,352 B / chainload near-instant
    menu photo taken before Enter?  NOT CONFIRMED -- operator not
      yet asked/answered for the 08-23 boot; record when known
(b) Windows boots:  PASS 2026-08-23, photo 4045.jpg
    procedure: USB sticks removed, firmware settings untouched,
      no F9. Fall-through 2001 (empty) -> 0001 Windows Boot
      Manager is INFERRED from the recorded BootOrder, not
      observed -- the operator saw a normal boot, not the
      firmware's selection.
    reached the desktop normally; no Automatic Repair on this boot
    earlier Automatic Repair episode (first post-install boot,
      ~07:40): CLOSED AS UNEXPLAINED (2026-08-23). What is
      established: Startup Repair NEVER RAN -- C:\Windows\System32\
      LogFiles listing shows only CloudFiles, setupcln, SQM, WMI;
      no Srt directory (listing not re-run with -Force). Srt is
      created BY a repair pass; no folder, no pass, nothing
      modified. Did not recur (next observed boot reached the
      desktop, photo 4045.jpg, firmware settings untouched).
      Four candidate
      mechanisms proposed, none survived (GPT-array overlap, stale
      entry CRC, unclean shutdowns, Fast Startup stale hibernation
      image -- hiberfil.sys does not exist, hibernation deliberately
      disabled on this machine). Event-log inquiry ABANDONED, not
      concluded: four successive instrument failures, recorded in
      the G6-CLOSEOUT doc (project-side). Honest gap, not a
      comfortable mechanism.

G6 CLOSED 2026-08-23: leg B memdisk (08-21 12:03), install §3a-3e
(08-22), chainload discriminator 0 (08-23 07:36), GPT clean and
host partitions untouched (sgdisk, 08-23 11:02), NVRAM
byte-identical to 08-22 09:01 baseline (efibootmgr, 08-23 11:02 --
predates the 4(b) Windows boot; re-check downgraded to optional:
Startup Repair provably never ran -- no Srt directory -- so nothing
rewrote boot configuration), Windows boots (08-23, photo 4045.jpg).
```

## Post-install verification (Ubuntu stick, UEFI, 2026-08-23)

Photos: 4042.jpg, 4043.jpg, 4044.jpg (taken 2026-08-23 11:02 --
AFTER both the chainload PASS at 07:36 and the Automatic Repair
episode; they establish the disk is clean NOW, not the state
Windows saw when it decided to run Startup Repair).

```
sgdisk -v:  "No problems found."  (primary/backup CRCs consistent --
    ADD-PARTITION maintained the table correctly)
gdisk -l:   P1-P5 at byte-identical LBAs to pre-install; P6 =
    34..582, 274.5 KiB, type FFFF (gdisk not recognizing
    FOS-TYPE-GUID, expected), name "FORTHOS" (MAKE-OWN-ENT's
    UTF-16LE name field intact)
efibootmgr: G4 EQUALITY PASS -- BootOrder 2001,0001,3001,0002,0000,
    0003,2002,2004 identical to 09:01 baseline; Boot0001 Windows
    Boot Manager byte-identical (GUID 62b09d32-..., 0x800,0x82000);
    Timeout: 0 seconds, identical to baseline. C0b held: installer
    cannot write NVRAM and didn't.
NOT ours:   "0xEE partition is oversized! Auto-repairing" is
    pre-existing (R8 recon 2026-08-01 recorded protective MBR size
    0xFFFFFFFF before any write); gdisk -l repair is in-memory only.
PRODUCT FINDING: alignment cautions are real -- P6 start 34 / end
    582 not 8-sector aligned; disk is 512e (4096 physical).
    FREE-EXTENT has no alignment policy. Improvement owed to the
    installer, not a defect from this run.
Automatic Repair cause: not visible in disk or NVRAM state.
    Candidates (unproven): Windows reacting to unrecognized
    partition on its boot disk, or unclean-shutdown flag from the
    day's power cycles / F9 hangs.
```
