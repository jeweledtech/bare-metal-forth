# Form-Engine Findings — 2026-05-23

**Type:** Findings record (not a task doc, not a mentor session). The
gaps-per-panel tally below is a *running instrument* — append to this file
when panel #5+ lands rather than starting a new one. The trend lives in one
place on purpose.

**Source:** Settings panel build (Milestone 4) + Phase 0 block-loading audit.

**Validation status:** Gaps were found *during build*. The build was
interrupted (403/login) before QEMU full-tier + free-tier runtime checks,
`make test-smoke`, and `make check-sync` ran. Settings builds clean
(full-tier 114,688 bytes, fits under KERNEL_PADDED_SIZE; combined image has
Settings at blocks 829–852, catalog non-blank) but is **not yet
runtime-validated in QEMU or on HP.** Do not treat Settings as validated.

---

## Phase 0 load-path finding (clears two tracks)

For form panels, FORM-LOAD takes the in-memory branch, not a block read.
The chain: `settings-form.fth` CREATEs the form buffer in RAM and calls
CATALOG-REGISTER, which sets CATALOG-MEM=1. When SETTINGS-RUN calls
CATALOG-FIND, it hits the in-memory registry first, and FORM-LOAD takes the
`CATALOG-MEM @ IF` branch — reads from RAM, no block I/O.

Consequence: even when Settings is loaded from blocks via THRU, the form
data is CREATEd in RAM *during* that THRU evaluation, before SETTINGS-RUN
ever calls FORM-LOAD. There is no nested block read. The single-buffer
collision risk (the "works in QEMU, bites on HP" failure mode the Phase 0
task was built to surface) is **structurally absent for form panels.**

Why this matters beyond panels: the loader is now shown able to nest a
parser-driven read inside a block-loaded vocab. That is exactly the path the
UBT track needs to deliver translated driver vocabularies into a running
ForthOS. One verification clears the panel ceiling AND hardens the UBT
delivery mechanism — provided runtime validation confirms the audit read.

`USING <panel>` block-loading is therefore viable; the boot blob can hold at
the ~7 boot-critical vocabs regardless of panel count. (Pending runtime
confirmation.)

---

## Three framework gaps surfaced by panel 4

All three are the same class: the framework worked for panels 1–3 because
they happened to dodge the gap; the new panel reveals it. Settings dodges all
three (finite interactions, no live rendering, bounded clicks). A clock, a
live system monitor, a progress display, or a network-traffic view would not.

**Gap #1 — DROPBOX is non-interactive.** WT-DROPBOX renders as `[label v]`
and is focusable via TAB, but: no activation (HANDLE-KEY has no ENTER case;
ADD-DROPBOX never stores an XT), no visual focus (RENDER-DROPBOX uses
ATTR-NORM, not RW-ATTR), no value buffer (unlike INPUT's IV-BASE).
Workaround used: cycling BUTTONs with runtime label updates (the hello-app
HA-GO pool-string pattern). To fix properly: ENTER handling for DROPBOX in
HANDLE-KEY (~5 lines), RW-ATTR in RENDER-DROPBOX (~2 lines), accept XT in
ADD-DROPBOX, wire in FORM-WIRE. ~15 lines across 4 core files.

**Gap #2 — render attributes are CONSTANTs, not VARIABLEs.** ATTR-NORM (7)
and ATTR-INV (112) in ui-core.fth are compile-time constants, hardcoded in
all render words. No setting can take genuinely live, system-wide effect
without an engine edit. The Settings "visible effect" is a post-exit VGA
banner (SC-DEMO writes a colored row after FORM-RUN exits) — this proves
Apply reads-and-uses the value *once*, but does NOT prove a live setting.
To fix properly: make ATTR-NORM/ATTR-INV VARIABLEs, update ~5 render words
to use `@`. ~12 lines in ui-core.fth. (Noted for Milestone 4a.)

**Gap #3 — label updates leak pool memory; no in-place mutation.**
SC-SET-LABEL (and the HA-GO pattern it's based on) updates a label by
allocating a NEW pool string and repointing the widget — the old string is
never reclaimed. Pool is ~44KB (0x202000–0x20D000); each update burns
~5–10 bytes. Safe for finite-interaction panels (Settings, dialogs: bounded
clicks consume <2KB). Would slowly exhaust the pool for any
continuously-updating panel; a panel updating a label on a timer would
eventually crash. To fix properly: add pool compaction, or an in-place label
mutation word that reuses the existing slot when the new string fits.

**Discipline note:** none of the three were fixed in this task. That is what
keeps the experiment honest — Settings is built around the gaps and the gaps
are reported, not patched mid-panel.

---

## Gaps-per-panel tally (the running instrument)

| Panel | # | Gaps surfaced | Cumulative |
|---|---|---|---|
| NOTEPAD | 1 | 0 | 0 |
| HELLO-APP | 2 | 0 | 0 |
| FILE-BROWSER | 3 | 0 | 0 |
| SETTINGS | 4 | 3 | 3 |

This is the N=4 reading on the reduction-posture experiment. The open
question: is this "fine, patch holes as we go, they trend to zero" or "every
panel keeps finding new holes, so the cost isn't actually sub-linear"? One
panel can't answer it; the trend across the next several can.

- If panel #5 finds three more *different* gaps and #6 finds three more →
  evidence the OS surface is genuinely large and the reduction posture is
  starting to look like rationalization. The maximalist capability would
  earn its keep.
- If #5 finds one gap and #6 finds zero *because the earlier gaps got
  patched and stayed patched* → framework converging, reduction validated.

You can't read that trend if the gaps aren't logged consistently. Hence:
append to this file, keep the tally cumulative.

---

## What is and isn't sub-linear (the honest split)

**Sub-linear (needed zero changes):** the rendering/event/wiring plumbing —
FORM-LOAD, FORM-WIRE, FORM-RUN, WIDGET-REGISTER, the focus cycle. The
declaration:logic ratio improves panel over panel:

- FILE-BROWSER: ~8 declaration : ~500+ logic (1:60+)
- NOTEPAD: ~24 : ~130 (1:5.4)
- HELLO-APP: ~10 : ~40 (1:4)
- SETTINGS: ~20 : ~60 (1:3)

**Not yet sub-linear:** the widget palette (DROPBOX half-finished, #1), the
render-state model (immutable attributes, #2), and memory management (no
in-place label mutation, #3). Panels 1–3 never hit these because they were
button-heavy, read-mostly, and didn't update labels continuously.

The plumbing is doing its job. The palette / render-state / memory layers
are where the next several panels will tell us whether the framework
converges or keeps leaking new gaps.
