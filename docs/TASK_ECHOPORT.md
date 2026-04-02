# Claude Code Task: ECHOPORT — Live Hardware Port Activity Recorder

## Background

The mentor on this project described a word from LMI Forth called `ECHOPORT`
that watched a running program and recorded every I/O port it touched. This
is the complement to PORT-MAPPER (which statically probes all ports) — 
ECHOPORT is a dynamic hardware trace: run any Forth code, see exactly which
ports it hits, in what order, with what values.

This connects directly to the UBT pipeline goal: the translator extracts port
accesses from Windows driver binaries statically. ECHOPORT does the same thing
live — run translated driver code in ForthOS and verify it hits the same ports
the static analysis predicted. This is the validation bridge between the two
systems.

## Repository

Location: `~/projects/forthos`
Primary file to modify: `src/kernel/forth.asm`
New vocabulary: `forth/dict/echoport.fth`

## Architecture

ECHOPORT works by wrapping the kernel's `INB`, `OUTB`, `INW`, `OUTW`, `INL`,
`OUTL` primitives. When tracing is enabled, every port I/O call logs to a
ring buffer before executing. The Forth programmer can then dump the log.

### Two-layer design

**Layer 1 — Kernel hooks (in forth.asm):**
Add tracing hooks directly into the INB/OUTB/INW/OUTW/INL/OUTL kernel words.
Each hook checks a `trace_enabled` flag. If set, writes a log entry to a
ring buffer before executing the real I/O.

**Layer 2 — ECHOPORT vocabulary (echoport.fth):**
Forth words to control tracing and display results. Loaded as an embedded
vocabulary (add to embed-vocabs.py list alongside HARDWARE and PORT-MAPPER).

---

## Part 1: Kernel Changes (forth.asm)

### Log buffer layout

Add to kernel data section:

```nasm
; ECHOPORT trace buffer
TRACE_BUF_SIZE  equ 256         ; 256 entries max
TRACE_ENTRY_SZ  equ 8           ; 8 bytes per entry

; Entry format (8 bytes):
;   byte 0: type (0=INB, 1=OUTB, 2=INW, 3=OUTW, 4=INL, 5=OUTL)
;   byte 1: reserved/pad
;   word 2: port address (16-bit)
;   dword 4: value read or written (32-bit)

trace_enabled:  db 0            ; 0=off, 1=on
trace_head:     dd 0            ; next write index (0-255)
trace_count:    dd 0            ; total entries logged (may exceed 256)
trace_buf:      times (TRACE_BUF_SIZE * TRACE_ENTRY_SZ) db 0
```

### Tracing macro

Add a macro `TRACE_PORT` that takes type, port (DX), value (AL/AX/EAX):

```nasm
%macro TRACE_PORT 1             ; arg = type byte
    push eax
    push ebx
    push edi
    cmp byte [trace_enabled], 0
    je %%skip
    ; Compute write slot: (trace_head % TRACE_BUF_SIZE) * TRACE_ENTRY_SZ
    mov edi, [trace_head]
    and edi, (TRACE_BUF_SIZE - 1)
    imul edi, TRACE_ENTRY_SZ
    add edi, trace_buf
    ; Write entry
    mov byte [edi], %1          ; type
    mov byte [edi+1], 0         ; pad
    mov [edi+2], dx             ; port
    mov [edi+4], eax            ; value (already in EAX from caller)
    ; Advance head
    inc dword [trace_head]
    inc dword [trace_count]
%%skip:
    pop edi
    pop ebx
    pop eax
%endmacro
```

### Hook each I/O primitive

Find the existing INB, OUTB, INW, OUTW, INL, OUTL kernel words and add
TRACE_PORT calls. The value must be in EAX at the time of the trace call.

For INB (reads port, result goes on stack):
```nasm
; Before: reads port from stack into AL
; After adding trace:
do_INB:
    pop edx             ; port number
    in al, dx           ; read
    movzx eax, al       ; zero-extend
    TRACE_PORT 0        ; type=INB, port in DX, value in EAX
    push eax
    NEXT
```

For OUTB (writes value to port):
```nasm
; Stack: ( value port -- )
do_OUTB:
    pop edx             ; port
    pop eax             ; value
    TRACE_PORT 1        ; type=OUTB, port in DX, value in EAX
    out dx, al          ; write
    NEXT
```

Apply same pattern to INW (type=2), OUTW (type=3), INL (type=4), OUTL (type=5).

**Important:** For IN instructions, trace AFTER the read (so value is captured).
For OUT instructions, trace BEFORE the write (value is still available).

---

## Part 2: ECHOPORT Vocabulary (echoport.fth)

File: `forth/dict/echoport.fth`

### Words to implement

```forth
ECHOPORT-ON  ( -- )
```
Enable port tracing. Sets trace_enabled=1, resets trace_head=0, trace_count=0.
Prints: `ECHOPORT: tracing on`

```forth
ECHOPORT-OFF  ( -- )
```
Disable port tracing. Sets trace_enabled=0.
Prints: `ECHOPORT: tracing off (N entries)`

```forth
ECHOPORT-CLEAR  ( -- )
```
Clear the trace buffer without stopping tracing.

```forth
ECHOPORT-COUNT  ( -- n )
```
Return number of entries logged (may be > 256 if buffer wrapped).

```forth
ECHOPORT-DUMP  ( -- )
```
Print all entries in the trace buffer (up to 256). Format:
```
  #000: INB  port=0020 val=FF
  #001: OUTB port=0021 val=FB
  #002: INB  port=0040 val=34
```
Type names: INB OUTB INW OUTW INL OUTL

```forth
ECHOPORT-SUMMARY  ( -- )
```
Print a de-duplicated summary of unique ports accessed, sorted by port address.
For each unique port: show port address, access type(s), and access count.
Format:
```
  ECHOPORT SUMMARY: 5 unique ports, 12 total accesses
  port=0020: INB x3  OUTB x1
  port=0021: INB x1  OUTB x2
  port=0040: INB x4
  port=0060: INB x1
```

```forth
ECHOPORT-WATCH  ( xt -- )
```
Execute word at xt with tracing on, then automatically call ECHOPORT-SUMMARY.
Usage: `' map-legacy ECHOPORT-WATCH`
This is the main user-facing word — one command to trace any Forth word.

### Implementation notes

- Vocabulary header: `VOCABULARY ECHOPORT`
- Dependencies: `ALSO HARDWARE` for hex printing helpers
- Use local `.H2` `.H4` hex print helpers (same pattern as PORT-MAPPER)
- 64-character line limit
- Do NOT use `2*` — use `DUP +`
- The trace buffer is in kernel memory — access via absolute addresses
  (expose trace_enabled, trace_head, trace_count, trace_buf as kernel
  variables accessible from Forth, similar to how VAR_HERE is exposed)

### Kernel variable exposure

Add these as named variables accessible from Forth (in forth.asm data section,
accessible via their absolute addresses). The ECHOPORT vocabulary accesses
them directly:

```nasm
; These are referenced by ECHOPORT vocabulary
; Expose addresses as Forth CREATEd variables or just use literal addresses
; that echoport.fth hardcodes (simpler — addresses are fixed at link time)
```

Simpler approach: in echoport.fth, define constants for the fixed addresses:
```forth
\ These addresses are fixed in the kernel binary
\ Verify against forth.asm data section after building
HEX
XXXXXXXX CONSTANT TRACE-ENABLED-ADDR
XXXXXXXX CONSTANT TRACE-HEAD-ADDR  
XXXXXXXX CONSTANT TRACE-COUNT-ADDR
XXXXXXXX CONSTANT TRACE-BUF-ADDR
DECIMAL
```

**Better approach:** Add kernel words that return these addresses:
```nasm
defword "TRACE-ENABLED", do_TRACE_ENABLED
    push trace_enabled
    NEXT

defword "TRACE-HEAD", do_TRACE_HEAD  
    push trace_head
    NEXT

defword "TRACE-COUNT", do_TRACE_COUNT
    push trace_count
    NEXT

defword "TRACE-BUF", do_TRACE_BUF
    push trace_buf
    NEXT
```

Then in echoport.fth:
```forth
: ECHOPORT-ON  1 TRACE-ENABLED C! 0 TRACE-HEAD ! 0 TRACE-COUNT ! ;
: ECHOPORT-OFF 0 TRACE-ENABLED C! ;
```

---

## Part 3: Add to Embedded Vocabularies

Update `tools/embed-vocabs.py` Makefile line to include echoport.fth:

```makefile
EMBED_VOCABS = forth/dict/hardware.fth forth/dict/port-mapper.fth \
               forth/dict/echoport.fth
```

Also add `ECHOPORT-ON` and `ECHOPORT-OFF` to the STRIP_INIT_CALLS set in
embed-vocabs.py (though echoport.fth probably has no auto-init calls).

---

## Part 4: Tests

File: `tests/test_echoport.py`

Tests:
1. ECHOPORT vocabulary loads
2. `USING ECHOPORT` succeeds
3. `ECHOPORT-ON` sets trace_enabled (TRACE-ENABLED C@ returns 1)
4. `ECHOPORT-OFF` clears trace_enabled
5. After ECHOPORT-ON, executing `HEX 20 INB DROP` logs one entry
6. ECHOPORT-COUNT returns 1 after one INB
7. ECHOPORT-DUMP prints "INB" and "0020"
8. ECHOPORT-SUMMARY prints "1 unique ports"
9. ECHOPORT-CLEAR resets count to 0
10. ECHOPORT-WATCH executes a word and prints summary
11. Buffer wrap: log 300 entries, ECHOPORT-COUNT returns 300, DUMP shows 256
12. System alive after all tests
13. Stack clean

Add `test_echoport` to Makefile test-vocabs loop.

---

## Usage example on real hardware

```forth
USING ECHOPORT
USING PORT-MAPPER

\ Trace what MAP-LEGACY touches
ECHOPORT-ON
MAP-LEGACY
ECHOPORT-OFF
ECHOPORT-SUMMARY
```

Output will show every port read during the legacy I/O scan — which ports
responded, in what order, with what values. This is the live complement to
the UBT static analysis.

```forth
\ Trace a single device interaction
ECHOPORT-ON
PIC-STATUS
ECHOPORT-OFF
ECHOPORT-DUMP
```

Shows exactly which PIC registers were read, in order, with values.

---

## Connection to UBT pipeline

When translated Windows driver code runs in ForthOS (future milestone),
ECHOPORT validates the translation:

1. UBT static analysis predicts: "this driver reads port 0x1F7, writes 0x1F6"
2. Run translated code with ECHOPORT-ON
3. ECHOPORT-SUMMARY shows actual runtime port accesses
4. Compare static prediction vs dynamic reality

Mismatches reveal translation errors or conditional port access paths that
static analysis missed.

---

## Commit message

```
Add ECHOPORT: live hardware port activity recorder

- Kernel hooks on INB/OUTB/INW/OUTW/INL/OUTL with 256-entry ring buffer
- TRACE-ENABLED TRACE-HEAD TRACE-COUNT TRACE-BUF kernel words
- ECHOPORT vocabulary: ECHOPORT-ON/OFF/CLEAR/DUMP/SUMMARY/WATCH
- ECHOPORT-WATCH: trace any Forth word with one command
- Embedded in kernel image (no block storage needed)
- Validates UBT static analysis against live runtime behavior
```
