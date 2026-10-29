# TASK: interpreter correctness (undefined word aborts; `(` over serial; interpret-mode `."`)

Status: PLAN + CENSUS A, RULED (2026-10-11), no code changed. Rulings in §6.

Owner ruling 2026-10-11 covers three changes:
1. An undefined word aborts and discards the rest of the line, as in
   Forth-83.
2. The `(` serial wedge.
3. Interpret-mode `."`.

The plan opens with a census: every vocabulary load, embedded or
block-loaded, that passes through an undefined word today. Each one
becomes a hard failure once the fix lands. The census includes the
seven top-level `."` lines. The plan and census come back before any
code.

Findings:
- docs/evidence/finding-undefined-word-continues-2026-10-11.md
- docs/evidence/finding-serial-paren-comment-wedges-2026-10-06.md

## 1. Census A: vocabulary loads (measured 2026-10-11)

The image was combined.img `38671d92…` (public 707b22f + private
65f12cf); bmforth-free.img `85f2cdfc…` was rebuilt from the same tree.
An error is the kernel's `<word> ? ` signature.

### Embedded streams: 0 undefined words

- **Full kernel:** booted from floppy with serial to a file, so
  nothing is lost before a client connects. The log is the banner,
  then `ok`, with no signature.
- **Free kernel:** same.
- **Control:** a kernel built outside the tree, whose stream has
  `ZZCENSUS` inserted at the start of hardware.fth. It prints
  `ZZCENSUS ?` on serial (and on VGA), then continues to `ok`. So
  embedded errors do reach serial, and the 0 above is measured, not
  unobserved.
- **The control also shows the hazard the fix creates.** Today the boot
  stream carries on past an error. Once an undefined word aborts, it
  would stop the boot stream there, and every later embedded vocabulary
  would be missing (§3, D1c).

### Block loads: 70 catalog entries, 9 pass through an undefined word

2026-10-28: five of the nine rows below are resolved (struck through,
each with the commit that fixed it); the other four are unchanged.

Method: `S" NAME" LOAD-VOCAB` in one fresh boot per entry (floppy + IDE
scratch copies), recording every signature, whether the reply ended at
the prompt, and DEPTH afterwards. 61 loads are clean, most of them
"present, skipped" because the vocabulary is embedded.

| entry | errors | ends | DEPTH | why | after the fix |
|---|---|---|---|---|---|
| DISK-SURVEY-FORM | 23 | prompt | 18 | a form data block (read by FORM-LOAD), not a vocabulary | aborts at the first token, which is better; LOAD-VOCAB could refuse non-vocabulary entries (out of scope) |
| PORT-MONITOR-FORM | 22 | prompt | 22 | same | same |
| VBR-TEMPLATE | 1 | prompt | 0 | the raw VBR payload, binary | same |
| THUMB2-ASM | ~~2~~ | ~~prompt~~ | ~~0~~ | ~~`META-COMPILER`, `T-!`: needs the metacompiler, which LOAD-VOCAB doesn't bring in~~ | ~~aborts; its real load path is test-meta's sequence (census B)~~ Resolved 2026-10-28 by ada8f56 (RESOLVE-DEPS loads every REQUIRES: name, so META-COMPILER comes in): loads clean in a fresh boot, 0 errors, DEPTH 0 (private docs/evidence/block-numbers-audit-2026-10-28/census_probe.log) |
| TARGET-X86 | ~~125~~ | ~~budget (hung)~~ | ~~?~~ | ~~same family~~ | ~~aborts at the first error instead of hanging~~ Resolved 2026-10-28 by ada8f56: loads clean, 0 errors, DEPTH 0 (test-resolve-deps R4-R6; private docs/evidence/block-numbers-audit-2026-10-28/census_probe.log) |
| TARGET-ARM64 | ~~1,256~~ | ~~closed~~ | ~~?~~ | ~~same family~~ | ~~same~~ Resolved 2026-10-28 by ada8f56: loads clean in a fresh boot, 0 errors, DEPTH 0 (private docs/evidence/block-numbers-audit-2026-10-28/census_probe.log) |
| TARGET-CORTEX-M | ~~837~~ | ~~prompt~~ | ~~587~~ | ~~same family~~ | ~~same~~ Resolved 2026-10-28 by ada8f56: loads clean in a fresh boot, 0 errors, DEPTH 0 (private docs/evidence/block-numbers-audit-2026-10-28/census_probe.log) |
| SURVEYOR-DEEP | ~~6~~ | ~~prompt~~ | ~~5~~ | ~~`CAB-EXTRACT MSI-READER ZIP-READER` and counters undefined: its dependencies don't load (consistent with Q-D3, `REQUIRES:` loading only the first name; not yet traced)~~ | ~~**a real load that works partly today and would abort**; needs its dependencies fixed first~~ Resolved 2026-10-28 by ada8f56 (CAB-EXTRACT, MSI-READER load) and private 456b260 (its REQUIRES: line names ZIP-READER): loads clean (test-resolve-deps R8-R9) |
| DICT-SYSTEM | 5 | budget (hung) | ? | uses `PLACE ?DO COUNT COMPARE`, which this kernel lacks | already broken; aborting is an improvement |

Raw per-entry results are kept with the evidence for this task (one
JSON record per entry, the logs beside it).

### Top-level `."` lines: 7 files

Each compiles dead code and prints nothing today:

| file | line | text |
|---|---|---|
| auto-detect.fth (embedded) | 225 | `." [AD-OK]" CR` |
| disasm.fth | 821 | `." DISASM loaded" CR` |
| mirror.fth | 583 | `." MIRROR vocabulary loaded" CR` |
| net-dict.fth | 226 | `." NET-DICT loaded" CR` |
| pci-bar.fth | 103 | `." PCI-BAR vocab loaded" CR` |
| rtl8139.fth | 290 | `." RTL8139 driver loaded" CR` |
| xhci.fth | 923 | `." XHCI vocab loaded" CR` |

target-arm64.fth's `."` lines are inside a colon definition, so they
are not counted.

## 2. Census B: what the test harness types (proposed as step 1, not run)

- **Why it's needed.** Tests drive the interpreter over serial, and
  some sequences pass through undefined words: test-meta's fixture
  loads, harness probes like the MIRROR-BLK one, and lines that rely on
  reading past an error.
- **Why the logs can't show it.** No test echoes its transcript into
  the make output (0 signatures in the last `make -k` log), and no
  test-meta fixture checks for the signature.
- **Method:**
  - A census kernel, as a copy outside the tree, whose `.undefined`
    also writes the word to I/O port 0xE9 (QEMU's debug console).
  - A wrapper named `qemu-system-i386` first on PATH, which adds
    `-debugcon file:<dir>/<recipe>-<pid>.log` to every QEMU the
    recipes and scripts start.
  - Run `make -k test` in a separate worktree whose combined.img is
    built from the census kernel, so build/ here is never touched.
- **Output:** for each recipe and fixture, every undefined word hit.
  That is the list of tests the fix will turn red, whether on purpose
  or not.
- **Cost:** a worktree build plus one full suite, about 1.5-2 hours of
  machine time.

## 3. Design

### D1. An undefined word aborts

**a. What it resets.** The handler prints `<word> ?`, then does what
the kernel's `ABORT` already does:
- empty the data stack and the return stack;
- STATE 0;
- TIB back to TIB_START, `>IN` 0, BLK 0, the block-loading flag 0;
- re-enter the interpreter.

The rest of the line is discarded. A block load ends, along with every
LOAD and THRU nested around it.

**Q1:** empty the data stack, as Forth-83's ABORT does, or keep it? The
recommendation is to empty it. "Aborts" means ABORT, and every test
that relies on a kept stack is an instrument fault anyway.

**b. A half definition.** Today `: UT1 ZZNOPE 5 . ;` leaves UT1 defined
and runs `5 .` live. After the fix the line is discarded, so `;` never
runs, and a hidden header is left at LATEST.

**Q2** (recommended): when the error comes while compiling, roll HERE
and LATEST back to just before that definition's header. `:` records
the point; it's a few bytes. The alternative is the whole-line rollback
the Ctrl+C path uses (`save_here`/`save_latest`). In a block load that
would also discard every word the load had already compiled, together
with vectors and hooks they installed, which would then point at freed
space. That is RELOAD-VOCAB's territory, so it's not proposed.

**c. Boot stream.** An error in the embedded stream would stop the boot
partway, leaving a system that looks booted with vocabularies missing.
Proposed:
- The handler names it: `EMBED ABORTED at <word>`. It checks the
  existing source-identity test (TIB inside the embed stream), not BLK,
  because of the pun noted in forth.asm.
- A make-test gate: every boot log in the suite carries no `<word> ?`
  signature. The full and free boots are clean today (census A), so the
  gate starts green.

**d. Loader state.** catalog-resolver's loading stack (LOADING-DEPTH,
LOADING-NAMES) stays pushed after an aborted load. The next LOAD-VOCAB
of that name is then refused as circular, RELOAD-VOCAB refuses with "a
load in progress", and after 8 aborts the stack is full. (Reasoned from
LOADING-PUSH/LOADING-POP and RL-VECTORS, not observed; U8 tests it.)

**Q3** (recommended): top-level LOAD-VOCAB, entered with BLK 0, resets
the loading stack first. The alternative is a kernel abort-hook vector
that catalog-resolver installs, which costs more bytes for a second
consumer that doesn't exist yet.

**e. Ctrl+C:** unchanged.

### D2. `(` over serial

Interactive `(` calls `read_key` until `)`, but the whole line is
already in TIB, so it blocks for input that never comes (finding
2026-10-06). The fix: scan TIB, which is NUL-terminated, for `)`, and
treat end of line as the end of the comment. That matches block mode,
which already scans its buffer.

### D3. Interpret-mode `."`

**Q4:** print it when STATE is 0, with no laydown (recommended: all
seven banners intend to print, and it's common practice), or refuse it
with a named error like `string_unterm_`, then delete the seven lines.

## 4. Red, before any change

Gates on a scratch boot, with harmless words only:

| # | case | today | after |
|---|---|---|---|
| U1 | `ZZNOPE 7 .` | prints 7 | no 7 |
| U2 | `1 2 ZZNOPE 3`, `DEPTH .` | 3 | 0 (Q1) |
| U3 | `: UT1 ZZNOPE 5 . ;`, `UT1`, then HERE and LATEST against before `:` | 5 at definition time; UT1 exists | no 5; `UT1 ?`; HERE and LATEST back (Q2) |
| U4 | staged block `ZZNOPE 6 .` / `8 .`, LOAD, then a second clean LOAD | 6 8 | no 6 8; the next LOAD works; DEPTH 0 |
| U8 | LOAD-VOCAB of a staged vocabulary with an undefined word, then LOAD-VOCAB of a clean one | continues; loader state clean today by luck | first aborts; second loads (Q3) |
| U9 | control kernel (ZZCENSUS in the stream) | `ZZCENSUS ?`, boot continues | `EMBED ABORTED at ZZCENSUS` visible |
| P1 | typed `( a comment ) 1 2 + .` | wedges, no ok | 3 |
| P2 | typed `( unterminated` then `4 .` on the next line | wedged | ok, then 4 |
| Q5 | `HERE @ . ." BANNER-TXT" HERE @ .` | silent, HERE +24 | prints BANNER-TXT, HERE unchanged (Q4 print) |
| Q6 | block-loaded `." BANNER-TXT" CR` | same | same |
| C | `: UT2 ." IN-COLON" ; UT2` | prints | prints (control) |

Gates after the change:
- the reds above;
- census A rerun: the 61 clean loads still clean, and the 9 each
  aborting at their first error;
- census B rerun;
- `make -k test`: only test-xhci red;
- kernel size against KERNEL_PADDED_SIZE (2,551 B left today);
- the boot-signature gate.

## 5. Decisions owed and order

- **Q1-Q4** above.
- **SURVEYOR-DEEP.** It works partly today and would abort after the
  fix. Trace and fix its dependency loading (Q-D3) first, inside this
  task, or accept it breaking until then.
- **The two form blocks and VBR-TEMPLATE.** Leave them: loading them by
  name was never valid.
- **Order:**
  1. census B;
  2. owner review of census B;
  3. reds;
  4. D2 (smallest, independent);
  5. D3;
  6. D1;
  7. gates and report.
- After this task: xHCI Phase 12, then NET-DATA, then Phase 3b, then
  Phase A.

## 6. Rulings (owner, 2026-10-11)

- **Q1, yes.** The abort empties the data and return stacks, through
  the same path as the kernel's ABORT.
- **Q2, yes.** Roll back only the definition in progress: HERE and
  LATEST are restored, and no half-made header is left.
- **Q3, yes.** A top-level LOAD-VOCAB resets the loading stack after an
  abort. Red U8 comes first.
- **Q4, yes.** Interpret-mode `."` prints.
- **`.(`:** confirm it exists, add it if not.
  - **Checked: it doesn't exist** (forth.asm and every forth/dict file),
    so D3 adds it.
  - It is IMMEDIATE and prints up to `)` in either state. In both
    interactive and block mode it reads from the current source,
    TIB-scanned the same way D2's `(` is.
  - New reds Q7 and Q8 below.
- **Boot stream: replaces D1c.** An undefined word in the embedded
  stream must still reach the prompt, with a loud message naming the
  word, and the boot-log gate fails the build on any.
  - Design:
    1. The handler sees the error came from the embed stream (the
       source-identity test) and prints `EMBED ABORTED at <word>: later
       embedded vocabularies not loaded`.
    2. Then it aborts to the prompt.
  - The gate is in the build, not only in make test: the image target
    boots the kernel it just built, headless, with serial to a file and
    QEMU killed by its pidfile. It fails the build on any `<word> ?`
    signature or that message. It covers the full and free kernels.
  - U9 after: the control kernel reaches `ok` and prints the message,
    and the build gate refuses the control image.
- **SURVEYOR-DEEP: let it fail loudly.** Trace the cause inside this
  task, diagnosis only. If the cause is Q-D3 (`REQUIRES:` loading only
  the first name), Q-D3 is the next task.
- **Queue, small items, not in this task:**
  - LOAD-VOCAB refuses a catalog entry that isn't a vocabulary (the
    forms, VBR-TEMPLATE) with a named error.
  - Add `REQUIRES: META-COMPILER` to the cross-compiler targets.
  - Write up DICT-SYSTEM as its own finding.
- **Census B: approved.** It runs in a separate worktree, and the main
  tree's build/combined.img stays untouched.
- **Order:**
  1. commit this plan with census A (public, scan first);
  2. census B;
  3. reds U1-U9 and P1/P2 (plus Q5-Q8), predictions written first;
  4. the code.

Added reds:

| # | case | today | after |
|---|---|---|---|
| Q7 | typed `.( HELLO-PAREN) 9 .` | `.( ?`, then the rest runs | prints HELLO-PAREN, then 9 |
| Q8 | inside a definition: `: UT3 .( AT-COMPILE) ;` | `.( ?` | AT-COMPILE printed while compiling; UT3 prints nothing when run |

## 7. Rulings, second round (owner, 2026-10-11)

1. **`'` on an unknown name aborts, like the interpreter.** All four
   not-found sites go through one abort routine: INTERPRET's
   `.undefined`, `'` (TICK), SEE, and USING. Today `'` prints only
   ` ? `, pushes nothing, and carries on, so whatever follows consumes a
   cell that isn't there (census-B control). `ALSO <unknown>` reaches
   INTERPRET's site, because ALSO doesn't parse a name.
2. **Search order after an abort:**
   - At the prompt, leave it alone: a typo must not wipe the user's
     search order.
   - Inside a load, restore CURRENT and the search order saved when the
     top-level load began. LOAD-VOCAB at top level saves them, beside
     the loading-stack reset (Q3). The abort routine restores them when
     a load was in progress.
3. **An aborted load rolls back the failing vocabulary** to the HERE and
   LATEST it had before that load began.
   - The safety checks are RELOAD-VOCAB's vector checks (RL-VECTORS:
     the block vectors, IRQ hooks, the IDT, the catalog registry and the
     named vocabulary variables).
   - If a vector points into the region, keep it and print `<NAME>
     partial: <what> points into it`.
   - A corrected retry must then really load (no "present, skipped").
   - Which vocabulary: the top-level one. Its dependencies that
     finished loading before the failure stay; nested loads are rolled
     back with it, because the region runs from the top-level load's
     start.
4. **DICT-SYSTEM** moved to docs/design/ with its finding (public
   0285bc2, not yet pushed; it goes out after the next full make test,
   since the catalog layout changes).
5. **SURVEYOR-DEEP:** ZIP-READER's missing `REQUIRES:` line goes with
   the Q-D3 task, after the confirming run.
6. **Order unchanged:** census B, then the red run, then the code.

Red changes (test_interp_abort.py; predictions re-frozen in a new file):

| # | case | today | after |
|---|---|---|---|
| U8d | host patches IA-BAD's block to remove ZZNOPE, EMPTY-BUFFERS, `S" IA-BAD" LOAD-VOCAB`, `IA-BAD IAB-AFTER .` | "IA-BAD present, skipped"; IAB-AFTER already 1 from the first load | the retry really loads; IAB-AFTER 1 |
| U8e | ORDER (and CURRENT) after the aborted load equal ORDER before it | the load's preamble leaves CURRENT = IA-BAD | equal |
| U8f | IA-VEC (`: IAV-W 2DROP 1 ; ' IAV-W BLK-WRITER!`, then ZZNOPE) | loads past the error | aborts, is kept, prints `IA-VEC partial: BLK-WRITER@ vector points into it`; IA-VEC still found |
| U10 | `' ZZNOPE 7 .` | ` ? ` then 7 | `ZZNOPE ?`, no 7 |
| U11 | `USING ZZVOC 7 .` | `ZZVOC ?` then 7 | no 7 |
| U12 | `SEE ZZSEE 7 .` | ` ? ` then 7 | no 7 |
| U13 | `ALSO HARDWARE`, then `ZZNOPE` at the prompt, then ORDER | HARDWARE kept | HARDWARE kept (a typo at the prompt keeps the search order) |

## 8. The rollback point (owner, third round, 2026-10-11)

**The point:** HERE and LATEST at the start of the failing vocabulary's
own block load, after its `REQUIRES:` dependencies have finished.

- **Where it is in the code.** LOAD-VOCAB-INNER (catalog-resolver.fth)
  runs `'RESOLVE-DEPS @ EXECUTE` (each dependency is a complete nested
  load) and then `THRU` over the vocabulary's own blocks. The point is
  HERE and LATEST immediately before that `THRU`.
- **One point per loading level.** Each point is recorded beside its
  name on the loading stack. A level still resolving its dependencies
  has not recorded one yet.
- **Dependencies stay.** They finished loading below the point.
- **Anything loaded inside the region rolls back with it,** for example
  a LOAD-VOCAB issued from the middle of the file. Its region lies above
  the point. The message names each vocabulary rolled back.
- **The open case, my reading.** The error may sit inside a vocabulary
  that another file loaded mid-file. Then both block loads are in
  progress at the abort, so the outer one fails too. The point used is
  the outermost in-progress block-load start, and both are named. This
  needs confirming.
- **Vector check:** RL-VECTORS over the region. A vector into it keeps
  the region and prints `<NAME> partial: <what> points into it`
  (accepted).

New red case:

| # | case | today | after |
|---|---|---|---|
| U8g | IA-BAD carries `\ REQUIRES: IA-GOOD`; IA-BAD fails; then `ALSO IA-GOOD IAG . PREVIOUS` | 42 (no abort today) | 42: the dependency finished below the point and survives the rollback |

## 9. Nested failure (owner, fourth round, 2026-10-11)

- **Confirmed:** an abort ends the whole top-level load. Every
  unfinished block load rolls back to the outermost unfinished point,
  and each one is named.
- **A dependency that fails before the outer `THRU` starts.** The outer
  vocabulary has recorded no point yet, so the dependency rolls back to
  its own point. The message says the outer vocabulary was not loaded
  because of it: `<OUTER> not loaded: <DEP> failed`.

| # | case | today | after |
|---|---|---|---|
| U8h | IA-OUTER (`\ REQUIRES: IA-DEPFAIL`, then `1 CONSTANT IAO`); IA-DEPFAIL fails at ZZNOPE. `S" IA-OUTER" LOAD-VOCAB`, then `ALSO IA-DEPFAIL PREVIOUS`, `ALSO IA-OUTER PREVIOUS` | both load past the error | `IA-OUTER not loaded: IA-DEPFAIL failed`; neither vocabulary exists afterwards (`IA-DEPFAIL ?`, `IA-OUTER ?`) |

## 10. Census B results and rulings (2026-10-11)

**Census B** (`make -k test` in a worktree, census kernel plus debug-console wrapper): 64 QEMU
launches, one with undefined-word hits, test_block_reload (its ZZZNEVERWAS control, R5's 40-char
token = 2 signatures, R6's ZZZENDBYTE). Rulings, fifth round:

1. test-log-validation boots QEMU, so it is censused too (its ignored files copied into the
   worktree). test-translator, test-pipeline and test-doc-drift don't boot Forth.
2. test_block_reload R5 is a planned red, recorded before any code: after the fix the 40-char token
   gives exactly one signature (the 31-char truncation), because the abort discards the rest of the
   block; R5's pin changes in the same commit. R6 and the control are unchanged.
3. After the test-meta census the code starts without a stop, unless the census finds an undefined
   word outside test_block_reload; then stop and report.
4. Queue after this task: UEFI-3 (multiboot2 entry) and UEFI-4 (framebuffer console), plan first,
   ahead of xHCI Phase 12.

**Census B complete** (2026-10-11): make test 64 QEMU launches, test-meta 9, test-log-validation 3.
Hits: test_block_reload (control, R5, R6: planned), test_meta_b6 and test_meta_b6b `NOTAWORD`
(deliberate: each checks the `?` message, alone on its line; unchanged by the fix), and
test_meta_b6b `T-HERE` (a report-only line, `HEX T-HERE @ T-IMAGE - .`, typed with X86-ASM not in
the search order: today it underflows the stack with `@`; after the fix the line is discarded; the
line should name X86-ASM's T-HERE). No vocabulary load in any suite passes through an undefined
word. Stopped for the owner (ruling 3: hits outside test_block_reload).

## 11. As built, and the sixth round of rulings (2026-10-11)

**Design change from §3: the abort calls a hook.** A rolled-back load
has to be undone at abort time: the dictionary and search order must be
clean before the next prompt, and the names printed then. So the kernel
calls `ABORT-HOOK` after its reset, and catalog-resolver installs
`CR-ABORT` there. This is the alternative Q3 named; the later rulings
require it.

**Rulings, sixth round:**
1. **The hook can't recurse.** The kernel marks the hook busy
   (`VAR_ABORT_BUSY`) before calling it. An abort inside the hook skips
   it, prints `ABORT-HOOK failed: an aborted load was not rolled back`,
   and clears the mark, so the next abort runs the hook again.
   - ABORT-HOOK is one of RELOAD-VOCAB's vector checks (RL-VECTORS).
   - Red U14: a hook that LOADs a block holding an undefined word.
     Before the guard it looped forever (`ZZHOOK ?` repeated, no
     prompt; red 31/34 as predicted). After: one `ZZHOOK ?`, the
     message, `ok`, DEPTH 0, and the next abort runs a marker hook
     (34/34).
2. **U8a is tightened** to require `IA-BAD ?`: after the rollback the
   vocabulary word itself is gone.
3. **The embed stripper collapses spaces inside strings** (finding
   2026-10-11). Messages in embedded code use an explicit `SPACE`
   meanwhile.
4. **Commit** when make -k shows only test-xhci red and test-meta
   passes.

**Built:**
- **Kernel:** `abort_undefined` (all four sites); the hook call with its
  busy guard; definition rollback (`:` saves and `;` clears
  `VAR_DEF_*`); interpret-mode `."` and the new `.(`, through
  `print_parsed`; `(` scanning TIB; `ABORT-HOOK` (DEFVAR, 0x280A4).
- **catalog-resolver:**
  - rollback points per level (AB-PTH, AB-PTL), recorded just before
    `THRU`;
  - `LOAD-VOCAB` resets the loading stack only at BLK 0, and saves the
    order at depth 0;
  - `CR-ABORT`: the outermost started point, the RL-VECTORS check
    (`partial`), AB-FREE (walks FORTH's and each vocabulary's LATEST
    cell back below the point), `<OUTER> not loaded: <DEP> failed`, each
    rolled-back level named, the order restored.
- **tools/boot_gate.py** runs in the bmforth.img and bmforth-free.img
  rules. A boot-stream signature, `EMBED ABORTED`, or no `ok` fails the
  build, and the image is removed. It is red on the control kernel and
  green on both real kernels.
- **`make test-interp-abort`** (port +68) is in `make test`.

**Kernel content:** 114,176 B of 114,688, so **512 B left** (was 2,551).
- +1,419 B of catalog-resolver stream (hook, points, order save);
- +36 B for the `SPACE`s;
- the rest is kernel code, including the guard.

The owner's order puts the kernel-pad move (demo apps to blocks) next,
before UEFI-3/4.
