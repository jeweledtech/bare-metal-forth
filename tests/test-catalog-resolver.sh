#!/bin/bash
# test-catalog-resolver.sh — Integration test for vocabulary catalog and dependency resolver
#
# Tests the complete chain:
#   1. Build kernel image
#   2. Create block disk with catalog + vocabularies
#   3. Boot QEMU with serial TCP
#   4. Load catalog-resolver from blocks
#   5. Verify ORDER shows search order
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

# Step 3: Look up catalog-resolver block location
echo "--- Looking up catalog-resolver block ---"
RESOLVER_INFO=$(python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR/tools')
from importlib.machinery import SourceFileLoader
wc = SourceFileLoader('wc', '$PROJECT_DIR/tools/write-catalog.py').load_module()
vocabs = wc.scan_vocabs('$PROJECT_DIR/forth/dict/')
_nc = (len(vocabs) + wc.CATALOG_DATA_LINES - 1) // wc.CATALOG_DATA_LINES
nb = 1 + _nc
for v in vocabs:
    if v['name'] == 'CATALOG-RESOLVER':
        print(f\"{nb} {v['blocks_needed']}\")
        break
    nb += v['blocks_needed']
" 2>/dev/null)

if [ -z "$RESOLVER_INFO" ]; then
    echo "FATAL: Could not find CATALOG-RESOLVER in block layout"
    exit 1
fi
RESOLVER_BLK=$(echo $RESOLVER_INFO | cut -d' ' -f1)
RESOLVER_CNT=$(echo $RESOLVER_INFO | cut -d' ' -f2)
echo "  Catalog-resolver at block $RESOLVER_BLK ($RESOLVER_CNT blocks)"

# Step 4: Boot QEMU with serial TCP
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

# Step 5: Run all tests over a single persistent TCP connection
echo "--- Running Forth commands ---"

# Build the THRU command for loading resolver
if [ "$RESOLVER_CNT" -eq 1 ]; then
    LOAD_CMD="$RESOLVER_BLK LOAD"
else
    LOAD_CMD="$RESOLVER_BLK DUP $((RESOLVER_CNT - 1)) + THRU"
fi

python3 -c "
import socket, time, sys

PORT = $PORT
RESOLVER_BLK = $RESOLVER_BLK
RESOLVER_CNT = $RESOLVER_CNT
LOAD_CMD = '$LOAD_CMD'

PASS = 0
FAIL = 0

def check(name, response, pattern):
    global PASS, FAIL
    if pattern in response:
        PASS += 1
        print(f'  PASS: {name}')
        return True
    else:
        FAIL += 1
        print(f'  FAIL: {name} - pattern \"{pattern}\" not found in: {response!r}')
        return False

def check_not(name, response, pattern):
    global PASS, FAIL
    if pattern not in response:
        PASS += 1
        print(f'  PASS: {name}')
        return True
    else:
        FAIL += 1
        print(f'  FAIL: {name} - unexpected pattern \"{pattern}\" found in: {response!r}')
        return False

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
s.connect(('127.0.0.1', PORT))

# Drain boot output
time.sleep(1.5)
try:
    while True:
        s.recv(4096)
except socket.timeout:
    pass

def send_cmd(cmd, wait=0.5):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(1)
    resp = b''
    while True:
        try:
            data = s.recv(4096)
            if not data:
                break
            resp += data
        except socket.timeout:
            break
    return resp.decode('ascii', errors='replace')

# Test 1: Basic arithmetic
print('  Testing basic interpreter...')
r = send_cmd('1 2 + .', 0.5)
check('Basic arithmetic (1 2 + .)', r, '3')

# Test 2: WORDS contains expected kernel words
print('  Testing WORDS...')
r = send_cmd('WORDS', 3)
check('WORDS contains BLOCK', r, 'BLOCK')

# Test 3: LIST block 1 shows catalog
print('  Testing catalog block...')
r = send_cmd('1 LIST', 1)
check('Block 1 contains vocabulary catalog', r, 'CATALOG')

# Test 4: Load catalog-resolver from blocks
print(f'  Loading catalog-resolver (block {RESOLVER_BLK}, {RESOLVER_CNT} blocks)...')
r = send_cmd(LOAD_CMD, 5)
check_not('Loaded catalog-resolver (no error)', r, 'rror')

# Test 5: ORDER shows search order
print('  Testing ORDER...')
r = send_cmd('ORDER', 1)
check('ORDER shows search order', r, 'Search:')

# Summary
print()
TOTAL = PASS + FAIL
print(f'--- Results ---')
print(f'Passed: {PASS}/{TOTAL}')
if FAIL > 0:
    print('SOME TESTS FAILED')
    sys.exit(1)
else:
    print('ALL TESTS PASSED')
    sys.exit(0)
" ; TEST_EXIT=$?

exit ${TEST_EXIT}
