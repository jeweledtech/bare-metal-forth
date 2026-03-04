\ ============================================
\ CATALOG: PIT-TIMER
\ CATEGORY: timer
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0x40-0x43
\ IRQ: 0
\ CONFIDENCE: high
\ ============================================
\
\ Intel 8254 Programmable Interval Timer.
\ Channel 0 connected to IRQ0 for system
\ tick. Uses kernel INB/OUTB and
\ TICK-COUNT/IRQ-UNMASK.
\
\ Usage:
\   USING PIT-TIMER
\   HEX 64 PIT-INIT
\   TICK-COUNT @ .
\   DECIMAL 100 MS-WAIT
\
\ ============================================

VOCABULARY PIT-TIMER
PIT-TIMER DEFINITIONS
HEX

\ ---- PIT Port Constants ----
40 CONSTANT PIT-CH0
42 CONSTANT PIT-CH2
43 CONSTANT PIT-CMD

\ ---- PIT Command Values ----
\ Ch0, lo/hi byte, rate generator mode 2
34 CONSTANT PIT-MODE2-CH0

\ ---- PIT Oscillator Frequency ----
\ 1193182 Hz = 12h 34DEh
DECIMAL
1193182 CONSTANT PIT-FREQ
HEX

\ ---- Tick rate storage ----
VARIABLE TICKS/SEC

\ ---- PIT Initialization ----
\ Program Ch0 to desired frequency.
\ Sends command byte FIRST, then
\ low byte, then high byte of divisor.
\ Finally unmasks IRQ0 for ticks.
: PIT-INIT ( hz -- )
    DUP TICKS/SEC !
    PIT-FREQ SWAP /
    PIT-MODE2-CH0 PIT-CMD OUTB
    DUP FF AND PIT-CH0 OUTB
    8 RSHIFT FF AND PIT-CH0 OUTB
    0 IRQ-UNMASK
;

\ ---- Read PIT counter ----
\ Latch Ch0, read lo then hi byte.
: PIT-READ ( -- count )
    0 PIT-CMD OUTB
    PIT-CH0 INB
    PIT-CH0 INB 8 LSHIFT OR
;

\ ---- Millisecond wait via ticks ----
\ Computes target tick count, then
\ busy-waits until TICK-COUNT reaches
\ or passes the target.
: MS-WAIT ( ms -- )
    TICKS/SEC @ * 3E8 /
    TICK-COUNT @ +
    BEGIN DUP TICK-COUNT @ <= UNTIL
    DROP
;

FORTH DEFINITIONS
DECIMAL
