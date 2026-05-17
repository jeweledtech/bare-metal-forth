# Open-Core Boundary Audit — 2026-05-16

Reference: ownership model established in commit 67749de
(`INCIDENT_REPO_SPLIT_DIVERGENCE.md` resolution, Option A).

---

## 1. Complete File Classification

### Legend

- **PUBLIC-OWNED**: tracked in public git, not gitignored, canonical source is public repo
- **PRIVATE-OWNED**: gitignored in public, tracked in private repo, on-disk for build only
- **PUBLIC-APP**: tracked in public, gitignored in private (application layer per incident resolution)
- **DUAL-TRACKED**: tracked in both repos (ownership violation)
- **ORPHAN**: untracked in public, not gitignored, not in private (no owner)

### Full Table (57 files in public forth/dict/)

| File | Pub Tracked | Pub Ignored | EMBED | Priv Tracked | Content | Classification |
|------|:-----------:|:-----------:|:-----:|:------------:|---------|----------------|
| ahci.fth | - | YES | YES | YES | **DIVERGED** (+104B pub) | PRIVATE-OWNED |
| arm64-asm.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| asm-vocab.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| audio.fth | - | YES | - | YES | **DIVERGED** (+168B pub) | PRIVATE-OWNED |
| auto-detect.fth | - | YES | YES | YES | identical | PRIVATE-OWNED |
| cab-extract.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| catalog-resolver.fth | YES | - | YES | - | n/a | PUBLIC-OWNED |
| deflate.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| dict_system.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| disasm.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| disk-survey-form.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| echoport.fth | YES | - | YES | - | n/a | PUBLIC-OWNED |
| editor.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| fat32.fth | - | YES | YES | YES | identical | PRIVATE-OWNED |
| file-browser-form.fth | YES | - | YES | - | n/a | PUBLIC-APP |
| file-browser.fth | YES | - | YES | - | n/a | PUBLIC-APP |
| file-editor.fth | YES | - | YES | - (gitignored) | identical on-disk | PUBLIC-APP |
| file-stream.fth | YES | - | YES | - | n/a | PUBLIC-APP |
| graphics.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| gui-harvest.fth | - | YES | YES | YES | identical | PRIVATE-OWNED |
| hardware.fth | YES | - | YES | **YES** | identical | **DUAL-TRACKED** |
| hello-app.fth | YES | - | YES | - | n/a | PUBLIC-APP |
| hello-form.fth | YES | - | YES | - | n/a | PUBLIC-APP |
| meta-compiler.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| mirror.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| msi-reader.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| ne2000.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| net-dict.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| notepad-form.fth | YES | - | YES | - (gitignored) | n/a | PUBLIC-APP |
| notepad.fth | YES | - | YES | - (gitignored) | identical on-disk | PUBLIC-APP |
| ntfs.fth | - | YES | YES | YES | identical | PRIVATE-OWNED |
| pci-enum.fth | YES | - | YES | - | n/a | PUBLIC-OWNED |
| pit-timer.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| port-mapper.fth | YES | - | YES | - | n/a | PUBLIC-OWNED |
| port-monitor-form.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| port-monitor.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| ps2-keyboard.fth | YES | - | YES | - | n/a | PUBLIC-OWNED |
| ps2-mouse.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| rtl8139.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| rtl8168.fth | - | YES | YES | YES | identical | PRIVATE-OWNED |
| serial-16550.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| stub-dispatch.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| surveyor-deep.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| surveyor-detail.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| surveyor.fth | - | YES | YES | YES | identical | PRIVATE-OWNED |
| target-arm64.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| target-cortex-m.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| target-x86.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| thumb2-asm.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| ui-core.fth | - | YES | YES | YES | **DIVERGED** (+1,232B pub) | PRIVATE-OWNED |
| ui-core-minimal.fth | - | - | - | - | n/a | **ORPHAN** |
| ui-events.fth | - | YES | YES | YES | **DIVERGED** (+216B pub) | PRIVATE-OWNED |
| ui-parser.fth | - | YES | YES | YES | identical | PRIVATE-OWNED |
| vga-graphics.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| video.fth | - | YES | - | YES | identical | PRIVATE-OWNED |
| x86-asm.fth | YES | - | - | - | n/a | PUBLIC-OWNED |
| zip-reader.fth | - | YES | - | YES | identical | PRIVATE-OWNED |

### Summary Counts

| Classification | Count |
|----------------|------:|
| PUBLIC-OWNED (free vocabs) | 16 |
| PUBLIC-APP (application files, public canonical) | 8 |
| PRIVATE-OWNED (paid tier, correctly gitignored) | 29 |
| DUAL-TRACKED (violation) | 1 |
| ORPHAN (no owner) | 1 |
| **Files with content divergence** | **4** |
| **Total** | **57** |

---

## 2. Issues Requiring Attention

### 2a. DUAL-TRACKED: hardware.fth

| Field | Value |
|-------|-------|
| First commit (public) | Pre-split (part of original kernel) |
| First commit (private) | 134b162 (2026-04-13, repo split import) |
| Most recent commit (private) | 52feec5 "HARDWARE: mirror PIT ch2 gate fix from public repo (c90ed26)" |
| Content | Identical (3,931 bytes) |

**Problem**: hardware.fth is a free-tier vocab (PUBLIC-OWNED per .gitignore
and tier structure) but is also tracked in the private repo. The private
repo has no .gitignore entry for it. This means edits in either repo can
diverge silently — the same pattern that caused the file-editor.fth incident.

### 2b. ORPHAN: ui-core-minimal.fth

| Field | Value |
|-------|-------|
| Size | 466 bytes |
| Modified | 2026-04-19 |
| CATALOG header | UI-CORE-MIN |
| Category | gui |
| Tracked | No (neither repo) |
| Gitignored | No |

**Problem**: This file exists on disk in the public repo's forth/dict/ but
is not tracked by git, not gitignored, and not present in the private repo.
It appears to be an experimental minimal UI-CORE stub. It will show in
`git status` noise indefinitely.

### 2c. DIVERGED FILES (4 files, all PRIVATE-OWNED)

These are correctly classified as private-owned. The issue is that the
on-disk working copies in the public repo (used for `make`) have been
modified locally and are now AHEAD of the private repo's committed version.
The private repo's tracked version is stale.

| File | Pub on-disk | Priv committed | Gap |
|------|------------:|---------------:|-----|
| ahci.fth | 10,066 | 9,962 | +104B — KERNEL-BLOCK constant + fallback dispatch |
| audio.fth | 8,513 | 8,345 | +168B — TODO comment re: BIOS-reserved memory |
| ui-core.fth | 10,691 | 9,459 | +1,232B — Milestone 2 d-word attributes (WTO-DWORD, SET-VISIBLE, CLR-VISIBLE, etc.) |
| ui-events.fth | 4,631 | 4,415 | +216B — visibility-aware NEXT-FOCUSABLE and BUTTON-ACTIVATE |

**Root cause**: The reconciliation commit (66a2160, 2026-05-16) aligned
file-editor, gui-harvest, and auto-detect but did NOT sync these 4 files.
The on-disk copies were modified during Milestone 2 work (2026-05-08) and
the private repo never received the updates.

---

## 3. README Paid-Tier Claims vs Reality

README states: *"The paid vocabulary tier (AHCI, NTFS, RTL8168, NIC drivers,
UBT pipeline, metacompiler) lives in a separate private repo. The kernel and
the free vocabularies are all you need to get running."*

### Technology Location Map

| Technology | README Claims | Actual Location | Status |
|------------|:------------:|-----------------|--------|
| AHCI | Paid/private | Gitignored in public, tracked in private, on-disk for build | Correct |
| NTFS | Paid/private | Gitignored in public, tracked in private, on-disk for build | Correct |
| RTL8168 | Paid/private | Gitignored in public, tracked in private, on-disk for build | Correct |
| NIC drivers | Paid/private | ne2000.fth is PUBLIC-TRACKED (free); rtl8168 is paid | **MIXED** |
| UBT pipeline | Paid/private | Gitignored in public, tracked in private (tools/translator/) | Correct |
| Metacompiler | Paid/private | Gitignored in public, tracked in private | Correct |
| UI substrate | Implied paid | ui-core, ui-parser, ui-events, gui-harvest: gitignored in public, tracked in private | Correct |
| FAT32 | Not mentioned | Gitignored in public, tracked in private | **Undocumented paid** |
| AUTO-DETECT | Not mentioned | Gitignored in public, tracked in private | **Undocumented paid** |
| SURVEYOR | Not mentioned | Gitignored in public, tracked in private | **Undocumented paid** |

### Critical False Claim

> "The kernel and the free vocabularies are all you need to get running."

**FALSE.** The public Makefile's EMBED_VOCABS list includes 10 gitignored
(paid) files. Running `make` in a fresh clone fails with FileNotFoundError
because ahci.fth, ntfs.fth, rtl8168.fth, auto-detect.fth, fat32.fth,
surveyor.fth, ui-core.fth, ui-parser.fth, ui-events.fth, and gui-harvest.fth
do not exist. The public repo is **not independently buildable**.

### EMBED_VOCABS Ownership Split

| Ownership | Count | Files |
|-----------|------:|-------|
| Public-tracked (free) | 18 | hardware, port-mapper, echoport, pci-enum, catalog-resolver, ps2-keyboard, ui-core, ui-parser, ui-events, gui-harvest, file-editor-core, notepad-form, notepad, hello-form, hello-app, file-stream, file-browser-form, file-browser |
| Gitignored (paid, on-disk) | 7 | ahci, rtl8168, ntfs, auto-detect, fat32, surveyor, file-editor-disk |

*Updated 2026-05-17: UI substrate (4 files) promoted to public. file-editor split into file-editor-core (public) + file-editor-disk (paid).*

---

## 4. Private Repo Tracking Violations

Files the public repo declares as public-owned (per INCIDENT resolution)
that the private repo incorrectly tracks:

| File | Private Tracked? | Private Gitignored? | Status |
|------|:----------------:|:-------------------:|--------|
| file-editor.fth | NO | YES | Correct |
| notepad.fth | NO | YES | Correct |
| notepad-form.fth | NO | YES | Correct |
| hello-app.fth | NO | YES | Correct |
| hello-form.fth | NO | YES | Correct |
| file-browser.fth | NO | YES | Correct |
| file-browser-form.fth | NO | YES | Correct |
| file-stream.fth | NO | YES | Correct |
| **hardware.fth** | **YES** | **NO** | **VIOLATION** |

**hardware.fth** is the only violation. It is free-tier, public-owned, but
tracked in both repos without a .gitignore entry in the private repo.

---

## 5. Recommendations

### 5a. hardware.fth — DUAL-TRACKED

**Action: (a) Untrack from private, add to private .gitignore**

Rationale: hardware.fth is free-tier, public-canonical. The private repo
tracked it only because the original repo-split import (134b162) brought
all .fth files wholesale. The single private commit (52feec5) was a
manual mirror that confirms public is canonical. Add to private .gitignore
alongside the other public-owned files.

Commands (for private repo):
```bash
git rm --cached forth/dict/hardware.fth
echo "forth/dict/hardware.fth" >> .gitignore
git commit -m "untrack public-owned hardware.fth, add to .gitignore"
```

### 5b. ui-core-minimal.fth — ORPHAN

**Action: (b) Either track in public (if it's a free stub) or gitignore
(if it's a paid experiment)**

Rationale: 466 bytes, no dependencies, appears to be a minimal fallback
for builds that don't need full ui-core. If it's meant to enable a
"free-tier GUI" path in the future, track it publicly. If it's a
one-off experiment, delete it.

Suggested: gitignore it for now (it's not referenced by Makefile or
any test), revisit when the free-tier build path is designed.

### 5c. ahci.fth — DIVERGED (private behind)

**Action: (c) Sync private from public on-disk copy, then continue
normal ownership (private-owned)**

The delta is small (KERNEL-BLOCK constant + fallback dispatch, 104 bytes).
This is a functional improvement made during file-browser development.
Copy the public on-disk version to private, commit.

### 5d. audio.fth — DIVERGED (private behind)

**Action: (c) Sync private from public on-disk copy**

The delta is a 4-line TODO comment warning about BIOS-reserved memory.
Trivial, no code change. Copy and commit.

### 5e. ui-core.fth — DIVERGED (private behind, +1,232 bytes)

**Action: (c) Sync private from public on-disk copy**

The delta is the entire Milestone 2 d-word attribute system (WTO-DWORD,
DW-VISIBLE, DW-ENABLED, SET-VISIBLE, CLR-VISIBLE, SET-ENABLED,
CLR-ENABLED, WIDGET-VIS?, WIDGET-ENA?). This is critical infrastructure
that the private-tracked test suites depend on. The private commit 188939e
added only IV-CLEAR (1 line) but missed the 50+ lines of attribute code.

This is the highest-priority sync — without it, the private repo's
ui-core.fth cannot support Milestone 2+ features.

### 5f. ui-events.fth — DIVERGED (private behind, +216 bytes)

**Action: (c) Sync private from public on-disk copy**

The delta adds visibility-aware checks to NEXT-FOCUSABLE and
BUTTON-ACTIVATE. These are the runtime counterparts to ui-core.fth's
attribute words — syncing one without the other would leave the private
build broken.

### 5g. README.md — False "independently buildable" claim

**Action: (b) Ratify current state and update README**

Options:
1. **Make it true**: Add a `EMBED_VOCABS_FREE` subset to the Makefile
   that builds a minimal (14-vocab) image from public-only sources.
   README claim becomes accurate.
2. **Make it honest**: Update README to say "full build requires the
   private vocabulary repo; a free-tier minimal image is planned."

Recommended: Option 2 now (documentation fix), Option 1 later when
the free-tier build path is designed.

---

## 6. Pre-Commit Hook Assessment

The hook in `.git/hooks/pre-commit` correctly:
- Reads staged files via `git diff --cached`
- Matches against .gitignore paid-tier patterns
- Blocks staging of any matching .fth file
- Provides override instruction (--no-verify)

**Gap**: The hook protects against future leaks but cannot detect the
existing dual-tracking issue (hardware.fth was tracked before the hook
existed). The hook also doesn't guard against Makefile changes that would
add new paid files to EMBED_VOCABS without corresponding .gitignore entries.

---

## 7. Summary of Required Actions

| Priority | File/Issue | Action | Effort |
|:--------:|------------|--------|--------|
| 1 | ui-core.fth divergence | Sync public→private | 1 commit |
| 2 | ui-events.fth divergence | Sync public→private | 1 commit |
| 3 | ahci.fth divergence | Sync public→private | 1 commit |
| 4 | audio.fth divergence | Sync public→private | 1 commit |
| 5 | hardware.fth dual-tracking | Untrack from private, add .gitignore | 1 commit |
| 6 | README "independently buildable" | Update text | 1 commit |
| 7 | ui-core-minimal.fth orphan | Gitignore or delete | 1 line |

Items 1-5 are private-repo commits. Item 6 is a public-repo commit.
Item 7 is either repo depending on decision.

No leaks found in the current state. The gui-harvest and auto-detect
leaks fixed in caa66fd have not recurred. The pre-commit hook is
functioning as designed.

---

*Read-only audit. No files modified except this report.*
