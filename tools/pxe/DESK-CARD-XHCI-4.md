# DESK CARD — HP 15-bs0xx: xHCI step 4 — Configure Endpoint + one keystroke on iron

Print this. Fill every blank **before leaving the desk**. Anything still
blank at the laptop is a step you cannot complete there.

Successor of `DESK-CARD-XHCI-3D.md` (rule 17: every 3D fix is ported
forward here; its closure falsifications are checked below). Sections
0–7 are 3D's proven legs, re-run because every trip re-enumerates
from a cold controller. The product of THIS trip is **one keystroke
from the real keyboard landing in a Forth buffer via a
controller-scheduled interrupt-IN transfer** — Sections 8–10. It ends
at "report bytes read", NOT at `KEY` returning it.
ONE evidence log: `docs/evidence/xhci-4-iron-<date>.log`.

**Run in THIS order — cheap unknowns FIRST, abort gate BEFORE any leg
that touches the controller irreversibly:**
bind → **CTX-SIZE abort gate** → survey/speed → PHYS-AUDIT baseline →
unbound guards → claim/SMI → **memdisk gate** → reset → up/run →
**PORT-RESET (re-plug if gone)** → Enable Slot/Address Device →
configure → **ENUM-HID** → **poll (no key / key / release / wrap)** →
Stop Endpoint → **HID-DOWN** → SLOT-DOWN → XHCI-DOWN → PHYS-AUDIT after.

> Every STOP below is a real stop: record what printed, take the photo,
> end the leg. A stopped leg with a clean log is a successful trip.

> **Two physical-0 hazards learned on QEMU (2026-09-16), both about
> commands issued without a valid context or ring:** (1) Configure
> Endpoint on a slot with no valid output context makes the controller
> read AND DMA-write physical 0 (the IVT); (2) any command word with
> no command ring (XHCI-UP not run) writes its TRB at physical 0.
> Nothing on this card issues a command before `XHCI-UP` reads -1 and
> `ENUM-ADDRESS` returns a slot; do not type 7.2a's or 10.2's manual
> blocks out of order.

**Dry-run (rule 16):** Sections 2–11 are TYPED into the test-xhci QEMU
fixture by `tools/pxe/dryrun-card.py`, which extracts this file's
fenced forth blocks in order, so the log is this card's own text
(blanks filled with the fixture's THRU range and port; key presses via
the monitor; a prose line must never begin with a fence marker, or the
tool types the prose: that happened once on 2026-09-17, DEPTH 6 at
exit, and the run was repeated). Status: **DONE 2026-09-17**,
`docs/evidence/xhci-4-dryrun-2026-09-17.log`, image a68b406be0526186…,
THRU 1724 1782, every line parsed, DEPTH 0 and BASE 10 at exit. Values
that differ on QEMU from the iron expectations printed beside the
lines, all anticipated: XHCI-OWNER/CLAIM/SMI-OFF read 0 (cap absent);
MEMDISK-BASE@ reads 0 (no memdisk: the 5.5 STOP is an iron rule);
CFG-STATE reads 1 BEFORE SET (QEMU configures usb-kbd at realize; iron
read 0 on 3D); keyboard HS on port 5 (bInterval 7 → interval 6). The
first dry-run attempt typed the pre-fix card and was discarded, log
renamed `…-DISCARDED-not-the-card.log`.

**Iron values from 3D (2026-09-13) that this card relies on:** CTX-SIZE
0x20 (32-byte contexts: the arm exercised in test); keyboard on the
EXTERNAL port 1, FULL speed (P-SPEED 1); a firmware-enabled device
drops across XHCI-RESET and must be RE-PLUGGED; CFG-STATE reads 0
before SET on iron; scratchpads real (SP-COUNT 34, 6 records at UP).

---

## 0. Desk prep — deploy provenance (hash the medium against the build)

```bash
git status --porcelain          # clean, or explain before proceeding
git remote -v                   # verified, not assumed
git log --oneline -1            # commit: ______________________ (expect ce2ff55 or later)
make                            # rebuild; the sweep is on record (ce2ff55: 1386/31 sum, 1374 lines)
sha256sum build/combined.img    # BUILD: a68b406be0526186bb13d0b820e0b826fbadf0fa90a5ffdfe41e323e53333036
python3 tools/catalog_layout.py XHCI   # THRU: 1724 1782 THRU (the vocab GREW in step 4; verify, do not copy 3D's 1771)
```

Refresh FORTHBOOT (memdisk boot REQUIRED — Section 5.5 kills the
controller behind the boot medium; a non-memdisk boot loses the stick).
The stick is the vfat volume labelled `FORTHBOOT` made by
`tools/make-uefi-usb.sh`; its GRUB entry memdisk-loads `/forth.img`.
Refreshing is a file copy, NOT a re-run of the script (the script wipes
the stick and defaults to `bmforth.img`, not `combined.img`):

```bash
# stick in the DEV HOST (not the laptop) for this whole block
lsblk -o NAME,LABEL,SIZE,TRAN   # exactly ONE FORTHBOOT, and its TRAN is usb
sudo mount -L FORTHBOOT /mnt/fb
sudo cp build/combined.img /mnt/fb/forth.img && sync
sha256sum /mnt/fb/forth.img build/combined.img   # the two lines MUST match
```
BUILD == STICK: ____ (yes/no)   boot path: USB FORTHBOOT (record if PXE instead)

Start the listener NOW, while the stick is still mounted here — it
hashes `--deployed` at startup and ABORTS on mismatch (that is the
gate). On a USB boot `--deployed` is REQUIRED and must point at the
stick:

```bash
python3 tools/hp-portread-capture.py --boot-path usb \
    --deployed /mnt/fb/forth.img \
    --out docs/evidence/xhci-4-iron-$(date +%F).log
```
Expect the header to print `hash gate: PASS (deployed == build)` and
`boot path: usb`. Only THEN:

```bash
sudo umount /mnt/fb        # listener keeps running; move the stick to the HP
```
Order matters: refresh → hash → listener up → unmount → stick into the
laptop → Section 1.

## 1. Boot — F9 → FORTHBOOT (memdisk) → banner → `ok`

Session nonce for continuity (grep the banner; a silent warm reset
forges a mid-chain-break signature):
NONCE / banner line: ______________________

## 2. Load + gate

```forth
DECIMAL ______ ______ THRU     \ XHCI range from Section 0, THIS build (expect 1724 1782)
ONLY FORTH DEFINITIONS
ALSO PCI-ENUM  ALSO XHCI  ALSO HARDWARE
DECIMAL
```
`DEF?` is a SUITE helper, NOT in the loaded vocab — define it HERE
before any use. No `BL` before `WORD` (this kernel's WORD takes no
delimiter); FIND leaves the xt, so the probes print a large NONZERO
address, never -1.
```forth
: DEF? WORD FIND NIP ;
```
```forth
STATE @ .              \ 0: the definition closed (Bug #31: a broken : leaves STATE 1)
```
```forth
DEF? DEF? .            \ self-test: large nonzero.  `DEF? ?` = it did
                       \ not take -- STOP, retype the : line
```
```forth
DEF? ENUM-HID .        \ large nonzero; 0 = wrong image (a 3D-era stick)
```
```forth
DEF? HID-POLL .        \ large nonzero
```
A wrong THRU range, or either probe printing 0 (with DEF? defined),
means the stick is not this build. STOP, back to Section 0.

## 3. Bind + the CHEAP UNKNOWNS + ABORT GATE

```forth
XHCI-BIND .                    \ -1;  0 = device not found, STOP (finding)
```

### 3.1 CTX-SIZE — THE ABORT GATE (iron 3D: 20)
```forth
HEX  CTX-SIZE .  DECIMAL        \ expect 20 (32).  40 (64) = ABORT
```
- [ ] **`20`:** the path exercised in test and confirmed on this
      silicon on 3D. Proceed.
- [ ] **`40` ⇒ STOP THE TRIP** (a different controller or a firmware
      change): the 64-byte arm is unexercised on iron; `I-EPN`/`O-EPN`
      scale with CTX-SZ but nothing has proven the controller accepts
      the 64-byte endpoint layout. Record, end here.
- [ ] Any other value ⇒ STOP, `HCC1` misread (finding).

### 3.2 Port survey — find the keyboard, measure its speed
```forth
.PORTS                          \ photo. #CONNECTED . = ______
```
Hot-plug the keyboard now if not already in; `.PORTS` again; the port
whose CCS/CSC flipped is the target. **Record it — do not hardcode.**
Port 1 is the EXTERNAL socket (empty until the keyboard went in on 3D);
port 2 (0xE03) is the FORTHBOOT stick; 4/5/7 are internal FS devices.
Navigate by the survey DIFF, never by number.
```
KEYBOARD PORT (measured): ______     its PORTSC: ________________
```
```forth
______ PORTSC@ P-SPEED .        \ speed of the keyboard port (3D: 1)
```
- [ ] **1 (FS) or 2 (LS):** expected. Record which — it selects the
      interval encoding in Section 8 (`INTERVAL-FS`).
- [ ] **3 (HS):** a surprise on iron (QEMU's fixture value); record it.
      `BUILD-EPCTX` then uses `INTERVAL-HS`; nothing else changes.
- [ ] Speed is meaningful ONLY on an enabled/U0 port (3D correction:
      a Polling port's speed field is noise). Re-read it after 5.9.

### 3.3 PHYS-AUDIT baseline (3D: live 7, unattributed 0, tags 4/2/1)
Gate the helper's inputs before defining it (twelfth rule: a `:` line
over an undefined word compiles a broken definition that the next
line then runs):
```forth
DEF? OWN-CAP .         \ large nonzero
```
```forth
DEF? OWN-SLOT .        \ large nonzero; 0 on either = STOP (allocator words absent)
```
```forth
: .OWNERS OWN-CAP 0 DO I OWN-SLOT DUP @ IF DUP 8 + @ U. DUP @ U. DUP 4 + @ U. CR THEN DROP LOOP ;
```
```forth
STATE @ .              \ 0 (closed)
```
```forth
HEX  PHYS-AUDIT  CR  .OWNERS  DECIMAL     \ photo — this is the baseline
```
The audit's `extents:` line is the FREE-LIST node count (0 here, 1
after teardown; that 0→1 is NOT a leak, 3D finding). Any slot tagged
FORTH-CELL, or a count != 7 ⇒ record, it changes the delta math.

## 4. Unbound-base guards — five words (3D: 5/5 fail-closed on iron)

Definition, gate, store on SEPARATE lines: if `VARIABLE` fails, a
same-line `B0 !` pops the base value as an ADDRESS and writes into
the controller's MMIO window (iron: B1210000).
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
```
Step-4 words, same null base (new on this card; suite checks 30/33):
```forth
ENUM-HID .             \ 0 (refused, no DMA write)
```
```forth
HID-POLL .             \ 0 (refused: no slot, no ring)
```
```forth
B0 @ XHCI-BASE !  XHCI-BASE @ B0 @ = .   \ -1, base restored
```
Any address word printing nonzero, or a wrapper printing 0/1/-1 instead
of -2, or ENUM-HID/HID-POLL printing anything but 0 under a null base
⇒ STOP (a guard failed open on iron).

## 5. Claim / SMI / reset — reach a running controller

```forth
XHCI-OWNER .           \ 1 (BIOS owned) expected — pair with CLAIM below
XHCI-CLAIM .           \ -1 released.  1 = stuck past budget: STOP, record legsup
SMI-OFF .              \ -1 (already clear) or 1 (cleared); 2 = STOP
```

### 5.5 MEMDISK GATE — verified, not a premise (before XHCI-RESET)
```forth
HEX  MEMDISK-BASE@ .  DECIMAL   \ nonzero + 4KiB-aligned; 3D: 37BB7000
```
- [ ] **Nonzero, low 3 nibbles 000 ⇒ memdisk-resident. Proceed.**
- [ ] **Zero or unaligned ⇒ STOP. Do NOT type XHCI-RESET.**

```forth
XHCI-HALT .            \ flag
XHCI-RESET .           \ -1
DECIMAL 1000 HRST-LEFT @ - .  \ elapsed ms (DECIMAL: 1000 not HEX 4096; 3D: 1)
XHCI-UP .              \ -1, else STOP (allocation failed) — NO command word before this reads -1
XHCI-RUN .             \ -1 (HCH cleared) — controller running
```
- [ ] `XHCI-UP` on iron allocates SIX records (scratchpads real).

### 5.9 PORT-RESET the target — validated on 3D; RE-PLUG if gone
HCRST disabled every port. **The hot-plugged keyboard may be GONE
after XHCI-RESET** (3D: 0x603 → 0x2A0, no self-redetect).
```forth
.PORTS
```
- [ ] If the target port reads empty (0x2A0), **RE-PLUG the keyboard**,
      `.PORTS` again (expect 0x206E1: connected + CSC), then:
```forth
______ PORT-RESET .            \ target port; -1 (PRC seen, PED set)
______ PORTSC@ P-SPEED .       \ VALID speed now: 1 (FS) or 2 (LS); 3D: 0x603, speed 1
```
- [ ] `PORT-RESET` = -1 and speed reads 1/2 (not 0). Only now is the
      port addressable. Record the speed here: ______ (feeds Section 8).

## 6. Enable Slot → Address Device (3D: validated at FS/mps 8)

```forth
______ ENUM-ADDRESS .          \ keyboard port; slot (1..MAX-SLOTS)
XSLOT @ .                      \ same slot
HEX  SLOT-STATE .  DECIMAL      \ 2 (Addressed)
```
- [ ] **slot > 0 and `SLOT-STATE` = 2.**
- [ ] **-3 ⇒ port not enabled: back to 5.9 (re-plug, PORT-RESET), retry.**
- [ ] **0 ⇒ other refusal: STOP, record.** (7.2a of the 3D card has the
      manual localization with its BASE discipline; use it verbatim.)

## 7. Configure (3D: 0 → 1 observed on iron)

```forth
CFG-STATE .                    \ 0 expected (3D confirmed); nonzero = record, continue
ENUM-CONFIGURE .               \ bConfigurationValue (expect 1), 0 = STOP
HEX  CFGCC8 @ .  DECIMAL        \ 1 or D; record
CFG-STATE .                    \ = CFGVAL (transition)
```

## 8. ENUM-HID — full config read, walker, Configure Endpoint (NEW; first on iron)

What iron can answer here that QEMU could not: the real keyboard's
`bInterval` and its FS interval encoding on a real scheduler; whether
the controller accepts the Interrupt-IN endpoint context (64-byte
acceptance is moot at CTX-SIZE 20); SET_PROTOCOL's real completion
code; the residual of a real full-config read.
```forth
DEPTH .                        \ 0 before the leg
```
```forth
ENUM-HID .                     \ -1;  0 = STOP (localize with 8.1)
```
- [ ] **-1:** endpoint found, Configure Endpoint cc 1, ring + buffer
      allocated (+2 records vs the 3.3 baseline until HID-DOWN).
- [ ] **0 ⇒ STOP, record, then 8.1.** Do NOT retype ENUM-HID on a slot
      that already reached -1 (it refuses: XEP1R live).

Readings (all recorded whatever they say; iron predictions beside):
```forth
HID-EPADDR @ .                 \ 129 (0x81 = EP1 IN) predicted; any 0x8n recorded
HID-MPS @ .                    \ 8 predicted (boot keyboard); record
HID-BINT @ .                   \ PREDICTED 8 or 10 (FS, ms frames); QEMU's HS value was 7; ANY 1..255 legal, record
HID-DCI @ .                    \ 3 predicted (2*1+1); = 2*EP + 1 for whatever EPADDR read
HID-IFACE @ .                  \ 0 predicted (single interface); a media-keys keyboard may read 1
GD-RESID @ .                   \ 0 predicted (full read landed); nonzero = short read, record
```
```forth
HEX  XODC @ @ 1B RSHIFT .  DECIMAL     \ output slot ctx entries: 3 (controller wrote it)
```
```forth
HEX  XODC @ HID-DCI @ O-EPN @ 7 AND .  DECIMAL   \ output EP ctx state: 1 (Running)
```
```forth
HEX  XICTX @ HID-DCI @ I-EPN @ 10 RSHIFT FF AND .  DECIMAL   \ interval field we wrote: 6 predicted for bInt 8 or 10 (3+floor(log2)); 3 for bInt 1; A for 255
```
```forth
HIDCC-PROT @ .                 \ SET_PROTOCOL cc: 1 predicted; 6 (STALL) = FINDING, not a failure
```
```forth
DEPTH .                        \ 0
```
- [ ] Output EP state 1 (Running) and entries 3 ⇒ the controller
      accepted the Interrupt-IN endpoint context on real silicon.
      **This is the step's first iron finding; photo it.**

### 8.1 Localization if ENUM-HID returned 0 (BASE discipline: HEX line, DEPTH after)
The refusal order inside ENUM-HID: no base / no slot / already
configured / config-descriptor read failed / no interrupt-IN endpoint
found / ring or buffer allocation / Configure Endpoint cc ≠ 1. Read
the cells that ENUM-HID fills BEFORE it fails: `HID-EPADDR @ .` = 0
means the walker found nothing (dump the descriptor: it is gone with
XDBUF, so re-read it by hand: `4096 PHYS-ALLOC` into a variable, `2 0
9 <buf> GET-DESC .`, then bytes 2-3 = wTotalLength, then `2 0 <total>
<buf> GET-DESC .` and `<buf> <total> EP-FIND .`); nonzero EPADDR with
0 from ENUM-HID means Configure Endpoint refused: re-run
`CONFIGURE-EP .` by hand ONLY IF `XEP1R @ .` is nonzero (a ring
exists) — its cc is the finding (5 TRB Error = flags; 17 Parameter
Error = a context field iron rejects; 19 = slot state). `DEPTH .`
after every line.

## 9. The keystroke — poll discipline (NEW; the trip's product)

**Read discipline (ruling 2026-09-14):** `HIDBUF` is read ONLY on the
line AFTER a `HID-POLL` that printed a nonzero cc. While a TRB is
pending the controller may write the buffer at any moment; a read
between polls is a race, not a reading. Gate and gated never share a
line.

### 9.1 No key — the NAK-is-silent model
Touch nothing. Then:
```forth
HID-POLL .                     \ 0 (timeout, ~0x100 ms budget): the TRB is LEFT PENDING
```
```forth
HID-PEND @ .                   \ -1 (pending, not re-enqueued)
```
- [ ] 0 then -1: the controller is scheduling the IN token every ESIT
      and the device NAKs silently, exactly as designed. Any nonzero cc
      here with no key pressed = a spontaneous report (record the
      bytes on the NEXT line, then continue; some keyboards send an
      all-zero report on configure).

### 9.2 One key — press and HOLD `a`, then type the poll line
(The report arrives on the next scheduled IN; holding avoids the
release report racing the poll.)
```forth
HID-POLL .                     \ cc: 1 (Success) predicted; D (13, Short Packet) also OK
```
Only if the previous line printed 1 or 13:
```forth
HEX  HIDBUF @ 2 + C@ .  HIDBUF @ C@ .  DECIMAL   \ 4 0  (usage 'a', no modifier)
```
- [ ] **`4 0` ⇒ ONE KEYSTROKE FROM THE REAL KEYBOARD LANDED IN A FORTH
      BUFFER VIA A CONTROLLER-SCHEDULED INTERRUPT-IN TRANSFER. Photo.
      This is the step-4 product.**
- [ ] cc 4 (USB Transaction Error) or 6 (STALL) ⇒ record; check the
      keyboard is still on its port (`.PORTS`); STOP the poll leg.
Now RELEASE the key, then:
```forth
HID-POLL .                     \ cc 1/13: the release report
```
```forth
HEX  HIDBUF @ 2 + C@ .  DECIMAL   \ 0 (no key)
```

### 9.3 Ring wrap — forced on iron by hand (16 reports over a 15-slot ring)
Press and release EIGHT different keys, one at a time, WITHOUT polling
between them (the device queues reports; a real keyboard's queue depth
is unknown — record how many polls return a report). Then poll until
a poll returns 0:
```forth
HID-POLL .   \ repeat this line; count nonzero returns: ______ (predicted 16; fewer = device queue depth, a finding)
```
```forth
HEX  XEP1ENQ @ .  XEP1CCS @ .  DECIMAL   \ ENQ < F and CCS 0 if 16+ TRBs went through (wrapped once)
```
### 9.4 After the wrap — one more key must still land (Link TRB followed)
(Dry-run 2026-09-17 found this as prose, never typed: rule 16.)
Press and HOLD `j`, then:
```forth
HID-POLL .                     \ cc 1/13
```
```forth
HEX  HIDBUF @ 2 + C@ .  DECIMAL   \ D (13 = usage 'j'); any other key's usage if you pressed another
```
Release, then:
```forth
HID-POLL .                     \ cc 1/13: the release report
```
- [ ] A report landed on the ring's second lap: the controller followed
      the Link TRB on real silicon.

## 10. Stop Endpoint + the slot-state question (NEW)

```forth
HEX  5 STOP-EP .  DECIMAL       \ C (12, Endpoint Not Enabled): DCI 5 was never enabled — forced control
```
```forth
HEX  HID-DCI @ STOP-EP .  DECIMAL   \ 1
```
```forth
HEX  XODC @ HID-DCI @ O-EPN @ 7 AND .  DECIMAL   \ 3 (Stopped): controller wrote the state
```
- [ ] 12 / 1 / 3 as predicted. The ring is now stopped; do NOT poll
      again (re-arming needs Set TR Dequeue, out of scope).

### 10.2 OPTIONAL — does iron cache the slot state? (QEMU control 55, iron unknown)
On QEMU the controller re-reads the output slot context's state field
on every Configure Endpoint, so poking it to 1 (Enabled) forces cc 19.
A real controller may cache slot state internally and ignore the poke.
Either answer is a finding. Skip this block if anything above STOPped.
```forth
DEPTH .
```
```forth
HEX
```
```forth
XODC @ C + @ DUP . 7FFFFFF AND 8000000 OR XODC @ C + !   \ prints saved dword3 (18000001-ish); state := 1
```
```forth
CONFIGURE-EP .                 \ 13 (=19, Context State Error) = iron re-reads state; 1 = iron CACHED it (finding either way)
```
```forth
DEPTH .
```
Restore from the value the poke line PRINTED (HEX is still active;
`<saved>` is that value, typed by hand, e.g. `18000001`):
```forth
<saved> XODC @ C + !           \ <saved> = the dword3 printed by the poke line
```
```forth
XODC @ C + @ 1B RSHIFT .       \ 3 (Configured) restored
```
```forth
DECIMAL
```

## 11. Teardown + leak check (+2 records must go away)

```forth
HID-DOWN .                     \ -1 (ring + buffer released; Stop Endpoint on a stopped ring is accepted), 1 = partial (record)
```
```forth
SLOT-DOWN .                    \ -1
```
```forth
XHCI-DOWN .                    \ -1
```
```forth
HEX  PHYS-AUDIT  CR  .OWNERS  DECIMAL     \ MUST equal the 3.3 baseline (live 7)
```
Post-teardown audit != baseline ⇒ leak of k records; the owner tag is
in the log. Record both audits verbatim.

## 12. Closeout

- [ ] Evidence log saved: `docs/evidence/xhci-4-iron-<date>.log`
- [ ] BUILD hash and boot path recorded (Section 0)
- [ ] Every STOP that fired: value recorded + photo
- [ ] Session nonce present at exit (no silent warm reset)
- [ ] Every "record" cell above filled (BINT, IFACE, RESID, HIDCC-PROT,
      wrap count, 10.2 answer)

## What each reading settles

| Reading | Settles |
|---|---|
| CTX-SIZE (3.1) | still 32 on this silicon; the endpoint layout arm in test is the one in use |
| keyboard speed (5.9) | FS/LS → `INTERVAL-FS` is the encoding under test |
| HID-BINT + interval field (8) | the FS interval formula against a real device's bInterval |
| output EP state 1 (8) | iron accepts the Interrupt-IN endpoint context (QEMU accepted it; iron may not) |
| HIDCC-PROT (8) | SET_PROTOCOL on real firmware (1, or 6 = a finding, not a failure) |
| 9.1 | NAK-is-silent on a real scheduler; TRB stays pending across a timeout |
| 9.2 | **the product**: one report via periodic interrupt-IN |
| 9.3 | Link TRB followed on iron; the device's report queue depth |
| 10 | Stop Endpoint codes on iron (12 / 1 / state 3) |
| 10.2 | whether iron re-reads or caches slot state (QEMU: re-reads) |
| PHYS-AUDIT after (11) | +2 records released; no leak across the HID leg |

**3D closure falsifications carried forward:** the XDBUF-leak
prediction (baseline+1) was falsified on 3D and resolved by citation
(XDBUF released inline); this card's +2 delta is ring + HIDBUF only,
both released by HID-DOWN. The 3D contamination (a pasted grep line
executing `BUILD-ICTX` unguarded) is why every manual block here has
`DEPTH .` before and after and why nothing is pasted from a terminal
into the netcon.
