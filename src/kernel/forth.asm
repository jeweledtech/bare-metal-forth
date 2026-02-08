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
;   0x00030000 - Dictionary start
;   0x000A0000 - VGA memory
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

; Input buffer
TIB_START           equ 0x28100     ; Terminal Input Buffer
TIB_SIZE            equ 256

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
; Kernel Entry Point
; ============================================================================

kernel_start:
    ; Initialize stacks
    mov esp, DATA_STACK_TOP
    mov ebp, RETURN_STACK_TOP
    
    ; Initialize variables
    mov dword [VAR_STATE], 0
    mov dword [VAR_HERE], DICT_START
    mov dword [VAR_LATEST], name_BYE    ; Last built-in word
    mov dword [VAR_BASE], 10
    mov dword [VAR_TIB], TIB_START
    mov dword [VAR_TOIN], 0
    
    ; Clear screen
    call init_screen
    
    ; Print welcome message
    mov esi, msg_welcome
    call print_string
    
    ; Enter main interpreter loop
    mov esi, cold_start
    jmp NEXT

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
    ; %1 = name string
    ; %2 = label
    ; %3 = flags (0 for normal, F_IMMEDIATE for immediate)
    
    section .data
    align 4
name_%2:
    dd link                 ; Link to previous word
    %define link name_%2
    db %3 + %%end_name - %%start_name  ; Flags + length
%%start_name:
    db %1                   ; Name
%%end_name:
    align 4                 ; Align to 4 bytes
%2:
    dd DOCOL               ; Code field: this is a colon definition
    ; Parameter field follows (list of word addresses)
%endmacro

%macro DEFCODE 3
    ; %1 = name string
    ; %2 = label
    ; %3 = flags
    
    section .data
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
    section .text
code_%2:
    ; Native code follows
%endmacro

%macro DEFVAR 3
    ; %1 = name string
    ; %2 = label
    ; %3 = initial value
    
    section .data
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
var_%2:
    dd %3
    section .text
code_%2:
    push var_%2
    NEXT
%endmacro

%macro DEFCONST 3
    ; %1 = name string
    ; %2 = label
    ; %3 = value
    
    section .data
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
    section .text
code_%2:
    push %3
    NEXT
%endmacro

; ============================================================================
; Core Interpreter Routines
; ============================================================================

section .text

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

section .data
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
    
    ; Apply floored semantics if needed
    mov ecx, eax
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

DEFCODE "ABS", ABS, 0
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
    pop ecx                 ; Count
    pop edi                 ; Destination
    pop esi                 ; Source
    rep movsb
    NEXT

DEFCODE "CMOVE>", CMOVEUP, 0  ; Move from high addresses down
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
    NEXT

DEFCODE "FILL", FILL, 0     ; ( addr count byte -- )
    pop eax                 ; Byte
    pop ecx                 ; Count
    pop edi                 ; Address
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
    pop esi                 ; Address
    test ecx, ecx
    jz .done
.loop:
    lodsb
    call print_char
    loop .loop
.done:
    NEXT

DEFCODE ".", DOT, 0         ; ( n -- ) Print number
    pop eax
    call print_number
    mov al, ' '
    call print_char
    NEXT

DEFCODE ".S", DOTS, 0       ; Show stack
    mov esi, msg_stack
    call print_string
    
    mov ecx, DATA_STACK_TOP
    sub ecx, esp
    shr ecx, 2              ; Number of items
    
    mov edi, esp
.loop:
    test ecx, ecx
    jz .done
    mov eax, [edi]
    call print_number
    mov al, ' '
    call print_char
    add edi, 4
    dec ecx
    jmp .loop
.done:
    mov al, '>'
    call print_char
    NEXT

; --- Variables and Constants ---

DEFVAR "STATE", STATE, 0
DEFVAR "HERE", HERE, DICT_START
DEFVAR "LATEST", LATEST, name_BYE
DEFVAR "BASE", BASE, 10

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
    mov esi, msg_undefined
    call print_string
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

DEFCODE "INTERPRET", INTERPRET, 0
    call interpret_
    NEXT

DEFCODE "WORD", WORD, 0     ; ( -- c-addr )
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
DEFCODE "POSTPONE", POSTPONE, F_IMMEDIATE
    call word_
    call find_
    test eax, eax
    jz .notfound
    ; Get flags
    mov ebx, [VAR_LATEST]
    ; Check if immediate
    mov cl, [eax + 4]       ; Get flags byte (in dictionary entry)
    ; For now, just compile a call to it
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
    ; Compile unconditional BRANCH
    mov eax, [VAR_HERE]
    mov dword [eax], BRANCH
    add dword [VAR_HERE], 4
    
    ; Push location for later patching
    push dword [VAR_HERE]
    add dword [VAR_HERE], 4
    
    ; Now resolve the IF
    pop ebx                    ; Get orig from IF (swapped)
    xchg eax, [esp]            ; Swap: orig2 goes on stack, get orig1
    mov ebx, [VAR_HERE]
    sub ebx, eax
    mov [eax], ebx
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
    mov dword [eax], code_DODO
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
    mov dword [eax], code_DOLOOP
    add dword [VAR_HERE], 4
    ; Calculate backward offset
    pop ebx                    ; Get loop start address
    mov ecx, [VAR_HERE]
    sub ebx, ecx
    sub ebx, 4
    mov eax, [VAR_HERE]
    mov [eax], ebx
    add dword [VAR_HERE], 4
    ; Compile (UNLOOP) offset (where to go when done)
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
    mov dword [eax], code_DOPLOOP
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
    ; The value follows the DOCON cell
    lodsd                      ; Get value
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
    mov eax, [VAR_LATEST]
.loop:
    test eax, eax
    jz .done
    push eax                   ; Save link
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
    NEXT

; SEE - Decompile a word
DEFCODE "SEE", SEE, 0
    call word_
    call find_
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
    pop eax
    ; Skip to CFA
    movzx ebx, byte [eax + 4]
    and ebx, F_LENMASK
    lea eax, [eax + 5 + ebx]
    add eax, 3
    and eax, ~3
    mov ebx, [eax]             ; First cell
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
    NEXT
.notfound:
    mov esi, msg_undefined
    call print_string
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
DEFCODE "S\"", SQUOTE, F_IMMEDIATE
    ; Check state
    mov eax, [VAR_STATE]
    test eax, eax
    jz .interpret
    ; Compile mode: compile (S")
    mov eax, [VAR_HERE]
    mov dword [eax], code_DOSQUOTE
    add dword [VAR_HERE], 4
    ; Copy string until "
    mov edi, [VAR_HERE]
.copy:
    call read_key
    cmp al, '"'
    je .endcopy
    stosb
    jmp .copy
.endcopy:
    mov byte [edi], 0          ; Null terminate
    ; Calculate length
    mov eax, edi
    sub eax, [VAR_HERE]
    ; Store length at start
    mov edi, [VAR_HERE]
    sub edi, 4
    mov [edi], eax
    ; Update HERE (align)
    mov eax, [VAR_HERE]
    add eax, edi
    sub eax, [VAR_HERE]
    add eax, 4
    add eax, 3
    and eax, ~3
    add [VAR_HERE], eax
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
DEFCODE "(S\")", DOSQUOTE, 0
    lodsd                      ; Get length
    push esi                   ; String address
    push eax                   ; Length
    add esi, eax               ; Skip past string
    add esi, 3
    and esi, ~3                ; Align
    NEXT

; ." - Print string
DEFCODE ".\"", DOTQUOTE, F_IMMEDIATE
    ; Compile S" then TYPE
    mov eax, [VAR_HERE]
    mov dword [eax], code_DOSQUOTE
    add dword [VAR_HERE], 4
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
    ; Store length and align
    mov eax, ecx
    mov ebx, [VAR_HERE]
    sub ebx, 4
    mov [ebx], eax
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
DEFCODE "\\", BACKSLASH, F_IMMEDIATE
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
DEFCODE "ALIGN", ALIGN, 0
    mov eax, [VAR_HERE]
    add eax, 3
    and eax, ~3
    mov [VAR_HERE], eax
    NEXT

; MOVE - ( src dst u -- ) Copy u bytes
DEFCODE "MOVE", MOVE, 0
    pop ecx                    ; count
    pop edi                    ; dst
    pop esi                    ; src
    rep movsb
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
; Low-Level Support Routines
; ============================================================================

section .text

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
; print_char - Print character in AL to screen
; ----------------------------------------------------------------------------
print_char:
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
; ----------------------------------------------------------------------------
read_key:
    push ebx
    
    ; Read from keyboard controller
.wait:
    in al, 0x64             ; Read status
    test al, 1              ; Data available?
    jz .wait
    
    in al, 0x60             ; Read scancode
    
    ; Convert scancode to ASCII (simplified)
    cmp al, 0x80            ; Key release?
    jge .wait
    
    mov ebx, eax
    mov al, [scancode_to_ascii + ebx]
    test al, al
    jz .wait
    
    pop ebx
    ret

; ============================================================================
; Interpreter Routines
; ============================================================================

; ----------------------------------------------------------------------------
; interpret_ - Main interpret loop
; ----------------------------------------------------------------------------
interpret_:
    push ebx
    push ecx
    push edx
    push edi
    push esi

.loop:
    ; Read line if needed
    cmp dword [VAR_TOIN], 0
    jne .have_input
    
    ; Prompt
    mov al, 'o'
    call print_char
    mov al, 'k'
    call print_char
    mov al, ' '
    call print_char
    
    ; Read line
    call read_line
    mov dword [VAR_TOIN], 0
    
.have_input:
    ; Get next word
    call word_
    test eax, eax
    jz .loop                ; Empty word, try again
    
    mov esi, eax            ; Save word address
    
    ; Try to find it
    call find_
    test eax, eax
    jz .try_number
    
    ; Found word
    mov ebx, eax            ; Save XT
    
    ; Check if immediate or compiling
    mov cl, [eax - 4]       ; Get flags+length
    mov edx, [VAR_STATE]
    test edx, edx
    jz .execute_word        ; Interpreting - always execute
    
    test cl, F_IMMEDIATE    ; Compiling - check immediate
    jnz .execute_word
    
    ; Compile the word
    mov eax, ebx
    call comma_
    jmp .loop
    
.execute_word:
    mov eax, ebx
    jmp [eax]               ; Execute it
    
.try_number:
    ; Try parsing as number
    call number_
    test edx, edx           ; EDX = 0 if success
    jnz .undefined
    
    ; Got a number
    mov edx, [VAR_STATE]
    test edx, edx
    jz .push_number
    
    ; Compile LIT + number
    push eax
    mov eax, LIT
    call comma_
    pop eax
    call comma_
    jmp .loop
    
.push_number:
    push eax
    jmp .loop
    
.undefined:
    mov esi, msg_undefined
    call print_string
    mov dword [VAR_STATE], 0  ; Reset state
    jmp .loop

.done:
    pop esi
    pop edi
    pop edx
    pop ecx
    pop ebx
    ret

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
    
    stosb
    inc ecx
    cmp ecx, 31             ; Max word length
    jl .copy_word
    
.end_word:
    mov byte [edi], 0       ; Null terminate
    
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
; find_ - Find word in dictionary, return XT in EAX (0 if not found)
; Input: word in word_buffer
; ----------------------------------------------------------------------------
find_:
    push ebx
    push ecx
    push edx
    push edi
    push esi
    
    ; Get word length
    mov esi, word_buffer
    xor ecx, ecx
.len_loop:
    lodsb
    test al, al
    jz .got_len
    inc ecx
    jmp .len_loop
.got_len:
    
    ; Search dictionary
    mov ebx, [VAR_LATEST]
    
.search_loop:
    test ebx, ebx
    jz .not_found
    
    ; Get flags+length
    mov al, [ebx + 4]
    and eax, F_LENMASK
    
    ; Compare length
    cmp eax, ecx
    jne .next_word
    
    ; Compare names
    lea esi, [ebx + 5]      ; Name in dictionary
    mov edi, word_buffer
    push ecx
    repe cmpsb
    pop ecx
    jne .next_word
    
    ; Found! Calculate XT (skip to code field)
    lea eax, [ebx + 5]      ; Start of name
    add eax, ecx            ; Add name length
    add eax, 3              ; Round up
    and eax, ~3             ; Align to 4 bytes
    
    pop esi
    pop edi
    pop edx
    pop ecx
    pop ebx
    ret
    
.next_word:
    mov ebx, [ebx]          ; Follow link
    jmp .search_loop
    
.not_found:
    xor eax, eax
    pop esi
    pop edi
    pop edx
    pop ecx
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
    push ecx
    push edi
    push esi
    
    mov edi, [VAR_HERE]
    
    ; Write link
    mov eax, [VAR_LATEST]
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
    
    ; Update LATEST and HERE
    mov eax, [VAR_HERE]
    mov [VAR_LATEST], eax
    mov [VAR_HERE], edi
    
    pop esi
    pop edi
    pop ecx
    pop eax
    ret

; ----------------------------------------------------------------------------
; read_line - Read a line of input into TIB
; ----------------------------------------------------------------------------
read_line:
    push ebx
    push ecx
    push edi
    
    mov edi, TIB_START
    xor ecx, ecx
    
.loop:
    call read_key
    
    cmp al, 13              ; Enter
    je .done
    cmp al, 8               ; Backspace
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
; Cold Start Word List
; ============================================================================

section .data

cold_start:
    dd INTERPRET
    dd BRANCH
    dd -8                   ; Loop back to INTERPRET

; ============================================================================
; Data
; ============================================================================

cursor_x:       dd 0
cursor_y:       dd 0

msg_welcome:    db 'Bare-Metal Forth v0.1 - Ship Builders System', 13, 10
                db 'Type WORDS to see available commands', 13, 10, 0
msg_stack:      db '<', 0
msg_undefined:  db '? ', 0
see_msg:        db 'SEE: ', 0
primitive_msg:  db '<primitive>', 0

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

; Pad to align
times 0x4000 - ($ - $$) db 0
