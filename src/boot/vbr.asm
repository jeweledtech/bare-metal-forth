; ============================================================================
; Bare-Metal Forth VBR (chainload variant)
; ============================================================================
;
; SIBLING of boot.asm, NOT a replacement. boot.asm remains the proven
; USB/PXE memdisk loader and must stay byte-stable. This variant is the
; boot sector BUILD-VBR (forth/dict/install.fth) bakes and installs into
; OWN-EXTENT; GRUB chainloads it at 0x7C00 with DL = boot drive.
;
; Deltas from boot.asm:
;   1. EDD-or-die: no CHS fallback. A chainloaded instance runs on a
;      BIOS that just proved EDD by loading this sector's partition.
;   2. DAP start-LBA assembles as VBR-SENTINEL (0xDEADBEEF). BUILD-VBR
;      bakes OWN-BASE+1 over it (VBR-LBA-OFF). Unbaked = loud DISK ERR,
;      never a silent boot of the wrong sectors.
;   3. Chunked read: 7 chunks x 32 sectors (= KERNEL_SECTORS 224).
;      SECTOR-COUNT CAP DEFENSE ONLY. The proven single-shot 224-sector
;      read has only ever run against memdisk's INT13; real AH=42h
;      commonly caps transfers at 127 sectors. Chunking does NOT avoid
;      64KB boundary crossings: offset stays 0x7E00 and the segment
;      advances 0x400/chunk, so chunk bases are 0x7E00/0xBE00/0xFE00/
;      0x13E00/... and chunk 2 straddles 0x10000 (later ones 0x20000).
;      Boundary handling is left to the BIOS, exactly as the proven
;      single-shot loader (which crosses the same boundaries and works
;      on iron) leaves it. Contiguity, not alignment, is what the
;      fixed-offset scheme buys.
;
; Memory map and PM handoff identical to boot.asm.
; ============================================================================

[BITS 16]
[ORG 0x7C00]

; ============================================================================
; Constants
; ============================================================================

KERNEL_OFFSET       equ 0x7E00      ; Where we load the kernel
KERNEL_SECTORS      equ 224         ; 224 sectors = 112KB (matches padding)
CHUNK_SECTORS       equ 32          ; 224 = 7 x 32, exact
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

    ; ---- Chunked EDD read, or die ----
    mov cx, KERNEL_SECTORS / CHUNK_SECTORS
.read_loop:
    push cx
    mov word [dap_count], CHUNK_SECTORS  ; some BIOSes rewrite count
    mov ah, 0x42                ; Extended Read
    mov dl, [boot_drive]
    mov si, dap
    int 0x13
    jc disk_error               ; EDD-or-die: no fallback
    add dword [dap_lba], CHUNK_SECTORS
    add word [dap_seg], (CHUNK_SECTORS * 512) >> 4   ; 0x400
    pop cx
    loop .read_loop

    ; ---- Memdisk detection ----
    ; Kept from boot.asm deliberately: on a chainload boot there is no
    ; $INT13SF hook, so this writes 0 to 0x28098 -- MEMDISK-VAR = 0 is
    ; the correct fail-closed state for the installed instance (block
    ; vector stays a loud-fail stub).
    ; Safe hook layout (syslinux mstructs.h):
    ;   +0  jump[3]   +3  "$INT13SF"  +11 vendor[8]
    ;   +19 old_hook  +23 flags       +27 mbft_ptr
    ; mBFT layout:
    ;   +0  "mBFT" (ACPI hdr, 36 bytes total)
    ;   +36 safe_hook_ptr  +40 mdi_hdr
    ;   +44 diskbuf (32-bit linear address)
    ; Access 0x28098 via segment 0x2800:0x98
    push ds
    mov ax, 0x2800
    mov ds, ax
    mov dword [0x98], 0             ; default = 0
    pop ds

    ; Read INT 13h vector from IVT
    xor ax, ax
    mov es, ax
    mov bx, [es:0x4C]
    mov ax, [es:0x4E]
    mov es, ax                      ; ES:BX = handler

    ; Signature "$INT13SF" at handler+3
    cmp dword [es:bx+3], 0x544E4924
    jne .no_memdisk
    cmp dword [es:bx+7], 0x46533331
    jne .no_memdisk

    ; mBFT physical address at handler+27
    mov eax, [es:bx+27]
    test eax, eax
    jz .no_memdisk
    ; Convert physical addr to seg:off for
    ; real-mode access (addr < 1MB guaranteed)
    mov si, ax
    and si, 0x000F                  ; offset = low 4 bits
    shr eax, 4
    mov es, ax                      ; segment = addr >> 4

    ; Verify "mBFT" signature at mBFT+0
    cmp dword [es:si], 0x5446426D
    jne .no_memdisk

    ; diskbuf at mBFT+44
    mov eax, [es:si+44]
    test eax, eax
    jz .no_memdisk
    push ds
    push bx
    mov bx, 0x2800
    mov ds, bx
    mov [0x98], eax
    pop bx
    pop ds

.no_memdisk:
    xor ax, ax
    mov es, ax

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
msg_boot:       db 'BMForth VBR', 13, 10, 0     ; distinct banner: iron
                                                ; output attributes which
                                                ; loader ran
msg_err:        db 'DISK ERR', 0

; Disk Address Packet. Segment and LBA fields are RUNTIME-mutated in
; this resident copy at 0x7C00 by the chunk loop; the on-disk template
; is never touched (BUILD-VBR patches only its RAM copy of the
; template, and only the LBA field, at VBR-LBA-OFF).
dap:
    db 16                       ; DAP size (16 bytes)
    db 0                        ; reserved
dap_count:
    dw CHUNK_SECTORS            ; sectors per call (rewritten each chunk)
dap_off:
    dw KERNEL_OFFSET            ; destination offset (constant)
dap_seg:
    dw 0                        ; destination segment (advances 0x400)
dap_lba:
    dd 0xDEADBEEF               ; VBR-SENTINEL -- BUILD-VBR bakes
                                ; OWN-BASE+1 here (VBR-LBA-OFF)
    dd 0                        ; LBA high dword

; ============================================================================
; Boot Signature
; ============================================================================

times 510 - ($ - $$) db 0
dw 0xAA55
