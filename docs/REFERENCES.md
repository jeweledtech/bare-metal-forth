# Reference Systems: Andy Valencia's ForthOS

Analysis of Andy Valencia's ForthOS (sources.vsta.org/forthos/) as it relates to
our Bare-Metal Forth project. ForthOS is a complete standalone Forth OS for x86
that has been in real daily use — not just a demo.

## Source

- Homepage: https://sources.vsta.org/forthos/
- Distribution: https://sources.vsta.org/forthos/dist/last/
- Metacompiler docs: http://sources.vsta.org/forthos/metacompile.html
- License: Public domain

## Architecture Comparison

| Feature | ForthOS (Valencia) | Bare-Metal Forth (Ours) |
|---------|--------------------|------------------------|
| Target | Intel 80386+ | Intel 80386+ (x86-32) |
| Boot | GRUB / Multiboot | Custom 512-byte bootloader |
| Threading | Subroutine threaded (STC) | Direct threaded (DTC) |
| Block size | 4KB (2KB source + 2KB shadow + 96B metadata) | 1KB (standard Forth-83) |
| Vocabulary | eForth-based, VOCAB.WORD notation | Forth-83 search order (ANS-style) |
| Metacompiler | Yes (two-pass bootstrap) | Not yet (planned) |
| Multitasking | Yes (cooperative) | Not yet |
| Editor | Vi-like full-screen | Not yet |
| Debugger | Yes (integrated) | Not yet |
| Assembler | x86 assembler in Forth | Not yet |

## Key Design Decisions: What We Adopted

### Block Storage Pattern
Valencia's ForthOS uses a block-based filesystem as the primary storage mechanism.
We adopted the same fundamental approach: numbered blocks on disk, buffer cache
with dirty tracking, and `LOAD` for source interpretation. Our implementation uses
standard 1KB blocks (Forth-83 convention) rather than ForthOS's 4KB blocks with
shadow comments.

### ATA PIO for Disk Access
Both systems use ATA PIO (Programmed I/O) for disk access — the simplest possible
disk interface with no DMA or interrupt complexity. This aligns with the "ship
builder's mindset" of radical simplicity.

### Self-Contained System
ForthOS proves the viability of a fully standalone Forth system with no underlying
OS layer. This validates our project's core premise.

## Key Design Decisions: What We Chose Differently

### Custom Bootloader vs GRUB
ForthOS uses GRUB (Multiboot-compliant). We use a custom 512-byte bootloader that
loads the kernel directly via BIOS INT 13h. Our approach gives us complete control
over the boot process with zero external dependencies — important for the space
systems use case where every byte must be auditable.

### DTC vs STC
ForthOS likely uses Subroutine Threaded Code. We use Direct Threaded Code (DTC)
with the classic `NEXT` macro: `lodsd; jmp [eax]`. DTC is slightly slower than
STC but makes decompilation (SEE) straightforward since every cell in a colon
definition is a recognizable XT pointer.

### Standard 1KB Blocks vs 4KB with Shadows
ForthOS uses 4KB blocks: 2KB source, 2KB shadow documentation, plus 96 bytes of
filesystem metadata. We use standard 1KB blocks for simplicity and Forth-83
compatibility. Shadow blocks could be added later as block N+1 for source block N.

### ANS Search Order vs Custom Vocabularies
ForthOS uses eForth-style vocabularies with a `VOCAB.WORD` naming convention. We
implemented the ANS Forth Search Order wordset (ALSO/PREVIOUS/ONLY/FORTH/ORDER)
plus a friendly `USING` word. This is more standard and allows the `USING GRAPHICS`
pattern from the project requirements.

## ForthOS Metacompiler — Our Phase 4 Goal

ForthOS's metacompiler is a two-pass bootstrap system:
1. **Pass 1**: Build a minimal core (inner interpreter, console I/O, disk access)
   that can run standalone
2. **Pass 2**: Boot the Pass 1 system and load the rest of the OS as normal Forth
   source from blocks

This is the approach we should follow for our metacompiler:
- The current kernel (assembly-language primitives) serves as our "Pass 1"
- Block loading (`LOAD`, `THRU`) now provides the mechanism for "Pass 2"
- The vocabulary system enables clean separation of metacompiler words from the
  target system's words

Key constraint from Valencia's docs: "Coding for [the metacompiler]—and debugging
your mistakes—takes a degree of skill and attention to detail much more demanding
than coding normal Forth words." The vocabulary system is critical here — the
metacompiler needs separate vocabularies for host-side and target-side words.

## ForthOS Features Worth Studying

### Local Variables
ForthOS implements local variables with stack format enforcement. This is useful
for complex words where stack juggling becomes unwieldy. Could be implemented as
a vocabulary of words that compile stack-frame management code.

### Vi-like Editor
A full-screen block editor using VGA direct memory access. We already have VGA
text mode output — extending this to a screen editor is straightforward once
block storage is working.

### Integrated Debugger
Single-stepping through threaded code by intercepting NEXT. With DTC this means
temporarily replacing the `lodsd; jmp [eax]` sequence with a call to the debugger.

### x86 Assembler in Forth
Allows defining CODE words entirely from Forth. Combined with the metacompiler,
this enables the system to rebuild itself without external tools.

## Lessons for Our Roadmap

1. **Block storage first** (done) — without disk I/O nothing else can persist
2. **Vocabulary system** (done) — needed for metacompiler and modular dictionaries
3. **Block editor** (next) — Vi-like editor for direct block editing
4. **Metacompiler** — two-pass approach, vocabulary-isolated
5. **Self-hosting** — the system can rebuild itself from source blocks
