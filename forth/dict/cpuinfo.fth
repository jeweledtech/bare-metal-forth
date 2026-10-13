\ ============================================
\ CATALOG: CPUINFO
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ ============================================
\
\ Read-only: what the processor says about
\ itself, through the kernel's CPUID
\ ( leaf subleaf -- eax ebx ecx edx ).
\ HAL phase 0: docs/TASK_HAL_DISCOVERY.md.
\ (Named CPUINFO: a vocabulary CPUID would
\ shadow the kernel word.)
\
\   CPU-VENDOR.    leaf 0
\   CPU-FEATURES.  leaf 1: named bits, 1/0
\   CPU-BRAND.     80000002-80000004
\ ============================================

VOCABULARY CPUINFO
CPUINFO DEFINITIONS
HEX

CREATE CV-BUF 30 ALLOT

: CPU-VENDOR. ( -- )
    0 0 CPUID
    SWAP CV-BUF 8 + ! CV-BUF 4 + !
    CV-BUF ! DROP
    ." Vendor: " CV-BUF 0C TYPE CR ;

: .BIT ( reg bit -- reg )
    OVER SWAP RSHIFT 1 AND . ;

\ EDX: FPU 0, TSC 4, MSR 5, PAE 6, APIC 9,
\ SSE 25, SSE2 26. ECX: SSE3 0, X2APIC 21,
\ AVX 28, HYPERVISOR 31 (decimal bits).
: CPU-FEATURES. ( -- )
    1 0 CPUID >R >R 2DROP R> R>
    ." FPU " 0 .BIT ." TSC " 4 .BIT
    ." MSR " 5 .BIT ." PAE " 6 .BIT
    ." APIC " 9 .BIT ." SSE " 19 .BIT
    ." SSE2 " 1A .BIT DROP
    ." SSE3 " 0 .BIT ." X2APIC " 15 .BIT
    ." AVX " 1C .BIT
    ." HYPERVISOR " 1F .BIT DROP CR ;

: CB! ( a b c d off -- )
    CV-BUF + >R R@ 0C + ! R@ 8 + !
    R@ 4 + ! R> ! ;

: CPU-BRAND. ( -- )
    80000000 0 CPUID 2DROP DROP
    DUP 80000000 AND 0= IF
        DROP ." Brand: none" CR EXIT
    THEN
    80000004 - 0< IF
        ." Brand: none" CR EXIT
    THEN
    80000002 0 CPUID 0 CB!
    80000003 0 CPUID 10 CB!
    80000004 0 CPUID 20 CB!
    ." Brand: " CV-BUF 30 TYPE CR ;

ONLY FORTH DEFINITIONS
DECIMAL
