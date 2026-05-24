# Claims vs. Reality — Translator & Marketing Reconciliation — 2026-05-23

**Type:** Findings record + marketing decision-support. The *decision* this
supports already lives in `docs/DECISIONS.md` ("C/Python are bootstrap
scaffolding"). This file is the **receipts** behind that decision plus the
**marketing reconciliation** that is this chat's job — not a duplicate of the
decision log.

**Already saved elsewhere (do not duplicate):**
- `docs/DECISIONS.md` — the C-is-scaffolding decision, abandoned-by-design
  native-codegen branches, UBT-vs-metacompiler distinction, Forth-hosted-
  translator framing.
- Claude Code memory `audit_marketing_vs_reality_2026_05_21.md` — the general
  realization and Shopify exposure note.
- `[ARCHIVED]` header on the stale UBT skeleton README in `archive/`.

**Source:** Two read-only Claude Code audits (translator line-count/capability
audit; Forth-side reimplementation audit) plus the file-currency check.

---

## ⚠️ Active blocker — reconcile before anything else

`make test` is **currently failing**: `TIMES value -1314 is negative` at
`forth.asm:5069` — kernel over its KERNEL_PADDED_SIZE boundary. Claude Code
flagged this as the 6th instance of the memory-map collision pattern.

**The cross-session smoking gun:** that −1314 is the *same 1,314 bytes* the
form-engine session was overflowing by **before** it removed Settings from
EMBED_VOCABS. In that session the full-tier kernel built clean at exactly
0x1C000 (114,688 bytes) *after* the removal. This session — same machine
(bbrown) — shows the pre-removal failure, with `M Makefile` dirty at session
start. Likely the form-engine Makefile fix never committed (stashed / reverted /
lost) or the embed blob regrew. **The two sessions disagree about whether the
kernel builds.** Resolve this on the machine first; a broken `make test` blocks
validating every other piece of open work.

---

## What actually works (the marketable reality)

- **C translator pipeline, end-to-end:** PE/ELF/COM load → x86 decode → UIR
  lift → semantic analysis (HAL-call recognition: READ_PORT_UCHAR→INB, etc.) →
  Forth-vocabulary source codegen. Validated on real Windows/Linux drivers
  (i8042prt, serial, ACPI) on HP bare metal. This is the differentiated product.
- **Metacompiler:** real and working — 1300+ lines, ~80 core words, self-hosting
  proven (test_meta_b6b 17/17). Builds bootable Forth kernels from Forth source.
- **Forth prerequisite vocabs (real, ~285 words):** DISASM (x86 decoder, used
  for live debugging), X86-ASM / ARM64-ASM / THUMB2-ASM (machine-code emitters),
  target drivers. These are building blocks, not a translator.

The honest headline: a host-side tool that turns foreign driver binaries into
Forth vocabularies that run on bare metal, plus a self-hosting metacompiler.
That is genuinely differentiated and currently under-marketed relative to the
vapor.

---

## What's overstated or vapor (the receipts)

| Claim | Reality |
|---|---|
| Line counts (x86_decoder 2784, codegen 1724, etc.) | AI-fabricated at archive time; never matched any version. Some live files exceed claim (translator.c 190%), others are 0.1% of it. |
| `codegen.c` — "native x64/ARM64/RISC-V generator" | `codegen.c` is a 1-line placeholder. Forth codegen works; native codegen does not. |
| `-t x64` / `-t arm64` / `-t riscv64` | Flags parse to enum values but **no dispatch handler exists** — produce no output ("parse but don't dispatch"). |
| x86 "99.95% coverage, SSE/AVX/AVX2" | Unsourced figure. Decoder is real and doesn't desync, but SSE/AVX decode to `X86_INS_NOP` — parse-only, no semantics. |
| ARM64 decoder | Real (915 lines) + UIR lifter exists, but **not wired into the CLI** — only reachable via test suite. |
| `riscv_decoder` / `optimize` / `api_map` | 1-line placeholders. Zero implementation. (api_map's real capability lives in semantic.c.) |
| **NEW:** README line 48 — metacompiler "builds for ARM64, RISC-V, Cortex-M33" | x86 + ARM64 (QEMU raspi3b) proven. RISC-V and Cortex-M33 have assemblers + target files written but **unvalidated** on hardware/emulator. Same vapor pattern, softer form. |

Working targets actually wired: `disasm`, `uir`, `forth`, `report`. That's it.

---

## The C/Forth boundary (so future sessions don't misread it)

Translation happens **entirely in C, offline.** The C tool emits Forth source
*text*; Python lays it on a block disk; Forth's `THRU` compiles it at boot.
**Zero C runs on bare metal; zero translation happens in Forth.** The
gui-harvest.fth UBT stub ("hooks into UBT when translator is ported to a Forth
vocabulary") explicitly marks the not-yet-built hook point. A future session
should neither assume the Forth translator is partway built (it isn't) nor
dismiss it as impossible (the prerequisite parts exist, just uncomposed).

---

## Marketing reconciliation (this chat's deliverable)

Two products, two **opposite** directions — do not conflate:

**UBT (C translator): narrow the claims DOWN to match engineering.** It was
marketed against the maximalist vision. The fix is editorial, not engineering:
market the binary→Forth-vocabulary capability it actually has and that is proven
on HP. Drop native-codegen / multi-arch-translation language.

**Metacompiler: raise productization UP to match the capability.** It genuinely
works as claimed. Any gap is packaging/docs for a customer to invoke it — not an
overclaim. Don't narrow this one.

**Copy that needs editing (specifics):**
- `README.md` line 48 — RISC-V/Cortex-M33 "builds for" → soften to "x86 and
  ARM64 proven; RISC-V/Cortex-M33 targets in development" (or remove until
  validated).
- Any Shopify / landing copy claiming native codegen, universal native
  translation, or multi-arch output from UBT.

**Shopify exposure (from CC marketing memory, restated for action):**
- Tiers 1–3 (vocabulary packs, $49/$39/$99): no exposure — these are fine.
- **Tier 4 — UBT Pipeline ($149):** primary exposure. Reconcile the listing to
  the binary→Forth reality before it's the thing a technical buyer tests.
- **Tier 5 — Metacompiler Pack ($199):** at most a packaging/docs gap, NOT an
  overclaim. Capability is real; make it invokable and documented.

Neither case is a backlog of features to build. One is "say less"; the other is
"package what exists."

---

## What is NOT worth saving from this session

The file-existence check, the archive-directory inventory, and the doc-archiving
mechanics are reconstructable and already acted on. The DECISIONS.md entry itself
is in the repo. This file exists for the receipts + the marketing actions + the
two un-captured findings (README overclaim, build break).
