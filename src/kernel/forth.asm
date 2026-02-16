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
;   0x00007E00 - Kernel start (loaded by bootloader)
;   0x00010000 - Data stack (grows down)
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
DATA_STACK_TOP      equ 0x10000
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

; Word flags
F_IMMEDIATE         equ 0x80        ; Immediate word
F_HIDDEN            equ 0x40        ; Hidden from FIND
F_LENMASK           equ 0x3F        ; Length mask

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
    mov dword [VAR_LATEST], name_USING   ; Last built-in word
    mov dword [VAR_BASE], 10
    mov dword [VAR_TIB], TIB_START
    mov dword [VAR_TOIN], 0

    ; Initialize block storage variables
    mov dword [VAR_BLK], 0
    mov dword [VAR_SCR], 0
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
    mov dword [VAR_FORTH_LATEST], name_USING  ; FORTH vocab starts same as LATEST
    mov dword [VAR_SEARCH_DEPTH], 1
    mov dword [VAR_SEARCH_ORDER], VAR_FORTH_LATEST  ; Addr of FORTH's LATEST cell
    mov dword [VAR_CURRENT], VAR_FORTH_LATEST       ; New defs go into FORTH

    ; Clear screen
    call init_screen

    ; Print welcome message
    mov esi, msg_welcome
    call print_string

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
    push eax
    NEXT

DEFCODE "INW", INW, 0       ; ( port -- word )
    pop edx
    xor eax, eax
    in ax, dx
    push eax
    NEXT

DEFCODE "INL", INL, 0       ; ( port -- dword )
    pop edx
    in eax, dx
    push eax
    NEXT

DEFCODE "OUTB", OUTB, 0     ; ( byte port -- )
    pop edx
    pop eax
    out dx, al
    NEXT

DEFCODE "OUTW", OUTW, 0     ; ( word port -- )
    pop edx
    pop eax
    out dx, ax
    NEXT

DEFCODE "OUTL", OUTL, 0     ; ( dword port -- )
    pop edx
    pop eax
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

    ; TOIN=0: either need new line (interactive) or block exhausted (LOAD)
    cmp dword [VAR_BLK], 0
    jne .block_exhausted         ; BLK!=0 means LOAD is done with this block

    ; Interactive mode: print prompt and read a line
    mov al, 'o'
    call print_char
    mov al, 'k'
    call print_char
    mov al, ' '
    call print_char

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
    pop esi
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
    pop ebx                    ; Get dest
    mov ecx, [VAR_HERE]
    sub ebx, ecx               ; Offset (negative for backward)
    sub ebx, 4                 ; Account for offset cell
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
    pop ebx
    mov ecx, [VAR_HERE]
    sub ebx, ecx
    sub ebx, 4
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
    pop ebx
    mov ecx, [VAR_HERE]
    sub ebx, ecx
    sub ebx, 4
    mov [ecx], ebx
    add dword [VAR_HERE], 4
    ; Patch WHILE's 0BRANCH
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
    ; Copy string characters starting at HERE
    mov edi, [VAR_HERE]
    xor ecx, ecx
.copy:
    call read_key
    cmp al, '"'
    je .endcopy
    stosb
    inc ecx
    jmp .copy
.endcopy:
    ; Patch the length
    mov [ebx], ecx
    ; Align HERE past string data
    mov eax, edi
    add eax, 3
    and eax, ~3
    mov [VAR_HERE], eax
    NEXT
.interpret:
    ; Interpret mode: read string to temp buffer
    mov edi, string_buffer
    xor ecx, ecx
.interp_copy:
    call read_key
    cmp al, '"'
    je .interp_done
    stosb
    inc ecx
    jmp .interp_copy
.interp_done:
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

; ." - Print string
DEFCODE '."', DOTQUOTE, F_IMMEDIATE
    ; Layout: [DOSQUOTE XT][length][string bytes...][align][TYPE XT]
    mov eax, [VAR_HERE]
    mov dword [eax], DOSQUOTE       ; Compile (S") XT
    add dword [VAR_HERE], 4
    ; Reserve space for length
    mov ebx, [VAR_HERE]             ; Save length cell address
    add dword [VAR_HERE], 4
    ; Copy string characters
    mov edi, [VAR_HERE]
    xor ecx, ecx
.copy:
    call read_key
    cmp al, '"'
    je .done
    stosb
    inc ecx
    jmp .copy
.done:
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
.skip:
    call read_key
    cmp al, ')'
    jne .skip
    NEXT

; \ - Line comment
DEFCODE '\', BACKSLASH, F_IMMEDIATE
.skip:
    call read_key
    cmp al, 10                 ; newline
    je .done
    cmp al, 13                 ; carriage return  
    je .done
    jmp .skip
.done:
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
    dd SWAP                     ; ( n2 n1 )
    dd DODO                     ; DO
    dd I                        ;   I
    dd LOAD                     ;   LOAD
    dd DOLOOP                   ;   LOOP
    dd -12                      ;   (backward offset: 3 cells = 12 bytes)
    dd EXIT

; ============================================================================
; Vocabulary / Search Order Words
; ============================================================================

; DOVOC runtime — executed when a vocabulary word runs
; Replaces top of search order with this vocabulary's LATEST cell address
DOVOC:
    mov eax, [eax + 4]         ; Parameter field = addr of vocab's LATEST cell
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
; Low-Level Support Routines
; ============================================================================

; ----------------------------------------------------------------------------
; init_serial - Initialize COM1 serial port (115200 baud, 8N1)
; ----------------------------------------------------------------------------
init_serial:
    push eax
    push edx
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
; serial_putchar - Write character in AL to serial port
; ----------------------------------------------------------------------------
serial_putchar:
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
    ret

; ----------------------------------------------------------------------------
; serial_getchar - Read character from serial port into AL (non-blocking)
; Returns: AL = char, CF clear = data available, CF set = no data
; (Previously used ZF which broke on NULL characters)
; ----------------------------------------------------------------------------
serial_getchar:
    push edx
    mov dx, COM1_PORT + 5
    in al, dx
    test al, 1              ; Data ready?
    jz .no_data
    mov dx, COM1_PORT
    in al, dx
    pop edx
    clc                     ; CF=0: data available
    ret
.no_data:
    pop edx
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
; print_char - Print character in AL to both VGA and serial port
; ----------------------------------------------------------------------------
print_char:
    call serial_putchar     ; Mirror to serial port
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
    jl .done
    
    ; Scroll screen
    call scroll_screen
    mov dword [cursor_y], VGA_HEIGHT - 1
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
    ; Check serial port first (for QEMU -nographic mode)
    call serial_getchar
    jc .try_kbd             ; CF set = no serial data
    ; Got serial character in AL
    cmp al, 3               ; Ctrl+C via serial?
    je .ctrl_c
    pop ebx
    ret

.try_kbd:
    ; Check PS/2 keyboard controller
    in al, 0x64             ; Read status
    test al, 1              ; Data available?
    jz .wait                ; Neither serial nor kbd ready, loop

    in al, 0x60             ; Read scancode

    ; Track Ctrl key state (scancode 0x1D = press, 0x9D = release)
    cmp al, 0x1D
    je .ctrl_press
    cmp al, 0x9D
    je .ctrl_release

    ; Key release? (bit 7 set = release)
    cmp al, 0x80
    jge .wait

    ; Check for Ctrl+C: Ctrl held + 'c' scancode (0x2E)
    cmp byte [ctrl_held], 0
    je .normal_key
    cmp al, 0x2E            ; 'c' scancode
    je .ctrl_c

.normal_key:
    ; Check for shift state for uppercase letters
    movzx ebx, al
    mov al, [scancode_to_ascii + ebx]
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
; Clobbers: EAX, ECX, EDX (and ESI temporarily via ata_write_sector)
; ----------------------------------------------------------------------------
blk_flush_one:
    test dword [ebx + 4], BLK_BUF_FLAG_DIRTY
    jz .not_dirty

    push ebx
    push edi

    ; Calculate buffer data address from header address
    mov eax, ebx
    sub eax, BLK_BUF_HEADERS
    push edx
    xor edx, edx
    push ebx
    mov ecx, BLK_HEADER_SIZE
    push eax
    pop eax
    xor edx, edx
    div ecx                     ; EAX = buffer index
    pop ebx
    pop edx
    imul eax, BLOCK_SIZE
    lea esi, [BLK_BUF_DATA + eax]  ; ESI = buffer data (source for write)

    ; Block# -> LBA: each block is 2 sectors (1024 bytes / 512)
    mov eax, [ebx]              ; block#
    shl eax, 1                  ; LBA = block# * 2
    mov ecx, eax                ; Save first LBA

    ; Write first sector (512 bytes)
    PUSHRSP esi                 ; Save Forth IP on return stack
    ; ESI already points to buffer data
    mov ebx, ecx                ; LBA
    call ata_write_sector

    ; Write second sector
    add esi, 512                ; Next 512 bytes
    inc ebx                     ; Next LBA
    call ata_write_sector
    POPRSP esi                  ; Restore Forth IP

    pop edi
    pop ebx

    ; Clear dirty flag (keep valid)
    and dword [ebx + 4], ~BLK_BUF_FLAG_DIRTY

.not_dirty:
    ret

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

; ============================================================================
; End of Kernel
; ============================================================================

; Pad kernel to exactly 32KB (64 sectors) to match bootloader's KERNEL_SECTORS
times 0x8000 - ($ - $$) db 0
