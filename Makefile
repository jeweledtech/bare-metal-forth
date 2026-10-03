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
VBR = $(BUILD)/vbr.bin
KERNEL = $(BUILD)/kernel.bin
IMAGE = $(BUILD)/bmforth.img
BLOCKS = $(BUILD)/blocks.img
COMBINED = $(BUILD)/combined.img
COMBINED_IDE = $(BUILD)/combined-ide.img
NTFS_TEST = test-data/ntfs-test.img
IMAGE_FREE = $(BUILD)/bmforth-free.img

# Auto-detect build tier: full (paid vocabs present) or free (public only)
ifneq ($(wildcard forth/dict/ahci.fth),)
  BUILD_TIER = full
  ACTIVE_IMAGE = $(IMAGE)
else
  BUILD_TIER = free
  ACTIVE_IMAGE = $(IMAGE_FREE)
endif

# Default target — builds whichever tier the working tree supports
all: $(ACTIVE_IMAGE)

# Create build directory
$(BUILD):
	mkdir -p $(BUILD)

# Assemble bootloader
$(BOOTLOADER): $(SRC_BOOT)/boot.asm | $(BUILD)
	$(NASM) -f bin -o $@ $<

# Assemble VBR chainload variant (sibling of boot.bin, never replaces it)
$(VBR): $(SRC_BOOT)/vbr.asm | $(BUILD)
	$(NASM) -f bin -o $@ $<

# Embedded vocabularies (evaluated at boot, no block storage needed)
EMBED_VOCABS = forth/dict/hardware.fth forth/dict/port-mapper.fth forth/dict/echoport.fth forth/dict/pci-enum.fth forth/dict/catalog-resolver.fth forth/dict/ahci.fth forth/dict/rtl8168.fth forth/dict/ntfs.fth forth/dict/auto-detect.fth forth/dict/fat32.fth forth/dict/ui-core.fth forth/dict/ui-parser.fth forth/dict/ui-events.fth forth/dict/gui-harvest.fth forth/dict/ps2-keyboard.fth forth/dict/file-editor-core.fth forth/dict/file-editor-disk.fth forth/dict/notepad-form.fth forth/dict/notepad.fth forth/dict/hello-form.fth forth/dict/hello-app.fth forth/dict/file-stream.fth forth/dict/file-browser-form.fth forth/dict/file-browser.fth
EMBEDDED = $(BUILD)/embedded.bin

# Free-tier vocabularies (public-tracked only, no paid/gitignored content)
# Excludes: file-editor-disk (NTFS/AHCI), file-stream (NTFS/AHCI/RTL8168),
#   file-browser (NTFS). NOTEPAD works RAM-only via file-editor-core vectors.
EMBED_VOCABS_FREE = forth/dict/hardware.fth forth/dict/port-mapper.fth forth/dict/echoport.fth \
    forth/dict/pci-enum.fth forth/dict/catalog-resolver.fth forth/dict/ps2-keyboard.fth \
    forth/dict/ui-core.fth forth/dict/ui-parser.fth forth/dict/ui-events.fth \
    forth/dict/gui-harvest.fth forth/dict/file-editor-core.fth forth/dict/notepad-form.fth \
    forth/dict/notepad.fth forth/dict/hello-form.fth forth/dict/hello-app.fth \
    forth/dict/settings-form.fth forth/dict/settings.fth \
    forth/dict/file-browser-form.fth

EMBEDDED_FREE = $(BUILD)/embedded-free.bin
KERNEL_FREE = $(BUILD)/kernel-free.bin

# For tools/evidence-snapshot.sh: make expands its own variable
# (continuations and all), so no external parser exists to drift.
.PHONY: print-embed-vocabs
print-embed-vocabs:
	@echo $(EMBED_VOCABS)

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

# --- Free-tier build (public vocabularies only) ---

$(EMBEDDED_FREE): $(EMBED_VOCABS_FREE) tools/embed-vocabs.py | $(BUILD)
	python3 tools/embed-vocabs.py $@ $(EMBED_VOCABS_FREE)

$(KERNEL_FREE): $(SRC_KERNEL)/forth.asm $(EMBEDDED_FREE) | $(BUILD)
	$(NASM) -f bin -dEMBED_FILE='"build/embedded-free.bin"' -o $@ $<

$(IMAGE_FREE): $(BOOTLOADER) $(KERNEL_FREE)
	@echo "Creating free-tier disk image..."
	cat $(BOOTLOADER) $(KERNEL_FREE) > $@
	@echo "Free-tier image: $@ ($$(stat -c%s $@) bytes)"

free: $(IMAGE_FREE)

run-free: $(IMAGE_FREE)
	$(QEMU) -drive file=$(IMAGE_FREE),format=raw,if=floppy -nographic

# --- Sync check (paid files vs private repo) ---
PRIVATE_REPO = ../forthos-vocabularies
PAID_VOCABS = ahci rtl8168 ntfs auto-detect fat32 surveyor file-editor-disk log-harness

check-sync:
	@if [ ! -d "$(PRIVATE_REPO)/forth/dict" ]; then \
		echo "Private vocab repo not present at $(PRIVATE_REPO) — skipping sync check"; \
		exit 0; \
	fi; \
	FAIL=0; \
	for v in $(PAID_VOCABS); do \
		LOCAL="forth/dict/$$v.fth"; \
		REMOTE="$(PRIVATE_REPO)/forth/dict/$$v.fth"; \
		if [ ! -f "$$LOCAL" ]; then continue; fi; \
		if [ ! -f "$$REMOTE" ]; then \
			echo "MISSING in private repo: $$REMOTE"; FAIL=1; continue; \
		fi; \
		if ! diff -q "$$LOCAL" "$$REMOTE" >/dev/null 2>&1; then \
			echo "DIVERGED: $$v.fth"; \
			FAIL=1; \
		fi; \
	done; \
	if [ $$FAIL -ne 0 ]; then \
		echo "check-sync FAILED: paid files have diverged"; \
		exit 1; \
	fi; \
	echo "check-sync OK: all paid files in sync"

# Run in QEMU (text mode, no graphics)
run: $(ACTIVE_IMAGE)
	$(QEMU) -drive format=raw,file=$(ACTIVE_IMAGE) -nographic

# Run in QEMU with graphics
run-gui: $(ACTIVE_IMAGE)
	$(QEMU) -drive format=raw,file=$(ACTIVE_IMAGE)

# Run with debugging enabled (GDB server on port 1234)
debug: $(ACTIVE_IMAGE)
	$(QEMU) -drive format=raw,file=$(ACTIVE_IMAGE) -s -S -nographic &
	@echo "QEMU started with GDB server on localhost:1234"
	@echo "Connect with: gdb -ex 'target remote localhost:1234'"

# Run with serial output to terminal
run-serial: $(ACTIVE_IMAGE)
	$(QEMU) -drive format=raw,file=$(ACTIVE_IMAGE) -serial mon:stdio -nographic

# --- Block Storage Targets ---

# All vocabulary sources — anything that should land in the catalog
VOCAB_SOURCES := $(wildcard forth/dict/*.fth) \
                 $(wildcard ../forthos-vocabularies/forth/dict/*.fth)

# Create blank 2MB blocks disk (2048 x 1K blocks)
$(BLOCKS): | $(BUILD)
	dd if=/dev/zero of=$(BLOCKS) bs=1024 count=2048
	@echo "Block disk created: $(BLOCKS) (2MB, 2048 blocks)"
blocks: $(BLOCKS)

# Stamp file proves the catalog has been written into $(BLOCKS)
# for the current set of vocab sources.  If write-catalog fails,
# the stamp is not created and the next build retries.
#
# $(VBR) is a prerequisite because the catalog now carries the VBR
# template as a raw payload. A catalog built from a stale vbr.bin
# yields a template that passes its OWN sum check while being the
# wrong build; the G6 harness compares against the host's
# build/vbr.bin and would catch it, but at the wrong layer and with
# far worse attribution.
$(BUILD)/.catalog.stamp: $(BLOCKS) $(VOCAB_SOURCES) tools/write-catalog.py $(VBR)
	@echo "Populating catalog into $(BLOCKS)..."
	$(MAKE) write-catalog && touch $@

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
#
# --raw VBR-TEMPLATE: the installer's VBR template, delivered as a
# catalog-addressed BINARY block (same shape as the *-form.fth data
# blocks: found by CATALOG-FIND, read as data, never interpreted).
# This is what lets INSTALL arm VBR-TPL with zero pokes, replacing
# the 512 hand-typed C! lines that blocked the iron session.
write-catalog: $(BLOCKS) $(VBR)
	python3 tools/write-catalog.py $(BLOCKS) forth/dict/ \
	        --raw VBR-TEMPLATE=$(VBR)

# --- Combined Image ---

# Combined image: kernel + blocks concatenated
# Block N is at LBA BLOCKS_LBA_BASE + N*2, where BLOCKS_LBA_BASE =
# image size / 512 (see forth.asm COMBINED_HEADER_SIZE; currently 225).
# Depends on .catalog.stamp so vocab sources are always in the disk.
$(COMBINED): $(IMAGE) $(BUILD)/.catalog.stamp
	cat $(IMAGE) $(BLOCKS) > $(COMBINED)
	@echo "Combined image: $(COMBINED)"
	@SECT=$$(( $$(stat -c%s $(IMAGE)) / 512 )); \
	echo "  Kernel: $$(stat -c%s $(IMAGE)) bytes (LBA 0-$$((SECT - 1)))"; \
	echo "  Blocks: $$(stat -c%s $(BLOCKS)) bytes (LBA $$SECT+)"
	@echo "  Total:  $$(stat -c%s $(COMBINED)) bytes"

combined: $(COMBINED) $(COMBINED_IDE)

# usb-image — compose a complete writable ForthOS disk image (loopback file,
# not /dev/sdX) plus its .sha256 files and a releases.json fragment, per
# TASK_FORTHOS_CREATOR.md §1/§3.  Server-side only; the Creator app never
# composes.  Compose needs root (losetup/mount/grub-install); packaging does
# not.  make-uefi-usb.sh keeps the interactive /dev/sdX path and its NVMe guard.
#   make usb-image VERSION=0.9.3
usb-image: $(COMBINED)
	VERSION="$(VERSION)" bash tools/make-usb-image.sh

# check-coverage — fail if a hardware-device vocabulary (by catalog CATEGORY)
# exists in forth/dict/ but HARDWARE-COVERAGE.md does not name it. Makes the
# 2026-09-29 staleness class (shipped vocab, doc still says PLANNED) a build
# failure. Fast, offline; wired into `make test`.
check-coverage:
	@bash tools/check-coverage.sh

# desk-hashes — write the CURRENT build's trip parameters to
# build/desk-hashes.txt at desk-prep time: the two image hashes AND every
# vocabulary's catalog block range (the full layout from catalog_layout.py,
# the same parser the G6 harness and completeness gate use). Desk cards point
# at this file instead of pinning hashes or `N M THRU` ranges inline, so a
# catalog shift (CARRIER-0b, the firstboot-wizard merge, a vocab that grew)
# cannot silently invalidate a trip document: the shift moves a vocab's blocks
# and changes combined.img together, and both re-derive here. The operator
# compares the stick against the combined.img line and reads each card's
# vocab (PCI-BAR, HDAUDBUS, XHCI, ...) off its line for the THRU range.
desk-hashes: $(IMAGE) $(COMBINED) $(BLOCKS)
	@printf 'bmforth.img  %s\ncombined.img %s\n' \
	  "$$(sha256sum $(IMAGE) | cut -d' ' -f1)" \
	  "$$(sha256sum $(COMBINED) | cut -d' ' -f1)" | tee $(BUILD)/desk-hashes.txt
	@python3 tools/catalog_layout.py | tee -a $(BUILD)/desk-hashes.txt

# QEMU IDE copy: avoids file lock conflict when same data is both floppy and IDE
$(COMBINED_IDE): $(COMBINED)
	cp $(COMBINED) $(COMBINED_IDE)

# Verify kernel size hasn't exceeded KERNEL_PADDED_SIZE + boot sector (BLOCKS_LBA_BASE constraint)
# Current: KERNEL_PADDED_SIZE = 0x1C000 (114688) + 512 boot sector = 115200
check-kernel-size: $(IMAGE)
	@SIZE=$$(stat -c%s $(IMAGE)); \
	 if [ $$SIZE -gt 115200 ]; then \
	   echo "ERROR: Kernel image $$SIZE bytes exceeds 115200 limit!"; \
	   echo "  KERNEL_PADDED_SIZE must be bumped in forth.asm"; \
	   exit 1; \
	 else \
	   echo "Kernel size OK: $$SIZE bytes (limit: 115200)"; \
	 fi

# --- Test Targets ---

# Port base for tests (each test uses a different port)
# Per-worktree default so two checkouts don't share a port range and
# cross-kill each other's QEMU (docs/evidence/finding-harness-pkill-cross-worktree-2026-09-30.md).
# Derived from this worktree's path; step 200 > the +0..+100 offsets the
# recipes use, so adjacent bases never overlap. Override explicitly with
# `make ... TEST_PORT_BASE=NNNN`.
TEST_PORT_BASE ?= $(shell b=$$(printf '%s' "$(CURDIR)" | cksum | cut -d' ' -f1); echo $$(( 2200 + (b % 34) * 200 )))

# Named timeout budgets for the batch-2 recipes (TASK_HARNESS_KILL_BY_PID
# §3b): hard upper bounds in seconds, about 2x the observed recipe time
# (2026-10-03, quiet machine): smoke 34s, loops 48s, abort 95s,
# dict-bounds 114s, phys-alloc 181s, pci-typing 172s.
T_SMOKE       ?= 90
T_LOOPS       ?= 120
T_ABORT       ?= 240
T_DICT_BOUNDS ?= 240
T_PHYS_ALLOC  ?= 360
T_PCI_TYPING  ?= 360

# Run smoke test (no block storage needed)
test-smoke: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-smoke.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; set -e; \
	echo "Running smoke test..."; \
	$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp::$(TEST_PORT_BASE),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_SMOKE) python3 tests/smoke_test.py $(TEST_PORT_BASE)

# Run BEGIN/WHILE/REPEAT test (no block storage needed)
test-loops: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-loops.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; set -e; \
	echo "Running loop control flow test..."; \
	$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp::$$(($(TEST_PORT_BASE)+1)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_LOOPS) python3 tests/test_begin_while.py $$(($(TEST_PORT_BASE)+1))

# Run ABORT / ABORT" kernel gate (no block storage needed).
# ABORT" is the substrate the INSTALL allowlist binds its refusal
# to, so this is a kernel-tier gate, not a vocabulary one.
test-abort: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-abort.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; set -e; \
	echo "Running ABORT/ABORT\" kernel test..."; \
	$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp::$$(($(TEST_PORT_BASE)+2)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_ABORT) python3 tests/test_abort.py $$(($(TEST_PORT_BASE)+2))

# Dictionary bounds gate (no block storage needed). Kernel-tier:
# proves HERE cannot silently cross DICT_START+DICT_SIZE, and that
# interpret mode stays usable as the recovery hatch when it would.
test-dict-bounds: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-dict-bounds.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; set -e; \
	echo "Running dictionary bounds test..."; \
	$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp::$$(($(TEST_PORT_BASE)+97)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_DICT_BOUNDS) python3 tests/test_dict_bounds.py $$(($(TEST_PORT_BASE)+97)) $(ACTIVE_IMAGE)

# Physical allocator gate: PHYS-RELEASE/PHYS-AUDIT/owner tags.
# Boot allocations come from embedded AHCI/RTL8168/NTFS vocabs,
# so the plain kernel image suffices (no block storage).
test-phys-alloc: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-phys-alloc.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; set -e; \
	echo "Running physical allocator test..."; \
	$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp::$$(($(TEST_PORT_BASE)+98)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_PHYS_ALLOC) python3 tests/test_phys_alloc.py $$(($(TEST_PORT_BASE)+98)) $(ACTIVE_IMAGE)

# PCI class-code typing gate: PCI-PROGIF@/PCI-FIND-CLASS/
# PCI-FIND-TYPE/FIND-XHCI/PCI-TYPES (docket step 1).
# -device qemu-xhci exists to place the target hardware: class
# 0C/03/30 (1b36:000d), the exact function typed discovery must
# find; i440FX has no USB controller otherwise.  -M pc pins the
# machine type so a future QEMU default flip to q35 cannot
# silently change the bus the suite characterizes.
test-pci-typing: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-pci-typing.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; set -e; \
	echo "Running PCI class-code typing test..."; \
	$(QEMU) -M pc -device qemu-xhci \
		-drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp::$$(($(TEST_PORT_BASE)+96)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_PCI_TYPING) python3 tests/test_pci_typing.py $$(($(TEST_PORT_BASE)+96)) $(ACTIVE_IMAGE)

# Run all vocabulary tests (need block storage)
test-vocabs: $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running vocabulary tests..."
	@PORT_BASE=$$(($(TEST_PORT_BASE)+10)); \
	for test in test_editor test_x86_asm test_driver_vocabs test_disasm test_port_mapper test_echoport test_catalog_complete; do \
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
test-gui: $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@PORT_BASE=$$(($(TEST_PORT_BASE)+30)); \
	for test in test_stub_dispatch test_ui_core test_gui_harvest test_ui_parser test_ui_events test_fe_strip_cr; do \
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

# LOG-HARNESS: private licensing/telemetry infrastructure. The vocab and
# both test scripts are canonical in the private repo
# (forthos-vocabularies); without them each recipe prints SKIPPED and
# exits 0. Offsets: +45 (test-log-harness), +46/+47/+48 (-nic: serial,
# QEMU's dgram end, the test's peer).
# Named timeout budgets (see docs/TASK_HARNESS_KILL_BY_PID.md §3b):
# a hard upper bound in seconds for the test invocation. Observed
# pass times: test-log-harness ~20s, test-log-harness-nic ~25s.
T_LOG_HARNESS     ?= 60
T_LOG_HARNESS_NIC ?= 90

test-log-harness-nic: $(COMBINED)
	@for f in forth/dict/log-harness.fth tests/test_log_harness_nic.py; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-log-harness-nic: private vocab absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	PIDF=$(BUILD)/test-log-harness-nic.pid; $(QEMU_KILL); \
	PCAP=$(BUILD)/log-harness-nic.pcap; rm -f $$PCAP; \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; set -e; \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running LOG-HARNESS NIC smoke test..."; \
	$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-netdev dgram,id=u1,local.type=inet,local.host=127.0.0.1,local.port=$$(($(TEST_PORT_BASE)+47)),remote.type=inet,remote.host=127.0.0.1,remote.port=$$(($(TEST_PORT_BASE)+48)) \
		-device ne2k_pci,netdev=u1,mac=52:54:00:12:34:56 \
		-object filter-dump,id=f1,netdev=u1,file=$$PCAP \
		-serial tcp::$$(($(TEST_PORT_BASE)+46)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_LOG_HARNESS_NIC) python3 tests/test_log_harness_nic.py \
		$$(($(TEST_PORT_BASE)+46)) $$PCAP $$(($(TEST_PORT_BASE)+48))

test-log-harness: $(COMBINED)
	@for f in forth/dict/log-harness.fth tests/test_log_harness.py; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-log-harness: private vocab absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	PIDF=$(BUILD)/test-log-harness.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; set -e; \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running LOG-HARNESS smoke test..."; \
	$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp::$$(($(TEST_PORT_BASE)+45)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_LOG_HARNESS) python3 tests/test_log_harness.py \
		$$(($(TEST_PORT_BASE)+45))

# Run the INSTALL write-allowlist gate (Piece 1).
# Needs $(COMBINED): INSTALL is block-loaded off the catalog, not
# embedded, so the block store has to be attached.
test-install: $(COMBINED) $(BOOTLOADER) $(VBR)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running INSTALL allowlist test..."
	@PORT=$$(($(TEST_PORT_BASE)+3)); \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; sleep 1; \
	$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp::$$PORT,server=on,wait=off \
		-display none -daemonize; \
	sleep 2; \
	python3 tests/test_install.py $$PORT; \
	STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; exit $$STATUS

# VBR variant boot smoke (test manages its own QEMU; monitor on port+1)
test-vbr: $(VBR) $(KERNEL) $(IMAGE)
	@echo "Running VBR variant boot smoke..."
	@PORT=$$(($(TEST_PORT_BASE)+8)); \
	python3 tests/test_vbr_boot.py $$PORT; \
	STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; exit $$STATUS

# G6 chain harness: live install + 4-leg boot matrix.
# Manages its own QEMU; monitor on port+1, so this target OWNS the
# two-port bracket +95/+96 (4595/4596).
#
# ALLOCATE BY BRACKET, NOT BY OFFSET. A target that spawns a
# monitor claims PORT..PORT+n, so grepping for the literal offset
# undercounts: +90 looks free but test_meta_does brackets 90/91/92.
# There are also two axes, and both must be checked -- Makefile
# allocations AND the `else 45xx` bare-run defaults in tests/,
# which a human debugging by hand will bind. +93 was the first
# choice and is free on the first axis only: 4593 is
# test_nfbuild_diag's default and 4594 is test_cortexm_boot's.
# +95/+96 is free on both. This paragraph is a rule, not a
# promise -- the previous version of this comment asserted that
# sharing +90 with test_meta_does was "safe because they never
# run concurrently," which is a condition nothing enforces.
#
# The grub-net prerequisite is DELIBERATE, not incidental: it
# guarantees build/tftp matches the current build. build-grub-net.sh
# rm -rf's and rebuilds the tree from combined.img, so re-staging is
# deterministic rather than accumulated state; combined.img was
# measured unchanged across test-install (the disk-writing target
# that precedes this one). Dropping the dep would permit a silently
# stale tree, which fails by misattribution -- the exact shape of
# the PXE-freshness incidents this project has already paid for.
# Known gap: nothing asserts WHICH tree booted; make ordering is
# the guarantee. See the docket's carried items.
test-g6: grub-net $(VBR) $(KERNEL)
	@echo "Running G6 chain harness..."
	@PORT=$$(($(TEST_PORT_BASE)+95)); \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+1))" 2>/dev/null || true; \
	sleep 1; \
	python3 tests/test_g6_chain.py $$PORT; \
	STATUS=$$?; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+1))" 2>/dev/null || true; \
	exit $$STATUS

# Run full integration test
test-integration: $(COMBINED)
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
test-network: $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running NE2000 network test..."
	@python3 tests/test_ne2000_network.py $$(($(TEST_PORT_BASE)+40))

# --- Defeated-backstop experiment build ---
# DICT_BACKSTOP=0 via -D so the in-loop string-laydown guard can be
# observed firing (tests/test_squote_laydown.py --backstop0).  The
# override is a build flag, never a source edit: a hand-edited
# equ 0 got committed at 9ae68d5.  Distinct image name; the kernel
# banner announces the defeated backstop at boot.

BACKSTOP0_KERNEL = $(BUILD)/kernel-backstop0.bin
BACKSTOP0_IMAGE = $(BUILD)/bmforth-backstop0.img

$(BACKSTOP0_KERNEL): $(SRC_KERNEL)/forth.asm $(EMBEDDED) | $(BUILD)
	$(NASM) -f bin -DDICT_BACKSTOP=0 -o $@ $<

$(BACKSTOP0_IMAGE): $(BOOTLOADER) $(BACKSTOP0_KERNEL)
	cat $(BOOTLOADER) $(BACKSTOP0_KERNEL) > $@

backstop0: $(BACKSTOP0_IMAGE)
	@echo "Defeated-backstop image: $(BACKSTOP0_IMAGE) ($$(stat -c%s $(BACKSTOP0_IMAGE)) bytes)"

# Block-cache reload gate (Bug #34): a cache HIT must not corrupt
# the neighbouring slot's cached block.  The script stages its own
# blocks into scratch copies of $(COMBINED) and launches QEMU
# itself (it must poke the image BEFORE boot).
test-block-reload: $(COMBINED)
	@echo "Running block-cache reload test (Bug #34)..."
	@PORT=$$(($(TEST_PORT_BASE)+95)); \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; sleep 1; \
	python3 tests/test_block_reload.py $$PORT $(COMBINED); \
	STATUS=$$?; pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null; exit $$STATUS

# xHCI vocab gate (docket step 2a): BAR64-MASK + PCI-BAR64@,
# block-loaded from forth/dict/xhci.fth via catalog THRU.  Needs
# block storage (combined image) AND the target device: -M pc
# pinned + -device qemu-xhci, same rationale as test-pci-typing
# (i440FX has no USB controller otherwise; the pin stops a q35
# default flip from silently changing the characterized bus).
# Step 4 fixture (design §4, 2026-09-15): usb-kbd gets id=kbd so the
# monitor can device_del it, and the QEMU HMP monitor is exposed over
# TCP so the suite can `sendkey` (the only way to make QEMU's keyboard
# produce a report) -- the discriminating experiment, not decoration.
# Monitor port: the design named +95, but +95 is test-block-reload's
# (observed above); +93 is unused and one below the serial port.
test-xhci: $(COMBINED)
	@PIDF=$(BUILD)/test-xhci.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; set -e; \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running xHCI vocab test..."; \
	$(QEMU) -M pc -device qemu-xhci -device usb-kbd,id=kbd \
		-drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp::$$(($(TEST_PORT_BASE)+94)),server=on,wait=off \
		-monitor tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+93)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_XHCI) python3 tests/test_xhci.py $$(($(TEST_PORT_BASE)+94)) $(COMBINED) $$(($(TEST_PORT_BASE)+93))

# PCI-BAR gate, (bz) R2 (docs/evidence/bz-base-finding-prereg-2026-09-27.md):
# block-loaded pci-bar.fth, instances of a class in scan order.  TWO
# intel-hda functions, so "never chosen implicitly" meets more than one
# instance (the HP has one).  Port +87 was unused.
test-pci-bar: $(COMBINED)
	@PIDF=$(BUILD)/test-pci-bar.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; set -e; \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running PCI-BAR vocab test..."; \
	$(QEMU) -M pc -device intel-hda -device intel-hda \
		-drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp::$$(($(TEST_PORT_BASE)+87)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_PCI_BAR) python3 tests/test_pci_bar.py $$(($(TEST_PORT_BASE)+87)) $(COMBINED)

# FIRSTBOOT wizard gate, docs/TASK_FORTHOS_FIRSTBOOT.md s.8 steps 1-3:
# block-loaded firstboot.fth, screens read through the monitor
# (pmemsave 0xB8000) because the wizard loop owns KEY.  Two fixtures:
# lan (rtl8139 driven, e1000 undriven, AHCI present) and offline (no
# NIC, PIIX IDE only -- the path three of four reference machines
# take).  Ports +88/+89 and +84/+85 were unused.
# Each fixture is ONE shell: a trap kills its QEMU (by pidfile) on any
# exit, INT, TERM or HUP.  SIGKILL cannot be trapped, so each run also
# first kills a QEMU left by a killed previous run (an orphan held the
# monitor port during development, 2026-09-29).
# Per-recipe test-invocation timeouts (seconds). A hung test is killed at its
# budget so the recipe fails in BOUNDED time instead of wedging (a per-recv
# timeout is not a test timeout — see §3b of docs/TASK_HARNESS_KILL_BY_PID.md).
# The hard kill propagates through `set -e` to the trap, which kills the QEMU
# by pidfile: no orphan, no held image lock. Derive each from the recipe's
# observed pass time with headroom; tune here, one greppable place.
T_XHCI ?= 120
T_PCI_BAR ?= 90

# QEMU_KILL — shared teardown for every daemonized test recipe: kill the PID
# in this recipe's pidfile (never a name pattern, which reaches other trees
# and other sessions — finding-harness-pkill-cross-worktree). Used via a trap
# so it fires on normal exit and on INT/TERM/HUP, plus once before launch to
# pre-clean a pidfile left by a SIGKILL'd previous run (SIGKILL can't be
# trapped). A stale pidfile names a dead PID that may since have been reused
# by an unrelated process, so the PID is killed only if it is a $(QEMU) that
# holds this tree's pidfile open (QEMU keeps it open and locked while alive;
# /proc/PID/fd shows the absolute path, which is unique per tree). Must stay
# free of single quotes: it is expanded inside trap '...'.
# Known refusals (not fixed): the guard then deletes the pidfile but leaves a
# real QEMU running, (1) when $(QEMU) resolves through a symlink, so
# `command -v` and /proc/PID/exe name different paths, and (2) when $(BUILD)
# is an absolute path, so "$(CURDIR)/$$PIDF" is not the path QEMU holds open.
# See docs/TASK_HARNESS_KILL_BY_PID.md.
QEMU_KILL = if [ -f $$PIDF ]; then QPID=$$(cat $$PIDF); \
	if [ "$$(readlink /proc/$$QPID/exe)" = "$$(command -v $(QEMU))" ] && \
	   readlink /proc/$$QPID/fd/* 2>/dev/null | grep -qxF "$(CURDIR)/$$PIDF"; \
	then kill -9 $$QPID 2>/dev/null; fi; rm -f $$PIDF; fi
test-firstboot: $(COMBINED)
	@PIDF=$(BUILD)/firstboot-lan.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running FIRSTBOOT wizard test (lan)..."; \
	$(QEMU) -M pc -nic none -device rtl8139 -device e1000 \
		-device ahci,id=ahci0 \
		-drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp::$$(($(TEST_PORT_BASE)+88)),server=on,wait=off \
		-monitor tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+89)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF || exit 1; \
	sleep 2; \
	python3 tests/test_firstboot.py $$(($(TEST_PORT_BASE)+88)) $(COMBINED) \
		$$(($(TEST_PORT_BASE)+89)) lan $(COMBINED_IDE)
	@PIDF=$(BUILD)/firstboot-offline.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP; \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running FIRSTBOOT wizard test (offline)..."; \
	$(QEMU) -M pc -nic none \
		-drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp::$$(($(TEST_PORT_BASE)+84)),server=on,wait=off \
		-monitor tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+85)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF || exit 1; \
	sleep 2; \
	python3 tests/test_firstboot.py $$(($(TEST_PORT_BASE)+84)) $(COMBINED) \
		$$(($(TEST_PORT_BASE)+85)) offline $(COMBINED_IDE)

# S"/."/ABORT" laydown suite (crafts blocks in buffer memory; no
# block storage image needed, same tier as test-dict-bounds).
test-squote-laydown: $(ACTIVE_IMAGE)
	@echo "Running S\"-laydown test..."
	@$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp::$$(($(TEST_PORT_BASE)+98)),server=on,wait=off \
		-display none -daemonize
	@sleep 2
	@python3 tests/test_squote_laydown.py $$(($(TEST_PORT_BASE)+98)) $(ACTIVE_IMAGE); \
		STATUS=$$?; pkill -9 -f "[q]emu.*$$(($(TEST_PORT_BASE)+98))" 2>/dev/null; exit $$STATUS

# Same suite against the defeated-backstop image: observes the
# in-loop DICT_LIMIT guard firing (unreachable in normal builds).
test-squote-laydown-backstop0: $(BACKSTOP0_IMAGE)
	@echo "Running S\"-laydown --backstop0 test..."
	@$(QEMU) -drive file=$(BACKSTOP0_IMAGE),format=raw,if=floppy \
		-serial tcp::$$(($(TEST_PORT_BASE)+99)),server=on,wait=off \
		-display none -daemonize
	@sleep 2
	@python3 tests/test_squote_laydown.py $$(($(TEST_PORT_BASE)+99)) $(BACKSTOP0_IMAGE) --backstop0; \
		STATUS=$$?; pkill -9 -f "[q]emu.*$$(($(TEST_PORT_BASE)+99))" 2>/dev/null; exit $$STATUS

# --- Debug flush targets ---

DEBUG_KERNEL = $(BUILD)/kernel-debug.bin
DEBUG_IMAGE = $(BUILD)/bmforth-debug.img

$(DEBUG_KERNEL): $(SRC_KERNEL)/forth.asm | $(BUILD)
	$(NASM) -f bin -DDEBUG_FLUSH -o $@ $<

$(DEBUG_IMAGE): $(BOOTLOADER) $(DEBUG_KERNEL)
	cat $(BOOTLOADER) $(DEBUG_KERNEL) > $@

DEBUG_COMBINED = $(BUILD)/combined-debug.img
DEBUG_COMBINED_IDE = $(BUILD)/combined-debug-ide.img

test-flush: $(DEBUG_IMAGE) $(BUILD)/.catalog.stamp
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
test-arm64-boot: $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running ARM64 boot test..."
	@python3 tests/test_arm64_boot.py $$(($(TEST_PORT_BASE)+50)); \
		STATUS=$$?; \
		pkill -9 -f "[q]emu.*$$(($(TEST_PORT_BASE)+50))" 2>/dev/null; \
		pkill -9 -f "[q]emu.*$$(($(TEST_PORT_BASE)+52))" 2>/dev/null; \
		exit $$STATUS

# Run Cortex-M33 boot test (cross-compile + QEMU mps2-an505)
test-cortexm: $(COMBINED)
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

test-ahci-write: $(COMBINED) $(AHCI_SCRATCH)
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

# UBT translator's own suite (24 binaries, ~300 checks, ~12 s).  Not
# in `test:` -- its output grammar (`TEST: name PASS`) is not the
# sweep's (`PASS: name`), and the headline is one grammar counted once
# from one log.  Nightly target; the schedule is HELD until the PE32+
# path has a red for the offset-00 case (see test_make_wiring.py).
# tools/translator/ is gitignored here and tracked in
# forthos-vocabularies: a public clone names this capability but does
# not ship it, and says so instead of failing on a missing directory.
test-translator:
	@test -f tools/translator/Makefile || { \
		echo "test-translator: tools/translator/Makefile not present."; \
		echo "  The UBT translator suite lives in the private forthos-vocabularies tree"; \
		echo "  (tools/translator/ is gitignored in this repo). This is not a broken checkout;"; \
		echo "  check out forthos-vocabularies alongside and copy or link tools/translator/ here."; \
		exit 3; }
	@echo "Running UBT translator test suite..."
	@$(MAKE) -C tools/translator test

# Offline GRUB cfg gates: drift, converter pin, scan fatality
# UEFI-2 red (docs/evidence/uefi-2-prereg-2026-09-28.md): at `ok`, QEMU's
# `info registers` must show the GDT inside the kernel image, CS=0x08,
# DS/ES/SS=0x10.  Floppy bmforth.img + IDE combined.img (amendment e).
test-uefi2-gdt: $(IMAGE) $(COMBINED)
	@echo "Running UEFI-2 own-GDT red..."
	@python3 tests/test_uefi2_gdt.py $(IMAGE) $(COMBINED) $$(($(TEST_PORT_BASE)+77)) $$(($(TEST_PORT_BASE)+78))

# CARRIER-0b host-safety gate (carrier-0b-write-vector-2026-09-29.md): a cell-0
# boot must NOT write blocks to a fixed disk by default. Floppy (cell-0) + a
# scratch IDE disk with a sentinel; a SAVE-BUFFERS must leave it intact.
test-carrier-write-safe: $(IMAGE)
	@echo "Running CARRIER-0b write-safety gate..."
	@python3 tests/test_carrier_write_safe.py $$(($(TEST_PORT_BASE)+79))

# M1 of the UEFI stages (uefi-1-prereg-2026-09-28.md): the HP's BIOS boot
# chain in QEMU -- pxelinux -> memdisk -> combined.img -- reaches ok,
# reads blocks from RAM and refuses writes loudly (M4b, bc06026).  It
# was never wired and no reason was recorded; ~2 min.  Port 4483 is its
# own; it prints SKIP and exits 0 if pxelinux/memdisk are not installed.
test-memdisk: $(COMBINED)
	@echo "Running memdisk boot test (pxelinux -> memdisk)..."
	@python3 tests/test_memdisk_blk_writer.py

# UEFI-1 red (docs/evidence/uefi-1-prereg-2026-09-28.md): a rootless replica
# of the make-uefi-usb.sh stick booted under OVMF (no CSM) must reach the
# Forth banner + ok on serial.  Registered red: prints XFAIL and exits 0
# until UEFI-3; XPASS exits 1.  Serial goes to a file, no TCP port.
test-uefi-boot: $(COMBINED)
	@echo "Running UEFI boot red (OVMF, no CSM)..."
	@python3 tests/test_uefi_boot.py $(COMBINED)

test-grub-cfg:
	@echo "Running GRUB cfg gates..."
	@python3 tests/test_grub_cfg.py

# Doc drift gate: docs someone types from must match their artifact
test-doc-drift:
	@echo "Running doc drift gates..."
	@python3 tests/test_doc_drift.py

# Makefile wiring gate: every test-* target wired into test: or
# exempted with a true reason (two orphans + one silently-broken
# suite earned this; see tests/test_make_wiring.py docstring)
test-make-wiring:
	@echo "Running Makefile wiring gate..."
	@python3 tests/test_make_wiring.py

# UBT LLM validation (single-binary, requires NVIDIA_API_KEY)
# The driver corpus is read from CORPUS_ROOT and never copied into this repo.
CORPUS_ROOT ?= $(HOME)/corpus
ubt-llm-validate:
	@echo "Running UBT LLM validation on i8042prt.sys..."
	@cd tools/ubt-llm && python3 ubt_llm_validate.py \
		--binary $(CORPUS_ROOT)/hp_i3/i8042prt.sys

ubt-llm-validate-prefilter:
	@echo "Running UBT LLM validation with prefilter on i8042prt.sys..."
	@cd tools/ubt-llm && python3 ubt_llm_validate.py \
		--binary $(CORPUS_ROOT)/hp_i3/i8042prt.sys --prefilter

test-file-stream: $(IMAGE)
	@PORT=$$(($(TEST_PORT_BASE)+55)); \
	echo "=== FILE-STREAM helpers (port $$PORT) ==="; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	sleep 0.5; \
	qemu-system-i386 \
		-drive file=build/bmforth.img,format=raw,if=floppy \
		-serial tcp::$$PORT,server=on,wait=off \
		-display none -daemonize; \
	sleep 2; \
	python3 tests/test_file_stream_helpers.py $$PORT; \
	RESULT=$$?; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	exit $$RESULT

# DISK-SURVEY placement gate: adversarial GPT layouts.
# The test authors each disk with sgdisk and launches its
# own QEMU per layout, so no QEMU is started here.
# Skipped when surveyor.fth is absent (paid tier) or when
# sgdisk is unavailable.
# The $(COMBINED) prerequisite is only demandable on the full
# tier: on the free tier surveyor.fth does not exist, so make
# would fail resolving embedded.bin before the skip guard below
# ever gets to run.
ifeq ($(BUILD_TIER),full)
SURVEY_DEPS = $(COMBINED)
else
SURVEY_DEPS =
endif

test-survey: $(SURVEY_DEPS)
	@REASON=""; \
	if [ ! -f forth/dict/surveyor.fth ]; then \
		REASON="surveyor.fth absent (paid tier)"; \
	elif ! command -v sgdisk >/dev/null 2>&1; then \
		REASON="sgdisk not installed"; \
	fi; \
	if [ -n "$$REASON" ]; then \
		echo "########################################"; \
		echo "## NOT RUN: DISK-SURVEY placement gate"; \
		echo "## reason: $$REASON"; \
		echo "## No survey coverage in this run."; \
		echo "## A green build here does NOT mean the"; \
		echo "## survey was tested."; \
		echo "########################################"; \
		exit 0; \
	fi; \
	PORT=$$(($(TEST_PORT_BASE)+100)); \
	echo "=== DISK-SURVEY layouts (ports $$PORT-$$((PORT+5))) ==="; \
	python3 tests/test_survey_layouts.py $$PORT

# Run metacompiler tests (5 files, x86 self-hosting verification)
# NOT included in 'make test' — slow, boots multiple QEMU instances.
test-meta: $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running metacompiler tests..."
	@set -e; \
	PORT=$$(($(TEST_PORT_BASE)+80)); \
	echo "  test_metacompiler (port $$PORT)..."; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	sleep 0.5; \
	$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp::$$PORT,server=on,wait=off \
		-display none -daemonize; \
	sleep 2; \
	python3 tests/test_metacompiler.py $$PORT; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; sleep 1; \
	PORT=$$(($(TEST_PORT_BASE)+81)); \
	echo "  test_meta_compile (port $$PORT)..."; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	sleep 0.5; \
	python3 tests/test_meta_compile.py $$PORT; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; sleep 1; \
	PORT=$$(($(TEST_PORT_BASE)+82)); \
	echo "  test_meta_b6 (port $$PORT)..."; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	sleep 0.5; \
	python3 tests/test_meta_b6.py $$PORT; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; sleep 1; \
	PORT=$$(($(TEST_PORT_BASE)+83)); \
	echo "  test_meta_boot (port $$PORT)..."; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+1))" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+2))" 2>/dev/null || true; \
	sleep 0.5; \
	python3 tests/test_meta_boot.py $$PORT; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+1))" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+2))" 2>/dev/null || true; \
	sleep 1; \
	PORT=$$(($(TEST_PORT_BASE)+86)); \
	echo "  test_meta_b6b (port $$PORT)..."; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+1))" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+2))" 2>/dev/null || true; \
	sleep 0.5; \
	python3 tests/test_meta_b6b.py $$PORT; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+1))" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+2))" 2>/dev/null || true; \
	sleep 1; \
	PORT=$$(($(TEST_PORT_BASE)+90)); \
	echo "  test_meta_does (port $$PORT)..."; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+1))" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+2))" 2>/dev/null || true; \
	sleep 0.5; \
	python3 tests/test_meta_does.py $$PORT; \
	pkill -9 -f "[q]emu.*$$PORT" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+1))" 2>/dev/null || true; \
	pkill -9 -f "[q]emu.*$$((PORT+2))" 2>/dev/null || true
	@echo "Metacompiler tests complete!"

# Run all tests (lint first, then functional tests)
# Reachability audit 2026-09-21 (docs/evidence/make-target-reachability-2026-09-21.md):
# test-translator was NOT in this list.  The UBT suite -- 25 suites, 115
# tests -- was invisible from the project's own test entry point while
# passing whenever it was invoked by hand.  Wired in by owner ruling.
# test-pipeline and check-sync were owed the same way and are wired with it.
#
# EXEMPT from this list, with reasons (same document):
#   QEMU trips (test-network, test-arm64-boot, test-cortexm, test-meta,
#     test-flush, test-ahci-write, test-squote-laydown-backstop0, run*) --
#     emulator trips, and QEMU is not a truth source.  test-network is
#     separately DEAD-PENDING-REPAIR, broken since 2026-08-30.
#   Outward-facing or destructive (pxe-*, write-block, write-catalog, iso,
#     combined, backstop0, blocks, free) -- these write boot media or push
#     to a network host and must never run automatically.
#   ubt-llm-validate, ubt-llm-validate-prefilter -- ADVISORY TOOLS, not
#     checks (owner ruling 2026-09-21).  A suite must be deterministic and
#     offline; a model adds network and cost to the class Ghidra was already
#     exempted from.  Its output carries no denominator and cannot be
#     re-taken, where every instrument here prints what it examined and
#     returns the same answer twice.  And it is the thirty-second rule's
#     family: where one side does not decide the same way twice, agreement
#     cannot be told from coincidence.  It runs on demand, a person reads
#     its output as evidence, and it never gates a build.  If it must ever
#     gate something, the gate goes on a deterministic artefact derived from
#     it and pinned -- the treatment the Ghidra oracle already has.
test: lint check-coverage test-smoke test-loops test-abort test-dict-bounds test-phys-alloc test-pci-typing test-xhci test-pci-bar test-firstboot test-block-reload test-squote-laydown test-install test-log-harness test-log-harness-nic test-vbr test-grub-cfg test-uefi-boot test-uefi2-gdt test-carrier-write-safe test-memdisk test-doc-drift test-make-wiring test-g6 test-vocabs test-gui test-integration test-file-stream test-survey test-translator test-pipeline check-sync
	@echo "All tests passed!"

# Create ISO (requires xorriso)
iso: $(ACTIVE_IMAGE)
	mkdir -p $(BUILD)/iso
	cp $(ACTIVE_IMAGE) $(BUILD)/iso/bmforth.img
	xorriso -as mkisofs -b bmforth.img -no-emul-boot -o $(BUILD)/bmforth.iso $(BUILD)/iso/

# Check syntax only (no output)
check: lint
	$(NASM) -f bin -o /dev/null $(SRC_BOOT)/boot.asm
	$(NASM) -f bin -o /dev/null $(SRC_BOOT)/vbr.asm
	$(NASM) -f bin -o /dev/null $(SRC_KERNEL)/forth.asm
	@echo "Syntax check passed."

# NTFS test image (lives outside build/ to survive make clean)
$(NTFS_TEST): tools/make-ntfs-test-image.sh
	mkdir -p test-data
	sudo bash $< $@
	sudo chown $$USER $@

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
	@echo "  free           - Build free-tier image (public vocabs only)"
	@echo "  run-free       - Run free-tier image in QEMU (text mode)"
	@echo "  check-sync     - Verify paid files match private repo"
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

# Stage the GRUB-PXE netboot tree (side-by-side with pxelinux)
grub-net: $(COMBINED) tools/pxe/grub.cfg
	@bash tools/pxe/build-grub-net.sh

# Push staged GRUB tree to /srv/tftp (side-by-side; no cutover)
pxe-push-grub: grub-net
	@bash tools/pxe/push-grub.sh

.PHONY: all run run-gui run-serial debug check clean help iso blocks run-blocks run-blocks-gui write-block write-catalog combined usb-image check-coverage desk-hashes check-kernel-size test test-smoke test-loops test-vocabs test-gui test-integration test-flush test-network test-ahci-write test-file-stream test-log-harness test-log-harness-nic pxe-setup pxe-push pxe-status grub-net pxe-push-grub free run-free check-sync test-grub-cfg test-g6
