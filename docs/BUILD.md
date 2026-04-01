# Building Bare-Metal Forth

## Requirements

- **NASM** (Netwide Assembler) 2.14+
- **QEMU** x86 system emulator (for testing)
- **Python 3** (for block tools and test harness)
- **GCC** and **Make** (for the binary translator)

```bash
# Ubuntu/Debian
sudo apt install nasm qemu-system-x86 make python3 gcc

# Arch Linux
sudo pacman -S nasm qemu python gcc make

# macOS
brew install nasm qemu python gcc
```

## Build

```bash
make                    # builds build/bmforth.img in <1 second
```

Output:
- `build/boot.bin` — bootloader (512 bytes)
- `build/embedded.bin` — compiled vocabularies (~18KB)
- `build/kernel.bin` — Forth kernel (64KB, includes embedded vocabs)
- `build/bmforth.img` — combined bootable image (~66KB)

## Run

```bash
make run                # QEMU text mode (serial console)
make run-gui            # QEMU with VGA window
make run-serial         # QEMU with serial on stdio
make debug              # QEMU with GDB server on port 1234
```

### With Block Storage

```bash
make blocks             # create 1MB block disk image
make write-catalog      # write all vocabularies to blocks
make run-blocks         # boot with block disk attached
make run-blocks-gui     # same, with VGA window
```

## Test

```bash
make test               # all tests: smoke, loops, vocabs, integration, pipeline
make test-smoke         # basic arithmetic and control flow (5 tests)
make test-loops         # BEGIN/WHILE/REPEAT/UNTIL (5 tests)
make test-integration   # vocabulary loading and execution (16 tests)
make test-vocabs        # all block-loadable vocabularies (35+ tests)
make test-network       # NE2000 two-instance transfer (52 tests, separate)
```

### Translator Tests

```bash
cd tools/translator
make clean && make      # build the translator
make test               # 270 tests across 22 suites
```

## PXE Boot (Real Hardware)

For testing on a physical machine over the network:

```bash
make pxe-setup          # configure TFTP + DHCP server (one-time, needs sudo)
make pxe-push           # deploy current build to PXE server (needs sudo)
make pxe-status         # check deployment status
```

Then boot the target machine from network (F9/F12 on HP laptops).

## Bootable ISO

```bash
make iso                # creates build/bmforth.iso
```

## Debugging with GDB

```bash
# Terminal 1
make debug

# Terminal 2
gdb
(gdb) target remote localhost:1234
(gdb) set architecture i386
(gdb) break *0x7e00
(gdb) continue
```

Useful addresses:
- `0x7E00` — kernel entry point
- `0x28000` — system variables (STATE, HERE, LATEST, BASE)
- `0x30000` — dictionary start
- `0xB8000` — VGA text buffer

## Project Structure

```
bare-metal-forth/
├── src/
│   ├── boot/boot.asm           bootloader (278 lines)
│   └── kernel/forth.asm        Forth kernel (4,879 lines)
├── forth/dict/                 22 vocabulary files (6,246 lines total)
├── tools/
│   ├── translator/             Universal Binary Translator
│   ├── embed-vocabs.py         compile vocabs into kernel binary
│   ├── write-catalog.py        build block catalog from .fth files
│   └── write-block.py          write Forth source to block images
├── tests/                      56 Python test files
├── docs/                       architecture + build docs
└── Makefile                    build system
```

## File Sizes

Expected build output:

| File | Size | Notes |
|------|------|-------|
| `boot.bin` | 512 bytes | exactly 1 sector, ends with 0xAA55 |
| `embedded.bin` | ~18 KB | 6 vocabularies, NUL-terminated |
| `kernel.bin` | 64 KB | padded, includes embedded blob |
| `bmforth.img` | ~66 KB | boot + kernel |
| `blocks.img` | 1 MB | 1024 blocks x 1KB each |

## Troubleshooting

**No output / boot failure**: Check that QEMU is using `-drive format=raw`. The image must be accessed as a raw floppy image.

**QEMU file lock error**: Kill stale QEMU processes with `pkill -9 -f "[q]emu-system"` before retrying.

**Tests time out**: Some vocab tests take 2-3 minutes. Use individual test targets to isolate failures.

**Block loading hangs**: Ensure `make blocks && make write-catalog` was run before `make run-blocks`. Block 1 must contain the vocabulary catalog.
