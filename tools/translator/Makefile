# ============================================================================
# Universal Binary Translator Makefile
# ============================================================================
#
# Targets:
#   make          - Build the translator
#   make test     - Run test suite
#   make clean    - Remove build artifacts
#
# ============================================================================

CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -D_POSIX_C_SOURCE=200809L -I$(SRCDIR) -I$(INCDIR)
CFLAGS_DEBUG = -Wall -Wextra -g -O0 -std=c11 -D_POSIX_C_SOURCE=200809L -DDEBUG -I$(SRCDIR) -I$(INCDIR)
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
# Testing
# ============================================================================

.PHONY: test
test: $(TARGET)
	@echo "$(CYAN)Running test suite...$(NC)"
	@if [ -f tests/run_tests.sh ]; then \
		bash tests/run_tests.sh; \
	else \
		echo "$(YELLOW)Test harness placeholder - implement tests/run_tests.sh$(NC)"; \
	fi

.PHONY: test-floored-div
test-floored-div:
	@echo "$(CYAN)Testing floored division...$(NC)"
	$(CC) $(CFLAGS) -o $(BUILDDIR)/test_floored \
		$(SRCDIR)/codegen/floored_div/test_floored_div.c
	./$(BUILDDIR)/test_floored

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
	@echo "  make          Build the translator"
	@echo "  make debug    Build with debug symbols"
	@echo "  make test     Run test suite"
	@echo "  make clean    Remove build artifacts"
	@echo "  make dist     Create distribution archive"
	@echo "  make help     Show this message"

# ============================================================================
# Dependencies (auto-generated, placeholder)
# ============================================================================

# TODO: Add automatic dependency generation with -MMD -MP
