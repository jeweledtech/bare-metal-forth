; ============================================================================
; Forth-83 Floored Division Primitives for Bare-Metal Forth Kernel
; ============================================================================
;
; These are the assembly-language words that implement Forth-83's floored
; division semantics. Each architecture section is self-contained.
;
; Forth-83 Division Words:
;   /      ( n1 n2 -- quotient )      Floored quotient
;   MOD    ( n1 n2 -- remainder )     Floored remainder  
;   /MOD   ( n1 n2 -- remainder quotient )  Both values
;   */     ( n1 n2 n3 -- n1*n2/n3 )   Scaled with intermediate double
;   */MOD  ( n1 n2 n3 -- remainder quotient )  Scaled with both
;
; The key insight: when dividend and divisor have opposite signs AND
; remainder is non-zero, we must adjust:
;   quotient  -= 1
;   remainder += divisor
;
; Copyright (c) 2026 Jolly Genius Inc.
; Ship's Systems Software
; ============================================================================

; ============================================================================
; ARCHITECTURE DETECTION
; ============================================================================

%ifdef __x86_64__
    %define ARCH_X64 1
%elifdef __aarch64__
    %define ARCH_ARM64 1
%elifdef __riscv
    %define ARCH_RISCV 1
%else
    ; Default to x86 32-bit for bare metal boot
    %define ARCH_X86 1
%endif

; ============================================================================
; x86 32-bit (Bare-Metal Forth)
; ============================================================================
%ifdef ARCH_X86

[BITS 32]

; Register conventions (from your kernel):
;   ESP - Data stack pointer
;   EBP - Return stack pointer  
;   ESI - Forth instruction pointer
;   EAX - Working register

; ----------------------------------------------------------------------------
; /  ( n1 n2 -- quotient )  Floored division
; ----------------------------------------------------------------------------
DEFWORD "/", 1, SLASH, 0
    ; Stack: n2 on top, n1 below
    pop     ebx             ; ebx = n2 (divisor)
    pop     eax             ; eax = n1 (dividend)
    
    ; Save original dividend sign for comparison
    mov     ecx, eax
    xor     ecx, ebx        ; ecx = sign comparison (negative if different signs)
    
    ; Perform signed division
    cdq                     ; Sign-extend EAX into EDX:EAX
    idiv    ebx             ; EAX = quotient, EDX = remainder
    
    ; Check if correction needed:
    ; If remainder != 0 AND signs were different
    test    edx, edx
    jz      .slash_done     ; remainder == 0, no correction
    test    ecx, ecx
    jns     .slash_done     ; same signs (sign bit clear), no correction
    
    ; Apply correction
    dec     eax             ; quotient -= 1
    
.slash_done:
    push    eax             ; Push quotient
    NEXT

; ----------------------------------------------------------------------------
; MOD  ( n1 n2 -- remainder )  Floored modulo
; ----------------------------------------------------------------------------
DEFWORD "MOD", 3, MOD, 0
    pop     ebx             ; ebx = n2 (divisor)
    pop     eax             ; eax = n1 (dividend)
    
    mov     ecx, eax
    xor     ecx, ebx        ; Sign comparison
    
    cdq
    idiv    ebx             ; EDX = remainder
    
    test    edx, edx
    jz      .mod_done
    test    ecx, ecx
    jns     .mod_done
    
    ; Apply correction
    add     edx, ebx        ; remainder += divisor
    
.mod_done:
    push    edx             ; Push remainder
    NEXT

; ----------------------------------------------------------------------------
; /MOD  ( n1 n2 -- remainder quotient )  Both values
; ----------------------------------------------------------------------------
DEFWORD "/MOD", 4, SLASHMOD, 0
    pop     ebx             ; ebx = n2 (divisor)
    pop     eax             ; eax = n1 (dividend)
    
    mov     ecx, eax
    xor     ecx, ebx        ; Sign comparison
    
    cdq
    idiv    ebx             ; EAX = quotient, EDX = remainder
    
    test    edx, edx
    jz      .slashmod_done
    test    ecx, ecx
    jns     .slashmod_done
    
    ; Apply correction to both
    dec     eax             ; quotient -= 1
    add     edx, ebx        ; remainder += divisor
    
.slashmod_done:
    push    edx             ; Push remainder (below)
    push    eax             ; Push quotient (on top)
    NEXT

; ----------------------------------------------------------------------------
; */  ( n1 n2 n3 -- n1*n2/n3 )  Scaled floored division
; Uses 64-bit intermediate to avoid overflow
; ----------------------------------------------------------------------------
DEFWORD "*/", 2, STARSLASH, 0
    pop     ecx             ; ecx = n3 (divisor)
    pop     ebx             ; ebx = n2
    pop     eax             ; eax = n1
    
    ; EDX:EAX = n1 * n2 (signed)
    imul    ebx             ; 64-bit result in EDX:EAX
    
    ; Save sign for correction
    mov     edi, edx        ; Save high word for sign
    xor     edi, ecx        ; Compare with divisor sign
    
    ; Signed divide EDX:EAX by ECX
    idiv    ecx             ; EAX = quotient, EDX = remainder
    
    ; Check for correction
    test    edx, edx
    jz      .starslash_done
    test    edi, edi
    jns     .starslash_done
    
    dec     eax             ; quotient -= 1
    
.starslash_done:
    push    eax
    NEXT

; ----------------------------------------------------------------------------
; */MOD  ( n1 n2 n3 -- remainder quotient )  Scaled with both values
; ----------------------------------------------------------------------------
DEFWORD "*/MOD", 5, STARSLASHMOD, 0
    pop     ecx             ; ecx = n3 (divisor)
    pop     ebx             ; ebx = n2
    pop     eax             ; eax = n1
    
    imul    ebx             ; EDX:EAX = n1 * n2
    
    mov     edi, edx
    xor     edi, ecx
    
    idiv    ecx
    
    test    edx, edx
    jz      .starslashmod_done
    test    edi, edi
    jns     .starslashmod_done
    
    dec     eax
    add     edx, ecx
    
.starslashmod_done:
    push    edx             ; remainder
    push    eax             ; quotient
    NEXT

%endif ; ARCH_X86

; ============================================================================
; x86-64 (64-bit Forth)
; ============================================================================
%ifdef ARCH_X64

[BITS 64]

; Register conventions for 64-bit:
;   RSP - Data stack
;   RBP - Return stack
;   RSI - Forth IP
;   RAX - TOS (top of stack) cache

; ----------------------------------------------------------------------------
; /  ( n1 n2 -- quotient )  Floored division 64-bit
; ----------------------------------------------------------------------------
DEFWORD_64 "/", 1, SLASH, 0
    pop     rbx             ; rbx = divisor
    pop     rax             ; rax = dividend
    
    mov     rcx, rax
    xor     rcx, rbx        ; Sign comparison
    
    cqo                     ; Sign-extend RAX into RDX:RAX
    idiv    rbx             ; RAX = quotient, RDX = remainder
    
    test    rdx, rdx
    jz      .slash64_done
    test    rcx, rcx
    jns     .slash64_done
    
    dec     rax
    
.slash64_done:
    push    rax
    NEXT

; ----------------------------------------------------------------------------
; MOD  ( n1 n2 -- remainder )
; ----------------------------------------------------------------------------
DEFWORD_64 "MOD", 3, MOD, 0
    pop     rbx
    pop     rax
    
    mov     rcx, rax
    xor     rcx, rbx
    
    cqo
    idiv    rbx
    
    test    rdx, rdx
    jz      .mod64_done
    test    rcx, rcx
    jns     .mod64_done
    
    add     rdx, rbx
    
.mod64_done:
    push    rdx
    NEXT

; ----------------------------------------------------------------------------
; /MOD  ( n1 n2 -- remainder quotient )
; ----------------------------------------------------------------------------
DEFWORD_64 "/MOD", 4, SLASHMOD, 0
    pop     rbx
    pop     rax
    
    mov     rcx, rax
    xor     rcx, rbx
    
    cqo
    idiv    rbx
    
    test    rdx, rdx
    jz      .slashmod64_done
    test    rcx, rcx
    jns     .slashmod64_done
    
    dec     rax
    add     rdx, rbx
    
.slashmod64_done:
    push    rdx
    push    rax
    NEXT

%endif ; ARCH_X64

; ============================================================================
; ARM64 (AArch64)
; ============================================================================
%ifdef ARCH_ARM64

; Register conventions:
;   SP  - Data stack
;   X28 - Return stack pointer
;   X27 - Forth IP
;   X0  - Working register / TOS cache

; ----------------------------------------------------------------------------
; /  ( n1 n2 -- quotient )
; ----------------------------------------------------------------------------
    .global forth_slash
forth_slash:
    ldp     x0, x1, [sp], #16   // Pop n1 (x0) and n2 (x1)
    
    eor     x4, x0, x1          // x4 = sign comparison
    
    sdiv    x2, x0, x1          // x2 = quotient (symmetric)
    msub    x3, x2, x1, x0      // x3 = remainder = n1 - q*n2
    
    cbz     x3, 1f              // if remainder == 0, done
    tbz     x4, #63, 1f         // if same signs, done
    
    sub     x2, x2, #1          // quotient -= 1
    
1:  str     x2, [sp, #-8]!      // Push quotient
    b       forth_next

; ----------------------------------------------------------------------------
; MOD  ( n1 n2 -- remainder )
; ----------------------------------------------------------------------------
    .global forth_mod
forth_mod:
    ldp     x0, x1, [sp], #16
    
    eor     x4, x0, x1
    
    sdiv    x2, x0, x1
    msub    x3, x2, x1, x0      // x3 = remainder
    
    cbz     x3, 1f
    tbz     x4, #63, 1f
    
    add     x3, x3, x1          // remainder += divisor
    
1:  str     x3, [sp, #-8]!
    b       forth_next

; ----------------------------------------------------------------------------
; /MOD  ( n1 n2 -- remainder quotient )
; ----------------------------------------------------------------------------
    .global forth_slashmod
forth_slashmod:
    ldp     x0, x1, [sp], #16
    
    eor     x4, x0, x1
    
    sdiv    x2, x0, x1
    msub    x3, x2, x1, x0
    
    cbz     x3, 1f
    tbz     x4, #63, 1f
    
    sub     x2, x2, #1
    add     x3, x3, x1
    
1:  stp     x3, x2, [sp, #-16]! // Push remainder then quotient
    b       forth_next

%endif ; ARCH_ARM64

; ============================================================================
; RISC-V 64-bit (RV64IM)
; ============================================================================
%ifdef ARCH_RISCV

; Register conventions:
;   sp  - Data stack
;   s0  - Return stack pointer
;   s1  - Forth IP
;   a0-a7 - Working registers

; ----------------------------------------------------------------------------
; /  ( n1 n2 -- quotient )
; ----------------------------------------------------------------------------
    .global forth_slash
forth_slash:
    ld      a0, 8(sp)           # a0 = n1 (dividend)
    ld      a1, 0(sp)           # a1 = n2 (divisor)
    addi    sp, sp, 16
    
    xor     t2, a0, a1          # t2 = sign comparison
    
    div     t0, a0, a1          # t0 = quotient (symmetric)
    rem     t1, a0, a1          # t1 = remainder
    
    beqz    t1, 1f              # if remainder == 0, done
    bgez    t2, 1f              # if same signs, done
    
    addi    t0, t0, -1          # quotient -= 1
    
1:  addi    sp, sp, -8
    sd      t0, 0(sp)           # Push quotient
    j       forth_next

; ----------------------------------------------------------------------------
; MOD  ( n1 n2 -- remainder )
; ----------------------------------------------------------------------------
    .global forth_mod
forth_mod:
    ld      a0, 8(sp)
    ld      a1, 0(sp)
    addi    sp, sp, 16
    
    xor     t2, a0, a1
    
    div     t0, a0, a1
    rem     t1, a0, a1
    
    beqz    t1, 1f
    bgez    t2, 1f
    
    add     t1, t1, a1          # remainder += divisor
    
1:  addi    sp, sp, -8
    sd      t1, 0(sp)
    j       forth_next

; ----------------------------------------------------------------------------
; /MOD  ( n1 n2 -- remainder quotient )
; ----------------------------------------------------------------------------
    .global forth_slashmod
forth_slashmod:
    ld      a0, 8(sp)
    ld      a1, 0(sp)
    addi    sp, sp, 16
    
    xor     t2, a0, a1
    
    div     t0, a0, a1
    rem     t1, a0, a1
    
    beqz    t1, 1f
    bgez    t2, 1f
    
    addi    t0, t0, -1
    add     t1, t1, a1
    
1:  addi    sp, sp, -16
    sd      t1, 8(sp)           # remainder (below)
    sd      t0, 0(sp)           # quotient (on top)
    j       forth_next

%endif ; ARCH_RISCV

; ============================================================================
; End of Architecture-Specific Code
; ============================================================================
