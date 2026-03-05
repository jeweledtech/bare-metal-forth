\ ============================================
\ CATALOG: PS2-KEYBOARD
\ CATEGORY: input
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0x60, 0x64
\ IRQ: 1
\ CONFIDENCE: high
\ ============================================
\
\ PS/2 Keyboard driver for i8042 controller.
\ Reads scancodes from kernel IRQ1 ring
\ buffer. US keyboard layout with shift,
\ ctrl, alt modifier tracking.
\
\ Usage:
\   USING PS2-KEYBOARD
\   KB-INIT
\   KB-KEY .
\
\ ============================================

VOCABULARY PS2-KEYBOARD
PS2-KEYBOARD DEFINITIONS
HEX

\ ---- i8042 Port Constants ----
60 CONSTANT KB-DATA
64 CONSTANT KB-STATUS-PORT
64 CONSTANT KB-CMD

\ ---- Status Bits ----
01 CONSTANT KB-OBF
02 CONSTANT KB-IBF

\ ---- Commands ----
AE CONSTANT KB-ENABLE-CMD
AD CONSTANT KB-DISABLE-CMD
ED CONSTANT KB-SET-LEDS

\ ---- Modifier State ----
\ bit0=shift bit1=ctrl bit2=alt
VARIABLE KB-MODS

\ ---- i8042 Helpers ----
: KB-STATUS ( -- byte )
    KB-STATUS-PORT INB
;

: KB-WAIT-INPUT ( -- )
    BEGIN KB-STATUS-PORT INB
    KB-IBF AND 0= UNTIL
;

: KB-WAIT-OUTPUT ( -- )
    BEGIN KB-STATUS-PORT INB
    KB-OBF AND UNTIL
;

: KB-SEND ( byte -- )
    KB-WAIT-INPUT KB-DATA OUTB
;

\ ---- Ring Buffer Access ----
: KB-KEY? ( -- flag )
    KB-RING-COUNT @ 0<>
;

: KB-SCAN ( -- scancode )
    KB-RING-COUNT @ 0=
    IF 0 EXIT THEN
    KB-RING-TAIL @
    KB-RING-BUF + C@
    KB-RING-TAIL @ 1+ F AND
    KB-RING-TAIL !
    KB-RING-COUNT @ 1-
    KB-RING-COUNT !
;

\ ---- Scancode-to-ASCII Tables ----
\ US layout, set 1, codes 00-39 hex
\ 58 entries (3A bytes)

CREATE KB-MAP
\ 00: NUL  01: ESC
 0 C, 1B C,
\ 02-0B: 1 2 3 4 5 6 7 8 9 0
 31 C, 32 C, 33 C, 34 C,
 35 C, 36 C, 37 C, 38 C,
 39 C, 30 C,
\ 0C: -  0D: =  0E: BS  0F: TAB
 2D C, 3D C, 08 C, 09 C,
\ 10: q w e r t y u i o p [ ]
 71 C, 77 C, 65 C, 72 C,
 74 C, 79 C, 75 C, 69 C,
 6F C, 70 C, 5B C, 5D C,
\ 1C: Enter  1D: Ctrl(0)
 0D C,  0 C,
\ 1E: a s d f g h j k l ; ' `
 61 C, 73 C, 64 C, 66 C,
 67 C, 68 C, 6A C, 6B C,
 6C C, 3B C, 27 C, 60 C,
\ 2A: LShift(0)  2B: backslash
  0 C, 5C C,
\ 2C: z x c v b n m , . /
 7A C, 78 C, 63 C, 76 C,
 62 C, 6E C, 6D C, 2C C,
 2E C, 2F C,
\ 36: RShift(0) 37: kp* 38: Alt(0)
  0 C,  0 C,  0 C,
\ 39: Space
 20 C,

CREATE KB-SHIFT-MAP
\ 00: NUL  01: ESC
 0 C, 1B C,
\ 02-0B: ! @ # $ % ^ & * ( )
 21 C, 40 C, 23 C, 24 C,
 25 C, 5E C, 26 C, 2A C,
 28 C, 29 C,
\ 0C: _  0D: +  0E: BS  0F: TAB
 5F C, 2B C, 08 C, 09 C,
\ 10: Q W E R T Y U I O P { }
 51 C, 57 C, 45 C, 52 C,
 54 C, 59 C, 55 C, 49 C,
 4F C, 50 C, 7B C, 7D C,
\ 1C: Enter  1D: Ctrl(0)
 0D C,  0 C,
\ 1E: A S D F G H J K L : " ~
 41 C, 53 C, 44 C, 46 C,
 47 C, 48 C, 4A C, 4B C,
 4C C, 3A C, 22 C, 7E C,
\ 2A: LShift(0)  2B: pipe
  0 C, 7C C,
\ 2C: Z X C V B N M < > ?
 5A C, 58 C, 43 C, 56 C,
 42 C, 4E C, 4D C, 3C C,
 3E C, 3F C,
\ 36: RShift(0) 37: kp* 38: Alt(0)
  0 C,  0 C,  0 C,
\ 39: Space
 20 C,

\ ---- Translate Scancode to ASCII ----
: KB-TRANSLATE ( scan -- char )
    DUP 3A < 0= IF DROP 0 EXIT THEN
    KB-MODS @ 1 AND IF
        KB-SHIFT-MAP + C@
    ELSE
        KB-MAP + C@
    THEN
;

\ ---- Update Modifier State ----
: KB-UPDATE-MODS ( scan -- )
    DUP 2A = OVER 36 = OR IF
        KB-MODS @ 1 OR KB-MODS !
        DROP EXIT
    THEN
    DUP 0AA = OVER 0B6 = OR IF
        KB-MODS @ 1 INVERT AND
        KB-MODS ! DROP EXIT
    THEN
    DUP 1D = IF
        KB-MODS @ 2 OR KB-MODS !
        DROP EXIT
    THEN
    DUP 9D = IF
        KB-MODS @ 2 INVERT AND
        KB-MODS ! DROP EXIT
    THEN
    DUP 38 = IF
        KB-MODS @ 4 OR KB-MODS !
        DROP EXIT
    THEN
    DUP 0B8 = IF
        KB-MODS @ 4 INVERT AND
        KB-MODS ! DROP EXIT
    THEN
    DROP
;

\ ---- Blocking Key Read ----
: KB-KEY ( -- char )
    BEGIN
        KB-KEY? 0= IF 0 THEN
        KB-KEY? IF
            KB-SCAN
            DUP KB-UPDATE-MODS
            DUP 80 AND IF
                DROP 0
            ELSE
                KB-TRANSLATE
            THEN
            DUP 0<> IF EXIT THEN
            DROP
        THEN
    AGAIN
;

\ ---- LED Control ----
: KB-LED! ( mask -- )
    KB-SET-LEDS KB-SEND
    KB-WAIT-OUTPUT DROP
    KB-SEND
;

\ ---- Initialization ----
: KB-INIT ( -- )
    0 KB-MODS !
    KB-ENABLE-CMD KB-CMD OUTB
    1 IRQ-UNMASK
;

FORTH DEFINITIONS
DECIMAL
