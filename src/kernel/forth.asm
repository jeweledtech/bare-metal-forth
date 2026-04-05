; ============================================================================
; Bare-Metal Forth Kernel - Threaded Code Interpreter
; ============================================================================
;
; This is the core Forth system implementing:
; - Direct Threaded Code (DTC) interpreter
; - Core stack manipulation words
; - Arithmetic and logic operations
; - Memory access (@ ! C@ C!)
; - I/O primitives (direct hardware access)
; - Dictionary and compiler
;
; Register Usage:
;   ESI = Instruction Pointer (IP) - points to next word address
;   EBP = Return Stack Pointer (RSP)
;   ESP = Data Stack Pointer (PSP)
;   EAX = Working register / Top of Stack cache
;   EBX = Working register
;   ECX = Working register
;   EDX = Working register / I/O
;
; Memory Map:
;   0x00000500 - Free conventional memory (data stack grows into here)
;   0x00007C00 - Data stack top (grows down into free memory)
;   0x00007E00 - Kernel start (loaded by bootloader, 64KB)
;   0x00017E00 - Kernel end
;   0x00020000 - Return stack (grows down)
;   0x00028000 - System variables (STATE, HERE, LATEST, BASE, TIB, TOIN)
;   0x00028018 - Block/vocabulary variables (BLK, SCR, search order, etc.)
;   0x00028060 - Block buffer headers (4 x 12 bytes)
;   0x00028100 - Terminal Input Buffer (256 bytes)
;   0x00028200 - Block buffers (4 x 1024 bytes)
;   0x00029200 - Guard byte + free space
;   0x00030000 - Dictionary start
;   0x000B8000 - VGA text buffer
;
; ============================================================================

[BITS 32]
[ORG 0x7E00]

; ============================================================================
; Constants
; ============================================================================

; Stack locations
DATA_STACK_TOP      equ 0x7C00      ; Below kernel, in free conventional memory
RETURN_STACK_TOP    equ 0x20000

; Dictionary
DICT_START          equ 0x30000
DICT_SIZE           equ 0x50000     ; 320KB for dictionary

; HERE and other system variables
VAR_STATE           equ 0x28000     ; Compilation state (0=interpret, 1=compile)
VAR_HERE            equ 0x28004     ; Dictionary pointer
VAR_LATEST          equ 0x28008     ; Latest word in dictionary
VAR_BASE            equ 0x2800C     ; Number base (default 10)
VAR_TIB             equ 0x28010     ; Terminal Input Buffer pointer
VAR_TOIN            equ 0x28014     ; >IN - offset into TIB

; Block storage variables
VAR_BLK             equ 0x28018     ; Current block being LOADed (0 = keyboard)
VAR_SCR             equ 0x2801C     ; Last block LISTed

; Vocabulary / search order variables
VAR_SEARCH_ORDER    equ 0x28020     ; 8 cells: vocabulary LATEST pointers (32 bytes)
VAR_SEARCH_DEPTH    equ 0x28040     ; Number of entries in search order (1-8)
VAR_CURRENT         equ 0x28044     ; Vocab that receives new definitions (addr of LATEST cell)
VAR_FORTH_LATEST    equ 0x28048     ; FORTH vocabulary's own LATEST pointer
VAR_BLOCK_LOADING   equ 0x2804C     ; Flag: 1 = LOAD just set up a block (skip first exhaustion check)

; Block buffer management
BLK_BUF_HEADERS     equ 0x28060     ; 4 headers x 12 bytes = 48 bytes
                                    ; Each: [block#(4)] [flags(4)] [age(4)]
                                    ; flags: bit 0=valid, bit 1=dirty
BLK_BUF_CUR         equ 0x28090     ; Index of current buffer (for UPDATE)
BLK_BUF_CLOCK        equ 0x28094    ; LRU age counter
BLK_NUM_BUFFERS     equ 4
BLK_HEADER_SIZE     equ 12
BLK_BUF_FLAG_VALID  equ 1
BLK_BUF_FLAG_DIRTY  equ 2
BLOCK_SIZE          equ 1024        ; 1KB per Forth block

; Block buffer data: 4 x 1024 bytes
BLK_BUF_DATA        equ 0x28200     ; 0x28200 - 0x291FF
BLK_BUF_GUARD       equ 0x29200     ; NUL guard byte for LOAD termination

; Input buffer
TIB_START           equ 0x28100     ; Terminal Input Buffer
TIB_SIZE            equ 256

; ATA PIO port constants (primary IDE controller)
ATA_DATA            equ 0x1F0
ATA_ERROR           equ 0x1F1
ATA_SECCOUNT        equ 0x1F2
ATA_LBA_LO          equ 0x1F3
ATA_LBA_MID         equ 0x1F4
ATA_LBA_HI          equ 0x1F5
ATA_DRIVE           equ 0x1F6
ATA_CMD_STATUS      equ 0x1F7
ATA_CTRL            equ 0x3F6

; VGA
VGA_TEXT            equ 0xB8000
VGA_WIDTH           equ 80
VGA_HEIGHT          equ 25
VGA_ATTR            equ 0x07        ; Light gray on black

; PIC (Programmable Interrupt Controller) ports
PIC1_CMD            equ 0x20        ; Master PIC command port
PIC1_DATA           equ 0x21        ; Master PIC data port
PIC2_CMD            equ 0xA0        ; Slave PIC command port
PIC2_DATA           equ 0xA1        ; Slave PIC data port
PIC_EOI             equ 0x20        ; End-of-interrupt command

; IDT (Interrupt Descriptor Table)
IDT_BASE            equ 0x29400     ; 256 entries x 8 bytes = 2048 bytes (0x29400-0x29BFF)
IDT_ENTRIES         equ 256
IDT_ENTRY_SIZE      equ 8

; ISR hook table (16 cells for future Forth-level IRQ hooks)
ISR_HOOK_TABLE      equ 0x29C00     ; 16 x 4 bytes = 64 bytes

; IRQ vector offsets (remapped)
IRQ_BASE_MASTER     equ 0x20        ; IRQ 0-7 -> INT 0x20-0x27
IRQ_BASE_SLAVE      equ 0x28        ; IRQ 8-15 -> INT 0x28-0x2F

; ISR data variables (in kernel data section, addresses resolved at assembly)
; These are labels in the data section, not EQU addresses in the sysvar area.
; Keyboard ring buffer
KB_RING_SIZE        equ 16          ; 16-byte ring buffer

; Word flags
F_IMMEDIATE         equ 0x80        ; Immediate word
F_HIDDEN            equ 0x40        ; Hidden from FIND
F_LENMASK           equ 0x3F        ; Length mask

; ECHOPORT trace buffer
TRACE_BUF_SIZE      equ 256         ; 256 entries (power of 2 for masking)
TRACE_ENTRY_SZ      equ 12          ; 12 bytes per entry
; Entry: [type:1][pad:1][port:2][value:4][caller:4]
; Types: 0=INB 1=OUTB 2=INW 3=OUTW 4=INL 5=OUTL
; caller = ESI (Forth IP) at time of I/O — points into calling word

; ============================================================================
; Threaded Code Interpreter Macros
; ============================================================================

; NEXT - Fetch next word and execute
; This is the heart of the Forth engine
%macro NEXT 0
    lodsd                   ; Load [ESI] into EAX, increment ESI
    jmp [eax]               ; Jump to code field
%endmacro

; PUSHRSP - Push to return stack
%macro PUSHRSP 1
    sub ebp, 4
    mov [ebp], %1
%endmacro

; POPRSP - Pop from return stack
%macro POPRSP 1
    mov %1, [ebp]
    add ebp, 4
%endmacro

; TRACE_PORT - Log a port I/O operation to trace ring buffer
; %1 = type byte (0-5), expects port in DX, value in EAX, caller in ESI
%macro TRACE_PORT 1
    cmp byte [trace_enabled], 0
    je %%skip
    push edi
    push ebx
    mov edi, [trace_head]
    mov ebx, edi
    and ebx, (TRACE_BUF_SIZE - 1)
    imul ebx, TRACE_ENTRY_SZ
    add ebx, trace_buf
    mov byte [ebx], %1             ; type
    mov byte [ebx+1], 0            ; pad
    mov [ebx+2], dx                ; port
    mov [ebx+4], eax               ; value
    mov [ebx+8], esi               ; caller (Forth IP)
    inc edi
    mov [trace_head], edi
    inc dword [trace_count]
    pop ebx
    pop edi
%%skip:
%endmacro

; ============================================================================
; Kernel Entry Point
; ============================================================================

; Serial port constants (COM1)
COM1_PORT       equ 0x3F8

kernel_start:
    ; Initialize stacks
    mov esp, DATA_STACK_TOP
    mov ebp, RETURN_STACK_TOP

    ; Initialize serial port (COM1) for debugging
    call init_serial

    ; Initialize variables
    mov dword [VAR_STATE], 0
    mov dword [VAR_HERE], DICT_START
    mov dword [VAR_LATEST], name_ADDR_READ_LINE ; Last built-in word
    mov dword [VAR_BASE], 10
    mov dword [VAR_TIB], TIB_START
    mov dword [VAR_TOIN], 0

    ; Initialize block storage variables
    mov dword [VAR_BLK], 0
    mov dword [VAR_SCR], 0
    mov dword [VAR_BLOCK_LOADING], 0
    mov dword [BLK_BUF_CUR], 0
    mov dword [BLK_BUF_CLOCK], 0
    ; Clear all 4 buffer headers (block#=-1, flags=0, age=0)
    mov edi, BLK_BUF_HEADERS
    mov ecx, BLK_NUM_BUFFERS
.init_buf_headers:
    mov dword [edi], 0xFFFFFFFF     ; block# = -1 (invalid)
    mov dword [edi + 4], 0          ; flags = 0
    mov dword [edi + 8], 0          ; age = 0
    add edi, BLK_HEADER_SIZE
    loop .init_buf_headers
    ; NUL guard byte after block buffers (for LOAD termination)
    mov byte [BLK_BUF_GUARD], 0

    ; Initialize vocabulary / search order
    mov dword [VAR_FORTH_LATEST], name_ADDR_READ_LINE ; FORTH vocab starts same as LATEST
    mov dword [VAR_SEARCH_DEPTH], 1
    mov dword [VAR_SEARCH_ORDER], VAR_FORTH_LATEST  ; Addr of FORTH's LATEST cell
    mov dword [VAR_CURRENT], VAR_FORTH_LATEST       ; New defs go into FORTH

    ; Initialize interrupt infrastructure (BEFORE sti)
    call init_pic                   ; Remap PIC, mask all IRQs
    call init_idt                   ; Build IDT, load IDTR
    sti                             ; Enable interrupts (all IRQs still masked)

    ; Unmask IRQ0 (timer) + IRQ1 (keyboard)
    ; Timer needed so hlt in read_key wakes periodically for serial polling
    in al, PIC1_DATA
    and al, ~0x03                   ; Clear bits 0+1 = unmask IRQ0 + IRQ1
    out PIC1_DATA, al

    ; Clear screen
    call init_screen

    ; Initialize 8042 keyboard controller (needed on real hardware)
    call kbd_init_8042

    ; Drain any scancodes captured during init
    mov dword [kb_ring_count], 0
    mov eax, [kb_ring_head]
    mov [kb_ring_tail], eax

    ; Print welcome message
    mov esi, msg_welcome
    call print_string

    ; Check for embedded vocabularies to evaluate at boot
    cmp dword [embed_size], 0
    je .no_embedded

    ; Push return frame on Forth return stack (LIFO order matching block_exhausted pop)
    ; block_exhausted pops: TIB, TOIN, BLK, ESI
    sub ebp, 4
    mov dword [ebp], cold_start     ; ESI: return to interactive loop after eval
    sub ebp, 4
    mov dword [ebp], 0              ; BLK: restore to 0 (interactive mode)
    sub ebp, 4
    mov dword [ebp], 0              ; TOIN: restore to 0
    sub ebp, 4
    mov dword [ebp], TIB_START      ; TIB: restore to serial input buffer

    ; Redirect interpreter to embedded source
    mov dword [VAR_TIB], embed_data
    mov dword [VAR_TOIN], 0
    mov dword [VAR_BLK], 1          ; Nonzero: prevents interactive read_line
    mov dword [VAR_BLOCK_LOADING], 1 ; Skip first exhaustion check

.no_embedded:
    ; Enter main interpreter loop
    mov esi, cold_start
    NEXT

; ============================================================================
; Dictionary Header Macro
; ============================================================================

; Dictionary entry format:
; +0: Link (4 bytes) - pointer to previous word
; +4: Flags + Length (1 byte)
; +5: Name (length bytes, not null-terminated)
; +n: Padding to 4-byte alignment
; +m: Code field (pointer to code)
; +m+4: Parameter field (varies)

%macro DEFWORD 3
    ; %1 = name string, %2 = label, %3 = flags
    align 4
name_%2:
    dd link                 ; Link to previous word
    %define link name_%2
    db %3 + %%end_name - %%start_name  ; Flags + length
%%start_name:
    db %1                   ; Name
%%end_name:
    align 4
%2:
    dd DOCOL               ; Code field: this is a colon definition
    ; Parameter field follows (list of word addresses)
%endmacro

%macro DEFCODE 3
    ; %1 = name string, %2 = label, %3 = flags
    align 4
name_%2:
    dd link
    %define link name_%2
    db %3 + %%end_name - %%start_name
%%start_name:
    db %1
%%end_name:
    align 4
%2:
    dd code_%2              ; Code field points to native code
code_%2:
    ; Native code follows
%endmacro

%macro DEFVAR 3
    ; %1 = name string, %2 = label, %3 = address of variable
    ; Variable storage is at the EQU address, initialized by kernel_start
    align 4
name_%2:
    dd link
    %define link name_%2
    db %%end_name - %%start_name
%%start_name:
    db %1
%%end_name:
    align 4
%2:
    dd code_%2
code_%2:
    push %3
    NEXT
%endmacro

%macro DEFCONST 3
    ; %1 = name string, %2 = label, %3 = value
    align 4
name_%2:
    dd link
    %define link name_%2
    db %%end_name - %%start_name
%%start_name:
    db %1
%%end_name:
    align 4
%2:
    dd code_%2
code_%2:
    push %3
    NEXT
%endmacro

; ============================================================================
; Core Interpreter Routines
; ============================================================================

; DOCOL - Enter a colon definition
; Called when a Forth word (non-primitive) is executed
DOCOL:
    PUSHRSP esi             ; Save return address
    add eax, 4              ; Skip code field
    mov esi, eax            ; Set IP to parameter field
    NEXT

; ============================================================================
; Dictionary - Initialize link
; ============================================================================

    link dd 0               ; Start of linked list

; ============================================================================
; Primitive Words
; ============================================================================

; --- Stack Manipulation ---

DEFCODE "DROP", DROP, 0
    pop eax                 ; Discard TOS
    NEXT

DEFCODE "DUP", DUP, 0
    mov eax, [esp]
    push eax
    NEXT

DEFCODE "SWAP", SWAP, 0
    pop eax
    pop ebx
    push eax
    push ebx
    NEXT

DEFCODE "OVER", OVER, 0
    mov eax, [esp + 4]
    push eax
    NEXT

DEFCODE "ROT", ROT, 0
    pop eax                 ; ( a b c -- b c a )
    pop ebx
    pop ecx
    push ebx
    push eax
    push ecx
    NEXT

DEFCODE "-ROT", NROT, 0
    pop eax                 ; ( a b c -- c a b )
    pop ebx
    pop ecx
    push eax
    push ecx
    push ebx
    NEXT

DEFCODE "2DROP", TWODROP, 0
    pop eax
    pop eax
    NEXT

DEFCODE "2DUP", TWODUP, 0
    mov eax, [esp]
    mov ebx, [esp + 4]
    push ebx
    push eax
    NEXT

DEFCODE "2SWAP", TWOSWAP, 0
    pop eax                 ; ( a b c d -- c d a b )
    pop ebx
    pop ecx
    pop edx
    push ebx
    push eax
    push edx
    push ecx
    NEXT

DEFCODE "2OVER", TWOOVER, 0
    mov eax, [esp + 12]         ; ( a b c d -- a b c d a b )
    mov ebx, [esp + 8]
    push ebx
    push eax
    NEXT

DEFCODE "?DUP", QDUP, 0
    mov eax, [esp]
    test eax, eax
    jz .skip
    push eax
.skip:
    NEXT

DEFCODE "NIP", NIP, 0
    pop eax                 ; ( a b -- b )
    pop ebx
    push eax
    NEXT

DEFCODE "TUCK", TUCK, 0
    pop eax                 ; ( a b -- b a b )
    pop ebx
    push eax
    push ebx
    push eax
    NEXT

DEFCODE "PICK", PICK, 0
    pop eax                 ; n
    mov eax, [esp + eax*4]
    push eax
    NEXT

; --- Return Stack ---

DEFCODE ">R", TOR, 0
    pop eax
    PUSHRSP eax
    NEXT

DEFCODE "R>", FROMR, 0
    POPRSP eax
    push eax
    NEXT

DEFCODE "R@", RFETCH, 0
    mov eax, [ebp]
    push eax
    NEXT

DEFCODE "RDROP", RDROP, 0
    add ebp, 4
    NEXT

; --- Arithmetic ---

DEFCODE "+", ADD, 0
    pop eax
    add [esp], eax
    NEXT

DEFCODE "-", SUB, 0
    pop eax
    sub [esp], eax
    NEXT

DEFCODE "*", MUL, 0
    pop eax
    pop ebx
    imul ebx
    push eax
    NEXT

; Floored division (Forth-83 semantics!)
; This is the CORRECT implementation that handles negative numbers properly
DEFCODE "/", DIV, 0
    pop ebx                 ; Divisor
    pop eax                 ; Dividend
    
    ; Check for divide by zero
    test ebx, ebx
    jz .div_zero
    
    ; Save signs
    mov ecx, eax
    xor ecx, ebx            ; ECX = sign of quotient
    
    ; Make both positive for division
    test eax, eax
    jns .pos_dividend
    neg eax
.pos_dividend:
    test ebx, ebx
    jns .pos_divisor
    neg ebx
.pos_divisor:
    
    ; Perform unsigned division
    xor edx, edx
    div ebx                 ; EAX = quotient, EDX = remainder
    
    ; Apply floored semantics:
    ; If signs differ AND there's a remainder, subtract 1 from quotient
    test ecx, ecx
    jns .positive_result
    
    ; Negative result
    test edx, edx           ; Was there a remainder?
    jz .just_negate
    inc eax                 ; Adjustment for floored division
.just_negate:
    neg eax
    
.positive_result:
    push eax
    NEXT
    
.div_zero:
    ; Division by zero - push special value
    push 0x7FFFFFFF         ; Max positive int
    NEXT

; Floored modulo (Forth-83 semantics!)
DEFCODE "MOD", MOD, 0
    pop ebx                 ; Divisor
    pop eax                 ; Dividend
    
    test ebx, ebx
    jz .mod_zero
    
    ; Standard division
    cdq                     ; Sign-extend EAX into EDX:EAX
    idiv ebx                ; EAX = quotient, EDX = remainder
    
    ; Floored MOD: remainder takes sign of divisor
    ; If remainder != 0 and signs differ, add divisor to remainder
    test edx, edx
    jz .done
    
    mov ecx, edx
    xor ecx, ebx            ; Check if signs differ
    jns .done
    
    add edx, ebx            ; Adjust for floored semantics
    
.done:
    push edx
    NEXT
    
.mod_zero:
    push 0
    NEXT

DEFCODE "/MOD", DIVMOD, 0
    pop ebx                 ; Divisor
    pop eax                 ; Dividend
    
    test ebx, ebx
    jz .divmod_zero
    
    cdq
    idiv ebx
    
    ; Apply floored semantics: if remainder and divisor have opposite
    ; signs (meaning symmetric division gave wrong result), adjust.
    ; Check: (remainder XOR divisor) < 0 means opposite signs.
    mov ecx, edx
    xor ecx, ebx
    jns .no_adjust
    
    test edx, edx
    jz .no_adjust
    
    dec eax                 ; Adjust quotient
    add edx, ebx            ; Adjust remainder
    
.no_adjust:
    push edx                ; Remainder
    push eax                ; Quotient
    NEXT
    
.divmod_zero:
    push 0
    push 0x7FFFFFFF
    NEXT

DEFCODE "1+", INCR, 0
    inc dword [esp]
    NEXT

DEFCODE "1-", DECR, 0
    dec dword [esp]
    NEXT

DEFCODE "2+", INCR2, 0
    add dword [esp], 2
    NEXT

DEFCODE "2-", DECR2, 0
    sub dword [esp], 2
    NEXT

DEFCODE "4+", INCR4, 0
    add dword [esp], 4
    NEXT

DEFCODE "4-", DECR4, 0
    sub dword [esp], 4
    NEXT

DEFCODE "NEGATE", NEGATE, 0
    neg dword [esp]
    NEXT

DEFCODE "ABS", FABS, 0
    mov eax, [esp]
    test eax, eax
    jns .positive
    neg eax
    mov [esp], eax
.positive:
    NEXT

DEFCODE "MIN", MIN, 0
    pop eax
    pop ebx
    cmp eax, ebx
    jl .a_smaller
    push ebx
    NEXT
.a_smaller:
    push eax
    NEXT

DEFCODE "MAX", MAX, 0
    pop eax
    pop ebx
    cmp eax, ebx
    jg .a_larger
    push ebx
    NEXT
.a_larger:
    push eax
    NEXT

; --- Comparison ---

DEFCODE "=", EQU, 0
    pop eax
    pop ebx
    cmp eax, ebx
    sete al
    movzx eax, al
    neg eax                 ; 0 -> 0, 1 -> -1 (true)
    push eax
    NEXT

DEFCODE "<>", NEQU, 0
    pop eax
    pop ebx
    cmp eax, ebx
    setne al
    movzx eax, al
    neg eax
    push eax
    NEXT

DEFCODE "<", LT, 0
    pop eax
    pop ebx
    cmp ebx, eax
    setl al
    movzx eax, al
    neg eax
    push eax
    NEXT

DEFCODE ">", GT, 0
    pop eax
    pop ebx
    cmp ebx, eax
    setg al
    movzx eax, al
    neg eax
    push eax
    NEXT

DEFCODE "<=", LE, 0
    pop eax
    pop ebx
    cmp ebx, eax
    setle al
    movzx eax, al
    neg eax
    push eax
    NEXT

DEFCODE ">=", GE, 0
    pop eax
    pop ebx
    cmp ebx, eax
    setge al
    movzx eax, al
    neg eax
    push eax
    NEXT

DEFCODE "0=", ZEQU, 0
    pop eax
    test eax, eax
    setz al
    movzx eax, al
    neg eax
    push eax
    NEXT

DEFCODE "0<", ZLT, 0
    pop eax
    test eax, eax
    sets al
    movzx eax, al
    neg eax
    push eax
    NEXT

DEFCODE "0>", ZGT, 0
    pop eax
    test eax, eax
    setg al
    movzx eax, al
    neg eax
    push eax
    NEXT

DEFCODE "0<>", ZNEQU, 0
    pop eax
    test eax, eax
    setnz al
    movzx eax, al
    neg eax
    push eax
    NEXT

; --- Logic ---

DEFCODE "AND", AND, 0
    pop eax
    and [esp], eax
    NEXT

DEFCODE "OR", OR, 0
    pop eax
    or [esp], eax
    NEXT

DEFCODE "XOR", XOR, 0
    pop eax
    xor [esp], eax
    NEXT

DEFCODE "INVERT", INVERT, 0
    not dword [esp]
    NEXT

DEFCODE "LSHIFT", LSHIFT, 0
    pop ecx
    shl dword [esp], cl
    NEXT

DEFCODE "RSHIFT", RSHIFT, 0
    pop ecx
    shr dword [esp], cl
    NEXT

; --- Memory Access (The Dangerous Stuff!) ---

DEFCODE "@", FETCH, 0
    pop eax
    mov eax, [eax]
    push eax
    NEXT

DEFCODE "!", STORE, 0
    pop ebx                 ; Address
    pop eax                 ; Value
    mov [ebx], eax
    NEXT

DEFCODE "+!", ADDSTORE, 0
    pop ebx                 ; Address
    pop eax                 ; Value
    add [ebx], eax
    NEXT

DEFCODE "-!", SUBSTORE, 0
    pop ebx
    pop eax
    sub [ebx], eax
    NEXT

DEFCODE "C@", CFETCH, 0
    pop eax
    movzx eax, byte [eax]
    push eax
    NEXT

DEFCODE "C!", CSTORE, 0
    pop ebx                 ; Address
    pop eax                 ; Value
    mov [ebx], al
    NEXT

DEFCODE "W@", WFETCH, 0     ; Word (16-bit) fetch
    pop eax
    movzx eax, word [eax]
    push eax
    NEXT

DEFCODE "W!", WSTORE, 0     ; Word (16-bit) store
    pop ebx
    pop eax
    mov [ebx], ax
    NEXT

; Block memory operations
DEFCODE "CMOVE", CMOVE, 0   ; ( src dst count -- )
    PUSHRSP esi             ; Save Forth IP
    pop ecx                 ; Count
    pop edi                 ; Destination
    pop esi                 ; Source
    rep movsb
    POPRSP esi              ; Restore Forth IP
    NEXT

DEFCODE "CMOVE>", CMOVEUP, 0  ; Move from high addresses down
    PUSHRSP esi             ; Save Forth IP
    pop ecx
    pop edi
    pop esi
    add esi, ecx
    dec esi
    add edi, ecx
    dec edi
    std
    rep movsb
    cld
    POPRSP esi              ; Restore Forth IP
    NEXT

DEFCODE "FILL", FILL, 0     ; ( addr count byte -- )
    pop eax                 ; Byte
    pop ecx                 ; Count
    pop edi                 ; Address (EDI doesn't affect Forth IP, but save for consistency)
    rep stosb
    NEXT

; --- Direct I/O Port Access (Ring 0 only!) ---

DEFCODE "INB", INB, 0       ; ( port -- byte )
    pop edx
    xor eax, eax
    in al, dx
    TRACE_PORT 0                ; type=INB, port=DX, val=EAX
    push eax
    NEXT

DEFCODE "INW", INW, 0       ; ( port -- word )
    pop edx
    xor eax, eax
    in ax, dx
    TRACE_PORT 2                ; type=INW
    push eax
    NEXT

DEFCODE "INL", INL, 0       ; ( port -- dword )
    pop edx
    in eax, dx
    TRACE_PORT 4                ; type=INL
    push eax
    NEXT

DEFCODE "OUTB", OUTB, 0     ; ( byte port -- )
    pop edx
    pop eax
    TRACE_PORT 1                ; type=OUTB, before write
    out dx, al
    NEXT

DEFCODE "OUTW", OUTW, 0     ; ( word port -- )
    pop edx
    pop eax
    TRACE_PORT 3                ; type=OUTW
    out dx, ax
    NEXT

DEFCODE "OUTL", OUTL, 0     ; ( dword port -- )
    pop edx
    pop eax
    TRACE_PORT 5                ; type=OUTL
    out dx, eax
    NEXT

; --- I/O ---

DEFCODE "KEY", KEY, 0       ; ( -- char )
    call read_key
    push eax
    NEXT

DEFCODE "EMIT", EMIT, 0     ; ( char -- )
    pop eax
    call print_char
    NEXT

DEFCODE "CR", CR, 0
    mov al, 13
    call print_char
    mov al, 10
    call print_char
    NEXT

DEFCODE "SPACE", SPACE, 0
    mov al, ' '
    call print_char
    NEXT

DEFCODE "TYPE", TYPE, 0     ; ( addr len -- )
    pop ecx                 ; Length
    PUSHRSP esi             ; Save Forth IP
    pop esi                 ; Address
    test ecx, ecx
    jz .done
.loop:
    lodsb
    call print_char
    loop .loop
.done:
    POPRSP esi              ; Restore Forth IP
    NEXT

DEFCODE ".", DOT, 0         ; ( n -- ) Print number
    pop eax
    call print_number
    mov al, ' '
    call print_char
    NEXT

DEFCODE ".S", DOTS, 0       ; Show stack (non-destructive, bottom to top)
    PUSHRSP esi              ; Save Forth IP on return stack
    mov esi, msg_stack
    call print_string

    mov ecx, DATA_STACK_TOP
    sub ecx, esp
    shr ecx, 2              ; Number of items

    ; Safety cap: if depth > 64, something is wrong — cap it
    cmp ecx, 64
    jle .depth_ok
    mov ecx, 64
.depth_ok:
    ; Also guard against negative depth (ESP above DATA_STACK_TOP)
    test ecx, ecx
    jle .done

    ; Print bottom-to-top: start at deepest item (near DATA_STACK_TOP)
    ; and walk down toward ESP. Deepest item is at ESP + (depth-1)*4.
    mov edi, ecx
    shl edi, 2              ; edi = depth * 4
    add edi, esp
    sub edi, 4              ; edi = ESP + (depth-1)*4 = bottom of stack
.loop:
    test ecx, ecx
    jz .done
    mov eax, [edi]
    call print_number
    mov al, ' '
    call print_char
    sub edi, 4              ; Move toward top of stack (lower addresses)
    dec ecx
    jmp .loop
.done:
    mov al, '>'
    call print_char
    POPRSP esi               ; Restore Forth IP
    NEXT

; --- Variables and Constants ---

DEFVAR "STATE", STATE, VAR_STATE
DEFVAR "HERE", HERE, VAR_HERE
DEFVAR "LATEST", LATEST, VAR_LATEST
DEFVAR "BASE", BASE, VAR_BASE

DEFCONST "VERSION", VERSION, 1
DEFCONST "CELL", CELL, 4
DEFCONST "TRUE", TRUE, -1
DEFCONST "FALSE", FALSE, 0

; --- Control Flow ---

DEFCODE "EXIT", EXIT, 0
    POPRSP esi
    NEXT

DEFCODE "BRANCH", BRANCH, 0
    add esi, [esi]
    NEXT

DEFCODE "0BRANCH", ZBRANCH, 0
    pop eax
    test eax, eax
    jz code_BRANCH
    add esi, 4              ; Skip offset
    NEXT

DEFCODE "EXECUTE", EXECUTE, 0
    pop eax
    jmp [eax]

DEFCODE "LIT", LIT, 0
    lodsd
    push eax
    NEXT

; --- Dictionary ---

DEFCODE "'", TICK, 0        ; ( "name" -- xt )
    call word_
    call find_
    test eax, eax
    jz .not_found
    push eax
    NEXT
.not_found:
    push esi
    mov esi, msg_undefined
    call print_string
    pop esi
    NEXT

DEFCODE ",", COMMA, 0       ; ( x -- ) Compile x to dictionary
    pop eax
    call comma_
    NEXT

DEFCODE "C,", CCOMMA, 0     ; ( c -- ) Compile byte
    pop eax
    mov edi, [VAR_HERE]
    stosb
    mov [VAR_HERE], edi
    NEXT

DEFCODE "ALLOT", ALLOT, 0   ; ( n -- ) Allocate n bytes
    pop eax
    add [VAR_HERE], eax
    NEXT

DEFCODE "CREATE", CREATE, 0
    call word_              ; Get name
    call create_
    ; Write default CFA so CREATE'd words push their parameter field address
    mov eax, [VAR_HERE]
    mov dword [eax], code_DOCREATE
    add dword [VAR_HERE], 4
    NEXT

DEFCODE "FIND", FIND, 0     ; ( c-addr -- c-addr 0 | xt 1 | xt -1 )
    ; Simplified: just returns xt or 0
    call find_
    push eax
    NEXT

; --- Interpreter ---

; INTERPRET - Process one token from the input stream
; This is called repeatedly by cold_start: INTERPRET, BRANCH -8
; Each invocation handles exactly ONE word or number, then returns
; to the threaded code loop via NEXT. This keeps ESI/ESP/EBP clean.
DEFCODE "INTERPRET", INTERPRET, 0
    ; Check if we need to read a new line
    cmp dword [VAR_TOIN], 0
    jne .have_input

    ; TOIN=0: either need new line (interactive), block just loaded, or block exhausted
    cmp dword [VAR_BLK], 0
    je .interactive              ; BLK=0: interactive mode, need new line

    ; BLK!=0: check if LOAD just set up this block
    cmp dword [VAR_BLOCK_LOADING], 0
    je .block_exhausted          ; Flag clear: block truly exhausted
    mov dword [VAR_BLOCK_LOADING], 0  ; Clear the flag
    jmp .have_input              ; Start parsing the block

.interactive:

    ; Interactive mode: print prompt and read a line
    mov al, 'o'
    call print_char
    mov al, 'k'
    call print_char
    mov al, ' '
    call print_char

    ; Flush net console so prompt appears on dev machine
    cmp byte [net_console_enabled], 0
    je .no_prompt_flush
    call net_flush
.no_prompt_flush:

    ; Save state snapshot for Ctrl+C recovery
    mov [save_esp], esp
    mov [save_ebp], ebp
    mov eax, [VAR_STATE]
    mov [save_state], eax
    mov eax, [VAR_HERE]
    mov [save_here], eax
    mov eax, [VAR_LATEST]
    mov [save_latest], eax

    ; Read a line of input
    call read_line

    ; Check for break flag (Ctrl+C during input)
    cmp byte [break_flag], 0
    je .no_break
    mov byte [break_flag], 0
    jmp .do_break
.no_break:
    mov dword [VAR_TOIN], 0

.have_input:
    ; Parse next word
    call word_
    test eax, eax
    jz .end_of_line          ; Empty = end of line, loop back for new prompt

    ; Try to find it in the dictionary
    ; find_ returns: EAX = XT (or 0), ECX = flags+len byte
    call find_
    test eax, eax
    jz .try_number

    ; Found a word! EAX = XT, ECX = flags+len
    mov ebx, eax             ; Save XT in EBX

    ; Check compile vs interpret mode
    mov edx, [VAR_STATE]
    test edx, edx
    jz .execute_word          ; STATE=0: interpreting, always execute

    ; Compiling: check if word is IMMEDIATE
    test cl, F_IMMEDIATE
    jnz .execute_word         ; Immediate words execute even during compilation

    ; Compile the word's XT into the definition
    mov eax, ebx
    call comma_
    NEXT                      ; Return to cold_start loop for next token

.execute_word:
    mov eax, ebx
    jmp [eax]                 ; Execute the word (it will end with NEXT)

.try_number:
    ; word_buffer still has the token — try parsing as number
    call number_
    test edx, edx             ; EDX = 0 if success
    jnz .undefined

    ; Got a number in EAX
    mov edx, [VAR_STATE]
    test edx, edx
    jz .push_number

    ; Compiling: compile LIT + number
    push eax
    mov eax, LIT
    call comma_
    pop eax
    call comma_
    NEXT

.push_number:
    push eax                  ; Push number onto data stack
    NEXT

.end_of_line:
    ; Line fully consumed — NEXT returns to cold_start which loops
    ; back to INTERPRET for a new prompt
    NEXT

.undefined:
    ; Print the unknown word
    push esi
    mov esi, word_buffer
    call print_string
    mov esi, msg_undefined
    call print_string
    pop esi
    ; Reset compilation state on error (abort current definition)
    mov dword [VAR_STATE], 0
    NEXT

.block_exhausted:
    ; Block fully parsed — restore input state saved by LOAD
    POPRSP ecx
    mov [VAR_TIB], ecx          ; Restore TIB
    POPRSP ecx
    mov [VAR_TOIN], ecx         ; Restore >IN
    POPRSP ecx
    mov [VAR_BLK], ecx          ; Restore BLK (may be 0 for interactive, or outer block#)
    POPRSP esi                  ; Restore Forth IP (returns to caller of LOAD)
    NEXT

.do_break:
    ; Ctrl+C: restore saved state
    mov esp, [save_esp]
    mov ebp, [save_ebp]
    mov eax, [save_state]
    mov [VAR_STATE], eax
    mov eax, [save_here]
    mov [VAR_HERE], eax
    mov eax, [save_latest]
    mov [VAR_LATEST], eax
    mov dword [VAR_TOIN], 0
    mov dword [VAR_BLK], 0      ; Also reset BLK on break
    mov dword [VAR_BLOCK_LOADING], 0
    ; Print break message
    push esi
    mov esi, msg_break
    call print_string
    pop esi
    NEXT

DEFCODE "WORD", FWORD, 0    ; ( -- c-addr )
    call word_
    push eax
    NEXT

DEFCODE "NUMBER", NUMBER, 0 ; ( c-addr -- n )
    pop eax                     ; Discard c-addr (number_ reads word_buffer)
    call number_
    push eax
    NEXT

; ============================================================================
; Compiler Words - The Heart of Forth
; ============================================================================

; : (COLON) - Start a new word definition
; Creates dictionary header and enters compile mode
DEFCODE ":", COLON, 0
    call word_              ; Get word name
    call create_            ; Create dictionary header
    
    ; Store DOCOL as first cell (makes it a threaded word)
    mov eax, [VAR_HERE]
    mov dword [eax], DOCOL
    add dword [VAR_HERE], 4
    
    ; Hide the word during compilation
    mov eax, [VAR_LATEST]
    or byte [eax + 4], F_HIDDEN
    
    ; Enter compile mode
    mov dword [VAR_STATE], 1
    NEXT

; ; (SEMICOLON) - End word definition
; Compiles EXIT and exits compile mode
DEFCODE ";", SEMICOLON, F_IMMEDIATE
    ; Compile EXIT
    mov eax, [VAR_HERE]
    mov dword [eax], EXIT
    add dword [VAR_HERE], 4
    
    ; Unhide the word
    mov eax, [VAR_LATEST]
    and byte [eax + 4], ~F_HIDDEN
    
    ; Exit compile mode
    mov dword [VAR_STATE], 0
    NEXT

; IMMEDIATE - Mark the latest word as immediate
DEFCODE "IMMEDIATE", IMMEDIATE, F_IMMEDIATE
    mov eax, [VAR_LATEST]
    xor byte [eax + 4], F_IMMEDIATE    ; Toggle IMMEDIATE flag
    NEXT

; [ - Switch to interpret mode
DEFCODE "[", LBRAC, F_IMMEDIATE
    mov dword [VAR_STATE], 0
    NEXT

; ] - Switch to compile mode
DEFCODE "]", RBRAC, 0
    mov dword [VAR_STATE], 1
    NEXT

; LITERAL - Compile a literal (used at compile time)
; ( n -- )   At compile time, compiles LIT n
DEFCODE "LITERAL", LITERAL, F_IMMEDIATE
    mov eax, [VAR_HERE]
    mov dword [eax], LIT      ; Compile LIT
    pop ebx
    mov dword [eax + 4], ebx  ; Compile the number
    add dword [VAR_HERE], 8
    NEXT

; COMPILE, - Compile the xt on the stack
; ( xt -- )
DEFCODE "COMPILE,", COMPILEC, 0
    mov eax, [VAR_HERE]
    pop ebx
    mov [eax], ebx
    add dword [VAR_HERE], 4
    NEXT

; ' (TICK) in compile mode - already defined, but add COMPILE' for convenience
DEFCODE "[']", BRACKETTICK, F_IMMEDIATE
    call word_
    call find_
    test eax, eax
    jz .notfound
    ; Compile LIT <xt>
    mov ebx, [VAR_HERE]
    mov dword [ebx], LIT
    mov [ebx + 4], eax
    add dword [VAR_HERE], 8
.notfound:
    NEXT

; POSTPONE - Compile the compilation semantics of a word
; For IMMEDIATE words: compile the XT directly (execute at compile time of target)
; For non-immediate words: compile LIT <xt> COMPILE, (defer compilation)
DEFCODE "POSTPONE", POSTPONE, F_IMMEDIATE
    call word_
    call find_              ; EAX = XT, ECX = flags+len
    test eax, eax
    jz .notfound
    test cl, F_IMMEDIATE
    jnz .compile_immediate
    ; Non-immediate: compile  LIT <xt>  COMPILE,
    mov ebx, [VAR_HERE]
    mov dword [ebx], LIT
    mov [ebx + 4], eax
    mov dword [ebx + 8], COMPILEC
    add dword [VAR_HERE], 12
    NEXT
.compile_immediate:
    ; Immediate word: just compile XT directly
    mov ebx, [VAR_HERE]
    mov [ebx], eax
    add dword [VAR_HERE], 4
.notfound:
    NEXT

; ============================================================================
; Control Flow Words
; ============================================================================

; IF - Conditional branch
; ( flag -- )  At compile time: ( -- orig )
DEFCODE "IF", IF, F_IMMEDIATE
    ; Compile 0BRANCH
    mov eax, [VAR_HERE]
    mov dword [eax], ZBRANCH
    add dword [VAR_HERE], 4
    ; Push location of offset (to be patched later)
    push dword [VAR_HERE]
    ; Reserve space for offset
    add dword [VAR_HERE], 4
    NEXT

; THEN - Resolve forward branch
; ( orig -- )
DEFCODE "THEN", THEN, F_IMMEDIATE
    pop eax                    ; Get address to patch
    mov ebx, [VAR_HERE]
    sub ebx, eax               ; Calculate offset
    mov [eax], ebx             ; Patch the offset
    NEXT

; ELSE - Alternative branch
; ( orig1 -- orig2 )
DEFCODE "ELSE", ELSE, F_IMMEDIATE
    ; Compile unconditional BRANCH + reserve offset space
    mov eax, [VAR_HERE]
    mov dword [eax], BRANCH
    add dword [VAR_HERE], 4
    mov ebx, [VAR_HERE]         ; ebx = ELSE_patch (offset location for THEN)
    add dword [VAR_HERE], 4

    ; Swap: pop IF_patch, push ELSE_patch for THEN to resolve
    pop eax                     ; eax = IF_patch (from IF)
    push ebx                    ; Leave ELSE_patch for THEN

    ; Resolve IF: patch 0BRANCH offset to jump to current HERE
    mov ecx, [VAR_HERE]
    sub ecx, eax                ; offset = HERE - IF_patch
    mov [eax], ecx              ; Patch IF's forward branch
    NEXT

; BEGIN - Start of a loop
; ( -- dest )
DEFCODE "BEGIN", BEGIN, F_IMMEDIATE
    push dword [VAR_HERE]      ; Push current address
    NEXT

; UNTIL - Loop until condition is true
; ( dest -- )
DEFCODE "UNTIL", UNTIL, F_IMMEDIATE
    ; Compile 0BRANCH
    mov eax, [VAR_HERE]
    mov dword [eax], ZBRANCH
    add dword [VAR_HERE], 4
    ; Calculate backward offset
    ; BRANCH/0BRANCH use: add esi,[esi] (no lodsd advance)
    ; So offset = target - offset_cell_address
    pop ebx                    ; Get dest
    mov ecx, [VAR_HERE]
    sub ebx, ecx               ; Offset (negative for backward)
    mov [ecx], ebx
    add dword [VAR_HERE], 4
    NEXT

; AGAIN - Unconditional loop
; ( dest -- )
DEFCODE "AGAIN", AGAIN, F_IMMEDIATE
    ; Compile BRANCH
    mov eax, [VAR_HERE]
    mov dword [eax], BRANCH
    add dword [VAR_HERE], 4
    ; Calculate backward offset
    ; BRANCH uses: add esi,[esi] (no lodsd advance)
    ; So offset = target - offset_cell_address
    pop ebx
    mov ecx, [VAR_HERE]
    sub ebx, ecx
    mov [ecx], ebx
    add dword [VAR_HERE], 4
    NEXT

; WHILE - Test in middle of loop
; ( dest -- orig dest )
DEFCODE "WHILE", WHILE, F_IMMEDIATE
    ; Compile 0BRANCH
    mov eax, [VAR_HERE]
    mov dword [eax], ZBRANCH
    add dword [VAR_HERE], 4
    ; Push orig for REPEAT to patch
    push dword [VAR_HERE]
    add dword [VAR_HERE], 4
    ; Swap so dest is on top
    pop eax
    pop ebx
    push eax
    push ebx
    NEXT

; REPEAT - End of BEGIN...WHILE...REPEAT loop
; ( orig dest -- )
DEFCODE "REPEAT", REPEAT, F_IMMEDIATE
    ; Compile BRANCH back to BEGIN
    mov eax, [VAR_HERE]
    mov dword [eax], BRANCH
    add dword [VAR_HERE], 4
    ; Get dest and calculate backward offset
    ; BRANCH uses: add esi,[esi] (no lodsd advance)
    ; So offset = target - offset_cell_address
    pop ebx
    mov ecx, [VAR_HERE]
    sub ebx, ecx
    mov [ecx], ebx
    add dword [VAR_HERE], 4
    ; Patch WHILE's 0BRANCH (forward ref, already correct)
    pop eax
    mov ebx, [VAR_HERE]
    sub ebx, eax
    mov [eax], ebx
    NEXT

; DO - Counted loop start
; ( limit start -- )   At compile: ( -- do-sys )
DEFCODE "DO", DO, F_IMMEDIATE
    ; Compile (DO) which moves limit and index to return stack
    mov eax, [VAR_HERE]
    mov dword [eax], DODO       ; Compile XT (not code_DODO!)
    add dword [VAR_HERE], 4
    ; Push address for LOOP to know where to branch back
    push dword [VAR_HERE]
    NEXT

; Runtime (DO) - moves loop parameters to return stack
DEFCODE "(DO)", DODO, 0
    pop eax                    ; index
    pop ebx                    ; limit
    ; Push to return stack: limit, then index
    sub ebp, 4
    mov [ebp], ebx             ; limit
    sub ebp, 4
    mov [ebp], eax             ; index
    NEXT

; LOOP - Counted loop end
DEFCODE "LOOP", LOOP, F_IMMEDIATE
    ; Compile (LOOP)
    mov eax, [VAR_HERE]
    mov dword [eax], DOLOOP     ; Compile XT (not code_DOLOOP!)
    add dword [VAR_HERE], 4
    ; Calculate backward offset
    pop ebx                    ; Get loop start address (from DO)
    mov ecx, [VAR_HERE]
    sub ebx, ecx
    sub ebx, 4
    mov eax, [VAR_HERE]
    mov [eax], ebx
    add dword [VAR_HERE], 4
    NEXT

; Runtime (LOOP)
DEFCODE "(LOOP)", DOLOOP, 0
    ; Increment index
    mov eax, [ebp]             ; index
    inc eax
    mov [ebp], eax
    ; Compare with limit
    mov ebx, [ebp + 4]         ; limit
    cmp eax, ebx
    jge .done
    ; Branch back
    lodsd                      ; Get offset
    add esi, eax
    NEXT
.done:
    ; Exit loop - remove loop params from return stack
    add ebp, 8
    lodsd                      ; Skip offset
    NEXT

; +LOOP - Increment loop by arbitrary amount
DEFCODE "+LOOP", PLOOP, F_IMMEDIATE
    ; Compile (+LOOP)
    mov eax, [VAR_HERE]
    mov dword [eax], DOPLOOP    ; Compile XT (not code_DOPLOOP!)
    add dword [VAR_HERE], 4
    ; Same as LOOP for offset
    pop ebx
    mov ecx, [VAR_HERE]
    sub ebx, ecx
    sub ebx, 4
    mov eax, [VAR_HERE]
    mov [eax], ebx
    add dword [VAR_HERE], 4
    NEXT

; Runtime (+LOOP)
DEFCODE "(+LOOP)", DOPLOOP, 0
    pop ecx                    ; increment
    mov eax, [ebp]             ; index
    mov edx, eax               ; save old index
    add eax, ecx               ; new index
    mov [ebp], eax
    mov ebx, [ebp + 4]         ; limit
    ; Check for crossing (complex because of signed increment)
    ; Simplified: just check if index >= limit for positive increment
    test ecx, ecx
    js .negative
    cmp eax, ebx
    jge .done
    jmp .continue
.negative:
    cmp eax, ebx
    jl .done
.continue:
    lodsd
    add esi, eax
    NEXT
.done:
    add ebp, 8
    lodsd
    NEXT

; I - Get loop index
DEFCODE "I", I, 0
    mov eax, [ebp]
    push eax
    NEXT

; J - Get outer loop index
DEFCODE "J", J, 0
    mov eax, [ebp + 8]         ; Skip current loop's limit and index
    push eax
    NEXT

; LEAVE - Exit loop immediately
DEFCODE "LEAVE", LEAVE, 0
    ; Set index = limit to force exit
    mov eax, [ebp + 4]         ; limit
    mov [ebp], eax             ; index = limit
    NEXT

; UNLOOP - Remove loop parameters from return stack
DEFCODE "UNLOOP", UNLOOP, 0
    add ebp, 8
    NEXT

; ============================================================================
; Defining Words
; ============================================================================

; VARIABLE - Create a variable
; Usage: VARIABLE name
DEFWORD "VARIABLE", VARIABLE, 0
    dd CREATE                  ; Create header
    dd LIT, 0                  ; Initial value
    dd COMMA                   ; Compile it
    dd EXIT

; CONSTANT - Create a constant
; Usage: value CONSTANT name
DEFCODE "CONSTANT", CONSTANT, 0
    call word_
    call create_
    ; Compile DOCON
    mov eax, [VAR_HERE]
    mov dword [eax], code_DOCON
    add dword [VAR_HERE], 4
    ; Compile the value
    pop ebx
    mov eax, [VAR_HERE]
    mov [eax], ebx
    add dword [VAR_HERE], 4
    NEXT

; Runtime for CONSTANT
DEFCODE "DOCON", DOCON, 0
    ; EAX still holds the XT (code field address) from NEXT/INTERPRET.
    ; The value is at [XT + 4] (right after the code field).
    push dword [eax + 4]
    NEXT

; DOCREATE - Runtime for CREATE'd words (variables, etc.)
; Pushes the parameter field address (CFA + 4) onto the data stack.
DEFCODE "DOCREATE", DOCREATE, 0
    lea eax, [eax + 4]
    push eax
    NEXT

; HIDDEN - Toggle hidden flag on a word
DEFCODE "HIDDEN", HIDDEN, 0
    pop eax                    ; xt of word
    xor byte [eax + 4], F_HIDDEN
    NEXT

; HIDE - Hide the word being defined
DEFWORD "HIDE", HIDE, 0
    dd LATEST, FETCH, HIDDEN, EXIT

; RECURSE - Compile a recursive call
DEFCODE "RECURSE", RECURSE, F_IMMEDIATE
    mov eax, [VAR_LATEST]
    ; Skip past link and name to get CFA
    movzx ebx, byte [eax + 4]  ; flags+len
    and ebx, F_LENMASK         ; just length
    lea eax, [eax + 5 + ebx]   ; skip link(4) + flags(1) + name(len)
    ; Align to 4 bytes
    add eax, 3
    and eax, ~3
    ; Compile the xt
    mov ebx, [VAR_HERE]
    mov [ebx], eax
    add dword [VAR_HERE], 4
    NEXT

; ============================================================================
; Utility Words
; ============================================================================

; WORDS - List all words in dictionary
DEFCODE "WORDS", WORDS, 0
    PUSHRSP esi                ; Save Forth IP
    mov eax, [VAR_LATEST]
.loop:
    test eax, eax
    jz .done
    push eax                   ; Save link on data stack (temp)
    ; Print word name
    movzx ecx, byte [eax + 4]  ; flags+len
    test cl, F_HIDDEN
    jnz .skip                  ; Don't print hidden words
    and ecx, F_LENMASK         ; just length
    lea esi, [eax + 5]         ; name starts after link(4) + flags(1)
.print:
    test ecx, ecx
    jz .space
    lodsb
    call print_char
    dec ecx
    jmp .print
.space:
    mov al, ' '
    call print_char
.skip:
    pop eax
    mov eax, [eax]             ; Follow link
    jmp .loop
.done:
    mov al, 13
    call print_char
    mov al, 10
    call print_char
    POPRSP esi                 ; Restore Forth IP
    NEXT

; SEE - Decompile a word
DEFCODE "SEE", SEE, 0
    PUSHRSP esi                ; Save Forth IP
    call word_
    call find_              ; EAX = XT (points to code field), ECX = flags+len
    test eax, eax
    jz .notfound
    push eax
    ; Print word name
    mov esi, see_msg
    call print_string
    ; Print xt address
    pop eax
    push eax
    call print_hex
    mov al, ':'
    call print_char
    mov al, ' '
    call print_char
    ; Check if it's a DOCOL word
    ; EAX = XT = pointer to code field (first cell of the word body)
    pop eax
    mov ebx, [eax]             ; First cell = code pointer (DOCOL or code_xxx)
    cmp ebx, DOCOL
    jne .primitive
    ; It's a colon definition - decompile it
    add eax, 4                 ; Move past DOCOL
.decompile:
    mov ebx, [eax]
    cmp ebx, EXIT
    je .doneword
    ; Try to find word name for this xt
    push eax
    push ebx
    call print_hex_short
    mov al, ' '
    call print_char
    pop ebx
    pop eax
    ; Check for LIT
    cmp ebx, LIT
    jne .notlit
    add eax, 4
    mov ecx, [eax]
    push eax
    mov eax, ecx
    call print_number
    mov al, ' '
    call print_char
    pop eax
.notlit:
    add eax, 4
    jmp .decompile
.primitive:
    mov esi, primitive_msg
    call print_string
    jmp .done2
.doneword:
    mov al, ';'
    call print_char
.done2:
    mov al, 13
    call print_char
    mov al, 10
    call print_char
    POPRSP esi                 ; Restore Forth IP
    NEXT
.notfound:
    mov esi, msg_undefined
    call print_string
    POPRSP esi                 ; Restore Forth IP
    NEXT

; HERE - ( -- addr ) Return dictionary pointer
DEFCODE "HERE@", HEREADDR, 0
    push dword [VAR_HERE]
    NEXT

; LATEST@ - ( -- addr ) Return latest word
DEFCODE "LATEST@", LATESTADDR, 0
    push dword [VAR_LATEST]
    NEXT

; >BODY - ( xt -- addr ) Get body of a CREATE'd word
DEFCODE ">BODY", TOBODY, 0
    pop eax
    add eax, 4                 ; Skip past code field
    push eax
    NEXT

; DEPTH - ( -- n ) Stack depth
DEFCODE "DEPTH", DEPTH, 0
    mov eax, DATA_STACK_TOP
    sub eax, esp
    shr eax, 2                 ; Divide by 4 (cell size)
    push eax
    NEXT

; SP@ - ( -- addr ) Get current data stack pointer (diagnostic)
DEFCODE "SP@", SPFETCH, 0
    push esp
    NEXT

; SP! - ( addr -- ) Set data stack pointer (dangerous! diagnostic only)
DEFCODE "SP!", SPSTORE, 0
    pop esp
    NEXT

; CHAR - Get character code
; Usage: CHAR x ( -- c )
DEFCODE "CHAR", CHAR, 0
    call word_
    movzx eax, byte [word_buffer]
    push eax
    NEXT

; [CHAR] - Compile character literal
DEFCODE "[CHAR]", BRACKETCHAR, F_IMMEDIATE
    call word_
    movzx eax, byte [word_buffer]
    mov ebx, [VAR_HERE]
    mov dword [ebx], LIT
    mov [ebx + 4], eax
    add dword [VAR_HERE], 8
    NEXT

; ============================================================================
; String Words
; ============================================================================

; S" - Compile or interpret a string
; Reads string from TIB (works in both interactive and block mode).
; In interactive mode, read_line already filled TIB with the full line.
; In block mode, TIB points to the block buffer. Either way, we
; advance TOIN past the closing '"' to consume the string from input.
DEFCODE 'S"', SQUOTE, F_IMMEDIATE
    ; Check state
    mov eax, [VAR_STATE]
    test eax, eax
    jz .interpret
    ; Compile mode: layout is [DOSQUOTE XT][length][string bytes...][align]
    mov eax, [VAR_HERE]
    mov dword [eax], DOSQUOTE       ; Compile (S") XT
    add dword [VAR_HERE], 4
    ; Reserve space for length (patch after we know it)
    mov ebx, [VAR_HERE]             ; Save length cell address
    add dword [VAR_HERE], 4
    ; Copy string characters from TIB starting at TOIN
    mov edi, [VAR_HERE]
    xor ecx, ecx
    ; Skip leading space after S" (word_ leaves TOIN at the delimiter)
    mov edx, [VAR_TOIN]
    mov eax, [VAR_TIB]
    cmp byte [eax + edx], ' '
    jne .copy
    inc edx
.copy:
    ; Read next character from TIB
    movzx eax, byte [eax + edx]
    test eax, eax                  ; NUL = end of interactive line
    jz .endcopy
    inc edx
    cmp al, '"'
    je .endcopy
    stosb
    inc ecx
    mov eax, [VAR_TIB]
    jmp .copy
.endcopy:
    mov [VAR_TOIN], edx
    ; Patch the length
    mov [ebx], ecx
    ; Align HERE past string data
    mov eax, edi
    add eax, 3
    and eax, ~3
    mov [VAR_HERE], eax
    NEXT
.interpret:
    ; Interpret mode: read string to temp buffer from TIB
    mov edi, string_buffer
    xor ecx, ecx
    ; Skip leading space after S"
    mov edx, [VAR_TOIN]
    mov eax, [VAR_TIB]
    cmp byte [eax + edx], ' '
    jne .interp_copy
    inc edx
.interp_copy:
    ; Read next character from TIB
    movzx eax, byte [eax + edx]
    test eax, eax                  ; NUL = end of interactive line
    jz .interp_done
    inc edx
    cmp al, '"'
    je .interp_done
    stosb
    inc ecx
    mov eax, [VAR_TIB]
    ; In block mode, also check for end of block
    cmp dword [VAR_BLK], 0
    je .interp_copy
    cmp edx, BLOCK_SIZE
    jl .interp_copy
.interp_done:
    mov [VAR_TOIN], edx
    push dword string_buffer
    push ecx
    NEXT

; Runtime (S")
DEFCODE '(S")', DOSQUOTE, 0
    lodsd                      ; Get length
    push esi                   ; String address
    push eax                   ; Length
    add esi, eax               ; Skip past string
    add esi, 3
    and esi, ~3                ; Align
    NEXT

; ." - Print string (always compile mode, since it's IMMEDIATE)
; Reads string from TIB, same as S" above.
DEFCODE '."', DOTQUOTE, F_IMMEDIATE
    ; Layout: [DOSQUOTE XT][length][string bytes...][align][TYPE XT]
    mov eax, [VAR_HERE]
    mov dword [eax], DOSQUOTE       ; Compile (S") XT
    add dword [VAR_HERE], 4
    ; Reserve space for length
    mov ebx, [VAR_HERE]             ; Save length cell address
    add dword [VAR_HERE], 4
    ; Copy string characters from TIB
    mov edi, [VAR_HERE]
    xor ecx, ecx
    ; Skip leading space after ."
    mov edx, [VAR_TOIN]
    mov eax, [VAR_TIB]
    cmp byte [eax + edx], ' '
    jne .copy
    inc edx
.copy:
    ; Read next character from TIB
    movzx eax, byte [eax + edx]
    test eax, eax                  ; NUL = end of interactive line
    jz .done
    inc edx
    cmp al, '"'
    je .done
    stosb
    inc ecx
    mov eax, [VAR_TIB]
    jmp .copy
.done:
    mov [VAR_TOIN], edx
    ; Patch length
    mov [ebx], ecx
    ; Align HERE past string data
    mov eax, edi
    add eax, 3
    and eax, ~3
    mov [VAR_HERE], eax
    ; Compile TYPE
    mov eax, [VAR_HERE]
    mov dword [eax], TYPE
    add dword [VAR_HERE], 4
    NEXT

; ============================================================================
; Comments
; ============================================================================

; ( - Start comment until )
DEFCODE "(", PAREN, F_IMMEDIATE
    cmp dword [VAR_BLK], 0
    je .interactive_paren

    ; Block mode: scan block buffer for ')'
    mov eax, [VAR_TIB]
    mov ecx, [VAR_TOIN]
.block_scan:
    cmp ecx, BLOCK_SIZE
    jge .block_done
    movzx edx, byte [eax + ecx]
    inc ecx
    cmp edx, ')'
    jne .block_scan
.block_done:
    mov [VAR_TOIN], ecx
    NEXT

.interactive_paren:
    ; Interactive mode: read from serial/keyboard until ')'
.skip:
    call read_key
    cmp al, ')'
    jne .skip
    NEXT

; \ - Line comment (skip to end of current line)
; In block mode: advance >IN to next 64-char line boundary
; In interactive mode: advance >IN past end of TIB line
DEFCODE '\', BACKSLASH, F_IMMEDIATE
    cmp dword [VAR_BLK], 0
    je .interactive_skip

    ; Block mode: advance TOIN to next multiple of 64 (line boundary)
    mov eax, [VAR_TOIN]
    add eax, 63
    and eax, ~63               ; Round up to next 64-byte boundary
    cmp eax, BLOCK_SIZE
    jle .set_toin
    mov eax, BLOCK_SIZE        ; Cap at block size
.set_toin:
    mov [VAR_TOIN], eax
    NEXT

.interactive_skip:
    ; Interactive mode: skip remaining chars in TIB line
    mov eax, [VAR_TIB]
    mov ecx, [VAR_TOIN]
.scan:
    movzx edx, byte [eax + ecx]
    test edx, edx             ; NUL?
    jz .end_line
    cmp edx, 13               ; CR?
    je .end_line
    cmp edx, 10               ; LF?
    je .end_line
    inc ecx
    jmp .scan
.end_line:
    mov [VAR_TOIN], ecx
    NEXT

; ============================================================================
; Memory and Arithmetic Extensions
; ============================================================================

; CELLS - ( n -- n*cell )
DEFCODE "CELLS", CELLS, 0
    pop eax
    shl eax, 2                 ; Multiply by 4
    push eax
    NEXT

; CELL+ - ( addr -- addr+cell )
DEFCODE "CELL+", CELLPLUS, 0
    pop eax
    add eax, 4
    push eax
    NEXT

; CHARS - ( n -- n )  (In this implementation, chars = bytes)
DEFCODE "CHARS", CHARS, 0
    NEXT

; CHAR+ - ( addr -- addr+1 )
DEFCODE "CHAR+", CHARPLUS, 0
    pop eax
    inc eax
    push eax
    NEXT

; ALIGNED - ( addr -- aligned-addr )
DEFCODE "ALIGNED", ALIGNED, 0
    pop eax
    add eax, 3
    and eax, ~3
    push eax
    NEXT

; ALIGN - Align HERE
DEFCODE "ALIGN", FALIGN, 0
    mov eax, [VAR_HERE]
    add eax, 3
    and eax, ~3
    mov [VAR_HERE], eax
    NEXT

; MOVE - ( src dst u -- ) Copy u bytes
DEFCODE "MOVE", MOVE, 0
    PUSHRSP esi                ; Save Forth IP
    pop ecx                    ; count
    pop edi                    ; dst
    pop esi                    ; src
    rep movsb
    POPRSP esi                 ; Restore Forth IP
    NEXT

; ERASE - ( addr u -- ) Fill with zeros
DEFCODE "ERASE", ERASE, 0
    pop ecx                    ; count
    pop edi                    ; addr
    xor al, al
    rep stosb
    NEXT

; BLANK - ( addr u -- ) Fill with spaces
DEFCODE "BLANK", BLANK, 0
    pop ecx
    pop edi
    mov al, ' '
    rep stosb
    NEXT

; ============================================================================
; Numeric Output Extensions
; ============================================================================

; HEX - Set base to 16
DEFCODE "HEX", HEX, 0
    mov dword [VAR_BASE], 16
    NEXT

; DECIMAL - Set base to 10
DEFCODE "DECIMAL", DECIMAL, 0
    mov dword [VAR_BASE], 10
    NEXT

; U. - Print unsigned
DEFCODE "U.", UDOT, 0
    pop eax
    call print_unsigned
    mov al, ' '
    call print_char
    NEXT

; .R - Print right-justified in field
DEFCODE ".R", DOTR, 0
    pop ebx                    ; width
    pop eax                    ; number
    ; TODO: Implement proper right-justified printing
    call print_number
    NEXT

; --- Special ---

DEFCODE "BYE", BYE, 0
    ; Halt the system
    cli
    hlt
    jmp code_BYE

; ============================================================================
; Block Storage Words
; ============================================================================

; BLK - ( -- addr ) Address of variable holding current block# (0=keyboard)
DEFVAR "BLK", BLK, VAR_BLK

; SCR - ( -- addr ) Address of variable holding last LISTed block#
DEFVAR "SCR", SCR, VAR_SCR

; BLOCK - ( n -- addr ) Get buffer address for block n, reading from disk if needed
DEFCODE "BLOCK", BLOCK, 0
    pop eax                     ; block#
    call blk_find_buffer        ; EDI=buffer addr, EBX=header addr, CF=needs load
    jnc .cached

    ; Need to read from disk: 2 sectors per block
    push edi                    ; Save buffer addr
    push ebx                    ; Save header addr
    mov eax, [ebx]              ; block#
    shl eax, 1                  ; LBA = block# * 2
    mov ebx, eax                ; EBX = LBA for ata_read_sector
    ; Read first sector
    call ata_read_sector
    jc .read_error
    ; Read second sector (EDI already advanced by rep insw)
    inc ebx
    call ata_read_sector
    jc .read_error

    pop ebx                     ; Restore header addr
    ; Mark valid
    or dword [ebx + 4], BLK_BUF_FLAG_VALID
    pop edi                     ; Restore buffer addr (original start)
    push edi                    ; Push result
    NEXT

.read_error:
    pop ebx
    pop edi
    ; Return buffer addr anyway (may contain garbage)
    push edi
    NEXT

.cached:
    push edi
    NEXT

; BUFFER - ( n -- addr ) Get buffer for block n without reading from disk
DEFCODE "BUFFER", BUFFER, 0
    pop eax                     ; block#
    call blk_find_buffer        ; EDI=buffer addr, EBX=header addr
    ; Mark valid without reading (caller will write the data)
    or dword [ebx + 4], BLK_BUF_FLAG_VALID
    push edi
    NEXT

; UPDATE - ( -- ) Mark current buffer as dirty (modified)
DEFCODE "UPDATE", UPDATE, 0
    mov eax, [BLK_BUF_CUR]     ; Current buffer index
    imul eax, BLK_HEADER_SIZE
    or dword [BLK_BUF_HEADERS + eax + 4], BLK_BUF_FLAG_DIRTY
    NEXT

; SAVE-BUFFERS - ( -- ) Write all dirty buffers to disk
DEFCODE "SAVE-BUFFERS", SAVEBUFFERS, 0
    PUSHRSP esi                 ; Save Forth IP (blk_flush_one uses ESI)
%ifdef DEBUG_FLUSH
    push eax
    mov al, '['
    call serial_putchar
    mov al, 13
    call serial_putchar
    mov al, 10
    call serial_putchar
    pop eax
%endif
    mov ebx, BLK_BUF_HEADERS
    mov ecx, BLK_NUM_BUFFERS
.flush_loop:
    push ecx
    push ebx
    call blk_flush_one
    pop ebx
    pop ecx
    add ebx, BLK_HEADER_SIZE
    dec ecx
    jnz .flush_loop
%ifdef DEBUG_FLUSH
    push eax
    mov al, ']'
    call serial_putchar
    mov al, 13
    call serial_putchar
    mov al, 10
    call serial_putchar
    pop eax
%endif
    POPRSP esi
    NEXT

; EMPTY-BUFFERS - ( -- ) Discard all buffers (clear headers, no write)
DEFCODE "EMPTY-BUFFERS", EMPTYBUFFERS, 0
    mov edi, BLK_BUF_HEADERS
    mov ecx, BLK_NUM_BUFFERS
.clear_loop:
    mov dword [edi], 0xFFFFFFFF     ; block# = invalid
    mov dword [edi + 4], 0          ; flags = 0
    mov dword [edi + 8], 0          ; age = 0
    add edi, BLK_HEADER_SIZE
    dec ecx
    jnz .clear_loop
    NEXT

; FLUSH - ( -- ) Save all dirty buffers then discard them
DEFWORD "FLUSH", FLUSH, 0
    dd SAVEBUFFERS
    dd EMPTYBUFFERS
    dd EXIT

; ============================================================================
; Block Source Loading Words
; ============================================================================

; LIST - ( n -- ) Display block n as 16 lines x 64 characters
DEFCODE "LIST", LIST, 0
    pop eax
    mov [VAR_SCR], eax          ; Remember for SCR

    ; Get block buffer (reads from disk if needed)
    call blk_find_buffer
    jnc .have_data
    ; Need to read
    push edi
    push ebx
    mov eax, [ebx]
    shl eax, 1
    mov ebx, eax
    call ata_read_sector
    inc ebx
    call ata_read_sector
    pop ebx
    or dword [ebx + 4], BLK_BUF_FLAG_VALID
    pop edi

.have_data:
    PUSHRSP esi                 ; Save Forth IP
    mov esi, edi                ; ESI = buffer data for printing

    ; Print 16 lines
    xor ecx, ecx               ; Line counter
.line_loop:
    cmp ecx, 16
    jge .done

    ; Print line number (right-justified in 2 digits)
    push ecx
    push esi
    mov eax, ecx
    call print_number
    mov al, ':'
    call print_char
    mov al, ' '
    call print_char
    pop esi
    pop ecx

    ; Print 64 characters of this line
    push ecx
    mov edx, 64
.char_loop:
    lodsb
    ; Replace control chars with space for display
    cmp al, 32
    jge .printable
    mov al, ' '
.printable:
    call print_char
    dec edx
    jnz .char_loop
    pop ecx

    ; Newline
    mov al, 13
    call print_char
    mov al, 10
    call print_char

    inc ecx
    jmp .line_loop

.done:
    POPRSP esi
    NEXT

; LOAD - ( n -- ) Interpret Forth source from block n
; Saves current input state on return stack, redirects interpreter to block buffer
DEFCODE "LOAD", LOAD, 0
    pop eax                     ; block#

    ; Get block buffer
    call blk_find_buffer
    jnc .have_data
    ; Need to read from disk
    push eax
    push edi
    push ebx
    mov eax, [ebx]
    shl eax, 1
    mov ebx, eax
    call ata_read_sector
    inc ebx
    call ata_read_sector
    pop ebx
    or dword [ebx + 4], BLK_BUF_FLAG_VALID
    pop edi
    pop eax

.have_data:
    ; Normalize block content: place NUL at end for word_ termination
    ; (The NUL guard at BLK_BUF_GUARD handles this for the last buffer,
    ;  but we also need it within the 1024-byte region)
    push eax
    mov byte [edi + BLOCK_SIZE], 0  ; NUL terminator after block data

    ; Save current input state on return stack
    PUSHRSP esi                 ; Save Forth IP
    mov ecx, [VAR_BLK]
    PUSHRSP ecx                 ; Save old BLK
    mov ecx, [VAR_TOIN]
    PUSHRSP ecx                 ; Save old >IN
    mov ecx, [VAR_TIB]
    PUSHRSP ecx                 ; Save old TIB

    ; Redirect input to block buffer
    pop eax                     ; Restore block#
    mov [VAR_BLK], eax
    mov [VAR_TIB], edi          ; TIB now points to block buffer
    mov dword [VAR_TOIN], 0     ; Start parsing from beginning
    mov dword [VAR_BLOCK_LOADING], 1  ; Signal: don't treat first TOIN=0 as exhaustion

    ; Jump into interpreter loop — it will parse from block buffer
    mov esi, cold_start
    NEXT

; --> - ( -- ) Chain-load next block (immediate)
DEFCODE "-->", CHAIN, F_IMMEDIATE
    mov eax, [VAR_BLK]
    test eax, eax
    jz .not_loading             ; Not in a LOAD, ignore
    inc eax
    mov [VAR_BLK], eax

    ; Get next block buffer
    call blk_find_buffer
    jnc .have_next
    push edi
    push ebx
    mov eax, [ebx]
    shl eax, 1
    mov ebx, eax
    call ata_read_sector
    inc ebx
    call ata_read_sector
    pop ebx
    or dword [ebx + 4], BLK_BUF_FLAG_VALID
    pop edi

.have_next:
    mov byte [edi + BLOCK_SIZE], 0
    mov [VAR_TIB], edi
    mov dword [VAR_TOIN], 0
.not_loading:
    NEXT

; THRU - ( n1 n2 -- ) Load blocks n1 through n2
DEFWORD "THRU", THRU, 0
    dd INCR                     ; ( first last+1 ) — include last block
    dd SWAP                     ; ( last+1 first )
    dd DODO                     ; DO
    dd I                        ;   I
    dd LOAD                     ;   LOAD
    dd DOLOOP                   ;   LOOP
    dd -16                      ;   (backward offset: I is 4 cells before here)
    dd EXIT

; ============================================================================
; Vocabulary / Search Order Words
; ============================================================================

; DOVOC runtime — executed when a vocabulary word runs
; Replaces top of search order with this vocabulary's LATEST cell address
DOVOC:
    lea eax, [eax + 4]         ; Address of vocab's LATEST cell (param field IS the cell)
    mov [VAR_SEARCH_ORDER], eax ; Replace top of search order
    NEXT

; VOCABULARY - ( "name" -- ) Create a new vocabulary
; Creates a word with DOVOC runtime. Parameter field = address of a new LATEST cell.
DEFCODE "VOCABULARY", VOCABULARY, 0
    call word_                  ; Parse vocabulary name
    call create_                ; Create dictionary header

    ; Write DOVOC as code field
    mov eax, [VAR_HERE]
    mov dword [eax], DOVOC
    add dword [VAR_HERE], 4

    ; Allocate and initialize a LATEST cell for this vocabulary (starts empty = 0)
    mov eax, [VAR_HERE]
    mov dword [eax], 0          ; This vocab's LATEST = 0 (empty)
    add dword [VAR_HERE], 4
    NEXT

; DEFINITIONS - ( -- ) Set compilation vocabulary to top of search order
DEFCODE "DEFINITIONS", DEFINITIONS, 0
    mov eax, [VAR_SEARCH_ORDER] ; Top of search order = addr of a LATEST cell
    mov [VAR_CURRENT], eax
    NEXT

; ALSO - ( -- ) Duplicate top of search order (push a copy)
DEFCODE "ALSO", ALSO, 0
    mov eax, [VAR_SEARCH_DEPTH]
    cmp eax, 8
    jge .full                   ; Max 8 entries
    ; Shift all entries down by one cell
    lea ebx, [VAR_SEARCH_ORDER + eax * 4]  ; End of current entries
    mov ecx, eax               ; Number of entries to shift
.shift:
    test ecx, ecx
    jz .done_shift
    mov edx, [ebx - 4]         ; Source
    mov [ebx], edx              ; Dest (one cell higher)
    sub ebx, 4
    dec ecx
    jmp .shift
.done_shift:
    ; Top entry is now duplicated (ORDER[0] still has original)
    inc dword [VAR_SEARCH_DEPTH]
.full:
    NEXT

; PREVIOUS - ( -- ) Remove top entry from search order
DEFCODE "PREVIOUS", PREVIOUS, 0
    mov eax, [VAR_SEARCH_DEPTH]
    cmp eax, 1
    jle .minimum                ; Must keep at least 1
    ; Shift all entries up by one cell
    dec eax
    mov [VAR_SEARCH_DEPTH], eax
    xor ecx, ecx
.shift:
    cmp ecx, eax
    jge .done
    mov edx, [VAR_SEARCH_ORDER + ecx * 4 + 4]  ; Next entry
    mov [VAR_SEARCH_ORDER + ecx * 4], edx        ; Move up
    inc ecx
    jmp .shift
.done:
.minimum:
    NEXT

; ONLY - ( -- ) Reset search order to just FORTH
DEFCODE "ONLY", ONLY, 0
    mov dword [VAR_SEARCH_DEPTH], 1
    mov dword [VAR_SEARCH_ORDER], VAR_FORTH_LATEST
    mov dword [VAR_CURRENT], VAR_FORTH_LATEST
    NEXT

; FORTH - ( -- ) Replace top of search order with FORTH vocabulary
DEFCODE "FORTH", FORTH, 0
    mov dword [VAR_SEARCH_ORDER], VAR_FORTH_LATEST
    NEXT

; ORDER - ( -- ) Display the current search order
DEFCODE "ORDER", ORDER, 0
    PUSHRSP esi
    ; Print "Search: "
    mov esi, msg_search
    call print_string

    mov ecx, [VAR_SEARCH_DEPTH]
    xor edx, edx
.print_loop:
    cmp edx, ecx
    jge .print_current
    push ecx
    push edx
    ; Print the address of each vocab LATEST cell
    mov eax, [VAR_SEARCH_ORDER + edx * 4]
    call print_hex
    mov al, ' '
    call print_char
    pop edx
    pop ecx
    inc edx
    jmp .print_loop

.print_current:
    ; Print "Compile: "
    mov esi, msg_compile
    call print_string
    mov eax, [VAR_CURRENT]
    call print_hex
    mov al, 13
    call print_char
    mov al, 10
    call print_char

    POPRSP esi
    NEXT

; USING - ( "name" -- ) Parse vocabulary name, add to search order
; Equivalent to: ALSO <vocab-name>
DEFCODE "USING", USING, 0
    call word_                  ; Parse vocabulary name
    call find_                  ; Find the vocabulary word
    test eax, eax
    jz .not_found

    ; Execute ALSO first (duplicate top of search order)
    push eax                    ; Save vocab XT
    mov eax, [VAR_SEARCH_DEPTH]
    cmp eax, 8
    jge .full
    lea ebx, [VAR_SEARCH_ORDER + eax * 4]
    mov ecx, eax
.shift:
    test ecx, ecx
    jz .done_shift
    mov edx, [ebx - 4]
    mov [ebx], edx
    sub ebx, 4
    dec ecx
    jmp .shift
.done_shift:
    inc dword [VAR_SEARCH_DEPTH]
.full:
    ; Now execute the vocabulary word (replaces top of search order)
    pop eax                     ; XT of vocabulary word
    jmp [eax]                   ; Execute it (DOVOC sets ORDER[0], then NEXT)

.not_found:
    push esi
    mov esi, word_buffer
    call print_string
    mov esi, msg_undefined
    call print_string
    pop esi
    NEXT

; ============================================================================
; Interrupt Infrastructure - Dictionary Words
; ============================================================================

; TICK-COUNT - ( -- addr ) Address of ISR tick counter variable
DEFVAR "TICK-COUNT", TICK_COUNT, isr_tick_count

; IDT-BASE - ( -- addr ) Base address of the IDT
DEFCONST "IDT-BASE", IDT_BASE_CONST, IDT_BASE

; IRQ-UNMASK - ( irq# -- ) Unmask a specific IRQ in the PIC
DEFCODE "IRQ-UNMASK", IRQ_UNMASK, 0
    pop eax                     ; irq#
    cmp eax, 8
    jae .slave
    ; Master PIC (IRQ 0-7): read mask, clear bit, write back
    mov ecx, eax
    mov dx, PIC1_DATA
    in al, dx
    mov ebx, 1
    shl ebx, cl
    not ebx
    and eax, ebx
    out dx, al
    NEXT
.slave:
    ; Slave PIC (IRQ 8-15): unmask on slave AND unmask IRQ2 on master (cascade)
    sub eax, 8
    mov ecx, eax
    mov dx, PIC2_DATA
    in al, dx
    mov ebx, 1
    shl ebx, cl
    not ebx
    and eax, ebx
    out dx, al
    ; Also unmask IRQ2 (cascade) on master
    mov dx, PIC1_DATA
    in al, dx
    and al, ~(1 << 2)          ; Clear bit 2 (IRQ2 = cascade)
    out dx, al
    NEXT

; KB-RING-BUF - ( -- addr ) Address of keyboard scancode ring buffer
DEFCONST "KB-RING-BUF", KB_RING_BUF_CONST, kb_ring_buf

; KB-RING-TAIL - ( -- addr ) Address of ring buffer tail (read position)
DEFVAR "KB-RING-TAIL", KB_RING_TAIL, kb_ring_tail

; KB-RING-COUNT - ( -- addr ) Address of ring buffer count
DEFVAR "KB-RING-COUNT", KB_RING_COUNT, kb_ring_count

; MOUSE-PKT-BUF - ( -- addr ) Address of 3-byte mouse packet buffer
DEFCONST "MOUSE-PKT-BUF", MOUSE_PKT_BUF_CONST, mouse_pkt_buf

; MOUSE-PKT-READY - ( -- addr ) Address of mouse packet ready flag
DEFVAR "MOUSE-PKT-READY", MOUSE_PKT_READY, mouse_pkt_ready

; MOUSE-X-VAR - ( -- addr ) Address of mouse X position variable
DEFVAR "MOUSE-X-VAR", MOUSE_X_VAR, mouse_x

; MOUSE-Y-VAR - ( -- addr ) Address of mouse Y position variable
DEFVAR "MOUSE-Y-VAR", MOUSE_Y_VAR, mouse_y

; MOUSE-BTN-VAR - ( -- addr ) Address of mouse button state variable
DEFVAR "MOUSE-BTN-VAR", MOUSE_BTN_VAR, mouse_btn

; MORE-ON - ( -- ) Enable line-count pagination (pause every 23 lines)
DEFCODE "MORE-ON", MORE_ON, 0
    mov byte [more_enabled], 1
    mov dword [more_lines], 0
    NEXT

; MORE-OFF - ( -- ) Disable pagination
DEFCODE "MORE-OFF", MORE_OFF, 0
    mov byte [more_enabled], 0
    mov dword [more_lines], 0
    NEXT

; MORE-LINES - ( -- addr ) Variable: current line count
DEFVAR "MORE-LINES", MORE_LINES_VAR, more_lines

; NET-CON-ON - ( -- ) Enable net console output mirroring
DEFCODE "NET-CON-ON", NET_CON_ON, 0
    mov byte [net_console_enabled], 1
    NEXT

; NET-CON-OFF - ( -- ) Disable net console, reset buffer
DEFCODE "NET-CON-OFF", NET_CON_OFF, 0
    mov byte [net_console_enabled], 0
    mov dword [net_buf_pos], 0
    NEXT

; NET-FLUSH - ( -- ) Flush any partial net console buffer as UDP packet
DEFCODE "NET-FLUSH", NET_FLUSH, 0
    cmp byte [net_console_enabled], 0
    je .nf_skip
    call net_flush
.nf_skip:
    NEXT

; NET-HDR - ( -- addr ) Address of 42-byte frame header template
DEFVAR "NET-HDR", NET_HDR_VAR, net_frame_hdr

; NET-RTL-BASE - ( -- addr ) Kernel copy of RTL-BASE for net_flush
DEFVAR "NET-RTL-BASE", NET_RTL_BASE_VAR, net_rtl_base

; NET-TX-DESC - ( -- addr ) Kernel copy of TX descriptor address
DEFVAR "NET-TX-DESC", NET_TX_DESC_VAR, net_tx_desc

; NET-TX-BUF - ( -- addr ) Kernel copy of TX buffer address
DEFVAR "NET-TX-BUF", NET_TX_BUF_VAR, net_tx_buf

; ECHOPORT kernel trace variables
DEFCODE "TRACE-ENABLED", TRACE_ENABLED_W, 0  ; ( -- addr )
    push trace_enabled
    NEXT

DEFCODE "TRACE-HEAD", TRACE_HEAD_W, 0       ; ( -- addr )
    push trace_head
    NEXT

DEFCODE "TRACE-COUNT", TRACE_COUNT_W, 0     ; ( -- addr )
    push trace_count
    NEXT

DEFCODE "TRACE-BUF", TRACE_BUF_W, 0         ; ( -- addr )
    push trace_buf
    NEXT

DEFCODE "TRACE-ENTRY-SZ", TRACE_ENTRY_SZ_W, 0  ; ( -- n )
    push TRACE_ENTRY_SZ
    NEXT

DEFCODE "TRACE-BUF-SIZE", TRACE_BUF_SIZE_W, 0  ; ( -- n )
    push TRACE_BUF_SIZE
    NEXT

; ============================================================================
; Metacompiler Support - Internal Routine Addresses
; ============================================================================
; Expose assembly helper addresses so the metacompiler can
; emit CALL instructions to them via CALL-ABS,.

DEFCONST "ADDR-READ-KEY", ADDR_READ_KEY, read_key
DEFCONST "ADDR-PRINT-CHAR", ADDR_PRINT_CHAR, print_char
DEFCONST "ADDR-PRINT-NUM", ADDR_PRINT_NUM, print_number
DEFCONST "ADDR-PRINT-STR", ADDR_PRINT_STR, print_string
DEFCONST "ADDR-WORD", ADDR_WORD_FN, word_
DEFCONST "ADDR-FIND", ADDR_FIND_FN, find_
DEFCONST "ADDR-NUMBER", ADDR_NUMBER_FN, number_
DEFCONST "ADDR-CREATE", ADDR_CREATE_FN, create_
DEFCONST "ADDR-COMMA", ADDR_COMMA_FN, comma_
DEFCONST "ADDR-READ-LINE", ADDR_READ_LINE, read_line

; ============================================================================
; Low-Level Support Routines
; ============================================================================

; ----------------------------------------------------------------------------
; init_serial - Initialize COM1 serial port (115200 baud, 8N1)
; ----------------------------------------------------------------------------
init_serial:
    push eax
    push edx
    ; Probe COM1: write scratch register, read back. If mismatch, no UART.
    mov dx, COM1_PORT + 7   ; Scratch register
    mov al, 0xA5
    out dx, al
    in al, dx
    cmp al, 0xA5
    je .com1_found
    mov byte [serial_present], 0
    pop edx
    pop eax
    ret
.com1_found:
    mov byte [serial_present], 1
    mov dx, COM1_PORT + 1
    xor al, al
    out dx, al              ; Disable interrupts
    mov dx, COM1_PORT + 3
    mov al, 0x80
    out dx, al              ; Enable DLAB (set baud rate divisor)
    mov dx, COM1_PORT + 0
    mov al, 1               ; Divisor 1 = 115200 baud
    out dx, al
    mov dx, COM1_PORT + 1
    xor al, al
    out dx, al              ; High byte of divisor
    mov dx, COM1_PORT + 3
    mov al, 0x03
    out dx, al              ; 8 bits, no parity, 1 stop bit
    mov dx, COM1_PORT + 2
    mov al, 0xC7
    out dx, al              ; Enable FIFO, clear, 14-byte threshold
    mov dx, COM1_PORT + 4
    mov al, 0x0B
    out dx, al              ; IRQs enabled, RTS/DSR set
    pop edx
    pop eax
    ret

; ----------------------------------------------------------------------------
; kbd_init_8042 - Explicitly initialize the 8042 keyboard controller
; Needed on some hardware where CSM/GRUB transition disables the keyboard
; ----------------------------------------------------------------------------
kbd_init_8042:
    pushad
    cli                     ; Prevent ISR from consuming 8042 responses

    ; Flush any pending data from 8042 output buffer
.flush:
    in al, 0x64
    test al, 1              ; OBF set?
    jz .flushed
    in al, 0x60             ; Read and discard
    jmp .flush
.flushed:

    ; Disable keyboard interface during configuration
    call .wait_input
    mov al, 0xAD             ; Disable keyboard
    out 0x64, al

    ; Read current controller command byte
    call .wait_input
    mov al, 0x20             ; Read command byte
    out 0x64, al
    call .wait_output
    in al, 0x60             ; Get command byte
    mov bl, al              ; Save it

    ; Write new command byte: enable keyboard interrupt, enable keyboard, scancode translation ON
    call .wait_input
    mov al, 0x60             ; Write command byte
    out 0x64, al
    call .wait_input
    mov al, bl
    or al, 0x01             ; Bit 0: enable keyboard interrupt (IRQ1)
    or al, 0x40             ; Bit 6: scancode translation (set 2 → set 1)
    and al, ~0x10           ; Bit 4: clear = keyboard interface enabled
    out 0x60, al

    ; Re-enable keyboard interface
    call .wait_input
    mov al, 0xAE             ; Enable keyboard
    out 0x64, al

    ; Reset keyboard (0xFF) — triggers re-initialization on real hardware
    call .wait_input
    mov al, 0xFF
    out 0x60, al

    ; Wait for ACK (0xFA) for reset
    mov ecx, 0x20000000
.wait_reset_ack:
    in al, 0x64
    test al, 1
    jnz .got_reset_ack
    dec ecx
    jnz .wait_reset_ack
    jmp .send_enable        ; Timeout — try enable scanning anyway
.got_reset_ack:
    in al, 0x60             ; Consume ACK (0xFA)

    ; Wait for self-test result (0xAA) — can take up to 750ms
    mov ecx, 0x40000000
.wait_bat:
    in al, 0x64
    test al, 1
    jnz .got_bat
    dec ecx
    jnz .wait_bat
    jmp .send_enable        ; Timeout — proceed anyway
.got_bat:
    in al, 0x60             ; Consume self-test result (0xAA)

.send_enable:
    ; Send 0xF4 (Enable Scanning) — required after reset
    call .wait_input
    mov al, 0xF4
    out 0x60, al

    ; Wait for ACK
    mov ecx, 0x20000000
.wait_f4_ack:
    in al, 0x64
    test al, 1
    jnz .got_f4_ack
    dec ecx
    jnz .wait_f4_ack
    jmp .init_done          ; Timeout — proceed
.got_f4_ack:
    in al, 0x60             ; Consume ACK

.init_done:
    sti                     ; Re-enable interrupts after init complete
    popad
    ret

.wait_input:
    ; Wait for 8042 input buffer empty (bit 1 of port 0x64 clear)
    push ecx
    mov ecx, 0x10000
.wi_loop:
    in al, 0x64
    test al, 2
    jz .wi_done
    dec ecx
    jnz .wi_loop
.wi_done:
    pop ecx
    ret

.wait_output:
    ; Wait for 8042 output buffer full (bit 0 of port 0x64 set)
    push ecx
    mov ecx, 0x10000
.wo_loop:
    in al, 0x64
    test al, 1
    jnz .wo_done
    dec ecx
    jnz .wo_loop
.wo_done:
    pop ecx
    ret


; ----------------------------------------------------------------------------
; print_hex_byte - Print AL as 2 hex digits to VGA
; ----------------------------------------------------------------------------
print_hex_byte:
    push eax
    push ecx
    mov cl, al              ; save byte
    shr al, 4              ; high nibble
    call .nibble
    mov al, cl             ; low nibble
    and al, 0x0F
    call .nibble
    pop ecx
    pop eax
    ret
.nibble:
    add al, '0'
    cmp al, '9'
    jle .digit
    add al, 7              ; 'A'-'9'-1
.digit:
    call print_char
    ret

; ----------------------------------------------------------------------------
; print_hex_word - Print AX as 4 hex digits to VGA
; ----------------------------------------------------------------------------
print_hex_word:
    push eax
    push eax
    shr eax, 8
    call print_hex_byte     ; high byte
    pop eax
    call print_hex_byte     ; low byte
    pop eax
    ret


; ----------------------------------------------------------------------------
; init_pic - Remap PIC and mask all IRQs
; IRQ 0-7 -> INT 0x20-0x27, IRQ 8-15 -> INT 0x28-0x2F
; ----------------------------------------------------------------------------
init_pic:
    push eax
    push edx

    ; ICW1: begin initialization sequence (cascade mode, ICW4 needed)
    mov al, 0x11
    out PIC1_CMD, al
    out PIC2_CMD, al

    ; ICW2: vector offsets
    mov al, IRQ_BASE_MASTER     ; Master PIC: IRQ 0 -> INT 0x20
    out PIC1_DATA, al
    mov al, IRQ_BASE_SLAVE      ; Slave PIC: IRQ 8 -> INT 0x28
    out PIC2_DATA, al

    ; ICW3: cascade wiring
    mov al, 0x04                ; Master: slave on IRQ2 (bit 2)
    out PIC1_DATA, al
    mov al, 0x02                ; Slave: cascade identity 2
    out PIC2_DATA, al

    ; ICW4: 8086 mode
    mov al, 0x01
    out PIC1_DATA, al
    out PIC2_DATA, al

    ; Mask all IRQs initially (0xFF = all masked)
    mov al, 0xFF
    out PIC1_DATA, al
    out PIC2_DATA, al

    pop edx
    pop eax
    ret

; ----------------------------------------------------------------------------
; init_idt - Build 256-entry IDT at IDT_BASE, load IDTR
; Default: all entries point to isr_default (just iret)
; Specific: IRQ0 (timer), IRQ1 (keyboard), IRQ12 (mouse)
; ----------------------------------------------------------------------------
init_idt:
    push eax
    push ebx
    push ecx
    push edx
    push edi

    ; First, fill all 256 entries with the default handler
    mov edi, IDT_BASE
    mov ecx, IDT_ENTRIES
    mov ebx, isr_default        ; Default handler address
.fill_idt:
    mov eax, ebx
    mov word [edi], ax          ; Offset low 16 bits
    mov word [edi+2], 0x08      ; Code segment selector (GDT code seg)
    mov byte [edi+4], 0         ; Reserved
    mov byte [edi+5], 0x8E      ; Present, DPL=0, 32-bit interrupt gate
    shr eax, 16
    mov word [edi+6], ax        ; Offset high 16 bits
    add edi, IDT_ENTRY_SIZE
    dec ecx
    jnz .fill_idt

    ; Install specific ISR handlers
    ; IRQ0 (INT 0x20) - Timer
    mov eax, isr_timer
    mov edi, IDT_BASE + (IRQ_BASE_MASTER + 0) * IDT_ENTRY_SIZE
    mov word [edi], ax
    shr eax, 16
    mov word [edi+6], ax

    ; IRQ1 (INT 0x21) - Keyboard
    mov eax, isr_keyboard
    mov edi, IDT_BASE + (IRQ_BASE_MASTER + 1) * IDT_ENTRY_SIZE
    mov word [edi], ax
    shr eax, 16
    mov word [edi+6], ax

    ; IRQ12 (INT 0x2C) - Mouse
    mov eax, isr_mouse
    mov edi, IDT_BASE + (IRQ_BASE_SLAVE + 4) * IDT_ENTRY_SIZE
    mov word [edi], ax
    shr eax, 16
    mov word [edi+6], ax

    ; Load IDTR
    lidt [idt_descriptor]

    ; Initialize ISR data
    mov dword [isr_tick_count], 0
    mov dword [kb_ring_head], 0
    mov dword [kb_ring_tail], 0
    mov dword [kb_ring_count], 0
    mov dword [mouse_pkt_idx], 0
    mov dword [mouse_pkt_ready], 0
    mov dword [mouse_x], 0
    mov dword [mouse_y], 0
    mov dword [mouse_btn], 0

    ; Clear ISR hook table (16 cells)
    mov edi, ISR_HOOK_TABLE
    xor eax, eax
    mov ecx, 16
.clear_hooks:
    mov [edi], eax
    add edi, 4
    dec ecx
    jnz .clear_hooks

    pop edi
    pop edx
    pop ecx
    pop ebx
    pop eax
    ret

; IDT descriptor for LIDT
idt_descriptor:
    dw IDT_ENTRIES * IDT_ENTRY_SIZE - 1   ; Limit (2048 - 1 = 0x7FF)
    dd IDT_BASE                            ; Base address

; ----------------------------------------------------------------------------
; ISR: Default handler (unhandled interrupts)
; ----------------------------------------------------------------------------
isr_default:
    iret

; ----------------------------------------------------------------------------
; ISR: Timer (IRQ0 / INT 0x20)
; Increments tick counter, sends EOI to master PIC
; ----------------------------------------------------------------------------
isr_timer:
    pushad
    inc dword [isr_tick_count]
    mov al, PIC_EOI
    out PIC1_CMD, al            ; EOI to master PIC
    popad
    iret

; ----------------------------------------------------------------------------
; ISR: Keyboard (IRQ1 / INT 0x21)
; Reads scancode from port 0x60 into 16-byte ring buffer
; ----------------------------------------------------------------------------
isr_keyboard:
    pushad
    in al, 0x60                 ; Read scancode from keyboard controller

    ; Check if ring buffer is full
    mov ecx, [kb_ring_count]
    cmp ecx, KB_RING_SIZE
    jge .kb_full                ; Drop scancode if buffer full

    ; Write to ring buffer at head position
    mov edi, [kb_ring_head]
    mov byte [kb_ring_buf + edi], al

    ; Advance head with wrap-around
    inc edi
    cmp edi, KB_RING_SIZE
    jb .kb_no_wrap
    xor edi, edi
.kb_no_wrap:
    mov [kb_ring_head], edi
    inc dword [kb_ring_count]

.kb_full:
    mov al, PIC_EOI
    out PIC1_CMD, al            ; EOI to master PIC
    popad
    iret

; ----------------------------------------------------------------------------
; ISR: Mouse (IRQ12 / INT 0x2C)
; Reads data byte into 3-byte packet buffer. When 3 bytes collected,
; sets mouse_pkt_ready flag.
; IRQ12 is on slave PIC (IRQ 8+4), so EOI goes to BOTH PIC2 and PIC1.
; ----------------------------------------------------------------------------
isr_mouse:
    pushad
    in al, 0x60                 ; Read data byte from PS/2 controller

    ; Store byte in packet buffer at current index
    mov edi, [mouse_pkt_idx]
    mov byte [mouse_pkt_buf + edi], al

    ; Advance packet index
    inc edi
    cmp edi, 3
    jb .mouse_partial

    ; Full 3-byte packet received — decode it
    ; Byte 0: buttons/signs, Byte 1: X movement, Byte 2: Y movement
    movzx eax, byte [mouse_pkt_buf]    ; buttons/flags byte
    mov ebx, eax
    and ebx, 0x07                       ; Low 3 bits = button state
    mov [mouse_btn], ebx

    ; X movement (sign-extend using bit 4 of byte 0)
    movzx ecx, byte [mouse_pkt_buf + 1]
    test eax, 0x10                      ; X sign bit
    jz .mouse_x_pos
    or ecx, 0xFFFFFF00                  ; Sign-extend negative
.mouse_x_pos:
    add [mouse_x], ecx

    ; Y movement (sign-extend using bit 5 of byte 0)
    movzx ecx, byte [mouse_pkt_buf + 2]
    test eax, 0x20                      ; Y sign bit
    jz .mouse_y_pos
    or ecx, 0xFFFFFF00                  ; Sign-extend negative
.mouse_y_pos:
    add [mouse_y], ecx

    ; Reset packet index, set ready flag
    xor edi, edi
    mov dword [mouse_pkt_ready], 1

.mouse_partial:
    mov [mouse_pkt_idx], edi

    ; EOI to both slave and master PIC (IRQ12 is on slave)
    mov al, PIC_EOI
    out PIC2_CMD, al            ; EOI to slave PIC
    out PIC1_CMD, al            ; EOI to master PIC
    popad
    iret

; ----------------------------------------------------------------------------
; serial_putchar - Write character in AL to serial port
; ----------------------------------------------------------------------------
serial_putchar:
    cmp byte [serial_present], 0
    je .skip                ; No COM1 — don't touch serial ports
    push edx
    push eax
    mov dx, COM1_PORT + 5
.wait:
    in al, dx
    test al, 0x20           ; Transmit buffer empty?
    jz .wait
    pop eax
    mov dx, COM1_PORT
    out dx, al
    pop edx
.skip:
    ret

; ----------------------------------------------------------------------------
; serial_getchar - Read character from serial port into AL (non-blocking)
; Returns: AL = char, CF clear = data available, CF set = no data
; (Previously used ZF which broke on NULL characters)
; ----------------------------------------------------------------------------
serial_getchar:
    cmp byte [serial_present], 0
    je .no_data             ; No COM1 hardware — skip
    push edx
    mov dx, COM1_PORT + 5
    in al, dx
    test al, 1              ; Data ready?
    jz .no_data_pop
    mov dx, COM1_PORT
    in al, dx
    pop edx
    clc                     ; CF=0: data available
    ret
.no_data_pop:
    pop edx
.no_data:
    stc                     ; CF=1: no data
    ret

; ----------------------------------------------------------------------------
; init_screen - Initialize VGA text mode
; ----------------------------------------------------------------------------
init_screen:
    push eax
    push ecx
    push edi
    
    ; Clear screen
    mov edi, VGA_TEXT
    mov ecx, VGA_WIDTH * VGA_HEIGHT
    mov ax, (VGA_ATTR << 8) | ' '
    rep stosw
    
    ; Reset cursor
    mov dword [cursor_x], 0
    mov dword [cursor_y], 0
    
    pop edi
    pop ecx
    pop eax
    ret

; ----------------------------------------------------------------------------
; net_flush - Flush net console buffer as UDP packet via RTL8168 TX
; Called from print_char when LF detected or buffer full.
; Uses pre-built frame header template at net_frame_hdr (42 bytes).
; Patches: IP total length, IP ID, IP checksum, UDP length.
; Synchronous: waits for TxOK in ISR before returning.
; ----------------------------------------------------------------------------
net_flush:
    pushad
    mov byte [net_flushing], 1

    mov ecx, [net_buf_pos]
    test ecx, ecx
    jz .nf_done

    ; Copy 42-byte header template to TX-BUF
    mov edi, [net_tx_buf]
    mov esi, net_frame_hdr
    push ecx
    push edi                    ; save TX-BUF base
    mov ecx, 42
    rep movsb
    ; EDI now at TX-BUF + 42

    ; Copy payload (net_buf) to TX-BUF + 42
    pop ebx                     ; EBX = TX-BUF base
    pop ecx                     ; ECX = payload_len
    mov esi, net_buf
    push ecx
    rep movsb

    ; Compute frame length (min 60)
    pop ecx                     ; payload_len
    lea edx, [ecx + 42]
    cmp edx, 60
    jge .nf_no_pad
    mov edx, 60
.nf_no_pad:
    push edx                    ; save frame_len

    ; Patch IP total length at offset 16 (big-endian)
    lea eax, [ecx + 28]
    mov byte [ebx + 16], ah
    mov byte [ebx + 17], al

    ; Patch UDP length at offset 38 (big-endian)
    lea eax, [ecx + 8]
    mov byte [ebx + 38], ah
    mov byte [ebx + 39], al

    ; Patch IP ID at offset 18 (big-endian)
    inc dword [net_pkt_id]
    mov eax, [net_pkt_id]
    mov byte [ebx + 18], ah
    mov byte [ebx + 19], al

    ; Zero IP checksum field at offset 24
    mov word [ebx + 24], 0

    ; Compute IP checksum: sum 10 big-endian 16-bit words
    ; IP header starts at offset 14 in frame
    xor eax, eax
    lea esi, [ebx + 14]
    mov ecx, 10
.nf_cksum:
    movzx edx, byte [esi]
    shl edx, 8
    movzx edi, byte [esi + 1]
    or edx, edi
    add eax, edx
    add esi, 2
    dec ecx
    jnz .nf_cksum

    ; Fold carry (twice)
    mov edx, eax
    shr edx, 16
    and eax, 0xFFFF
    add eax, edx
    mov edx, eax
    shr edx, 16
    add eax, edx
    and eax, 0xFFFF
    xor eax, 0xFFFF

    ; Store checksum at offset 24 (big-endian)
    mov byte [ebx + 24], ah
    mov byte [ebx + 25], al

    ; Set up TX descriptor
    pop edx                     ; frame_len
    mov edi, [net_tx_desc]
    or edx, 0xF0000000          ; OWN + EOR + FS + LS
    mov [edi], edx              ; opts1
    mov dword [edi + 4], 0      ; opts2
    mov [edi + 8], ebx          ; buf addr low (= TX-BUF)
    mov dword [edi + 12], 0     ; buf addr high

    ; Clear TX status, trigger TX, wait for wire completion
    mov eax, [net_rtl_base]
    mov word [eax + 0x3E], 0x000C   ; Clear TxOK + TxErr (w1c)
    mov byte [eax + 0x38], 0x40     ; TxPoll = NPQ

    ; Wait for TxOK or TxErr (ISR bits 2-3) — frame on wire
    mov ecx, 100000
.nf_wait_txok:
    test word [eax + 0x3E], 0x000C
    jnz .nf_txdone
    pause
    dec ecx
    jnz .nf_wait_txok
.nf_txdone:
    mov word [eax + 0x3E], 0x000C   ; Acknowledge TX status
    movzx ecx, word [eax + 0x3E]   ; Read-back flushes PCI posted writes

    ; Reset buffer
    mov dword [net_buf_pos], 0

.nf_done:
    mov byte [net_flushing], 0
    popad
    ret

; ----------------------------------------------------------------------------
; print_char - Print character in AL to both VGA and serial port
; ----------------------------------------------------------------------------
print_char:
    call serial_putchar     ; Mirror to serial port

    ; --- Net console: buffer char for UDP ---
    cmp byte [net_console_enabled], 0
    je .no_net
    cmp byte [net_flushing], 0
    jne .no_net
    push edx
    movzx edx, al
    push eax
    mov eax, [net_buf_pos]
    mov byte [net_buf + eax], dl
    inc eax
    mov [net_buf_pos], eax
    pop eax
    pop edx
    ; Flush on LF (0x0A) or buffer full
    cmp dl, 10
    je .net_do_flush
    cmp dword [net_buf_pos], 256
    jge .net_do_flush
    jmp .no_net
.net_do_flush:
    push eax
    call net_flush
    pop eax
.no_net:

    push ebx
    push ecx
    push edx
    push edi

    cmp al, 13              ; Carriage return
    je .cr
    cmp al, 10              ; Line feed
    je .lf
    cmp al, 8               ; Backspace
    je .bs
    
    ; Normal character
    mov edi, VGA_TEXT
    mov ecx, [cursor_y]
    imul ecx, VGA_WIDTH * 2
    add edi, ecx
    mov ecx, [cursor_x]
    shl ecx, 1
    add edi, ecx
    
    mov ah, VGA_ATTR
    stosw
    
    inc dword [cursor_x]
    cmp dword [cursor_x], VGA_WIDTH
    jl .done
    
.cr:
    mov dword [cursor_x], 0
    jmp .done
    
.lf:
    inc dword [cursor_y]
    cmp dword [cursor_y], VGA_HEIGHT
    jl .lf_more
    ; Scroll screen
    call scroll_screen
    mov dword [cursor_y], VGA_HEIGHT - 1
.lf_more:
    ; MORE pagination: count lines and pause when full screen
    cmp byte [more_enabled], 0
    je .done
    inc dword [more_lines]
    cmp dword [more_lines], 23
    jl .done
    ; Pause: print "-- more --" and wait for keypress
    push eax
    push esi
    mov esi, msg_more
    call print_string
    call read_key               ; Wait for any key
    ; Clear the "-- more --" line: CR + spaces + CR
    mov al, 13
    call serial_putchar
    mov dword [cursor_x], 0
    mov ecx, 12
.more_clear:
    mov al, ' '
    push ecx
    call print_char
    pop ecx
    dec ecx
    jnz .more_clear
    mov al, 13
    call serial_putchar
    mov dword [cursor_x], 0
    pop esi
    pop eax
    mov dword [more_lines], 0
    jmp .done
    
.bs:
    cmp dword [cursor_x], 0
    je .done
    dec dword [cursor_x]
    mov al, ' '
    call print_char
    dec dword [cursor_x]
    
.done:
    pop edi
    pop edx
    pop ecx
    pop ebx
    ret

; ----------------------------------------------------------------------------
; scroll_screen - Scroll VGA text buffer up one line
; ----------------------------------------------------------------------------
scroll_screen:
    push ecx
    push esi
    push edi
    
    mov edi, VGA_TEXT
    mov esi, VGA_TEXT + VGA_WIDTH * 2
    mov ecx, VGA_WIDTH * (VGA_HEIGHT - 1)
    rep movsw
    
    ; Clear last line
    mov ecx, VGA_WIDTH
    mov ax, (VGA_ATTR << 8) | ' '
    rep stosw
    
    pop edi
    pop esi
    pop ecx
    ret

; ----------------------------------------------------------------------------
; print_string - Print null-terminated string at ESI
; ----------------------------------------------------------------------------
print_string:
    push eax
    push esi
.loop:
    lodsb
    test al, al
    jz .done
    call print_char
    jmp .loop
.done:
    pop esi
    pop eax
    ret

; ----------------------------------------------------------------------------
; print_number - Print signed number in EAX using current BASE
; ----------------------------------------------------------------------------
print_number:
    push ebx
    push ecx
    push edx
    push esi
    push edi

    mov edi, num_buffer + 32
    mov byte [edi], 0

    mov ebx, [VAR_BASE]
    test eax, eax
    jns .positive

    ; Negative
    push eax
    mov al, '-'
    call print_char
    pop eax
    neg eax

.positive:
    mov ecx, eax

.digit_loop:
    xor edx, edx
    div ebx

    cmp dl, 10
    jl .decimal
    add dl, 'A' - 10
    jmp .store
.decimal:
    add dl, '0'
.store:
    dec edi
    mov [edi], dl

    test eax, eax
    jnz .digit_loop

    ; Print the number
    mov esi, edi
    call print_string

    pop edi
    pop esi
    pop edx
    pop ecx
    pop ebx
    ret

; ----------------------------------------------------------------------------
; print_unsigned - Print unsigned number in EAX using current base
; ----------------------------------------------------------------------------
print_unsigned:
    push ebx
    push ecx
    push edx
    push esi
    push edi

    mov edi, num_buffer + 32
    mov byte [edi], 0

    mov ebx, [VAR_BASE]
    test ebx, ebx
    jnz .valid_base
    mov ebx, 10                 ; Default to decimal
.valid_base:

.digit_loop:
    xor edx, edx
    div ebx

    cmp dl, 10
    jl .decimal
    add dl, 'A' - 10
    jmp .store
.decimal:
    add dl, '0'
.store:
    dec edi
    mov [edi], dl

    test eax, eax
    jnz .digit_loop

    ; Print the number
    mov esi, edi
    call print_string

    pop edi
    pop esi
    pop edx
    pop ecx
    pop ebx
    ret

; ----------------------------------------------------------------------------
; print_hex - Print 8-digit hex number in EAX
; ----------------------------------------------------------------------------
print_hex:
    push ebx
    push ecx
    push edx
    
    mov ecx, 8                  ; 8 hex digits
    mov ebx, eax
    
.next_digit:
    rol ebx, 4                  ; Rotate left to get next nibble
    mov al, bl
    and al, 0x0F
    cmp al, 10
    jl .decimal
    add al, 'A' - 10
    jmp .print
.decimal:
    add al, '0'
.print:
    call print_char
    dec ecx
    jnz .next_digit
    
    pop edx
    pop ecx
    pop ebx
    ret

; ----------------------------------------------------------------------------
; print_hex_short - Print 4-digit hex number in EAX (lower 16 bits)
; ----------------------------------------------------------------------------
print_hex_short:
    push ebx
    push ecx
    push edx
    
    mov ecx, 4                  ; 4 hex digits
    mov ebx, eax
    shl ebx, 16                 ; Move to upper 16 bits for rotation
    
.next_digit:
    rol ebx, 4                  ; Rotate left to get next nibble
    mov al, bl
    and al, 0x0F
    cmp al, 10
    jl .decimal
    add al, 'A' - 10
    jmp .print
.decimal:
    add al, '0'
.print:
    call print_char
    dec ecx
    jnz .next_digit
    
    pop edx
    pop ecx
    pop ebx
    ret

; ----------------------------------------------------------------------------
; read_key - Wait for and return a keypress in AL
; Tracks Ctrl key state. Ctrl+C sets break_flag and returns 3 (ETX).
; ----------------------------------------------------------------------------
read_key:
    push ebx

.wait:
    ; Check serial port first (for QEMU testing)
    call serial_getchar
    jc .try_kbd             ; CF set = no serial data
    ; Got serial character in AL
    cmp al, 3               ; Ctrl+C via serial?
    je .ctrl_c
    pop ebx
    ret

.try_kbd:
    ; Check keyboard ring buffer (filled by IRQ1 ISR)
    cmp dword [kb_ring_count], 0
    jne .read_ring
    hlt                     ; Sleep until interrupt (timer/keyboard)
    jmp .wait

.read_ring:
    ; Read scancode from ring buffer
    push edi
    mov edi, [kb_ring_tail]
    movzx eax, byte [kb_ring_buf + edi]
    inc edi
    cmp edi, KB_RING_SIZE
    jb .no_wrap
    xor edi, edi
.no_wrap:
    mov [kb_ring_tail], edi
    dec dword [kb_ring_count]
    pop edi

.got_scancode:

    ; Track Ctrl key state (scancode 0x1D = press, 0x9D = release)
    cmp al, 0x1D
    je .ctrl_press
    cmp al, 0x9D
    je .ctrl_release

    ; Track Shift key state
    cmp al, 0x2A            ; Left Shift press
    je .shift_press
    cmp al, 0x36            ; Right Shift press
    je .shift_press
    cmp al, 0xAA            ; Left Shift release
    je .shift_release
    cmp al, 0xB6            ; Right Shift release
    je .shift_release

    ; Caps Lock toggle (press only; release 0xBA falls through to >= 0x80)
    cmp al, 0x3A
    je .caps_toggle

    ; Key release? (bit 7 set = release, unsigned >= 0x80)
    cmp al, 0x80
    jae .wait

    ; Check for Ctrl+C: Ctrl held + 'c' scancode (0x2E)
    cmp byte [ctrl_held], 0
    je .normal_key
    cmp al, 0x2E            ; 'c' scancode
    je .ctrl_c

.normal_key:
    ; Look up ASCII — use shifted table if Shift held
    movzx ebx, al
    cmp byte [shift_held], 0
    jne .use_shift_table
    mov al, [scancode_to_ascii + ebx]
    jmp .apply_caps
.use_shift_table:
    mov al, [scancode_to_ascii_shift + ebx]

.apply_caps:
    ; Caps Lock toggles letter case (a-z <-> A-Z)
    cmp byte [caps_lock], 0
    je .check_result
    cmp al, 'a'
    jb .check_upper
    cmp al, 'z'
    ja .check_result
    sub al, 0x20            ; lowercase -> uppercase
    jmp .check_result
.check_upper:
    cmp al, 'A'
    jb .check_result
    cmp al, 'Z'
    ja .check_result
    add al, 0x20            ; uppercase -> lowercase

.check_result:
    test al, al
    jz .wait

    pop ebx
    ret

.ctrl_press:
    mov byte [ctrl_held], 1
    jmp .wait

.ctrl_release:
    mov byte [ctrl_held], 0
    jmp .wait

.shift_press:
    mov byte [shift_held], 1
    jmp .wait

.shift_release:
    mov byte [shift_held], 0
    jmp .wait

.caps_toggle:
    xor byte [caps_lock], 1
    jmp .wait

.ctrl_c:
    ; Set break flag — interpreter checks this after read_line returns
    mov byte [break_flag], 1
    mov al, 3               ; ETX (Ctrl+C character)
    pop ebx
    ret

; ============================================================================
; Interpreter support routines
; ============================================================================
; (interpret_ has been replaced by inline code in code_INTERPRET above)

; ----------------------------------------------------------------------------
; word_ - Parse next word from input, return address in EAX
; ----------------------------------------------------------------------------
word_:
    push ebx
    push ecx
    push edi
    push esi
    
    mov esi, [VAR_TIB]
    add esi, [VAR_TOIN]
    
    ; Skip leading spaces
.skip_space:
    lodsb
    cmp al, ' '
    je .skip_space
    cmp al, 9               ; Tab
    je .skip_space
    
    test al, al             ; End of line?
    jz .empty
    cmp al, 13
    je .empty
    cmp al, 10
    je .empty
    
    ; Found start of word
    dec esi
    mov edi, word_buffer
    xor ecx, ecx
    
.copy_word:
    lodsb
    cmp al, ' '
    je .end_word
    cmp al, 9
    je .end_word
    test al, al
    jz .end_word
    cmp al, 13
    je .end_word
    cmp al, 10
    je .end_word

    ; Convert to uppercase for dictionary matching
    cmp al, 'a'
    jb .no_upper
    cmp al, 'z'
    ja .no_upper
    sub al, 0x20
.no_upper:
    stosb
    inc ecx
    cmp ecx, 31             ; Max word length
    jl .copy_word
    
.end_word:
    mov byte [edi], 0       ; Null terminate

    ; CRITICAL: lodsb advanced ESI past the delimiter. If the delimiter
    ; was NUL/CR/LF (end-of-line), we must NOT advance past it — otherwise
    ; the next word_ call reads leftover garbage from previous, longer lines.
    ; Fix: always back up to point AT the delimiter. For space/tab delimiters,
    ; the next word_ call will simply skip it in .skip_space.
    dec esi

    ; Update >IN
    mov eax, esi
    sub eax, [VAR_TIB]
    mov [VAR_TOIN], eax

    mov eax, word_buffer
    pop esi
    pop edi
    pop ecx
    pop ebx
    ret

.empty:
    xor eax, eax
    mov dword [VAR_TOIN], 0
    pop esi
    pop edi
    pop ecx
    pop ebx
    ret

; ----------------------------------------------------------------------------
; find_ - Find word in dictionary
; Input: word in word_buffer
; Output: EAX = XT (or 0 if not found), ECX = flags+len byte (if found)
; ----------------------------------------------------------------------------
find_:
    push ebx
    push edx
    push edi
    push esi

    ; Get word length from word_buffer
    mov esi, word_buffer
    xor ecx, ecx
.len_loop:
    lodsb
    test al, al
    jz .got_len
    inc ecx
    jmp .len_loop
.got_len:
    mov edx, ecx            ; EDX = word length

    ; Walk the search order: VAR_SEARCH_ORDER[0..depth-1]
    ; Each entry is the address of a vocabulary's LATEST cell
    xor ecx, ecx            ; ECX = search order index

.next_vocab:
    cmp ecx, [VAR_SEARCH_DEPTH]
    jge .not_found

    ; Get chain head for this vocabulary
    push ecx                 ; Save search order index
    mov eax, [VAR_SEARCH_ORDER + ecx * 4]  ; Address of LATEST cell
    mov ebx, [eax]           ; Dereference: actual latest word in this vocab

.search_loop:
    test ebx, ebx
    jz .vocab_exhausted

    ; Get flags+length byte
    movzx eax, byte [ebx + 4]

    ; Skip hidden words
    test al, F_HIDDEN
    jnz .next_word

    ; Compare length (mask out flags)
    mov ecx, eax
    and ecx, F_LENMASK
    cmp ecx, edx
    jne .next_word

    ; Compare names (repe cmpsb clobbers ESI/EDI/ECX)
    lea esi, [ebx + 5]      ; Name in dictionary
    mov edi, word_buffer
    push ecx
    repe cmpsb
    pop ecx
    jne .next_word

    ; Found! Get flags+len byte
    pop ecx                  ; Discard saved search order index
    movzx ecx, byte [ebx + 4]   ; ECX = flags+length byte

    ; Calculate XT (skip to code field)
    mov eax, edx             ; Name length
    lea eax, [ebx + 5 + eax] ; Skip link(4) + flags(1) + name(len)
    add eax, 3               ; Round up
    and eax, ~3              ; Align to 4 bytes

    pop esi
    pop edi
    pop edx
    pop ebx
    ret

.next_word:
    mov ebx, [ebx]          ; Follow link
    jmp .search_loop

.vocab_exhausted:
    pop ecx                  ; Restore search order index
    inc ecx
    jmp .next_vocab

.not_found:
    ; Fallback: always search the FORTH vocabulary as a last resort.
    ; This ensures core words (DEFINITIONS, FORTH, ORDER, etc.) remain
    ; reachable even when the search order contains only empty vocabularies.
    mov ebx, [VAR_FORTH_LATEST]
.forth_fallback:
    test ebx, ebx
    jz .truly_not_found

    movzx eax, byte [ebx + 4]
    test al, F_HIDDEN
    jnz .forth_next

    mov ecx, eax
    and ecx, F_LENMASK
    cmp ecx, edx
    jne .forth_next

    lea esi, [ebx + 5]
    mov edi, word_buffer
    push ecx
    repe cmpsb
    pop ecx
    jne .forth_next

    ; Found in FORTH fallback
    movzx ecx, byte [ebx + 4]
    mov eax, edx
    lea eax, [ebx + 5 + eax]
    add eax, 3
    and eax, ~3
    pop esi
    pop edi
    pop edx
    pop ebx
    ret

.forth_next:
    mov ebx, [ebx]
    jmp .forth_fallback

.truly_not_found:
    xor eax, eax
    xor ecx, ecx
    pop esi
    pop edi
    pop edx
    pop ebx
    ret

; ----------------------------------------------------------------------------
; number_ - Parse number from word_buffer
; Returns: EAX = number, EDX = 0 on success, -1 on failure
; ----------------------------------------------------------------------------
number_:
    push ebx
    push ecx
    push esi
    
    mov esi, word_buffer
    xor eax, eax
    xor ecx, ecx            ; Accumulator
    mov ebx, [VAR_BASE]
    xor edx, edx            ; Sign flag
    
    ; Check for negative
    cmp byte [esi], '-'
    jne .parse_loop
    inc edx                 ; Set sign flag
    inc esi
    
.parse_loop:
    movzx eax, byte [esi]
    test al, al
    jz .done
    
    ; Convert character to digit
    cmp al, '0'
    jl .error
    cmp al, '9'
    jle .decimal
    
    ; Could be hex
    or al, 0x20             ; Lowercase
    cmp al, 'a'
    jl .error
    cmp al, 'z'
    jg .error
    sub al, 'a' - 10
    jmp .got_digit
    
.decimal:
    sub al, '0'
    
.got_digit:
    cmp eax, ebx            ; Check against base
    jge .error
    
    imul ecx, ebx
    add ecx, eax
    inc esi
    jmp .parse_loop
    
.done:
    mov eax, ecx
    test edx, edx
    jz .positive
    neg eax
.positive:
    xor edx, edx            ; Success
    pop esi
    pop ecx
    pop ebx
    ret
    
.error:
    mov edx, -1             ; Failure
    pop esi
    pop ecx
    pop ebx
    ret

; ----------------------------------------------------------------------------
; comma_ - Compile cell in EAX to dictionary
; ----------------------------------------------------------------------------
comma_:
    push edi
    mov edi, [VAR_HERE]
    stosd
    mov [VAR_HERE], edi
    pop edi
    ret

; ----------------------------------------------------------------------------
; create_ - Create dictionary header for word in word_buffer
; ----------------------------------------------------------------------------
create_:
    push eax
    push ebx
    push ecx
    push edi
    push esi

    mov edi, [VAR_HERE]

    ; Write link: chain into the current vocabulary
    mov ebx, [VAR_CURRENT]      ; Address of current vocab's LATEST cell
    mov eax, [ebx]              ; Dereference: actual latest word in this vocab
    stosd

    ; Calculate name length
    mov esi, word_buffer
    xor ecx, ecx
.len:
    lodsb
    test al, al
    jz .got_len
    inc ecx
    jmp .len
.got_len:

    ; Write flags + length
    mov al, cl
    stosb

    ; Write name
    mov esi, word_buffer
    rep movsb

    ; Align to 4 bytes
    mov eax, edi
    add eax, 3
    and eax, ~3
    mov edi, eax

    ; Update current vocab's LATEST and global LATEST and HERE
    mov eax, [VAR_HERE]         ; Address of new word header
    mov ebx, [VAR_CURRENT]
    mov [ebx], eax              ; Update current vocab's LATEST
    mov [VAR_LATEST], eax       ; Also update global LATEST (for ; IMMEDIATE etc.)
    mov [VAR_HERE], edi

    pop esi
    pop edi
    pop ecx
    pop ebx
    pop eax
    ret

; ----------------------------------------------------------------------------
; read_line - Read a line of input into TIB
; If Ctrl+C is pressed during input, break_flag is set and line is discarded.
; ----------------------------------------------------------------------------
read_line:
    push ebx
    push ecx
    push edi

    mov edi, TIB_START
    xor ecx, ecx

.loop:
    call read_key

    ; Check for Ctrl+C break (read_key returns 3 = ETX)
    cmp al, 3
    je .break

    cmp al, 13              ; Carriage return (Enter via keyboard)
    je .done
    cmp al, 10              ; Line feed (Enter via serial)
    je .done
    cmp al, 8               ; Backspace
    je .backspace
    cmp al, 127             ; DEL (Backspace via serial terminal)
    je .backspace

    cmp ecx, TIB_SIZE - 1
    jge .loop               ; Buffer full

    stosb
    inc ecx
    call print_char         ; Echo
    jmp .loop

.backspace:
    test ecx, ecx
    jz .loop
    dec edi
    dec ecx
    mov al, 8
    call print_char
    mov al, ' '
    call print_char
    mov al, 8
    call print_char
    jmp .loop

.break:
    ; Discard line, null-terminate at start
    mov edi, TIB_START
    mov byte [edi], 0
    mov al, 13
    call print_char
    mov al, 10
    call print_char
    pop edi
    pop ecx
    pop ebx
    ret

.done:
    mov byte [edi], 0       ; Null terminate
    mov al, 13
    call print_char
    mov al, 10
    call print_char

    pop edi
    pop ecx
    pop ebx
    ret

; ============================================================================
; ATA PIO Driver
; ============================================================================

; ----------------------------------------------------------------------------
; ata_wait_ready - Wait for ATA drive to be ready (BSY clear)
; Clobbers: AL, DX
; ----------------------------------------------------------------------------
ata_wait_ready:
    mov dx, ATA_CMD_STATUS
.wait:
    in al, dx
    test al, 0x80               ; BSY bit
    jnz .wait
    ret

; ----------------------------------------------------------------------------
; ata_wait_drq - Wait for DRQ (data request) after command
; Returns: CF clear = OK, CF set = error
; Clobbers: AL, DX
; ----------------------------------------------------------------------------
ata_wait_drq:
    mov dx, ATA_CMD_STATUS
.wait:
    in al, dx
    test al, 0x80               ; Still busy?
    jnz .wait
    test al, 0x01               ; ERR bit?
    jnz .error
    test al, 0x08               ; DRQ bit?
    jz .wait
    clc
    ret
.error:
    stc
    ret

; ----------------------------------------------------------------------------
; ata_read_sector - Read one 512-byte sector via ATA PIO
; Input:  EBX = LBA sector number, EDI = destination buffer
; Output: CF clear = success, CF set = error
; Clobbers: EAX, ECX, EDX
; Note: Does NOT clobber ESI (uses rep insw with EDI only)
; ----------------------------------------------------------------------------
ata_read_sector:
    call ata_wait_ready

    ; Set sector count = 1
    mov dx, ATA_SECCOUNT
    mov al, 1
    out dx, al

    ; Set LBA bytes
    mov dx, ATA_LBA_LO
    mov al, bl
    out dx, al

    mov dx, ATA_LBA_MID
    mov al, bh
    out dx, al

    mov dx, ATA_LBA_HI
    mov eax, ebx
    shr eax, 16
    out dx, al

    ; Drive select: IDE slave (index=1), LBA mode, top 4 LBA bits
    mov dx, ATA_DRIVE
    mov eax, ebx
    shr eax, 24
    and al, 0x0F
    or al, 0xF0                 ; LBA mode + slave (bit 4 = 1)
    out dx, al

    ; Send READ SECTORS command
    mov dx, ATA_CMD_STATUS
    mov al, 0x20
    out dx, al

    ; Wait for data
    call ata_wait_drq
    jc .done

    ; Read 256 words (512 bytes) from data port
    mov dx, ATA_DATA
    mov ecx, 256
    rep insw

    clc
.done:
    ret

; ----------------------------------------------------------------------------
; ata_write_sector - Write one 512-byte sector via ATA PIO
; Input:  EBX = LBA sector number, ESI = source buffer
; Output: CF clear = success, CF set = error
; Clobbers: EAX, ECX, EDX, ESI (caller must save/restore Forth IP!)
; ----------------------------------------------------------------------------
ata_write_sector:
    call ata_wait_ready

    ; Set sector count = 1
    mov dx, ATA_SECCOUNT
    mov al, 1
    out dx, al

    ; Set LBA bytes
    mov dx, ATA_LBA_LO
    mov al, bl
    out dx, al

    mov dx, ATA_LBA_MID
    mov al, bh
    out dx, al

    mov dx, ATA_LBA_HI
    mov eax, ebx
    shr eax, 16
    out dx, al

    ; Drive select: IDE slave, LBA mode, top 4 LBA bits
    mov dx, ATA_DRIVE
    mov eax, ebx
    shr eax, 24
    and al, 0x0F
    or al, 0xF0                 ; LBA mode + slave
    out dx, al

    ; Send WRITE SECTORS command
    mov dx, ATA_CMD_STATUS
    mov al, 0x30
    out dx, al

    ; Wait for DRQ
    call ata_wait_drq
    jc .done

    ; Write 256 words (512 bytes) to data port
    mov dx, ATA_DATA
    mov ecx, 256
    rep outsw

    ; Flush write cache
    call ata_wait_ready
    mov dx, ATA_CMD_STATUS
    mov al, 0xE7                ; FLUSH CACHE command
    out dx, al
    call ata_wait_ready

    clc
.done:
    ret

; ============================================================================
; Block Buffer Manager
; ============================================================================

; ----------------------------------------------------------------------------
; blk_find_buffer - Find or allocate a buffer for a given block number
; Input:  EAX = block number
; Output: EDI = buffer data address
;         EBX = header address
;         CF set = buffer needs loading from disk, CF clear = already cached
; Clobbers: ECX, EDX
; ----------------------------------------------------------------------------
blk_find_buffer:
    push eax
    mov edx, eax                ; EDX = requested block#

    ; Search existing buffers for a match
    mov ebx, BLK_BUF_HEADERS
    mov ecx, BLK_NUM_BUFFERS
.search:
    cmp [ebx], edx              ; block# match?
    jne .next_search
    test dword [ebx + 4], BLK_BUF_FLAG_VALID
    jz .next_search
    ; Found! Update age for LRU
    inc dword [BLK_BUF_CLOCK]
    mov eax, [BLK_BUF_CLOCK]
    mov [ebx + 8], eax          ; Update age
    ; Calculate buffer index and data address
    mov eax, ebx
    sub eax, BLK_BUF_HEADERS
    push edx
    xor edx, edx
    push ebx
    mov ebx, BLK_HEADER_SIZE
    div ebx                     ; EAX = buffer index
    pop ebx
    pop edx
    mov [BLK_BUF_CUR], eax
    imul eax, BLOCK_SIZE
    lea edi, [BLK_BUF_DATA + eax]
    pop eax
    clc                         ; Already cached
    ret

.next_search:
    add ebx, BLK_HEADER_SIZE
    dec ecx
    jnz .search

    ; Not found — find a free buffer or LRU victim
    mov ebx, BLK_BUF_HEADERS
    mov ecx, BLK_NUM_BUFFERS
    xor eax, eax                ; Best candidate index
    mov edi, 0xFFFFFFFF         ; Lowest age so far (for LRU)
    push esi                    ; Save temporarily

    ; First pass: look for a free (invalid) buffer
    mov esi, BLK_BUF_HEADERS
    xor ecx, ecx
.find_free:
    cmp ecx, BLK_NUM_BUFFERS
    jge .find_lru
    test dword [esi + 4], BLK_BUF_FLAG_VALID
    jz .found_slot
    ; Track LRU while searching
    mov ebx, [esi + 8]         ; age
    cmp ebx, edi
    jge .not_older
    mov edi, ebx               ; New lowest age
    mov eax, ecx               ; Remember this index
.not_older:
    add esi, BLK_HEADER_SIZE
    inc ecx
    jmp .find_free

.find_lru:
    ; No free buffer — use LRU victim (index in EAX)
    ; If victim is dirty, flush it first
    imul ebx, eax, BLK_HEADER_SIZE
    add ebx, BLK_BUF_HEADERS
    test dword [ebx + 4], BLK_BUF_FLAG_DIRTY
    jz .setup_slot
    pop esi
    push edx                   ; Save requested block#
    call blk_flush_one
    pop edx
    push esi                   ; Re-save
    jmp .setup_slot

.found_slot:
    ; Free buffer at index ECX
    mov eax, ecx
    imul ebx, eax, BLK_HEADER_SIZE
    add ebx, BLK_BUF_HEADERS

.setup_slot:
    pop esi                    ; Restore
    ; Set up the header
    mov [ebx], edx             ; block#
    mov dword [ebx + 4], 0    ; flags = 0 (not valid yet, caller will set)
    inc dword [BLK_BUF_CLOCK]
    mov ecx, [BLK_BUF_CLOCK]
    mov [ebx + 8], ecx        ; age
    mov [BLK_BUF_CUR], eax    ; Current buffer index

    ; Calculate data address
    imul eax, BLOCK_SIZE
    lea edi, [BLK_BUF_DATA + eax]

    pop eax                    ; Restore original block#
    stc                        ; Needs loading from disk
    ret

; ----------------------------------------------------------------------------
; blk_flush_one - Write a dirty buffer back to disk
; Input:  EBX = header address (must point to a valid dirty buffer)
; Preserves ESI (Forth IP). Clobbers: EAX, ECX, EDX, EDI
; ----------------------------------------------------------------------------
blk_flush_one:
    test dword [ebx + 4], BLK_BUF_FLAG_DIRTY
    jz .not_dirty

    push ebx
    push edi
    PUSHRSP esi                 ; Save Forth IP BEFORE overwriting ESI

    ; Calculate buffer data address from header address
    mov eax, ebx
    sub eax, BLK_BUF_HEADERS
    push edx
    push ebx
    xor edx, edx
    mov ecx, BLK_HEADER_SIZE
    div ecx                     ; EAX = buffer index
    pop ebx
    pop edx

%ifdef DEBUG_FLUSH
    ; Trace entry: F<slot> <block#_hex> <flags_hex>
    push eax                    ; save buffer index
    push eax
    mov al, 'F'
    call serial_putchar
    pop eax
    add al, '0'                 ; slot index as ASCII digit
    call serial_putchar
    mov al, ' '
    call serial_putchar
    mov eax, [ebx]              ; block#
    call serial_print_hex
    mov al, ' '
    call serial_putchar
    mov eax, [ebx + 4]          ; flags
    call serial_print_hex
    mov al, 13
    call serial_putchar
    mov al, 10
    call serial_putchar
    pop eax                     ; restore buffer index
%endif

    imul eax, BLOCK_SIZE
    lea esi, [BLK_BUF_DATA + eax]  ; ESI = buffer data (source for write)

    ; Block# -> LBA: each block is 2 sectors (1024 bytes / 512)
    mov eax, [ebx]              ; block#
    shl eax, 1                  ; LBA = block# * 2
    mov ecx, eax                ; Save first LBA

%ifdef DEBUG_FLUSH
    ; Trace write start: W<LBA_hex> <ESI_hex>
    push eax
    mov al, 'W'
    call serial_putchar
    mov eax, ecx                ; LBA
    call serial_print_hex
    mov al, ' '
    call serial_putchar
    mov eax, esi                ; buffer data address
    call serial_print_hex
    mov al, 13
    call serial_putchar
    mov al, 10
    call serial_putchar
    pop eax
%endif

    ; Write first sector (512 bytes)
    mov ebx, ecx                ; LBA
    call ata_write_sector
    ; rep outsw already advanced ESI by 512

    ; Write second sector (ESI now points to buffer + 512)
    inc ebx                     ; Next LBA
    call ata_write_sector

%ifdef DEBUG_FLUSH
    ; Trace write done: D<ATA_status_hex>
    push eax
    push edx
    mov al, 'D'
    call serial_putchar
    mov dx, 0x1F7               ; ATA status register
    in al, dx
    movzx eax, al
    call serial_print_hex
    mov al, 13
    call serial_putchar
    mov al, 10
    call serial_putchar
    pop edx
    pop eax
%endif

    POPRSP esi                  ; Restore Forth IP

    pop edi
    pop ebx

    ; Clear dirty flag (keep valid)
    and dword [ebx + 4], ~BLK_BUF_FLAG_DIRTY

.not_dirty:
    ret

%ifdef DEBUG_FLUSH
; ----------------------------------------------------------------------------
; serial_print_hex - Print 8-digit hex number in EAX to serial port only
; (Does not touch VGA, unlike print_hex which calls print_char)
; ----------------------------------------------------------------------------
serial_print_hex:
    push ebx
    push ecx
    push edx
    mov ecx, 8
    mov ebx, eax
.next_digit:
    rol ebx, 4
    mov al, bl
    and al, 0x0F
    cmp al, 10
    jl .decimal
    add al, 'A' - 10
    jmp .emit
.decimal:
    add al, '0'
.emit:
    call serial_putchar
    dec ecx
    jnz .next_digit
    pop edx
    pop ecx
    pop ebx
    ret
%endif

; ============================================================================
; Cold Start Word List
; ============================================================================

cold_start:
    dd INTERPRET
    dd BRANCH
    dd -8                   ; Loop back to INTERPRET

; ============================================================================
; Data
; ============================================================================

cursor_x:       dd 0
cursor_y:       dd 0

; Ctrl+C break handler state
ctrl_held:      db 0                ; 1 = Ctrl key currently pressed
shift_held:     db 0                ; 1 = Shift key currently pressed
caps_lock:      db 0                ; 1 = Caps Lock active
serial_present: db 1                ; 0 = no COM1 hardware (set by init_serial probe)
break_flag:     db 0                ; 1 = Ctrl+C detected, pending break
                align 4
save_esp:       dd 0                ; Snapshot: data stack pointer
save_ebp:       dd 0                ; Snapshot: return stack pointer
save_state:     dd 0                ; Snapshot: compiler STATE
save_here:      dd 0                ; Snapshot: dictionary HERE pointer
save_latest:    dd 0                ; Snapshot: LATEST word pointer

msg_welcome:    db 'Bare-Metal Forth v0.1 - Ship Builders System', 13, 10
                db 'Type WORDS to see available commands', 13, 10, 0
msg_stack:      db '<', 0
msg_undefined:  db ' ? ', 13, 10, 0
msg_break:      db 'BREAK', 13, 10, 0
msg_more:       db '-- more --', 0
see_msg:        db 'SEE: ', 0
primitive_msg:  db '<primitive>', 0
msg_search:     db 'Search: ', 0
msg_compile:    db ' Compile: ', 0

word_buffer:    times 32 db 0
num_buffer:     times 36 db 0
string_buffer:  times 256 db 0

; Scancode to ASCII table (simplified US layout)
scancode_to_ascii:
    db 0, 27, '1234567890-=', 8, 9       ; 0x00-0x0F
    db 'qwertyuiop[]', 13, 0, 'as'       ; 0x10-0x1F
    db 'dfghjkl;', 39, '`', 0, '\zxcv'   ; 0x20-0x2F
    db 'bnm,./', 0, '*', 0, ' '          ; 0x30-0x3F
    times 64 db 0                         ; 0x40-0x7F

; Shifted scancode to ASCII table (US layout)
scancode_to_ascii_shift:
    db 0, 27, '!@#$%^&*()_+', 8, 9       ; 0x00-0x0F
    db 'QWERTYUIOP{}', 13, 0, 'AS'       ; 0x10-0x1F
    db 'DFGHJKL:', 34, '~', 0, '|ZXCV'   ; 0x20-0x2F
    db 'BNM<>?', 0, '*', 0, ' '          ; 0x30-0x3F
    times 64 db 0                         ; 0x40-0x7F

; ============================================================================
; ISR Data
; ============================================================================

; Timer tick counter (incremented by IRQ0 ISR)
isr_tick_count:     dd 0

; Keyboard ring buffer (16 bytes, filled by IRQ1 ISR)
kb_ring_buf:        times KB_RING_SIZE db 0
                    align 4
kb_ring_head:       dd 0            ; Write position (used by ISR only)
kb_ring_tail:       dd 0            ; Read position (used by Forth)
kb_ring_count:      dd 0            ; Number of bytes in buffer

; Mouse packet buffer (3 bytes, filled by IRQ12 ISR)
mouse_pkt_buf:      times 3 db 0
                    align 4
mouse_pkt_idx:      dd 0            ; Current byte index in packet (0-2)
mouse_pkt_ready:    dd 0            ; 1 = full 3-byte packet available

; Mouse state (decoded from packets)
mouse_x:            dd 0            ; Accumulated X position
mouse_y:            dd 0            ; Accumulated Y position
mouse_btn:          dd 0            ; Button state (low 3 bits)

; MORE pagination state
more_enabled:       db 0            ; 0 = off (default), 1 = on
                    align 4
more_lines:         dd 0            ; Lines printed since last pause

; Net console state (UDP output mirror)
net_console_enabled:    db 0        ; 1 = mirror output to UDP
net_flushing:           db 0        ; 1 = flush in progress (re-entrancy guard)
                        align 4
net_buf_pos:            dd 0        ; Current position in output buffer
net_rtl_base:           dd 0        ; Copy of RTL-BASE (MMIO address)
net_tx_desc:            dd 0        ; TX descriptor physical address
net_tx_buf:             dd 0        ; TX frame buffer physical address
net_pkt_id:             dd 0        ; IP packet ID counter
net_frame_hdr:          times 42 db 0   ; Pre-built Ethernet+IP+UDP header
net_buf:                times 256 db 0  ; Output character buffer

; ECHOPORT trace state
trace_enabled:      db 0            ; 0 = off, 1 = on
                    align 4
trace_head:         dd 0            ; Next write index (wraps via AND mask)
trace_count:        dd 0            ; Total entries logged (may exceed BUF_SIZE)
trace_buf:          times (TRACE_BUF_SIZE * TRACE_ENTRY_SZ) db 0

; ============================================================================
; Embedded Vocabularies (evaluated at boot, no block storage needed)
; ============================================================================
; Built by: python3 tools/embed-vocabs.py build/embedded.bin <files...>
; Contains comment-stripped Forth source as a NUL-terminated token stream.
; The kernel evaluates this at boot before entering the interactive prompt.

embed_data:
    incbin "build/embedded.bin"
embed_end:

embed_size: dd (embed_end - embed_data)

; ============================================================================
; End of Kernel
; ============================================================================

; Pad kernel to exactly 64KB (128 sectors) to match bootloader's KERNEL_SECTORS
times 0x10000 - ($ - $$) db 0
