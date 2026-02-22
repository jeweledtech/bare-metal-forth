#!/bin/bash
# fetch-reactos-serial.sh — Download ReactOS serial.sys for pipeline validation
#
# ReactOS is GPL-licensed; we download but do not redistribute the binary.
# This script attempts to extract serial.sys from a ReactOS release ISO.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/../tests/data"
OUTPUT="$DATA_DIR/serial.sys"

if [ -f "$OUTPUT" ]; then
    echo "serial.sys already exists at $OUTPUT"
    exit 0
fi

echo "Attempting to download ReactOS serial.sys..."
echo ""
echo "This script needs a ReactOS ISO. You can:"
echo "  1. Download manually from https://reactos.org/download/"
echo "  2. Provide the ISO path as an argument: $0 <path-to-iso>"
echo ""

if [ -n "$1" ] && [ -f "$1" ]; then
    ISO_PATH="$1"
    echo "Using provided ISO: $ISO_PATH"

    # Try to extract with 7z or bsdtar
    TMPDIR=$(mktemp -d)
    trap "rm -rf $TMPDIR" EXIT

    if command -v 7z &>/dev/null; then
        7z x -o"$TMPDIR" "$ISO_PATH" "reactos/system32/drivers/serial.sys" 2>/dev/null || true
    elif command -v bsdtar &>/dev/null; then
        bsdtar -C "$TMPDIR" -xf "$ISO_PATH" "reactos/system32/drivers/serial.sys" 2>/dev/null || true
    fi

    FOUND=$(find "$TMPDIR" -name "serial.sys" -print -quit 2>/dev/null)
    if [ -n "$FOUND" ]; then
        cp "$FOUND" "$OUTPUT"
        echo "Extracted serial.sys to $OUTPUT"
        echo "Size: $(wc -c < "$OUTPUT") bytes"
        exit 0
    else
        echo "Could not find serial.sys in ISO"
        exit 1
    fi
fi

echo "No ISO provided. Please download manually."
echo "Place the file at: $OUTPUT"
exit 1
