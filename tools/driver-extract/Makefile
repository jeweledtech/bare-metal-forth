# Driver Extraction Tool Makefile
# Compiles the driver extraction library and optional CLI tool

CC = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11 -I.
BUILDDIR = build

.PHONY: all lib cli clean

all: lib

$(BUILDDIR):
	mkdir -p $(BUILDDIR)

# Library object (no main)
lib: $(BUILDDIR)/driver_extract.o
	@echo "Driver extraction library built: $(BUILDDIR)/driver_extract.o"

$(BUILDDIR)/driver_extract.o: driver_extract.c driver_extract.h uir.h x86_decoder.h pe_loader.h | $(BUILDDIR)
	$(CC) $(CFLAGS) -c driver_extract.c -o $@

# CLI tool (requires full translator implementation)
# cli: $(BUILDDIR)/drv-extract
# $(BUILDDIR)/drv-extract: driver_extract.c | $(BUILDDIR)
# 	$(CC) $(CFLAGS) -DDRIVER_EXTRACT_MAIN -o $@ driver_extract.c

clean:
	rm -rf $(BUILDDIR)
