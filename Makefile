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
BLOCKS = $(BUILD)/blocks.img

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

# --- Block Storage Targets ---

# Create blank 1MB blocks disk (1024 x 1K blocks)
blocks: | $(BUILD)
	dd if=/dev/zero of=$(BLOCKS) bs=1024 count=1024
	@echo "Block disk created: $(BLOCKS) (1MB, 1024 blocks)"

# Run with block storage attached (IDE slave)
run-blocks: $(IMAGE) $(BLOCKS)
	$(QEMU) -drive format=raw,file=$(IMAGE) \
	        -drive format=raw,file=$(BLOCKS),if=ide,index=1 \
	        -nographic

# Run with block storage and graphics
run-blocks-gui: $(IMAGE) $(BLOCKS)
	$(QEMU) -drive format=raw,file=$(IMAGE) \
	        -drive format=raw,file=$(BLOCKS),if=ide,index=1

# Write Forth source into a block (auto-spans multiple blocks for long files)
# Usage: make write-block BLK=0 SRC=forth/dict/myfile.fth
write-block: $(BLOCKS)
	python3 tools/write-block.py $(BLOCKS) $(BLK) $(SRC)

# Build vocabulary catalog and write all .fth files to blocks disk
# Block 0: reserved, Block 1: catalog, Block 2+: vocabularies
write-catalog: $(BLOCKS)
	python3 tools/write-catalog.py $(BLOCKS) forth/dict/

# --- Test Targets ---

# Port base for tests (each test uses a different port)
TEST_PORT_BASE ?= 4500

# Run smoke test (no block storage needed)
test-smoke: $(IMAGE)
	@echo "Running smoke test..."
	@$(QEMU) -drive file=$(IMAGE),format=raw,if=floppy \
		-serial tcp::$(TEST_PORT_BASE),server=on,wait=off \
		-display none -daemonize
	@sleep 2
	@python3 tests/smoke_test.py $(TEST_PORT_BASE); \
		STATUS=$$?; pkill -9 -f "qemu.*$(TEST_PORT_BASE)" 2>/dev/null; exit $$STATUS

# Run BEGIN/WHILE/REPEAT test (no block storage needed)
test-loops: $(IMAGE)
	@echo "Running loop control flow test..."
	@$(QEMU) -drive file=$(IMAGE),format=raw,if=floppy \
		-serial tcp::$$(($(TEST_PORT_BASE)+1)),server=on,wait=off \
		-display none -daemonize
	@sleep 2
	@python3 tests/test_begin_while.py $$(($(TEST_PORT_BASE)+1)); \
		STATUS=$$?; pkill -9 -f "qemu.*$$(($(TEST_PORT_BASE)+1))" 2>/dev/null; exit $$STATUS

# Run all vocabulary tests (need block storage)
test-vocabs: $(IMAGE) $(BLOCKS) write-catalog
	@echo "Running vocabulary tests..."
	@for test in test_editor test_x86_asm test_metacompiler; do \
		PORT=$$(($(TEST_PORT_BASE) + RANDOM % 1000 + 100)); \
		echo "  $$test (port $$PORT)..."; \
		$(QEMU) -drive file=$(IMAGE),format=raw,if=floppy \
			-drive file=$(BLOCKS),format=raw,if=ide,index=1 \
			-serial tcp::$$PORT,server=on,wait=off \
			-display none -daemonize; \
		sleep 2; \
		python3 tests/$$test.py $$PORT; \
		STATUS=$$?; pkill -9 -f "qemu.*$$PORT" 2>/dev/null; sleep 1; \
		if [ $$STATUS -ne 0 ]; then exit $$STATUS; fi; \
	done

# Run full integration test
test-integration: $(IMAGE) $(BLOCKS) write-catalog
	@echo "Running full integration test..."
	@PORT=$$(($(TEST_PORT_BASE) + RANDOM % 1000 + 200)); \
	$(QEMU) -drive file=$(IMAGE),format=raw,if=floppy \
		-drive file=$(BLOCKS),format=raw,if=ide,index=1 \
		-serial tcp::$$PORT,server=on,wait=off \
		-display none -daemonize; \
	sleep 2; \
	python3 tests/test_full_integration.py $$PORT; \
	STATUS=$$?; pkill -9 -f "qemu.*$$PORT" 2>/dev/null; exit $$STATUS

# Run all tests
test: test-smoke test-loops test-vocabs test-integration
	@echo "All tests passed!"

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
	@echo "  all            - Build disk image (default)"
	@echo "  run            - Run in QEMU (text mode)"
	@echo "  run-gui        - Run in QEMU with graphics"
	@echo "  run-serial     - Run with serial output"
	@echo "  debug          - Run with GDB server"
	@echo "  blocks         - Create blank 1MB block storage disk"
	@echo "  run-blocks     - Run with block storage attached (text mode)"
	@echo "  run-blocks-gui - Run with block storage attached (graphics)"
	@echo "  write-block    - Write source file into a block (BLK=n SRC=file)"
	@echo "  check          - Syntax check only"
	@echo "  iso            - Create bootable ISO"
	@echo "  clean          - Remove build artifacts"
	@echo "  help           - Show this help"
	@echo ""
	@echo "Block Storage:"
	@echo "  make blocks                          # Create blank disk"
	@echo "  make write-block BLK=0 SRC=file.fth  # Write source to block 0"
	@echo "  make run-blocks                      # Boot with blocks disk"
	@echo ""
	@echo "Requirements:"
	@echo "  - nasm (Netwide Assembler)"
	@echo "  - qemu-system-i386 (for testing)"
	@echo "  - python3 (for write-block utility)"

.PHONY: all run run-gui run-serial debug check clean help iso blocks run-blocks run-blocks-gui write-block write-catalog test test-smoke test-loops test-vocabs test-integration
