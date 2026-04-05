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

# Embedded vocabularies (evaluated at boot, no block storage needed)
EMBED_VOCABS = forth/dict/hardware.fth forth/dict/port-mapper.fth forth/dict/echoport.fth forth/dict/pci-enum.fth forth/dict/rtl8168.fth forth/dict/ahci.fth forth/dict/ntfs.fth forth/dict/fat32.fth forth/dict/auto-detect.fth
EMBEDDED = $(BUILD)/embedded.bin

$(EMBEDDED): $(EMBED_VOCABS) tools/embed-vocabs.py | $(BUILD)
	python3 tools/embed-vocabs.py $@ $(EMBED_VOCABS)

# Assemble kernel (depends on embedded vocab binary)
$(KERNEL): $(SRC_KERNEL)/forth.asm $(EMBEDDED) | $(BUILD)
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
$(BLOCKS): | $(BUILD)
	dd if=/dev/zero of=$(BLOCKS) bs=1024 count=1024
	@echo "Block disk created: $(BLOCKS) (1MB, 1024 blocks)"
blocks: $(BLOCKS)

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
		STATUS=$$?; pkill -9 -f "[q]emu.*$(TEST_PORT_BASE)" 2>/dev/null; exit $$STATUS

# Run BEGIN/WHILE/REPEAT test (no block storage needed)
test-loops: $(IMAGE)
	@echo "Running loop control flow test..."
	@$(QEMU) -drive file=$(IMAGE),format=raw,if=floppy \
		-serial tcp::$$(($(TEST_PORT_BASE)+1)),server=on,wait=off \
		-display none -daemonize
	@sleep 2
	@python3 tests/test_begin_while.py $$(($(TEST_PORT_BASE)+1)); \
		STATUS=$$?; pkill -9 -f "[q]emu.*$$(($(TEST_PORT_BASE)+1))" 2>/dev/null; exit $$STATUS

# Run all vocabulary tests (need block storage)
test-vocabs: $(IMAGE) $(BLOCKS) write-catalog
	@echo "Running vocabulary tests..."
	@PORT_BASE=$$(($(TEST_PORT_BASE)+10)); \
	for test in test_editor test_x86_asm test_metacompiler test_driver_vocabs test_disasm test_port_mapper test_echoport; do \
		PORT=$$PORT_BASE; PORT_BASE=$$((PORT_BASE+1)); \
		echo "  $$test (port $$PORT)..."; \
		$(QEMU) -drive file=$(IMAGE),format=raw,if=floppy \
			-drive file=$(BLOCKS),format=raw,if=ide,index=1 \
			-nic model=ne2k_pci \
			-serial tcp::$$PORT,server=on,wait=off \
			-display none -daemonize; \
		sleep 2; \
		python3 tests/$$test.py $$PORT; \
		STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; sleep 1; \
		if [ $$STATUS -ne 0 ]; then exit $$STATUS; fi; \
	done

# Run full integration test
test-integration: $(IMAGE) $(BLOCKS) write-catalog
	@echo "Running full integration test..."
	@PORT=$$(($(TEST_PORT_BASE)+20)); \
	$(QEMU) -drive file=$(IMAGE),format=raw,if=floppy \
		-drive file=$(BLOCKS),format=raw,if=ide,index=1 \
		-serial tcp::$$PORT,server=on,wait=off \
		-display none -daemonize; \
	sleep 2; \
	python3 tests/test_full_integration.py $$PORT; \
	STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; exit $$STATUS

# --- End-to-End Pipeline: .sys binary → block vocab → USING ---

TRANSLATOR = tools/translator/bin/translator
WRITE_BLOCK = tools/write-block.py
VOCAB_BUILD = $(BUILD)/vocabs
I8042_SYS = tools/translator/tests/data/i8042prt.sys
HARDWARE_FTH = forth/dict/hardware.fth

# Combined block image: HARDWARE at block 50, I8042PRT at block 100
$(VOCAB_BUILD)/combined.img: $(HARDWARE_FTH) $(I8042_SYS) | $(VOCAB_BUILD)
	$(TRANSLATOR) -t forth $(I8042_SYS) > $(VOCAB_BUILD)/i8042prt.fth
	dd if=/dev/zero of=$@ bs=1024 count=1024 2>/dev/null
	python3 $(WRITE_BLOCK) $@ 50 $(HARDWARE_FTH)
	python3 $(WRITE_BLOCK) $@ 100 $(VOCAB_BUILD)/i8042prt.fth

$(VOCAB_BUILD):
	mkdir -p $(VOCAB_BUILD)

# Boot with HARDWARE + I8042PRT vocabularies
.PHONY: run-i8042
run-i8042: $(IMAGE) $(VOCAB_BUILD)/combined.img
	$(QEMU) -drive format=raw,file=$(IMAGE) \
	        -drive format=raw,file=$(VOCAB_BUILD)/combined.img,if=ide,index=1 \
	        -nographic

# End-to-end pipeline test (HARDWARE + I8042PRT, zero ? errors)
test-pipeline-e2e: $(IMAGE) $(VOCAB_BUILD)/combined.img
	@echo "Running end-to-end pipeline test..."
	@PORT=$$(($(TEST_PORT_BASE)+30)); \
	$(QEMU) -drive file=$(IMAGE),format=raw,if=floppy \
		-drive file=$(VOCAB_BUILD)/combined.img,format=raw,if=ide,index=1 \
		-serial tcp::$$PORT,server=on,wait=off \
		-display none -daemonize; \
	sleep 2; \
	python3 tests/test_pipeline_e2e.py $$PORT; \
	STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; exit $$STATUS

# Run NE2000 network test (two QEMU instances)
test-network: $(IMAGE) $(BLOCKS) write-catalog
	@echo "Running NE2000 network test..."
	@python3 tests/test_ne2000_network.py $$(($(TEST_PORT_BASE)+40))

# --- Debug flush targets ---

DEBUG_KERNEL = $(BUILD)/kernel-debug.bin
DEBUG_IMAGE = $(BUILD)/bmforth-debug.img

$(DEBUG_KERNEL): $(SRC_KERNEL)/forth.asm | $(BUILD)
	$(NASM) -f bin -DDEBUG_FLUSH -o $@ $<

$(DEBUG_IMAGE): $(BOOTLOADER) $(DEBUG_KERNEL)
	cat $(BOOTLOADER) $(DEBUG_KERNEL) > $@

test-flush: $(DEBUG_IMAGE) $(BLOCKS)
	@echo "Running flush stress test..."
	@PORT=$$(($(TEST_PORT_BASE)+50)); \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; sleep 1; \
	$(QEMU) -drive file=$(DEBUG_IMAGE),format=raw,if=floppy \
		-drive file=$(BLOCKS),format=raw,if=ide,index=1 \
		-serial tcp::$$PORT,server=on,wait=off \
		-display none -daemonize; \
	sleep 2; \
	python3 tests/test_flush_stress.py $$PORT; \
	STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; exit $$STATUS

test-meta-compile: $(IMAGE) $(BLOCKS) write-catalog
	@echo "Running metacompiler compile test (B5)..."
	@python3 tests/test_meta_compile.py $$(($(TEST_PORT_BASE)+55))

test-meta-boot: $(IMAGE) $(BLOCKS) write-catalog
	@echo "Running metacompiler boot test..."
	@python3 tests/test_meta_boot.py $$(($(TEST_PORT_BASE)+60))

test-ubt-expansion:
	@echo "Running UBT expansion tests..."
	@cd tools/translator && make 2>&1 | tail -1
	@python3 tests/test_ubt_expansion.py

# Run all tests
test: test-smoke test-loops test-vocabs test-integration test-pipeline-e2e test-ubt-expansion test-meta-compile
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

# --- PXE Dev Workflow ---

.PHONY: pxe-setup pxe-push pxe-status

pxe-setup:
	@echo "Setting up PXE boot server..."
	@bash tools/pxe/setup-tftp.sh
	@bash tools/pxe/setup-dnsmasq.sh
	@bash tools/pxe/install-pxelinux-cfg.sh
	@echo ""
	@echo "PXE setup complete. Run 'make pxe-push' to deploy an image."

pxe-push: $(IMAGE)
	@bash tools/pxe/push.sh

pxe-status:
	@bash tools/pxe/test-pxe.sh

.PHONY: all run run-gui run-serial debug check clean help iso blocks run-blocks run-blocks-gui write-block write-catalog test test-smoke test-loops test-vocabs test-integration test-flush test-meta-compile test-meta-boot pxe-setup pxe-push pxe-status
