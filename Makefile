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
COMBINED = $(BUILD)/combined.img
COMBINED_IDE = $(BUILD)/combined-ide.img

# Default target
all: $(IMAGE)

# Create build directory
$(BUILD):
	mkdir -p $(BUILD)

# Assemble bootloader
$(BOOTLOADER): $(SRC_BOOT)/boot.asm | $(BUILD)
	$(NASM) -f bin -o $@ $<

# Embedded vocabularies (evaluated at boot, no block storage needed)
EMBED_VOCABS = forth/dict/hardware.fth forth/dict/port-mapper.fth forth/dict/echoport.fth forth/dict/pci-enum.fth forth/dict/catalog-resolver.fth
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

# Create blank 2MB blocks disk (2048 x 1K blocks)
$(BLOCKS): | $(BUILD)
	dd if=/dev/zero of=$(BLOCKS) bs=1024 count=2048
	@echo "Block disk created: $(BLOCKS) (2MB, 2048 blocks)"
blocks: $(BLOCKS)

# Run with block storage attached (combined image)
run-blocks: $(COMBINED) $(COMBINED_IDE)
	$(QEMU) -drive format=raw,file=$(COMBINED) \
	        -drive format=raw,file=$(COMBINED_IDE),if=ide,index=1 \
	        -nographic

# Run with block storage and graphics
run-blocks-gui: $(COMBINED) $(COMBINED_IDE)
	$(QEMU) -drive format=raw,file=$(COMBINED) \
	        -drive format=raw,file=$(COMBINED_IDE),if=ide,index=1

# Write Forth source into a block (auto-spans multiple blocks for long files)
# Usage: make write-block BLK=0 SRC=forth/dict/myfile.fth
write-block: $(BLOCKS)
	python3 tools/write-block.py $(BLOCKS) $(BLK) $(SRC)

# Build vocabulary catalog and write all .fth files to blocks disk
# Block 0: reserved, Block 1: catalog, Block 2+: vocabularies
write-catalog: $(BLOCKS)
	python3 tools/write-catalog.py $(BLOCKS) forth/dict/

# --- Combined Image ---

# Combined image: kernel + blocks concatenated
# Block N is at LBA 129 + N*2 within this image
$(COMBINED): $(IMAGE) $(BLOCKS)
	cat $(IMAGE) $(BLOCKS) > $(COMBINED)
	@echo "Combined image: $(COMBINED)"
	@echo "  Kernel: $$(stat -c%s $(IMAGE)) bytes (LBA 0-128)"
	@echo "  Blocks: $$(stat -c%s $(BLOCKS)) bytes (LBA 129+)"
	@echo "  Total:  $$(stat -c%s $(COMBINED)) bytes"

combined: $(COMBINED)

# QEMU IDE copy: avoids file lock conflict when same data is both floppy and IDE
$(COMBINED_IDE): $(COMBINED)
	cp $(COMBINED) $(COMBINED_IDE)

# Verify kernel size hasn't exceeded 66048 bytes (BLOCKS_LBA_BASE constraint)
check-kernel-size: $(IMAGE)
	@SIZE=$$(stat -c%s $(IMAGE)); \
	 if [ $$SIZE -gt 66048 ]; then \
	   echo "ERROR: Kernel image $$SIZE bytes exceeds 66048 limit!"; \
	   echo "  BLOCKS_LBA_BASE must be updated in forth.asm"; \
	   exit 1; \
	 else \
	   echo "Kernel size OK: $$SIZE bytes (limit: 66048)"; \
	 fi

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
	@cat $(IMAGE) $(BLOCKS) > $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running vocabulary tests..."
	@PORT_BASE=$$(($(TEST_PORT_BASE)+10)); \
	for test in test_editor test_x86_asm test_driver_vocabs test_disasm test_port_mapper test_echoport; do \
		PORT=$$PORT_BASE; PORT_BASE=$$((PORT_BASE+1)); \
		echo "  $$test (port $$PORT)..."; \
		$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
			-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
			-nic model=ne2k_pci \
			-serial tcp::$$PORT,server=on,wait=off \
			-display none -daemonize; \
		sleep 2; \
		python3 tests/$$test.py $$PORT; \
		STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; sleep 1; \
		if [ $$STATUS -ne 0 ]; then exit $$STATUS; fi; \
	done

# Run GUI vocabulary tests (paid tier — skipped if files absent)
test-gui: $(IMAGE) $(BLOCKS) write-catalog
	@cat $(IMAGE) $(BLOCKS) > $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@PORT_BASE=$$(($(TEST_PORT_BASE)+30)); \
	for test in test_stub_dispatch test_ui_core test_gui_harvest test_ui_parser test_ui_events; do \
		if [ ! -f tests/$$test.py ]; then continue; fi; \
		PORT=$$PORT_BASE; PORT_BASE=$$((PORT_BASE+1)); \
		echo "  $$test (port $$PORT)..."; \
		$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
			-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
			-serial tcp::$$PORT,server=on,wait=off \
			-display none -daemonize; \
		sleep 2; \
		python3 tests/$$test.py $$PORT; \
		STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; sleep 1; \
		if [ $$STATUS -ne 0 ]; then exit $$STATUS; fi; \
	done

# Run full integration test
test-integration: $(IMAGE) $(BLOCKS) write-catalog
	@cat $(IMAGE) $(BLOCKS) > $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running full integration test..."
	@PORT=$$(($(TEST_PORT_BASE)+20)); \
	$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp::$$PORT,server=on,wait=off \
		-display none -daemonize; \
	sleep 2; \
	python3 tests/test_full_integration.py $$PORT; \
	STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; exit $$STATUS

# Run NE2000 network test (two QEMU instances)
test-network: $(IMAGE) $(BLOCKS) write-catalog
	@cat $(IMAGE) $(BLOCKS) > $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running NE2000 network test..."
	@python3 tests/test_ne2000_network.py $$(($(TEST_PORT_BASE)+40))

# --- Debug flush targets ---

DEBUG_KERNEL = $(BUILD)/kernel-debug.bin
DEBUG_IMAGE = $(BUILD)/bmforth-debug.img

$(DEBUG_KERNEL): $(SRC_KERNEL)/forth.asm | $(BUILD)
	$(NASM) -f bin -DDEBUG_FLUSH -o $@ $<

$(DEBUG_IMAGE): $(BOOTLOADER) $(DEBUG_KERNEL)
	cat $(BOOTLOADER) $(DEBUG_KERNEL) > $@

DEBUG_COMBINED = $(BUILD)/combined-debug.img
DEBUG_COMBINED_IDE = $(BUILD)/combined-debug-ide.img

test-flush: $(DEBUG_IMAGE) $(BLOCKS)
	@cat $(DEBUG_IMAGE) $(BLOCKS) > $(DEBUG_COMBINED)
	@cp $(DEBUG_COMBINED) $(DEBUG_COMBINED_IDE)
	@echo "Running flush stress test..."
	@PORT=$$(($(TEST_PORT_BASE)+50)); \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; sleep 1; \
	$(QEMU) -drive file=$(DEBUG_COMBINED),format=raw,if=floppy \
		-drive file=$(DEBUG_COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp::$$PORT,server=on,wait=off \
		-display none -daemonize; \
	sleep 2; \
	python3 tests/test_flush_stress.py $$PORT; \
	STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; exit $$STATUS

# Lint Forth source (vocabulary files + kernel assembly)
lint:
	@python3 tools/lint-forth.py forth/dict/*.fth
	@python3 tools/lint-forth.py --asm $(SRC_KERNEL)/forth.asm

# Run ARM64 boot test (cross-compile + QEMU raspi3b)
test-arm64-boot: $(IMAGE) $(BLOCKS) write-catalog
	@cat $(IMAGE) $(BLOCKS) > $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running ARM64 boot test..."
	@python3 tests/test_arm64_boot.py $$(($(TEST_PORT_BASE)+50)); \
		STATUS=$$?; \
		pkill -9 -f "[q]emu.*$$(($(TEST_PORT_BASE)+50))" 2>/dev/null; \
		pkill -9 -f "[q]emu.*$$(($(TEST_PORT_BASE)+52))" 2>/dev/null; \
		exit $$STATUS

# Run Cortex-M33 boot test (cross-compile + QEMU mps2-an505)
test-cortexm: $(IMAGE) $(BLOCKS) write-catalog
	@cat $(IMAGE) $(BLOCKS) > $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running Cortex-M33 boot test..."
	@python3 tests/test_cortexm_boot.py $$(($(TEST_PORT_BASE)+60)); \
		STATUS=$$?; \
		pkill -9 -f "[q]emu.*$$(($(TEST_PORT_BASE)+60))" 2>/dev/null; \
		pkill -9 -f "[q]emu.*$$(($(TEST_PORT_BASE)+62))" 2>/dev/null; \
		exit $$STATUS

# Run AHCI write test (ICH9-AHCI + scratch disk)
AHCI_SCRATCH = $(BUILD)/ahci-scratch.img
$(AHCI_SCRATCH): | $(BUILD)
	dd if=/dev/zero of=$(AHCI_SCRATCH) bs=512 count=2048 2>/dev/null

test-ahci-write: $(IMAGE) $(BLOCKS) write-catalog $(AHCI_SCRATCH)
	@cat $(IMAGE) $(BLOCKS) > $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running AHCI write test..."
	@PORT=$$(($(TEST_PORT_BASE)+75)); \
	$(QEMU) \
		-drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-drive file=$(AHCI_SCRATCH),format=raw,if=none,id=sata0 \
		-device ich9-ahci,id=ahci0 \
		-device ide-hd,drive=sata0,bus=ahci0.0 \
		-serial tcp::$$PORT,server=on,wait=off \
		-display none & \
	sleep 3; \
	python3 tests/test_ahci_write.py $$PORT; \
	STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; exit $$STATUS

# Run pipeline integration test (offline)
test-pipeline:
	@echo "Running pipeline integration test..."
	@python3 tests/test_pipeline_integration.py

# Run all tests (lint first, then functional tests)
test: lint test-smoke test-loops test-vocabs test-gui test-integration
	@echo "All tests passed!"

# Create ISO (requires xorriso)
iso: $(IMAGE)
	mkdir -p $(BUILD)/iso
	cp $(IMAGE) $(BUILD)/iso/
	xorriso -as mkisofs -b bmforth.img -no-emul-boot -o $(BUILD)/bmforth.iso $(BUILD)/iso/

# Check syntax only (no output)
check: lint
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

pxe-push: $(COMBINED) check-kernel-size
	@bash tools/pxe/push.sh

pxe-status:
	@bash tools/pxe/test-pxe.sh

.PHONY: all run run-gui run-serial debug check clean help iso blocks run-blocks run-blocks-gui write-block write-catalog combined check-kernel-size test test-smoke test-loops test-vocabs test-gui test-integration test-flush test-network test-ahci-write pxe-setup pxe-push pxe-status
