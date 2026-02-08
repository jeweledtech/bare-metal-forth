; ============================================================================
; Bare-Metal Forth Bootloader
; ============================================================================
;
; This bootloader:
; 1. Loads from disk (first sector = MBR, 512 bytes)
; 2. Loads kernel sectors from disk into memory at 0x7E00
; 3. Enables A20 line for full memory access
; 4. Switches to 32-bit protected mode
; 5. Jumps to Forth kernel at 0x7E00
;
; Boot sequence: BIOS -> boot.asm -> forth.asm
;
; Memory Map:
;   0x0000:0x7C00  - Bootloader (512 bytes, this file)
;   0x0000:0x7E00  - Kernel load address (32KB)
;   0x0000:0x9000  - Real mode stack (grows down)
;
; ============================================================================

[BITS 16]
[ORG 0x7C00]

; ============================================================================
; Constants
; ============================================================================

KERNEL_OFFSET       equ 0x7E00      ; Where we load the kernel
KERNEL_SECTORS      equ 64          ; 64 sectors = 32KB (matches kernel padding)
STACK_TOP           equ 0x7C00      ; Stack below bootloader (grows down)

; ============================================================================
; Entry Point
; ============================================================================

start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, STACK_TOP
    mov [boot_drive], dl        ; Save boot drive number
    sti

    ; Print banner
    mov si, msg_boot
    call print_string

    ; Load kernel from disk — single BIOS call
    ; INT 13h AH=02: Read sectors
    mov ah, 0x02
    mov al, KERNEL_SECTORS      ; Number of sectors to read
    mov bx, KERNEL_OFFSET       ; ES:BX = destination buffer
    mov ch, 0                   ; Cylinder 0
    mov cl, 2                   ; Start at sector 2 (sector 1 = boot)
    mov dh, 0                   ; Head 0
    mov dl, [boot_drive]        ; Drive number
    int 0x13
    jc disk_error               ; Carry flag = error

    ; Enable A20 line
    call enable_a20

    ; Switch to protected mode
    cli
    lgdt [gdt_descriptor]
    mov eax, cr0
    or eax, 1
    mov cr0, eax
    jmp CODE_SEG:pm_start       ; Far jump flushes pipeline

; ============================================================================
; 16-bit Subroutines
; ============================================================================

print_string:
    push ax
    push si
    mov ah, 0x0E
.loop:
    lodsb
    test al, al
    jz .done
    int 0x10
    jmp .loop
.done:
    pop si
    pop ax
    ret

enable_a20:
    ; Try BIOS method first (fastest, most compatible)
    mov ax, 0x2401
    int 0x15
    jnc .done

    ; Fallback: keyboard controller method
    call .wait_kbd
    mov al, 0xAD
    out 0x64, al
    call .wait_kbd
    mov al, 0xD0
    out 0x64, al
    call .wait_kbd_data
    in al, 0x60
    push ax
    call .wait_kbd
    mov al, 0xD1
    out 0x64, al
    call .wait_kbd
    pop ax
    or al, 2
    out 0x60, al
    call .wait_kbd
    mov al, 0xAE
    out 0x64, al
    call .wait_kbd
.done:
    ret

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

disk_error:
    mov si, msg_err
    call print_string
    cli
    hlt

; ============================================================================
; 32-bit Protected Mode Entry
; ============================================================================

[BITS 32]

pm_start:
    mov ax, DATA_SEG
    mov ds, ax
    mov es, ax
    mov fs, ax
    mov gs, ax
    mov ss, ax
    mov esp, 0x90000

    ; Jump to kernel
    jmp KERNEL_OFFSET

; ============================================================================
; Global Descriptor Table
; ============================================================================

gdt_start:

gdt_null:
    dd 0, 0

gdt_code:                       ; Code segment: ring 0, exec/read, 4GB
    dw 0xFFFF
    dw 0x0000
    db 0x00
    db 10011010b
    db 11001111b
    db 0x00

gdt_data:                       ; Data segment: ring 0, read/write, 4GB
    dw 0xFFFF
    dw 0x0000
    db 0x00
    db 10010010b
    db 11001111b
    db 0x00

gdt_end:

gdt_descriptor:
    dw gdt_end - gdt_start - 1
    dd gdt_start

CODE_SEG equ gdt_code - gdt_start
DATA_SEG equ gdt_data - gdt_start

; ============================================================================
; Data
; ============================================================================

boot_drive:     db 0
msg_boot:       db 'BMForth v0.1', 13, 10, 0
msg_err:        db 'DISK ERR', 0

; ============================================================================
; Boot Signature
; ============================================================================

times 510 - ($ - $$) db 0
dw 0xAA55
