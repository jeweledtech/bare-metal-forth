# ForthOS

No Linux. No Windows. No HAL. No story. Just the machine.

ForthOS is a bare-metal Forth-83 operating system written from BIOS entry
in x86 NASM and Forth. It boots in under a second on a USB stick, talks
to your hardware directly, and gives you a REPL on the bare metal of
a real computer — the way programmers worked before vendors decided
you weren't allowed to anymore.

This repo contains the kernel and the free vocabulary set. Paid
vocabulary packs (hardware drivers, binary translation tools, the
metacompiler) live in a separate repository and are available at
[shop.jollygeniusinc.com](https://shop.jollygeniusinc.com).

## What you get for free

The kernel and the public vocabularies build into two images:

- **`bmforth.img`** — full developer build (requires paid vocabs on disk)
- **`bmforth-free.img`** — free-tier build, kernel plus 16 public vocabularies

The free image gives you:

- A Forth-83 REPL on bare metal, ~115 KB total
- **PORT-MAPPER**: enumerate and probe I/O ports live
- **ECHOPORT**: trace port activity during code execution
- **PCI-ENUM**: walk the PCI bus, identify devices
- **PS2-KEYBOARD**: keyboard input on real hardware
- **GUI substrate**: form engine with widgets, focus, dispatch (`HELLO-APP` runs)
- **NOTEPAD**: text editor with buffer + cursor + dispatch, runs in RAM

What the free tier does *not* include: disk I/O, networking, audio,
video, the metacompiler, the binary translation toolchain. Those are
paid packs because that's where the months of driver work live.

## What the paid tier adds

| Pack | Adds capability |
|------|-----------------|
| Disk Stack | AHCI (real SATA), NTFS read, FAT32 read — open files from your Windows partition without Windows |
| Gigabit Ethernet | RTL8168 driver, network console |
| Input Devices | Full i8042prt + PS/2 mouse |
| UBT Pipeline | Universal Binary Translation: extract a Windows `.sys` driver, decompile it, re-emit as Forth |
| HP Win11 Driver Library | 18+ pre-translated drivers from a real laptop disk |

Subscription tiers bundle these plus the metacompiler (build ForthOS
for ARM64, RISC-V, Cortex-M33) and ARM/RISC-V/embedded targets.

## Building

You need NASM, GNU Make, Python 3, and QEMU (for testing).

```bash
git clone https://github.com/jeweledtech/bare-metal-forth.git
cd bare-metal-forth
make free          # builds bmforth-free.img from public sources alone
make run-free      # boots it in QEMU
```

If you also have the paid vocabulary repo checked out as
`../forthos-vocabularies/`, `make` builds the full image with all
drivers integrated.

## What ForthOS isn't

It isn't a hobby project. It isn't a teaching kernel. It isn't a
toy. It's the operating system that the open-vendor world should
have had — direct hardware access, live recompilation against running
code, no protected-mode coffin around the programmer.

It also isn't going to replace your daily driver. Today it boots,
reads disks, runs a GUI demo, and disassembles itself live. Audio
playback, video, USB, modern filesystems — those are roadmap items.
What's here works on real metal: validated against an HP 15-bs0xx
laptop, boots from USB, reads the NTFS partition that Windows wrote.

## Project lineage

ForthOS descends from Laboratory Microsystems Inc. (LMI) Forth-83,
the same toolchain NASA JPL used. Architectural mentorship comes
from Padma Gonpo Rinpoche, who worked on UR-FORTH. The guiding
principle is the five-plane model of digital systems (physical map,
timing, address, data, code) and "simplicity is king."

## Status

| Metric | Value |
|--------|-------|
| Kernel size | 115,200 bytes (boot + kernel) |
| Dictionary words | 222 |
| Embedded vocabularies (full build) | 25 |
| Embedded vocabularies (free build) | 16 |
| Forth OS test checks | 200+ across 14 scripts |
| UBT translator tests | 270 across 22 suites |

All numbers traceable to commit hashes in repo history.

## More

- [Architecture](docs/ARCHITECTURE.md) — kernel layout, vocabulary system
- [Hybrid validation report](docs/REPORT_HYBRID_HP_VALIDATION.md) —
  UBT + LLM cross-validation against real Windows drivers
- [Open-core boundary](docs/open-core-audit-2026-05-16.md) — what's
  free, what's paid, why
- [Buy paid packs](https://shop.jollygeniusinc.com)

---

ForthOS is built by [Brenden Brown](https://github.com/jeweledtech)
at JeweledTech / Jolly Genius Inc. Licensed MIT for the kernel and
free vocabularies. Paid vocabulary packs are licensed separately.
