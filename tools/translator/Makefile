# ============================================================================
# Universal Binary Translator Makefile
# ============================================================================
#
# Targets:
#   make          - Build the translator
#   make test     - Run all tests
#   make clean    - Remove build artifacts
#
# ============================================================================

CC = gcc
CFLAGS = -Wall -Wextra -Wpedantic -O2 -std=c11 -D_POSIX_C_SOURCE=200809L -I$(SRCDIR) -I$(INCDIR)
CFLAGS_DEBUG = -Wall -Wextra -Wpedantic -g -O0 -std=c11 -D_POSIX_C_SOURCE=200809L -DDEBUG -I$(SRCDIR) -I$(INCDIR)
LDFLAGS =

# Directories
SRCDIR = src
INCDIR = include
BUILDDIR = build
BINDIR = bin

# Source files
SRCS = $(wildcard $(SRCDIR)/main/*.c) \
       $(wildcard $(SRCDIR)/loaders/*.c) \
       $(wildcard $(SRCDIR)/decoders/*.c) \
       $(wildcard $(SRCDIR)/ir/*.c) \
       $(wildcard $(SRCDIR)/codegen/*.c) \
       $(wildcard $(SRCDIR)/optimize/*.c) \
       $(wildcard $(SRCDIR)/api/*.c)

OBJS = $(SRCS:$(SRCDIR)/%.c=$(BUILDDIR)/%.o)

# Output
TARGET = $(BINDIR)/translator

# Colors
GREEN = \033[32m
CYAN = \033[36m
YELLOW = \033[33m
RED = \033[31m
NC = \033[0m

# ============================================================================
# Default target
# ============================================================================

.PHONY: all
all: $(TARGET)
	@echo "$(GREEN)Build complete: $(TARGET)$(NC)"

# ============================================================================
# Build directories
# ============================================================================

$(BUILDDIR):
	@mkdir -p $(BUILDDIR)/main
	@mkdir -p $(BUILDDIR)/loaders
	@mkdir -p $(BUILDDIR)/decoders
	@mkdir -p $(BUILDDIR)/ir
	@mkdir -p $(BUILDDIR)/codegen
	@mkdir -p $(BUILDDIR)/optimize
	@mkdir -p $(BUILDDIR)/api
	@mkdir -p $(BUILDDIR)/tests

$(BINDIR):
	@mkdir -p $(BINDIR)

# ============================================================================
# Compilation
# ============================================================================

$(BUILDDIR)/%.o: $(SRCDIR)/%.c | $(BUILDDIR)
	@echo "$(CYAN)Compiling $<...$(NC)"
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c $< -o $@

$(TARGET): $(OBJS) | $(BINDIR)
	@echo "$(CYAN)Linking $(TARGET)...$(NC)"
	$(CC) $(OBJS) $(LDFLAGS) -o $@

# ============================================================================
# Debug build
# ============================================================================

.PHONY: debug
debug: CFLAGS = $(CFLAGS_DEBUG)
debug: clean $(TARGET)
	@echo "$(YELLOW)Debug build complete$(NC)"

# ============================================================================
# Testing — individual component tests
# ============================================================================

.PHONY: test-pe
test-pe: | $(BUILDDIR)
	@echo "$(CYAN)Testing PE loader...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_pe_loader \
		tests/test_pe_loader.c \
		$(SRCDIR)/loaders/pe_loader.c
	./$(BUILDDIR)/tests/test_pe_loader

.PHONY: test-x86
test-x86: | $(BUILDDIR)
	@echo "$(CYAN)Testing x86 decoder...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_x86_decoder \
		tests/test_x86_decoder.c \
		$(SRCDIR)/decoders/x86_decoder.c
	./$(BUILDDIR)/tests/test_x86_decoder

.PHONY: test-cil
test-cil: | $(BUILDDIR)
	@echo "$(CYAN)Testing CIL decoder...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_cil_decoder \
		tests/test_cil_decoder.c \
		$(SRCDIR)/decoders/cil_decoder.c \
		$(SRCDIR)/loaders/pe_loader.c
	./$(BUILDDIR)/tests/test_cil_decoder
	@echo "$(CYAN)Testing CIL semantic classifier...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_cil_semantic \
		tests/test_cil_semantic.c \
		$(SRCDIR)/ir/cil_semantic.c \
		$(SRCDIR)/decoders/cil_decoder.c \
		$(SRCDIR)/loaders/pe_loader.c -lm
	./$(BUILDDIR)/tests/test_cil_semantic

.PHONY: test-arm64
test-arm64: | $(BUILDDIR)
	@echo "$(CYAN)Testing ARM64 decoder...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_arm64_decoder \
		tests/test_arm64_decoder.c \
		$(SRCDIR)/decoders/arm64_decoder.c
	./$(BUILDDIR)/tests/test_arm64_decoder

.PHONY: test-uir
test-uir: | $(BUILDDIR)
	@echo "$(CYAN)Testing UIR lifter...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_uir \
		tests/test_uir.c \
		$(SRCDIR)/ir/uir.c \
		$(SRCDIR)/decoders/x86_decoder.c
	./$(BUILDDIR)/tests/test_uir

.PHONY: test-semantic
test-semantic: | $(BUILDDIR)
	@echo "$(CYAN)Testing semantic analyzer...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_semantic \
		tests/test_semantic.c \
		$(SRCDIR)/ir/semantic.c \
		$(SRCDIR)/ir/uir.c \
		$(SRCDIR)/decoders/x86_decoder.c
	./$(BUILDDIR)/tests/test_semantic

.PHONY: test-forth-codegen
test-forth-codegen: | $(BUILDDIR)
	@echo "$(CYAN)Testing Forth codegen...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_forth_codegen \
		tests/test_forth_codegen.c \
		$(SRCDIR)/codegen/forth_codegen.c
	./$(BUILDDIR)/tests/test_forth_codegen

.PHONY: test-pipeline
test-pipeline: | $(BUILDDIR)
	@echo "$(CYAN)Testing end-to-end pipeline...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_pipeline \
		tests/test_pipeline.c \
		$(SRCDIR)/loaders/pe_loader.c \
		$(SRCDIR)/decoders/x86_decoder.c \
		$(SRCDIR)/ir/uir.c \
		$(SRCDIR)/ir/semantic.c \
		$(SRCDIR)/codegen/forth_codegen.c
	./$(BUILDDIR)/tests/test_pipeline

.PHONY: test-16550
test-16550: | $(BUILDDIR)
	@echo "$(CYAN)Testing synthetic 16550 driver...$(NC)"
	$(CC) $(CFLAGS) -DTRANSLATOR_NO_MAIN -o $(BUILDDIR)/tests/test_16550_driver \
		tests/test_16550_driver.c \
		$(SRCDIR)/main/translator.c \
		$(SRCDIR)/loaders/pe_loader.c \
		$(SRCDIR)/loaders/elf_loader.c \
		$(SRCDIR)/loaders/format_detect.c \
		$(SRCDIR)/loaders/com_loader.c \
		$(SRCDIR)/decoders/x86_decoder.c \
		$(SRCDIR)/ir/uir.c \
		$(SRCDIR)/ir/semantic.c \
		$(SRCDIR)/codegen/forth_codegen.c
	./$(BUILDDIR)/tests/test_16550_driver

.PHONY: test-floored-div
test-floored-div: | $(BUILDDIR)
	@echo "$(CYAN)Testing floored division...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_floored \
		$(SRCDIR)/codegen/floored_div/test_floored_div.c
	./$(BUILDDIR)/tests/test_floored

# ============================================================================
# Ghidra validation — synthetic driver and comparison tests
# ============================================================================

# Ghidra headless analyzer configuration (override with environment or make args)
# Example: make ghidra-fixtures GHIDRA_HOME=/opt/ghidra_12.0_PUBLIC
GHIDRA_HOME ?= /snap/ghidra/35/ghidra_12.0_PUBLIC
GHIDRA_JAVA_HOME ?= /snap/ghidra/35/usr/lib/jvm/java-21-openjdk-amd64
GHIDRA_HEADLESS = JAVA_HOME=$(GHIDRA_JAVA_HOME) \
	$(GHIDRA_HOME)/support/analyzeHeadless

# Build synthetic .sys test binaries
.PHONY: build-synth
build-synth: | $(BUILDDIR)
	@echo "$(CYAN)Building synthetic drivers...$(NC)"
	@mkdir -p $(BUILDDIR)/tests
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/build_synth \
		tests/data/build_synthetic_drivers.c
	./$(BUILDDIR)/tests/build_synth tests/data/

# Regenerate Ghidra fixtures (requires Ghidra installed)
.PHONY: ghidra-fixtures
ghidra-fixtures: build-synth
	@echo "$(CYAN)Generating Ghidra fixtures...$(NC)"
	@mkdir -p tests/data/fixtures /tmp/ghidra_fixture /tmp/ghidra_i8042
	$(GHIDRA_HEADLESS) /tmp/ghidra_fixture GhidraFixture \
		-import tests/data/serial16550_synth.sys \
		-postScript ExportSemanticReport.java \
			tests/data/fixtures/serial16550_synth.ghidra.json \
		-scriptPath ../../tools/ghidra \
		-overwrite -deleteProject
	$(GHIDRA_HEADLESS) /tmp/ghidra_i8042 GhidraI8042 \
		-import tests/data/i8042prt.sys \
		-postScript ExportSemanticReport.java \
			tests/data/fixtures/i8042prt.ghidra.json \
		-scriptPath ../../tools/ghidra \
		-overwrite -deleteProject
	@echo "$(GREEN)Ghidra fixtures generated$(NC)"

# Ghidra comparison test (uses cached fixtures, no Ghidra needed)
.PHONY: test-ghidra-compare
test-ghidra-compare: | $(BUILDDIR)
	@echo "$(CYAN)Testing Ghidra comparison...$(NC)"
	@mkdir -p $(BUILDDIR)/tests
	$(CC) $(CFLAGS) -DTRANSLATOR_NO_MAIN -o $(BUILDDIR)/tests/test_ghidra_compare \
		tests/test_ghidra_compare.c \
		$(SRCDIR)/main/translator.c \
		$(SRCDIR)/loaders/pe_loader.c \
		$(SRCDIR)/loaders/elf_loader.c \
		$(SRCDIR)/loaders/format_detect.c \
		$(SRCDIR)/loaders/com_loader.c \
		$(SRCDIR)/decoders/x86_decoder.c \
		$(SRCDIR)/ir/uir.c \
		$(SRCDIR)/ir/semantic.c \
		$(SRCDIR)/codegen/forth_codegen.c
	./$(BUILDDIR)/tests/test_ghidra_compare

# i8042prt.sys Ghidra validation (HAL cross-reference comparison)
.PHONY: test-i8042-validation
test-i8042-validation: | $(BUILDDIR)
	@echo "$(CYAN)Testing i8042prt.sys Ghidra validation...$(NC)"
	@mkdir -p $(BUILDDIR)/tests
	$(CC) $(CFLAGS) -DTRANSLATOR_NO_MAIN -o $(BUILDDIR)/tests/test_i8042_validation \
		tests/test_i8042_validation.c \
		$(SRCDIR)/main/translator.c \
		$(SRCDIR)/loaders/pe_loader.c \
		$(SRCDIR)/loaders/elf_loader.c \
		$(SRCDIR)/loaders/format_detect.c \
		$(SRCDIR)/loaders/com_loader.c \
		$(SRCDIR)/decoders/x86_decoder.c \
		$(SRCDIR)/ir/uir.c \
		$(SRCDIR)/ir/semantic.c \
		$(SRCDIR)/codegen/forth_codegen.c
	./$(BUILDDIR)/tests/test_i8042_validation

# ============================================================================
# Format detection and COM loader tests
# ============================================================================

.PHONY: test-elf
test-elf: | $(BUILDDIR)
	@echo "$(CYAN)Testing ELF loader...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_elf_loader \
		tests/test_elf_loader.c \
		$(SRCDIR)/loaders/elf_loader.c
	./$(BUILDDIR)/tests/test_elf_loader

.PHONY: test-format-detect
test-format-detect: | $(BUILDDIR)
	@echo "$(CYAN)Testing format detector...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_format_detect \
		tests/test_format_detect.c \
		$(SRCDIR)/loaders/format_detect.c
	./$(BUILDDIR)/tests/test_format_detect

.PHONY: test-com-loader
test-com-loader: | $(BUILDDIR)
	@echo "$(CYAN)Testing COM loader...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/tests/test_com_loader \
		tests/test_com_loader.c \
		$(SRCDIR)/loaders/com_loader.c \
		$(SRCDIR)/decoders/x86_decoder.c
	./$(BUILDDIR)/tests/test_com_loader

# ============================================================================
# Run all tests
# ============================================================================

.PHONY: test test-all
test: test-all
test-all: test-pe test-x86 test-cil test-arm64 test-uir test-semantic test-forth-codegen test-pipeline test-16550 test-ghidra-compare test-i8042-validation test-elf test-format-detect test-com-loader
	@echo ""
	@echo "$(GREEN)All tests passed$(NC)"

# ============================================================================
# Clean
# ============================================================================

.PHONY: clean
clean:
	@echo "$(CYAN)Cleaning build artifacts...$(NC)"
	rm -rf $(BUILDDIR) $(BINDIR)
	@echo "$(GREEN)Clean complete$(NC)"

# ============================================================================
# Distribution
# ============================================================================

.PHONY: dist
dist: clean
	@echo "$(CYAN)Creating distribution archive...$(NC)"
	tar -czvf universal-translator.tar.gz \
		--exclude='.git' \
		--exclude='build' \
		--exclude='bin' \
		.
	@echo "$(GREEN)Archive created: universal-translator.tar.gz$(NC)"

# ============================================================================
# Help
# ============================================================================

.PHONY: help
help:
	@echo "Universal Binary Translator Build System"
	@echo "========================================"
	@echo ""
	@echo "Targets:"
	@echo "  make              Build the translator"
	@echo "  make debug        Build with debug symbols"
	@echo "  make test         Run all tests"
	@echo "  make test-pe      Test PE loader"
	@echo "  make test-x86     Test x86 decoder"
	@echo "  make test-uir     Test UIR lifter"
	@echo "  make test-semantic Test semantic analyzer"
	@echo "  make test-forth-codegen Test Forth codegen"
	@echo "  make test-pipeline Test end-to-end pipeline"
	@echo "  make test-ghidra-compare  Test Ghidra semantic comparison"
	@echo "  make build-synth  Build synthetic .sys test binaries"
	@echo "  make ghidra-fixtures  Regenerate Ghidra fixtures (needs Ghidra)"
	@echo "  make clean        Remove build artifacts"
	@echo "  make dist         Create distribution archive"
	@echo "  make help         Show this message"
