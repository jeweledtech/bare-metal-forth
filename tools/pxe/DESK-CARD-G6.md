# DESK CARD — HP 15-bs0xx: redeploy current image, execute leg, xHCI BAR reading

Print this. Fill every blank **before leaving the desk**. Anything still
blank at the laptop is a step you cannot complete there.

This card supersedes the G6 *install* card (install CLOSED 2026-08-23;
that card's final form is in git history at f325ec5 and the install
sequence remains authoritative in `RUNBOOK-G6.md` §3). This trip does
not write the disk — it deploys the current image over PXE, closes the
iron loop (execute leg), and takes the step-2 BAR reading.

> **The runbook is the authority for any install/rollback line.** This
> card carries numbers, checkboxes, and the short typed sequences new
> to this trip. Long sequences stay in the runbook — a second copy is
> how F1 happened.

**ONE physical session, TWO boots, in this order:**
1. Linux live USB — the xHCI BAR0 reading (decides step-2 scope)
2. PXE — deploy verification, execute leg, ForthOS-side reading

---

## A. Desk prep — IN ORDER (the MD5 comes AFTER block staging)

```bash
git status                      # clean, or explain before proceeding
git log --oneline -1            # commit: ______________________
make combined
# stage the translated i8042prt vocabulary (execute leg):
tools/translator/bin/translator \
    tools/translator/tests/data/i8042prt.sys -t forth -o build/demo_i8042.fth
python3 tools/write-block.py build/blocks.img 1600 build/demo_i8042.fth
cat build/bmforth.img build/blocks.img > build/combined.img
```

```
i8042 block range       1600  ______   ( 1600 + ceil(lines/16) - 1;
                                         was 1606 at card-cut time )
combined.img MD5        ______________________________________
  $ md5sum build/combined.img          # ONLY after the cat above

SURVEYOR catalog range  ______  ______   ( "<n> <m> THRU" )
  $ python3 tools/catalog_layout.py SURVEYOR
  Against the SAME build/blocks.img you just staged into.

make test headline      Passed: ______  over ______ "Passed:" lines
  Re-derive after any tree change. Do NOT carry 1065/29 forward —
  it is pinned to f325ec5.

dnsmasq revert line     dhcp-boot=pxelinux.0
  ON PAPER. The rollback cannot live on a netbooted machine.
```

Push and listener:

```bash
make grub-net && make pxe-push-grub
```
- [ ] `forth.img` MD5 **equals** combined.img MD5 above
- [ ] `Deployed OK: our-files hash …` printed. On mismatch: rerun;
      **do not cut over until it passes**

```bash
python3 tools/hp-portread-capture.py --boot-path pxe --port 6666 \
    --out docs/EVIDENCE_G6_NETCON.log        # start BEFORE leaving desk
```
- [ ] Listener up (its hash gate re-checks deployed vs build/combined.img)

## B. Physically in the bag

- [ ] Linux-EFI USB stick — **booted once, here, now**
- [ ] **RUNBOOK-G6.md, printed** — this card defers to it; carrying
      the card without it recreates the sole-copy problem at the
      one place you cannot fetch a document. The rollback ladder
      (efibootmgr baseline → entry delete → sgdisk by GUID →
      Windows recovery) is runbook **§4(c)**, GUID included.
- [ ] Windows recovery media — this trip does not write the disk,
      but low odds × no-network × live Windows install is the exact
      shape the paper-rollback rule exists for
- [ ] Camera / phone
- [ ] This card
- [ ] FORTHBOOT stick stays home unless refreshing it — and then:
      `tools/make-uefi-usb.sh /dev/sdX build/combined.img` — the
      script's DEFAULT is bmforth.img (kernel-only, no blocks).
      **Always pass the image path.** Never wipe FORTHBOOT for
      utility use — it is a peer delivery path.

---

## C. Boot 1 — Linux live USB: xHCI BAR0 type bits

```bash
lspci | grep -i usb                    # xHCI BDF: ______ (expect 00:14.0)
sudo setpci -s <bdf> BASE_ADDRESS_0    # BAR0 dword: ______________
sudo lspci -xxx -s <bdf>               # full dump — photo or file
```
BAR0 = row `10:`, first 4 bytes, **little-endian**. If bits 2:1 = 10,
also record the upper dword at 0x14: ______________

Interpret AT THE MACHINE:

| bit 0 | bits 2:1 | meaning | consequence |
|-------|----------|---------|-------------|
| 0 | 00 | 32-bit memory BAR | PCI-BAR64@ **not** needed; ECAM moot |
| 0 | 10 | 64-bit memory BAR | PCI-BAR64@ **needed** — step-2 scope confirmed |
| 1 | —  | I/O BAR | **outside the set — finding.** Record, stop this leg |
| 0 | 01 / 11 | reserved | **outside the set — finding.** Record, stop this leg |

## D. Boot 2 — PXE: deploy, execute leg, ForthOS-side reading

- [ ] dnsmasq cutover if not already set: `dhcp-boot=grub/i386-pc/core.0`,
      restart dnsmasq (revert line is on paper, section A)
- [ ] F9 → network boot → GRUB menu → **let it time out** → memdisk →
      banner → `ok`
- [ ] Net console live (AUTO-DETECT self-enables). Fallback:

```forth
ALSO RTL8168  RTL8168-INIT  NET-CONSOLE-ON
NET-CON-ENABLED C@ .        \ must print 1
```

### D1. Execute leg — closes the iron loop

```forth
DECIMAL 1600 ______ THRU    \ i8042 range from section A
USING I8042PRT
PORT-FN-16FCC
```
- [ ] `DECIMAL` opens the THRU line — boot base traps apply here too
- [ ] **SUCCESS = the word loaded, executed, returned a value, and the
      interpreter is alive after.** That is the entire claim.
- [ ] Value returned: ______________ — recorded as DATA. The July
      reading (0x3FD → 0x60) came from QEMU's emulated device and is
      evidence about QEMU, **not** the pass criterion here. A different
      value from working hardware is not a failed translation.

### D2. ForthOS-side BAR reading — corroborates Boot 1

```forth
HEX
FIND-XHCI .            \ must print -1 (b d f remain on stack)
10 PCI-READ .H8        \ RAW BAR0 dword: ______________
DECIMAL                \ not optional
```
- [ ] **Do NOT use PCI-BAR@ here** — it masks the type bits
      (`FFFFFFF0 AND`). PCI-READ or the reading is worthless.
- [ ] Matches Boot 1 dword?  YES / NO — a NO is the finding, not a
      retry.

### D3. If time remains

- FILE-STREAM a driver off the HP's NTFS (proven path, 2026-04-29;
  `ALSO`, not `USING`)
- SURVEYOR sanity via range from section A

---

## E. Closeout

- [ ] Photos: GRUB menu, `ok` banner, both BAR readings
- [ ] Net-console transcript saved (or **"transcript SKIPPED"** written —
      do not let a screen session read like a captured one)
- [ ] Record which boot path actually served the image
- [ ] Re-derive every number you write from **this run's own log**
- [ ] As-built notes mirrored to the private repo **by absolute path**

## What each reading settles

- **C (Boot 1):** whether step 2 (xHCI) needs PCI-BAR64@/ECAM at all
- **D1:** iron loop closed — machine-translated Forth ran on the HP
- **D2:** ForthOS's own PCI view agrees with Linux's — or the
  disagreement is the next session's finding
