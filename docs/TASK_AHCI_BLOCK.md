# TASK: AHCI Block System — Wire BLOCK to AHCI on Real Hardware
# Critical fix: HP 15-bs0xx hangs on BLOCK because ATA PIO has no timeout

## The Problem

On the HP 15-bs0xx, `0 LIST` hangs forever. Root cause: the kernel
`BLOCK` word calls `ata_read_sector` which calls `ata_wait_ready`.
`ata_wait_ready` spins on the BSY bit in the ATA status register with
no timeout:

```nasm
ata_wait_ready:
    mov dx, ATA_CMD_STATUS   ; 0x1F7
.wait:
    in al, dx
    test al, 0x80            ; BSY bit
    jnz .wait                ; SPINS FOREVER if no ATA drive
    ret
```

The HP's SATA controller (Intel Sunrise Point AHCI, visible as
"Intel AHCI at 00:17.00" in boot output) does NOT expose legacy ATA
I/O ports (0x1F0-0x1F7). Reading 0x1F7 returns 0xFF (floating bus),
which has BSY set (bit 7), causing infinite spin.

The AHCI vocabulary DOES work on HP — "AHCI ok" in boot output proves
it. But the kernel `BLOCK`/`SAVE-BUFFERS` path bypasses AHCI entirely.

## Two Required Fixes

### Fix 1 — Add timeout to ata_wait_ready (prevents hang, QEMU safe)

`ata_wait_ready` and `ata_wait_drq` in `src/kernel/forth.asm` must
timeout instead of spinning forever. A 32-bit counter of ~10,000,000
iterations gives ~100ms timeout on a 3GHz machine (conservative).

On QEMU this has no effect — ATA responds immediately. On HP with no
ATA device, it returns error (CF set) after timeout instead of hanging.

### Fix 2 — AHCI-BLOCK: redirect BLOCK through AHCI on real hardware

The kernel `BLOCK` word calls `blk_find_buffer` → `ata_read_sector`.
We need a path where BLOCK calls `ahci_read_sector` instead when AHCI
is available.

Approach: add a VARIABLE `BLK-READ-HOOK` to the kernel. At boot it
points to `ata_read_sector`. The AHCI vocabulary sets it to
`ahci_read_sector` during AHCI-INIT. The `BLOCK` code calls through
the hook instead of directly.

This is a kernel patch + AHCI vocab patch. No new vocab needed.

## Repository

~/projects/forthos (github.com/jeweledtech/bare-metal-forth)

## Fix 1: Timeout in src/kernel/forth.asm

### 1a: ata_wait_ready with timeout

Find `ata_wait_ready` in forth.asm and replace:

```nasm
; BEFORE — hangs forever:
ata_wait_ready:
    mov dx, ATA_CMD_STATUS
.wait:
    in al, dx
    test al, 0x80               ; BSY bit
    jnz .wait
    ret
```

Replace with:

```nasm
; AFTER — timeout after ~10M iterations (~100ms at 3GHz):
ata_wait_ready:
    mov dx, ATA_CMD_STATUS
    mov ecx, 10000000           ; timeout counter
.wait:
    in al, dx
    test al, 0x80               ; BSY bit
    jz .ready
    dec ecx
    jnz .wait
    stc                         ; CF=1: timeout error
    ret
.ready:
    clc                         ; CF=0: success
    ret
```

### 1b: ata_wait_drq with timeout

Same pattern — find `ata_wait_drq` and add the same timeout:

```nasm
; AFTER:
ata_wait_drq:
    mov dx, ATA_CMD_STATUS
    mov ecx, 10000000
.wait:
    in al, dx
    test al, 0x80               ; Still busy?
    jnz .check_timeout
    test al, 0x01               ; ERR bit?
    jnz .error
    test al, 0x08               ; DRQ bit?
    jnz .ready
.check_timeout:
    dec ecx
    jnz .wait
    stc                         ; timeout
    ret
.error:
    stc
    ret
.ready:
    clc
    ret
```

### 1c: Propagate CF from ata_wait_ready into ata_read_sector

`ata_read_sector` currently calls `ata_wait_ready` but ignores CF.
Add a check:

```nasm
ata_read_sector:
    call ata_wait_ready
    jc .done                    ; ADD THIS: bail on timeout/error
    ; ... rest of existing code ...
```

Same for `ata_write_sector`.

### 1d: Add BLK-READ-HOOK variable to kernel memory map

After the existing system variable declarations (near VAR_STATE,
VAR_HERE etc.), add:

```nasm
; Block I/O hook — points to sector-read function
; Default: ata_read_sector. AHCI vocab sets this to ahci_read_sector.
; Signature: ( EBX=LBA EDI=buffer-addr -- CF=error? )
BLK_READ_HOOK   equ 0x2804C     ; next free slot after existing vars
BLK_WRITE_HOOK  equ 0x28050     ; for SAVE-BUFFERS
```

Verify 0x2804C is actually free by checking the memory map in forth.asm.
The existing vars end at VAR_FORTH_LATEST (0x28048) + 4 bytes = 0x2804C.
That should be free — confirm before using.

Add DEFVAR entries so Forth code can read/write the hooks:

```nasm
DEFVAR "BLK-READ-HOOK",  BLK_READ_HOOK_VAR,  BLK_READ_HOOK
DEFVAR "BLK-WRITE-HOOK", BLK_WRITE_HOOK_VAR, BLK_WRITE_HOOK
```

### 1e: Initialize hooks to ata_read_sector at boot

In `kernel_start` or the initialization sequence, after the existing
variable setup:

```nasm
    mov dword [BLK_READ_HOOK],  ata_read_sector
    mov dword [BLK_WRITE_HOOK], ata_write_sector
```

### 1f: Wire blk_find_buffer path to call through hook

In `BLOCK` (the DEFCODE for BLOCK), find where `ata_read_sector` is
called directly and replace with an indirect call:

```nasm
; BEFORE:
    call ata_read_sector

; AFTER:
    call [BLK_READ_HOOK]
```

Same for `ata_write_sector` in the `SAVE-BUFFERS` / `blk_flush` path.

There are two call sites to update:
1. In the BLOCK DEFCODE, for the read-on-cache-miss path
2. In the SAVE-BUFFERS / blk_write path

Search for `call ata_read_sector` and `call ata_write_sector` in
forth.asm — replace both with the indirect form.

## Fix 2: AHCI vocab patch — set the hook during AHCI-INIT

### 2a: Add ahci_read_sector assembly stub in forth.asm

The hook needs a native assembly function with the same signature as
`ata_read_sector`:

```
Input:  EBX = LBA sector number (32-bit)
        EDI = destination buffer
Output: CF clear = success, CF set = error
Clobbers: EAX, ECX, EDX (must preserve ESI = Forth IP)
```

Add this stub near `ata_read_sector` in forth.asm:

```nasm
; ----------------------------------------------------------------------------
; ahci_read_sector - Read one 512-byte sector via AHCI
; Input:  EBX = LBA sector number, EDI = destination buffer
; Output: CF clear = success, CF set = error
; Clobbers: EAX, ECX, EDX
; Note: AHCI_PORT_BASE must be initialized by AHCI vocab before use
; ----------------------------------------------------------------------------
ahci_read_sector:
    ; Check if AHCI is initialized
    cmp dword [AHCI_PORT_BASE], 0
    je .no_ahci

    ; Use AHCI port 0 (single drive)
    ; The AHCI vocab already has the full command issue sequence.
    ; This stub calls back into the Forth AHCI-READ-SECTOR word
    ; by pushing args and using a pre-computed CFA.
    ; Simpler: replicate the minimal AHCI read sequence here.

    ; Port base = AHCI_PORT_BASE (set by AHCI vocab AHCI-INIT)
    mov eax, [AHCI_PORT_BASE]  ; port MMIO base

    ; Wait for port idle (PxCMD.CR = 0 and PxCMD.FR = 0)
    ; PxCMD offset = 0x18 from port base
    mov ecx, 100000
.wait_idle:
    mov edx, [eax + 0x18]      ; PxCMD
    test edx, 0x8001            ; CR | ST bits
    jz .port_idle
    dec ecx
    jnz .wait_idle
    stc
    ret

.port_idle:
    ; Build command in AHCI command table
    ; FIS at AHCI_CFIS_BASE (set during AHCI-INIT)
    ; Command slot 0 used exclusively for block I/O

    ; Write H2D Register FIS to command table
    mov ecx, [AHCI_CFIS_BASE]
    mov byte [ecx + 0],  0x27  ; FIS type: H2D Register
    mov byte [ecx + 1],  0x80  ; C=1 (command, not control)
    mov byte [ecx + 2],  0x25  ; Command: READ DMA EX (48-bit)
    mov byte [ecx + 3],  0     ; Features (low)
    mov dword [ecx + 4], ebx   ; LBA[27:0] + device
    and dword [ecx + 4], 0x0FFFFFFF
    or  dword [ecx + 4], 0x40000000  \ LBA mode bit
    mov byte [ecx + 8],  0     ; LBA[47:32] high bytes (0 for <4GB)
    mov byte [ecx + 9],  0
    mov byte [ecx + 10], 0
    mov byte [ecx + 11], 0     ; Features (high)
    mov word [ecx + 12], 1     ; Count: 1 sector
    mov byte [ecx + 14], 0     ; Icc
    mov byte [ecx + 15], 0     ; Control

    ; Set PRDT entry: physical address = EDI, byte count = 511 (512-1)
    mov ecx, [AHCI_PRDT_BASE]
    mov [ecx + 0],  edi        ; Data base address (low)
    mov dword [ecx + 4], 0     ; Data base address (high) = 0
    mov dword [ecx + 8], 0     ; Reserved
    mov dword [ecx + 12], 511  ; Byte count - 1 (DBC field, bit 31=IRQ)

    ; Clear PxIS (interrupt status) before command
    mov eax, [AHCI_PORT_BASE]
    mov dword [eax + 0x10], 0xFFFFFFFF  ; PxIS = clear all

    ; Issue command: set PxCI bit 0 (command slot 0)
    mov dword [eax + 0x38], 1  ; PxCI

    ; Poll PxCI until bit 0 clears (command complete)
    mov ecx, 5000000            ; ~50ms timeout
.wait_done:
    mov edx, [eax + 0x38]      ; PxCI
    test edx, 1
    jz .done_ok
    ; Check PxIS for error
    mov edx, [eax + 0x10]      ; PxIS
    test edx, 0x40000000        ; TFES (Task File Error Status)
    jnz .ahci_error
    dec ecx
    jnz .wait_done
    stc
    ret

.ahci_error:
    stc
    ret

.done_ok:
    clc
    ret

.no_ahci:
    stc                        ; No AHCI: return error
    ret
```

NOTE: This requires three new kernel variables:
- `AHCI_PORT_BASE` — MMIO address of port 0 (set by AHCI-INIT)
- `AHCI_CFIS_BASE` — physical address of command FIS buffer
- `AHCI_PRDT_BASE` — physical address of PRDT entry

These are currently managed inside the AHCI vocabulary. They need to
be promoted to kernel-level variables so `ahci_read_sector` can access
them from assembly. Add them near BLK_READ_HOOK:

```nasm
AHCI_PORT_BASE  equ 0x28054    ; AHCI port 0 MMIO base (0 = not init)
AHCI_CFIS_BASE  equ 0x28058    ; Command FIS buffer address
AHCI_PRDT_BASE  equ 0x2805C    ; PRDT entry address
```

Expose as DEFVAR:
```nasm
DEFVAR "AHCI-PORT-BASE", AHCI_PORT_BASE_VAR, AHCI_PORT_BASE
DEFVAR "AHCI-CFIS-BASE", AHCI_CFIS_BASE_VAR, AHCI_CFIS_BASE
DEFVAR "AHCI-PRDT-BASE", AHCI_PRDT_BASE_VAR, AHCI_PRDT_BASE
```

### 2b: Add ahci_write_sector assembly stub

Same structure as ahci_read_sector but uses WRITE DMA EX (0x35)
and OUTSB direction instead of INSB. The PRDT entry points to the
source buffer (EDI in the write case — caller convention must match).

For write: Input EBX=LBA, ESI=source buffer (matches ata_write_sector).

```nasm
ahci_write_sector:
    ; Same structure as ahci_read_sector but:
    ; - Command = 0x35 (WRITE DMA EX)
    ; - PRDT data address = ESI (source buffer)
    ; Full implementation follows same pattern
    ; ... (implement fully, not stubbed)
```

### 2c: Patch forth/dict/ahci.fth — set kernel hooks during AHCI-INIT

Find `AHCI-INIT` in `forth/dict/ahci.fth` (or whatever the init word
is called). After confirming the port is ready, add:

```forth
\ Set kernel block I/O hooks to use AHCI
\ These Forth words store into the kernel VARIABLE slots
\ that blk_find_buffer and SAVE-BUFFERS call through.
\ ahci_read_sector and ahci_write_sector are kernel asm functions
\ whose addresses we need to store. Use ' (tick) to get the CFA
\ of the CODE words we'll define, or use the DEFVAR addresses.

\ Expose asm function addresses as Forth constants:
\ (These need to be added to forth.asm as DEFCODE words or
\  as constants whose values are the asm function labels)

' AHCI-READ-SECT  BLK-READ-HOOK  !
' AHCI-WRITE-SECT BLK-WRITE-HOOK !
```

This requires adding Forth-callable wrappers for `ahci_read_sector`
and `ahci_write_sector` in forth.asm:

```nasm
; Forth-callable wrapper for ahci_read_sector
; Stack: ( lba buf -- )  (matching ata_read_sector convention)
DEFCODE "AHCI-READ-SECT", AHCI_READ_SECT, 0
    pop edi                    ; buf
    pop ebx                    ; lba
    call ahci_read_sector
    ; push error flag?
    NEXT

DEFCODE "AHCI-WRITE-SECT", AHCI_WRITE_SECT, 0
    pop esi                    ; src buf
    pop ebx                    ; lba
    call ahci_write_sector
    NEXT
```

BUT — the BLK-READ-HOOK stores a raw function pointer (asm address),
not a Forth CFA. The hook is called with `call [BLK_READ_HOOK]` from
assembly. So it must point directly to `ahci_read_sector`, not to the
Forth DEFCODE wrapper. The cleanest approach: define a kernel constant
whose value is the address of `ahci_read_sector`:

```nasm
; In forth.asm, after ahci_read_sector:
DEFCONST "AHCI-READ-ADDR", AHCI_READ_ADDR, ahci_read_sector
DEFCONST "AHCI-WRITE-ADDR", AHCI_WRITE_ADDR, ahci_write_sector
```

Then in ahci.fth AHCI-INIT:
```forth
\ Wire AHCI into block system
AHCI-READ-ADDR  BLK-READ-HOOK  !
AHCI-WRITE-ADDR BLK-WRITE-HOOK !
\ Also store port base and buffer addresses for asm stub
AHCI-PORT-BASE-ADDR AHCI-PORT-BASE !  \ kernel var
AHCI-CFIS-ADDR      AHCI-CFIS-BASE !  \ kernel var
AHCI-PRDT-ADDR      AHCI-PRDT-BASE !  \ kernel var
```

The AHCI vocab already has `AHCI-PORT` (port MMIO address) and the
command slot/PRDT addresses as VARIABLEs. Look up their exact names
in `forth/dict/ahci.fth` before writing this code.

### 2d: AHCI write sector support

The current AHCI vocabulary may only implement reads. Check whether
`ahci_write_sector` and SAVE-BUFFERS support exist. If not, SAVE-BUFFERS
must be disabled on HP hardware (or just refuse if BLK-WRITE-HOOK is 0).

For the demo, read-only block access is sufficient — vocabularies are
read from disk, not written back. Add a guard:

```forth
\ In SAVE-BUFFERS, before writing:
BLK-WRITE-HOOK @ 0= IF
  ." SAVE-BUFFERS: no write hook (read-only)" CR EXIT
THEN
```

## Part 3: Also fix ALSO AUTO-DETECT timing

The boot output shows AUTO-DETECT runs before vocabularies are loaded.
The AHCI hook needs to be set AFTER AUTO-DETECT (which calls AHCI-INIT).
Verify the boot sequence:

1. Kernel boots → BLK-READ-HOOK = ata_read_sector (default)
2. AUTO-DETECT loads automatically (already happens at boot)
3. AUTO-DETECT calls AHCI-INIT (or equivalent)
4. AHCI-INIT sets BLK-READ-HOOK = ahci_read_sector
5. User types `0 LIST` → now goes through AHCI → works

If AUTO-DETECT does NOT call the hook-setting code, the user must
manually trigger it. Check `forth/dict/auto-detect.fth` to see if
AHCI-INIT is called there. If AHCI-INIT already runs at boot
(evidenced by "AHCI ok" in boot output), we just need the hook-setting
code to be part of AHCI-INIT.

## Part 4: Tests

### 4a: QEMU regression — ATA timeout must not break existing tests

The timeout in `ata_wait_ready` must not fire during normal QEMU
operation. QEMU's ATA responds in <<1ms. A 10,000,000-iteration timeout
at QEMU speed (~100ms at 100MHz emulated) gives plenty of margin.

Verify: all existing tests still pass with `make test`. The timeout
only fires on real hardware with no ATA device.

### 4b: New test: BLK-READ-HOOK exists and is non-zero

Add to `tests/test_integration.py` or a new `tests/test_block_hook.py`:

```python
def test_blk_read_hook_defined():
    """BLK-READ-HOOK variable exists and is initialized non-zero"""
    r = send(s, "BLK-READ-HOOK @ .")
    assert '?' not in r
    val = int(r.strip().split()[-2], 16)  # parse hex
    assert val != 0, "BLK-READ-HOOK must be non-zero at boot"

def test_blk_write_hook_defined():
    """BLK-WRITE-HOOK variable exists"""
    r = send(s, "BLK-WRITE-HOOK @ .")
    assert '?' not in r

def test_ahci_addr_constants():
    """AHCI-READ-ADDR and AHCI-WRITE-ADDR are defined"""
    r = send(s, "AHCI-READ-ADDR .")
    assert '?' not in r
```

### 4c: HP hardware validation test

After fix is deployed via PXE:

```
ok 0 LIST
```

Must print block 0 contents (catalog) rather than hanging. This is the
acceptance criterion for the entire task.

Expected output:
```
Screen 0
\ FORTHOSBLOCKS CATALOG V1
...
ok
```

## Part 5: Alternate simpler approach — consider first

Before implementing the full hook mechanism, consider whether the AHCI
vocabulary already has a Forth-level `AHCI-BLOCK` word (or equivalent)
that reads a block via AHCI. If so, the simplest fix is:

1. Add ATA timeout (Fix 1 — always needed)
2. Add `AHCI-LOAD` ( n -- addr ) to AHCI vocab: like BLOCK but via AHCI
3. Redefine `BLOCK` to call AHCI-LOAD when AHCI is active:

```forth
\ In AHCI vocab, after AHCI-INIT succeeds:
: BLOCK ( n -- addr )    \ redefine kernel BLOCK
  AHCI-LOAD
;
```

This is a Forth-level redefinition — it shadows the kernel BLOCK word
in the current search order. Simpler than patching forth.asm, but only
works if the Forth search order includes AHCI before FORTH.

**Check if this simpler approach is viable before implementing the asm
hook mechanism.** Read `forth/dict/ahci.fth` to see what block-level
words already exist.

## Implementation Priority

1. **Fix 1 (ATA timeout) — MUST DO FIRST**
   - Prevents hardware hang
   - Zero risk to QEMU
   - Commit immediately as a hotfix

2. **Simpler Forth BLOCK redefinition — try this second**
   - Check if AHCI vocab has block-level words
   - If yes: redefine BLOCK in AHCI vocab after init
   - Test on HP via PXE

3. **Full hook mechanism (Fix 2) — do if simpler approach fails**
   - More invasive kernel change
   - Required if Forth redefinition doesn't work (e.g. search order issues)

## Sequence of Events for Claude Code

1. Read `forth/dict/ahci.fth` — identify existing block-level words
   and exact variable names for port base, CFIS, PRDT

2. Read `src/kernel/forth.asm` — find:
   - `ata_wait_ready` exact code
   - `ata_wait_drq` exact code
   - `BLOCK` DEFCODE implementation
   - Memory map: verify 0x2804C is free

3. Implement Fix 1 (ATA timeout) as a standalone commit:
   ```
   Fix ATA wait loop: add timeout to prevent hardware hang

   ata_wait_ready and ata_wait_drq spin forever if ATA device absent.
   On HP 15-bs0xx (AHCI-only), 0x1F7 reads 0xFF (BSY set), causing
   0 LIST to hang with no escape. Add 10M-iteration timeout (~100ms).
   CF set on timeout = error return, same as existing error path.
   All QEMU tests unaffected (ATA responds in <1ms).
   ```

4. Try simpler approach: check if AHCI vocab can redefine BLOCK

5. If simpler approach works — commit that. If not, implement full hook.

6. Deploy via PXE to HP, test `0 LIST`

7. Final commit message:
   ```
   Wire BLOCK system through AHCI on HP hardware

   HP 15-bs0xx has no legacy ATA PIO ports — block reads must go
   through AHCI. Two changes:
   1. ATA timeout: prevents infinite hang when ATA absent
   2. AHCI-BLOCK: redefine BLOCK to use AHCI when initialized
      (or: BLK-READ-HOOK kernel mechanism if redefinition fails)

   HP validation: 0 LIST prints catalog block without hanging.
   QEMU regression: all N tests still pass.
   ```

## Critical Notes for Claude Code

### Do NOT break QEMU

The ATA timeout and AHCI hook must be transparent to QEMU. QEMU uses
ATA PIO (the existing path). The hook defaults to `ata_read_sector`,
so QEMU continues using ATA. The hook only switches to `ahci_read_sector`
when the AHCI vocab explicitly sets it during AHCI-INIT.

### AHCI command slot / CFIS addresses

The AHCI vocabulary allocates a command list and command table at fixed
addresses (set during AHCI-INIT). These are already working on HP
(disk survey ran successfully). The asm stub must use the same addresses
the vocab set up — do not allocate new ones.

### LBA 0 = block 0 in ForthOS block system

The kernel `BLOCK` word maps block N to LBA N*2 (two 512-byte sectors
per 1024-byte Forth block). `ahci_read_sector` takes an LBA number.
The existing mapping in `blk_find_buffer` computes `LBA = block# * 2`.
This math is unchanged — only the sector read function is swapped.

### The PRDT DBAU bug was already fixed

Memory note from project history: Bug #N fixed the PRDT DBAU (upper
32-bit DMA address) being garbage from PXE boot. The fix zeroed DBAU.
The `ahci_read_sector` stub must also zero DBAU (offset +4 in PRDT).
This is already in the stub above — confirm it's correct.
