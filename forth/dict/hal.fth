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
\ Body: binding cell address, header, next
\ vector XT, own cell. The binding cell is
\ the vector's own, or an existing one
\ (HAL-VECTOR-AT).
: HAL-SET ( xt vxt -- ) >BODY @ ! ;
: HAL-GET ( vxt -- xt ) >BODY @ @ ;
: BIND ( xt "name" -- ) ' HAL-SET ;

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

\ ---- Block contract (slice 2) ----
\ BLK-WRITE ( buf-addr blk# -- ior )
\ BLK-READ  ( buf-addr blk# -- ior )
\ ior 0 = success. Over the kernel's own
\ cells: BLK-WRITER! / BLK-READER! and
\ BIND write the same cell. Bound at boot
\ by the kernel (ATA, or the fail-closed
\ NONE words on memdisk and UEFI); AHCI-RW
\ rebinds them on the HP.
BLK-WRITE-CELL HAL-VECTOR-AT BLK-WRITE
BLK-READ-CELL HAL-VECTOR-AT BLK-READ

\ ---- Network contract ----
\ NET-SEND ( addr len -- ior ) one
\ Ethernet frame: destination, source,
\ type, payload, no FCS; len 14 to 1514,
\ shorter than 60 goes out zero-padded.
\ ior 0 = handed to the card (and sent,
\ where the card says so), 1 = refused or
\ failed. Unbound until a NIC driver's
\ init finds its card (RTL8168, NE2000).
HAL-VECTOR NET-SEND
: NET-LEN-OK? ( len -- flag )
    DUP 0E < 0= SWAP 5EA > 0= AND ;

ONLY FORTH DEFINITIONS
DECIMAL
