# ForthOS UBT: Protocol Validator Design
**Date:** 2026-03-21  
**Status:** Design doc — review with mentor before implementing  
**Commit base:** `93f7142` (234 tests passing)  
**Context:** Structural extraction is proven (234 tests). This doc designs the next level: behavioral correctness against hardware datasheets.

---

## The Gap

Current UBT validation answers: *"did we extract the right functions and filter the right scaffolding?"*

Protocol validation answers: *"does the extracted Forth reproduce the correct hardware interaction sequences?"*

Example: The UART init extracted from `serial.sys` has a function that writes to DLL and DLM. The structural test passes because those register writes exist. The protocol test asks: *was DLAB set before those writes?* Without DLAB, the divisor write goes to the wrong register — the UART silently misbehaves.

This is the difference between correct structure and correct behavior.

---

## Five Validator Categories (Priority Order)

### 1. Port Pairing Rules (index→data)

Several hardware devices use an index port + data port pattern. The index is written first, then data is read or written from the adjacent port. Writing data without the preceding index write is illegal.

**Instances:**
- RTC CMOS: write register index to `0x70`, read/write data from `0x71`
- VGA CRTC: write register index to `0x3D4`, read/write value from `0x3D5`
- VGA attribute controller: write index to `0x3C0`, read from `0x3C1`
- PIT mode: write control word to `0x43`, write counter to `0x40`/`0x41`/`0x42`

**Rule format:**
```
PORT_PAIR(index_port, data_port):
  WRITE(index_port) must precede READ/WRITE(data_port)
  READ(data_port) without preceding WRITE(index_port) = VIOLATION
```

**Implementation:** Walk the extracted Forth words, build a port access event stream, run a state machine that tracks "last written index port" and checks that data port accesses have a corresponding preceding index write.

### 2. Sequence Ordering Constraints

Some hardware protocols require operations in a specific order. Performing them out of order causes undefined behavior.

**UART 16550 init sequence (from datasheet):**
```
Step 1: Write LCR with DLAB=1 (bit 7 set) — enables divisor access
Step 2: Write DLL (port 0x3F8 or base+0) — divisor low byte
Step 3: Write DLM (port 0x3F9 or base+1) — divisor high byte
Step 4: Write LCR with DLAB=0 — disables divisor access, sets word format
Step 5: Write FCR — configure FIFO
Step 6: Write IER — enable interrupts
```

**Violations:**
- Write to DLL/DLM when DLAB=0 (writes go to THR/IER instead)
- Write to IER before FCR (FIFO state undefined)
- Clear DLAB before writing both DLL and DLM

**PIT frequency synthesis sequence:**
```
Step 1: Write control word to 0x43 (select channel + mode)
Step 2: Write divisor low byte to 0x40/0x41/0x42
Step 3: Write divisor high byte to same port (two consecutive writes required)
```

**Violation:** Write to 0x40 twice without preceding 0x43 control word.

### 3. Bitmask Read-Modify-Write Detection

Control registers often have reserved bits or bits owned by other subsystems. Writing a raw value destroys those bits. The correct pattern is read → mask → OR/AND → write.

**PC speaker gate (port 0x61):**
```
Correct:   IN AL, 0x61  /  OR AL, 0x03  /  OUT 0x61, AL
Incorrect: MOV AL, 0x03  /  OUT 0x61, AL  (destroys other bits)
```

**Rule:** For known control registers, any WRITE without a preceding READ of the same register is flagged as a potential RMW violation.

**Known control registers:**
- `0x61` — PC speaker / NMI control (bits 0-1 = speaker, bits 2-7 = system)
- `0x64` — i8042 command port (status register on read)
- LCR, MCR in UART (multiple fields, must preserve unrelated bits)

### 4. Polling Loop Recognition

Hardware drivers frequently busy-wait for a status bit before proceeding. Misidentifying these loops (or missing them) means the extracted Forth hangs or races the hardware.

**Pattern:**
```
LOOP: IN AL, STATUS_PORT
      TEST AL, READY_BIT
      JZ LOOP          ← backward jump to same port read
```

**Forth equivalent:**
```forth
: WAIT-READY ( -- )
  BEGIN STATUS-PORT INB READY-BIT AND UNTIL ;
```

**Validation:** Verify that any extracted word containing a polling pattern produces a Forth word with `BEGIN ... UNTIL` structure, not a fixed-count loop or a single read.

**Known polling patterns:**
- UART: `BEGIN LSR INB 020 AND UNTIL` (TX ready)
- ATA: `BEGIN 1F7 INB 80 AND 0= UNTIL` (BSY clear)
- FDC: `BEGIN 3F4 INB 80 AND UNTIL` (MSR ready)
- i8042: `BEGIN 64 INB 02 AND 0= UNTIL` (input buffer empty)

### 5. Illegal State Detection

Some register writes are only legal in specific hardware modes. Writing outside that mode produces wrong behavior silently.

**UART DLAB mode:**
- DLL (base+0) and DLM (base+1) are only accessible when LCR bit 7 (DLAB) = 1
- When DLAB=0, writes to base+0 go to THR (transmit holding), base+1 goes to IER
- A write to DLL/DLM without DLAB=1 is an illegal state access

**VGA plane select:**
- Sequencer register 02h (map mask) only meaningful when in planar mode
- Writing to VRAM without correct sequencer state produces wrong output

**Detection approach:** Build a symbolic state machine that tracks register values through the extracted Forth word sequence and flags writes that occur in the wrong hardware mode.

---

## Implementation Design

### Phase 1: Port Event Stream (implement first)

Every extracted Forth word is converted to a sequence of port events:

```python
PortEvent = namedtuple('PortEvent', ['port', 'access', 'value', 'word_name'])
# access: 'READ' | 'WRITE'
# value: integer if known statically, None if runtime-determined
```

**Input:** Forth vocabulary output from the translator  
**Parser:** Scan for `INB`/`OUTB`/`C@-PORT`/`C!-PORT` calls and their preceding constant loads

**Example for SerialSetBaudRate:**
```python
[
  PortEvent(0x3FB, 'WRITE', 0x80, 'SerialSetBaudRate'),  # LCR DLAB=1
  PortEvent(0x3F8, 'WRITE', None, 'SerialSetBaudRate'),  # DLL (runtime val)
  PortEvent(0x3F9, 'WRITE', None, 'SerialSetBaudRate'),  # DLM (runtime val)
  PortEvent(0x3FB, 'WRITE', 0x03, 'SerialSetBaudRate'),  # LCR 8N1 DLAB=0
]
```

### Phase 2: Rule DSL

A simple Python DSL for expressing hardware rules:

```python
class PortValidator:
    def pair_rule(self, index_port, data_port, name):
        """Every data_port access must be preceded by index_port write."""
        
    def sequence_rule(self, name, steps):
        """Steps must occur in order within a function's port event stream."""
        # step: ('WRITE', port, mask, expected_value) or ('READ', port)
        
    def rmw_rule(self, port, name):
        """Writes to port must be preceded by read of same port."""
        
    def state_rule(self, guard_port, guard_mask, guard_value,
                   target_port, target_access, name):
        """target_port access only legal when guard_port & mask == value."""
```

**UART rules expressed in DSL:**
```python
v = PortValidator()

# DLAB must be set before divisor writes
v.state_rule(
    guard_port=0x3FB, guard_mask=0x80, guard_value=0x80,  # LCR DLAB=1
    target_port=0x3F8, target_access='WRITE',
    name='UART_DLL_requires_DLAB'
)
v.state_rule(
    guard_port=0x3FB, guard_mask=0x80, guard_value=0x80,
    target_port=0x3F9, target_access='WRITE',
    name='UART_DLM_requires_DLAB'
)

# RTC index→data pairing
v.pair_rule(index_port=0x70, data_port=0x71, name='RTC_index_data')

# PC speaker RMW
v.rmw_rule(port=0x61, name='PC_speaker_gate_RMW')

# PIT control before data
v.sequence_rule('PIT_control_before_data', [
    ('WRITE', 0x43),   # control word
    ('WRITE', 0x42),   # or 0x40/0x41 depending on channel
])
```

### Phase 3: Validator Execution

```python
def validate_vocabulary(fth_path, rules):
    events = parse_port_events(fth_path)
    violations = []
    for rule in rules:
        violations.extend(rule.check(events))
    return violations

# Output format
for v in violations:
    print(f"VIOLATION: {v.rule_name}")
    print(f"  Function: {v.word_name}")
    print(f"  At port: 0x{v.port:02X} ({v.access})")
    print(f"  Detail: {v.detail}")
```

### Phase 4: Integration with Test Suite

Add `test_protocol_validation.c` (or `test_protocol_validation.py`) that:
1. Runs translator against `serial.sys`, `i8042prt.sys`, `floppy.sys`
2. Parses the Forth output into port event streams
3. Applies UART / i8042 / FDC rules respectively
4. Asserts zero violations

This becomes a CI test — structural AND behavioral correctness required before commit.

---

## Scope Boundaries

**In scope for Phase 1 implementation:**
- Port event stream parser (Forth → event list)
- Pair rules (index→data)
- Sequence ordering (UART init, PIT setup)
- Validation against serial.sys and i8042prt.sys

**Deferred to Phase 2:**
- Bitmask RMW detection (requires value tracking)
- Illegal state detection (requires symbolic execution)
- Polling loop recognition (requires control flow analysis)
- Cross-binary differential validation

**Out of scope entirely:**
- Full symbolic execution engine
- Runtime behavioral testing (no hardware simulation)
- Completeness checking (we only check what we have rules for)

---

## Review Checklist Before Implementing

This doc should be reviewed with the mentor alongside the metacompiler discussion because:

1. The LMI manual may document hardware protocol sequences the mentor implemented in the 1990s — those would be ground truth for the rules
2. The mentor's experience with MIRROR/LOOKINGGLASS means they've debugged exactly this class of hardware sequencing bug on real hardware
3. The DSL design should be simple enough to express rules verbally before they're coded — the mentor can validate rules by reading them

**Questions for mentor:**
- What hardware sequencing bugs were most common in the LMI era? (These are the rules worth implementing first)
- Is there a Forth-idiomatic way to express sequence constraints that we're missing?
- Does the LMI manual document any formal hardware protocol verification approach?

---

## Files to Create (When Ready to Implement)

```
tools/translator/
  protocol/
    validator.py          ← Port event stream parser + rule engine
    rules/
      uart_16550.py       ← UART init sequence + DLAB rules
      rtc_cmos.py         ← RTC index→data pairing
      pit_8254.py         ← PIT control→data sequencing
      i8042.py            ← Keyboard controller rules
      fdc_765.py          ← Floppy controller rules (future)
  tests/
    test_protocol_validation.py  ← Integration tests

docs/
  PROTOCOL_VALIDATION.md  ← User-facing documentation
```

---

## Commit Message When Done

`"UBT: add protocol validator — datasheet-driven behavioral assertions for hardware sequences"`
