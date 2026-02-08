# ============================================================================
# Makefile for Floored Division Package
# Jolly Genius Inc. - Ship's Systems Software
# ============================================================================

CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11
CFLAGS_DEBUG = -Wall -Wextra -g -O0 -std=c11 -DDEBUG

# Assemblers
NASM = nasm
AS = as

# Build directory
BUILD = build

# ============================================================================
# Default target
# ============================================================================

.PHONY: all
all: test

# ============================================================================
# Test suite
# ============================================================================

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/test_floored_div: test_floored_div.c floored_div.h | $(BUILD)
	$(CC) $(CFLAGS) -o $@ test_floored_div.c

.PHONY: test
test: $(BUILD)/test_floored_div
	@echo "Running floored division test suite..."
	@./$(BUILD)/test_floored_div

.PHONY: test-debug
test-debug: test_floored_div.c floored_div.h | $(BUILD)
	$(CC) $(CFLAGS_DEBUG) -o $(BUILD)/test_floored_div_debug test_floored_div.c
	./$(BUILD)/test_floored_div_debug

# ============================================================================
# Native code generation validation (x86-64 only on x86-64 host)
# ============================================================================

$(BUILD)/codegen_x64_test: codegen_floored_x64.c floored_div.h | $(BUILD)
	@echo "// Test harness" > $(BUILD)/codegen_test_main.c
	@echo "#include <stdio.h>" >> $(BUILD)/codegen_test_main.c
	@echo "#include <stdint.h>" >> $(BUILD)/codegen_test_main.c
	@echo "#include <string.h>" >> $(BUILD)/codegen_test_main.c
	@cat codegen_floored_x64.c >> $(BUILD)/codegen_test_main.c
	@echo "" >> $(BUILD)/codegen_test_main.c
	@echo "int main() {" >> $(BUILD)/codegen_test_main.c
	@echo "    uint8_t buf[128];" >> $(BUILD)/codegen_test_main.c
	@echo "    size_t len = emit_floored_div_x64(buf, sizeof(buf));" >> $(BUILD)/codegen_test_main.c
	@echo "    printf(\"x64 floored div: %zu bytes\\n\", len);" >> $(BUILD)/codegen_test_main.c
	@echo "    for (size_t i = 0; i < len; i++) printf(\"%02x \", buf[i]);" >> $(BUILD)/codegen_test_main.c
	@echo "    printf(\"\\n\");" >> $(BUILD)/codegen_test_main.c
	@echo "    len = emit_floored_mod_x64(buf, sizeof(buf));" >> $(BUILD)/codegen_test_main.c
	@echo "    printf(\"x64 floored mod: %zu bytes\\n\", len);" >> $(BUILD)/codegen_test_main.c
	@echo "    for (size_t i = 0; i < len; i++) printf(\"%02x \", buf[i]);" >> $(BUILD)/codegen_test_main.c
	@echo "    printf(\"\\n\");" >> $(BUILD)/codegen_test_main.c
	@echo "    len = emit_floored_divmod_x64(buf, sizeof(buf));" >> $(BUILD)/codegen_test_main.c
	@echo "    printf(\"x64 floored divmod: %zu bytes\\n\", len);" >> $(BUILD)/codegen_test_main.c
	@echo "    for (size_t i = 0; i < len; i++) printf(\"%02x \", buf[i]);" >> $(BUILD)/codegen_test_main.c
	@echo "    printf(\"\\n\");" >> $(BUILD)/codegen_test_main.c
	@echo "    return 0;" >> $(BUILD)/codegen_test_main.c
	@echo "}" >> $(BUILD)/codegen_test_main.c
	$(CC) $(CFLAGS) -o $@ $(BUILD)/codegen_test_main.c

.PHONY: codegen-test
codegen-test: $(BUILD)/codegen_x64_test
	@echo "Testing native code generation..."
	./$(BUILD)/codegen_x64_test

# ============================================================================
# Assemble Forth primitives (for validation)
# ============================================================================

# x86 32-bit (bare metal)
$(BUILD)/forth_div_x86.o: forth_division_primitives.asm | $(BUILD)
	$(NASM) -f elf32 -DARCH_X86 -o $@ $<

# x86-64
$(BUILD)/forth_div_x64.o: forth_division_primitives.asm | $(BUILD)
	$(NASM) -f elf64 -DARCH_X64 -o $@ $<

.PHONY: asm-test
asm-test: $(BUILD)/forth_div_x86.o $(BUILD)/forth_div_x64.o
	@echo "Assembly validation successful"
	@ls -la $(BUILD)/forth_div_*.o

# ============================================================================
# Package for distribution
# ============================================================================

DIST_FILES = floored_div.h \
             codegen_floored_x64.c \
             codegen_floored_arm64.c \
             codegen_floored_riscv64.c \
             forth_division_primitives.asm \
             test_floored_div.c \
             README.md \
             Makefile

.PHONY: dist
dist: $(BUILD)
	tar -czvf $(BUILD)/floored-division.tar.gz $(DIST_FILES)
	@echo "Created $(BUILD)/floored-division.tar.gz"

# ============================================================================
# Clean
# ============================================================================

.PHONY: clean
clean:
	rm -rf $(BUILD)

# ============================================================================
# Help
# ============================================================================

.PHONY: help
help:
	@echo "Floored Division Package - Build Targets"
	@echo "========================================="
	@echo "  make test        - Build and run test suite (default)"
	@echo "  make test-debug  - Build with debug symbols"
	@echo "  make codegen-test- Test native code generation"
	@echo "  make asm-test    - Assemble Forth primitives"
	@echo "  make dist        - Create distribution archive"
	@echo "  make clean       - Remove build artifacts"
	@echo "  make help        - Show this message"
