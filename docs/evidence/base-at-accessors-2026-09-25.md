# BASE where (bt)'s accessors compile (2026-09-25, a measurement, no code)

**The question (owner):** `: HDAUDBUS-R58+14-W@ ( base -- x ) 14 + W@ ;`
means 0x14 only if BASE is 16 when the line compiles. In DECIMAL, `14`
is 0x0E, which is STATESTS/WAKESTS. No pinned-text test can see this.

**From the emitted files** (the 10 drivers (bt) moved, build
`cfa43f46783de0ec`):
- `emit_vocabulary_preamble` writes `HEX` **unconditionally**, after
  `DEFINITIONS` and any `ALSO`. The only other base word the emitter
  writes is the footer's `DECIMAL` (`forth_codegen.c`).
- In each of the 5 files with accessors there is **exactly one `HEX`
  before the first accessor**, and the only `DECIMAL` comes after the last
  one.
- Every non-comment line between them lies inside a colon definition, so
  it compiles and does not execute. Nothing in the file changes BASE
  before an accessor compiles.

**From the load path** (`src/kernel/forth.asm`):
- The kernel writes BASE only in `HEX` (`:2765`), in `DECIMAL` (`:2770`),
  at boot (10, `:324`), and through a user's `BASE !`.
- **The undefined-word path (`.undefined`, `:1529`) resets STATE only and
  leaves BASE alone**, so an error earlier in the load cannot switch BASE
  back to 10.
- The 09-10 route (`xhci-iron-2026-09-10.log`): the owner types `DECIMAL
  <first> <last> THRU` to block-load a catalog range, and the file's own
  `HEX` then executes in order.

**Verdict:** BASE **is** 16 where the accessors compile, **provided the
load includes the file's preamble**. A whole-file catalog load always does.
**No letter is minted.**
- **The hazard is named, not taken.** A partial `THRU` that starts past
  the `HEX` line compiles the accessors in whatever BASE the caller set,
  and the 09-10 route sets DECIMAL first.

**Base-sensitive accessors:** of the **26** corpus accessors, **3** have
an offset whose decimal and hex readings differ. All three are
`HDAUDBUS-R58+14-W@` (HP, Newer ASUS, Older ASUS), where `14` reads as
0x14 in hex and 0x0E in decimal. Every other offset (0, 2, 3, 4, 6, 8)
reads the same in both bases.

**Name length:** `word_` copies at most **31** characters
(`cmp ecx, 31`) and silently splits a longer token. `F_LENMASK` is 0x3F,
and `word_buffer` is 32 bytes.
- The longest corpus accessor name is `HDAUDBUS-R58+14-W@`, at **18**.
- **Named, not taken:** the emitter does not check name length. A long
  vocabulary name (the existing `IALPSS2I-I2C-BXT-P` is 18) plus
  `-R<park>+<off>-W@` could pass 31.

**The iron card's last pair tests this on the HP.** `B1228014 W@` reads
0x14 directly, and the emitted `HDAUDBUS-R58+14-W@` must return the same
value.
