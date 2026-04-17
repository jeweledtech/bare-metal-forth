# ForthOS — Bare-Metal Forth-83 OS

A complete Forth-83 operating system that boots directly on x86 hardware. No Linux. No Windows. No HAL. Direct from BIOS to a live Forth interpreter in 66KB.

---

## If You Just Want the Forth

That's the right instinct. Here's all it takes:

**3 files:**
```
src/boot/boot.asm      — 512-byte bootloader (real → protected mode, A20, GDT)
src/kernel/forth.asm   — the entire Forth-83 kernel
Makefile               — nasm + cat, essentially
```

**2 commands:**
```bash
make        # assembles and combines
make run    # boots in QEMU
```

**1 tool dependency:** [NASM](https://www.nasm.us/) — a single-binary assembler, available on every platform.

```bash
# Ubuntu/Debian
sudo apt-get install nasm qemu-system-x86

# macOS
brew install nasm qemu

# Arch
sudo pacman -S nasm qemu
```

Output is a 66KB bootable image. Boot it in QEMU or `dd` it to a USB stick and boot on real hardware.

---

## What You Get

178-word dictionary. Direct Threaded Code interpreter (ESI = IP, EBP = return stack). Full Forth-83 semantics including floored division.

**Kernel words (built into the binary):**
- Stack: `DROP DUP SWAP OVER ROT ?DUP 2DUP 2DROP PICK ROLL DEPTH`
- Arithmetic: `+ - * / MOD /MOD NEGATE ABS MIN MAX 1+ 1-`
- Floored division: `-7 3 /` → `-3` (correct Forth-83 behavior, not symmetric)
- Comparison: `= <> < > <= >= 0= 0< U<`
- Logic: `AND OR XOR INVERT`
- Memory: `@ ! C@ C! +! FILL MOVE CMOVE`
- Return stack: `>R R> R@`
- I/O: `KEY EMIT CR SPACE TYPE`
- Compiler: `: ; IMMEDIATE [ ] LITERAL ' EXECUTE`
- Control: `IF ELSE THEN BEGIN UNTIL WHILE REPEAT DO LOOP +LOOP I J LEAVE`
- Defining: `VARIABLE CONSTANT CREATE DOES> ALLOT ,`
- Strings: `." S" COUNT`
- Utility: `WORDS SEE . .S HEX DECIMAL DUMP`
- Block storage: `BLOCK BUFFER UPDATE SAVE-BUFFERS FLUSH LOAD THRU LIST`
- Vocabulary: `VOCABULARY ALSO PREVIOUS ONLY DEFINITIONS USING`
- Port I/O: `INB INW INL OUTB OUTW OUTL` (direct hardware, no HAL)
- Disassembler: `DIS DECOMP` (in-system x86 disassembler)

Everything else in the repo — the translator, the Python block packer, the test suites — is cross-development tooling that runs on your host machine. The target never sees any of it. Ignore it if you want. Take the three files and go.

---

## Try It

```forth
2 3 + .             \ 5
: SQUARE DUP * ;
7 SQUARE .          \ 49
-7 3 / .            \ -3  (floored, correct Forth-83)
HEX FF00 .          \ FF00
100 0 DO I . LOOP   \ 0 1 2 3 ... 99
```

Direct hardware access (on real iron, not QEMU):
```forth
HEX
3F8 INB .           \ read COM1 line status register
41 3F8 OUTB         \ write 'A' to COM1
```

---

## What Makes This Different

Most Forth implementations today run on top of Linux, Windows, or some OS. They inherit the HAL problem — the OS mediates every hardware access. If you want to talk to a serial port or a NIC directly, the OS gets in the way.

This doesn't do that. It talks to hardware the way Forth always did: `INB`, `OUTB`, direct memory writes, direct interrupt vectors. If you know the port address, you own the device.

The vocabulary system works the same way it always did:
```forth
USING RTL8168        \ load NIC driver
USING AHCI           \ load disk driver
USING NTFS           \ load filesystem
```

Each vocabulary is a Forth source file loaded from block storage. Load what you need. Nothing more arrives unless you ask for it.

---

## Self-Hosting

The metacompiler is complete. ForthOS can now rebuild itself from its own source, running inside the live system. No NASM required on the target. The full self-hosting loop:

1. Boot the kernel (NASM-assembled, 66KB)
2. Load the metacompiler vocabulary (`USING META`)
3. Point it at the kernel source blocks
4. The running system assembles and writes a new bootable image

Editor, assembler, block filesystem, compiler — all inside. This is the traditional Forth way. We're there.

---

## The Bigger Project

Beyond the kernel, there's a Universal Binary Translator (UBT) pipeline. It takes Windows driver binaries (`.sys` files, PE32/PE32+), extracts the hardware protocol — the actual port reads and writes — and emits them as Forth vocabulary source files.

Result: you can run `USING I8042PRT` and the keyboard controller behavior extracted from the real Windows driver becomes a loadable Forth vocabulary. Tested against 18 real-world binaries: serial, storport, usbxhci, HDAudBus, pci, i8042, and more.

This is the `chat_gpt_produced.docx` vision made real. Map the DLL, strip the security theater, call it like a regular code module.

---

## Repository Layout

```
bare-metal-forth/           ← public repo (this one)
├── src/
│   ├── boot/boot.asm       — 512-byte bootloader
│   └── kernel/forth.asm    — 178-word Forth-83 kernel
├── forth/dict/             — loadable vocabulary source files
│   ├── hardware.fth        — IRQ, DPC, timing primitives
│   ├── disasm.fth          — in-system x86 disassembler
│   ├── ps2-mouse.fth       — PS/2 mouse driver
│   └── ...
├── Makefile
└── docs/
```

The paid vocabulary tier (AHCI, NTFS, RTL8168, NIC drivers, UBT pipeline, metacompiler) lives in a separate private repo. The kernel and the free vocabularies are all you need to get running.

---

## Current Status

- **Kernel**: 178 words, 66KB bootable image, boots on real x86 hardware (HP 15-bs0xx validated)
- **Tests**: 151/151 kernel unit tests, 145/145 translator tests, 8/8 end-to-end pipeline tests
- **Self-hosting**: metacompiler complete (Phases B3–B6b), kernel rebuilds itself from blocks
- **UBT pipeline**: 258 tests / 22 suites, 18 real-world Windows binaries validated
- **Network console**: UDP port 6666, 100% reliable on real hardware
- **Block storage**: 1KB blocks, ATA PIO + AHCI, GPT + NTFS + FAT32 support

---

## Who This Is For

- People who've written Forth before and miss having direct hardware access
- Embedded / firmware engineers who want a real-time Forth without an OS layer
- x86 bootloader developers who want a working base to extend
- Anyone who remembers when you could poke a memory address and it *worked*

If you've never touched a Forth before, the [Starting Forth](https://www.forth.com/starting-forth/) resource is the classic intro. Come back when you're comfortable with the stack.

---

## Contributing

Every vocabulary has a test suite. Regressions block commits.

If you want to discuss the project, find us in the Forth Facebook groups or open an issue.

---

## License

MIT License. Build it. Modify it. Boot it on real hardware. See [LICENSE](LICENSE).

*"The best way to predict the future is to implement it in Forth."*
