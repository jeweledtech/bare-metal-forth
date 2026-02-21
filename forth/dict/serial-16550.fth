\ ====================================================================
\ CATALOG: SERIAL-16550
\ CATEGORY: serial
\ SOURCE: hand-written
\ SOURCE-BINARY: none
\ VENDOR-ID: none
\ DEVICE-ID: none
\ PORTS: 0x3F8-0x3FF
\ MMIO: none
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( C@-PORT C!-PORT )
\ ====================================================================
\
\ 16550 UART driver vocabulary — hand-written from the National
\ Semiconductor 16550 datasheet.  Serves as the "known good"
\ reference that the extraction pipeline's output is compared against.
\
\ The 16550 is the de facto standard PC serial port controller.
\ Register offsets below apply to any 16550-compatible UART
\ (COM1 at 0x3F8, COM2 at 0x2F8, etc.).
\
\ Usage:
\   USING SERIAL-16550
\   HEX 3F8 UART-INIT          \ Init COM1 at 115200 baud
\   42 UART-EMIT                \ Send 'B'
\   UART-KEY                    \ Wait for and receive a character
\
\ ====================================================================

VOCABULARY SERIAL-16550
SERIAL-16550 DEFINITIONS
HEX

\ ---- Register Offsets (from 16550 datasheet) ----
00 CONSTANT RBR     \ Receive Buffer Register (read, DLAB=0)
00 CONSTANT THR     \ Transmit Holding Register (write, DLAB=0)
00 CONSTANT DLL     \ Divisor Latch Low (DLAB=1)
01 CONSTANT IER     \ Interrupt Enable Register (DLAB=0)
01 CONSTANT DLM     \ Divisor Latch High (DLAB=1)
02 CONSTANT IIR     \ Interrupt Identification Register (read)
02 CONSTANT FCR     \ FIFO Control Register (write)
03 CONSTANT LCR     \ Line Control Register
04 CONSTANT MCR     \ Modem Control Register
05 CONSTANT LSR     \ Line Status Register
06 CONSTANT MSR     \ Modem Status Register
07 CONSTANT SCR-REG \ Scratch Register (SCR conflicts with system var)

\ ---- LSR Bit Masks ----
01 CONSTANT LSR-DR      \ Data Ready
20 CONSTANT LSR-THRE    \ Transmitter Holding Register Empty
40 CONSTANT LSR-TEMT    \ Transmitter Empty
1E CONSTANT LSR-ERR     \ Error bits (OE+PE+FE+BI)

\ ---- LCR Bit Values ----
03 CONSTANT LCR-8N1     \ 8 data bits, no parity, 1 stop
80 CONSTANT LCR-DLAB    \ Divisor Latch Access Bit

\ ---- MCR Bit Values ----
01 CONSTANT MCR-DTR     \ Data Terminal Ready
02 CONSTANT MCR-RTS     \ Request to Send
08 CONSTANT MCR-OUT2    \ OUT2 (enables IRQ on PC)
0B CONSTANT MCR-NORMAL  \ DTR + RTS + OUT2

\ ---- FCR Bit Values ----
01 CONSTANT FCR-ENABLE  \ FIFO Enable
06 CONSTANT FCR-CLEAR   \ Clear both FIFOs
C0 CONSTANT FCR-TRIG14  \ 14-byte trigger level
C7 CONSTANT FCR-INIT    \ Enable + Clear + 14-byte trigger

\ ---- Baud Rate Divisors (115200 / desired baud) ----
0001 CONSTANT BAUD-115200
0002 CONSTANT BAUD-57600
0003 CONSTANT BAUD-38400
000C CONSTANT BAUD-9600
0018 CONSTANT BAUD-4800
0060 CONSTANT BAUD-1200

\ ---- Hardware Base ----
VARIABLE UART-BASE

\ ---- Register Access ----
\ These words compute the port address from base + offset,
\ then use the HARDWARE dictionary's C@-PORT / C!-PORT.

: UART-REG  ( offset -- port )  UART-BASE @ + ;
: UART@     ( offset -- byte )  UART-REG C@-PORT ;
: UART!     ( byte offset -- )  UART-REG C!-PORT ;

\ ---- Status Words ----
: TX-READY?  ( -- flag )  LSR UART@ LSR-THRE AND 0<> ;
: RX-READY?  ( -- flag )  LSR UART@ LSR-DR AND 0<> ;
: TX-EMPTY?  ( -- flag )  LSR UART@ LSR-TEMT AND 0<> ;
: RX-ERROR?  ( -- flag )  LSR UART@ LSR-ERR AND 0<> ;

\ ---- I/O Words ----
: UART-EMIT  ( char -- )
    BEGIN TX-READY? UNTIL
    THR UART!
;

: UART-KEY  ( -- char )
    BEGIN RX-READY? UNTIL
    RBR UART@
;

: UART-KEY?  ( -- flag )
    RX-READY?
;

: UART-TYPE  ( addr len -- )
    0 ?DO
        DUP C@ UART-EMIT
        1+
    LOOP
    DROP
;

\ ---- Baud Rate ----
: UART-BAUD!  ( divisor -- )
    LCR UART@ LCR-DLAB OR LCR UART!     \ Set DLAB
    DUP FF AND DLL UART!                  \ Divisor low byte
    8 RSHIFT DLM UART!                    \ Divisor high byte
    LCR UART@ LCR-DLAB INVERT AND LCR UART!  \ Clear DLAB
;

\ ---- Initialization ----
: UART-INIT  ( port -- )
    UART-BASE !
    00 IER UART!                 \ Disable all interrupts
    LCR-DLAB LCR UART!          \ Enable DLAB
    BAUD-115200 DUP
    FF AND DLL UART!             \ Divisor low (115200 baud)
    8 RSHIFT DLM UART!           \ Divisor high
    LCR-8N1 LCR UART!           \ 8N1, DLAB off
    FCR-INIT FCR UART!           \ Enable FIFO, clear, 14-byte trigger
    MCR-NORMAL MCR UART!         \ DTR + RTS + OUT2
;

\ ---- Loopback Test ----
\ Uses MCR bit 4 to route TX directly back to RX.
\ Returns TRUE if the UART echoes the test byte correctly.
: UART-LOOPBACK-TEST  ( port -- flag )
    UART-BASE !
    \ Enable loopback mode (MCR bit 4)
    MCR UART@ 10 OR MCR UART!
    \ Send test byte
    A5 THR UART!
    \ Small delay for byte to loop back
    10 0 DO LOOP
    \ Read back
    RBR UART@
    \ Disable loopback
    MCR UART@ 10 INVERT AND MCR UART!
    \ Check result
    A5 =
;

\ ---- Interrupt Enable ----
\ IER bits: 0=RX data, 1=TX empty, 2=line status, 3=modem status
: UART-INT-RX-ON   ( -- )  IER UART@ 01 OR IER UART! ;
: UART-INT-RX-OFF  ( -- )  IER UART@ 01 INVERT AND IER UART! ;
: UART-INT-TX-ON   ( -- )  IER UART@ 02 OR IER UART! ;
: UART-INT-TX-OFF  ( -- )  IER UART@ 02 INVERT AND IER UART! ;

\ ---- Drain ----
\ Read and discard all pending bytes from the receive buffer.
: UART-DRAIN  ( -- )
    BEGIN RX-READY? WHILE
        RBR UART@ DROP
    REPEAT
;

\ ---- Wait for TX complete ----
: UART-FLUSH  ( -- )
    BEGIN TX-EMPTY? UNTIL
;

FORTH DEFINITIONS
DECIMAL
