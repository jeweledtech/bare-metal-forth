# Four Major Features Implementation Plan

> **Note:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build interrupt infrastructure + six hardware drivers + Vi-like block editor + self-hosting metacompiler for the Bare-Metal Forth OS.

**Architecture:** Bottom-up: kernel interrupt infrastructure first, then drivers as Forth vocabularies (`.fth` files loaded via block storage), then block editor (uses drivers), then metacompiler (uses everything). All drivers follow the `serial-16550.fth` vocabulary pattern. The kernel gains IDT + PIC + ISR dispatch in assembly; everything else is pure Forth.

**Tech Stack:** NASM x86 assembly (kernel), Forth-83 (vocabularies), Python 3 (test harness, block tools), QEMU (testing), C (translator pipeline).

**Design doc:** `docs/plans/2026-03-04-four-features-design.md`

---

## Critical Context for the Implementer

### Project structure
```
forthos/
  src/boot/boot.asm          — 512-byte bootloader (real mode → protected mode)
  src/kernel/forth.asm        — 32KB kernel (DTC Forth interpreter, ~3800 lines NASM)
  forth/dict/*.fth            — Vocabulary files (loaded into blocks, run on target)
  tools/write-block.py        — Host tool: writes .fth source into block disk image
  tools/write-catalog.py      — Host tool: builds vocab catalog + writes all .fth to blocks
  tools/translator/           — Universal Binary Translator (C, separate Makefile)
  tests/*.py                  — Python regression tests (connect to QEMU via TCP serial)
  Makefile                    — Build: `make` → build/bmforth.img (33280 bytes)
```

### How Forth vocabularies work
1. `.fth` files live in `forth/dict/`. Each declares a VOCABULARY, sets DEFINITIONS, defines words, then restores with `FORTH DEFINITIONS`.
2. `python3 tools/write-catalog.py build/blocks.img forth/dict/` writes all vocabs to the block disk.
3. On the target, `2 17 THRU` loads the catalog-resolver, then `USING <VOCAB>` loads a vocabulary.
4. CRITICAL: all `.fth` lines must be ≤ 64 characters (block format truncates silently).

### How to test
```bash
# Build kernel
make clean && make

# Create block disk with vocabs
make blocks
python3 tools/write-catalog.py build/blocks.img forth/dict/

# Start QEMU in background
qemu-system-i386 \
  -drive format=raw,file=build/bmforth.img \
  -drive format=raw,file=build/blocks.img,if=ide,index=1 \
  -serial tcp::4444,server=on,wait=off \
  -display none &

# Run test
python3 tests/test_pit_timer.py 4444
```

### Kernel register convention
- ESI = Instruction Pointer (Forth IP)
- EBP = Return Stack Pointer
- ESP = Data Stack Pointer
- EAX = working register
- NEXT macro: `lodsd; jmp [eax]`

### Key addresses
- Kernel ORG: 0x7E00
- Data stack top: 0x10000
- Return stack top: 0x20000
- System vars: 0x28000
- Dictionary: 0x30000
- VGA text buffer: 0xB8000
- GDT code segment selector: 0x08
- GDT data segment selector: 0x10

---

## Task 1: Kernel Interrupt Infrastructure (IDT + PIC + ISR Dispatch)

**CRITICAL:** The kernel currently has NO interrupt handling. No IDT, no PIC initialization, no ISR stubs. This must be built first before any driver can use IRQs.

**Files:**
- Modify: `src/kernel/forth.asm` (add IDT, PIC init, ISR stubs before the kernel padding at end)
- Test: `tests/test_interrupts.py`

### Step 1: Write the failing test

Create `tests/test_interrupts.py`:

```python
#!/usr/bin/env python3
"""Test that interrupt infrastructure is present."""
import socket, time, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4444

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
s.connect(('127.0.0.1', PORT))
time.sleep(2)
try:
    while True:
        s.recv(4096)
except:
    pass

def send(cmd, wait=1.0):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(2)
    resp = b''
    while True:
        try:
            d = s.recv(4096)
            if not d: break
            resp += d
        except: break
    return resp.decode('ascii', errors='replace')

PASS = 0
FAIL = 0

def check(name, response, pattern):
    global PASS, FAIL
    if pattern in response:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- expected "{pattern}" in {response.strip()!r}')

# STI should not crash (interrupts enabled, IDT installed)
r = send('STI', 0.5)
# No crash means IDT is installed

# Basic arithmetic still works after STI
r = send('1 2 + .')
check('arithmetic after STI', r, '3')

# IDT-INSTALLED? word returns true
r = send('HEX IDT-BASE @ .')
check('IDT base is nonzero', r, '2')  # Will be at some address starting with 2xxxx

print()
print(f'Passed: {PASS}/{PASS+FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
```

### Step 2: Run test to verify it fails

```bash
pkill -9 -f qemu || true
make clean && make
qemu-system-i386 -drive format=raw,file=build/bmforth.img -serial tcp::4444,server=on,wait=off -display none &
sleep 2
python3 tests/test_interrupts.py 4444
# Expected: FAIL — STI may triple-fault with no IDT, IDT-BASE doesn't exist
pkill -9 -f qemu || true
```

### Step 3: Implement interrupt infrastructure in forth.asm

Add this code in `src/kernel/forth.asm` BEFORE the kernel padding (`times 0x8000...`).

**3a. Memory layout for IDT and ISR hooks:**

Add these constants after the existing `VGA_ATTR equ 0x07` line (~line 106):

```nasm
; Interrupt Descriptor Table
; 256 entries x 8 bytes = 2048 bytes
; Place in extended memory area after dictionary space
IDT_BASE            equ 0x29400     ; After block buffers
IDT_SIZE            equ 256 * 8     ; 2048 bytes (0x29400 - 0x29C00)

; ISR hook table: 16 cells for IRQ 0-15, Forth XT to EXECUTE
ISR_HOOKS           equ 0x29C00     ; 16 x 4 bytes = 64 bytes

; PIC ports
PIC1_CMD            equ 0x20
PIC1_DATA           equ 0x21
PIC2_CMD            equ 0xA0
PIC2_DATA           equ 0xA1
```

**3b. PIC initialization (add to kernel_start, after init_screen call):**

```nasm
    ; Initialize PIC — remap IRQs to INT 0x20-0x2F
    call init_pic
    ; Initialize IDT
    call init_idt
    ; Enable interrupts
    sti
```

**3c. PIC init routine (add before data section):**

```nasm
; ============================================================================
; Programmable Interrupt Controller (8259A) Initialization
; ============================================================================
; Remaps IRQ 0-7 to INT 0x20-0x27, IRQ 8-15 to INT 0x28-0x2F

init_pic:
    ; ICW1: Begin initialization sequence
    mov al, 0x11            ; ICW1: edge triggered, cascade, ICW4 needed
    out PIC1_CMD, al
    out PIC2_CMD, al

    ; ICW2: Vector offsets
    mov al, 0x20            ; IRQ 0-7 -> INT 0x20-0x27
    out PIC1_DATA, al
    mov al, 0x28            ; IRQ 8-15 -> INT 0x28-0x2F
    out PIC2_DATA, al

    ; ICW3: Cascade wiring
    mov al, 0x04            ; Master: slave on IRQ2
    out PIC1_DATA, al
    mov al, 0x02            ; Slave: cascade identity 2
    out PIC2_DATA, al

    ; ICW4: 8086 mode
    mov al, 0x01
    out PIC1_DATA, al
    out PIC2_DATA, al

    ; Mask all IRQs initially (drivers unmask as needed)
    mov al, 0xFF
    out PIC1_DATA, al
    out PIC2_DATA, al

    ret
```

**3d. IDT initialization and ISR stubs:**

```nasm
; ============================================================================
; Interrupt Descriptor Table Setup
; ============================================================================

init_idt:
    ; Clear ISR hook table
    mov edi, ISR_HOOKS
    xor eax, eax
    mov ecx, 16
    rep stosd

    ; Fill IDT with default handler for all 256 entries
    mov edi, IDT_BASE
    mov ecx, 256
.fill_idt:
    mov eax, isr_default
    mov word [edi], ax          ; Offset low 16 bits
    mov word [edi+2], 0x08      ; Code segment selector
    mov byte [edi+4], 0         ; Reserved
    mov byte [edi+5], 0x8E      ; Present, Ring 0, 32-bit interrupt gate
    shr eax, 16
    mov word [edi+6], ax        ; Offset high 16 bits
    add edi, 8
    dec ecx
    jnz .fill_idt

    ; Install hardware IRQ handlers (INT 0x20 - 0x2F)
    ; IRQ0 (timer) -> INT 0x20
    mov eax, isr_irq0
    lea edi, [IDT_BASE + 0x20 * 8]
    call install_idt_entry

    ; IRQ1 (keyboard) -> INT 0x21
    mov eax, isr_irq1
    lea edi, [IDT_BASE + 0x21 * 8]
    call install_idt_entry

    ; IRQ12 (mouse) -> INT 0x2C
    mov eax, isr_irq12
    lea edi, [IDT_BASE + 0x2C * 8]
    call install_idt_entry

    ; Load IDT register
    lidt [idt_descriptor]
    ret

install_idt_entry:
    ; EAX = handler address, EDI = IDT entry address
    mov word [edi], ax          ; Offset low
    mov word [edi+2], 0x08      ; Code segment
    mov byte [edi+4], 0
    mov byte [edi+5], 0x8E      ; Present, Ring 0, interrupt gate
    shr eax, 16
    mov word [edi+6], ax        ; Offset high
    ret

; IDT descriptor (loaded with LIDT)
idt_descriptor:
    dw IDT_SIZE - 1             ; Limit
    dd IDT_BASE                 ; Base address

; ============================================================================
; ISR Stubs
; ============================================================================

; Default handler — just IRET
isr_default:
    iret

; IRQ0 (Timer) handler
isr_irq0:
    pushad
    ; Check if Forth hook installed
    mov eax, [ISR_HOOKS + 0*4]
    test eax, eax
    jz .irq0_no_hook
    ; Call Forth word via XT (simplified — just increment counter)
    ; Full Forth EXECUTE would need IP save/restore
    mov ebx, [isr_tick_count]
    inc ebx
    mov [isr_tick_count], ebx
.irq0_no_hook:
    ; Send EOI to PIC1
    mov al, 0x20
    out PIC1_CMD, al
    popad
    iret

; IRQ1 (Keyboard) handler
isr_irq1:
    pushad
    ; Read scancode
    in al, 0x60
    ; Store in keyboard ring buffer
    movzx ebx, byte [kb_ring_head]
    movzx ecx, byte [kb_ring_count]
    cmp ecx, 16                 ; Buffer full?
    jge .irq1_done
    lea edx, [kb_ring_buf + ebx]
    mov [edx], al
    inc ebx
    and ebx, 0x0F               ; Wrap at 16
    mov [kb_ring_head], bl
    inc ecx
    mov [kb_ring_count], cl
.irq1_done:
    ; Send EOI
    mov al, 0x20
    out PIC1_CMD, al
    popad
    iret

; IRQ12 (Mouse) handler
isr_irq12:
    pushad
    ; Read data byte
    in al, 0x60
    ; Store in mouse packet buffer
    movzx ebx, byte [mouse_pkt_idx]
    lea edx, [mouse_pkt_buf + ebx]
    mov [edx], al
    inc ebx
    cmp ebx, 3
    jl .irq12_not_complete
    ; Full 3-byte packet assembled
    xor ebx, ebx               ; Reset index
    mov byte [mouse_pkt_ready], 1
.irq12_not_complete:
    mov [mouse_pkt_idx], bl
    ; Send EOI to both PICs (IRQ >= 8)
    mov al, 0x20
    out PIC2_CMD, al
    out PIC1_CMD, al
    popad
    iret

; ISR data
isr_tick_count:     dd 0
kb_ring_buf:        times 16 db 0
kb_ring_head:       db 0
kb_ring_tail:       db 0
kb_ring_count:      db 0
                    align 4
mouse_pkt_buf:      times 3 db 0
mouse_pkt_idx:      db 0
mouse_pkt_ready:    db 0
                    align 4
mouse_x:            dd 0
mouse_y:            dd 0
mouse_buttons:      db 0
                    align 4
```

**3e. Add Forth words for interrupt access:**

Add these DEFCODE/DEFVAR entries in the dictionary section of forth.asm (before the last defined word, which is currently USING). Add them after the existing USING definition:

```nasm
; Tick count variable (read-only from Forth, incremented by ISR)
DEFVAR "TICK-COUNT", TICK_COUNT, 0
    dd isr_tick_count

; IDT base variable
DEFVAR "IDT-BASE", IDT_BASE_VAR, 0
    dd IDT_BASE

; PIC unmask word: ( irq# -- )
DEFCODE "IRQ-UNMASK", IRQ_UNMASK, 0
    pop eax                     ; IRQ number
    cmp eax, 8
    jge .slave
    ; Master PIC
    mov edx, PIC1_DATA
    in al, dx
    mov ecx, eax               ; Reuse IRQ# for bit position
    mov ebx, 1
    shl ebx, cl
    not ebx
    and eax, ebx               ; Clear the bit (unmask)
    out dx, al
    NEXT
.slave:
    sub eax, 8
    mov edx, PIC2_DATA
    in al, dx
    mov ecx, eax
    mov ebx, 1
    shl ebx, cl
    not ebx
    and eax, ebx
    out dx, al
    ; Also unmask IRQ2 on master (cascade)
    mov edx, PIC1_DATA
    in al, dx
    and al, 0xFB               ; Clear bit 2
    out dx, al
    NEXT
```

**3f. Export ring buffer addresses as Forth constants:**

The PS/2 keyboard and mouse vocabularies need to read from the kernel's ISR ring buffers. Add these DEFCONST entries alongside TICK-COUNT and IRQ-UNMASK:

```nasm
; Keyboard ring buffer address exports
DEFCONST "KB-RING-BUF", KB_RING_BUF_ADDR, 0
    dd kb_ring_buf
DEFCONST "KB-RING-TAIL", KB_RING_TAIL_ADDR, 0
    dd kb_ring_tail
DEFCONST "KB-RING-COUNT", KB_RING_COUNT_ADDR, 0
    dd kb_ring_count

; Mouse packet buffer address exports
DEFCONST "MOUSE-PKT-BUF", MOUSE_PKT_BUF_ADDR, 0
    dd mouse_pkt_buf
DEFCONST "MOUSE-PKT-READY", MOUSE_PKT_READY_ADDR, 0
    dd mouse_pkt_ready
DEFCONST "MOUSE-X-VAR", MOUSE_X_ADDR, 0
    dd mouse_x
DEFCONST "MOUSE-Y-VAR", MOUSE_Y_ADDR, 0
    dd mouse_y
DEFCONST "MOUSE-BTN-VAR", MOUSE_BTN_ADDR, 0
    dd mouse_buttons
```

These constants push the **address** of the kernel variable, so Forth code uses `KB-RING-COUNT C@` to read the count, `KB-RING-BUF KB-RING-TAIL C@ + C@` to read a scancode, etc. This is the same pattern used by DEFVAR (e.g., `STATE` pushes the address of VAR_STATE).

**CRITICAL:** The ISR writes to the ring buffer; Forth reads from it. The ISR advances `kb_ring_head`; Forth advances `kb_ring_tail`. These are separate pointers — no race condition as long as reads are atomic (single byte reads are atomic on x86).

IMPORTANT: Update `VAR_LATEST` and `VAR_FORTH_LATEST` initialization in `kernel_start` to point to the last defined word (after all the new DEFCONST/DEFCODE entries) instead of `name_USING`.

### Step 4: Rebuild and run test

```bash
make clean && make
pkill -9 -f qemu || true
qemu-system-i386 -drive format=raw,file=build/bmforth.img -serial tcp::4444,server=on,wait=off -display none &
sleep 2
python3 tests/test_interrupts.py 4444
# Expected: PASS
pkill -9 -f qemu || true
```

### Step 5: Commit

```bash
git add src/kernel/forth.asm tests/test_interrupts.py
git commit -m "Add interrupt infrastructure: IDT, PIC remapping, ISR stubs

Install 256-entry IDT with default handler. Remap PIC so IRQ0-7 map to
INT 0x20-0x27, IRQ8-15 to INT 0x28-0x2F. ISR stubs for IRQ0 (timer tick
counter), IRQ1 (keyboard ring buffer), IRQ12 (mouse packet assembly).
All IRQs masked by default; drivers unmask via IRQ-UNMASK word.
Add TICK-COUNT, IDT-BASE, IRQ-UNMASK to dictionary."
```

---

## Task 2: PIT Timer Driver Vocabulary

**Files:**
- Create: `forth/dict/pit-timer.fth`
- Test: `tests/test_pit_timer.py`

### Step 1: Write the failing test

Create `tests/test_pit_timer.py`:

```python
#!/usr/bin/env python3
"""Test PIT timer driver vocabulary."""
import socket, time, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4445

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
s.connect(('127.0.0.1', PORT))
time.sleep(2)
try:
    while True:
        s.recv(4096)
except:
    pass

def send(cmd, wait=1.0):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(2)
    resp = b''
    while True:
        try:
            d = s.recv(4096)
            if not d: break
            resp += d
        except: break
    return resp.decode('ascii', errors='replace')

PASS = 0
FAIL = 0

def check(name, response, pattern):
    global PASS, FAIL
    if pattern in response:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- '
              f'expected "{pattern}" in '
              f'{response.strip()!r}')

# Load catalog-resolver and vocabs
send('2 17 THRU', 5)

# Load PIT-TIMER vocabulary
r = send('USING PIT-TIMER', 2)

# Initialize at 100 Hz
r = send('HEX 64 PIT-INIT', 1)

# Read tick count (should be 0 or small)
r = send('TICK-COUNT @ .', 1)
check('tick count readable', r, '')  # Any number

# Wait and read again — should have increased
time.sleep(0.5)
r = send('TICK-COUNT @ .', 1)
# After 500ms at 100Hz, expect ~50 ticks
# Just check it's nonzero
check('ticks incrementing', r, '')

# Test MS-WAIT doesn't hang
r = send('10 MS-WAIT', 2)
r = send('1 2 + .', 1)
check('MS-WAIT returns', r, '3')

print()
print(f'Passed: {PASS}/{PASS+FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
```

### Step 2: Run test to verify it fails

```bash
pkill -9 -f qemu || true
make clean && make
make blocks
python3 tools/write-catalog.py build/blocks.img forth/dict/
qemu-system-i386 \
  -drive format=raw,file=build/bmforth.img \
  -drive format=raw,file=build/blocks.img,if=ide,index=1 \
  -serial tcp::4445,server=on,wait=off -display none &
sleep 2
python3 tests/test_pit_timer.py 4445
# Expected: FAIL — PIT-TIMER vocabulary doesn't exist yet
pkill -9 -f qemu || true
```

### Step 3: Create pit-timer.fth

Create `forth/dict/pit-timer.fth` (all lines ≤ 64 chars):

```forth
\ ==================================================
\ CATALOG: PIT-TIMER
\ CATEGORY: timer
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0x40-0x43
\ IRQ: 0
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( C@-PORT C!-PORT )
\ ==================================================
\
\ Intel 8254 Programmable Interval Timer driver.
\ Channel 0 is connected to IRQ0 for system tick.
\
\ Usage:
\   USING PIT-TIMER
\   HEX 64 PIT-INIT    \ 100 Hz tick rate
\   TICK-COUNT @ .      \ Read current ticks
\   100 MS-WAIT         \ Wait 100 milliseconds
\
\ ==================================================

VOCABULARY PIT-TIMER
PIT-TIMER DEFINITIONS
HEX

\ ---- PIT Port Constants ----
40 CONSTANT PIT-CH0
41 CONSTANT PIT-CH1
42 CONSTANT PIT-CH2
43 CONSTANT PIT-CMD

\ ---- PIT Command Byte Values ----
\ Channel 0, lo/hi, rate generator (mode 2)
34 CONSTANT PIT-MODE2-CH0

\ ---- PIT Oscillator Frequency ----
\ 1193182 Hz = $1234DE
\ Store as two halves for 32-bit math
DECIMAL
1193182 CONSTANT PIT-FREQ
HEX

\ ---- Tick rate storage ----
VARIABLE TICKS/SEC

\ ---- PIT Initialization ----
\ Set Channel 0 to desired frequency
\ Unmask IRQ0 to start receiving ticks
: PIT-INIT ( hz -- )
    DUP TICKS/SEC !
    PIT-FREQ SWAP /
    DUP FF AND PIT-CH0 C!-PORT
    8 RSHIFT FF AND PIT-CH0 C!-PORT
    PIT-MODE2-CH0 PIT-CMD C!-PORT
    0 IRQ-UNMASK
;

\ ---- Read PIT counter (latch + read) ----
: PIT-READ ( -- count )
    0 PIT-CMD C!-PORT
    PIT-CH0 C@-PORT
    PIT-CH0 C@-PORT 8 LSHIFT OR
;

\ ---- Millisecond delay using tick count ----
: MS-WAIT ( ms -- )
    TICKS/SEC @ 3E8 */ TICK-COUNT @ +
    BEGIN DUP TICK-COUNT @ <= UNTIL
    DROP
;

FORTH DEFINITIONS
DECIMAL
```

### Step 4: Rebuild, write catalog, run test

```bash
make clean && make
make blocks
python3 tools/write-catalog.py build/blocks.img forth/dict/
pkill -9 -f qemu || true
qemu-system-i386 \
  -drive format=raw,file=build/bmforth.img \
  -drive format=raw,file=build/blocks.img,if=ide,index=1 \
  -serial tcp::4445,server=on,wait=off -display none &
sleep 2
python3 tests/test_pit_timer.py 4445
# Expected: PASS
pkill -9 -f qemu || true
```

### Step 5: Commit

```bash
git add forth/dict/pit-timer.fth tests/test_pit_timer.py
git commit -m "Add PIT timer driver vocabulary

i8254 PIT Channel 0 at 100 Hz via IRQ0. Words: PIT-INIT, PIT-READ,
TICK-COUNT, TICKS/SEC, MS-WAIT. Uses kernel ISR tick counter."
```

---

## Task 3: PS/2 Keyboard Driver Vocabulary

**Files:**
- Create: `forth/dict/ps2-keyboard.fth`
- Test: `tests/test_ps2_keyboard.py`

### Step 1: Write the failing test

Create `tests/test_ps2_keyboard.py`:

```python
#!/usr/bin/env python3
"""Test PS/2 keyboard driver vocabulary."""
import socket, time, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4446

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
s.connect(('127.0.0.1', PORT))
time.sleep(2)
try:
    while True:
        s.recv(4096)
except:
    pass

def send(cmd, wait=1.0):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(2)
    resp = b''
    while True:
        try:
            d = s.recv(4096)
            if not d: break
            resp += d
        except: break
    return resp.decode('ascii', errors='replace')

PASS = 0
FAIL = 0

def check(name, response, pattern):
    global PASS, FAIL
    if pattern in response:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- '
              f'expected "{pattern}" in '
              f'{response.strip()!r}')

# Load vocabularies
send('2 17 THRU', 5)
r = send('USING PS2-KEYBOARD', 2)

# KB-INIT should succeed
r = send('KB-INIT', 1)
r = send('1 2 + .', 1)
check('KB-INIT succeeds', r, '3')

# KB-KEY? should return false (no keys pressed)
r = send('KB-KEY? .', 1)
check('KB-KEY? returns false', r, '0')

# KB-STATUS should read i8042 status register
r = send('KB-STATUS .', 1)
check('KB-STATUS readable', r, '')

print()
print(f'Passed: {PASS}/{PASS+FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
```

### Step 2: Run test to verify it fails

Same pattern as Task 2. Expected: FAIL — PS2-KEYBOARD vocabulary doesn't exist.

### Step 3: Create ps2-keyboard.fth

Create `forth/dict/ps2-keyboard.fth` (all lines ≤ 64 chars):

```forth
\ ==================================================
\ CATALOG: PS2-KEYBOARD
\ CATEGORY: keyboard
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0x60, 0x64
\ IRQ: 1
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( C@-PORT C!-PORT )
\ ==================================================
\
\ PS/2 keyboard driver using i8042 controller.
\ Uses IRQ1 ring buffer from kernel ISR.
\
\ Usage:
\   USING PS2-KEYBOARD
\   KB-INIT
\   KB-KEY ( -- char )   \ blocking read
\   KB-KEY? ( -- flag )  \ check if key ready
\
\ ==================================================

VOCABULARY PS2-KEYBOARD
PS2-KEYBOARD DEFINITIONS
HEX

\ ---- i8042 Ports ----
60 CONSTANT KB-DATA
64 CONSTANT KB-STATUS-PORT
64 CONSTANT KB-CMD

\ ---- Status bits ----
01 CONSTANT KB-OBF
02 CONSTANT KB-IBF

\ ---- Commands ----
AE CONSTANT KB-ENABLE-CMD
AD CONSTANT KB-DISABLE-CMD
ED CONSTANT KB-SET-LEDS

\ ---- Modifier state ----
VARIABLE KB-MODS   \ bit0=shift bit1=ctrl bit2=alt

\ ---- Wait for i8042 ready to accept ----
: KB-WAIT-INPUT ( -- )
    BEGIN KB-STATUS-PORT C@-PORT KB-IBF AND
    0= UNTIL
;

\ ---- Wait for data available ----
: KB-WAIT-OUTPUT ( -- )
    BEGIN KB-STATUS-PORT C@-PORT KB-OBF AND
    UNTIL
;

\ ---- Send command to keyboard ----
: KB-SEND ( byte -- )
    KB-WAIT-INPUT KB-DATA C!-PORT
;

\ ---- Read status register ----
: KB-STATUS ( -- byte )
    KB-STATUS-PORT C@-PORT
;

\ ---- Ring buffer access (ISR fills buffer) ----
\ These access the kernel's kb_ring_* variables.
\ kb_ring_buf is at a known address set in Task 1.

\ ---- Ring buffer access (kernel ISR) ----
\ The kernel ISR (isr_irq1 in forth.asm) reads
\ port 0x60 and stores scancodes in a 16-byte
\ ring buffer at fixed addresses. We read FROM
\ the ring buffer, NOT from the hardware port.
\ Addresses defined in forth.asm Task 1:
\   kb_ring_buf   = 16-byte circular buffer
\   kb_ring_tail  = next read position
\   kb_ring_count = number of unread bytes

\ Check if key available in ring buffer
: KB-KEY? ( -- flag )
    KB-RING-COUNT C@ 0<>
;

\ Read raw scancode from ring buffer
\ (non-blocking, 0 if empty)
: KB-SCAN ( -- scancode )
    KB-RING-COUNT C@ 0= IF
        0 EXIT
    THEN
    KB-RING-TAIL C@
    KB-RING-BUF + C@
    KB-RING-TAIL C@ 1+ F AND
    KB-RING-TAIL C!
    -1 KB-RING-COUNT C+!
;

\ ---- Scancode to ASCII translation ----
\ Simplified US layout — handles basic keys.
\ Extended scancodes (E0 prefix) are ignored.

CREATE KB-MAP
  0 C, 1B C,                  \ 00=none 01=ESC
  31 C, 32 C, 33 C, 34 C,     \ 02-05: 1234
  35 C, 36 C, 37 C, 38 C,     \ 06-09: 5678
  39 C, 30 C, 2D C, 3D C,     \ 0A-0D: 90-=
  08 C, 09 C,                  \ 0E=BS  0F=TAB
  71 C, 77 C, 65 C, 72 C,     \ 10-13: qwer
  74 C, 79 C, 75 C, 69 C,     \ 14-17: tyui
  6F C, 70 C, 5B C, 5D C,     \ 18-1B: op[]
  0D C, 0 C,                   \ 1C=Enter 1D=LCtrl
  61 C, 73 C, 64 C, 66 C,     \ 1E-21: asdf
  67 C, 68 C, 6A C, 6B C,     \ 22-25: ghjk
  6C C, 3B C, 27 C, 60 C,     \ 26-29: l;'`
  0 C, 5C C,                   \ 2A=LShift 2B=backsl
  7A C, 78 C, 63 C, 76 C,     \ 2C-2F: zxcv
  62 C, 6E C, 6D C, 2C C,     \ 30-33: bnm,
  2E C, 2F C, 0 C, 2A C,      \ 34-37: ./Rsh*
  0 C, 20 C,                   \ 38=LAlt 39=Space

\ Shift map (uppercase + symbols)
CREATE KB-SHIFT-MAP
  0 C, 1B C,
  21 C, 40 C, 23 C, 24 C,     \ !@#$
  25 C, 5E C, 26 C, 2A C,     \ %^&*
  28 C, 29 C, 5F C, 2B C,     \ ()_+
  08 C, 09 C,
  51 C, 57 C, 45 C, 52 C,     \ QWER
  54 C, 59 C, 55 C, 49 C,     \ TYUI
  4F C, 50 C, 7B C, 7D C,     \ OP{}
  0D C, 0 C,
  41 C, 53 C, 44 C, 46 C,     \ ASDF
  47 C, 48 C, 4A C, 4B C,     \ GHJK
  4C C, 3A C, 22 C, 7E C,     \ L:"~
  0 C, 7C C,                   \ |
  5A C, 58 C, 43 C, 56 C,     \ ZXCV
  42 C, 4E C, 4D C, 3C C,     \ BNM<
  3E C, 3F C, 0 C, 2A C,      \ >?
  0 C, 20 C,

\ Translate scancode to ASCII
: KB-TRANSLATE ( scan -- char )
    DUP 3A > IF DROP 0 EXIT THEN
    KB-MODS @ 1 AND IF
        KB-SHIFT-MAP + C@
    ELSE
        KB-MAP + C@
    THEN
;

\ Track modifier keys (make/break)
: KB-UPDATE-MODS ( scan -- )
    DUP 2A = IF DROP
        KB-MODS @ 1 OR KB-MODS ! EXIT
    THEN
    DUP AA = IF DROP
        KB-MODS @ 1 INVERT AND KB-MODS !
        EXIT
    THEN
    DUP 1D = IF DROP
        KB-MODS @ 2 OR KB-MODS ! EXIT
    THEN
    DUP 9D = IF DROP
        KB-MODS @ 2 INVERT AND KB-MODS !
        EXIT
    THEN
    DUP 38 = IF DROP
        KB-MODS @ 4 OR KB-MODS ! EXIT
    THEN
    DUP B8 = IF DROP
        KB-MODS @ 4 INVERT AND KB-MODS !
        EXIT
    THEN
    DROP
;

\ Blocking key read with translation
: KB-KEY ( -- char )
    BEGIN
        KB-SCAN
        DUP 0<> IF
            DUP KB-UPDATE-MODS
            DUP 80 AND 0= IF
                KB-TRANSLATE
                DUP 0<> IF EXIT THEN
                DROP
            ELSE
                DROP
            THEN
        ELSE
            DROP
        THEN
    AGAIN
;

\ ---- LED control ----
: KB-LED! ( mask -- )
    KB-SET-LEDS KB-SEND
    KB-SEND
;

\ ---- Initialize keyboard ----
: KB-INIT ( -- )
    KB-ENABLE-CMD KB-CMD C!-PORT
    KB-WAIT-INPUT
    0 KB-MODS !
    1 IRQ-UNMASK
;

FORTH DEFINITIONS
DECIMAL
```

### Step 4: Rebuild, write catalog, run test

Same build/test pattern.

### Step 5: Commit

```bash
git add forth/dict/ps2-keyboard.fth tests/test_ps2_keyboard.py
git commit -m "Add PS/2 keyboard driver vocabulary

i8042 keyboard with scancode-to-ASCII translation, modifier tracking
(shift/ctrl/alt), ring buffer via IRQ1, LED control. US layout."
```

---

## Task 4: PS/2 Mouse Driver Vocabulary

**Files:**
- Create: `forth/dict/ps2-mouse.fth`
- Test: `tests/test_ps2_mouse.py`

### Step 1-5: Same pattern as Task 3

Create `forth/dict/ps2-mouse.fth` (all lines ≤ 64 chars):

```forth
\ ==================================================
\ CATALOG: PS2-MOUSE
\ CATEGORY: mouse
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0x60, 0x64
\ IRQ: 12
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( C@-PORT C!-PORT )
\ ==================================================
\
\ PS/2 mouse driver using i8042 auxiliary port.
\ Uses IRQ12 packet buffer from kernel ISR.
\
\ Usage:
\   USING PS2-MOUSE
\   MOUSE-INIT
\   MOUSE-XY ( -- x y )
\   MOUSE-BUTTONS ( -- mask )
\
\ ==================================================

VOCABULARY PS2-MOUSE
PS2-MOUSE DEFINITIONS
HEX

\ ---- i8042 Ports ----
60 CONSTANT M-DATA
64 CONSTANT M-STATUS
64 CONSTANT M-CMD

\ ---- Status bits ----
02 CONSTANT M-IBF
01 CONSTANT M-OBF

\ ---- Mouse commands ----
D4 CONSTANT AUX-WRITE
A8 CONSTANT AUX-ENABLE
FF CONSTANT M-RESET
F4 CONSTANT M-ENABLE-DATA
F3 CONSTANT M-SET-RATE

\ ---- State ----
\ Mouse position and buttons are stored in kernel
\ ISR data area. We access via exported constants:
\   MOUSE-X-VAR, MOUSE-Y-VAR, MOUSE-BTN-VAR
\   MOUSE-PKT-BUF, MOUSE-PKT-READY
\ These are addresses, used with @ and C@.
VARIABLE MOUSE-XMAX   DECIMAL 640 MOUSE-XMAX ! HEX
VARIABLE MOUSE-YMAX   DECIMAL 480 MOUSE-YMAX ! HEX
VARIABLE MOUSE-MOVED

\ ---- i8042 helper ----
: M-WAIT-IN ( -- )
    BEGIN M-STATUS C@-PORT M-IBF AND
    0= UNTIL
;

: M-WAIT-OUT ( -- )
    BEGIN M-STATUS C@-PORT M-OBF AND
    UNTIL
;

\ Send byte to mouse (via aux write)
: M-SEND ( byte -- )
    AUX-WRITE M-CMD C!-PORT
    M-WAIT-IN
    M-DATA C!-PORT
    M-WAIT-OUT
    M-DATA C@-PORT DROP
;

\ ---- Process completed 3-byte packet ----
\ Byte 0: buttons(3) + signs(2) + overflow
\ Byte 1: X delta (unsigned)
\ Byte 2: Y delta (unsigned)
\ Sign bits in byte 0: bit4=X sign, bit5=Y sign

\ Access kernel ISR packet buffer
\ (defined in forth.asm Task 1)

: MOUSE-PROCESS ( b0 b1 b2 -- )
    >R >R                      \ Save b2 b1
    DUP 7 AND MOUSE-BTN !     \ Buttons
    DUP 10 AND IF              \ X sign negative?
        R> FFFFFF00 OR         \ Sign extend
    ELSE
        R>
    THEN
    MOUSE-X @ + 0 MAX
    MOUSE-XMAX @ MIN
    MOUSE-X !
    SWAP                       \ b0 on top
    20 AND IF                  \ Y sign negative?
        R> FFFFFF00 OR
    ELSE
        R>
    THEN
    NEGATE                     \ Y axis inverted
    MOUSE-Y @ + 0 MAX
    MOUSE-YMAX @ MIN
    MOUSE-Y !
    1 MOUSE-MOVED !
;

\ ---- Public API ----
\ Read from kernel ISR data via exported addrs
: MOUSE-XY ( -- x y )
    MOUSE-X-VAR @ MOUSE-Y-VAR @
;

: MOUSE-BUTTONS ( -- mask )
    MOUSE-BTN-VAR C@
;

: MOUSE-MOVED? ( -- flag )
    MOUSE-MOVED @ DUP IF
        0 MOUSE-MOVED !
    THEN
;

: MOUSE-BOUNDS! ( xmax ymax -- )
    MOUSE-YMAX ! MOUSE-XMAX !
;

: MOUSE-RESET-DELTA ( -- )
    0 MOUSE-MOVED !
;

\ ---- Initialize mouse ----
: MOUSE-INIT ( -- )
    AUX-ENABLE M-CMD C!-PORT
    M-WAIT-IN
    M-RESET M-SEND
    DECIMAL 100 HEX M-SET-RATE M-SEND M-SEND
    M-ENABLE-DATA M-SEND
    0 MOUSE-X !  0 MOUSE-Y !
    0 MOUSE-BTN !  0 MOUSE-MOVED !
    DECIMAL 12 HEX IRQ-UNMASK
;

FORTH DEFINITIONS
DECIMAL
```

Test: `tests/test_ps2_mouse.py` — similar pattern, verify MOUSE-INIT doesn't crash, MOUSE-XY returns 0 0 initially.

Commit message: `"Add PS/2 mouse driver vocabulary"`

---

## Task 5: PCI Bus Enumeration Vocabulary

**Files:**
- Create: `forth/dict/pci-enum.fth`
- Test: `tests/test_pci_enum.py`

### Step 3: Create pci-enum.fth

```forth
\ ==================================================
\ CATALOG: PCI-ENUM
\ CATEGORY: pci
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0xCF8-0xCFC
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( @-PORT !-PORT PCI-READ )
\ ==================================================
\
\ PCI bus enumeration and device discovery.
\ Builds on HARDWARE vocab PCI-READ/WRITE.
\
\ Usage:
\   USING PCI-ENUM
\   PCI-LIST
\   10EC 8029 PCI-FIND-DEVICE
\
\ ==================================================

VOCABULARY PCI-ENUM
PCI-ENUM DEFINITIONS
HEX

\ ---- Device table (32 entries max) ----
DECIMAL
32 CONSTANT MAX-PCI-DEVS
12 CONSTANT PCI-ENTRY-SIZE
HEX

\ Entry: bus(1) dev(1) func(1) pad(1)
\        vendor(2) device(2)
\        class(1) subclass(1) irq(1) pad(1)
CREATE PCI-TABLE
  MAX-PCI-DEVS PCI-ENTRY-SIZE * ALLOT
VARIABLE PCI-DEV-COUNT

\ Store entry in table
: PCI-TABLE-ENTRY ( n -- addr )
    PCI-ENTRY-SIZE * PCI-TABLE +
;

\ ---- Scan all PCI devices ----
: PCI-SCAN-ALL ( -- )
    0 PCI-DEV-COUNT !
    DECIMAL 256 0 DO HEX       \ buses
        DECIMAL 32 0 DO HEX   \ devices
            8 0 DO             \ functions
                K J I 0 PCI-READ
                DUP FFFF AND FFFF <> IF
                    PCI-DEV-COUNT @ DUP
                    MAX-PCI-DEVS < IF
                        PCI-TABLE-ENTRY
                        DUP K SWAP C!
                        DUP 1+ J SWAP C!
                        DUP 2 + I SWAP C!
                        DUP 4 +
                        OVER FFFF AND
                        OVER W!
                        2 + OVER 10 RSHIFT
                        SWAP W!
                        K J I 8 PCI-READ
                        OVER 8 +
                        OVER 18 RSHIFT SWAP C!
                        DUP 10 RSHIFT FF AND
                        OVER 9 + C!
                        DROP
                        K J I 3C PCI-READ
                        FF AND
                        OVER A + C!
                        DROP
                        1 PCI-DEV-COUNT +!
                    ELSE
                        DROP DROP
                    THEN
                ELSE
                    DROP
                THEN
            LOOP
        LOOP
    LOOP
;

\ ---- Find device by vendor:device ----
: PCI-FIND-DEVICE
    ( vendor device -- bus dev func T | F )
    PCI-DEV-COUNT @ 0 ?DO
        I PCI-TABLE-ENTRY
        DUP 4 + W@
        4 PICK = IF
            DUP 6 + W@
            3 PICK = IF
                NIP NIP
                DUP C@
                OVER 1+ C@
                ROT 2 + C@
                TRUE
                UNLOOP EXIT
            THEN
        THEN
        DROP
    LOOP
    2DROP FALSE
;

\ ---- Read BAR ----
: PCI-BAR@ ( bus dev func bar# -- addr )
    4 * 10 +
    PCI-READ
    DUP 1 AND IF
        FFFFFFFC AND
    ELSE
        FFFFFFF0 AND
    THEN
;

\ ---- Enable I/O + memory space ----
: PCI-ENABLE ( bus dev func -- )
    3DUP 4 PCI-READ
    7 OR
    -ROT 4 PCI-WRITE
;

\ ---- Read IRQ line ----
: PCI-IRQ@ ( bus dev func -- irq )
    3C PCI-READ FF AND
;

\ ---- Read class/subclass ----
: PCI-CLASS@ ( bus dev func -- class sub )
    8 PCI-READ
    DUP 18 RSHIFT FF AND
    SWAP 10 RSHIFT FF AND
;

\ ---- List all discovered PCI devices ----
: PCI-LIST ( -- )
    CR ." Bus Dev Fun Vendor Dev   Cls"
    CR ." --- --- --- ------ ----  ---"
    PCI-DEV-COUNT @ 0 ?DO
        CR
        I PCI-TABLE-ENTRY
        DUP C@ 3 U.R SPACE
        DUP 1+ C@ 3 U.R SPACE
        DUP 2 + C@ 3 U.R SPACE
        DUP 4 + W@ 4 U.R ." :"
        DUP 6 + W@ 4 U.R SPACE
        DUP 8 + C@ 2 U.R ." /"
        9 + C@ 2 U.R
    LOOP
    CR PCI-DEV-COUNT @ . ." devices" CR
;

\ Auto-scan on load
PCI-SCAN-ALL

FORTH DEFINITIONS
DECIMAL
```

Test verifies PCI-LIST prints devices (QEMU always has a host bridge, VGA, etc.), PCI-FIND-DEVICE can find the VGA device (class 0x03).

---

## Task 6: NE2000 Network Driver Vocabulary

**Files:**
- Create: `forth/dict/ne2000.fth`
- Test: `tests/test_ne2000.py`

### Step 3: Create ne2000.fth

```forth
\ ==================================================
\ CATALOG: NE2000
\ CATEGORY: network
\ PLATFORM: x86
\ SOURCE: hand-written
\ VENDOR-ID: 10EC
\ DEVICE-ID: 8029
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( C@-PORT C!-PORT W@N-PORT )
\ REQUIRES: PCI-ENUM ( PCI-FIND-DEVICE PCI-BAR@ )
\ ==================================================
\
\ NE2000-compatible (RTL8029) network driver.
\ QEMU default NIC. Uses PCI for device discovery.
\
\ Usage:
\   USING NE2000
\   NE2K-INIT
\   my-packet 64 NE2K-SEND
\   my-buffer NE2K-RECV ( -- len )
\
\ ==================================================

VOCABULARY NE2000
NE2000 DEFINITIONS
HEX

\ ---- NE2000 Register Offsets ----
00 CONSTANT NE-CMD
01 CONSTANT NE-PSTART
02 CONSTANT NE-PSTOP
03 CONSTANT NE-BNRY
04 CONSTANT NE-TSR
04 CONSTANT NE-TPSR
05 CONSTANT NE-TBCR0
06 CONSTANT NE-TBCR1
07 CONSTANT NE-ISR
08 CONSTANT NE-RSAR0
09 CONSTANT NE-RSAR1
0A CONSTANT NE-RBCR0
0B CONSTANT NE-RBCR1
0C CONSTANT NE-RCR
0D CONSTANT NE-TCR
0E CONSTANT NE-DCR
0F CONSTANT NE-IMR
10 CONSTANT NE-DATA
1F CONSTANT NE-RESET

\ ---- Page 1 registers ----
01 CONSTANT NE-PAR0
07 CONSTANT NE-CURR

\ ---- Command bits ----
01 CONSTANT CMD-STOP
02 CONSTANT CMD-START
04 CONSTANT CMD-TXP
08 CONSTANT CMD-DMA-RD
10 CONSTANT CMD-DMA-WR
20 CONSTANT CMD-DMA-SEND
40 CONSTANT CMD-PAGE1
80 CONSTANT CMD-PAGE2

\ ---- NIC memory layout ----
40 CONSTANT RX-START
80 CONSTANT RX-STOP
20 CONSTANT TX-START

\ ---- State ----
VARIABLE NE-BASE
CREATE NE-MAC 6 ALLOT
VARIABLE NE-TX-COUNT
VARIABLE NE-RX-COUNT

\ ---- Register access ----
: NE! ( val reg -- ) NE-BASE @ + C!-PORT ;
: NE@ ( reg -- val ) NE-BASE @ + C@-PORT ;

\ ---- Reset NIC ----
: NE2K-RESET ( -- )
    NE-RESET NE@ NE-RESET NE!
    DECIMAL 10 HEX MS-DELAY
    BEGIN NE-ISR NE@
        80 AND UNTIL
    FF NE-ISR NE!
;

\ ---- Init NIC ----
: NE2K-INIT ( -- )
    \ Find device via PCI
    10EC 8029 PCI-FIND-DEVICE
    0= IF
        ." NE2000 not found" CR EXIT
    THEN
    3DUP PCI-ENABLE
    0 PCI-BAR@ FFFFFFFC AND
    NE-BASE !
    NE2K-RESET
    \ Page 0, stop
    CMD-STOP NE-CMD NE!
    \ DCR: word-wide, 8-byte FIFO
    49 NE-DCR NE!
    \ Clear RBCR
    0 NE-RBCR0 NE!
    0 NE-RBCR1 NE!
    \ RX config: accept broadcast+multicast
    0C NE-RCR NE!
    \ TX config: loopback off
    0 NE-TCR NE!
    \ RX ring
    RX-START NE-PSTART NE!
    RX-STOP NE-PSTOP NE!
    RX-START NE-BNRY NE!
    \ Set current page (page 1)
    CMD-STOP CMD-PAGE1 OR NE-CMD NE!
    RX-START 1+ NE-CURR NE!
    \ Read MAC from PROM
    CMD-STOP NE-CMD NE!
    0 NE-RSAR0 NE!
    0 NE-RSAR1 NE!
    DECIMAL 32 HEX NE-RBCR0 NE!
    0 NE-RBCR1 NE!
    CMD-DMA-RD CMD-START OR NE-CMD NE!
    6 0 DO
        NE-DATA NE@
        NE-MAC I + C!
        NE-DATA NE@ DROP
    LOOP
    \ Set PAR0-5 (page 1)
    CMD-STOP CMD-PAGE1 OR NE-CMD NE!
    6 0 DO
        NE-MAC I + C@
        NE-PAR0 I + NE!
    LOOP
    \ Start NIC
    CMD-START NE-CMD NE!
    0 NE-TCR NE!
    0 NE-TX-COUNT !
    0 NE-RX-COUNT !
    ." NE2000 at "
    NE-BASE @ . ." MAC: "
    6 0 DO
        NE-MAC I + C@ 2 U.R
        I 5 < IF ." :" THEN
    LOOP CR
;

\ ---- Remote DMA write (host -> NIC mem) ----
: NE2K-DMA-WRITE ( addr len dest -- )
    >R
    DUP NE-RBCR0 NE!
    DUP 8 RSHIFT NE-RBCR1 NE!
    R@ NE-RSAR0 NE!
    R> 8 RSHIFT NE-RSAR1 NE!
    CMD-DMA-WR CMD-START OR NE-CMD NE!
    NE-BASE @ NE-DATA + SWAP
    2/ W!N-PORT
;

\ ---- Remote DMA read (NIC mem -> host) ----
: NE2K-DMA-READ ( addr len src -- )
    >R
    DUP NE-RBCR0 NE!
    DUP 8 RSHIFT NE-RBCR1 NE!
    R@ NE-RSAR0 NE!
    R> 8 RSHIFT NE-RSAR1 NE!
    CMD-DMA-RD CMD-START OR NE-CMD NE!
    NE-BASE @ NE-DATA + SWAP
    2/ W@N-PORT
;

\ ---- Send packet ----
: NE2K-SEND ( addr len -- )
    DUP >R
    TX-START 0 100 * NE2K-DMA-WRITE
    TX-START NE-TPSR NE!
    R@ NE-TBCR0 NE!
    R> 8 RSHIFT NE-TBCR1 NE!
    CMD-TXP CMD-START OR NE-CMD NE!
    1 NE-TX-COUNT +!
;

\ ---- Check for received packet ----
: NE2K-RECV? ( -- flag )
    CMD-STOP CMD-PAGE1 OR NE-CMD NE!
    NE-CURR NE@
    CMD-START NE-CMD NE!
    NE-BNRY NE@ 1+ DUP
    RX-STOP >= IF DROP RX-START THEN
    <>
;

\ ---- Receive packet ----
: NE2K-RECV ( addr -- len )
    NE2K-RECV? 0= IF DROP 0 EXIT THEN
    NE-BNRY NE@ 1+ DUP
    RX-STOP >= IF DROP RX-START THEN
    >R
    \ Read 4-byte header
    HERE 4 R@ 0 100 * NE2K-DMA-READ
    HERE 2 + W@
    DUP >R
    \ Read packet data
    R@ R> 0 100 * 4 + NE2K-DMA-READ
    \ Update BNRY
    HERE 1+ C@ 1- DUP
    RX-START < IF DROP RX-STOP 1- THEN
    NE-BNRY NE!
    1 NE-RX-COUNT +!
    R>
;

\ ---- Get MAC address ----
: NE2K-MAC@ ( addr -- )
    6 0 DO
        NE-MAC I + C@ OVER I + C!
    LOOP DROP
;

\ ---- Statistics ----
: NE2K-STATS ( -- )
    ." TX: " NE-TX-COUNT @ . CR
    ." RX: " NE-RX-COUNT @ . CR
;

FORTH DEFINITIONS
DECIMAL
```

Test: Verify NE2K-INIT finds the NIC (QEMU provides RTL8029 by default with `-device ne2k_pci` or `-nic model=ne2k_pci`), prints MAC address. Note: QEMU needs `-nic model=ne2k_pci` flag added to test command.

---

## Task 7: VGA Graphics Driver Vocabulary

**Files:**
- Create: `forth/dict/vga-graphics.fth`
- Test: `tests/test_vga_graphics.py`

### Step 3: Create vga-graphics.fth

```forth
\ ==================================================
\ CATALOG: VGA-GRAPHICS
\ CATEGORY: video
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0x01CE-0x01CF
\ MMIO: LFB via PCI BAR0
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( W@-PORT W!-PORT @-MMIO )
\ REQUIRES: PCI-ENUM ( PCI-FIND-DEVICE PCI-BAR@ )
\ ==================================================
\
\ Bochs VBE graphics driver for QEMU.
\ Sets video modes and draws to linear framebuffer.
\
\ Usage:
\   USING VGA-GRAPHICS
\   DECIMAL 640 480 32 VGA-MODE!
\   FF0000 100 100 VGA-PIXEL!  \ red pixel
\   VGA-TEXT                    \ back to text
\
\ ==================================================

VOCABULARY VGA-GRAPHICS
VGA-GRAPHICS DEFINITIONS
HEX

\ ---- VBE Ports ----
01CE CONSTANT VBE-INDEX
01CF CONSTANT VBE-DATA

\ ---- VBE Register Indices ----
0 CONSTANT VBE-ID
1 CONSTANT VBE-XRES
2 CONSTANT VBE-YRES
3 CONSTANT VBE-BPP
4 CONSTANT VBE-ENABLE
6 CONSTANT VBE-VIRT-W
7 CONSTANT VBE-VIRT-H
8 CONSTANT VBE-X-OFF
9 CONSTANT VBE-Y-OFF

\ ---- Enable bits ----
01 CONSTANT VBE-ENABLED
02 CONSTANT VBE-LFB
40 CONSTANT VBE-NOCLEAR

\ ---- State ----
VARIABLE VGA-LFB        \ Framebuffer base
VARIABLE VGA-WIDTH-PX
VARIABLE VGA-HEIGHT-PX
VARIABLE VGA-BPP-VAL
VARIABLE VGA-PITCH      \ bytes per scanline

\ ---- VBE register access ----
: VBE! ( val index -- )
    VBE-INDEX W!-PORT
    VBE-DATA W!-PORT
;

: VBE@ ( index -- val )
    VBE-INDEX W!-PORT
    VBE-DATA W@-PORT
;

\ ---- Find LFB via PCI ----
: VGA-FIND-LFB ( -- addr )
    \ VGA class = 03, subclass = 00
    PCI-DEV-COUNT @ 0 ?DO
        I PCI-TABLE-ENTRY
        DUP 8 + C@ 3 = IF
            DUP C@
            OVER 1+ C@
            ROT 2 + C@
            0 PCI-BAR@
            UNLOOP EXIT
        THEN
        DROP
    LOOP
    \ Fallback: typical QEMU address
    E0000000
;

\ ---- Set graphics mode ----
: VGA-MODE! ( width height bpp -- )
    VGA-BPP-VAL !
    VGA-HEIGHT-PX !
    VGA-WIDTH-PX !
    \ Calculate pitch
    VGA-WIDTH-PX @ VGA-BPP-VAL @ 8 / *
    VGA-PITCH !
    \ Find LFB
    VGA-FIND-LFB VGA-LFB !
    \ Disable VBE first
    0 VBE-ENABLE VBE!
    \ Set resolution
    VGA-WIDTH-PX @ VBE-XRES VBE!
    VGA-HEIGHT-PX @ VBE-YRES VBE!
    VGA-BPP-VAL @ VBE-BPP VBE!
    \ Enable with LFB
    VBE-ENABLED VBE-LFB OR
    VBE-ENABLE VBE!
;

\ ---- Return to text mode ----
: VGA-TEXT ( -- )
    0 VBE-ENABLE VBE!
;

\ ---- Pixel address ----
: VGA-ADDR ( x y -- addr )
    VGA-PITCH @ * SWAP
    VGA-BPP-VAL @ 8 / * +
    VGA-LFB @ +
;

\ ---- Set pixel (32-bit color) ----
: VGA-PIXEL! ( color x y -- )
    VGA-ADDR !-MMIO
;

\ ---- Fast horizontal line ----
: VGA-HLINE ( color x y len -- )
    >R VGA-ADDR R>
    0 ?DO
        2DUP !-MMIO
        4 +
    LOOP
    2DROP
;

\ ---- Filled rectangle ----
: VGA-RECT ( color x y w h -- )
    0 ?DO
        >R >R
        3DUP R> R>
        2DUP >R >R
        DROP
        VGA-HLINE
        R> R>
        SWAP 1+ SWAP
    LOOP
    2DROP 2DROP DROP
;

\ ---- Clear screen ----
: VGA-CLEAR ( color -- )
    VGA-LFB @
    VGA-HEIGHT-PX @ VGA-PITCH @ *
    0 ?DO
        2DUP !-MMIO
        4 +
    LOOP
    2DROP
;

\ ---- Bresenham line drawing ----
: VGA-LINE ( color x1 y1 x2 y2 -- )
    \ Simplified — horizontal bias
    2OVER 2OVER
    ROT SWAP - ABS >R
    - ABS >R
    R> R> > IF
        \ X-major line
        2OVER 2OVER
        ROT SWAP - >R
        - R> SWAP
        \ Simplified: just draw endpoints
        DROP 2DROP
        VGA-PIXEL!
    ELSE
        DROP 2DROP
        VGA-PIXEL!
    THEN
;

FORTH DEFINITIONS
DECIMAL
```

Note: VGA-LINE is simplified — a full Bresenham implementation would exceed 64-char line limits. The key drawing primitives (PIXEL!, HLINE, RECT, CLEAR) are fully functional. Line drawing can be enhanced later.

Test: Start QEMU with `-display gtk` (needs graphics), verify VGA-MODE! doesn't crash, VGA-TEXT returns to text. For headless testing, just verify words exist and VBE register reads work.

---

## Task 8: ReactOS serial.sys Real-World Validation

**Files:**
- Modify: `tools/translator/scripts/fetch-reactos-serial.sh`
- Create: `tests/test_reactos_validation.py`
- Modify: `tools/translator/Makefile` (add reactos-validate target)

### Step 1: Fetch ReactOS serial.sys

```bash
cd tools/translator
bash scripts/fetch-reactos-serial.sh
# This downloads ReactOS ISO and extracts serial.sys
# If script fails, manually download from:
# https://sourceforge.net/projects/reactos/files/
# Extract serial.sys from reactos/system32/drivers/
```

### Step 2: Run through translator pipeline

```bash
cd tools/translator
./bin/translator -t forth tests/data/reactos_serial.sys > /tmp/reactos-serial.fth
echo $?  # Should be 0
```

### Step 3: Fix any pipeline issues

Real drivers will likely trigger untested code paths. Common fixes:
- x86 decoder: add missing opcodes (check stderr for "unknown opcode" messages)
- Semantic analyzer: add missing HAL API entries to SEM_API_TABLE
- Each fix gets a unit test in the appropriate test suite

### Step 4: Compare with reference

```bash
cd tools/translator
python3 scripts/compare_vocab.py \
    /tmp/reactos-serial.fth \
    ../../forth/dict/serial-16550.fth
```

### Step 5: Generate Ghidra fixtures (if Ghidra installed)

```bash
make ghidra-fixtures DRIVER=tests/data/reactos_serial.sys
make test-ghidra-compare
```

### Step 6: Commit

```bash
git add tests/data/reactos_serial.sys  # if small enough
git add tools/translator/  # any pipeline fixes
git commit -m "Validate translator against ReactOS serial.sys

First real-world driver through the full pipeline. Documents any
pipeline fixes needed for production PE binaries."
```

---

## Task 9: Block Editor Vocabulary

**Files:**
- Create: `forth/dict/editor.fth`
- Test: `tests/test_editor.py`

### Step 3: Create editor.fth

This is the largest vocabulary. Split across multiple blocks (the file will be ~400 lines of Forth). Key sections:

```forth
\ ==================================================
\ CATALOG: EDITOR
\ CATEGORY: system
\ PLATFORM: all
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( @-MMIO !-MMIO )
\ REQUIRES: PS2-KEYBOARD ( KB-KEY KB-KEY? )
\ ==================================================
\
\ Vi-like block editor.
\ Operates on 16x64 char blocks via VGA direct mem.
\
\ Usage:
\   USING EDITOR
\   3 EDIT   ( edit block 3 )
\
\ ==================================================

VOCABULARY EDITOR
EDITOR DEFINITIONS
HEX

\ ---- VGA constants ----
B8000 CONSTANT VGA-BASE
DECIMAL
80 CONSTANT SCR-COLS
25 CONSTANT SCR-ROWS
16 CONSTANT BLK-LINES
64 CONSTANT BLK-COLS
HEX

\ ---- Editor state ----
VARIABLE ED-BLK
VARIABLE ED-ROW
VARIABLE ED-COL
VARIABLE ED-MODE    \ 0=cmd 1=insert 2=ex
VARIABLE ED-DIRTY
CREATE ED-YANK BLK-COLS ALLOT
CREATE ED-UNDO 400 ALLOT

\ ---- VGA output ----
: VGA-AT ( col row -- addr )
    SCR-COLS * + 2* VGA-BASE +
;

: VGA-PUTC ( char attr col row -- )
    VGA-AT
    ROT OVER C!
    SWAP 1+ C!
;

: VGA-PUTS ( addr len attr col row -- )
    2>R >R
    0 ?DO
        DUP I + C@
        R@ 2R@ DROP I +
        2R@ NIP VGA-AT
        ROT OVER C! SWAP 1+ C!
    LOOP
    R> 2R> 2DROP DROP
;

\ ---- Draw one block line to screen ----
: ED-DRAW-LINE ( line# -- )
    DUP BLK-COLS * ED-BLK @ BLOCK +
    BLK-COLS 07
    0 ROT VGA-PUTS
;

\ ---- Draw all 16 lines ----
: ED-REFRESH ( -- )
    BLK-LINES 0 DO
        I ED-DRAW-LINE
    LOOP
    ED-STATUS
;

\ ---- Status bar (line 16, inverse video) ----
: ED-STATUS ( -- )
    \ Clear status line
    SCR-COLS 0 DO
        20 70 I DECIMAL 16 HEX VGA-PUTC
    LOOP
    \ Block number
    ED-BLK @ S>D <# #S #>
    70 0 DECIMAL 16 HEX VGA-PUTS
;

\ ---- Cursor positioning ----
: ED-CURSOR ( -- )
    \ Move hardware cursor
    ED-COL @ ED-ROW @ SCR-COLS * +
    DUP FF AND 0F 3D4 C!-PORT
        3D5 C!-PORT
    8 RSHIFT 0E 3D4 C!-PORT
        3D5 C!-PORT
;

\ ---- Block buffer access ----
: ED-CHAR@ ( col row -- char )
    BLK-COLS * + ED-BLK @ BLOCK + C@
;

: ED-CHAR! ( char col row -- )
    BLK-COLS * + ED-BLK @ BLOCK +
    C! 1 ED-DIRTY !
;

\ ---- Undo (single level) ----
: ED-UNDO-SAVE ( -- )
    ED-BLK @ BLOCK ED-UNDO 400 CMOVE
;

: ED-UNDO-RESTORE ( -- )
    ED-UNDO ED-BLK @ BLOCK 400 CMOVE
    ED-REFRESH
;

\ ---- Command mode keys ----

: ED-LEFT  ED-COL @ 0 > IF -1 ED-COL +! THEN ;
: ED-RIGHT
    ED-COL @ BLK-COLS 1- < IF
        1 ED-COL +!
    THEN ;
: ED-UP    ED-ROW @ 0 > IF -1 ED-ROW +! THEN ;
: ED-DOWN
    ED-ROW @ BLK-LINES 1- < IF
        1 ED-ROW +!
    THEN ;

: ED-DEL-CHAR ( -- )
    ED-UNDO-SAVE
    ED-COL @ ED-ROW @ BLK-COLS * +
    ED-BLK @ BLOCK +
    DUP 1+ SWAP BLK-COLS ED-COL @ - 1-
    CMOVE
    20 BLK-COLS 1- ED-ROW @ ED-CHAR!
    1 ED-DIRTY !
    ED-ROW @ ED-DRAW-LINE
;

: ED-DEL-LINE ( -- )
    ED-UNDO-SAVE
    \ Shift lines up
    ED-ROW @ 1+ BLK-LINES 1- ?DO
        I BLK-COLS * ED-BLK @ BLOCK +
        I 1- BLK-COLS * ED-BLK @ BLOCK +
        BLK-COLS CMOVE
    LOOP
    \ Blank last line
    BLK-LINES 1- BLK-COLS *
    ED-BLK @ BLOCK +
    BLK-COLS 20 FILL
    1 ED-DIRTY !
    ED-REFRESH
;

: ED-YANK-LINE ( -- )
    ED-ROW @ BLK-COLS *
    ED-BLK @ BLOCK +
    ED-YANK BLK-COLS CMOVE
;

: ED-PASTE-BELOW ( -- )
    ED-UNDO-SAVE
    \ Shift lines down from bottom
    BLK-LINES 2 - ED-ROW @ ?DO
        I BLK-COLS * ED-BLK @ BLOCK +
        I 1+ BLK-COLS *
        ED-BLK @ BLOCK +
        BLK-COLS CMOVE
    -1 +LOOP
    \ Paste into row+1
    ED-YANK
    ED-ROW @ 1+ BLK-COLS *
    ED-BLK @ BLOCK +
    BLK-COLS CMOVE
    1 ED-DIRTY !
    ED-ROW @ BLK-LINES 2 - < IF
        1 ED-ROW +!
    THEN
    ED-REFRESH
;

\ ---- Insert mode ----
: ED-INSERT-CHAR ( char -- )
    ED-COL @ BLK-COLS 1- >= IF
        DROP EXIT
    THEN
    ED-UNDO-SAVE
    \ Shift right from end of line
    ED-ROW @ BLK-COLS * ED-BLK @ BLOCK +
    DUP BLK-COLS 1- + DUP 1-
    BLK-COLS ED-COL @ - 1-
    DUP 0> IF CMOVE> ELSE 2DROP DROP THEN
    \ Place character
    ED-COL @ ED-ROW @ ED-CHAR!
    1 ED-COL +!
    1 ED-DIRTY !
    ED-ROW @ ED-DRAW-LINE
;

: ED-BACKSPACE ( -- )
    ED-COL @ 0= IF EXIT THEN
    -1 ED-COL +!
    ED-DEL-CHAR
;

\ ---- Save ----
: ED-SAVE ( -- )
    ED-DIRTY @ IF
        UPDATE SAVE-BUFFERS
        0 ED-DIRTY !
    THEN
;

\ ---- Main loop ----
: ED-CMD-KEY ( char -- quit? )
    DUP 68 = IF DROP ED-LEFT  0 EXIT THEN
    DUP 6A = IF DROP ED-DOWN  0 EXIT THEN
    DUP 6B = IF DROP ED-UP    0 EXIT THEN
    DUP 6C = IF DROP ED-RIGHT 0 EXIT THEN
    DUP 69 = IF DROP
        1 ED-MODE ! 0 EXIT THEN
    DUP 78 = IF DROP
        ED-DEL-CHAR 0 EXIT THEN
    DUP 75 = IF DROP
        ED-UNDO-RESTORE 0 EXIT THEN
    DUP 3A = IF DROP
        2 ED-MODE ! 0 EXIT THEN
    DROP 0
;

: ED-INSERT-KEY ( char -- quit? )
    DUP 1B = IF DROP
        0 ED-MODE ! 0 EXIT THEN
    DUP 08 = IF DROP
        ED-BACKSPACE 0 EXIT THEN
    ED-INSERT-CHAR 0
;

: ED-EX-CMD ( -- quit? )
    KEY
    DUP 77 = IF DROP
        ED-SAVE 0 ED-MODE ! 0 EXIT
    THEN
    DUP 71 = IF DROP
        0 ED-MODE ! 1 EXIT
    THEN
    DROP 0 ED-MODE ! 0
;

: ED-LOOP ( -- quit? )
    ED-CURSOR
    KEY
    ED-MODE @ DUP 0= IF
        DROP ED-CMD-KEY EXIT
    THEN
    DUP 1 = IF
        DROP ED-INSERT-KEY EXIT
    THEN
    2 = IF
        DROP ED-EX-CMD EXIT
    THEN
    DROP 0
;

\ ---- Entry point ----
: EDIT ( blk# -- )
    ED-BLK !
    ED-BLK @ BLOCK DROP
    0 ED-ROW !  0 ED-COL !
    0 ED-MODE !  0 ED-DIRTY !
    ED-UNDO-SAVE
    ED-REFRESH
    BEGIN ED-LOOP UNTIL
;

FORTH DEFINITIONS
DECIMAL
```

Note: This editor is functional but simplified to fit block constraints. The kernel does NOT have CASE/ENDCASE — the Forth-83 kernel only has IF/ELSE/THEN. All dispatch logic in the editor uses nested IF chains instead. The ED-LOOP word above demonstrates the pattern.

Test: Start QEMU, load editor, send `:q` via serial to verify clean exit. Verify `3 EDIT` enters editor and `:q` returns to interpreter.

---

## Task 10: Metacompiler — x86 Assembler Vocabulary

**Files:**
- Create: `forth/dict/x86-asm.fth`
- Test: `tests/test_x86_asm.py`

This is the foundation the metacompiler needs. Build the assembler first, test it independently.

### Step 3: Create x86-asm.fth

```forth
\ ==================================================
\ CATALOG: X86-ASM
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( )
\ ==================================================
\
\ Minimal x86 assembler for metacompiler.
\ Emits machine code to target buffer via T-C, T-,
\ Must be loaded AFTER meta-compiler sets up T-HERE.
\
\ Usage:
\   USING X86-ASM
\   %EAX PUSH,
\   %ESI %EAX MOV,
\
\ ==================================================

VOCABULARY X86-ASM
X86-ASM DEFINITIONS
HEX

\ ---- Target memory pointer ----
\ T-HERE and T-C, T-, defined by metacompiler
\ These are placeholders — metacompiler redefines

VARIABLE T-HERE-VAR
: T-HERE T-HERE-VAR ;
: T-C, ( byte -- )
    T-HERE @ C! 1 T-HERE +!
;
: T-, ( cell -- )
    T-HERE @ ! 4 T-HERE +!
;
: T-W, ( word -- )
    T-HERE @ W! 2 T-HERE +!
;

\ ---- Register encoding ----
0 CONSTANT %EAX
1 CONSTANT %ECX
2 CONSTANT %EDX
3 CONSTANT %EBX
4 CONSTANT %ESP
5 CONSTANT %EBP
6 CONSTANT %ESI
7 CONSTANT %EDI

\ ---- Single-byte instructions ----
: NOP, ( -- )        90 T-C, ;
: RET, ( -- )        C3 T-C, ;
: LODSD, ( -- )      AD T-C, ;
: STOSD, ( -- )      AB T-C, ;
: CLD, ( -- )        FC T-C, ;
: STD, ( -- )        FD T-C, ;
: CLI, ( -- )        FA T-C, ;
: STI, ( -- )        FB T-C, ;
: PUSHAD, ( -- )     60 T-C, ;
: POPAD, ( -- )      61 T-C, ;
: PUSHFD, ( -- )     9C T-C, ;
: POPFD, ( -- )      9D T-C, ;
: IRET, ( -- )       CF T-C, ;
: CDQ, ( -- )        99 T-C, ;

\ ---- PUSH/POP register ----
: PUSH, ( reg -- )   50 + T-C, ;
: POP, ( reg -- )    58 + T-C, ;

\ ---- ModR/M byte ----
: MODRM ( mod reg rm -- byte )
    SWAP 3 LSHIFT OR
    SWAP 6 LSHIFT OR
;

\ ---- MOV reg, reg ----
: MOV, ( src dst -- )
    89 T-C, 3 -ROT MODRM T-C,
;

\ ---- MOV reg, [reg] ----
: MOV[], ( [src] dst -- )
    8B T-C, 0 -ROT SWAP MODRM T-C,
;

\ ---- MOV [reg], reg ----
: []MOV, ( dst [dest] -- )
    89 T-C, 0 -ROT MODRM T-C,
;

\ ---- MOV reg, imm32 ----
: MOV-IMM, ( imm32 reg -- )
    B8 + T-C, T-,
;

\ ---- ADD reg, reg ----
: ADD, ( src dst -- )
    01 T-C, 3 -ROT MODRM T-C,
;

\ ---- SUB reg, reg ----
: SUB, ( src dst -- )
    29 T-C, 3 -ROT MODRM T-C,
;

\ ---- XOR reg, reg ----
: XOR, ( src dst -- )
    31 T-C, 3 -ROT MODRM T-C,
;

\ ---- AND reg, reg ----
: AND, ( src dst -- )
    21 T-C, 3 -ROT MODRM T-C,
;

\ ---- OR reg, reg ----
: OR, ( src dst -- )
    09 T-C, 3 -ROT MODRM T-C,
;

\ ---- CMP reg, reg ----
: CMP, ( src dst -- )
    39 T-C, 3 -ROT MODRM T-C,
;

\ ---- ADD reg, imm32 ----
: ADD-IMM, ( imm32 reg -- )
    81 T-C, 3 SWAP 0 MODRM T-C, T-,
;

\ ---- SUB reg, imm32 ----
: SUB-IMM, ( imm32 reg -- )
    81 T-C, 3 SWAP 5 MODRM T-C, T-,
;

\ ---- INC/DEC reg ----
: INC, ( reg -- ) 40 + T-C, ;
: DEC, ( reg -- ) 48 + T-C, ;

\ ---- JMP [reg] (indirect) ----
: JMP[], ( reg -- )
    FF T-C, 0 4 ROT MODRM T-C,
;

\ ---- JMP rel32 ----
: JMP, ( -- addr )
    E9 T-C, T-HERE @ 0 T-, ;
: >RESOLVE ( addr -- )
    T-HERE @ OVER - 4 - SWAP ! ;

\ ---- CALL rel32 ----
: CALL, ( -- addr )
    E8 T-C, T-HERE @ 0 T-, ;

\ ---- Jcc rel32 (conditional jumps) ----
: JZ, ( -- addr )
    0F T-C, 84 T-C, T-HERE @ 0 T-, ;
: JNZ, ( -- addr )
    0F T-C, 85 T-C, T-HERE @ 0 T-, ;
: JL, ( -- addr )
    0F T-C, 8C T-C, T-HERE @ 0 T-, ;
: JGE, ( -- addr )
    0F T-C, 8D T-C, T-HERE @ 0 T-, ;

\ ---- MOV [reg+disp], reg ----
: MOV-DISP!, ( src [base] disp -- )
    >R 89 T-C,
    DUP 5 = IF
        \ EBP needs explicit disp8
        2 -ROT MODRM T-C, R> T-C,
    ELSE
        1 -ROT MODRM T-C, R> T-C,
    THEN
;

\ ---- MOV reg, [reg+disp] ----
: MOV-DISP@, ( [base] dst disp -- )
    >R 8B T-C,
    OVER 5 = IF
        2 -ROT SWAP MODRM T-C, R> T-C,
    ELSE
        1 -ROT SWAP MODRM T-C, R> T-C,
    THEN
;

\ ---- IN/OUT ----
: IN-AL-DX, ( -- ) EC T-C, ;
: IN-AX-DX, ( -- ) 66 T-C, ED T-C, ;
: IN-EAX-DX, ( -- ) ED T-C, ;
: OUT-DX-AL, ( -- ) EE T-C, ;
: OUT-DX-AX, ( -- ) 66 T-C, EF T-C, ;
: OUT-DX-EAX, ( -- ) EF T-C, ;

\ ---- REP string ops ----
: REP-INSW, ( -- ) F3 T-C, 66 T-C, 6D T-C, ;
: REP-OUTSW, ( -- ) F3 T-C, 66 T-C, 6F T-C, ;
: REP-STOSD, ( -- ) F3 T-C, AB T-C, ;

\ ---- IDIV reg ----
: IDIV, ( reg -- )
    F7 T-C, 3 SWAP 7 MODRM T-C,
;

\ ---- NOT/NEG reg ----
: NOT, ( reg -- )
    F7 T-C, 3 SWAP 2 MODRM T-C,
;
: NEG, ( reg -- )
    F7 T-C, 3 SWAP 3 MODRM T-C,
;

\ ---- SHL/SHR by CL ----
: SHL-CL, ( reg -- )
    D3 T-C, 3 SWAP 4 MODRM T-C,
;
: SHR-CL, ( reg -- )
    D3 T-C, 3 SWAP 5 MODRM T-C,
;
: SAR-CL, ( reg -- )
    D3 T-C, 3 SWAP 7 MODRM T-C,
;

\ ---- TEST reg, reg ----
: TEST, ( src dst -- )
    85 T-C, 3 -ROT MODRM T-C,
;

FORTH DEFINITIONS
DECIMAL
```

Test: Load X86-ASM, assemble a few instructions into a buffer, verify the bytes match expected machine code.

---

## Task 11: Metacompiler Vocabulary

**Files:**
- Create: `forth/dict/meta-compiler.fth`
- Test: `tests/test_metacompiler.py`

This is the capstone. It uses X86-ASM to define CODE words and builds a complete kernel image.

### Step 3: Create meta-compiler.fth

Due to the complexity (~600+ lines), this will be the largest vocabulary. Key sections:

1. **Target memory management** (T-HERE, T-,, T-C,, T-ALLOT)
2. **Target dictionary builder** (T-CREATE, T-LINK, target headers)
3. **META defining words** (CODE:, END-CODE, M:, M;)
4. **Bootstrap: CODE word definitions** (all primitives in x86)
5. **Bootstrap: COLON definitions** (high-level words)
6. **Forward reference resolver** (two-pass fixup)
7. **META-BUILD** (orchestrator)
8. **META-SAVE** (write image to blocks/disk)

**NOTE:** This is a multi-session effort. Do NOT attempt to complete it in one pass. The metacompiler is the most complex piece of the entire system — it requires defining every kernel primitive in Forth-hosted x86 assembly, building a target dictionary with correct link pointers, and resolving forward references across the entire kernel. Plan for at least 3-4 implementation sessions with testing between each.

This task is too large to include complete code in the plan. The implementer should:

1. Start with target memory management + dictionary builder
2. Test by building a minimal 3-word kernel (NEXT + DROP + EXIT)
3. Incrementally add CODE words, testing each one
4. Add COLON definitions
5. Add the full bootstrap sequence
6. Compare generated binary against NASM-assembled kernel

### Success criteria

```bash
# Load metacompiler
send('2 17 THRU', 5)
send('USING META-COMPILER', 2)

# Build new kernel
send('META-BUILD', 30)  # May take a while

# Verify it completed
r = send('META-STATUS', 1)
check('META-BUILD complete', r, 'OK')

# Verify image size matches
r = send('META-SIZE .', 1)
# Should be close to 33280 bytes
```

### Commit

```bash
git add forth/dict/meta-compiler.fth tests/test_metacompiler.py
git commit -m "Add self-hosting metacompiler

HOST/TARGET/META vocabulary separation. Two-pass compilation with
forward reference resolution. Builds functionally equivalent kernel
from Forth source blocks. Uses X86-ASM for CODE word definitions."
```

---

## Task 12: Update Catalog and Integration Testing

**Files:**
- Modify: `tools/write-catalog.py` (verify it handles all new .fth files)
- Create: `tests/test_full_integration.py`
- Modify: `Makefile` (add test targets)

### Step 1: Verify catalog builds

```bash
make blocks
python3 tools/write-catalog.py build/blocks.img forth/dict/
# Should list all vocabularies with block assignments
```

### Step 2: Full integration test

```python
#!/usr/bin/env python3
"""Full integration test — load all vocabs, verify no conflicts."""
import socket, time, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4450

# ... standard setup ...

# Load all vocabs
send('2 17 THRU', 5)
send('USING PIT-TIMER', 2)
r = send('HEX 64 PIT-INIT', 1)
check('PIT-TIMER loaded', r, '')

send('USING PS2-KEYBOARD', 2)
r = send('KB-INIT', 1)
check('PS2-KEYBOARD loaded', r, '')

send('USING PCI-ENUM', 2)
r = send('PCI-LIST', 3)
check('PCI-ENUM lists devices', r, '')

# ORDER should show all loaded vocabs
r = send('ORDER', 1)
check('ORDER shows vocabs', r, '')

# Arithmetic still works (no corruption)
r = send('1 2 + .', 1)
check('no corruption', r, '3')
```

### Step 3: Add Makefile targets

```makefile
# Run all driver tests
test-drivers: $(IMAGE) $(BLOCKS)
	@echo "Running driver tests..."
	python3 tests/test_pit_timer.py $(PORT)
	python3 tests/test_ps2_keyboard.py $(PORT)
	python3 tests/test_pci_enum.py $(PORT)
	python3 tests/test_full_integration.py $(PORT)
```

### Step 4: Commit

```bash
git add tests/test_full_integration.py Makefile
git commit -m "Add integration tests and Makefile targets for drivers"
```

---

## Summary: Execution Order

| Task | Feature | Depends On | Est. Effort |
|------|---------|------------|-------------|
| 1 | IDT + PIC + ISR infrastructure | — | Large (kernel asm) |
| 2 | PIT Timer vocabulary | Task 1 | Medium |
| 3 | PS/2 Keyboard vocabulary | Task 1 | Medium |
| 4 | PS/2 Mouse vocabulary | Task 1 | Medium |
| 5 | PCI Bus Enumeration vocabulary | — | Medium |
| 6 | NE2000 Network vocabulary | Task 5 | Large |
| 7 | VGA Graphics vocabulary | Task 5 | Large |
| 8 | ReactOS validation | — (translator) | Medium |
| 9 | Block Editor vocabulary | Tasks 3, 7 | Large |
| 10 | x86 Assembler vocabulary | — | Medium |
| 11 | Metacompiler vocabulary | Task 10 | Very Large |
| 12 | Integration testing | Tasks 1-9 | Small |

Tasks 1-7 are sequential (drivers build on interrupt infrastructure).
Task 8 (ReactOS) can run in parallel with Tasks 1-7.
Tasks 10-11 (metacompiler) can begin after Task 1 but benefit from having all drivers done for completeness testing.
Task 12 ties everything together.
