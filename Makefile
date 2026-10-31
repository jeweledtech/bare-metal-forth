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
# The demo apps (hello, notepad, file browser) are block-loaded, not
# embedded (TASK_KERNEL_PAD_MOVE): S" NOTEPAD" LOAD-VOCAB etc. first.
EMBED_VOCABS = forth/dict/hardware.fth forth/dict/hal.fth forth/dict/port-mapper.fth forth/dict/echoport.fth forth/dict/pci-enum.fth forth/dict/catalog-resolver.fth forth/dict/ahci.fth forth/dict/rtl8168.fth forth/dict/ntfs.fth forth/dict/auto-detect.fth forth/dict/fat32.fth forth/dict/ui-core.fth forth/dict/ui-parser.fth forth/dict/ui-events.fth forth/dict/gui-harvest.fth forth/dict/ps2-keyboard.fth forth/dict/file-editor-core.fth forth/dict/file-editor-disk.fth forth/dict/file-stream.fth
EMBEDDED = $(BUILD)/embedded.bin

# Free-tier vocabularies (public-tracked only, no paid/gitignored content)
# Excludes: file-editor-disk (NTFS/AHCI), file-stream (NTFS/AHCI/RTL8168),
#   file-browser (NTFS). NOTEPAD works RAM-only via file-editor-core vectors.
EMBED_VOCABS_FREE = forth/dict/hardware.fth forth/dict/hal.fth forth/dict/port-mapper.fth forth/dict/echoport.fth \
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
.PHONY: print-embed-vocabs test-port-inventory test-kill-traps FORCE
FORCE:
print-embed-vocabs:
	@echo $(EMBED_VOCABS)

# The list itself is a prerequisite: removing a file from EMBED_VOCABS
# changes no remaining file's timestamp, so without this stamp the old
# stream (and kernel) silently stayed. Rewritten only when the list changes.
$(BUILD)/embed-vocabs.list: FORCE | $(BUILD)
	@echo "$(EMBED_VOCABS)" | cmp -s - $@ || echo "$(EMBED_VOCABS)" > $@

$(EMBEDDED): $(EMBED_VOCABS) tools/embed-vocabs.py $(BUILD)/embed-vocabs.list | $(BUILD)
	python3 tools/embed-vocabs.py $@ $(EMBED_VOCABS)

# Assemble kernel (depends on embedded vocab binary)
$(KERNEL): $(SRC_KERNEL)/forth.asm $(EMBEDDED) tools/pad_report.py | $(BUILD)
	$(NASM) -f bin -o $@ $<
	@python3 tools/pad_report.py $< $(BUILD)/pad-report.d

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
	@# Boot-log gate (TASK_INTERPRETER_CORRECTNESS): an undefined word in the
	@# embedded boot stream fails the build; the image is removed, not kept.
	@python3 tools/boot_gate.py $@ || { rm -f $@; exit 1; }

# --- Free-tier build (public vocabularies only) ---

$(BUILD)/embed-vocabs-free.list: FORCE | $(BUILD)
	@echo "$(EMBED_VOCABS_FREE)" | cmp -s - $@ || echo "$(EMBED_VOCABS_FREE)" > $@

$(EMBEDDED_FREE): $(EMBED_VOCABS_FREE) tools/embed-vocabs.py $(BUILD)/embed-vocabs-free.list | $(BUILD)
	python3 tools/embed-vocabs.py $@ $(EMBED_VOCABS_FREE)

$(KERNEL_FREE): $(SRC_KERNEL)/forth.asm $(EMBEDDED_FREE) | $(BUILD)
	$(NASM) -f bin -dEMBED_FILE='"build/embedded-free.bin"' -o $@ $<

$(IMAGE_FREE): $(BOOTLOADER) $(KERNEL_FREE)
	@echo "Creating free-tier disk image..."
	cat $(BOOTLOADER) $(KERNEL_FREE) > $@
	@echo "Free-tier image: $@ ($$(stat -c%s $@) bytes)"
	@python3 tools/boot_gate.py $@ || { rm -f $@; exit 1; }

free: $(IMAGE_FREE)

run-free: $(IMAGE_FREE)
	$(QEMU) -drive file=$(IMAGE_FREE),format=raw,if=floppy -nographic

# --- Sync check (paid files vs private repo) ---
# Compares, against the private repo:
#   - forth/dict/<v>.fth for each v in PAID_VOCABS (when present locally);
#   - every tests/*.py the private repo tracks, when present locally
#     (DIVERGED). A script tracked here too is public-owned: reported as
#     SHARED and not compared;
#   - every tests/*.py this repo ignores and that is on disk must be tracked
#     in the private repo (MISSING), so a private-only script cannot live
#     in one working tree alone;
#   - every file the private repo tracks that is on disk here and not
#     tracked here must be ignored here (LEAK RISK), so one `git add`
#     cannot publish it. Files tracked in both repos are not checked here.
# With no private repo it prints SKIPPED and exits 0; never a silent pass.
PRIVATE_REPO ?= ../forthos-vocabularies
PAID_VOCABS = ahci rtl8168 ntfs auto-detect fat32 surveyor file-editor-disk log-harness cd-atapi hal-machines atapi-ahci

check-sync:
	@if [ ! -d "$(PRIVATE_REPO)/forth/dict" ]; then \
		echo "SKIPPED: private repo not found at $(PRIVATE_REPO)"; \
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
	for f in $$(git -C "$(PRIVATE_REPO)" ls-files -- 'tests/*.py' | grep -E '^tests/[^/]+\.py$$'); do \
		if git ls-files --error-unmatch -- "$$f" >/dev/null 2>&1; then \
			echo "SHARED (tracked in both repos; public-owned, not compared): $$f"; \
			continue; \
		fi; \
		if [ ! -f "$$f" ]; then continue; fi; \
		if ! cmp -s "$$f" "$(PRIVATE_REPO)/$$f"; then \
			echo "DIVERGED: $$f"; FAIL=1; \
		fi; \
	done; \
	for f in $$(git ls-files --others --ignored --exclude-standard -- 'tests/*.py' | grep -E '^tests/[^/]+\.py$$'); do \
		if ! git -C "$(PRIVATE_REPO)" ls-files --error-unmatch -- "$$f" >/dev/null 2>&1; then \
			echo "MISSING in private repo: $$f"; FAIL=1; \
		fi; \
	done; \
	LEAK=$$(git -C "$(PRIVATE_REPO)" ls-files | while IFS= read -r f; do \
		[ -e "$$f" ] || continue; \
		git ls-files --error-unmatch -- "$$f" >/dev/null 2>&1 && continue; \
		git check-ignore -q -- "$$f" || echo "$$f"; \
	done); \
	if [ -n "$$LEAK" ]; then \
		printf '%s\n' "$$LEAK" | sed 's/^/LEAK RISK (tracked in private, on disk here, not ignored here): /'; \
		FAIL=1; \
	fi; \
	if [ $$FAIL -ne 0 ]; then \
		echo "check-sync FAILED: paid files diverged, missing, or at leak risk"; \
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

# Create blank 2.5MB blocks disk (2560 x 1K blocks): code store above the
# 320-block MIRROR reservation (216-535) ends past block 2048
BLOCKS_COUNT = 2560
$(BLOCKS): | $(BUILD)
	dd if=/dev/zero of=$(BLOCKS) bs=1024 count=$(BLOCKS_COUNT)
	@echo "Block disk created: $(BLOCKS) (2.5MB, $(BLOCKS_COUNT) blocks)"
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
$(BUILD)/.catalog.stamp: $(BLOCKS) $(VOCAB_SOURCES) tools/write-catalog.py tools/make_font_blocks.py $(VBR)
	@echo "Populating catalog into $(BLOCKS)..."
	@# Zeroed first, every time: write-catalog writes only the blocks it
	@# places, so a reused image kept old source in reserved ranges and its
	@# old size; the image now depends on the sources, not on build history.
	dd if=/dev/zero of=$(BLOCKS) bs=1024 count=$(BLOCKS_COUNT) 2>/dev/null
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
# with prompt-terminated reads (2026-10-12, docs/TASK_BOUNDED_READS_4D.md):
# smoke 11s, loops 17s, abort 22s, dict-bounds 24s, phys-alloc 31s,
# pci-typing 30s (were 34, 48, 95, 114, 181, 172s).
T_SMOKE       ?= 25
T_LOOPS       ?= 35
T_ABORT       ?= 45
T_DICT_BOUNDS ?= 50
T_PHYS_ALLOC  ?= 60
T_PCI_TYPING  ?= 60
# Batch 2b, about 2x observed (2026-10-03): squote-laydown 567s,
# backstop0 219s, flush 151s; file-stream 28s and integration 21s
# (2026-10-12, prompt-terminated reads; were 161s and 90s).
T_SQUOTE_LAYDOWN   ?= 1200
T_SQUOTE_BACKSTOP0 ?= 480
T_FLUSH            ?= 360
T_FILE_STREAM      ?= 60
T_INTEGRATION      ?= 45

# Run smoke test (no block storage needed)
test-smoke: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-smoke.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-smoke --base $(TEST_PORT_BASE); \
	echo "Running smoke test..."; \
	$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp:127.0.0.1:$(TEST_PORT_BASE),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_SMOKE) python3 tests/smoke_test.py $(TEST_PORT_BASE)

# Run BEGIN/WHILE/REPEAT test (no block storage needed)
test-loops: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-loops.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-loops --base $(TEST_PORT_BASE); \
	echo "Running loop control flow test..."; \
	$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+1)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_LOOPS) python3 tests/test_begin_while.py $$(($(TEST_PORT_BASE)+1))

# Run ABORT / ABORT" kernel gate (no block storage needed).
# ABORT" is the substrate the INSTALL allowlist binds its refusal
# to, so this is a kernel-tier gate, not a vocabulary one.
test-abort: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-abort.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-abort --base $(TEST_PORT_BASE); \
	echo "Running ABORT/ABORT\" kernel test..."; \
	$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+2)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_ABORT) python3 tests/test_abort.py $$(($(TEST_PORT_BASE)+2))

# Dictionary bounds gate (no block storage needed). Kernel-tier:
# proves HERE cannot silently cross DICT_START+DICT_SIZE, and that
# interpret mode stays usable as the recovery hatch when it would.
test-dict-bounds: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-dict-bounds.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-dict-bounds --base $(TEST_PORT_BASE); \
	echo "Running dictionary bounds test..."; \
	$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+97)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_DICT_BOUNDS) python3 tests/test_dict_bounds.py $$(($(TEST_PORT_BASE)+97)) $(ACTIVE_IMAGE)

# Physical allocator gate: PHYS-RELEASE/PHYS-AUDIT/owner tags.
# Boot allocations come from embedded AHCI/RTL8168/NTFS vocabs,
# so the plain kernel image suffices (no block storage).
test-phys-alloc: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-phys-alloc.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-phys-alloc --base $(TEST_PORT_BASE); \
	echo "Running physical allocator test..."; \
	$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+98)),server=on,wait=off \
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
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-pci-typing --base $(TEST_PORT_BASE); \
	echo "Running PCI class-code typing test..."; \
	$(QEMU) -M pc -device qemu-xhci \
		-drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+96)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_PCI_TYPING) python3 tests/test_pci_typing.py $$(($(TEST_PORT_BASE)+96)) $(ACTIVE_IMAGE)

# Run all vocabulary tests (need block storage)
# Loop recipes (batch 2c): one pidfile per fixture,
# $(BUILD)/<target>-<fixture>.pid (TASK_HARNESS_KILL_BY_PID §3a). The
# pre-clean and the trap walk the full *_ALL list, so a leftover from
# any fixture is cleared whichever fixtures the next run selects.
# *_TESTS may be overridden to run a subset; a fixture keeps its port.
VOCAB_TESTS_ALL = test_editor test_x86_asm test_driver_vocabs test_disasm test_port_mapper test_echoport test_catalog_complete
VOCAB_TESTS ?= $(VOCAB_TESTS_ALL)
VOCABS_KILL_ALL = for f in $(VOCAB_TESTS_ALL); do PIDF=$(BUILD)/test-vocabs-$$f.pid; $(QEMU_KILL); done
GUI_TESTS_ALL = test_stub_dispatch test_ui_core test_gui_harvest test_ui_parser test_ui_events test_fe_strip_cr
GUI_TESTS ?= $(GUI_TESTS_ALL)
GUI_KILL_ALL = for f in $(GUI_TESTS_ALL); do PIDF=$(BUILD)/test-gui-$$f.pid; $(QEMU_KILL); done
T_VOCAB_FIXTURE ?= 480
T_GUI_FIXTURE   ?= 300
T_INSTALL       ?= 4200
T_METACOMPILER  ?= 600
# test-meta fixtures 2-6 (scripts start their own QEMUs, pidfiles in
# $(BUILD)/test-meta.d). About 2x the slowest fixture, measured 2026-10-04:
# compile 171s, b6 334s, boot 672s, b6b 220s, does 241s
# (fixture 1, metacompiler: 248s).
T_META_FIXTURE  ?= 1400
# test-meta fixtures: name:port-offset. Fixture 1 (test_metacompiler) is
# started by the recipe; fixtures 2-6 start their own QEMUs. All pidfiles go
# in $(BUILD)/test-meta.d, swept at start, after each fixture, and by the
# trap. META_FIXTURES may name a subset; a fixture keeps its port.
META_FIXTURES_ALL = test_metacompiler:80 test_meta_compile:81 test_meta_b6:82 \
                    test_meta_boot:83 test_meta_b6b:86 test_meta_does:90
META_FIXTURES ?= test_metacompiler test_meta_compile test_meta_b6 \
                 test_meta_boot test_meta_b6b test_meta_does

# MIRROR gate (TASK_MIRROR_FIX): refusals naming every overlap, honest
# failure, readback through the persistent reader, LOOKINGGLASS after a
# reboot, on scratch copies with the ATA writer and on the HP-549 fixture
# with AHCI-RW (SKIPPED without ahci.fth).  It launches its own QEMUs (two
# configurations and a reboot), so it is its own recipe; test-vocabs
# depends on it.
# Interpreter correctness (TASK_INTERPRETER_CORRECTNESS): an undefined
# word aborts and discards the rest of its input, an aborted load rolls
# back, `(` over serial, interpret-mode `."` and `.(`, and the boot stream's
# loud message. Fixture image and a control kernel under build/test-interp.d;
# the script launches QEMU itself.
# Kernel-pad move (TASK_KERNEL_PAD_MOVE): hello, notepad and the file
# browser are block-loaded; each loads and builds its form; an installed
# instance (no memdisk, AHCI) loads nothing from blocks. The script
# launches QEMU itself; the installed case needs ahci.fth (SKIPPED without).
# HAL slice 1 (docs/TASK_HAL_DISPLAY.md): the binding mechanism and the
# display contract on the BIOS image; serial on +4 (unused before).
test-hal: $(COMBINED)
	@QPIDDIR=$(BUILD)/test-hal.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-hal --base $(TEST_PORT_BASE); \
	echo "Running HAL binding test..."; \
	PORT=$$(($(TEST_PORT_BASE)+4)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_HAL) python3 tests/test_hal.py $$PORT

# HAL NET-SEND contract (docs/TASK_HAL_NET_SEND.md): ne2k_pci binds it,
# no NIC leaves it unbound. Serial on +12, the dgram netdev on +13/+14
# (unused before).
test-hal-net: $(COMBINED)
	@QPIDDIR=$(BUILD)/test-hal-net.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-hal-net --base $(TEST_PORT_BASE); \
	echo "Running HAL NET-SEND test..."; \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_HAL_NET) python3 tests/test_hal_net.py \
		$$(($(TEST_PORT_BASE)+12)) $$(($(TEST_PORT_BASE)+13)) $$(($(TEST_PORT_BASE)+14))

# Per-machine bindings (docs/TASK_HAL_MACHINE.md): HAL-MATCH binds from
# SMBIOS, QEMU told made-up strings (a match, then none); serial on +5.
test-hal-match: $(COMBINED)
	@QPIDDIR=$(BUILD)/test-hal-match.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-hal-match --base $(TEST_PORT_BASE); \
	echo "Running HAL-MATCH test..."; \
	PORT=$$(($(TEST_PORT_BASE)+5)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_HAL_MATCH) python3 tests/test_hal_match.py $$PORT

# The private machine entries, dry-run (forthos-vocabularies); SKIPPED
# without them. Serial on +6.
test-hal-match-hp: $(COMBINED)
	@for f in forth/dict/hal-machines.fth tests/test_hal_match_hp.py; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-hal-match-hp: private machine entries absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	QPIDDIR=$(BUILD)/test-hal-match-hp.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-hal-match-hp --base $(TEST_PORT_BASE); \
	PORT=$$(($(TEST_PORT_BASE)+6)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_HAL_MATCH_HP) python3 tests/test_hal_match_hp.py $$PORT

test-pad-move: $(COMBINED)
	@QPIDDIR=$(BUILD)/test-pad-move.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-pad-move --base $(TEST_PORT_BASE); \
	echo "Running kernel-pad move test..."; \
	PORT=$$(($(TEST_PORT_BASE)+69)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_PAD_MOVE) python3 tests/test_pad_move.py $$PORT

test-interp-abort: $(COMBINED)
	@QPIDDIR=$(BUILD)/test-interp.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-interp-abort --base $(TEST_PORT_BASE); \
	echo "Running interpreter-correctness test..."; \
	PORT=$$(($(TEST_PORT_BASE)+68)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_INTERP_ABORT) python3 tests/test_interp_abort.py $$PORT

test-mirror: $(COMBINED)
	@QPIDDIR=$(BUILD)/test-mirror.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-mirror --base $(TEST_PORT_BASE); \
	echo "Running MIRROR test..."; \
	PORT=$$(($(TEST_PORT_BASE)+67)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_MIRROR) python3 tests/test_mirror.py $$PORT $(COMBINED)

test-vocabs: $(COMBINED) test-mirror
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running vocabulary tests..."
	@$(VOCABS_KILL_ALL); \
	trap '$(VOCABS_KILL_ALL)' EXIT INT TERM HUP PIPE; set -e; \
	for test in $(VOCAB_TESTS); do \
		I=0; for a in $(VOCAB_TESTS_ALL); do [ $$a = $$test ] && break; I=$$((I+1)); done; \
		PORT=$$(($(TEST_PORT_BASE)+10+I)); \
		$(PORTS_FREE) --recipe test-vocabs --fixture $$test --base $(TEST_PORT_BASE); \
		PIDF=$(BUILD)/test-vocabs-$$test.pid; \
		echo "  $$test (port $$PORT)..."; \
		$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
			-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
			-nic model=ne2k_pci \
			-serial tcp:127.0.0.1:$$PORT,server=on,wait=off \
			-display none -daemonize -pidfile $$PIDF; \
		sleep 2; \
		timeout --foreground $(T_VOCAB_FIXTURE) python3 tests/$$test.py $$PORT; \
		$(QEMU_KILL); \
	done

# Run GUI vocabulary tests (paid tier — skipped if files absent)
test-gui: $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@$(GUI_KILL_ALL); \
	trap '$(GUI_KILL_ALL)' EXIT INT TERM HUP PIPE; set -e; \
	for test in $(GUI_TESTS); do \
		if [ ! -f tests/$$test.py ]; then continue; fi; \
		I=0; for a in $(GUI_TESTS_ALL); do [ $$a = $$test ] && break; I=$$((I+1)); done; \
		PORT=$$(($(TEST_PORT_BASE)+30+I)); \
		$(PORTS_FREE) --recipe test-gui --fixture $$test --base $(TEST_PORT_BASE); \
		PIDF=$(BUILD)/test-gui-$$test.pid; \
		echo "  $$test (port $$PORT)..."; \
		$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
			-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
			-serial tcp:127.0.0.1:$$PORT,server=on,wait=off \
			-display none -daemonize -pidfile $$PIDF; \
		sleep 2; \
		timeout --foreground $(T_GUI_FIXTURE) python3 tests/$$test.py $$PORT; \
		$(QEMU_KILL); \
	done

# LOG-HARNESS: private licensing/telemetry infrastructure. The vocab and
# both test scripts are canonical in the private repo
# (forthos-vocabularies); without them each recipe prints SKIPPED and
# exits 0. Offsets: +45 (test-log-harness), +46/+47/+48 (-nic: serial,
# QEMU's dgram end, the test's peer).
# Named timeout budgets (see docs/TASK_HARNESS_KILL_BY_PID.md §3b):
# a hard upper bound in seconds for the test invocation. Observed
# pass times (2026-10-12, prompt-terminated reads): test-log-harness
# 12s, test-log-harness-nic 15s (were 48s and 66s).
T_LOG_HARNESS     ?= 25
T_LOG_HARNESS_NIC ?= 30

test-log-harness-nic: $(COMBINED)
	@for f in forth/dict/log-harness.fth tests/test_log_harness_nic.py; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-log-harness-nic: private vocab absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	PIDF=$(BUILD)/test-log-harness-nic.pid; $(QEMU_KILL); \
	PCAP=$(BUILD)/log-harness-nic.pcap; rm -f $$PCAP; \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-log-harness-nic --base $(TEST_PORT_BASE); \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running LOG-HARNESS NIC smoke test..."; \
	$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-netdev dgram,id=u1,local.type=inet,local.host=127.0.0.1,local.port=$$(($(TEST_PORT_BASE)+47)),remote.type=inet,remote.host=127.0.0.1,remote.port=$$(($(TEST_PORT_BASE)+48)) \
		-device ne2k_pci,netdev=u1,mac=52:54:00:12:34:56 \
		-object filter-dump,id=f1,netdev=u1,file=$$PCAP \
		-serial tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+46)),server=on,wait=off \
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
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-log-harness --base $(TEST_PORT_BASE); \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running LOG-HARNESS smoke test..."; \
	$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+45)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_LOG_HARNESS) python3 tests/test_log_harness.py \
		$$(($(TEST_PORT_BASE)+45))

# LOG-HARNESS block header + LOG-RESTORE gates (60 checks) and the
# disk-validation gates (17). Both scripts are private-owned.
# test_log_validation runs from its ignored public copy (check-sync
# keeps it equal to the private one): its root is its own parent.
# test_log_restore runs in place from $(PRIVATE_REPO): it finds its
# decoder and the HP telemetry file under its own root, and the
# public tree under the working directory. Each launches its QEMUs
# with a pidfile in build/<name>.d; the trap kills by that pidfile.
# Together about 5 minutes (measured 2026-10-11).
T_LOG_RESTORE    ?= 600
T_LOG_VALIDATION ?= 400

test-log-restore: $(COMBINED)
	@for f in forth/dict/log-harness.fth \
		$(PRIVATE_REPO)/tests/test_log_restore.py; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-log-restore: private file absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	PIDF=$(BUILD)/log-restore.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-log-restore --base $(TEST_PORT_BASE); \
	echo "Running LOG-RESTORE gates..."; \
	timeout --foreground $(T_LOG_RESTORE) python3 $(PRIVATE_REPO)/tests/test_log_restore.py \
		$$(($(TEST_PORT_BASE)+70)) all

# LOG-HARNESS Phase 3b, send-only (private TASK_LOG_PHASE3B_SEND.md):
# LOG-SEND's five frames from an NE2000 pcap, checked against the model.
T_LOG_SEND ?= 300
test-log-send: $(COMBINED)
	@for f in forth/dict/log-harness.fth \
		$(PRIVATE_REPO)/tests/test_log_send.py; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-log-send: private file absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	PIDF=$(BUILD)/log-send.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-log-send --base $(TEST_PORT_BASE); \
	echo "Running LOG-SEND (Phase 3b) gates..."; \
	timeout --foreground $(T_LOG_SEND) python3 $(PRIVATE_REPO)/tests/test_log_send.py \
		$$(($(TEST_PORT_BASE)+101)) $$(($(TEST_PORT_BASE)+102)) $$(($(TEST_PORT_BASE)+103))

# Data-stack floor guard (Bug #35, private TASK_STACK_FLOOR): a . on an
# empty stack, then what DEPTH and .S read; four fresh boots.
T_STACK_FLOOR ?= 120
test-stack-floor: $(COMBINED)
	@PIDF=$(BUILD)/stack-floor.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-stack-floor --base $(TEST_PORT_BASE); \
	echo "Running data-stack floor (Bug #35) gates..."; \
	timeout --foreground $(T_STACK_FLOOR) python3 tests/test_stack_floor.py $$(($(TEST_PORT_BASE)+108))

# The console wraps at column 80 onto the next row (private TASK_VGA_WRAP):
# the screen read through the monitor, serial compared byte for byte.
T_VGA_WRAP ?= 150
test-vga-wrap: $(COMBINED)
	@PIDF=$(BUILD)/vga-wrap.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-vga-wrap --base $(TEST_PORT_BASE); \
	echo "Running VGA column-80 wrap gates..."; \
	timeout --foreground $(T_VGA_WRAP) python3 tests/test_vga_wrap.py \
		$$(($(TEST_PORT_BASE)+109)) $$(($(TEST_PORT_BASE)+110))

# RELOAD-VOCAB recompiles an edited vocabulary in place (TASK_RELOAD_VOCAB);
# the test had no recipe until the wiring gate checked scripts (private
# TASK_TEST_WIRING_SCRIPTS). Fixture image under build/reload-vocab.d.
T_RELOAD_VOCAB ?= 300
test-reload-vocab: $(COMBINED)
	@PIDF=$(BUILD)/reload-vocab.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-reload-vocab --base $(TEST_PORT_BASE); \
	echo "Running RELOAD-VOCAB test..."; \
	timeout --foreground $(T_RELOAD_VOCAB) python3 tests/test_reload_vocab.py $$(($(TEST_PORT_BASE)+111))

# RESOLVE-DEPS loads every name on a REQUIRES: line, not only the first
# (private TASK_RESOLVE_DEPS_EVERY_NAME). Fixture image under
# build/resolve-deps.d.
T_RESOLVE_DEPS ?= 300
test-resolve-deps: $(COMBINED)
	@PIDF=$(BUILD)/resolve-deps.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-resolve-deps --base $(TEST_PORT_BASE); \
	echo "Running RESOLVE-DEPS every-name gates..."; \
	timeout --foreground $(T_RESOLVE_DEPS) python3 tests/test_resolve_deps.py $$(($(TEST_PORT_BASE)+112))

T_LOAD_VOCAB ?= 120
test-load-vocab: $(COMBINED)
	@PIDF=$(BUILD)/load-vocab.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-load-vocab --base $(TEST_PORT_BASE); \
	echo "Running LOAD-VOCAB search-order and miss gates..."; \
	timeout --foreground $(T_LOAD_VOCAB) python3 tests/test_load_vocab.py $$(($(TEST_PORT_BASE)+106))

T_DLG2FORM ?= 200
test-dlg2form: $(COMBINED)
	@for f in $(PRIVATE_REPO)/tools/dlg2form.py \
		$(PRIVATE_REPO)/tests/test_dlg2form.py; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-dlg2form: private file absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	PIDF=$(BUILD)/dlg2form.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-dlg2form --base $(TEST_PORT_BASE); \
	echo "Running dlg2form (Windows About box as a FORM) gates..."; \
	timeout --foreground $(T_DLG2FORM) python3 $(PRIVATE_REPO)/tests/test_dlg2form.py \
		$$(($(TEST_PORT_BASE)+104)) $$(($(TEST_PORT_BASE)+105))

# RTL8168's IP-CKSUM against RFC 1071 (private TASK_RTL8168_CKSUM): three
# 20-byte vectors typed into the guest, word level (QEMU has no RTL8168).
T_RTL8168_CKSUM ?= 120
test-rtl8168-cksum: $(COMBINED)
	@for f in forth/dict/rtl8168.fth \
		$(PRIVATE_REPO)/tests/test_rtl8168_cksum.py; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-rtl8168-cksum: private file absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	PIDF=$(BUILD)/rtl8168-cksum.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-rtl8168-cksum --base $(TEST_PORT_BASE); \
	echo "Running RTL8168 IP-CKSUM (RFC 1071) gates..."; \
	timeout --foreground $(T_RTL8168_CKSUM) python3 $(PRIVATE_REPO)/tests/test_rtl8168_cksum.py \
		$$(($(TEST_PORT_BASE)+107))

test-log-validation: $(COMBINED)
	@for f in forth/dict/log-harness.fth tests/test_log_validation.py; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-log-validation: private file absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	PIDF=$(BUILD)/log-validation.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-log-validation --base $(TEST_PORT_BASE); \
	echo "Running LOG-HARNESS disk validation gates..."; \
	timeout --foreground $(T_LOG_VALIDATION) python3 tests/test_log_validation.py \
		$$(($(TEST_PORT_BASE)+73)) both

# Host only: the decoder's image, header and dump are byte-identical
# to the decoder before the layout refactor (TASK_LOG_LAYOUT_REFACTOR).
test-log-decode-layout:
	@if [ ! -f $(PRIVATE_REPO)/tests/test_log_decode_layout.py ]; then \
		echo "SKIPPED: test-log-decode-layout: private test absent"; \
	else \
		echo "Running LOG decoder layout check..."; \
		python3 $(PRIVATE_REPO)/tests/test_log_decode_layout.py; \
	fi

# Run the INSTALL write-allowlist gate (Piece 1).
# Needs $(COMBINED): INSTALL is block-loaded off the catalog, not
# embedded, so the block store has to be attached.
test-install: $(COMBINED) $(BOOTLOADER) $(VBR)
	@cp $(COMBINED) $(COMBINED_IDE)
	@PIDF=$(BUILD)/test-install.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-install --base $(TEST_PORT_BASE); \
	PORT=$$(($(TEST_PORT_BASE)+3)); \
	echo "Running INSTALL allowlist test..."; \
	$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp:127.0.0.1:$$PORT,server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_INSTALL) python3 tests/test_install.py $$PORT

# VBR variant boot smoke (test manages its own QEMU; monitor on port+1)
test-vbr: $(VBR) $(KERNEL) $(IMAGE)
	@QPIDDIR=$(BUILD)/test-vbr.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-vbr --base $(TEST_PORT_BASE); \
	echo "Running VBR variant boot smoke..."; \
	PORT=$$(($(TEST_PORT_BASE)+8)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_VBR) python3 tests/test_vbr_boot.py $$PORT

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
	@QPIDDIR=$(BUILD)/test-g6.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-g6 --base $(TEST_PORT_BASE); \
	echo "Running G6 chain harness..."; \
	PORT=$$(($(TEST_PORT_BASE)+95)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_G6) python3 tests/test_g6_chain.py $$PORT

# Run full integration test
test-integration: $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@PIDF=$(BUILD)/test-integration.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-integration --base $(TEST_PORT_BASE); \
	PORT=$$(($(TEST_PORT_BASE)+20)); \
	echo "Running full integration test..."; \
	$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp:127.0.0.1:$$PORT,server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_INTEGRATION) python3 tests/test_full_integration.py $$PORT

# Run NE2000 network test (two QEMU instances)
test-network: $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@QPIDDIR=$(BUILD)/test-network.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-network --base $(TEST_PORT_BASE); \
	echo "Running NE2000 network test..."; \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_NETWORK) python3 tests/test_ne2000_network.py $$(($(TEST_PORT_BASE)+40))

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
	@QPIDDIR=$(BUILD)/test-block-reload.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-block-reload --base $(TEST_PORT_BASE); \
	echo "Running block-cache reload test (Bug #34)..."; \
	PORT=$$(($(TEST_PORT_BASE)+95)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_BLOCK_RELOAD) python3 tests/test_block_reload.py $$PORT $(COMBINED)

# Block-cache eviction gate (TASK_BLK_EVICT_FIX): the LRU replaces the
# least recently used slot, and an eviction flush keeps the victim's slot
# index whether the writer refuses or succeeds.  A fixture writer and the
# ATA writer on scratch copies of $(COMBINED); the script launches QEMU.
test-blk-evict: $(COMBINED)
	@QPIDDIR=$(BUILD)/test-blk-evict.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-blk-evict --base $(TEST_PORT_BASE); \
	echo "Running block-cache eviction test..."; \
	PORT=$$(($(TEST_PORT_BASE)+66)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_BLK_EVICT) python3 tests/test_blk_evict.py $$PORT $(COMBINED)

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
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-xhci --base $(TEST_PORT_BASE); \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running xHCI vocab test..."; \
	$(QEMU) -M pc -device qemu-xhci -device usb-kbd,id=kbd \
		-drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+94)),server=on,wait=off \
		-monitor tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+93)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_XHCI) python3 -u tests/test_xhci.py $$(($(TEST_PORT_BASE)+94)) $(COMBINED) $$(($(TEST_PORT_BASE)+93))

# PCI-BAR gate, (bz) R2 (docs/evidence/bz-base-finding-prereg-2026-09-27.md):
# block-loaded pci-bar.fth, instances of a class in scan order.  TWO
# intel-hda functions, so "never chosen implicitly" meets more than one
# instance (the HP has one).  Port +87 was unused.
test-pci-bar: $(COMBINED)
	@PIDF=$(BUILD)/test-pci-bar.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-pci-bar --base $(TEST_PORT_BASE); \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running PCI-BAR vocab test..."; \
	$(QEMU) -M pc -device intel-hda -device intel-hda \
		-drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+87)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_PCI_BAR) python3 -u tests/test_pci_bar.py $$(($(TEST_PORT_BASE)+87)) $(COMBINED)

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
# xhci: about 2x observed (2026-10-12): 3m58s, 319/319 with Phase 12,
# every read prompt-terminated. The old 120 s never measured a pass: it
# bounded the settle-and-gap reads (20+ minutes a run), and the cut-off
# read as a Phase 12 hang.
T_XHCI ?= 480
# pci-bar: about 2x observed (2026-10-12): 24s, 16/16, every read
# prompt-terminated (was 223s on settle-and-gap reads, 64 reads at ~3.3s;
# the earlier 90s never measured a pass).
T_PCI_BAR ?= 50

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
# The exe check accepts any qemu-system-* binary (batch 3b: test scripts
# start aarch64/arm QEMUs too); the pidfile-held-open check is what ties the
# PID to this tree and is unchanged.
# Known refusal (not fixed): the guard deletes the pidfile but leaves a real
# QEMU running when $(BUILD) (or QEMU_PIDDIR) is an absolute path, since
# "$(CURDIR)/$$PIDF" is then not the path QEMU holds open.
# See docs/TASK_HARNESS_KILL_BY_PID.md.
QEMU_KILL = if [ -f $$PIDF ]; then QPID=$$(cat $$PIDF 2>/dev/null); \
	case "$$(readlink /proc/$$QPID/exe)" in */qemu-system-*) \
	  if readlink /proc/$$QPID/fd/* 2>/dev/null | grep -qxF "$(CURDIR)/$$PIDF"; \
	  then kill -9 $$QPID 2>/dev/null; fi;; esac; rm -f $$PIDF; fi
# QEMU_KILL_DIR: for recipes whose test SCRIPT starts the QEMU(s) (batch 3b).
# The recipe sets QPIDDIR=$(BUILD)/<target>.d and exports it as QEMU_PIDDIR;
# the script passes -pidfile $QEMU_PIDDIR/<role>.pid for every QEMU it starts
# (tests/qemu_pid.py). Pre-clean and trap run QEMU_KILL over each one.
QEMU_KILL_DIR = for PIDF in $$QPIDDIR/*.pid; do [ -e "$$PIDF" ] || continue; $(QEMU_KILL); done
# Refuse to start on a taken port (TASK_PORT_REFUSAL_4C): every QEMU recipe
# runs this after its pre-clean and before any launch; it reads the ports
# from tools/qemu_ports.json and fails naming the first busy one.
PORTS_FREE ?= python3 tools/ports_free.py
# Budgets for the batch-3b recipes, about 2x observed (2026-10-04): vbr 39s,
# g6 613s, arm64-boot 354s; block-reload 12s (2026-10-12, prompt-terminated
# reads; was 64s). cortexm is provisional: its
# baseline fails before the ARM phase (2/5), so its full time is unknown.
T_VBR ?= 90
# .py step, py-a (about 2x observed 2026-10-04): survey 554s; carrier 6s and
# memdisk 16s (2026-10-12, prompt-terminated reads; were 37s and 122s). network: 439.5s in each of two full runs (2026-10-05,
# after its start_qemu_pair NameError was fixed); 447.6s in each of two runs (2026-10-13, NET-DATA:
# the ATA writer armed on both instances, 56 checks).
T_CARRIER ?= 15
T_MEMDISK ?= 35
T_SURVEY ?= 1100
T_NETWORK ?= 900
T_G6 ?= 1200
T_BLOCK_RELOAD ?= 25
# About 2x measured (2026-10-11): blk-evict 27 s, mirror 30 s, interp-abort
# 44 s, pad-move 17 s. A limit is never raised as a fix.
T_BLK_EVICT ?= 60
T_MIRROR ?= 60
T_INTERP_ABORT ?= 90
T_PAD_MOVE ?= 40
# About 2x measured (2026-10-12): hal 13.7 s (three runs, slices 1 + 2).
T_HAL ?= 30
# About 2x measured: hal-match 17.4 s (2026-10-12, two boots, two runs; 18.8 s 10-13),
# hal-match-hp 12.7 s (2026-10-13, two runs; boots pxelinux -> memdisk, as the stick).
T_HAL_MATCH ?= 35
# About 2x measured: hal-net 9.9 s (2026-10-13, two boots, two runs).
T_HAL_NET ?= 20
T_HAL_MATCH_HP ?= 25
# About 2x measured (2026-10-12): uefi-boot 56.6 s (OVMF + SeaBIOS legs, each
# running HELLO-RUN, notepad's editor, PCI-TYPES and the phase-0 discovery
# words; 50.5 s before discovery, 17.7 s before the apps). 66.8 s (2026-10-13,
# two runs) with the firmware memory and range checks: 135.
T_UEFI_BOOT ?= 135
# About 2x measured (2026-10-12): uefi-netboot 12 s (three runs; grub-net staging included).
T_UEFI_NETBOOT ?= 30
T_ARM64_BOOT ?= 720
T_CORTEXM ?= 600
test-firstboot: $(COMBINED)
	@PIDF=$(BUILD)/firstboot-lan.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; \
	$(PORTS_FREE) --recipe test-firstboot --base $(TEST_PORT_BASE) || exit 1; \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running FIRSTBOOT wizard test (lan)..."; \
	$(QEMU) -M pc -nic none -device rtl8139 -device e1000 \
		-device ahci,id=ahci0 \
		-drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+88)),server=on,wait=off \
		-monitor tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+89)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF || exit 1; \
	sleep 2; \
	python3 tests/test_firstboot.py $$(($(TEST_PORT_BASE)+88)) $(COMBINED) \
		$$(($(TEST_PORT_BASE)+89)) lan $(COMBINED_IDE)
	@PIDF=$(BUILD)/firstboot-offline.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running FIRSTBOOT wizard test (offline)..."; \
	$(QEMU) -M pc -nic none \
		-drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+84)),server=on,wait=off \
		-monitor tcp:127.0.0.1:$$(($(TEST_PORT_BASE)+85)),server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF || exit 1; \
	sleep 2; \
	python3 tests/test_firstboot.py $$(($(TEST_PORT_BASE)+84)) $(COMBINED) \
		$$(($(TEST_PORT_BASE)+85)) offline $(COMBINED_IDE)

# S"/."/ABORT" laydown suite (crafts blocks in buffer memory; no
# block storage image needed, same tier as test-dict-bounds).
test-squote-laydown: $(ACTIVE_IMAGE)
	@PIDF=$(BUILD)/test-squote-laydown.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-squote-laydown --base $(TEST_PORT_BASE); \
	PORT=$$(($(TEST_PORT_BASE)+98)); \
	echo "Running S\"-laydown test..."; \
	$(QEMU) -drive file=$(ACTIVE_IMAGE),format=raw,if=floppy \
		-serial tcp:127.0.0.1:$$PORT,server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_SQUOTE_LAYDOWN) python3 tests/test_squote_laydown.py $$PORT $(ACTIVE_IMAGE)

# Same suite against the defeated-backstop image: observes the
# in-loop DICT_LIMIT guard firing (unreachable in normal builds).
test-squote-laydown-backstop0: $(BACKSTOP0_IMAGE)
	@PIDF=$(BUILD)/test-squote-laydown-backstop0.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-squote-laydown-backstop0 --base $(TEST_PORT_BASE); \
	PORT=$$(($(TEST_PORT_BASE)+99)); \
	echo "Running S\"-laydown --backstop0 test..."; \
	$(QEMU) -drive file=$(BACKSTOP0_IMAGE),format=raw,if=floppy \
		-serial tcp:127.0.0.1:$$PORT,server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_SQUOTE_BACKSTOP0) python3 tests/test_squote_laydown.py $$PORT $(BACKSTOP0_IMAGE) --backstop0

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
	@PIDF=$(BUILD)/test-flush.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-flush --base $(TEST_PORT_BASE); \
	PORT=$$(($(TEST_PORT_BASE)+50)); \
	echo "Running flush stress test..."; \
	$(QEMU) -drive file=$(DEBUG_COMBINED),format=raw,if=floppy \
		-drive file=$(DEBUG_COMBINED_IDE),format=raw,if=ide,index=1 \
		-serial tcp:127.0.0.1:$$PORT,server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_FLUSH) python3 tests/test_flush_stress.py $$PORT

# Lint Forth source (vocabulary files + kernel assembly)
lint:
	@python3 tools/lint-forth.py forth/dict/*.fth
	@python3 tools/lint-forth.py --asm $(SRC_KERNEL)/forth.asm

# Run ARM64 boot test (cross-compile + QEMU raspi3b)
# In make test (private TASK_TWO_OVER: it carries TARGET-ARM64's 2OVER
# check). Skipped, not passed, without the private vocabularies or
# qemu-system-aarch64.
test-arm64-boot: $(COMBINED)
	@for f in forth/dict/meta-compiler.fth forth/dict/arm64-asm.fth \
		forth/dict/target-arm64.fth; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-arm64-boot: private vocabulary absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	if ! command -v qemu-system-aarch64 >/dev/null 2>&1; then \
		echo "SKIPPED: test-arm64-boot: qemu-system-aarch64 absent"; \
		exit 0; \
	fi; \
	cp $(COMBINED) $(COMBINED_IDE); \
	QPIDDIR=$(BUILD)/test-arm64-boot.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-arm64-boot --base $(TEST_PORT_BASE); \
	echo "Running ARM64 boot test..."; \
	PORT=$$(($(TEST_PORT_BASE)+50)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_ARM64_BOOT) python3 tests/test_arm64_boot.py $$PORT

# test-meta-b6b: test-meta's one fixture that boots a META-COMPILE-X86-BOOT
# kernel, in make test because it carries TARGET-X86's 2OVER check
# (private TASK_TWO_OVER). test-meta (all six, about 30 min) stays outside
# the sweep. Skipped, not passed, without the private script or
# vocabularies.
test-meta-b6b: $(COMBINED)
	@for f in tests/test_meta_b6b.py forth/dict/meta-compiler.fth \
		forth/dict/target-x86.fth; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-meta-b6b: private file absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	$(MAKE) --no-print-directory test-meta META_FIXTURES=test_meta_b6b

# Run Cortex-M33 boot test (cross-compile + QEMU mps2-an505)
test-cortexm: $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@QPIDDIR=$(BUILD)/test-cortexm.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-cortexm --base $(TEST_PORT_BASE); \
	echo "Running Cortex-M33 boot test..."; \
	PORT=$$(($(TEST_PORT_BASE)+60)); \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_CORTEXM) python3 tests/test_cortexm_boot.py $$PORT

# Run AHCI write test (ICH9-AHCI + scratch disk)
# Timeout budget: about 2x the observed 129s (2026-10-04).
T_AHCI_WRITE ?= 260
# No "vocab absent" check: without ahci.fth the image build fails first, which is the intended loud failure.
AHCI_SCRATCH = $(BUILD)/ahci-scratch.img
$(AHCI_SCRATCH): | $(BUILD)
	dd if=/dev/zero of=$(AHCI_SCRATCH) bs=512 count=2048 2>/dev/null

test-ahci-write: $(COMBINED) $(AHCI_SCRATCH)
	@if [ ! -f tests/test_ahci_write.py ]; then \
		echo "SKIPPED: test-ahci-write: private test absent (tests/test_ahci_write.py)"; \
		exit 0; \
	fi; \
	PIDF=$(BUILD)/test-ahci-write.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-ahci-write --base $(TEST_PORT_BASE); \
	cp $(COMBINED) $(COMBINED_IDE); \
	echo "Running AHCI write test..."; \
	PORT=$$(($(TEST_PORT_BASE)+75)); \
	$(QEMU) \
		-drive file=$(COMBINED),format=raw,if=floppy \
		-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
		-drive file=$(AHCI_SCRATCH),format=raw,if=none,id=sata0 \
		-device ich9-ahci,id=ahci0 \
		-device ide-hd,drive=sata0,bus=ahci0.0 \
		-serial tcp:127.0.0.1:$$PORT,server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 3; \
	timeout --foreground $(T_AHCI_WRITE) python3 tests/test_ahci_write.py $$PORT

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
# UBT end to end (private TASK_PIPELINE_E2E_REWRITE): translate i8042prt.sys,
# catalog the vocabulary in a fixture image under build/pipeline-e2e.d, find
# it with CATALOG-FIND, load it, call a translated port word. Skipped, not
# passed, when the private test, the translator or the binary is absent.
T_PIPELINE_E2E ?= 300
test-pipeline-e2e: $(COMBINED)
	@for f in $(PRIVATE_REPO)/tests/test_pipeline_e2e.py tools/translator/Makefile \
		tools/translator/tests/data/i8042prt.sys; do \
		if [ ! -f $$f ]; then \
			echo "SKIPPED: test-pipeline-e2e: input absent ($$f)"; \
			exit 0; \
		fi; \
	done; \
	$(MAKE) -s -C tools/translator >/dev/null; \
	PIDF=$(BUILD)/pipeline-e2e.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-pipeline-e2e --base $(TEST_PORT_BASE); \
	echo "Running UBT end-to-end (translated vocabulary from blocks) gates..."; \
	timeout --foreground $(T_PIPELINE_E2E) python3 $(PRIVATE_REPO)/tests/test_pipeline_e2e.py $$(($(TEST_PORT_BASE)+113))

# The net console flushes on LF, not on the caller's DL (private
# TASK_NET_FLUSH_LF). No NIC: the TX pointers aim at RAM the test allots.
T_NET_FLUSH_LF ?= 120
test-net-flush-lf: $(COMBINED)
	@PIDF=$(BUILD)/net-flush-lf.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-net-flush-lf --base $(TEST_PORT_BASE); \
	echo "Running net console LF flush gates..."; \
	timeout --foreground $(T_NET_FLUSH_LF) python3 tests/test_net_flush_lf.py $$(($(TEST_PORT_BASE)+114))

# test-console-band: the console as window 0 (private TASK_CONSOLE_BAND,
# DESIGN_WINDOW_FOCUS step 1). CON-REGION bounds the scroll, MORE, PAGE and
# backspace to a band; the WINDOW vocabulary's table and accessors. The
# screen is read back at FB-BASE on a BIOS boot.
T_CONSOLE_BAND ?= 120
test-console-band: $(COMBINED)
	@PIDF=$(BUILD)/console-band.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-console-band --base $(TEST_PORT_BASE); \
	echo "Running console band gates..."; \
	timeout --foreground $(T_CONSOLE_BAND) python3 tests/test_console_band.py $$(($(TEST_PORT_BASE)+115))

# test-window-focus: Ctrl+W moves the keys and the cursor between windows
# (private TASK_WINDOW_FOCUS, DESIGN_WINDOW_FOCUS step 2): the kernel's
# FOCUS-HOOK, FOCUS-SWITCH and FOCUS-BUSY, WINDOW's key handlers, a form in
# a window, NOTEPAD's editor. Keys over serial and PS/2 (monitor sendkey).
T_WINDOW_FOCUS ?= 240
test-window-focus: $(COMBINED)
	@PIDF=$(BUILD)/window-focus.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-window-focus --base $(TEST_PORT_BASE); \
	echo "Running window focus gates..."; \
	timeout --foreground $(T_WINDOW_FOCUS) python3 tests/test_window_focus.py $$(($(TEST_PORT_BASE)+118)) $$(($(TEST_PORT_BASE)+119))

# test-free-boot: the free image (make free; EMBED_VOCABS_FREE embeds
# NOTEPAD) boots to ok, every embedded line resolves, NOTEPAD is loaded
# (private TASK_WINDOW_FOCUS). No other test boots it.
T_FREE_BOOT ?= 120
test-free-boot: $(IMAGE_FREE)
	@PIDF=$(BUILD)/free-boot.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-free-boot --base $(TEST_PORT_BASE); \
	echo "Running free image boot gates..."; \
	timeout --foreground $(T_FREE_BOOT) python3 tests/test_free_boot.py $$(($(TEST_PORT_BASE)+120)) $(IMAGE_FREE)

# test-search-order: ALSO and USING on a full search order refuse with
# SEARCH ORDER FULL instead of dropping the top entry (private
# TASK_ALSO_FULL, part a).
T_SEARCH_ORDER ?= 120
test-search-order: $(COMBINED)
	@PIDF=$(BUILD)/search-order.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-search-order --base $(TEST_PORT_BASE); \
	echo "Running search order gates..."; \
	timeout --foreground $(T_SEARCH_ORDER) python3 tests/test_search_order.py $$(($(TEST_PORT_BASE)+121))

# test-abort-routes: ABORT and a fired ABORT" go through abort_common (a
# load they stop rolls back; the embedded stream says EMBED ABORTED), and a
# Ctrl+C read by KEY leaves the console's next line alone (private
# TASK_ABORT_ROUTES).
T_ABORT_ROUTES ?= 300
test-abort-routes: $(COMBINED)
	@PIDF=$(BUILD)/abort-routes.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-abort-routes --base $(TEST_PORT_BASE); \
	echo "Running abort route gates..."; \
	timeout --foreground $(T_ABORT_ROUTES) python3 tests/test_abort_routes.py $$(($(TEST_PORT_BASE)+122))

# test-vocab-dedup: LOAD-VOCAB of a vocabulary already present adds
# nothing; dictionary headers counted by pmemsave (docs/TASK_VOCAB_DEDUP.md).
T_VOCAB_DEDUP ?= 300
test-vocab-dedup: $(COMBINED)
	@PIDF=$(BUILD)/vocab-dedup.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-vocab-dedup --base $(TEST_PORT_BASE); \
	echo "Running vocab dedup gates..."; \
	PRIVATE_REPO='$(PRIVATE_REPO)' PRIVATE_REPO_ORIGIN='$(origin PRIVATE_REPO)' \
	timeout --foreground $(T_VOCAB_DEDUP) python3 tests/test_vocab_dedup.py $$(($(TEST_PORT_BASE)+123))

# test-phys-refuse: AHCI, RTL8168 and NTFS refuse a DMA buffer PHYS-ALLOC
# refused (0) instead of using address 0; low memory is the witness
# (private TASK_PHYS_CEILING). The free kernel, the drivers from blocks.
T_PHYS_REFUSE ?= 300
test-phys-refuse: $(IMAGE_FREE) $(COMBINED)
	@PIDF=$(BUILD)/phys-refuse.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-phys-refuse --base $(TEST_PORT_BASE); \
	echo "Running DMA buffer refusal gates..."; \
	PRIVATE_REPO='$(PRIVATE_REPO)' PRIVATE_REPO_ORIGIN='$(origin PRIVATE_REPO)' \
	timeout --foreground $(T_PHYS_REFUSE) python3 tests/test_phys_refuse.py $$(($(TEST_PORT_BASE)+124))

# test-window-forms: a form per window, kept in the window's own area,
# Ctrl+W around the windows with a key handler (private TASK_WINDOW_STEP3A).
# Its own fixture catalog under build/window-forms.d.
T_WINDOW_FORMS ?= 300
test-window-forms: $(COMBINED)
	@PIDF=$(BUILD)/window-forms.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-window-forms --base $(TEST_PORT_BASE); \
	echo "Running window form gates..."; \
	timeout --foreground $(T_WINDOW_FORMS) python3 tests/test_window_forms.py $$(($(TEST_PORT_BASE)+125))

# test-double-cell: 2DROP 2DUP 2SWAP 2OVER against Forth-83 13.2, and
# RL-VAR's recorded name (private TASK_TWO_OVER). 2ROT 2@ 2! are optional
# and absent: reported, not counted.
T_DOUBLE_CELL ?= 120
test-double-cell: $(COMBINED)
	@PIDF=$(BUILD)/double-cell.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-double-cell --base $(TEST_PORT_BASE); \
	echo "Running double-cell word gates..."; \
	timeout --foreground $(T_DOUBLE_CELL) python3 tests/test_double_cell.py $$(($(TEST_PORT_BASE)+116))

# test-forth83: the kernel's UM* and UM/MOD, and the block-loaded FORTH83
# vocabulary (Forth-83 Required words the kernel lacked, and DOES>), with
# DOES>'s checks: another CURRENT, SEE, TARGET-X86 alongside, a MIRROR image
# across a reboot (private TASK_FORTH83_VOCAB). Carries see1_RED (XFAIL).
T_FORTH83 ?= 240
test-forth83: $(COMBINED)
	@PIDF=$(BUILD)/forth83.d/qemu.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-forth83 --base $(TEST_PORT_BASE); \
	echo "Running FORTH83 gates..."; \
	timeout --foreground $(T_FORTH83) python3 tests/test_forth83.py $$(($(TEST_PORT_BASE)+117))

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
	@$(PORTS_FREE) --recipe test-uefi2-gdt --base $(TEST_PORT_BASE)
	@python3 tests/test_uefi2_gdt.py $(IMAGE) $(COMBINED) $$(($(TEST_PORT_BASE)+77)) $$(($(TEST_PORT_BASE)+78))

# CARRIER-0b host-safety gate (carrier-0b-write-vector-2026-09-29.md): a cell-0
# boot must NOT write blocks to a fixed disk by default. Floppy (cell-0) + a
# scratch IDE disk with a sentinel; a SAVE-BUFFERS must leave it intact.
test-carrier-write-safe: $(IMAGE)
	@QPIDDIR=$(BUILD)/test-carrier-write-safe.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-carrier-write-safe --base $(TEST_PORT_BASE); \
	echo "Running CARRIER-0b write-safety gate..."; \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_CARRIER) python3 tests/test_carrier_write_safe.py $$(($(TEST_PORT_BASE)+79))

# M1 of the UEFI stages (uefi-1-prereg-2026-09-28.md): the HP's BIOS boot
# chain in QEMU -- pxelinux -> memdisk -> combined.img -- reaches ok,
# reads blocks from RAM and refuses writes loudly (M4b, bc06026).  It
# was never wired and no reason was recorded; ~2 min.  Port 4483 is its
# own; it prints SKIP and exits 0 if pxelinux/memdisk are not installed.
test-memdisk: $(COMBINED)
	@QPIDDIR=$(BUILD)/test-memdisk.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-memdisk --base $(TEST_PORT_BASE); \
	echo "Running memdisk boot test (pxelinux -> memdisk)..."; \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_MEMDISK) python3 tests/test_memdisk_blk_writer.py $$(($(TEST_PORT_BASE)+65))

# UEFI-1 red (docs/evidence/uefi-1-prereg-2026-09-28.md): a rootless replica
# of the make-uefi-usb.sh stick booted under OVMF (no CSM) must reach the
# Forth banner + ok on serial.  Registered red: prints XFAIL and exits 0
# until UEFI-3; XPASS exits 1.  Serial goes to a file, no TCP port.
# UEFI-3/4 gate (docs/TASK_UEFI_3_4.md): the stick replica under OVMF (no CSM,
# multiboot2 kernel + module, framebuffer) and SeaBIOS (legacy, memdisk);
# serial on +74, monitor (screen dump) on +76.
test-uefi-boot: $(COMBINED)
	@QPIDDIR=$(BUILD)/test-uefi-boot.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-uefi-boot --base $(TEST_PORT_BASE); \
	echo "Running UEFI boot gate (OVMF, no CSM, multiboot2)..."; \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_UEFI_BOOT) python3 -u tests/test_uefi_boot.py $$(($(TEST_PORT_BASE)+74)) $$(($(TEST_PORT_BASE)+76)) $(COMBINED)

# UEFI network boot gate (docs/TASK_UEFI_3_4.md): OVMF boots the staged GRUB
# tree over QEMU's own DHCP/TFTP; serial on +71 (unused before).  Never
# touches the live PXE server.
test-uefi-netboot: grub-net
	@QPIDDIR=$(BUILD)/test-uefi-netboot.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-uefi-netboot --base $(TEST_PORT_BASE); \
	echo "Running UEFI network boot gate (OVMF, TFTP)..."; \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_UEFI_NETBOOT) python3 -u tests/test_uefi_netboot.py $$(($(TEST_PORT_BASE)+71))

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

# QEMU port inventory drift check (TASK_PORT_REFUSAL_4C §3): the ports every
# recipe and its scripts listen on, regenerated from the Makefile and
# tests/*.py, must equal the committed tools/qemu_ports.json, and no serial
# or monitor may use tcp::PORT (every interface). Regenerate with
#   python3 tools/port_inventory.py > tools/qemu_ports.json
test-port-inventory:
	@echo "Running QEMU port inventory check..."
	@python3 tools/port_inventory.py --check tools/qemu_ports.json

# Every kill trap must include PIPE: under `make ... 2>&1 | grep`, a dead
# pipe reader turns the recipe shell's next write into SIGPIPE, and without
# PIPE in the list the shell dies before its trap runs, orphaning its QEMUs
# (docs/TASK_TEST_META_ORPHAN_RACE.md; 0/31 before the fix, 2026-10-10).
test-kill-traps:
	@echo "Running kill-trap PIPE check..."
	@python3 tools/check_kill_traps.py Makefile

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
	@PIDF=$(BUILD)/test-file-stream.pid; $(QEMU_KILL); \
	trap '$(QEMU_KILL)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-file-stream --base $(TEST_PORT_BASE); \
	PORT=$$(($(TEST_PORT_BASE)+55)); \
	echo "=== FILE-STREAM helpers (port $$PORT) ==="; \
	$(QEMU) -drive file=build/bmforth.img,format=raw,if=floppy \
		-serial tcp:127.0.0.1:$$PORT,server=on,wait=off \
		-display none -daemonize -pidfile $$PIDF; \
	sleep 2; \
	timeout --foreground $(T_FILE_STREAM) python3 tests/test_file_stream_helpers.py $$PORT

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
	QPIDDIR=$(BUILD)/test-survey.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; $(PORTS_FREE) --recipe test-survey --base $(TEST_PORT_BASE); \
	PORT=$$(($(TEST_PORT_BASE)+100)); \
	echo "=== DISK-SURVEY layouts (ports $$PORT-$$((PORT+5))) ==="; \
	QEMU_PIDDIR=$$QPIDDIR timeout --foreground $(T_SURVEY) python3 tests/test_survey_layouts.py $$PORT

# Run metacompiler tests (5 files, x86 self-hosting verification)
# NOT included in 'make test' — slow, boots multiple QEMU instances.
# Each fixture prints "DICT MARGIN <fixture>: peak HERE ..., N bytes below
# <ceiling>" at the end of its host phase (tests/meta_margin.py; reported,
# not a check).  Measured 2026-10-10 (stream 89,679 B, boot HERE 0x5C7F4):
# smallest margin 39,204 B (test_meta_boot), 39,228 in four fixtures,
# 66,388 in test_metacompiler.  test-meta, not the stream size, is the
# dictionary's tightest consumer: dictionary added at boot raises its peak
# one-for-one, while the stream alone does not move it (a stream filling
# the 0x1C000 pad left the peak unchanged).  Embedded code costs 0.7-2.4
# dictionary bytes per stream byte; an ALLOT buffer is bounded only by
# this margin.  After RELOAD-VOCAB (same day; stream 92,925 B, 2,879 B of
# pad left): smallest margin 35,468 B (test_meta_boot), 35,492 in four,
# 62,652 in test_metacompiler.
test-meta: $(COMBINED)
	@cp $(COMBINED) $(COMBINED_IDE)
	@echo "Running metacompiler tests..."
	@QPIDDIR=$(BUILD)/test-meta.d; mkdir -p $$QPIDDIR; $(QEMU_KILL_DIR); \
	trap '$(QEMU_KILL_DIR)' EXIT INT TERM HUP PIPE; set -e; \
	export QEMU_PIDDIR=$$QPIDDIR; \
	for spec in $(META_FIXTURES_ALL); do \
		name=$${spec%:*}; off=$${spec#*:}; \
		case " $(META_FIXTURES) " in *" $$name "*) ;; *) continue;; esac; \
		PORT=$$(($(TEST_PORT_BASE)+$$off)); \
		$(PORTS_FREE) --recipe test-meta --fixture $$name --base $(TEST_PORT_BASE); \
		echo "  $$name (port $$PORT)..."; \
		if [ $$name = test_metacompiler ]; then \
			$(QEMU) -drive file=$(COMBINED),format=raw,if=floppy \
				-drive file=$(COMBINED_IDE),format=raw,if=ide,index=1 \
				-serial tcp:127.0.0.1:$$PORT,server=on,wait=off \
				-display none -daemonize -pidfile $$QPIDDIR/metacompiler.pid; \
			sleep 2; \
			timeout --foreground $(T_METACOMPILER) python3 tests/$$name.py $$PORT; \
		else \
			timeout --foreground $(T_META_FIXTURE) python3 tests/$$name.py $$PORT; \
		fi; \
		$(QEMU_KILL_DIR); \
	done
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
#     emulator trips, and QEMU is not a truth source.  test-network runs
#     again since 2026-10-05 but fails 6/52 (block data on B is the
#     previous block's); see finding-test-network-six-reds-after-crash-fix.
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
test: lint check-coverage test-smoke test-loops test-abort test-dict-bounds test-phys-alloc test-pci-typing test-xhci test-pci-bar test-firstboot test-block-reload test-blk-evict test-squote-laydown test-install test-log-harness test-log-harness-nic test-log-restore test-log-validation test-log-decode-layout test-log-send test-dlg2form test-rtl8168-cksum test-stack-floor test-vga-wrap test-reload-vocab test-load-vocab test-resolve-deps test-vbr test-grub-cfg test-uefi-boot test-uefi-netboot test-uefi2-gdt test-carrier-write-safe test-memdisk test-doc-drift test-make-wiring test-port-inventory test-kill-traps test-g6 test-mirror test-interp-abort test-pad-move test-hal test-hal-net test-hal-match test-hal-match-hp test-network test-vocabs test-gui test-integration test-file-stream test-survey test-translator test-pipeline test-pipeline-e2e test-net-flush-lf test-console-band test-window-focus test-free-boot test-search-order test-abort-routes test-vocab-dedup test-phys-refuse test-window-forms test-double-cell test-forth83 test-arm64-boot test-meta-b6b check-sync
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

.PHONY: all run run-gui run-serial debug check clean help iso blocks run-blocks run-blocks-gui write-block write-catalog combined usb-image check-coverage desk-hashes check-kernel-size test test-blk-evict test-mirror test-interp-abort test-pad-move test-smoke test-loops test-vocabs test-gui test-integration test-flush test-network test-ahci-write test-file-stream test-log-harness test-log-harness-nic test-log-restore test-log-validation test-log-decode-layout test-log-send test-dlg2form test-rtl8168-cksum test-stack-floor test-vga-wrap test-reload-vocab test-load-vocab test-resolve-deps test-pipeline-e2e test-net-flush-lf test-console-band test-window-focus test-free-boot test-search-order test-abort-routes test-vocab-dedup test-phys-refuse test-window-forms test-double-cell test-forth83 test-meta-b6b pxe-setup pxe-push pxe-status grub-net pxe-push-grub free run-free check-sync test-grub-cfg test-g6 test-uefi-netboot test-hal test-hal-net test-hal-match test-hal-match-hp
