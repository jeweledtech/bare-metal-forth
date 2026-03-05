\ ============================================
\ CATALOG: PS2-MOUSE
\ CATEGORY: input
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0x60, 0x64
\ IRQ: 12
\ CONFIDENCE: high
\ ============================================
\
\ PS/2 mouse driver using i8042 aux port.
\ Kernel ISR (IRQ12) assembles 3-byte packets
\ and updates mouse_x, mouse_y, mouse_btn.
\ This vocabulary provides init and read API.
\
\ Usage:
\   USING PS2-MOUSE
\   MOUSE-INIT
\   MOUSE-XY ( -- x y )
\   MOUSE-BUTTONS ( -- mask )
\
\ ============================================

VOCABULARY PS2-MOUSE
PS2-MOUSE DEFINITIONS
HEX

\ ---- i8042 Port Constants ----
60 CONSTANT M-DATA
64 CONSTANT M-STATUS
64 CONSTANT M-CMD

\ ---- Status Bits ----
02 CONSTANT M-IBF
01 CONSTANT M-OBF

\ ---- Mouse Commands ----
D4 CONSTANT AUX-WRITE
A8 CONSTANT AUX-ENABLE
FF CONSTANT M-RESET
F4 CONSTANT M-ENABLE-DATA
F3 CONSTANT M-SET-RATE

\ ---- Bounds ----
VARIABLE MOUSE-XMAX
VARIABLE MOUSE-YMAX

\ ---- i8042 Helpers ----
: M-WAIT-IN ( -- )
    BEGIN M-STATUS INB M-IBF AND
    0= UNTIL
;

: M-WAIT-OUT ( -- )
    BEGIN M-STATUS INB M-OBF AND
    UNTIL
;

\ Send byte to mouse via aux channel
: M-SEND ( byte -- )
    AUX-WRITE M-CMD OUTB
    M-WAIT-IN
    M-DATA OUTB
    M-WAIT-OUT
    M-DATA INB DROP
;

\ ---- Public API ----
\ Read from kernel ISR variables
: MOUSE-XY ( -- x y )
    MOUSE-X-VAR @ MOUSE-Y-VAR @
;

: MOUSE-BUTTONS ( -- mask )
    MOUSE-BTN-VAR @
;

: MOUSE-PKT? ( -- flag )
    MOUSE-PKT-READY @ 0<>
;

: MOUSE-ACK ( -- )
    0 MOUSE-PKT-READY !
;

: MOUSE-BOUNDS! ( xmax ymax -- )
    MOUSE-YMAX ! MOUSE-XMAX !
;

\ ---- Initialize mouse ----
: MOUSE-INIT ( -- )
    DECIMAL
    640 MOUSE-XMAX !
    480 MOUSE-YMAX !
    HEX
    AUX-ENABLE M-CMD OUTB
    M-WAIT-IN
    M-ENABLE-DATA M-SEND
    0 MOUSE-X-VAR !
    0 MOUSE-Y-VAR !
    0 MOUSE-BTN-VAR !
    0 MOUSE-PKT-READY !
    DECIMAL 12 HEX IRQ-UNMASK
;

FORTH DEFINITIONS
DECIMAL
