# UBT Sanitizer Demo — Approved Copy (i8042prt.sys)

This is the canonical wording for any surface that presents the demo
(landing page, social posts, whitepaper §4.4). Counts come from the
committed transcript (`docs/demo-i8042-transcript.txt`); if the
analyzer changes, re-run `demo_i8042.sh` and update the numbers here
from the new transcript — never quote counts the artifact doesn't
show. The demo is byte-reproducible: independent runs produce
identical transcripts (verified 2026-07-07), so a diff against the
committed transcript is itself a drift check.

## What's public, what's paid (state the line, don't blur it)

The transcript is a real captured run, published unmodified. Be
explicit about which parts a reader can verify and which part is the
product:

- **Public and checkable:** the input is the open-source ReactOS
  build of `i8042prt.sys` (SHA-256 in the transcript) — anyone can
  disassemble it and check every classification claim, function by
  function, reason by reason. The transcript itself, including the
  full strip list, is committed here as-is.
- **Paid:** the UBT translator that produced the strip, and the demo
  harness (`demo_i8042.sh`, `demo_i8042_qemu.py`) that regenerates
  the transcript, are part of the commercial tier.

Do not publish wording that implies a public reader can re-run the
pipeline themselves. What they *can* do — and what the copy should
say — is check every claim the transcript makes against the open
input binary. The reproduction machinery is the product; the claims
are checkable without it.

## The pitch (use this wording)

> A real Windows-ABI kernel-mode driver — 50 functions calling into
> hal.dll and ntoskrnl.exe — reduced to 9 callable hardware Forth
> words. 33 functions of OS scaffolding dropped, each with a stated,
> checkable reason (IRP dispatch, PnP, power, sync, debug plumbing).
> 8 functions the analyzer could not prove either way — so it says so,
> and keeps them out. Then it boots on bare metal and reads the
> keyboard controller port.

Three-bucket honesty is the feature: `9 kept + 33 scaffolding +
8 unclassified = 50`. Both output formats render the same counts, and
a committed test fails if they ever drift.

## Provenance is the pitch (not a caveat)

This is the **ReactOS build** of the PS/2 keyboard driver:
open-source, real Windows kernel ABI, and fully inspectable. That's
the point — you can check every claim we make about what we did to
it. Checkable provenance beats a signed binary nobody can open.

The adversarial check is the demo's strongest moment — state it
specifically, not generically:

> The analyzer looked at `func_11B19` — the driver's dispatch and
> initialization hub — and named everything it saw: IRP dispatch,
> PnP, memory management, synchronization, debug logging
> (`IRP+PNP+MEMORY+SYNC+DIAGNOSTIC`). Five documented reasons, each
> one checkable against the disassembly. It judged the function OS
> scaffolding, dropped it, and the live session proves the drop is
> real: `FUNC_11B19` is absent from `WORDS` and fails at the
> interpreter. Not commented out — *not there*.

That is a substantive, multi-part, checkable judgment about a
significant function, with the truth told about both the judgment
and the removal. Lead with it.

## Safety framing (required wording discipline)

The demo makes a driver's direct hardware access callable and
unmediated. Do **not** sell that as *safe* — sell it as *powerful and
legible*:

> You can see exactly what hardware this touches, because every kept
> function is shown with what it does — and everything we removed is
> listed with the reason it was removed.

Legibility IS the safety story. Never claim unmediated hardware
access is risk-free.

## Do not say

- **"signed"** — the corpus binary is the unsigned ReactOS build.
  (The signed-retail variant is banked with translator endpoint #2.)
- **"manifest"** — nothing in this demo parses or strips a manifest.
- **"9/41"** — stale. The honest split of the 41 non-hardware
  functions is 33 confident drops + 8 unclassified.
- **".NET" / "CLR"** — the CIL path exists but is not wired into this
  pipeline; this demo is native x86 only.

## Filed note (do not fix here): aspirational architecture words

`docs/ARCHITECTURE-TRANSLATOR.md` names `LOAD-PE`, `DECOMPILE-CLR`,
`STRIP-MANIFEST`, `STRIP-SIGNATURE`, and `UIR>NATIVE-DLL` as if they
exist. They are aspirational and unimplemented. Demo copy must not
borrow those words. A doc-truth pass on the architecture doc is a
separate, later task — filed here per TASK_UBT_SANITIZER_BUILD.md
line item 3.
