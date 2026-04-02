# Claude Code Task: Hardware Port Mapper Vocabulary

## Context

ForthOS is now running interactively on real hardware (HP 15-bs0xx laptop).
The keyboard works. The next step is to use Forth's live execution capability
to explore and map the hardware from the inside — scanning I/O port ranges,
identifying responding devices, and building a picture of the machine's
hardware topology directly from bare metal.

This is the "explore from the inside" capability that made Forth powerful for
embedded and hardware work. The goal is a `PORT-MAPPER` vocabulary that can
be loaded and used interactively at the `ok` prompt on real hardware.

Repository: `~/projects/forthos`
Forth blocks: `forth/dict/` — new vocabulary goes here
Block range: assign blocks 110-125 (check catalog for availability)

---

## Task: Implement `PORT-MAPPER` Vocabulary

### File to create

`forth/dict/port-mapper.fth`

Load range: blocks 110-120 (adjust if occupied — check `forth/dict/catalog.fth`)

---

### Words to implement

#### 1. Basic port probe

```forth
: PORT? ( port -- flag )
```
Returns true if a port appears to respond (not 0xFF = floating bus).
Reads the port byte. Returns 0 if result is 0xFF (no device), -1 otherwise.

```forth
: PORT. ( port -- )
```
Read and print a port value in hex with address. Format: `03F8: 60`

#### 2. Range scanner

```forth
: PORT-SCAN ( start end -- )
```
Scan ports from start to end inclusive. For each port that responds
(not 0xFF), print: `  PORT xxxx = yy` where xxxx is port address in hex
and yy is the byte value in hex. Skip ports that return 0xFF.

Include a small delay between reads (use `US-DELAY` from HARDWARE vocab)
to avoid overwhelming slow SuperIO chips: 10 microseconds per port.

#### 3. Known device identifier

```forth
: PORT-ID ( port -- )
```
Read a port and print a human-readable device name if the address is
in the known table. Print `  xxxx: [device name] = yy` format.

Known port ranges to identify (build as a table of base addresses + names):

| Port(s) | Device |
|---------|--------|
| 0x0020-0x0021 | PIC1 (Interrupt Controller) |
| 0x0040-0x0043 | PIT (Timer 8254) |
| 0x0060, 0x0064 | PS/2 Keyboard/Mouse (8042) |
| 0x0070-0x0071 | CMOS/RTC |
| 0x0080 | POST code port |
| 0x00A0-0x00A1 | PIC2 (Interrupt Controller) |
| 0x01F0-0x01F7 | ATA Primary |
| 0x0170-0x0177 | ATA Secondary |
| 0x02E8-0x02EF | COM4 |
| 0x02F8-0x02FF | COM2 |
| 0x03B0-0x03BF | VGA (mono) |
| 0x03C0-0x03CF | VGA (color, EGA) |
| 0x03D0-0x03DF | VGA (CGA/color) |
| 0x03E8-0x03EF | COM3 |
| 0x03F0-0x03F7 | Floppy controller |
| 0x03F8-0x03FF | COM1 (Serial) |
| 0x0CF8-0x0CFB | PCI Config Address |
| 0x0CFC-0x0CFF | PCI Config Data |

Implement this as a Forth word list scan, not a C table. Each entry is
a base port and a string. Use `DOES>` pattern or simple IF/THEN chain.

#### 4. Standard range scans

```forth
: MAP-LEGACY ( -- )
```
Scan the legacy I/O range 0x0000-0x03FF and print all responding ports
with device identification. This covers all classic PC hardware.
Print a header: `=== Legacy I/O Map (0000-03FF) ===`

```forth
: MAP-EXTENDED ( -- )
```
Scan 0x0400-0x0FFF. Print header: `=== Extended I/O Map (0400-0FFF) ===`

```forth
: MAP-PCI ( -- )
```
Not a port scan — use PCI-SCAN from PCI-ENUM vocabulary if loaded.
If PCI-ENUM not in search order, print: `Load PCI-ENUM first`

#### 5. Register dump words

```forth
: PIC-STATUS ( -- )
```
Read and display PIC1 and PIC2 state:
- PIC1 IMR (0x21): which IRQs are masked
- PIC2 IMR (0xA1): which IRQs are masked
- Print each as a binary-style list: `IRQ0:unmasked IRQ1:unmasked` etc.

```forth
: PIT-STATUS ( -- )
```
Read PIT channel 0 status (0x43 readback command, then 0x40).
Print current timer mode and approximate frequency.

```forth
: CMOS-DUMP ( -- )
```
Dump CMOS/RTC registers 0x00-0x3F. For each, write index to 0x70,
read data from 0x71, print: `CMOS[xx] = yy`
Note: disable NMI during access (set bit 7 of 0x70), restore after.

#### 6. Live monitor

```forth
: PORT-WATCH ( port count -- )
```
Read a port `count` times with a 100ms delay between reads, printing
the value each time. Useful for watching a status register change.
Stop on any keypress (non-blocking key check in loop).

---

### Implementation notes

- Vocabulary header: `VOCABULARY PORT-MAPPER`
- Dependencies: `ALSO HARDWARE` (for `INB`, `US-DELAY`, `C@-PORT`)
- Use `HEX` at start of file, `DECIMAL` at end
- 64-character line limit (hard constraint — Forth block format)
- No word name longer than 31 characters
- Do NOT use `2*` — use `DUP +` instead (not in kernel dictionary)
- All words must work with INB/OUTB kernel primitives directly
- Test in QEMU first with `make test` before USB deployment

---

### QEMU validation

Add to `tests/test_port_mapper.py` (new test file):

```python
# Basic smoke tests for PORT-MAPPER
tests = [
    # Load vocabulary
    ("50 BLOCK LOAD\n209 223 THRU\n110 120 THRU\n", None),  # adjust block range
    # Test PORT? on known-present PIC port (0x20 should not return 0xFF)
    ("USING PORT-MAPPER\nHEX 20 PORT? . DECIMAL\n", "-1"),  # PIC1 present
    # Test PORT? on obviously absent port
    ("USING PORT-MAPPER\nHEX 3FF PORT? . DECIMAL\n", "0"),   # scratch reg absent
]
```

---

### Milestone

When complete, a user can type at the `ok` prompt on real hardware:

```forth
USING PORT-MAPPER
MAP-LEGACY
```

And see every responding I/O port in the 0x0000-0x03FF range with device
names. This is the hardware discovery capability that enables the rest of
the UBT work — knowing what's actually on the machine vs what drivers assume.

---

### Commit message

```
Add PORT-MAPPER vocabulary: hardware I/O port discovery from bare metal

- PORT? PORT. PORT-SCAN PORT-ID: basic probe and identification
- MAP-LEGACY MAP-EXTENDED: full range scans with device names  
- PIC-STATUS PIT-STATUS CMOS-DUMP: register-level hardware state
- PORT-WATCH: live port monitor for status register observation
- Known device table covers standard PC I/O map 0x0000-0x0CFF
```
