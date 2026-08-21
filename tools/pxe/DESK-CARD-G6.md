# G6 DESK CARD — fill in at the desk, carry to the HP

Print this. Fill every blank **before leaving the desk**. Anything still
blank at the laptop is a step you cannot complete there.

Companion to `tools/pxe/RUNBOOK-G6.md` — this card does not replace it.
The runbook carries the STOP conditions and the rollback; this carries
the numbers and the exact lines to type.

> **The runbook is the authority for every line you type.** This card
> carries the *numbers* and the *checkboxes*; where a Forth block is
> long enough that copying it here would create a second version to go
> stale, the card points at the runbook section instead. That is
> deliberate — F1 (2026-08-19) existed because a typed sequence lived in
> two places and one of them drifted. Do not "helpfully" paste the
> blocks back in.

---

## A. Numbers to carry

```
combined.img MD5        ______________________________________
  $ md5sum build/combined.img

INSTALL catalog range   ______  ______   ( "<n> <m> THRU" )
  $ python3 tools/catalog_layout.py INSTALL
  Run against the SAME build/blocks.img you are about to boot.

expected TPL-SUM        ______________
  $ python3 -c "d=open('build/vbr.bin','rb').read(); \
    assert len(d)==512, len(d); print(sum(d))"

forth.img size          ______________ bytes   (aliasing tell #2)
  $ ls -l build/tftp/forth.img

QEMU-green commit       ______________________________________
  $ git rev-parse --short HEAD     (after `make test` exits 0)

make test headline      Passed: ______   over ______ "Passed:" lines
  Re-derive. Do NOT carry 804 forward — it is pinned to c0bb8b4,
  two commits back. Never write 817.

dnsmasq revert line     dhcp-boot=pxelinux.0
  ON PAPER. The rollback cannot live on a netbooted machine.
```

## B. Physically in the bag

- [ ] Linux-EFI USB stick — **booted once, here, now**
- [ ] **Windows recovery media** — the only failure with no
      construction-level recovery is the one where you cannot download it
- [ ] Camera / phone
- [ ] This card

## C. Baseline before anything

```bash
sudo efibootmgr -v          # VERBATIM — photo or transcript
```

- [ ] Captured. If not: write **"G4 recorded SKIPPED"** in the notes.
      Do not infer NVRAM equality later from a baseline never taken.

---

## D. Step 1 — push (at the desk)

```bash
make grub-net && make pxe-push-grub
```

- [ ] `forth.img` MD5 **equals** the `combined.img` MD5 above
- [ ] `Deployed OK: our-files hash …` printed
      (on `ERROR: deployed tree hash … != staged …`, rerun; **do not cut
      dnsmasq over until it passes**)

## E. Step 2 — cutover, then leg B

```
dhcp-boot=pxelinux.0   →   dhcp-boot=grub/i386-pc/core.0
```
then restart dnsmasq.

- [ ] F9 → network boot → **GRUB menu appears**
- [ ] **Let it time out** → memdisk → banner → `ok`
- [ ] Photograph the menu

**STOP if memdisk does not reach `ok`.** The chainload path cannot be
diagnosed on a machine whose baseline boot is broken.
**Rollback = revert that one line.**

---

## F. Step 3 — install, over the net console

**Start the transcript first** — bring-up procedure is runbook §3.0
(listener command, confirmation gate, manual fallback). If the net
console cannot be raised, photograph the screen after every line below
and write **"transcript SKIPPED"** in the notes — do not let it read
like a pass.

### 3a — load and init (harness: `RUNBOOK-3A` markers, drift-gated)

```forth
DECIMAL ______ ______ THRU   \ the two numbers from section A
USING AHCI
AHCI-INIT
ALSO SURVEYOR
USING INSTALL
DECIMAL                \ AHCI-INIT leaves BASE=16; restore it once
```

- [ ] **`DECIMAL` opens the `THRU` line and closes the block** —
      arming step 1. Boot base here is HEX; a bare range loads the
      wrong 200 blocks and *the next probe still prints ok*.
- [ ] `THRU` **before** `AHCI-INIT` — order kept as typed
- [ ] `ALSO SURVEYOR` **before** `USING INSTALL` — the DOVOC trap
- [ ] **Never type `INSTALL-THRU`.** It is not a word.

### 3b — arm the vectors

```forth
' AHCI-READ SEC-READ-VEC !
SEC-BUF RD-BUF-ADDR !
BIND-WRITER AHCI-WRITE
```

### 3c — arm the VBR template (one line + content gate)

```forth
ARM-VBR-TPL .
```

- [ ] Prints `-1`. A `0` means no template — **stop**, everything after
      it is noise.

```forth
: TPL-SUM 0 512 0 DO VBR-RAW I + C@ + LOOP ;
TPL-SUM .              \ must equal ______________ from section A
VBR-RAW 510 + C@ .     \ 85
VBR-RAW 511 + C@ .     \ 170
VBR-TPL @ VBR-RAW = .  \ -1
```

- [ ] Sum matches. **The `-1` above does not prove the bytes** — measured
      2026-08-13, a one-byte flip still returned `-1`. Two gates, and
      they stay two.

### 3d — declare the ESP extent, from the LIVE map

```forth
______ ESP-BASE !
______ ESP-LEN !
ESP-BASE @ .   ESP-LEN @ .
```

- [ ] Values from **this machine's `PARTITION-MAP`**, not from any
      document. R7 cross-check was `[2048, 534527]` → base 2048, len
      532480. **If the live map disagrees, the live map wins** — note the
      discrepancy.
- [ ] `BASE` is decimal. If you came back here after a `HEX`, typing
      `2048` stores **8264** and nothing warns you.

### 3e — survey, claim, install

**Type from `RUNBOOK-G6.md` §3e. Do not type from memory or from this
card** — this is the block F1 was in, and it is the one place where a
stale second copy costs you the session.

Before you start, confirm the runbook in front of you is the patched
one. Three tells, any of which is enough:

- [ ] It cites the **`RUNBOOK-3E-BEGIN/END` markers** (not a bare
      line range) at the top of §3e
- [ ] **`GPT-ARM .` appears BEFORE `MAKE-OWN-ENT`**
- [ ] **Every line ends in `.`** and there is no `-1 . \ sanity` line

If any tell is missing you have the pre-2026-08-19 runbook. **Stop and
get the patched one** — the old block hands `-1` to `ADD-PARTITION` as
its entry pointer, writes garbage into the slot, and *returns `-1`
anyway*.

Record as you go:

```
OWN-BASE  ______________      (where ForthOS landed)
OWN-LEN   ______  (expect 225)
FS-SLOT   ______  (MUST be >= 0 — Bug #33 was this step omitted)
```

- [ ] `MAP-TRUSTED? .` printed `-1` **before** anything wrote
- [ ] `DEPTH .` printed 0 — an after-the-write diagnostic, not a gate
- [ ] Transcript saved

**A refusal at any gate leaves the disk untouched by construction.**

---

## G. Step 4 — G6, two checkboxes

**(a) chainload**

- [ ] Reboot → PXE → GRUB → **SELECT the chainload entry** (do not let it
      time out)
- [ ] **Photograph the menu with the entry highlighted, before Enter**
- [ ] Banner + `ok` on the VGA screen

Aliasing tells, strongest first:

```forth
HEX 28098 @ .  DECIMAL     \ 0 == chainloaded.  The DECIMAL is not
                           \ optional and must be on the same line.
```
- [ ] Photographed. GRUB's keyboard working is **not** evidence ForthOS's
      keyboard path works — different mechanism.
- [ ] Load-time tell: memdisk visibly hauls ______________ bytes over
      TFTP; chainload is near-instant.

If it cannot find the disk it prints `ForthOS: partition GUID not
found` — loud and attributable, not a hang. **But note:** that is also
what an F1-corrupted entry looks like. If you see it on a leg A run,
check `DEPTH` and the slot's GUIDs before blaming `search`.

**(b) Windows still boots**

- [ ] Reboot → Windows boots normally

**This is the whole reason the installer is allowlist-gated.**

## H. If (b) fails — rollback, least invasive first, stop when Windows boots

1. `sudo efibootmgr -o <baseline BootOrder, verbatim from section C>`
2. `sudo efibootmgr -b <NNNN> -B` — **only entries absent from the
   baseline.** Cannot tell which is new? Go to 3.
3. `sudo sgdisk --print /dev/sda` → find slot by GUID
   `32ba60fb-4548-4d4c-a439-fb80ce572b31` →
   `sudo sgdisk --delete=<slot> /dev/sda` → `sudo partprobe /dev/sda`
   **Confirm the GUID. The slot number alone is not identification.**
4. Windows recovery media → Startup Repair, or `bootrec /rebuildbcd`

- [ ] Record which of 1–4 was needed. That is the finding — it tells you
      which layer the installer actually disturbed.

## I. Closeout

- [ ] Photos: GRUB menu, `ok` screen, discriminator, any `DISK ERR`
- [ ] Step 3 transcript saved as a file
- [ ] `sudo efibootmgr -v` after → G4 equality. Else **"G4 SKIPPED."**
- [ ] As-built notes → `docs/TASK_INSTALL_BOOT_ENTRY.md`, mirrored to the
      private repo **by absolute path**, project copy updated. Three
      stores; an edit in one is not an edit in the others.
- [ ] Re-derive every number you write from **this run's own log.**

### Hand-running the harness during the session

```bash
python3 tests/test_g6_chain.py 4595
```

Pass an explicit port. The bare default is 4590 and collides with
`test_meta_does`. Ports bound by other bare-run defaults: **4590–4594,
4598.**
