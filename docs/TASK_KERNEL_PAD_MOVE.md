# TASK: kernel-pad move, the demo apps to blocks

Status: PLAN (2026-10-11), no code changed.

Owner ruling 2026-10-11, following the interpreter-correctness task:
- The kernel-pad move comes next: the demo apps to blocks, plan first.
  512 B of pad won't hold UEFI-3/4.
- The embed-stripper fix comes after it; its byte cost against the pad is
  reported here.
- The plan must also cover the installed HP boot. It chainloads with no
  memdisk, so block-loaded vocabularies aren't available there. Show
  that nothing on that path (FIRSTBOOT, the installer, any forms or UI)
  needs hello, notepad or the file browser, or list exactly what stops
  working there.

Background: docs/TASK_KERNEL_PAD.md (the 10-10 inventory and options).

## 1. Numbers (measured 2026-10-11)

- **Full kernel:** content 114,176 B of KERNEL_PADDED_SIZE 114,688, so
  **512 B left** (after the interpreter-correctness change).
- **Free kernel:** content 81,374 B, so **33,314 B left**. The free build
  doesn't need the move.
- **The move, groups A+B+C from the 10-10 plan:**

| group | file | embedded stream (B) |
|---|---|---|
| A | hello-form | 1,074 |
| A | hello-app | 1,444 |
| B | notepad-form | 1,771 |
| B | notepad | 2,819 |
| C | file-browser-form | 1,102 |
| C | file-browser | 6,156 |
| | **total, with the joining spaces** | **14,372** |

  After the move: about 14,884 B of pad left (512 + 14,372). The boot
  dictionary shrinks by about 11 KB (the 10-10 dictionary figures for
  A+B+C), which raises test-meta's margin by the same amount.
- **The embed-stripper fix** (finding 2026-10-11) puts back the spaces it
  collapses inside string literals. The cost is the spaces lost: **42 B**
  over 32 literals in the full build, 22 B over 12 in the free build.
  That is counted from the literals in each embedded file; the exact
  figure comes from the rebuilt stream.

## 2. Nothing else depends on these six

Searched in both repositories: no file has an `ALSO`, `USING` or
`REQUIRES:` naming HELLO-APP, HELLO-FORM, NOTEPAD, NOTEPAD-FORM,
FILE-BROWSER or FILE-BROWSER-FORM, except the six themselves. The
mentions in file-editor-core, port-monitor and ntfs are comments.

The six only need what stays embedded: UI-CORE, UI-PARSER, UI-EVENTS,
GUI-HARVEST, FILE-EDITOR, CATALOG-RESOLVER and NTFS (their `REQUIRES:`
and `ALSO` lines). So a block load finds every dependency present.

## 3. The installed HP boot (the owner's question)

Reasoned from the code and the disk layout, not observed; red I1 below
observes it.

- **There is no memdisk on an installed boot.** The VBR chainloads the
  224 kernel sectors from P6, and `BLK_IMAGE_BASE` is 0. G6 leg A
  asserts that discriminator: "chainload, no memdisk".
- **Kernel BLOCK then takes the ATA PIO path** (forth.asm, BLOCK). The HP
  has no legacy ATA ports.
- **AHCI's BLOCK override** (ahci.fth `AHCI-BLOCK`, active once AHCI is
  in the search order and initialised) reads absolute LBA 225+2N on the
  SATA disk.
  **But LOAD-VOCAB doesn't use it.** catalog-resolver is embedded before
  AHCI, so CATALOG-FIND's `BLOCK` was compiled against the kernel's
  BLOCK. The override only reaches words compiled after AHCI, or typed.
  So an installed `LOAD-VOCAB` takes the kernel's ATA PIO path. The
  waits there are bounded (`ata_wait_ready`/`ata_wait_drq`: 10,000,000
  status reads, then CF=1). On the HP, with no legacy ATA ports, each
  read should time out, which would take seconds on iron (reasoned).
  BLOCK then returns its buffer unfilled, CAT-HDR? fails, and nothing
  loads. The bullet below holds whichever path BLOCK takes.
- **The installer writes no block store.** It writes `KERNEL-SECTORS`
  (224) at OWN-BASE+1, plus the VBR (install.fth `ABE-KWRITE`,
  `ADD-BOOT-ENTRY`). On the HP that is LBA 35-258, so the catalog's
  block 1 (LBA 227-228) reads kernel bytes. CATALOG-FIND finds no
  catalog header and `LOAD-VOCAB` loads nothing.
- **So today an installed instance can load no block-loaded vocabulary
  at all.** That is a pre-existing gap the move doesn't create:
  - **FIRSTBOOT** (block-loaded; needs UI-CORE, UI-EVENTS, PCI-ENUM,
    CATALOG-RESOLVER) can't load there today. The firstboot plan's
    installed-instance branch ("the installer writes a has-run marker;
    the hook reads it") assumes it can.
  - **INSTALL and SURVEYOR** (block-loaded) can't load there today
    either. That doesn't matter: installing is done from the stick.
  - **The 10-10 pad plan's line** "AHCI … and CATALOG-RESOLVER (to load
    anything at all …) must stay embedded" for the installed instance
    is wrong as written: there is nothing to load. AHCI still has to
    stay for disk access itself.
- **Nothing on the installed boot path calls the six.**
  - At boot only the embedded stream runs. Its top-level lines are RAM
    and table set-up, PCI-SCAN and AUTO-DETECT (checked for the ASUS
    card, 2026-10-11). None of them is one of the six.
  - The forms' `CATALOG-REGISTER` calls only fill the in-memory registry.
  - No embedded word refers to the six.
- **What stops working on the installed instance after the move:**
  - **HELLO-APP, NOTEPAD and FILE-BROWSER** (and their entry words) are
    no longer at the `ok` prompt. On a memdisk or ATA boot,
    `S" NOTEPAD" LOAD-VOCAB` brings them back; on the installed instance
    nothing can (above).
  - **NOTEPAD-FORM, HELLO-FORM and FILE-BROWSER-FORM** are no longer in
    the in-memory catalog registry, so `CATALOG-FIND` on those names
    finds nothing there.
  - **Nothing else.** FIRSTBOOT, INSTALL and SURVEYOR are already
    unavailable there, and no remaining embedded word depends on the
    six.
- **For the owner:** the installed instance becomes a bare `ok` prompt
  with drivers and the UI library, but no demo app. Whether that is
  acceptable, or whether the installer should also write a block store
  (which would fix FIRSTBOOT there too), is a decision, not part of this
  move.

## 4. Other boot paths

- **memdisk (the HP stick, PXE) and UEFI module (future):** the whole
  combined image is in RAM, so `LOAD-VOCAB` works from the first prompt.
- **QEMU IDE:** ATA reads the combined image, so `LOAD-VOCAB` works.
- **Free build:** unchanged by this plan (33 KB of pad). Moving the same
  files there too would be for parity only; recommended no (minimum
  diff).

## 5. Users to change

- **tests/test_catalog_registry.py** (not in make test): expects
  NOTEPAD-FORM in the boot registry (CATALOG-MEM = 1). After the move it
  runs `S" NOTEPAD-FORM" LOAD-VOCAB` first, and the registry hit comes
  from that load.
- **tests/test_catalog_complete.py** (test-vocabs) already handles both
  answer shapes (registry and block). After the move these three forms
  resolve from blocks until loaded; to be confirmed by its run.
- **tests/test_nfbuild_diag.py** (not wired; a diagnostic) loads
  notepad-form itself: to be checked.
- **GUI suites** (test-gui) and test-integration: no reference found by
  name search. They run in the gates.
- **Cards and docs that type NOTEPAD, HELLO-APP or FILE-BROWSER-RUN at
  the prompt** need a `LOAD-VOCAB` line first. A name search of
  tools/pxe and the private cards found none current. To be grepped again
  in the change.
- **Makefile:** remove the six from `EMBED_VOCABS` (full only). They stay
  in the catalog (write-catalog packs every forth/dict file), so they are
  block-loadable as they are.

## 6. Red, before the change

| # | case | today | after |
|---|---|---|---|
| K1 | kernel-only image (bmforth.img): `NOTEPAD`, `HELLO-APP`, `FILE-BROWSER` as vocabulary words | present | absent (`NOTEPAD ?`) |
| K2 | combined image: `S" NOTEPAD" LOAD-VOCAB`, then `USING NOTEPAD` and a NOTEPAD word, DEPTH 0; the same for HELLO-APP and FILE-BROWSER | "present, skipped" | loads; the word answers |
| K3 | combined image: `S" NOTEPAD-FORM" CATALOG-FIND`, then CATALOG-MEM | registry hit (MEM 1) | block hit (MEM 0) before loading; registry hit (MEM 1) after `LOAD-VOCAB` |
| K4 | kernel content against KERNEL_PADDED_SIZE | 512 B left | ≥ 14,800 B left |
| I1 | installed instance: an HP-549 fixture laid out as ADD-BOOT-ENTRY writes it (P6 34-582, VBR at 34, kernel at 35-258). The kernel boots from floppy (stand-in for the chainload: the same no-memdisk BLOCK state). `USING AHCI AHCI-INIT`, then `S" MIRROR" LOAD-VOCAB` and `S" FIRSTBOOT" LOAD-VOCAB` | (observes §3: predicted to load nothing; the prompt answers afterwards) | unchanged: a characterisation of the installed path. QEMU's empty IDE bus can't show the HP's ATA timeouts, only that nothing loads |

## 7. Gates

- K1-K4 green; I1 recorded.
- `make -k test`: only test-xhci red. test-meta full, with its margins
  re-read (they should rise by the dictionary freed).
- The boot-log gate on both kernels.
- test-install and the G6 chain.
- The HP stick: rebuilt after this task, carrying the interpreter fix and
  the move, checked with hp_stick_check, and the HP card dry-run again.
  The card types nothing from the six, so it should be unchanged.

## 8. Decisions owed

1. **Groups:** A+B+C as above (recommended), or also E (the GUI stack,
   29,138 B more, much larger reach).
2. **The installed instance** (§3): accept "no demo apps there", or queue
   an installer change that writes a block store. That second option
   would also fix FIRSTBOOT's installed branch.
3. **Free build:** leave unchanged (recommended) or move the same files
   for parity.

## 9. Rulings (owner, 2026-10-11)

1. **Groups:** hello, notepad and file browser only, not the GUI stack.
2. **Installed instance:** no demo apps there for now. A new task is
   queued, "installed block store": the installer writes a catalog and
   block store that the installed instance can read, so FIRSTBOOT and
   LOAD-VOCAB work there. Plan first. It goes after UEFI-3/4, before
   xHCI Phase 12.
   - Note from §3: LOAD-VOCAB uses the kernel BLOCK, not AHCI's
     override, so that task must also decide how catalog-resolver
     reaches the AHCI disk.
3. **Free build:** unchanged.
4. **Red I1** must observe the installed instance's inability before
   the plan relies on it.
5. **The corrections are recorded in their own docs:**
   - docs/TASK_FORTHOS_FIRSTBOOT.md §8, a local file never committed to
     either repository;
   - docs/TASK_KERNEL_PAD.md §3.
6. **Order:** commit the interpreter work once its gates pass, then
   these reds with predictions, then the code.

## 10. Go (owner, 2026-10-11, new working rule)

- **No further review: red, code, gates, then one report.**
- **Groups: hello, notepad and FILE-BROWSER (option 1).** There is no
  word called MFT-SCAN. The "full MFT scan" explorer is file-browser.fth
  itself.
  - The installed instance keeps NTFS's embedded text listing (MFT-LIST,
    MFT-SHOW, MFT-FIND) and loses the FILE-BROWSER tree until the
    installed block store lands.
  - On the HP stick (memdisk), `S" FILE-BROWSER" LOAD-VOCAB` brings the
    tree back. The demo script does that before using it.
- **The free build is unchanged.** The two earlier docs are corrected in
  the same commit.

## 11. Results (2026-10-11)

**Red: 8/16, as predicted** (`0e246da7`). Two earlier runs were void,
both instrument faults:
- QEMU's default boot order tried the HP-549 fixture disk before the
  floppy; fixed with `-boot order=a`.
- The next run found the port still held by the first run's I1 QEMU:
  `boot()` raised before its `try`, so the kill never ran. `boot()` now
  registers the pidfile kill at exit.

**I1 observed:** on the installed stand-in (no memdisk, AHCI-INIT ok),
`LOAD-VOCAB` of MIRROR and FIRSTBOOT loads nothing, and the prompt
answers afterwards.

**Built:**
- **EMBED_VOCABS (full build) drops the six demo-app files.** The free
  build is unchanged.
- **New finding, fixed:** removing a file from EMBED_VOCABS changed no
  remaining file's timestamp, so the stream and kernel silently stayed
  stale (the first green run used the old kernel, `0e246da7`). The
  Makefile now has a list stamp (build/embed-vocabs.list, and -free),
  rewritten only when the list changes, as a prerequisite of the embedded
  stream.
- **New finding, fixed:** embedding had guaranteed each form loaded
  before its app; block-loaded, nothing loaded the form. Each form's
  catalog blocks hold Forth source, not form text, so FORM-LOAD's block
  path can't stand in for it. notepad, hello-app and file-browser each
  gain a `REQUIRES:` line for their form (one name per line, because of
  the first-name gap, Q-D3).
- **Tests:** tests/test_catalog_registry.py loads NOTEPAD-FORM first.
  `make test-pad-move` (port +69) is in `make test`.
- **Limits, about 2x measured, never raised as a fix:** T_BLK_EVICT 60
  (27 s), T_MIRROR 60 (30 s), T_INTERP_ABORT 90 (44 s), T_PAD_MOVE 40
  (17 s). The first two were 150 before.

**Green: test-pad-move 19/19** (`8b340b52`):
- K4: content 99,804 B, so **14,884 B of pad left**.
- K1: each app is absent at boot.
- K2: each loads, and its entry word is found.
- K3: NOTEPAD-FORM resolves from blocks before the load and from the
  registry after.
- K5: each form loads with its app, and FORM-LOAD builds 21, 9 and 9
  widgets.
- I1: unchanged.

Both kernels pass the boot gate.
