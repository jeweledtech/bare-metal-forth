# Bare-Metal Forth Makefile
# The Ship Builder's System

NASM = nasm
QEMU = qemu-system-i386
QEMU64 = qemu-system-x86_64

# Directories
SRC_BOOT = src/boot
SRC_KERNEL = src/kernel
BUILD = build

# Files
BOOTLOADER = $(BUILD)/boot.bin
KERNEL = $(BUILD)/kernel.bin
IMAGE = $(BUILD)/bmforth.img

# Default target
all: $(IMAGE)

# Create build directory
$(BUILD):
	mkdir -p $(BUILD)

# Assemble bootloader
$(BOOTLOADER): $(SRC_BOOT)/boot.asm | $(BUILD)
	$(NASM) -f bin -o $@ $<

# Assemble kernel
$(KERNEL): $(SRC_KERNEL)/forth.asm | $(BUILD)
	$(NASM) -f bin -o $@ $<

# Create disk image
# Bootloader at sector 0, kernel starting at sector 1
$(IMAGE): $(BOOTLOADER) $(KERNEL)
	@echo "Creating disk image..."
	cat $(BOOTLOADER) $(KERNEL) > $@
	@# Pad to 1.44MB floppy size (optional, helps with some emulators)
	@# truncate -s 1474560 $@
	@echo "Disk image created: $@"
	@echo "  Bootloader: $$(stat -c%s $(BOOTLOADER)) bytes"
	@echo "  Kernel: $$(stat -c%s $(KERNEL)) bytes"
	@echo "  Total: $$(stat -c%s $@) bytes"

# Run in QEMU (text mode, no graphics)
run: $(IMAGE)
	$(QEMU) -drive format=raw,file=$(IMAGE) -nographic

# Run in QEMU with graphics
run-gui: $(IMAGE)
	$(QEMU) -drive format=raw,file=$(IMAGE)

# Run with debugging enabled (GDB server on port 1234)
debug: $(IMAGE)
	$(QEMU) -drive format=raw,file=$(IMAGE) -s -S -nographic &
	@echo "QEMU started with GDB server on localhost:1234"
	@echo "Connect with: gdb -ex 'target remote localhost:1234'"

# Run with serial output to terminal
run-serial: $(IMAGE)
	$(QEMU) -drive format=raw,file=$(IMAGE) -serial mon:stdio -nographic

# Create ISO (requires xorriso)
iso: $(IMAGE)
	mkdir -p $(BUILD)/iso
	cp $(IMAGE) $(BUILD)/iso/
	xorriso -as mkisofs -b bmforth.img -no-emul-boot -o $(BUILD)/bmforth.iso $(BUILD)/iso/

# Check syntax only (no output)
check:
	$(NASM) -f bin -o /dev/null $(SRC_BOOT)/boot.asm
	$(NASM) -f bin -o /dev/null $(SRC_KERNEL)/forth.asm
	@echo "Syntax check passed."

# Clean build artifacts
clean:
	rm -rf $(BUILD)

# Show help
help:
	@echo "Bare-Metal Forth Build System"
	@echo "============================="
	@echo ""
	@echo "Targets:"
	@echo "  all        - Build disk image (default)"
	@echo "  run        - Run in QEMU (text mode)"
	@echo "  run-gui    - Run in QEMU with graphics"
	@echo "  run-serial - Run with serial output"
	@echo "  debug      - Run with GDB server"
	@echo "  check      - Syntax check only"
	@echo "  iso        - Create bootable ISO"
	@echo "  clean      - Remove build artifacts"
	@echo "  help       - Show this help"
	@echo ""
	@echo "Requirements:"
	@echo "  - nasm (Netwide Assembler)"
	@echo "  - qemu-system-i386 (for testing)"

.PHONY: all run run-gui run-serial debug check clean help iso
