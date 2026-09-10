# DESK CARD — HP 15-bs0xx: xHCI 2e — the single iron trip closing step 2

Print this. Fill every blank **before leaving the desk**. Anything still
blank at the laptop is a step you cannot complete there.

This trip has **no red, no sweep, no headline delta** — the suite work is
done (2a-2d + 2e prep). Its product is ONE evidence log:
`docs/evidence/xhci-iron-<date>.log` (netcon capture, or the photo
protocol with "transcript SKIPPED" written).

**Value concentrates where QEMU cannot model** — run in THIS order:
bind/caps → survey #1 → handoff (claim) → SMI-clear → **memdisk gate**
→ halt/reset (the budget measurement) → run/NOP → survey #2 → teardown.
Survey #1 sits BEFORE the handoff so outcome C still yields a baseline.

> Every STOP below is a real stop: record what printed, take the photo,
> and end the leg. A stopped leg with a clean log is a successful trip.

---

## 0. Desk prep — deploy provenance (the 37-day passive-reminder failure)

```bash
git status --porcelain          # clean, or explain before proceeding
git remote -v                   # verified, not assumed
git log --oneline -1            # commit: ______________________
make && make test               # green tree FIRST — it rebuilds
sha256sum build/combined.img    # BUILD:  ________________________________
```

Refresh FORTHBOOT (memdisk boot is REQUIRED — see Section 4.5):

```bash
tools/make-uefi-usb.sh /dev/sdX build/combined.img
# script DEFAULT is bmforth.img (kernel-only, no blocks) —
# ALWAYS pass the image path.  Never wipe FORTHBOOT for utility use.
sha256sum <image file read back from the stick>
#                                 STICK:  ________________________________
```

- [ ] STICK sha256 **equals** BUILD sha256 — no boot until they match

```bash
python3 tools/catalog_layout.py XHCI      # against THIS build/blocks.img
```

```
XHCI THRU range          ______  ______     ( literal digits, from the
                                              command above, THIS run )
combined.img sha256      recorded above
netcon listener          tools/hp-portread-capture.py --boot-path usb
                         --port 6666 --out docs/evidence/xhci-iron-$(date +%F).log
```

## 1. Boot — F9 → FORTHBOOT (memdisk) → banner → `ok`

- [ ] Session nonce: type a marker, e.g. `12345 .` — a re-appearing
      banner later = silent warm reset (Bug #35 signature is FORGED
      chain-break; grep for the banner before diagnosing corruption)
- [ ] **Internal i8042 keyboard ONLY** for this whole session — the
      trip resets the controller behind every USB port
- [ ] Net console live, or photo protocol declared now

## 2. Load + gate

```forth
DECIMAL ______ ______ THRU     \ XHCI range from Section 0
ONLY FORTH DEFINITIONS
ALSO PCI-ENUM  ALSO XHCI  ALSO HARDWARE
DECIMAL                        \ re-assert: AHCI-INIT-class BASE traps
```

- [ ] `DEF? XHCI-CLAIM` and `DEF? MEMDISK-BASE@` both -1 — a 0 means
      wrong image on the stick: STOP, back to Section 0

## 3. Read leg — bind, caps, survey #1 (BEFORE handoff)

```forth
XHCI-BIND .                    \ must print -1;  0 = STOP (finding)
HEX XHCI-BASE @ .H8 DECIMAL    \ BAR: ______________ (expect 64-bit path)
CAP-LEN . HCI-VER . MAX-PORTS . MAX-SLOTS .
\   caplen ____  ver ____  ports ____  slots ____
XHCI-OWNER .                   \ OWNER: ____   (0 absent / 1 BIOS-owned /
                               \ 2 present, BIOS bit clear)
.PORTS                         \ SURVEY #1 — photo/log EVERY line
```

Survey #1 is the pre-reset baseline. Keyboard port expect: `conn en`
with a speed; other ports as found. **Record, don't interpret yet.**

## 4. Handoff + SMI — the real payload

```forth
XHCI-CLAIM .                   \ CLAIM: ____
```

OWNER/CLAIM recorded ADJACENTLY above — "BIOS yielded" (1 then -1) vs
"never held" (2 then -1) are different facts; the pair preserves which.

| CLAIM | meaning | action |
|-------|---------|--------|
| 0  | cap absent (outcome A) | proceed — QEMU-shaped machine |
| -1 | released (outcome B) | proceed |
| 1  | **stuck past 1000 ms (outcome C)** — unmasked `legsup=` printed | **STOP card.** Record the dword. Follow-ups (longer budget, UEFI-native leg) are NOT this trip |

Then SMI-clear — its own step, invoked AFTER you have seen the claim
result. Read-record-conditional-write:

```forth
HEX 1 XECP-FIND DUP . 4 + @ .H8 DECIMAL
\ LEGCTL before: ______________   (this read is the record)
SMI-OFF .                      \ SMI: ____
```

| SMI | meaning | action |
|-----|---------|--------|
| 0  | cap absent | proceed |
| -1 | already clear — **no write occurred; that is a finding** | proceed |
| 1  | enables cleared (Linux-shaped write, E1FEE preserve + E0000000 RW1C) | proceed |
| 2  | **write did not stick** | **STOP card.** Record |

## 4.5 MEMDISK GATE — verified check, not a premise

`XHCI-RESET` kills the controller behind a USB boot stick. The 09-05
docket recorded memdisk residence by operator action only; this gate
replaces that with a kernel-sysvar read (MEMDISK_BASE, 0x28098 —
selects the RAM block path at boot):

```forth
HEX MEMDISK-BASE@ DUP .H8 FFF AND . DECIMAL
\ value: ______________   low-12: ____
```

- [ ] Nonzero AND low-12 = 0 (4 KiB-aligned). Pre-registered from the
      09-05 iron reading **0x37BB7000** (the formerly unnamed cell).
- [ ] **Zero or unaligned ⇒ STOP. Do not type XHCI-RESET.** The
      refusal side is QEMU-proven (check 128); this is the pass side.

## 5. Reset leg — the budget measurement

```forth
USBSTS@ 1 AND .                \ pre-halt HCH: ____ (0 = BIOS left it
                               \ RUNNING — the does-real-work branch)
XHCI-HALT .                    \ must print -1
XHCI-RESET . 1000 HRST-LEFT @ - . 1000 PN @ - .
\ flag ____   HCRST ms ______   CNR ms ______
```

- [ ] **All three reads on the ONE line above** — PN is the shared poll
      counter; any word typed between RESET and the PN read clobbers
      the CNR figure. HRST-LEFT is the only durable HCRST copy.
- [ ] flag 0: the unmasked `.H8` print names which poll — a real dword
      = stuck (record it; budget finding), FFFFFFFF = dead window
      (record; STOP)

## 6. Run leg + survey #2

```forth
XHCI-UP .                      \ -1, or STOP
XHCI-RUN .                     \ -1
DECIMAL 32 NOP-TEST .          \ ____ (32 = ring wrapped twice,
                               \ link-toggle executed on iron)
.PORTS                         \ SURVEY #2 — photo/log EVERY line
```

Survey #2 vs #1, interpreted AT THE MACHINE:

- Keyboard port `conn`, **no** `en`, `7 pls`, CSC set — **EXPECTED**:
  HCRST clears PED on a BIOS-enabled port (2d mechanism, QEMU-proven).
  This is NOT "the port died". Re-enable is step-3's port reset.
- USB3 ports may show PLS changes (retrain) — pre-registered named
  alternative, record as data.
- `15 pls` renders as decimal `15` now (.D fix) — a bare `F` in the
  log means the wrong image booted: STOP, provenance failed.

## 7. Teardown

```forth
XHCI-DOWN .                    \ -1 (or 1 = partial: record which)
PHYS-AUDIT                     \ must be clean
```

## 8. Closeout

- [ ] Evidence log saved: `docs/evidence/xhci-iron-<date>.log`
      (netcon), or photos + **"transcript SKIPPED"** written
- [ ] Record which boot path actually served the image (peer paths:
      FORTHBOOT usb / PXE — this card assumes usb)
- [ ] Re-derive every number from THIS run's own log
- [ ] As-built notes mirrored to the private repo by absolute path

## What each reading settles

- **OWNER/CLAIM pair:** first-ever handoff data on a machine whose
  BIOS can actually own xHCI (QEMU only ever produced 0) — outcome
  B/C decides whether step 3 starts from a claimed or contested
  controller
- **LEGCTL before + SMI code:** whether this BIOS arms SMIs at all
  (bit 4 = Host System Error SMI — armed during the reset leg is the
  worst moment)
- **HCRST/CNR ms:** turns the reasoned 1000 ms budget into a
  measurement on Intel silicon
- **Survey #1 vs #2:** the HCRST-clears-PED mechanism on iron, and
  the port map step 3 will inherit
