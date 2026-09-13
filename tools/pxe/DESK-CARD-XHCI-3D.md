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

---

## 0. Desk prep — deploy provenance (hash the medium against the build)

```bash
git status --porcelain          # clean, or explain before proceeding
git remote -v                   # verified, not assumed
git log --oneline -1            # commit: ______ (MUST match c660e6b, the sweep tree)
make                            # rebuild the image only (see sweep note below)
sha256sum build/combined.img    # BUILD:  ________________________________
python3 tools/catalog_layout.py XHCI   # THRU: ______ ______ (expect 1724 1771, verify)
```

Refresh FORTHBOOT (memdisk boot REQUIRED — the memdisk gate (5.5) kills the
controller behind the boot medium; a non-memdisk boot loses the stick):

```
#                                 STICK:  ________________________________
```
The sweep is NOT re-run on trip day (cadence ruling): `docs/evidence/sweep-2026-09-12.log` already measured THIS tree (c660e6b) at 1319/31, all suites green. Re-run `make test` ONLY if `git log` does not match c660e6b.

Hash-verify the stick against BUILD before the laptop. Record the boot
path used (USB FORTHBOOT / PXE). BUILD == STICK: ____ (yes/no)

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
DEF? ENUM-CONFIGURE .           \ nonzero, else wrong image: STOP, Section 0
```
A wrong THRU range or `DEF? ENUM-CONFIGURE` = 0 means the stick is not
this build. STOP, back to Section 0.

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
- [ ] Note: port 1 is the internal HS device (enabled pre-HCRST on the
      2e trip). It is NOT the target. `FIRST-CCS` would pick it — the
      word is fixture-side and absent here by design.

### 3.3 PHYS-AUDIT baseline (step-2 open item: attribute the 7 pages)
```forth
DEF? OWN-CAP .          \ nonzero (req'd before the : line)
DEF? OWN-SLOT .         \ nonzero (req'd before the : line)
\ .OWNERS is ONE definition typed across the lines below (the
\ interpreter reads to the ;).  No line wraps on the printout.
: .OWNERS  OWN-CAP 0 DO
    I OWN-SLOT  DUP @ IF
      DUP 8 + @ U.  DUP @ U.  DUP 4 + @ U.  CR
    THEN  DROP
  LOOP ;
STATE @ .   \ MUST be 0 (a bad name mid-def zeroes STATE)
HEX  PHYS-AUDIT  CR  .OWNERS  DECIMAL   \ photo: baseline
```
Pre-registered: **live 7, unattributed 0, extents 0x103000-0x109000**
(4 AHCI + 2 RTL8168 + 1 NTFS boot allocations). Any slot tagged
FORTH-CELL, or a count != 7 ⇒ record, it changes the post-UP delta math.

## 4. Unbound-base guards — five words, first iron run (step-2 leftover)

The guards refuse when `XHCI-BASE @ 0=`. On the 2e trip an unbound
`XHCI-CLAIM` read the real-mode IVT. Verify the refusals on iron, then
restore. (Base is bound from Section 3; save/null/refuse/restore.)

> **If any refusal below reads wrong, type `B0 @ XHCI-BASE !` FIRST,
> then stop.** Stopping with the base still null makes every later word
> refuse correctly — which looks exactly like a dead controller and
> sends the diagnosis to the wrong layer.

Define B0 on its own line — a `VARIABLE` and a `!` on one line with a
live value on the stack is the twelfth-rule trap: if the define fails,
`!` writes that value into the controller's MMIO base.
```forth
VARIABLE B0
```
```forth
DEF? B0 .                      \ nonzero
```
```forth
XHCI-BASE @ B0 !  B0 @ 0<> .   \ -1 (base saved)
0 XHCI-BASE !
XECP-BASE .            \ 0 (refused)
1 XECP-FIND .          \ 0
XHCI-CLAIM .           \ -2 (refused, NOT 0 = cap absent)
SMI-OFF .              \ -2
XHCI-OWNER .           \ -2
B0 @ XHCI-BASE !  XHCI-BASE @ B0 @ = .   \ -1, base restored
```
Any address word printing nonzero, or a wrapper printing 0/1/-1 instead
of -2, under a null base ⇒ restore the base (above), then STOP (the
guard failed open on iron).

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
XHCI-RESET .           \ -1;  HEX 1000 HRST-LEFT @ -  = elapsed ms (record)
XHCI-UP .              \ -1, else STOP (allocation failed)
XHCI-RUN .             \ -1 (HCH cleared) — controller running
```

## 6. Enable Slot → Address Device (the 3b payload, first on iron)

```forth
______ ENUM-ADDRESS .          \ keyboard port from 3.2; prints slot (1..MAX-SLOTS), 0 = STOP
XSLOT @ .                      \ same slot
HEX  SLOT-STATE .  DECIMAL      \ 2 (Addressed) — the controller wrote the output ctx
```
- [ ] slot nonzero, `SLOT-STATE` = 2. Any Parameter Error path inside
      ENUM-ADDRESS returns 0 ⇒ STOP, record; if CTX-SIZE was 40 this is
      the layer that fails (but the 3.1 gate should have stopped you).

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
