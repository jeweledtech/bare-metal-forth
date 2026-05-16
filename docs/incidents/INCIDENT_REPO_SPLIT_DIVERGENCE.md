# Incident: Repo-Split File Ownership Divergence

**Discovered**: 2026-05-15, during polish tier cleanup (Items 1/3)
**Status**: RESOLVED (2026-05-16)
**Severity**: Medium — no data loss, but every commit to affected files
widens the divergence and increases future merge cost
**Resolution**: Option A (public owns apps) with pre-commit hook guard.
Leaks fixed (caa66fd), files reconciled (66a2160), ownership documented.

---

## Discovery

While committing Item 1 (VGA-PUTC fix, commit 4eebfc9 in public repo)
and Item 3 (FAT32 LFN bitmask, commit a8cc9b9 in private repo), a
routine check of the private repo's working tree revealed uncommitted
changes in two files that the public repo also tracks. Investigation
showed structural divergence — not a simple sync gap.

## Background

The open-core repo split happened at:
- Public repo (forthos): commit 4bbf6a2
- Private repo (forthos-vocabularies): commit 134b162
- Documented in memory entry #19 (repo_split_2026_04_13.md)

Stated discipline: "Never git add paid paths in public repo. Mirror
manually." The split designated 19 free vocabs as public and paid
content in the private repo.

## Affected Files

### 1. file-editor.fth — DIVERGED (Critical)

**Tracked in both repos.** 118 diff lines between the public and
private copies. This is NOT a sync gap — the two copies have
structurally diverged with different naming conventions and
implementations.

**Naming divergences:**

| Public repo (forthos) | Private repo (forthos-vocabularies) |
|-----------------------|-------------------------------------|
| `FE-VGA` (constant) | `VGA` (constant) |
| `FE-LINE-LEN` (word) | `LINE-LEN` (word) |
| `CUR-FE-LINE-LEN` (word) | `CUR-LINE-LEN` (word) |

**Implementation divergences:**
- `LINE-LEN` / `FE-LINE-LEN`: private uses stack-based approach
  (`OVER`/`NIP`/`SWAP 1+ SWAP 1+`), public uses `LS-OFF` variable
  and simpler control flow
- `BUF-DEL`: private has `DUP FE-SIZE @ 1- >=` guard and different
  CMOVE size calculation; public has `DUP FE-SIZE @ >=`
- `FE-OPEN`: private has LEAVE-safe DO/LOOP with IF/ELSE and
  FE-STRIP-CR call; public has simpler `FILE-SZ @ 1000 MIN FE-SIZE !`

**Features present only in public:**
- `FE-STRIP-ALL-CR` (commit c766196, 2026-05-15)
- VGA-PUTC fix: `1+ C!` instead of `SWAP 1+ C!` (commit 4eebfc9, 2026-05-15)

**Features present only in private (uncommitted working copy):**
- `FE-STRIP-CR` (CRLF-only variant)
- `FE-CTRL?` helper
- LEAVE-comment block in FE-OPEN

**The divergence predates the May 15 work.** The different naming
conventions (VGA vs FE-VGA, LINE-LEN vs FE-LINE-LEN) existed before
commits c766196 and 4eebfc9 were made. The May 15 commits widened
the gap further.

### 2. ui-core.fth — Behind (Manageable)

**Gitignored in public, tracked in private.** This is the correct
ownership model — ui-core.fth is a paid-tier file. The local copy
in the public repo's working directory is the source of truth for
development but is correctly gitignored from public commits.

**Sync gap (59 diff lines):** The private repo's committed version
is missing:
- D-word attribute constants: `WTO-DWORD`, `WTO-DW-HI`, `DW-VISIBLE`,
  `DW-ENABLED`, `DW-VIS-ENA`
- D-word access words: `W-DW!`, `W-DW@`, `W-DW-HI!`, `W-DW-HI@`
- Visibility/enable helpers: `SET-VISIBLE`, `CLR-VISIBLE`,
  `SET-ENABLED`, `CLR-ENABLED`, `WIDGET-VIS?`, `WIDGET-ENA?`
- `IV-CLEAR` call inside `ADD-INPUT` (1 line, uncommitted in working copy)

**Resolution**: Straightforward sync — copy local to private, commit.
No naming divergence, no structural conflict.

### 3. notepad-form.fth — Accidental Duplicate (Trivial)

**Tracked in public, untracked in private.** Byte-identical copy.
The file was committed to the public repo at 7f7c8c8. The private
repo's copy is an accidental artifact from a manual copy session.

**Resolution**: Delete the private repo's copy or add to .gitignore.

## Current State

- Public repo commit 4eebfc9 (Item 1: VGA-PUTC fix) is **unpushed**.
  It modifies file-editor.fth, which is tracked in both repos.
- Private repo commit a8cc9b9 (Item 3: FAT32 LFN bitmask) is
  **unpushed**. It modifies fat32.fth and surveyor.fth only (correctly
  private-only files).
- Neither commit will be pushed until the ownership question is settled.

## Open Question

**Which repo owns file-editor.fth long-term?**

Option A: **Public owns it.** Remove from private repo tracking.
Private repo's combined.img build pulls from the public repo's copy
(or a submodule/symlink). The structural divergences in the private
copy are abandoned — the public copy's naming convention (FE-VGA,
FE-LINE-LEN) wins.

Option B: **Private owns it.** Remove from public repo tracking, add
to .gitignore. Public repo consumers (smoke tests, QEMU harness) use
the local working copy. The private copy's naming convention (VGA,
LINE-LEN) wins, and all recent public-repo commits (c766196, 4eebfc9)
need to be ported to the private version.

Option C: **Reconcile and pick one.** Merge the divergent changes into
a single canonical version. Assign ownership to one repo. Delete the
other copy.

## Files That May Also Be in This State (Not Yet Investigated)

The following application-layer .fth files are tracked in the public
repo and may also have copies (tracked or untracked) in the private
repo with unknown divergence status:

- notepad.fth
- hello-app.fth
- hello-form.fth
- file-browser.fth
- file-browser-form.fth
- file-stream.fth
- gui-harvest.fth
- ui-events.fth
- ui-parser.fth

These should be audited for the same dual-tracking / divergence pattern
before any ownership decision is finalized.

## Impact on Current Work

- Item 1 (VGA-PUTC fix): committed to public repo only. If private repo
  ownership is chosen (Option B), the fix must be ported to the private
  copy with the different naming conventions.
- Item 3 (FAT32 LFN bitmask): committed to private repo. No ownership
  conflict — fat32.fth and surveyor.fth are correctly private-only.
- Item 2 (NOTEPAD button): deferred. No ownership impact.

---

## Resolution (2026-05-16)

**Decision: Option A — public owns application files.**

### Ownership Rule

**Public repo (forthos) owns:**
- Kernel (forth.asm, boot.asm)
- Free embedded vocabs (hardware, port-mapper, echoport, pci-enum,
  catalog-resolver, ps2-keyboard)
- Application files (file-editor, notepad, notepad-form, hello-app,
  hello-form, file-browser, file-browser-form, file-stream)
- Free block-loadable vocabs (editor, x86-asm, disasm, mirror, etc.)

**Private repo (forthos-vocabularies) owns:**
- Tier 1: ahci, ntfs, fat32, auto-detect
- Tier 2: rtl8168
- Tier 3: surveyor, graphics, audio, video, stub-dispatch, ui-core,
  ui-parser, ui-events, gui-harvest, disk-survey-form, port-monitor
- Tier 4: translator, driver-extract tools
- Tier 5: meta-compiler, target-x86, target-arm64, arm64-asm

**Rule:** Files owned by one repo MUST NOT be git-added in the
other. The private build consumes public files from local disk
(sibling checkout), not from its own tracking.

### Actions Taken

1. **Leaks fixed** (public commit caa66fd): `git rm --cached`
   gui-harvest.fth and auto-detect.fth from public tracking.
2. **Pre-commit hook installed** in public .git/hooks/pre-commit:
   rejects staging of any .fth file matching .gitignore paid-tier
   patterns. Catches `git add -f` bypass.
3. **Bug fixes** (private commit 188939e): `[']` in notepad.fth,
   FE-STRIP-ALL-CR and FE-CTRL? in file-editor.fth, IV-CLEAR in
   ui-core.fth.
4. **Files reconciled** (private commit 66a2160): file-editor.fth,
   gui-harvest.fth, auto-detect.fth aligned with public canonical.
5. **Ownership enforced** in private: file-editor.fth and notepad.fth
   untracked from private, added to private .gitignore.

### Prevention

- Pre-commit hook in public repo guards against re-leaking paid files.
- Private .gitignore lists all public-owned .fth files.
- Phase 3 (git submodule) deferred until manual sync proves unstable.

### Items 1/3 Status

- Item 1 (VGA-PUTC fix, 4eebfc9): pushed to public, reconciled to
  private via file-editor.fth alignment.
- Item 3 (FAT32 LFN bitmask, a8cc9b9): pushed to private.
- HP validation of Item 1 (ghost highlights): still pending.
