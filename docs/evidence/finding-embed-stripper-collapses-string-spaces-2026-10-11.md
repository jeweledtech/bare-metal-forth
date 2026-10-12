# FINDING: the embed stripper collapses runs of spaces inside string literals (2026-10-11)

Owner ruling 2026-10-11: write this up as a finding. The fix comes
later: the stripper should leave string contents alone.

## What happens

tools/embed-vocabs.py builds the boot token stream. It joins every
embedded vocabulary's lines and then, at line 137, runs

```
combined = re.sub(r'  +', ' ', combined).strip()
```

on the whole stream. Every run of spaces becomes one space, including
runs inside `."`, `S"` and `ABORT"` strings.

That costs a string one or more spaces in two ways:
- **Interior runs shrink.** `." B  D  F  Vend:Dev  Cl"` arrives as
  `." B D F Vend:Dev Cl"`.
- **Leading spaces disappear.** `."` and `S"` skip exactly one space
  after the word. A string written `."  partial"` (two spaces, meaning
  one leading space) arrives as `." partial"`, and the parser takes that
  one space as the delimiter. The text then prints as `partial`, glued
  to whatever came before.

The comment pass above line 137 already has a string state machine (it
keeps `(` and `\` verbatim inside strings). The collapse at line 137
does not use it.

## Seen

During the interpreter-correctness change (2026-10-11), catalog-resolver's
new abort messages, written `."  partial: "` and `."  failed"`, printed
as `IA-VECpartial:` and `IA-DEPFAILfailed`. The run was green-1 of
tests/test_interp_abort.py, U8f and U8h. The same text, block-loaded
rather than embedded, keeps its space. The messages now use an explicit
`SPACE`, as catalog-resolver's older code already did (`TYPE SPACE ."
present, skipped"`).

## Reach today

32 string literals in the embedded vocabularies (EMBED_VOCABS, full
build) have a leading space or a run of spaces. Counted 2026-10-11 by
scanning `."`/`S"`/`ABORT"` literals in each embedded file. Examples:

- `pci-enum.fth:245` `." B  D  F  Vend:Dev  Cl"`: PCI-LIST's column
  header.
- `ahci.fth:286-305`: register dumps `."  CT="`, `."  SEC="`,
  `."  TFD="` and others print glued to the value before them.
- `ahci.fth:339`, `392`, `472`: `." MBR:  "`, `." GPT:  "`,
  `." MFT offset:  "`.
- `notepad.fth:84`, `87`: menu labels padded to a width
  (`." Cut    "`, `." Copy   "`). The padding is lost, so the menu's
  columns shift.
- port-mapper, echoport, rtl8168, ntfs, fat32, gui-harvest: leading-space
  separators.

Only the embedded stream is affected. The same files loaded from blocks
keep their strings, so a vocabulary prints differently embedded and
block-loaded.

## Not done here

No fix, by ruling. The fix is for the collapse to skip string contents,
as the comment pass already does. That changes the boot stream's bytes,
so the kernel pad and the embedded-stream size have to be re-measured.
