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

### 3.0 Net-console bring-up — dev box first, then CONFIRM on the HP

**Source: `forth/dict/auto-detect.fth:199-224` (auto path),
`forth/dict/rtl8168.fth:447,484` (manual words), `src/kernel/forth.asm:3263`
(probe word). Iron precedent: the console has come up on this exact
HP twice — `atapi-iron.txt` line 1 is `Net console ON`, before any
typed input, and the 2026-03-25 bring-up session established it.**

**This is NOT a block load and carries no ordering constraint
against arming step 1.** `rtl8168.fth` is in `EMBED_VOCABS`
(`Makefile:49`) — embedded in the full-tier image like AHCI. The
`THRU` constraint below is about the INSTALL catalog range; nothing
in this section touches blocks. (Checked, not assumed — an earlier
draft of this session's plan guessed a block-load constraint that is
not there.)

#### On the dev box, BEFORE the step-2 PXE boot

The kernel's UDP destination is **hardcoded** (`rtl8168.fth:74-76`):
HP `10.42.0.100` → dev box `10.42.0.1`, port `6666`. That works only
if dnsmasq hands out that range and the listener is bound on that
interface — a subnet change becomes a silent no-transcript, the same
fail-open shape as the confirmation gate below. Pre-check:

```bash
ip -4 addr show | grep '10\.42\.0\.1/'   # dev box must hold 10.42.0.1
```

Then start the listener. Use the purpose-built capture tool — it
flushes per packet and hash-gates the deployed image against the
build (step 1's discipline, mechanised):

```bash
python3 tools/hp-portread-capture.py --boot-path pxe --port 6666 \
    --out docs/EVIDENCE_G6_NETCON.log
```

`--port 6666` is also the tool's default
(`hp-portread-capture.py:46`); it is written out because the number
must agree with the hardcoded destination two paragraphs up, and an
explicit flag makes that agreement checkable on the page.

**What was verified, exactly (2026-08-20, `d0b4efc`):**

- *Listener path*: scripted UDP sender against
  `--port 4610 --skip-hash-gate` — binds `0.0.0.0:<port>`, plain
  `recvfrom` loop with **no sender lock**, per-packet flush,
  appends; the tail line arrived. The docstring says "port-read
  capture" but nothing in the receive path is port-read-specific;
  it is a general UDP console listener.
- *Hash-gate path*: the documented invocation (no skip), run
  against a genuinely stale `/srv/tftp/forth.img` — **ABORT, exit
  1, no log file created, socket never bound.** The listener
  refuses to start on a stale deploy. That is step 1's discipline,
  not a malfunction: run this command **after** step 1's
  `make pxe-push-grub`, and treat an ABORT here as "step 1 is not
  actually done."
- *Composition — gate-pass followed by listening* (added
  2026-08-20, `7c66cc6`): run with `--port 6666` and `--deployed`
  pointed at a **byte-identical copy** of `build/combined.img` —
  header records `hash gate: PASS` with both sha256s equal,
  listener binds `udp/:6666`, two UDP packets arrive timestamped,
  and the log survives a hard kill (per-packet flush). The one
  thing this does not exercise is the literal default `--deployed`
  path: `/srv/tftp/forth.img` was stale at test time, and
  deploying out of order just to green a smoke test would invert
  step 1. Same gate code, same pass branch; only the path string
  differs.

**Do not use `nc -u -l 6666` for the evidence transcript.** UDP
netcat locks onto the first sender and, depending on version (`-l`
vs `-lk`, BSD vs GNU), either exits after the first datagram or
buffers such that the tail is lost. The transcript's most important
line is `DEPTH .` printing 0 — the proof the stack was clean — and
that is exactly the packet a buffered listener eats. If netcat is
the only option: `nc -u -lk 6666 | tee -a transcript.txt`, and
record the tail risk in the session notes.

Start the listener **before** the step-2 PXE boot, so the boot spew
— including the `Net console ON` line itself — lands in the
transcript.

#### On the HP: nothing to type, ONE thing to confirm

`AUTO-DETECT` runs at boot (`auto-detect.fth:224`) and enables the
console only when the NIC probe succeeds — `NIC-OK @ IF
NET-CONSOLE-ON THEN` (`auto-detect.fth:209`). That `IF` is the trap:
**a failed probe leaves the console off and says nothing**, which
from the operator's chair is indistinguishable from "no output yet."
You would type the whole install, get nothing, and learn at step 5
that the evidence never existed. Absence-of-output is not a health
check — the same fail-open shape as §3e's all-zero-buffer read.

**Confirmation gate — before ANY of §3a. The one mandatory tell is
arrival at the listener; nothing on the HP's side can substitute:**

- [ ] **Boot spew arriving at the dev-box listener.** This is the
      gate. Every other check below is a diagnostic for *why* it is
      not arriving, not an alternative way to pass — the local flag
      can read 1 with the wrong subnet, a listener bound on the
      wrong interface, or a firewall in the way, and every one of
      those leaves the transcript empty while the HP looks healthy.
- [ ] `Net console ON` on the **VGA screen** in the boot spew
      (diagnostic: distinguishes "console never enabled" — go to
      the manual fallback — from "enabled but not arriving" — go
      to the dev-box pre-checks above).
- [ ] The explicit probe — a kernel word, needs no search-order
      change (`forth.asm:3263`) — same diagnostic, for when the
      spew has scrolled off:

```forth
NET-CON-ENABLED C@ .    \ 1 = enabled locally; says NOTHING about
                        \ arrival. 0 = OFF -- manual fallback below
```

#### Manual fallback, if the probe prints 0

```forth
ALSO RTL8168
RTL8168-INIT
NET-CONSOLE-ON
NET-CON-ENABLED C@ .    \ must now print 1
```

- [ ] **`ALSO RTL8168`, not `USING RTL8168` — and run the fallback
      BEFORE any of §3a.** `USING` replaces the top of the search
      order: the same DOVOC trap §3a documents for `USING INSTALL`
      evicting SURVEYOR. An operator who reaches for this fallback
      *after* §3a's `ALSO SURVEYOR / USING INSTALL` and types `USING
      RTL8168` silently evicts INSTALL, and the next install word
      wedges. The vocab's own usage header says `USING RTL8168`
      (`rtl8168.fth:20`) — safe at a bare post-boot `ok`, wrong
      mid-install; since the hazard is positional, use the form that
      is safe in both positions.
      **`ALSO RTL8168` is observed, not inferred** (QEMU serial,
      `combined.img` at `d0b4efc`, 2026-08-20): after `ALSO
      RTL8168`, the vocab word `NET-CONSOLE-OFF` executed (`Net
      console OFF`), `ORDER` showed the search order two deep with
      FORTH still beneath (`0003652C 00028048`), `DEPTH .` printed
      0. Search-order semantics are kernel software, identical on
      iron — QEMU is a valid oracle for this claim, unlike for
      hardware behaviour.
- [ ] If `RTL8168-INIT` prints `RTL8168 not found`, the boot-time
      probe failure is real hardware news, not a transient — go to
      the skip fallback below.

#### If the console cannot be brought up

Record **"transcript SKIPPED"** — in those words — in the session
notes, and photograph the VGA screen after **every** §3e line (each
ends in `.`, so each response fits a frame). A skip must not read
like a pass: steps 3 and 5 list the transcript as required evidence,
and a photo series is a degraded substitute, not an equivalent.

### FIVE ARMING STEPS — none enforced by the word chain

The installer's words are individually gated but **collectively
unsequenced**. Missing any one fails at a later gate, and before
Bug #33's sentinel, one of them silently destroyed the ESP entry.
Tick each:

1. [ ] **`DECIMAL` is in effect on the line that types the INSTALL
       catalog range** — the real invariant, mechanism confirmed
       2026-08-20 (third act of the ⚠ block below). The `THRU`
       still runs before `AHCI-INIT` **as typed** — order kept,
       retired as mechanism
2. [ ] vector binds
3. [ ] VBR-TPL push
4. [ ] ESP extent declaration
5. [ ] `FREE-SLOT` claim

> **⚠ Step 1's stated REASON was falsified 2026-08-13. The step
> stands.** This runbook used to justify step 1 with "block source
> goes hostile after `AHCI-INIT`." That generalisation is dead:
> `ARM-VBR-TPL` (§3c) does a single `BLOCK` read *after*
> `AHCI-INIT` in the green harness and gets correct bytes —
> `TPL-SUM` equals the host's `sum(vbr.bin)`, G6 71/71.
>
> **A single `BLOCK` read is not a `THRU` of a range.** What was
> actually observed on 2026-08-06 is narrower and still unrefuted:
> `THRU`-ing the INSTALL catalog range *after* `AHCI-INIT` spews
> meta-compiler words and reboots; *before* it is clean. Different
> operation, so the measurement **narrows the reason and retires
> nothing.** Do not delete step 1 on the strength of §3c.
>
> Note also that step 1 is about the **block load**, not the search
> order: `ALSO SURVEYOR` and `USING INSTALL` demonstrably run
> *after* `AHCI-INIT` in the green harness. Only the `THRU` is
> order-constrained.
>
> **Third distinct rot mechanism, same symptom.**
> `search --part-uuid` was a real mechanism *named wrong*.
> `INSTALL-THRU` was *shorthand mistaken for a mechanism*. This one
> was **an observation that was true when recorded and was later
> falsified by a better measurement** — the most insidious of the
> three, because it was honestly earned. The defense does not vary
> with the mechanism: **when you falsify something, grep for it
> before you move on.** This claim outlived its refutation in three
> stores after being corrected in one.
>
> **Third act (2026-08-20): mechanism CONFIRMED; the ordering is
> RETIRED as mechanism and kept as the typed sequence.** A
> pre-registered experiment (suspects named before the run, the
> misparse range derived from the shipped catalog, a forward-order
> control leg) reproduced the 2026-08-06 spew and explained it:
> `AHCI-INIT`'s success path ends `." Drive on port " DECIMAL . HEX
> CR` (`ahci.fth:499`) and returns with **BASE=16**. A bare
> `575 653` typed after it parses as hex — blocks 1397–1619, today
> the metacompiler TARGET/UI source — and `THRU` loads *those*:
> undefined-word spew, wedge. With `DECIMAL` on the line, the same
> range `THRU` is clean **after** `AHCI-INIT` and INSTALL fully
> loads. The 08-13 falsifier above never touched this because
> `ARM-VBR-TPL` finds its block **by name** — no numeral is parsed.
> *A measurement can be correct, honestly earned, and still not
> bear on the thing it appears to bear on* — a fourth rot species;
> when a claim survives a falsification attempt, ask what the
> attempt did **not** exercise.
>
> **The replacement invariant: BASE must be decimal when block
> numbers are typed.** Stated unconditionally — boot base is
> habitat-dependent (decimal on a floppy boot, **HEX on the
> GRUB-memdisk path iron uses**), and a conditional invites the
> operator to check, guess, or skip. §3a carries it **twice**: the
> first typed line (boot base is HEX before it) and the block's
> closing `DECIMAL` (because `AHCI-INIT` runs at the *end* of §3a,
> BASE would otherwise be 16 through §3b–§3d — §3c's `512`-loop
> would run 1298 iterations, §3d's `2048` would store 8264 — until
> §3e's own `DECIMAL`). The `2048 → 8264` warning under the
> aliasing tells is the SAME defect at a second site, there for the
> loop-back case. The typed order is
> unchanged: this page's only authority is agreeing with the green
> harness, and the harness keeps the `THRU` first. The root fix —
> caller-transparent save/restore inside `AHCI-INIT` — was
> deliberately deferred to **after** iron G6: it rebuilds
> `combined.img`, invalidating the desk card's hash, the pushed
> TFTP tree, and the QEMU-green commit that session rested on. The
> deferral was pinned mechanically, not in prose: the harness
> asserted `BASE is 16 after AHCI-INIT (known defect)`, to go red
> the day the fix landed.
>
> **Fourth act (2026-08-23): the root fix LANDED.** `AHCI-INIT` is
> now base-transparent. The §3a `DECIMAL` lines **stay** — the
> invariant "BASE must be decimal when block numbers are typed" is
> unconditional and does not lean on one word's manners; they are
> now belt-and-braces, not the sole defense. Detail:
> `docs/evidence/base-transparency-item1-2026-08-23.txt`, docket
> 08-23 entry.

### 3a. Load and initialise

**Source: `tests/test_g6_chain.py`, between the `RUNBOOK-3A-BEGIN`
and `RUNBOOK-3A-END` markers — drift-gated by
`tests/test_doc_drift.py` (gate B-3a), so this block cannot silently
disagree with the harness.** Type what the green harness types;
check it against that region if anything differs.

`install.fth` is **not** in `EMBED_VOCABS` (`Makefile:49`) — it is
the one vocab here that needs a block load, and `LOAD-VOCAB` is
broken on this boot path (`'F ?'` then wedge), so the documented
workaround is a literal `THRU` of its catalog range. Get the two
numbers **at the desk** and carry them; do not try to compute them
at the console:

```sh
python3 tools/catalog_layout.py INSTALL      # prints "<n> <m> THRU"
```

It reads `build/blocks.img` — the catalog **the machine reads** —
so the numbers are the running image's, not a recomputation that
could disagree with it. Run it against the *same* image you are
about to boot.

```forth
DECIMAL <first> <last> THRU  \ range from the generator above
USING AHCI
AHCI-INIT
ALSO SURVEYOR
USING INSTALL
DECIMAL                    \ belt-and-braces: BASE decimal for typed block numbers
```

- [ ] **`DECIMAL` opens the `THRU` line and closes the block** —
      arming step 1. Boot base on this (GRUB-memdisk) path is HEX,
      so a bare range misparses into the metacompiler blocks. The
      trailing `DECIMAL` is belt-and-braces since the 2026-08-23
      fix (`AHCI-INIT` is now base-transparent — ⚠ fourth act);
      it stays because §3b–§3e all type numerals and the invariant
      must not lean on one word's manners.
      Unconditional — do not probe BASE and decide; type it.
- [ ] **The `THRU` comes BEFORE `AHCI-INIT`** — order kept as
      typed; retired as mechanism (⚠ third act above). The
      search-order words come *after*.
- [ ] **`ALSO SURVEYOR` comes BEFORE `USING INSTALL`** — the DOVOC
      trap: `USING` replaces the top of the search order, so an
      `ALSO` issued after it is lost.
- [ ] `USING AHCI` needs no block load; AHCI is an embedded vocab.

> **Corrected 2026-08-13.** This block previously read `USING AHCI`
> / `ALSO SURVEYOR` / `USING INSTALL` / `AHCI-INIT`, with no block
> load at all — so the operator's `USING INSTALL` would have hit a
> vocab that was never loaded, on the first session that used it,
> and `AHCI-INIT` ran last in violation of arming step 1. It cited
> `:702-706`, a range that had since drifted. **A citation is only
> a defense if someone follows it** — this one was checked against
> the harness and disagreed with it in three ways.

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

### 3c. Arm the VBR template — **one line**

**Source: `tests/test_g6_chain.py`, the "Arm VBR-TPL from the
blocks-side template" block.** Type what the green harness types;
check it against that file if anything differs.

```forth
ARM-VBR-TPL .
```

- [ ] Prints `-1`. A `0` means the template was **not** delivered
      — do not continue, `BUILD-VBR` will refuse at the
      no-template gate and everything after it is noise.

`ARM-VBR-TPL` looks `VBR-TEMPLATE` up in the block catalog **by
name** (the block number is derived, never typed), copies the 512
bytes out of the block buffer into `VBR-RAW`, and stores that
address in `VBR-TPL`.

**Then verify the CONTENT — the flag does not.** `-1` reports that
delivery happened; it cannot report that the bytes are right.
Measured 2026-08-13: against an image with one byte of the staged
block flipped, `ARM-VBR-TPL` still returned `-1` while the sum
moved by exactly the flip. Two gates, and they stay two.

```forth
: TPL-SUM 0 512 0 DO VBR-RAW I + C@ + LOOP ;
TPL-SUM .              \ must equal the sum noted at the desk
VBR-RAW 510 + C@ .     \ 85   (0x55)
VBR-RAW 511 + C@ .     \ 170  (0xAA)
VBR-TPL @ VBR-RAW = .  \ -1
```

Get the expected sum **at the desk, from the build you deployed**,
and carry it on paper — do not trust a number written in this file:

```bash
python3 -c "d=open('build/vbr.bin','rb').read(); \
assert len(d)==512, len(d); print('TPL-SUM must print', sum(d))"
```

- [ ] Sum matches. A mismatch means the block store and
      `build/vbr.bin` disagree — **stop and re-check which image
      this machine actually booted** (step 0's hash check). Do not
      proceed on a template that does not match the build.

**Why this is one line and not 512 pokes.** On this laptop there
is no way to paste: the net console is **output only**
(`forth.asm:5432`, `net_console_enabled: db 0 ; 1 = mirror output
to UDP`), `NET-DICT` — the inbound path — `REQUIRES: NE2000`
(`forth/dict/net-dict.fth:7-9`) and the board has an RTL8168, and
the HP is believed to have no UART (**asserted, unverified** —
traced to prose in `docs/TASK_INSTALL_BOOT_ENTRY.md:746` and
nowhere else; no serial header has been *observed* on the
15-bs0xx). So input is the **PS/2 keyboard**, and before Task 12.5
this step meant hand-typing 512 pokes across 128 lines with one
sum gate at the end and no indication of which line was dropped.

That fallback is **deleted, not parked.** The generator that
produced those lines is in git history, where retrieving it costs
a deliberate act. Leaving it here as a "last resort" would keep a
substitute mechanism one bad session away from being used on the
day blocks delivery misbehaves — which is the day you most need
this step to be exercising the real path.

**How this surfaced,** because it generalizes: the gap was already
written down and accurately described — "VBR-TPL runtime template
delivery (blocks-side; today only the test fixture populates it)"
— and had been sitting in the carried items as backlog. It became
visible as a *blocker* only by asking what the operator physically
types. **A dependency recorded as a known gap can still be
undiscovered as a blocker.**

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

**Source: `tests/test_g6_chain.py`, between the `RUNBOOK-3E-BEGIN`
and `RUNBOOK-3E-END` markers — drift-gated by
`tests/test_doc_drift.py` (gate B). An earlier citation here was a
line range; it went stale the first time the harness grew a line
above it, which is what the markers exist to survive.** Type what
the green
harness types; check it against that file if anything differs.

**Every line ends in `.`, and that is not cosmetic.** The harness sends
each expression as `DECIMAL <expr> .`, which *consumes* the flag. Typing
these words bare leaves flags on the stack, and `ADD-PARTITION ( entry
-- flag )` takes whatever is on top as its entry pointer — see the
warning after this block.

```forth
DECIMAL

\ flag-checked LBA 0 probe BEFORE trusting any buffer
0 1 AHCI-READ .         \ 0   (nonzero = failed read; a zero buffer is
                        \      a failed read, not an empty MBR)
SEC-BUF 510 + C@ .      \ 85
SEC-BUF 511 + C@ .      \ 170

PARTITION-MAP           \ leaves nothing on the stack
DECIMAL                 \ belt-and-braces: BASE decimal for the typed sector counts
MAP-TRUSTED? .          \ -1  required before anything writes

225 FREE-EXTENT .       \ -1
OWN-BASE @ .            \ RECORD THIS — where ForthOS landed
OWN-LEN @ .             \ 225

FREE-SLOT .             \ -1
FS-SLOT @ .             \ MUST be >= 0

GPT-ARM .               \ -1  — arm BEFORE composing
MAKE-OWN-ENT DUP 0= 0= .   \ -1, and LEAVES the entry on the stack
ADD-PARTITION .         \ -1  — consumes the entry
ADD-BOOT-ENTRY .        \ -1
DEPTH .                 \ 0
```

- [ ] **`FS-SLOT @ .` prints ≥ 0.** The load-time value is `-1`
      and `GPT-ARM` refuses it. **Bug #33 was exactly this step
      omitted** — the arming looked complete and was not.
- [ ] **`GPT-ARM .` comes before `MAKE-OWN-ENT`, and prints `-1`.**
- [ ] **`MAKE-OWN-ENT DUP 0= 0= .` prints `-1`.** The `DUP 0= 0=` is
      the attribution split: it probes a *copy* of the flag and leaves
      the entry address in place. Do **not** type `MAKE-OWN-ENT .` —
      that consumes the entry and `ADD-PARTITION` then reads whatever is
      beneath it.
- [ ] **`DEPTH .` prints 0.** A nonzero depth means a flag went
      unconsumed somewhere above, which means `ADD-PARTITION` may have
      been handed the wrong pointer. **This is an after-the-write
      diagnostic, not a gate** — it cannot un-write the disk.
- [ ] Transcript saved.

> **⚠ Why the `.` and the order are load-bearing.** `GPT-ARM ( -- flag )`
> pushes `-1`; `ADD-PARTITION ( entry -- flag )` pops its entry from the
> top of stack. Typed bare and in the old order — `MAKE-OWN-ENT`,
> `GPT-ARM`, `ADD-PARTITION` — the stack is `entry -1` and
> `ADD-PARTITION` takes **`-1` as the entry address**. The `AP-ENT @ 0=`
> guard passes (`-1` is not zero), `AP-PATCH` `CMOVE`s 128 bytes from
> `0xFFFFFFFF` into the slot, and steps 7–8 verify the write **against
> the buffer they just patched** — so it *returns `-1` and looks like a
> success*. The disk then carries a slot with garbage where the
> canonical GUIDs belong, GRUB's probe loop cannot find it, and leg A
> fails with `ForthOS: partition GUID not found` — **the leg C message,
> on a leg A run.** A stack discipline this quiet is why the harness
> citation on this block is not optional.

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
- [ ] **The `make test` headline is measured THIS session, not
      quoted from this page.** A pinned value here went stale in
      under a day once, in the document that teaches "when you
      falsify something, grep for it." Run `make test`, sum the
      `^Passed:` lines, and say **measured per-suite** when you
      write it. The value's history lives in the test-count lineage
      section of `BUILD-DOCKET.md` (claude.ai project store) —
      record the new measurement there. On a free-tier checkout the
      line count is 16 and a lower sum; that is tier, not
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

**pkill self-match trap.** `pkill -9 -f qemu` matches against every
process's FULL command line — including the shell that is executing
the pkill, whose own command string contains the word "qemu". The
shell kills itself before the rest of the line runs, which presents
as a command that "failed instantly with no output" (observed
2026-08-24: two phantom failures, both traced to this). Always use
the bracket form, `pkill -9 -f "[q]emu"` — the pattern `[q]emu`
matches `qemu` but not its own literal text. The Makefile's
per-suite cleanups already do this; the trap is hand-typed and
script-embedded pkills. Related: a `make test` that is orphaned
rather than killed (e.g. a tool timeout) keeps running invisibly,
and two concurrent `make test` runs murder each other's QEMUs via
the per-suite port cleanups.

**The bracket form's limit** (the sharper version of the same
trap): `[q]emu` only defeats self-match when the target string
appears NOWHERE ELSE on the invoking command line. A compound
command that both greps for `make test` and *runs* `make test`
matches itself on the run clause no matter how the grep pattern is
bracketed — no regex trick separates them, you need a different
predicate. Concretely: guard a full run by checking for the thing
that actually collides (`pgrep -af '[q]emu-system'`, a string that
appears once), not for the make itself. And put the guard in
`if/else`, not `&&`/`||` — the chain form lets the abort branch
exit 0, a fail-open guard that skips the run while reporting
success (observed as a rejected command 2026-08-25; the same
defect class as a skip that reads like a pass).
