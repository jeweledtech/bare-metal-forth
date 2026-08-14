# RUNBOOK-G6 — iron boot-chain session (HP 15-bs0xx)

Operator checklist for proving ForthOS boots from the disk it
installed itself onto: PXE → iPXE → TFTP → GRUB → chainload into
ForthOS's own VBR → kernel.

**Read this at the desk before leaving it.** Steps 0 and 1 are
desk work; 2 onward are at the laptop. Every step has a stated
STOP condition. A step that cannot be completed is recorded
**SKIPPED, in that word** — a skip must not read like a pass.

**Location note:** this file lives in `tools/pxe/`, deliberately
NOT in `docs/TASK_*.md`, which a blanket gitignore hides from the
project side. (The ATAPI work was iron-green and invisible for
weeks for exactly that reason.)

---

## Step 0 — Session prerequisites (at the desk)

- [ ] **Linux-EFI USB stick exists and is BOOT-VERIFIED.** Boot it
      once, here, now. An unbootable stick discovered at the HP
      turns G4 into a skip for want of ten minutes of prep.
- [ ] **`build/combined.img` MD5 noted** (write it down; you will
      compare against what the server prints in step 1):
      ```bash
      md5sum build/combined.img
      ```
- [ ] **Windows recovery media, physically present.** Required by
      step 4(c), which is the only failure in this session with no
      construction-level recovery. Bring it even though you expect
      not to need it: the step that needs it is the step where the
      laptop no longer boots the OS you would download it from.
- [ ] **dnsmasq revert line on paper or phone.** The rollback must
      not depend on the thing being rolled back — if the cutover
      breaks PXE, you cannot read the rollback off a netbooted
      machine.
- [ ] **QEMU-green commit hash** the pushed tree was built from.
      Record it; it is what "this session tested THAT build" means
      later.

### G4/R2 baseline — `efibootmgr -v` BEFORE anything

Vehicle: F9 → "Boot from EFI File" → the stick. (An `x86_64-efi`
`grub-mknetdir` netboot of Linux is the noted fallback; real infra
for one capture, so the stick is preferred.)

```bash
sudo efibootmgr -v          # capture VERBATIM, photo or transcript
```

**STOP condition:** if this capture cannot be obtained, write
**"G4 recorded SKIPPED"** in the session notes. Do not infer NVRAM
equality later from a baseline you never took.

---

## Step 1 — Push + provenance (at the desk)

```bash
make grub-net && make pxe-push-grub
```

`push-grub.sh` prints a per-file manifest, a `manifest:` hash, and
`forth.img`'s MD5, then verifies the DEPLOYED tree hash equals the
STAGED one and refuses on mismatch.

- [ ] **`forth.img` MD5 equals the `combined.img` MD5 from step 0.**
      They are the same file under two names; a mismatch means you
      pushed a different build than the one you tested.
- [ ] **`Deployed OK: our-files hash …` printed.** If instead you
      see `ERROR: deployed tree hash … != staged …`, rerun
      `make pxe-push-grub`. **Do NOT cut dnsmasq over until it
      passes.**

**Why this is a gate and not a formality:** hash-verifying the boot
medium against the build is a discipline this project paid for —
several sessions were spent debugging a stale image that had every
appearance of a code defect.

---

## Step 2 — Cutover + daily-driver proof (iron leg B)

`push-grub.sh` PRINTS the cutover line and never applies it. Apply
it by hand:

```
# in the dnsmasq config, change:
    dhcp-boot=pxelinux.0
# to:
    dhcp-boot=grub/i386-pc/core.0
# then restart dnsmasq
```

- [ ] PXE boot the HP (F9 → network boot).
- [ ] **GRUB menu appears** over TFTP.
- [ ] **Let it time out** — fall through to the memdisk entry →
      ForthOS banner → `ok`.

**This is iron leg B and it gates everything after it.** If the
memdisk path does not reach `ok`, stop: the chainload path cannot
be diagnosed on a machine whose baseline boot is broken.

**ROLLBACK = revert that one line and restart dnsmasq.** Nothing
else in this step touches the laptop's disk.

---

## Step 3 — Install over the net console (memdisk instance)

Everything below runs against the **memdisk-booted** ForthOS, over
the net console. **Save the full transcript.** It is the iron
equivalent of the harness log, and it is what makes "did AHCI-INIT
actually run first?" answerable a month from now.

### FIVE ARMING STEPS — none enforced by the word chain

The installer's words are individually gated but **collectively
unsequenced**. Missing any one fails at a later gate, and before
Bug #33's sentinel, one of them silently destroyed the ESP entry.
Tick each:

1. [ ] **load the install vocab before `AHCI-INIT`** (observed
       constraint — block source goes hostile after AHCI-INIT)
2. [ ] vector binds
3. [ ] VBR-TPL push
4. [ ] ESP extent declaration
5. [ ] `FREE-SLOT` claim

### 3a. Load and initialise

**Source: `tests/test_g6_chain.py:702-706`.** Type what the green
harness types; check it against that file if anything differs.

```forth
USING AHCI
ALSO SURVEYOR
USING INSTALL
AHCI-INIT
```

- [ ] **`ALSO SURVEYOR` comes BEFORE `USING INSTALL`** — the DOVOC
      trap: `USING` replaces the top of the search order, so an
      `ALSO` issued after it is lost.
- [ ] `USING AHCI` needs no block load; AHCI is an embedded vocab.

> **⚠ `INSTALL-THRU` is not a word. Do not type it.** It has no
> definition anywhere in `forth/`, `src/`, `tests/`, or `tools/`.
> It was *narrative shorthand for "get the install vocab loaded"*
> in the plan and the docket — both corrected 2026-08-13; the
> reasoning is recorded at `docs/TASK_INSTALL_BOOT_ENTRY.md`,
> "CORRECTION 2026-08-13". An earlier draft of this runbook
> transcribed it into an imperative block, where it would have
> failed on the session's first typed line.
>
> **This is a distinct rot from `search --part-uuid`.** That was a
> real mechanism named wrong. This was never a mechanism at all —
> and shorthand and command are typographically identical on the
> page, so a reader cannot tell which one they are looking at.
> **The defense is citation: any doc someone will TYPE FROM names
> its source inline,** so the next transcriber can check instead of
> trusting. That is why the line above this block exists.

### 3b. Arm the vectors

```forth
' AHCI-READ SEC-READ-VEC !
SEC-BUF RD-BUF-ADDR !
BIND-WRITER AHCI-WRITE
```

### 3c. Push the VBR template — **BLOCKED**

> ### ⛔ BLOCKED — requires blocks-side VBR-TPL delivery (Task 12.5)
>
> **Do not schedule the iron session until 12.5 lands.** This step
> gates everything after it: without `VBR-TPL` armed, `BUILD-VBR`
> refuses and iron G6 produces nothing.
>
> **Why it is blocked.** On this laptop there is no way to paste.
> - The net console is **output only** — `forth.asm:5432`,
>   `net_console_enabled: db 0 ; 1 = mirror output to UDP`.
> - `NET-DICT`, the inbound code path, `REQUIRES: NE2000`
>   (`forth/dict/net-dict.fth:7-9`). The HP has an RTL8168.
> - The HP has no UART — **(ASSERTED, UNVERIFIED.** Traced to
>   prose in `docs/TASK_INSTALL_BOOT_ENTRY.md:746` and nowhere
>   else; no serial header has been *observed* on the 15-bs0xx.
>   **Check the board before relying on this.** If a header
>   exists, this leg falls and the fallback below may be
>   unnecessary — the other two legs stand on their own.)
>   An unmarked assertion sitting between two cited facts
>   inherits their credibility without earning it.
>
> So input is the **PS/2 keyboard**, and the fallback below means
> hand-typing **512 pokes across 128 lines**, with one sum gate at
> the end and no indication of which line was dropped.
>
> **The fix** is build-side and QEMU-testable: bake the VBR
> template into the blocks image, registered in the catalog by
> name so the block number is derived and not hardcoded, and have
> the install vocab copy it into `VBR-TPL`. This step then
> collapses to **one** typed line (a callable arming word).
> Auto-arming at load time would make it zero, but that means
> calling `BLOCK` while `install.fth` is itself being loaded from
> blocks — the same nested-block territory as a known live defect
> — so it is deliberately deferred rather than bundled.
>
> **How this surfaced,** because it generalizes: the gap was
> already written down and accurately described — "VBR-TPL runtime
> template delivery (blocks-side; today only the test fixture
> populates it)" — and had been sitting in the carried items as
> backlog. It became visible as a *blocker* only by asking what
> the operator physically types. **A dependency recorded as a
> known gap can still be undiscovered as a blocker.**

**Fallback, explicit last resort only** — if 12.5 has not landed
and the session must proceed anyway. Generate the lines **at the
desk, from the current build**, and carry the output on paper:

```bash
python3 - <<'EOF'
data = open('build/vbr.bin', 'rb').read()
assert len(data) == 512, len(data)
print('CREATE VBR-LIVE 512 ALLOT')
for i in range(0, 512, 4):
    print('  '.join(
        f'{data[i+j]} VBR-LIVE {i+j} + C!' for j in range(4)))
print(': TPL-SUM 0 512 0 DO VBR-LIVE I + C@ + LOOP ;')
print(f'\\ TPL-SUM must print {sum(data)}')
print('\\ after TPL-SUM verifies, type: VBR-LIVE VBR-TPL !')
EOF
```

Paste the block, then verify **before** arming:

```forth
TPL-SUM .              \ must equal the noted sum
VBR-LIVE 510 + C@ .    \ 85   (0x55)
VBR-LIVE 511 + C@ .    \ 170  (0xAA)
```

- [ ] Sum matches → **now** type the store by hand:
      ```forth
      VBR-LIVE VBR-TPL !
      VBR-TPL @ VBR-LIVE = .    \ -1
      ```

**The store line is a COMMENT in the generator on purpose:**
pasting the whole block must not arm the pointer. A sum mismatch
means a dropped poke line — redo the push, do not proceed.
Fail-closed ordering: verify, then arm.

### 3d. Declare the ESP extent

`ESP-BASE`/`ESP-LEN` default to 0 and **nothing in the word chain
declares them**; `ADD-BOOT-ENTRY` refuses at the ESP-BASELINE gate
if they are unset. Take the values from the **LIVE `PARTITION-MAP`
output on this machine**, not from this document:

```forth
<base> ESP-BASE !
<len>  ESP-LEN !
ESP-BASE @ .   ESP-LEN @ .
```

- [ ] Cross-check against the R7 survey `[2048, 534527]`
      (→ base 2048, len 532480). **If the live map disagrees,
      trust the live map and note the discrepancy** — do not paste
      the survey numbers over a machine that has since changed.

### 3e. Survey, claim, install

```forth
\ flag-checked LBA 0 probe first
PARTITION-MAP
MAP-TRUSTED? .          \ must be true before anything writes
225 FREE-EXTENT
FREE-SLOT
FS-SLOT @ .             \ MUST print a slot >= 0
```

- [ ] **`FS-SLOT @ .` prints ≥ 0.** The load-time value is `-1`
      and GPT-ARM refuses it. **Bug #33 was exactly this step
      omitted** — the arming looked complete and was not.

```forth
MAKE-OWN-ENT
```

- [ ] **Probe the entry nonzero BEFORE `ADD-PARTITION`.** Same
      attribution split the harness uses: it separates "the
      composer failed" from "the write failed."

```forth
GPT-ARM
ADD-PARTITION
ADD-BOOT-ENTRY
-1 .        \ sanity
DEPTH .     \ 0
```

- [ ] Transcript saved.

**A refusal at any gate leaves the disk untouched by construction.**
Install rollback is a non-event unless G1/G3 say otherwise.

---

## Step 4 — G6 proper: two checkboxes, neither substitutes for the other

### (a) Chainload boot

- [ ] Reboot → PXE → GRUB menu → **SELECT the chainload entry**
      (do not let it time out; the timeout goes to memdisk).
- [ ] ForthOS banner + `ok` on the **VGA screen**.

**How the chainload entry finds the disk.** GRUB's `search` has
**no `--part-uuid` mode in any version** — `probe --part-uuid` is
GRUB's only GUID accessor. The shipped entry therefore sets
`biosdisk` and loops every `(hd*,gpt*)` calling `probe`, matching
on the **unique partition-GUID field**:

```
32ba60fb-4548-4d4c-a439-fb80ce572b31     (FOS-UNIQ, lowercase)
```

Type GUIDs are not probeable at all, which is why ForthOS's
identity had to live in the unique field. If the entry cannot find
the disk it prints `ForthOS: partition GUID not found` and sleeps
5s — that message is a **loud, attributable failure**, not a hang.

### Aliasing tells — leg A vs leg B, in order of strength

The two instances are **byte-identical kernels**. The screen cannot
differ. Record all three; three weak tells beat one assumed
checkbox:

1. **Kernel-keyboard discriminator (definitive, if input works):**
   ```forth
   HEX 28098 @ .  DECIMAL
   \ prints 0 == chainloaded
   ```
   **The `DECIMAL` is not optional and must be on the same line.**
   `HEX` is a runtime word, not immediate, and it stays set. If
   you loop back to step 3d and retype `2048 ESP-BASE !` with
   BASE still 16, you store 8264 and nothing warns you.
   Photograph it.
   **GRUB's menu keyboard is NOT evidence this will work.** GRUB
   runs on BIOS INT 16h via the CSM's EC emulation — the same
   mechanism as the F9 menus you already drove — so *selection*
   will work. What is unverified is ForthOS's own keyboard path on
   this laptop.
2. **Load-time tell (needs no input):** the memdisk entry visibly
   hauls the whole image over TFTP; the chainload entry is
   near-instant. Current payload — **re-measure, do not trust this
   number, `combined.img` grows**:
   ```bash
   ls -l build/tftp/forth.img      # 2,212,352 bytes at time of writing
   ```
3. **Photograph the GRUB menu with the highlighted entry BEFORE
   pressing enter** — not just the `ok` screen after.

### (b) Windows still boots

- [ ] Reboot → **Windows boots normally.**

This is not a formality. It is the whole reason the installer is
allowlist-gated and fail-closed.

### (c) ROLLBACK, if 4(b) fails

**Read this before starting step 3, not after 4(b) fails.**

Every other step in this runbook has a recovery: the dnsmasq
cutover is one line, and an installer refusal leaves the disk
untouched *by construction*. **4(b) is the one failure the
fail-closed argument does not cover** — it is downstream of a
*successful* `ADD-PARTITION` and `ADD-BOOT-ENTRY`. The disk was
written on purpose. Recovery is manual.

**You need TWO things from step 0, and one of them is a
prerequisite you must have brought:**
1. the verbatim `efibootmgr -v` baseline (step 0), and
2. **Windows recovery media.**

A photograph of a working NVRAM state you have no way to restore
is a souvenir, not a rollback.

**Recovery order, least invasive first — stop as soon as Windows
boots:**

1. **Restore the boot order only.** Boot the Linux-EFI stick and
   compare against the step-0 baseline:
   ```bash
   sudo efibootmgr -v
   ```
   If ForthOS's entry is merely ahead of the Windows Boot Manager,
   reorder rather than delete:
   ```bash
   sudo efibootmgr -o <baseline BootOrder, verbatim from step 0>
   ```
2. **Remove the added NVRAM entry** if reordering is not enough.
   Identify it by its label, confirm the number against the
   baseline (it will be an entry the baseline does NOT contain),
   then:
   ```bash
   sudo efibootmgr -b <NNNN> -B
   ```
   **Delete only entries absent from the step-0 baseline.** If you
   cannot tell which entry is new, stop and go to 3 — a wrong
   `-B` is how a recoverable session becomes a reinstall.
3. **Remove the added GPT partition entry.** ForthOS's partition
   is identified by its unique GUID
   `32ba60fb-4548-4d4c-a439-fb80ce572b31`. From the Linux stick:
   ```bash
   sudo sgdisk --print /dev/sda        # find the slot by GUID
   sudo sgdisk --delete=<slot> /dev/sda
   sudo partprobe /dev/sda
   ```
   The installer claims free space only, so deleting its entry
   returns the disk to its prior layout. **Confirm the GUID before
   deleting; the slot number alone is not identification.**
4. **Windows recovery media**, if 1–3 do not restore boot:
   ```
   Startup Repair, or:  bootrec /rebuildbcd
   ```

- [ ] Record which of 1–4 was needed, in the session notes. That
      is the finding, not an embarrassment — it tells you which
      layer the installer actually disturbed.

---

## Step 5 — Evidence + closeout

- [ ] Photos: GRUB menu (highlighted entry), `ok` screen,
      discriminator value, `DISK ERR` screen if any leg failed
- [ ] Step 3 net-console transcript, saved as a file
- [ ] `sudo efibootmgr -v` **after** (if a UEFI session is
      available → G4 equality against step 0's baseline).
      Otherwise: **"G4 recorded SKIPPED."**
- [ ] As-built notes appended to `docs/TASK_INSTALL_BOOT_ENTRY.md`,
      mirrored to the private repo **by absolute path**, project
      copy updated (three-store discipline: repo, private mirror,
      claude.ai Project store — an edit in one is not an edit in
      the others).

### Numbers the as-built notes may cite

- [ ] **Do not write 817.** It was a frozen expectation that the
      run contradicted; it was never measured and was not
      reconciled toward the observation. Anything descending from
      it (655-old, 668) is falsified with it.
- [ ] **The `make test` headline is 804**, and say **measured
      per-suite** when you write it — 22 `^Passed:` lines, exit 0,
      full tree, public `c0bb8b4`. On a free-tier checkout the
      count is 16 lines and a lower sum; that is tier, not
      regression, so **carry the line count next to the sum**.
- [ ] **Re-derive any decomposition you write, in the same
      session, from that run's own log.** Do not carry a part
      forward as "unchanged." A grep-derived total self-corrects
      every run; a prose decomposition beside it does not, and the
      disagreement stays invisible until someone sums the parts.
      That is how 234 survived four months. **Either re-derive it
      or drop it and record the total alone, saying so.**

---

## If you need to run the QEMU harness by hand during the session

**Pass an explicit port. Do not rely on the default.**

```bash
python3 tests/test_g6_chain.py 4595
```

`tests/test_g6_chain.py`'s bare default is **4590**, which collides
with `test_meta_does`. `make test-g6` allocates `4595/4596` (the
harness needs PORT and PORT+1 for its monitor) and is unaffected —
the hazard is specifically hand-invocation, which is what iron
debugging consists of. The default is not fixed in the file because
the harness is hash-pinned and changing it would invalidate the
pinned expectation; the instruction here is the operational
substitute.

Ports bound by bare-run defaults elsewhere in `tests/`:
**4590–4594, 4598.** Avoid them.
