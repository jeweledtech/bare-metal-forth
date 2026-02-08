# Building Bare-Metal Forth

## Requirements

### Assembler
- **NASM** (Netwide Assembler) version 2.14 or later
  ```bash
  # Ubuntu/Debian
  sudo apt-get install nasm
  
  # macOS
  brew install nasm
  
  # Arch Linux
  sudo pacman -S nasm
  
  # Windows (via chocolatey)
  choco install nasm
  ```

### Emulator (for testing)
- **QEMU** x86 system emulator
  ```bash
  # Ubuntu/Debian
  sudo apt-get install qemu-system-x86
  
  # macOS
  brew install qemu
  
  # Arch Linux
  sudo pacman -S qemu
  
  # Windows
  # Download from https://www.qemu.org/download/#windows
  ```

### Optional
- **GDB** for debugging
- **dd** for disk image manipulation (included on Linux/macOS)

---

## Build Instructions

### Quick Build

```bash
cd bare-metal-forth
make
```

This produces `build/bmforth.img`, a bootable disk image.

### Build Targets

| Target | Description |
|--------|-------------|
| `make` or `make all` | Build disk image |
| `make run` | Build and run in QEMU (text mode) |
| `make run-gui` | Build and run with graphical display |
| `make run-serial` | Build and run with serial output |
| `make debug` | Build and run with GDB server |
| `make check` | Verify assembly syntax |
| `make clean` | Remove build artifacts |
| `make help` | Show all targets |

### Manual Build

If you prefer to build manually:

```bash
# Create build directory
mkdir -p build

# Assemble bootloader (must be exactly 512 bytes)
nasm -f bin src/boot/boot.asm -o build/boot.bin

# Assemble kernel
nasm -f bin src/kernel/forth.asm -o build/kernel.bin

# Combine into disk image
cat build/boot.bin build/kernel.bin > build/bmforth.img
```

---

## Running

### In QEMU (Recommended for Testing)

```bash
# Basic run (text mode in terminal)
qemu-system-i386 -drive format=raw,file=build/bmforth.img -nographic

# With graphical display
qemu-system-i386 -drive format=raw,file=build/bmforth.img

# With serial output for debugging
qemu-system-i386 -drive format=raw,file=build/bmforth.img \
    -serial stdio -display none
```

### On Real Hardware

**WARNING: This will overwrite the target drive!**

```bash
# Write to USB drive (replace /dev/sdX with your drive)
sudo dd if=build/bmforth.img of=/dev/sdX bs=512 conv=notrunc

# Sync and eject
sync
```

Then boot from the USB drive (may need to configure BIOS/UEFI).

### In Bochs

Create a `bochsrc.txt`:
```
megs: 32
romimage: file=$BXSHARE/BIOS-bochs-latest
vgaromimage: file=$BXSHARE/VGABIOS-lgpl-latest
floppya: 1_44=build/bmforth.img, status=inserted
boot: floppy
log: bochs.log
panic: action=ask
```

Run: `bochs -f bochsrc.txt`

---

## Debugging

### With GDB

```bash
# Terminal 1: Start QEMU with GDB server
make debug

# Terminal 2: Connect GDB
gdb
(gdb) target remote localhost:1234
(gdb) set architecture i386
(gdb) break *0x7e00      # Break at kernel entry
(gdb) continue
```

### Useful GDB Commands

```gdb
# View registers
info registers

# View stack (parameter stack starts at 0x10000)
x/16x $esp

# View memory at address
x/32x 0x7e00

# Disassemble
x/20i $eip

# Step one instruction
stepi

# Continue
continue
```

### Serial Output

For debugging print statements, run with serial output:
```bash
make run-serial
```

Kernel output will appear in the terminal.

---

## Testing

After booting, you should see:
```
Bare-Metal Forth v0.1 - The Ship Builder's OS
Type WORDS to see available commands
ok
```

### Basic Tests

```forth
\ Arithmetic
2 3 + .           \ Should print: 5 ok
10 3 - .          \ Should print: 7 ok
6 7 * .           \ Should print: 42 ok

\ Stack manipulation
1 2 3 .S          \ Should print: <3> 1 2 3 ok
DROP .S           \ Should print: <2> 1 2 ok
SWAP .S           \ Should print: <2> 2 1 ok

\ Define a new word
: SQUARE DUP * ;
7 SQUARE .        \ Should print: 49 ok

\ Control flow
: TEST 10 0 DO I . LOOP ;
TEST              \ Should print: 0 1 2 3 4 5 6 7 8 9 ok

\ Variables
VARIABLE X
42 X !
X @ .             \ Should print: 42 ok
```

### Forth-83 Division Test

```forth
\ Test floored division semantics
-7 3 / .          \ Should print: -3 (floored, not -2)
-7 3 MOD .        \ Should print: 2 (positive remainder)
7 -3 / .          \ Should print: -3
7 -3 MOD .        \ Should print: -2
```

### Memory Dump Test

```forth
HEX
7E00 40 DUMP      \ Dump kernel entry point
DECIMAL
```

---

## Troubleshooting

### "Boot failed" or no output
- Verify QEMU is using the correct image file
- Check bootloader is exactly 512 bytes with 0xAA55 signature
- Try with `-nographic` flag

### Keyboard doesn't work
- QEMU may need focus on the window
- Try clicking in the QEMU window
- With `-nographic`, input goes directly to serial

### Stack underflow
- Forth requires operands before operators
- Use `.S` to inspect stack state

### Word not found
- Forth is case-insensitive but check spelling
- Use `WORDS` to list available words

### Crash during word execution
- May indicate stack corruption
- Restart and use simpler test cases
- Check for missing operands

---

## Project Structure

```
bare-metal-forth/
├── Makefile              # Build system
├── build/                # Build output (created by make)
│   ├── boot.bin         # Assembled bootloader
│   ├── kernel.bin       # Assembled kernel
│   └── bmforth.img      # Combined disk image
├── docs/                 # Documentation
│   ├── MANIFEST.md      # Project philosophy
│   ├── README.md        # Overview
│   ├── ROADMAP.md       # Development plan
│   ├── RECRUITING.md    # Collaboration guide
│   └── BUILD.md         # This file
└── src/
    ├── boot/
    │   └── boot.asm     # Bootloader (512 bytes)
    └── kernel/
        └── forth.asm    # Forth kernel (~2500 lines)
```

---

## File Sizes

Expected build output sizes:
- `boot.bin`: exactly 512 bytes
- `kernel.bin`: ~16KB (padded to 16KB boundary)
- `bmforth.img`: ~32KB (boot + kernel)

If sizes differ significantly, check for assembly errors.

---

## Next Steps

After successful build and test:

1. **Explore the system**: Try the built-in words
2. **Define new words**: Use `: NAME ... ;` syntax
3. **Inspect the dictionary**: Use `WORDS` and `SEE`
4. **Test direct memory**: Use `@` `!` `C@` `C!`
5. **Study the source**: Read `forth.asm` to understand internals

---

*"The stars are waiting."*
