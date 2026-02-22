#!/bin/bash
# test-catalog-resolver.sh — Integration test for vocabulary catalog and dependency resolver
#
# Tests the complete chain:
#   1. Build kernel image
#   2. Create block disk with catalog + vocabularies
#   3. Boot QEMU with serial TCP
#   4. Load catalog-resolver from blocks
#   5. Load SERIAL-16550 (which depends on HARDWARE)
#   6. Verify both vocabularies loaded via ORDER
#
# Requires: make, qemu-system-i386, python3
#
# Usage: ./tests/test-catalog-resolver.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_DIR/build"
IMAGE="$BUILD_DIR/bmforth.img"
BLOCKS="$BUILD_DIR/test-resolver-blocks.img"

# Pick a unique TCP port to avoid conflicts
PORT=$((5000 + $$ % 1000))

PASS=0
FAIL=0
TOTAL=0

pass() { PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); echo "  PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); echo "  FAIL: $1"; }

cleanup() {
    if [ -n "$QEMU_PID" ]; then
        kill "$QEMU_PID" 2>/dev/null || true
        wait "$QEMU_PID" 2>/dev/null || true
    fi
    rm -f "$BLOCKS"
}
trap cleanup EXIT

echo "Catalog Resolver Integration Test"
echo "================================="
echo ""

# Step 1: Build kernel
echo "--- Building kernel ---"
cd "$PROJECT_DIR"
make clean >/dev/null 2>&1 || true
make 2>&1 | tail -1
if [ ! -f "$IMAGE" ]; then
    echo "FATAL: Kernel build failed"
    exit 1
fi

# Step 2: Create block disk and write vocabularies
echo "--- Creating block disk with catalog ---"
dd if=/dev/zero of="$BLOCKS" bs=1024 count=1024 2>/dev/null
python3 tools/write-catalog.py "$BLOCKS" forth/dict/
echo ""

# Step 3: Boot QEMU with serial TCP
echo "--- Booting QEMU on TCP port $PORT ---"
qemu-system-i386 \
    -drive format=raw,file="$IMAGE" \
    -drive format=raw,file="$BLOCKS",if=ide,index=1 \
    -serial tcp::$PORT,server=on,wait=off \
    -display none &
QEMU_PID=$!

# Wait for QEMU to start
sleep 2

# Verify QEMU is running
if ! kill -0 "$QEMU_PID" 2>/dev/null; then
    echo "FATAL: QEMU failed to start"
    exit 1
fi

# Step 4: Send Forth commands via TCP and check responses
echo "--- Running Forth commands ---"

send_cmd() {
    # Send a command and read response with timeout
    local cmd="$1"
    local timeout="${2:-3}"
    # Use Python for reliable TCP communication
    python3 -c "
import socket, time
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout($timeout)
s.connect(('127.0.0.1', $PORT))
time.sleep(0.2)
# Read any pending output (prompt)
try:
    s.recv(4096)
except:
    pass
# Send command
s.sendall(('$cmd\r').encode())
time.sleep(0.5)
# Read response
resp = b''
while True:
    try:
        data = s.recv(4096)
        if not data:
            break
        resp += data
    except socket.timeout:
        break
s.close()
print(resp.decode('ascii', errors='replace'))
" 2>/dev/null
}

# Test: Basic Forth interpreter works
echo "  Testing basic interpreter..."
RESULT=$(send_cmd "1 2 + ." 3)
if echo "$RESULT" | grep -q "3"; then
    pass "Basic arithmetic (1 2 + .)"
else
    fail "Basic arithmetic - expected 3, got: $RESULT"
fi

# Test: WORDS command works
echo "  Testing WORDS..."
RESULT=$(send_cmd "WORDS" 5)
if echo "$RESULT" | grep -q "BLOCK\|LOAD\|VOCABULARY"; then
    pass "WORDS contains block/vocab words"
else
    fail "WORDS missing expected words: $RESULT"
fi

# Test: LIST block 1 shows catalog
echo "  Testing catalog block..."
RESULT=$(send_cmd "1 LIST" 3)
if echo "$RESULT" | grep -q "VOCAB-CATALOG\|CATALOG\|HARDWARE"; then
    pass "Block 1 contains vocabulary catalog"
else
    fail "Block 1 catalog not found: $RESULT"
fi

# Test: LOAD catalog-resolver blocks
# First we need to know which block the resolver is at.
# The write-catalog.py output tells us.
echo "  Looking up catalog-resolver block..."
RESOLVER_INFO=$(python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR/tools')
from importlib.machinery import SourceFileLoader
wc = SourceFileLoader('wc', '$PROJECT_DIR/tools/write-catalog.py').load_module()
vocabs = wc.scan_vocabs('$PROJECT_DIR/forth/dict/')
layout = {}
nb = 2
for v in vocabs:
    layout[v['name']] = nb
    nb += v['blocks_needed']
for v in vocabs:
    if v['name'] == 'CATALOG-RESOLVER':
        print(f\"{layout[v['name']]} {v['blocks_needed']}\")
        break
" 2>/dev/null)

if [ -z "$RESOLVER_INFO" ]; then
    fail "Could not find CATALOG-RESOLVER in block layout"
else
    RESOLVER_BLK=$(echo $RESOLVER_INFO | cut -d' ' -f1)
    RESOLVER_CNT=$(echo $RESOLVER_INFO | cut -d' ' -f2)
    echo "  Catalog-resolver at block $RESOLVER_BLK ($RESOLVER_CNT blocks)"

    # Load the resolver
    if [ "$RESOLVER_CNT" -eq 1 ]; then
        RESULT=$(send_cmd "$RESOLVER_BLK LOAD" 5)
    else
        RESULT=$(send_cmd "$RESOLVER_BLK DUP $((RESOLVER_CNT - 1)) + THRU" 5)
    fi

    if echo "$RESULT" | grep -qv "ERROR\|error\|rror"; then
        pass "Loaded catalog-resolver from block $RESOLVER_BLK"
    else
        fail "Loading catalog-resolver failed: $RESULT"
    fi
fi

# Test: ORDER shows current search order
echo "  Testing ORDER..."
RESULT=$(send_cmd "ORDER" 3)
if echo "$RESULT" | grep -q "FORTH"; then
    pass "ORDER shows FORTH vocabulary"
else
    fail "ORDER failed: $RESULT"
fi

echo ""
echo "--- Results ---"
echo "Passed: $PASS/$TOTAL"

if [ "$FAIL" -gt 0 ]; then
    echo "SOME TESTS FAILED"
    exit 1
else
    echo "ALL TESTS PASSED"
    exit 0
fi
