# DESK CARD — HP 15-bs0xx: xHCI 3d — single-device enumeration on iron

Print this. Fill every blank **before leaving the desk**. Anything still
blank at the laptop is a step you cannot complete there.

This trip's product is the device **enumerated on real hardware** —
Enable Slot → Address Device → GET_DESCRIPTOR → SET_CONFIGURATION on a
keyboard, plus the step-2 leftovers that never ran on iron. It ends at
**Configured**, not at a keystroke; the keystroke is step 4's trip, and
step 4 is not built until this trip answers the unknowns it depends on.
ONE evidence log: `docs/evidence/xhci-3d-iron-<date>.log` (netcon
capture, or the photo protocol with "transcript SKIPPED" written).

**Run in THIS order — cheap unknowns FIRST, abort gate BEFORE any leg
that touches the controller irreversibly:**
bind → **CTX-SIZE abort gate** → survey/speed → PHYS-AUDIT baseline →
unbound-base guards → claim/SMI → **memdisk gate** → reset → up/run →
Enable Slot → Address Device → config-before → configure → config-after
→ teardown → PHYS-AUDIT after.

> Why this order: `CTX-SIZE` is unmeasured on this silicon and
> load-bearing. QEMU reads every context at hardcoded 32-byte stride,
> so it is **structurally incapable** of telling you the iron value.
> If CSZ=1 (64-byte contexts), the entire 3b/3c layout path ran only on
> the 32-byte arm in test. Discover that in the first two minutes, at
> the gate, for free — not after Address Device returns a Parameter
> Error and you debug two layers at once.

> Every STOP below is a real stop: record what printed, take the photo,
> end the leg. A stopped leg with a clean log is a successful trip.

**Dry-run (rule 16):** Sections 2–8 were TYPED into the test-xhci QEMU
fixture on 2026-09-14 (`docs/evidence/xhci-3d-dryrun-2026-09-14.log`,
image f7e8d18e…, THRU 1724 1771): every line parsed, every QEMU-side
expectation printed as written, DEPTH 0 and BASE 10 at exit. Values
marked "iron" below are the HP readings from 2026-09-13, not QEMU's.

---

## 0. Desk prep — deploy provenance (hash the medium against the build)

```bash
git status --porcelain          # clean, or explain before proceeding
git remote -v                   # verified, not assumed
git log --oneline -1            # commit: ______________________ (expect c660e6b or later)
make                            # rebuild; the sweep is already on record (c660e6b, 1319/31)
sha256sum build/combined.img    # BUILD:  1787cdbf114b1e5b670bd31478f644684cb3964dc30c5072d4d6fe14cafba4bb
python3 tools/catalog_layout.py XHCI   # THRU: 1724 1771 THRU (expect 1724 1771, verify)
```

Refresh FORTHBOOT (memdisk boot REQUIRED — Section 5.5 kills the
controller behind the boot medium; a non-memdisk boot loses the stick).
The stick is the vfat volume labelled `FORTHBOOT` made by
`tools/make-uefi-usb.sh`; its GRUB entry memdisk-loads `/forth.img`.
Refreshing is a file copy, NOT a re-run of the script (the script wipes
the stick and defaults to `bmforth.img`, not `combined.img`):

```bash
# stick in the DEV HOST (not the laptop) for this whole block
lsblk -o NAME,LABEL,SIZE,TRAN   # exactly ONE FORTHBOOT, and its TRAN is usb (label failed to resolve twice on 3d)
sudo mount -L FORTHBOOT /mnt/fb
sudo cp build/combined.img /mnt/fb/forth.img && sync
sha256sum /mnt/fb/forth.img build/combined.img   # the two lines MUST match
```
BUILD == STICK: ____ (yes/no)   boot path: USB FORTHBOOT (record if PXE instead)

Start the listener NOW, while the stick is still mounted here — it
hashes `--deployed` at startup and ABORTS on mismatch (that is the
gate). On a USB boot `--deployed` is REQUIRED and must point at the
stick; the default `/srv/tftp/forth.img` is the PXE tree, which a USB
boot never loads, so leaving it off aborts every USB trip on a stale
PXE hash:

```bash
python3 tools/hp-portread-capture.py --boot-path usb \
    --deployed /mnt/fb/forth.img \
    --out docs/evidence/xhci-3d-iron-$(date +%F).log
```
Expect the header to print `hash gate: PASS (deployed == build)` and
`boot path: usb`. Only THEN:

```bash
sudo umount /mnt/fb        # listener keeps running; move the stick to the HP
```
Order matters: refresh → hash → listener up → unmount → stick into the
laptop → Section 1. A listener started after the stick left the dev
host cannot hash it and the log carries no provenance.

## 1. Boot — F9 → FORTHBOOT (memdisk) → banner → `ok`

Session nonce for continuity (grep the banner; a silent warm reset
forges a mid-chain-break signature — see the warm-reset lesson):
NONCE / banner line: ______________________

## 2. Load + gate

```forth
DECIMAL ______ ______ THRU     \ XHCI range from Section 0, THIS build
ONLY FORTH DEFINITIONS
ALSO PCI-ENUM  ALSO XHCI  ALSO HARDWARE
DECIMAL
```
`DEF?` is a SUITE helper, NOT in the loaded vocab — define it HERE
before any use. If you skip it, `DEF?` is undefined, prints `DEF? ?`,
and the twelfth rule lets the REST of the line execute (on 2e that ran
a word on an unbound controller — closure falsification 3, fixed in
ea3441e; this card dropped it again as gap 6). No `BL` before `WORD`
(this kernel's WORD takes no delimiter); FIND leaves the xt, so the
probes print a large NONZERO address, never -1.
```forth
: DEF? WORD FIND NIP ;
```
```forth
DEF? DEF? .            \ self-test: large nonzero.  `DEF? ?` = it did
                       \ not take -- STOP, retype the : line
```
```forth
DEF? ENUM-CONFIGURE .  \ large nonzero; 0 = wrong image
```
A wrong THRU range, or `DEF? ENUM-CONFIGURE` printing 0 (with DEF?
defined), means the stick is not this build. STOP, back to Section 0.

## 3. Bind + the CHEAP UNKNOWNS + ABORT GATE (before any irreversible leg)

```forth
XHCI-BIND .                    \ -1;  0 = device not found, STOP (finding)
```

### 3.1 CTX-SIZE — THE ABORT GATE
```forth
HEX  CTX-SIZE .  DECIMAL        \ expect 20 (32).  40 (64) = ABORT
```
- [ ] **`20` (32-byte contexts):** the path exercised in test. Proceed.
- [ ] **`40` (64-byte contexts) ⇒ STOP THE TRIP.** The offset words
      scale with `CTX-SZ`, so they *should* be correct — but the
      64-byte arm is **unexercised** (QEMU is always 32). Do NOT trust
      Address Device / contexts on the unvalidated path. Record the
      value, end here, validate the 64-byte layout at the desk before
      any slot work. This is the whole reason the gate is first.
- [ ] Any other value ⇒ STOP, `HCC1` misread (finding).

### 3.2 Port survey — find the keyboard, measure its speed
```forth
.PORTS                          \ photo. #CONNECTED . = ______
```
Hot-plug the keyboard now if not already in; `.PORTS` again; the port
whose CCS/CSC flipped is the target. **Record it — do not hardcode.**
```
KEYBOARD PORT (measured): ______     its PORTSC: ________________
```
```forth
______ PORTSC@ P-SPEED .        \ speed of the keyboard port
```
- [ ] **1 (FS) or 2 (LS):** expected — a real boot keyboard. Record which.
- [ ] **3 (HS):** the QEMU fixture value; on iron this is a surprise —
      record it, an HS keyboard is unusual but not fatal (default MPS
      then 64, and 3c's Evaluate Context path handles a mismatch).
- [ ] Note: port 1 is an EXTERNAL socket; its occupant varies (empty on
      the 3d trip until the keyboard went in, then the keyboard). The
      internal HS device is port 2 (0xE03 = the FORTHBOOT stick);
      ports 4/5/7 are internal FS devices. Do not navigate by port
      number — navigate by the survey DIFF (the port whose CCS/CSC
      flipped when you plugged the keyboard). `FIRST-CCS` would pick
      the lowest connected port — the word is fixture-side and absent
      here by design. (QEMU dry-run: the fixture keyboard is port 5,
      speed 3 — a different machine, same method.)

### 3.3 PHYS-AUDIT baseline (step-2 open item: attribute the 7 pages)
```forth
: .OWNERS OWN-CAP 0 DO I OWN-SLOT DUP @ IF DUP 8 + @ U. DUP @ U. DUP 4 + @ U. CR THEN DROP LOOP ;
HEX  PHYS-AUDIT  CR  .OWNERS  DECIMAL     \ photo — this is the baseline
```
Pre-registered (iron 2026-09-13 CONFIRMED): **live 7, unattributed 0,
records 0x103000–0x109000** (4 AHCI + 2 RTL8168 + 1 NTFS boot
allocations, tags 4/2/1 in `.OWNERS`). The audit's own `extents:` line
is the FREE-LIST node count, not an address range: it reads 0 here and
1 after teardown (bump-at-baseline → one coalesced extent) — that
0→1 is NOT a leak (3d finding; QEMU dry-run shows the same 0→1). Any
slot tagged FORTH-CELL, or a count != 7 ⇒ record, it changes the
post-UP delta math.

## 4. Unbound-base guards — five words, first iron run (step-2 leftover)

The guards refuse when `XHCI-BASE @ 0=`. On the 2e trip an unbound
`XHCI-CLAIM` read the real-mode IVT. Verify the refusals on iron, then
restore. (Base is bound from Section 3; save/null/refuse/restore.)
Definition, gate, store on SEPARATE lines (fixed 2026-09-17 when the
step-4 card was cloned from this one: the one-liner had survived here,
so rule 17 cloned it; if `VARIABLE` fails, a same-line `B0 !` writes
the base value into the controller's MMIO window):
```forth
VARIABLE B0
```
```forth
DEF? B0 .              \ large nonzero; 0 = STOP, do not store
```
```forth
XHCI-BASE @ B0 !
```
```forth
0 XHCI-BASE !
XECP-BASE .            \ 0 (refused)
1 XECP-FIND .          \ 0
XHCI-CLAIM .           \ -2 (refused, NOT 0 = cap absent)
SMI-OFF .              \ -2
XHCI-OWNER .           \ -2
B0 @ XHCI-BASE !  XHCI-BASE @ B0 @ = .   \ -1, base restored
```
Any address word printing nonzero, or a wrapper printing 0/1/-1 instead
of -2, under a null base ⇒ STOP (the guard failed open on iron).

## 5. Claim / SMI / reset — reach a running controller (step-2 legs)

Handoff each boot (BIOS re-owns on reset). Survey #1 already taken (3.2).
```forth
XHCI-OWNER .           \ 1 (BIOS owned) expected — pair with CLAIM below
XHCI-CLAIM .           \ -1 released.  1 = stuck past budget: STOP, record legsup
SMI-OFF .              \ -1 (already clear) or 1 (cleared); 2 = STOP
```

### 5.5 MEMDISK GATE — verified, not a premise (before XHCI-RESET)
```forth
HEX  MEMDISK-BASE@ .  DECIMAL   \ nonzero + 4KiB-aligned; prior 37BB7000
```
- [ ] **Nonzero, low 3 nibbles 000 ⇒ memdisk-resident. Proceed.**
- [ ] **Zero or unaligned ⇒ STOP. Do NOT type XHCI-RESET** — reset kills
      the controller behind a non-memdisk boot stick.

```forth
XHCI-HALT .            \ flag
XHCI-RESET .           \ -1
DECIMAL 1000 HRST-LEFT @ - .  \ elapsed ms (DECIMAL: 1000 not HEX 4096)
XHCI-UP .              \ -1, else STOP (allocation failed)
XHCI-RUN .             \ -1 (HCH cleared) — controller running
```
- [ ] `XHCI-UP` on iron allocates SIX records (4 structs + scratchpad
      array + the SP-COUNT-buffer block), not QEMU's 4 — scratchpads
      are REAL here (SP-COUNT 34 on the HP). `SP-COUNT .` if curious.

### 5.9 PORT-RESET the target — VALIDATED ON IRON (defect 6/9)
HCRST (5.5) disabled every port (2d/3d: 0x206E1, PED clear, Polling).
A device in Polling cannot answer USB traffic, and ENUM-ADDRESS reads
its speed into the slot context — off a disabled port that speed is 0
and Address Device fails cc4 two layers from the cause.
```forth
.PORTS
```
- [ ] **The hot-plugged keyboard may be GONE after XHCI-RESET** (3d:
      a firmware-enabled device drops across the reset and does NOT
      self-redetect). If the target port reads empty (0x2A0), **RE-PLUG
      it** before continuing — this is not a broken controller.
```forth
______ PORT-RESET .            \ target port; -1 (PRC seen, PED set)
______ PORTSC@ P-SPEED .       \ VALID speed now: 1 (FS) or 2 (LS)
```
- [ ] `PORT-RESET` = -1 and speed reads 1/2 (not 0). Iron 3d: port ->
      0x603, PED set, U0, speed 1. Only now is the port addressable.

## 6. Enable Slot → Address Device (the 3b payload, first on iron)

```forth
______ ENUM-ADDRESS .          \ keyboard port from 3.2; slot (1..MAX-SLOTS)
XSLOT @ .                      \ same slot
HEX  SLOT-STATE .  DECIMAL      \ 2 (Addressed) — controller wrote the output ctx
```
- [ ] **slot > 0 and `SLOT-STATE` = 2** — addressed.
- [ ] **-3 ⇒ port not enabled: go back to 5.9, PORT-RESET (or RE-PLUG
      then PORT-RESET) that port, retry.** The guard reports the port
      state at the entry, not a cc4 two layers down (3d fix).
- [ ] **0 ⇒ other refusal (unbound / no DCBAA / Enable Slot failed /
      Address Device cc != 1): STOP, record.** If CTX-SIZE read 40 the
      context layout is the suspect — but the 3.1 gate should have
      stopped you before here.

## 7. Configure — the before/after transition, Evaluate Context on iron

### 7.1 Config BEFORE (no deconfigure — the iron pre-registration)
```forth
CFG-STATE .                    \ expect 0 (freshly-addressed = unconfigured)
```
- [ ] **0:** expected. A real just-Addressed keyboard is unconfigured.
- [ ] **nonzero ⇒ FINDING (record, do not paper over):** firmware
      configured the device at USB level — the `XHCI-OWNER=1` family, on
      a BIOS that was driving USB minutes ago. Record the value; the
      transition below is then value→value, note it.

### 7.2 Configure
```forth
ENUM-CONFIGURE .               \ bConfigurationValue (expect 1), 0 = STOP
HEX  CFGCC8 @ .  DECIMAL        \ GET_DESCRIPTOR(8) cc: 1 (Success) or D (short); record
CFGVAL @ .                     \ bConfigurationValue READ from the descriptor (expect 1)
```
This is where **Evaluate Context first runs on real silicon** (if the
keyboard's `bMaxPacketSize0` differs from the speed-derived default).
QEMU could never exercise it in the ENUM path. If ENUM-CONFIGURE returns
0, capture `CFGCC8` and re-run the sub-steps by hand to localize.

### 7.2a Manual localization — BASE discipline (defect 10, 3d trip)
Every hand-typed command line below carries HEX literals (`2C00`,
`18 LSHIFT`). On the trip a localization line was typed after a line
that ended `DECIMAL`: `2C00` failed to parse, `18 LSHIFT` shifted by
18 not 0x18, `CMD-RUN` ran one cell short, the controller answered
cc 5 (TRB Error) to a type-less TRB, and the stack UNDERFLOWED two
cells (DEPTH 0x3FFFFFFE) — a plausible-looking wrong answer. So:
**`HEX` on its own line first, `DEPTH .` before and after, and
`DECIMAL` on its own line at the end.** A DEPTH that is not 0 (or
prints a huge number) means the previous line did not parse — STOP,
do not type the next command on top of it.
```forth
DEPTH .                        \ 0 before you start
```
```forth
HEX
```
```forth
ENABLE-SLOT . .                \ prints "<slot> <cc>": cc 1, a NEW slot (not XSLOT)
```
```forth
DEPTH .                        \ 0 — the line consumed what it pushed
```
```forth
______ DISABLE-SLOT .          \ that new slot; cc 1 (release it: not tracked by SLOT-DOWN)
```
```forth
DECIMAL
```
Address Device by hand (only if ENABLE-SLOT above was fine and
`XSLOT @` is the addressed slot): `HEX` line first, then
`XICTX @ 0 0 XSLOT @ 18 LSHIFT 2C00 OR CMD-RUN . .`, then `DEPTH .`,
then `DECIMAL`. Do NOT retype it on a device that already reached
Addressed — a second Address Device on an addressed slot is a
Context State Error (cc 13 hex / 19) by spec, not a localization.
(Dry-run 2026-09-14: the ENABLE-SLOT block above printed `2 1` and
DEPTH 0 on QEMU.)

### 7.3 Config AFTER
```forth
CFG-STATE .                    \ = CFGVAL (transition observed on iron)
```

## 8. Teardown + leak check

```forth
SLOT-DOWN .                    \ -1 (all released), 1 = partial (record)
XHCI-DOWN .                    \ -1
HEX  PHYS-AUDIT  CR  .OWNERS  DECIMAL     \ MUST equal the 3.3 baseline
```
Post-teardown audit != baseline ⇒ leak of k records; the owner tag is in
the log. Record both audits verbatim.

## 9. Closeout

- [ ] Evidence log saved: `docs/evidence/xhci-3d-iron-<date>.log`
- [ ] BUILD hash and boot path recorded (Section 0)
- [ ] Every STOP that fired: value recorded + photo
- [ ] Session nonce present at exit (no silent warm reset)

## What each reading settles

| Reading | Settles |
|---|---|
| CTX-SIZE (3.1) | whether 3b/3c contexts are on a validated path; the abort gate |
| keyboard speed (3.2) | FS/LS vs the QEMU HS fixture; the EP0 default MPS |
| PHYS-AUDIT baseline (3.3) | the step-2 open item: attribute the 7 live pages |
| unbound guards (4) | the guards refuse fail-closed on iron, not just QEMU |
| config-before (7.1) | is the device firmware-configured? (XHCI-OWNER family) |
| CFGCC8 (7.2) | GET_DESCRIPTOR(8) completion code on real silicon |
| Evaluate Context (7.2) | 64-byte / MPS-correction acceptance — untestable on QEMU |
| PHYS-AUDIT after (8) | no leak across the full enumerate/teardown cycle |

**Step 4 waits for this trip's answers.** Do not build Configure
Endpoint + HID interrupt-IN on an unvalidated CTX-SIZE.
