\ ============================================
\ CATALOG: HAL
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ ============================================
\
\ The binding layer: one name per device
\ contract, and which driver answers it on
\ this machine is a cell you can change at
\ the ok prompt. Nothing is mediated: @ !
\ C@ C! INB OUTB still reach any address or
\ port directly. Kernel: HAL-VECTOR (DOVEC)
\ and HAL-HEAD. docs/TASK_HAL_DISPLAY.md.
\
\   ' NEW-WORD BIND FB-BASE   live rebind
\   HAL-LIST                  every vector
\ ============================================

VOCABULARY HAL
HAL DEFINITIONS
HEX

\ ---- Binding ----
\ A vector's XT, >BODY = its bound-XT cell.
: HAL-SET ( xt vxt -- ) >BODY ! ;
: HAL-GET ( vxt -- xt ) >BODY @ ;
: BIND ( xt "name" -- ) ' HAL-SET ;

\ Body: bound xt, header, next vector XT.
: HAL-NAME ( vxt -- addr len )
    >BODY 4 + @ DUP 5 + SWAP 4 + C@ 3F AND ;
: HAL-NEXT ( vxt -- vxt' | 0 ) >BODY 8 + @ ;

: HAL-LIST ( -- )
    HAL-HEAD @
    BEGIN ?DUP WHILE
        DUP HAL-NAME TYPE SPACE ." ->" SPACE
        DUP HAL-GET ?DUP IF
            BASE @ SWAP HEX U. BASE !
        ELSE ." unbound" THEN CR
        HAL-NEXT
    REPEAT ;

\ ---- Display contract ----
\ FB-BASE  ( -- addr )  the text screen
\                       memory, 80x25 cells
\ FB-FLUSH ( -- )       make the screen
\                       show it
HAL-VECTOR FB-BASE
HAL-VECTOR FB-FLUSH

\ BIOS: VGA text mode.
: FB-BASE-VGA ( -- addr ) B8000 ;
: FB-FLUSH-VGA ( -- ) ;
\ UEFI: the kernel's text shadow, drawn
\ on the framebuffer.
: FB-BASE-SHADOW ( -- addr ) SCREEN ;
: FB-FLUSH-SHADOW ( -- ) SCREEN-FLUSH ;

\ Chosen from BOOT-MODE: UEFI (3) with the
\ framebuffer console on uses the shadow;
\ anything else, VGA text.
: HAL-BIND-DISPLAY ( -- )
    BOOT-MODE 3 = SCREEN B8000 <> AND IF
        ['] FB-BASE-SHADOW ['] FB-FLUSH-SHADOW
    ELSE
        ['] FB-BASE-VGA ['] FB-FLUSH-VGA
    THEN
    ['] FB-FLUSH HAL-SET ['] FB-BASE HAL-SET ;
HAL-BIND-DISPLAY

ONLY FORTH DEFINITIONS
DECIMAL
