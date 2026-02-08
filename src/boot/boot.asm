; ============================================================================
; Bare-Metal Forth Bootloader
; ============================================================================
; 
; This bootloader:
; 1. Loads from disk (first sector = MBR)
; 2. Enables A20 line for full memory access
; 3. Switches to 32-bit protected mode
; 4. Loads kernel from disk
; 5. Jumps to Forth kernel
;
; Boot sequence: BIOS -> boot.asm -> forth.asm
;
; Memory Map:
;   0x0000:0x7C00  - Bootloader (512 bytes, this file)
;   0x0000:0x7E00  - Kernel load address
;   0x0000:0x9000  - Stack (grows down)
;   0x00100000     - Extended memory (1MB+, our playground)
;
; ============================================================================

[BITS 16]
[ORG 0x7C00]

; ============================================================================
; Constants
; ============================================================================

KERNEL_OFFSET       equ 0x7E00      ; Where we load the kernel
KERNEL_SECTORS      equ 64          ; Load 64 sectors (32KB) of kernel
STACK_TOP           equ 0x9000      ; Stack top in real mode

; VGA text mode constants
VGA_WIDTH           equ 80
VGA_HEIGHT          equ 25
VGA_SEGMENT         equ 0xB800

; ============================================================================
; Entry Point
; ============================================================================

start:
    ; Disable interrupts during setup
    cli
    
    ; Set up segments
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, STACK_TOP
    
    ; Save boot drive
    mov [boot_drive], dl
    
    ; Re-enable interrupts
    sti
    
    ; Clear screen and show banner
    call clear_screen
    mov si, msg_boot
    call print_string
    
    ; Load kernel from disk
    mov si, msg_loading
    call print_string
    call load_kernel
    
    ; Enable A20 line
    mov si, msg_a20
    call print_string
    call enable_a20
    
    ; Switch to protected mode
    mov si, msg_pmode
    call print_string
    call switch_to_pm
    
    ; Never returns

; ============================================================================
; 16-bit Real Mode Functions
; ============================================================================

; ----------------------------------------------------------------------------
; clear_screen - Clear screen using BIOS
; ----------------------------------------------------------------------------
clear_screen:
    push ax
    push bx
    push cx
    push dx
    
    mov ax, 0x0600          ; Scroll up, clear
    mov bh, 0x07            ; White on black
    mov cx, 0x0000          ; Top-left
    mov dx, 0x184F          ; Bottom-right (24,79)
    int 0x10
    
    ; Move cursor to top-left
    mov ah, 0x02
    mov bh, 0x00
    mov dh, 0x00
    mov dl, 0x00
    int 0x10
    
    pop dx
    pop cx
    pop bx
    pop ax
    ret

; ----------------------------------------------------------------------------
; print_string - Print null-terminated string at SI
; ----------------------------------------------------------------------------
print_string:
    push ax
    push bx
    push si
    
    mov ah, 0x0E            ; Teletype output
    mov bh, 0x00            ; Page 0
    
.loop:
    lodsb                   ; Load byte from SI
    test al, al             ; Check for null
    jz .done
    int 0x10                ; Print character
    jmp .loop
    
.done:
    pop si
    pop bx
    pop ax
    ret

; ----------------------------------------------------------------------------
; print_hex - Print AL as two hex digits
; ----------------------------------------------------------------------------
print_hex:
    push ax
    push bx
    push cx
    
    mov cl, al              ; Save original
    
    ; High nibble
    shr al, 4
    call .print_nibble
    
    ; Low nibble
    mov al, cl
    and al, 0x0F
    call .print_nibble
    
    pop cx
    pop bx
    pop ax
    ret
    
.print_nibble:
    cmp al, 10
    jl .digit
    add al, 'A' - 10
    jmp .print
.digit:
    add al, '0'
.print:
    mov ah, 0x0E
    int 0x10
    ret

; ----------------------------------------------------------------------------
; load_kernel - Load kernel sectors from disk
; ----------------------------------------------------------------------------
load_kernel:
    push ax
    push bx
    push cx
    push dx
    
    mov bx, KERNEL_OFFSET   ; ES:BX = destination
    mov dh, 0               ; Head 0
    mov dl, [boot_drive]    ; Boot drive
    mov ch, 0               ; Cylinder 0
    mov cl, 2               ; Start at sector 2 (sector 1 = boot)
    
    ; Read in chunks (max 128 sectors per read on some BIOSes)
    mov si, KERNEL_SECTORS
    
.read_loop:
    ; Calculate sectors to read this iteration
    mov al, si
    cmp al, 64              ; Max 64 sectors per read
    jle .do_read
    mov al, 64
    
.do_read:
    push ax                 ; Save sector count
    
    mov ah, 0x02            ; BIOS read sectors
    int 0x13
    jc .error               ; Carry set = error
    
    pop cx                  ; Restore sector count to CX
    
    ; Update counters
    sub si, cx              ; Remaining sectors
    jz .done
    
    ; Update destination
    mov ax, cx
    shl ax, 5               ; * 32 (512/16 = 32 paragraphs per sector)
    add bx, ax
    
    ; Update sector number
    add cl, al
    cmp cl, 63              ; Max sector
    jle .read_loop
    
    ; Move to next head/cylinder
    mov cl, 1
    inc dh
    cmp dh, 2
    jl .read_loop
    mov dh, 0
    inc ch
    jmp .read_loop
    
.done:
    mov si, msg_ok
    call print_string
    pop dx
    pop cx
    pop bx
    pop ax
    ret
    
.error:
    mov si, msg_error
    call print_string
    mov al, ah              ; Error code
    call print_hex
    cli
    hlt

; ----------------------------------------------------------------------------
; enable_a20 - Enable A20 line for full memory access
; ----------------------------------------------------------------------------
enable_a20:
    push ax
    
    ; Try BIOS method first
    mov ax, 0x2401
    int 0x15
    jnc .check_a20
    
    ; Try keyboard controller method
    call .wait_kbd
    mov al, 0xAD            ; Disable keyboard
    out 0x64, al
    
    call .wait_kbd
    mov al, 0xD0            ; Read output port
    out 0x64, al
    
    call .wait_kbd_data
    in al, 0x60
    push ax
    
    call .wait_kbd
    mov al, 0xD1            ; Write output port
    out 0x64, al
    
    call .wait_kbd
    pop ax
    or al, 2                ; Set A20 bit
    out 0x60, al
    
    call .wait_kbd
    mov al, 0xAE            ; Enable keyboard
    out 0x64, al
    
    call .wait_kbd
    
.check_a20:
    ; Verify A20 is enabled
    push ds
    push es
    push di
    push si
    
    xor ax, ax
    mov es, ax
    mov di, 0x0500
    
    mov ax, 0xFFFF
    mov ds, ax
    mov si, 0x0510
    
    mov byte [es:di], 0x00
    mov byte [ds:si], 0xFF
    
    cmp byte [es:di], 0xFF
    
    pop si
    pop di
    pop es
    pop ds
    
    je .a20_failed
    
    mov si, msg_ok
    call print_string
    pop ax
    ret
    
.a20_failed:
    mov si, msg_a20_fail
    call print_string
    cli
    hlt
    
.wait_kbd:
    in al, 0x64
    test al, 2
    jnz .wait_kbd
    ret
    
.wait_kbd_data:
    in al, 0x64
    test al, 1
    jz .wait_kbd_data
    ret

; ============================================================================
; Switch to Protected Mode
; ============================================================================

switch_to_pm:
    cli                     ; Disable interrupts
    
    lgdt [gdt_descriptor]   ; Load GDT
    
    ; Set PE (Protection Enable) bit in CR0
    mov eax, cr0
    or eax, 1
    mov cr0, eax
    
    ; Far jump to flush pipeline and load CS
    jmp CODE_SEG:pm_start

; ============================================================================
; 32-bit Protected Mode Code
; ============================================================================

[BITS 32]

pm_start:
    ; Set up segment registers
    mov ax, DATA_SEG
    mov ds, ax
    mov es, ax
    mov fs, ax
    mov gs, ax
    mov ss, ax
    
    ; Set up stack
    mov esp, 0x90000
    
    ; Print "OK" in VGA memory (top-right corner)
    mov dword [0xB8000 + (VGA_WIDTH - 4) * 2], 0x0F4B0F4F  ; "OK" in white
    
    ; Jump to kernel
    jmp KERNEL_OFFSET

; ============================================================================
; Global Descriptor Table
; ============================================================================

gdt_start:

gdt_null:                   ; Null descriptor (required)
    dd 0
    dd 0

gdt_code:                   ; Code segment
    dw 0xFFFF               ; Limit (low)
    dw 0x0000               ; Base (low)
    db 0x00                 ; Base (middle)
    db 10011010b            ; Access: Present, Ring 0, Code, Exec/Read
    db 11001111b            ; Flags: 4K granularity, 32-bit + Limit (high)
    db 0x00                 ; Base (high)

gdt_data:                   ; Data segment
    dw 0xFFFF               ; Limit (low)
    dw 0x0000               ; Base (low)
    db 0x00                 ; Base (middle)
    db 10010010b            ; Access: Present, Ring 0, Data, Read/Write
    db 11001111b            ; Flags: 4K granularity, 32-bit + Limit (high)
    db 0x00                 ; Base (high)

gdt_end:

gdt_descriptor:
    dw gdt_end - gdt_start - 1  ; Size
    dd gdt_start                 ; Address

; Segment selectors
CODE_SEG equ gdt_code - gdt_start
DATA_SEG equ gdt_data - gdt_start

; ============================================================================
; Data Section
; ============================================================================

boot_drive:     db 0

msg_boot:       db 'Bare-Metal Forth v0.1 - Ship Builders System', 13, 10
                db '====================================', 13, 10, 0
msg_loading:    db 'Loading kernel... ', 0
msg_a20:        db 'Enabling A20... ', 0
msg_pmode:      db 'Entering protected mode...', 13, 10, 0
msg_ok:         db 'OK', 13, 10, 0
msg_error:      db 'DISK ERROR: ', 0
msg_a20_fail:   db 'FAILED', 13, 10, 0

; ============================================================================
; Boot Signature
; ============================================================================

times 510 - ($ - $$) db 0   ; Pad to 510 bytes
dw 0xAA55                   ; Boot signature
