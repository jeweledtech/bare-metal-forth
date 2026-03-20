#!/usr/bin/env python3
"""Stress test for SAVE-BUFFERS bulk flush with DEBUG_FLUSH tracing.

Requires the debug kernel (bmforth-debug.img) built with -DDEBUG_FLUSH.
Tests 5 scenarios to identify why bulk SAVE-BUFFERS fails for odd-indexed
cache slots while single SAVE-BUFFERS works.
"""
import socket, time, sys, re

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4550

# --- Connection setup ---
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
s.connect(('127.0.0.1', PORT))

time.sleep(1.5)
try:
    while True:
        s.recv(4096)
except:
    pass


def send(cmd, wait=1.0):
    """Send a Forth command, return all serial output."""
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(2)
    resp = b''
    while True:
        try:
            d = s.recv(4096)
            if not d:
                break
            resp += d
        except:
            break
    return resp.decode('ascii', errors='replace')


def send_collect(cmd, wait=1.5):
    """Send command with longer wait for trace output."""
    return send(cmd, wait=wait)


PASS = 0
FAIL = 0
ALL_TRACES = []


def check(name, response, pattern):
    global PASS, FAIL
    if pattern in response:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- expected "{pattern}" in {response.strip()!r}')


def check_val(name, actual, expected):
    """Check a numeric value."""
    global PASS, FAIL
    if actual == expected:
        PASS += 1
        print(f'  PASS: {name} (got {actual})')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- expected {expected}, got {actual}')


def parse_traces(output):
    """Parse F/W/D/[/] trace lines from serial output.

    Returns list of dicts:
      {'type': 'F', 'slot': int, 'block': int, 'flags': int}
      {'type': 'W', 'lba': int, 'esi': int}
      {'type': 'D', 'status': int}
      {'type': '['}  (flush start)
      {'type': ']'}  (flush end)
    """
    traces = []
    for line in output.split('\n'):
        line = line.strip().replace('\r', '')
        if not line:
            continue
        if line == '[':
            traces.append({'type': '['})
        elif line == ']':
            traces.append({'type': ']'})
        elif line.startswith('F') and ' ' in line[1:]:
            # F<slot> <block_hex> <flags_hex>
            m = re.match(r'F(\d)\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)', line)
            if m:
                traces.append({
                    'type': 'F',
                    'slot': int(m.group(1)),
                    'block': int(m.group(2), 16),
                    'flags': int(m.group(3), 16),
                })
        elif line.startswith('W') and ' ' in line[1:]:
            # W<LBA_hex> <ESI_hex>
            m = re.match(r'W([0-9A-Fa-f]+)\s+([0-9A-Fa-f]+)', line)
            if m:
                traces.append({
                    'type': 'W',
                    'lba': int(m.group(1), 16),
                    'esi': int(m.group(2), 16),
                })
        elif line.startswith('D'):
            m = re.match(r'D([0-9A-Fa-f]+)', line)
            if m:
                traces.append({
                    'type': 'D',
                    'status': int(m.group(1), 16),
                })
    return traces


def print_trace_table(traces):
    """Pretty-print trace entries for debugging."""
    if not traces:
        print('    (no trace output)')
        return
    for t in traces:
        if t['type'] == '[':
            print('    --- SAVE-BUFFERS start ---')
        elif t['type'] == ']':
            print('    --- SAVE-BUFFERS end ---')
        elif t['type'] == 'F':
            print(f'    FLUSH slot={t["slot"]} block={t["block"]} '
                  f'flags=0x{t["flags"]:02X} '
                  f'({"dirty" if t["flags"] & 2 else "clean"}'
                  f'{", valid" if t["flags"] & 1 else ""})')
        elif t['type'] == 'W':
            print(f'    WRITE LBA={t["lba"]} ESI=0x{t["esi"]:08X}')
        elif t['type'] == 'D':
            status = t['status']
            bits = []
            if status & 0x01: bits.append('ERR')
            if status & 0x08: bits.append('DRQ')
            if status & 0x20: bits.append('DF')
            if status & 0x40: bits.append('DRDY')
            if status & 0x80: bits.append('BSY')
            print(f'    DONE  ATA=0x{status:02X} ({"|".join(bits) if bits else "ok"})')


def extract_number(response):
    """Extract the last integer before 'ok' from Forth output.

    Forth echoes the input command over serial, so '900 BLOCK C@ . 170 ok'
    has both 900 (from echo) and 170 (from '.'). We want the last one.
    """
    last = None
    for token in response.split():
        if token == 'ok':
            break
        try:
            last = int(token)
        except ValueError:
            continue
    return last


def extract_hex(response):
    """Extract last hex number before 'ok' from Forth output (when BASE=HEX)."""
    last = None
    for token in response.split():
        if token == 'ok':
            break
        try:
            last = int(token, 16)
        except ValueError:
            continue
    return last


# ============================================================================
print('=== Test 1: Bulk flush (the failing case) ===')
# Fill all 4 cache slots with different blocks, UPDATE each, single SAVE-BUFFERS
# ============================================================================

send('EMPTY-BUFFERS')

# Fill 4 slots with distinct patterns (AA, BB, CC, DD)
send('900 BUFFER DUP 1024 170 FILL DROP UPDATE')   # slot 0: 0xAA
send('901 BUFFER DUP 1024 187 FILL DROP UPDATE')   # slot 1: 0xBB
send('902 BUFFER DUP 1024 204 FILL DROP UPDATE')   # slot 2: 0xCC
send('903 BUFFER DUP 1024 221 FILL DROP UPDATE')   # slot 3: 0xDD

# Single bulk flush — this is the operation we're investigating
r = send_collect('SAVE-BUFFERS', wait=3.0)
bulk_traces = parse_traces(r)
ALL_TRACES.append(('Test 1: Bulk SAVE-BUFFERS', bulk_traces))
print('  Trace output:')
print_trace_table(bulk_traces)

# Force disk read-back by clearing cache
send('EMPTY-BUFFERS')
time.sleep(0.5)

# Read back each block and check first byte
r0 = send('900 BLOCK C@ .')
r1 = send('901 BLOCK C@ .')
r2 = send('902 BLOCK C@ .')
r3 = send('903 BLOCK C@ .')

v0 = extract_number(r0)
v1 = extract_number(r1)
v2 = extract_number(r2)
v3 = extract_number(r3)

check_val('block 900 (slot 0)', v0, 170)
check_val('block 901 (slot 1)', v1, 187)
check_val('block 902 (slot 2)', v2, 204)
check_val('block 903 (slot 3)', v3, 221)

# Check trace completeness: should have 4 F entries (one per dirty slot)
flush_entries = [t for t in bulk_traces if t['type'] == 'F']
check_val('bulk flush slot count', len(flush_entries), 4)

# Check for ATA errors in trace
ata_errors = [t for t in bulk_traces if t['type'] == 'D' and (t['status'] & 0x01)]
if ata_errors:
    print(f'  WARNING: ATA errors detected in {len(ata_errors)} write(s)')

# ============================================================================
print()
print('=== Test 2: Single-flush baseline (the working case) ===')
# Same blocks/patterns, but SAVE-BUFFERS after EACH block's UPDATE
# ============================================================================

send('EMPTY-BUFFERS')

send('900 BUFFER DUP 1024 170 FILL DROP UPDATE')
r_s0 = send_collect('SAVE-BUFFERS', wait=2.0)
send('901 BUFFER DUP 1024 187 FILL DROP UPDATE')
r_s1 = send_collect('SAVE-BUFFERS', wait=2.0)
send('902 BUFFER DUP 1024 204 FILL DROP UPDATE')
r_s2 = send_collect('SAVE-BUFFERS', wait=2.0)
send('903 BUFFER DUP 1024 221 FILL DROP UPDATE')
r_s3 = send_collect('SAVE-BUFFERS', wait=2.0)

single_traces = parse_traces(r_s0 + r_s1 + r_s2 + r_s3)
ALL_TRACES.append(('Test 2: Individual SAVE-BUFFERS', single_traces))
print('  Trace output:')
print_trace_table(single_traces)

send('EMPTY-BUFFERS')
time.sleep(0.5)

r0 = send('900 BLOCK C@ .')
r1 = send('901 BLOCK C@ .')
r2 = send('902 BLOCK C@ .')
r3 = send('903 BLOCK C@ .')

check_val('block 900 (single)', extract_number(r0), 170)
check_val('block 901 (single)', extract_number(r1), 187)
check_val('block 902 (single)', extract_number(r2), 204)
check_val('block 903 (single)', extract_number(r3), 221)

# ============================================================================
print()
print('=== Test 3: Verify UPDATE marks correct slot ===')
# Load two blocks, UPDATE only the second. Check flags.
# ============================================================================

send('EMPTY-BUFFERS')
send('900 BUFFER DROP')       # slot 0: valid, NOT dirty
send('901 BUFFER DROP UPDATE')  # slot 1: valid + dirty

# Read header flags via memory access
# Slot 0 header at 0x28060: [block#(4)][flags(4)][age(4)]
# Slot 1 header at 0x2806C: [block#(4)][flags(4)][age(4)]
r_flags0 = send('HEX 28064 @ .')  # slot 0 flags
r_flags1 = send('28070 @ .')      # already in HEX
send('DECIMAL')  # restore base

v_flags0 = extract_hex(r_flags0)
v_flags1 = extract_hex(r_flags1)

# Slot 0 should be valid only (1), slot 1 should be valid+dirty (3)
check_val('slot 0 flags (valid only)', v_flags0, 1)
check_val('slot 1 flags (valid+dirty)', v_flags1, 3)

# ============================================================================
print()
print('=== Test 4: Verify buffer data addresses ===')
# Each BUFFER call should return a distinct address.
# ============================================================================

send('EMPTY-BUFFERS')

r_a0 = send('HEX 900 BUFFER .')
r_a1 = send('901 BUFFER .')
r_a2 = send('902 BUFFER .')
r_a3 = send('903 BUFFER .')
send('DECIMAL')

# Parse hex addresses
a0 = extract_number(r_a0)
a1 = extract_number(r_a1)
a2 = extract_number(r_a2)
a3 = extract_number(r_a3)

# Expected: 0x28200, 0x28600, 0x28A00, 0x28E00
a0 = extract_hex(r_a0)
a1 = extract_hex(r_a1)
a2 = extract_hex(r_a2)
a3 = extract_hex(r_a3)

check_val('buffer 900 addr', a0, 0x28200)
check_val('buffer 901 addr', a1, 0x28600)
check_val('buffer 902 addr', a2, 0x28A00)
check_val('buffer 903 addr', a3, 0x28E00)

# ============================================================================
print()
print('=== Test 5: Cache vs disk coherence ===')
# Write, SAVE-BUFFERS, read from cache, EMPTY-BUFFERS, read from disk.
# Both should return the same value.
# ============================================================================

send('EMPTY-BUFFERS')
send('900 BUFFER DUP 1024 99 FILL DROP UPDATE')  # 0x63
r_save = send_collect('SAVE-BUFFERS', wait=2.0)

# Read from cache (should hit)
r_cached = send('DECIMAL 900 BLOCK C@ .')
v_cached = extract_number(r_cached)

# Force disk read
send('EMPTY-BUFFERS')
time.sleep(0.5)
r_disk = send('900 BLOCK C@ .')
v_disk = extract_number(r_disk)

check_val('cached read', v_cached, 99)
check_val('disk read', v_disk, 99)

# ============================================================================
# Hypothesis analysis
# ============================================================================
print()
print('=== Trace Analysis ===')

# Compare bulk (test 1) vs single (test 2) flush entries
bulk_F = [t for t in bulk_traces if t['type'] == 'F']
bulk_W = [t for t in bulk_traces if t['type'] == 'W']
bulk_D = [t for t in bulk_traces if t['type'] == 'D']

print(f'  Bulk flush:   {len(bulk_F)} F entries, {len(bulk_W)} W entries, {len(bulk_D)} D entries')

single_F = [t for t in single_traces if t['type'] == 'F']
single_W = [t for t in single_traces if t['type'] == 'W']
single_D = [t for t in single_traces if t['type'] == 'D']

print(f'  Single flush: {len(single_F)} F entries, {len(single_W)} W entries, {len(single_D)} D entries')

# H1: Missing flush entries for odd slots?
bulk_slots = sorted([t['slot'] for t in bulk_F])
if bulk_slots != [0, 1, 2, 3]:
    print(f'  >>> H1 CONFIRMED: Missing slots! Got {bulk_slots}, expected [0,1,2,3]')
else:
    print(f'  H1 eliminated: all 4 slots flushed ({bulk_slots})')

# H2: Register corruption (wrong block# or address)?
for t_f, t_w in zip(bulk_F, bulk_W):
    expected_lba = t_f['block'] * 2
    expected_esi = 0x28200 + t_f['slot'] * 1024
    if t_w['lba'] != expected_lba:
        print(f'  >>> H2 CONFIRMED: slot {t_f["slot"]} LBA mismatch: '
              f'expected {expected_lba}, got {t_w["lba"]}')
    if t_w['esi'] != expected_esi:
        print(f'  >>> H2/H4 CONFIRMED: slot {t_f["slot"]} ESI mismatch: '
              f'expected 0x{expected_esi:08X}, got 0x{t_w["esi"]:08X}')

# H3: ATA errors?
for i, t_d in enumerate(bulk_D):
    if t_d['status'] & 0x01:
        print(f'  >>> H3 CONFIRMED: ATA error on write {i}: status=0x{t_d["status"]:02X}')
    if t_d['status'] & 0x20:
        print(f'  >>> H3: Device fault on write {i}: status=0x{t_d["status"]:02X}')

if not any(t['status'] & 0x21 for t in bulk_D):
    print(f'  H3 partial: no ATA errors in status bits')

# H5: Cache vs disk mismatch?
if v_cached != v_disk:
    print(f'  >>> H5 CONFIRMED: cached={v_cached} vs disk={v_disk}')
else:
    print(f'  H5 eliminated: cache and disk agree ({v_cached})')

# ============================================================================
# Summary
# ============================================================================
print()
TOTAL = PASS + FAIL
print(f'Passed: {PASS}/{TOTAL}')
if FAIL > 0:
    print()
    print('Full trace dump for failed test investigation:')
    for label, traces in ALL_TRACES:
        print(f'\n  {label}:')
        print_trace_table(traces)

s.close()
sys.exit(0 if FAIL == 0 else 1)
