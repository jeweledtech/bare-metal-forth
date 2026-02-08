\ ============================================================================
\ RTL8139 Network Interface Controller - Driver Module
\ ============================================================================
\
\ Description: RealTek RTL8139 10/100 Ethernet Controller
\ Vendor: RealTek
\ PCI ID: 10EC:8139
\
\ Auto-extracted from Windows driver by Bare-Metal Forth Driver Extraction Tool
\ with manual refinements for completeness.
\
\ Usage:
\   USING HARDWARE
\   USING RTL8139
\   $C000 RTL8139-INIT      \ Initialize at I/O base $C000
\
\ This driver demonstrates the extraction workflow:
\   1. Windows driver contained IRP/PnP scaffolding (removed)
\   2. Hardware register access sequences (kept)
\   3. Timing loops for reset (kept)
\   4. Interrupt setup (translated to our primitives)
\
\ ============================================================================

\ Module marker - executing this word removes all definitions after it
MARKER --RTL8139--

\ ============================================================================
\ PCI Identification
\ ============================================================================

$10EC CONSTANT RTL-VENDOR-ID
$8139 CONSTANT RTL-DEVICE-ID

\ ============================================================================
\ Register Definitions (offsets from I/O base)
\ ============================================================================

\ MAC Address registers (6 bytes)
$00 CONSTANT RTL-IDR0       \ ID Register 0-5 (MAC address)

\ Multicast registers
$08 CONSTANT RTL-MAR0       \ Multicast Address Register 0-7

\ Transmit Status registers (4 descriptors)
$10 CONSTANT RTL-TSD0       \ Transmit Status Descriptor 0
$14 CONSTANT RTL-TSD1       \ Transmit Status Descriptor 1
$18 CONSTANT RTL-TSD2       \ Transmit Status Descriptor 2
$1C CONSTANT RTL-TSD3       \ Transmit Status Descriptor 3

\ Transmit Start Address registers (4 descriptors)
$20 CONSTANT RTL-TSAD0      \ Transmit Start Address 0
$24 CONSTANT RTL-TSAD1      \ Transmit Start Address 1
$28 CONSTANT RTL-TSAD2      \ Transmit Start Address 2
$2C CONSTANT RTL-TSAD3      \ Transmit Start Address 3

\ Receive Buffer Start Address
$30 CONSTANT RTL-RBSTART    \ Receive Buffer Start (physical addr)

\ Early Receive Byte Count
$34 CONSTANT RTL-ERBCR      \ Early Rx Byte Count

\ Early Receive Status
$36 CONSTANT RTL-ERSR       \ Early Rx Status Register

\ Command Register
$37 CONSTANT RTL-CMD        \ Command Register

\ Current Address of Packet Read
$38 CONSTANT RTL-CAPR       \ Current Address of Packet Read

\ Current Buffer Address
$3A CONSTANT RTL-CBR        \ Current Buffer Address

\ Interrupt Mask Register
$3C CONSTANT RTL-IMR        \ Interrupt Mask Register (16-bit)

\ Interrupt Status Register
$3E CONSTANT RTL-ISR        \ Interrupt Status Register (16-bit)

\ Transmit Configuration
$40 CONSTANT RTL-TCR        \ Transmit Configuration Register

\ Receive Configuration
$44 CONSTANT RTL-RCR        \ Receive Configuration Register

\ Timer Count Register
$48 CONSTANT RTL-TCTR       \ Timer Count Register

\ Missed Packet Counter
$4C CONSTANT RTL-MPC        \ Missed Packet Counter

\ EEPROM Control Register
$50 CONSTANT RTL-9346CR     \ 93C46 Command Register

\ Configuration Registers
$52 CONSTANT RTL-CONFIG0    \ Configuration Register 0
$53 CONSTANT RTL-CONFIG1    \ Configuration Register 1

\ Media Status Register
$58 CONSTANT RTL-MSR        \ Media Status Register

\ Configuration 3
$59 CONSTANT RTL-CONFIG3    \ Configuration Register 3

\ Configuration 4
$5A CONSTANT RTL-CONFIG4    \ Configuration Register 4

\ Basic Mode Control Register (PHY)
$62 CONSTANT RTL-BMCR       \ Basic Mode Control Register

\ Basic Mode Status Register (PHY)
$64 CONSTANT RTL-BMSR       \ Basic Mode Status Register

\ ============================================================================
\ Command Register Bits
\ ============================================================================

$01 CONSTANT CMD-BUFE       \ Buffer Empty
$04 CONSTANT CMD-TE         \ Transmitter Enable
$08 CONSTANT CMD-RE         \ Receiver Enable
$10 CONSTANT CMD-RST        \ Reset

\ ============================================================================
\ Interrupt Bits (for IMR and ISR)
\ ============================================================================

$0001 CONSTANT INT-ROK      \ Receive OK
$0002 CONSTANT INT-RER      \ Receive Error
$0004 CONSTANT INT-TOK      \ Transmit OK
$0008 CONSTANT INT-TER      \ Transmit Error
$0010 CONSTANT INT-RXOVW    \ Rx Buffer Overflow
$0020 CONSTANT INT-PUN      \ Packet Underrun / Link Change
$0040 CONSTANT INT-FOVW     \ Rx FIFO Overflow
$2000 CONSTANT INT-LENCHG   \ Cable Length Change
$4000 CONSTANT INT-TIMEOUT  \ Time Out
$8000 CONSTANT INT-SERR     \ System Error

\ All useful interrupts
INT-ROK INT-RER OR INT-TOK OR INT-TER OR INT-RXOVW OR INT-PUN OR
CONSTANT INT-ALL

\ ============================================================================
\ Receive Configuration Bits
\ ============================================================================

$0001 CONSTANT RCR-AAP      \ Accept All Packets
$0002 CONSTANT RCR-APM      \ Accept Physical Match
$0004 CONSTANT RCR-AM       \ Accept Multicast
$0008 CONSTANT RCR-AB       \ Accept Broadcast
$0010 CONSTANT RCR-AR       \ Accept Runt
$0020 CONSTANT RCR-AER      \ Accept Error Packet
$0080 CONSTANT RCR-WRAP     \ Wrap (ring buffer)

\ Buffer size encoding (bits 11-13)
\ 00 = 8K+16, 01 = 16K+16, 10 = 32K+16, 11 = 64K+16
$0000 CONSTANT RCR-RBLEN-8K
$0800 CONSTANT RCR-RBLEN-16K
$1000 CONSTANT RCR-RBLEN-32K
$1800 CONSTANT RCR-RBLEN-64K

\ ============================================================================
\ Module State
\ ============================================================================

VARIABLE RTL-BASE           \ I/O Base Port
VARIABLE RTL-RX-BUFFER      \ Receive buffer address (physical)
VARIABLE RTL-TX-SLOT        \ Current TX descriptor slot (0-3)
CREATE RTL-MAC 6 ALLOT      \ MAC address storage

\ Receive buffer size (we'll use 8K + 16 byte header + 1500 margin)
8192 16 + 1500 + CONSTANT RTL-RX-SIZE

\ ============================================================================
\ Low-Level Register Access
\ ============================================================================

: RTL-C@  ( offset -- byte )
    RTL-BASE @ + C@-PORT
;

: RTL-C!  ( byte offset -- )
    RTL-BASE @ + C!-PORT
;

: RTL-W@  ( offset -- word )
    RTL-BASE @ + W@-PORT
;

: RTL-W!  ( word offset -- )
    RTL-BASE @ + W!-PORT
;

: RTL-@  ( offset -- dword )
    RTL-BASE @ + @-PORT
;

: RTL-!  ( dword offset -- )
    RTL-BASE @ + !-PORT
;

\ ============================================================================
\ Chip Reset (extracted from Windows driver)
\ ============================================================================

\ This sequence was extracted from the Windows driver reset routine.
\ The Windows version had KeStallExecutionProcessor(10) which we
\ translate to our US-DELAY.

: RTL-RESET  ( -- )
    \ Issue reset command
    CMD-RST RTL-CMD RTL-C!
    
    \ Poll until reset completes (bit clears)
    \ Windows driver timeout was ~1ms (1000 iterations at 1us each)
    1000 0 DO
        RTL-CMD RTL-C@
        CMD-RST AND 0= IF
            UNLOOP EXIT
        THEN
        1 US-DELAY
    LOOP
    
    ." RTL8139: Reset timeout!" CR
;

\ ============================================================================
\ MAC Address (extracted from Windows driver)
\ ============================================================================

: RTL-READ-MAC  ( -- )
    \ Read 6-byte MAC from IDR0-IDR5
    6 0 DO
        RTL-IDR0 I + RTL-C@
        RTL-MAC I + C!
    LOOP
;

: RTL-PRINT-MAC  ( -- )
    ." MAC: "
    6 0 DO
        RTL-MAC I + C@
        0 <# # # #> TYPE
        I 5 < IF ." :" THEN
    LOOP
    CR
;

\ ============================================================================
\ Receiver Setup (extracted from Windows driver)
\ ============================================================================

: RTL-RX-INIT  ( rx-buffer-phys -- )
    \ Store buffer address
    DUP RTL-RX-BUFFER !
    
    \ Program receive buffer start address
    RTL-RBSTART RTL-!
    
    \ Configure receiver:
    \ - Accept broadcast (AB)
    \ - Accept physical match (APM)
    \ - 8K buffer
    \ - Wrap mode
    RCR-AB RCR-APM OR RCR-RBLEN-8K OR RCR-WRAP OR
    RTL-RCR RTL-!
    
    \ Reset packet read pointer
    $FFF0 RTL-CAPR RTL-W!       \ Spec says start at 0xFFF0
;

\ ============================================================================
\ Transmitter Setup (extracted from Windows driver)
\ ============================================================================

: RTL-TX-INIT  ( -- )
    \ Clear all 4 TX descriptor status registers
    0 RTL-TSD0 RTL-!
    0 RTL-TSD1 RTL-!
    0 RTL-TSD2 RTL-!
    0 RTL-TSD3 RTL-!
    
    \ Start with slot 0
    0 RTL-TX-SLOT !
;

\ ============================================================================
\ Enable Chip (extracted from Windows driver)
\ ============================================================================

: RTL-ENABLE  ( -- )
    \ Enable receiver and transmitter
    CMD-RE CMD-TE OR RTL-CMD RTL-C!
;

: RTL-DISABLE  ( -- )
    \ Disable receiver and transmitter
    0 RTL-CMD RTL-C!
;

\ ============================================================================
\ Interrupt Setup (translated from Windows driver)
\ ============================================================================

: RTL-INT-ENABLE  ( mask -- )
    RTL-IMR RTL-W!
;

: RTL-INT-DISABLE  ( -- )
    0 RTL-IMR RTL-W!
;

: RTL-INT-ACK  ( -- status )
    \ Read and clear interrupt status
    RTL-ISR RTL-W@
    DUP RTL-ISR RTL-W!      \ Writing 1s clears the bits
;

\ ============================================================================
\ Link Status (extracted from Windows driver)
\ ============================================================================

: RTL-LINK?  ( -- flag )
    \ Check Media Status Register for link
    RTL-MSR RTL-C@
    $04 AND 0=              \ Bit 2 = 0 means link up
;

: RTL-SPEED  ( -- 10|100 )
    \ Check if 10Mbps or 100Mbps
    RTL-MSR RTL-C@
    $08 AND IF 10 ELSE 100 THEN
;

\ ============================================================================
\ Transmit Packet (extracted and simplified from Windows driver)
\ ============================================================================

: RTL-TX  ( buffer-phys length -- )
    \ Get current TX slot
    RTL-TX-SLOT @
    
    \ Calculate register offsets
    DUP 4 * RTL-TSAD0 +     \ Start address register
    SWAP 4 * RTL-TSD0 +     \ Status register
    
    \ Program start address
    ROT                     ( length status-reg addr-reg buffer )
    ROT SWAP RTL-!          ( length status-reg )
    
    \ Program length and start transmission
    \ Size in bits 0-12, OWN bit (13) must be 0
    SWAP $1FFF AND          \ Mask to 13 bits max
    SWAP RTL-!              \ Write starts transmission
    
    \ Move to next slot (round-robin)
    RTL-TX-SLOT @ 1+ 3 AND RTL-TX-SLOT !
;

\ Wait for TX completion
: RTL-TX-WAIT  ( slot -- ok? )
    4 * RTL-TSD0 +          \ Calculate status register
    1000 0 DO
        DUP RTL-@
        DUP $8000 AND IF    \ TOK bit set = complete
            DROP DROP TRUE UNLOOP EXIT
        THEN
        $4000 AND IF        \ TUN bit set = underrun error
            DROP FALSE UNLOOP EXIT
        THEN
        1 US-DELAY
    LOOP
    DROP FALSE              \ Timeout
;

\ ============================================================================
\ Receive Packet (extracted from Windows driver)
\ ============================================================================

\ Check if packet available
: RTL-RX?  ( -- flag )
    RTL-CMD RTL-C@ CMD-BUFE AND 0=
;

\ Get receive buffer read position
: RTL-RX-POS  ( -- offset )
    RTL-CAPR RTL-W@ $10 +    \ CAPR + 16 (header)
    RTL-RX-SIZE 1- AND       \ Wrap around
;

\ Acknowledge received packet (advance read pointer)
: RTL-RX-ACK  ( packet-length -- )
    RTL-RX-POS +            \ New position
    4 + 3 INVERT AND        \ Align to dword
    $10 - $FFFF AND         \ Adjust and wrap
    RTL-CAPR RTL-W!
;

\ ============================================================================
\ Full Initialization Sequence
\ ============================================================================

: RTL-INIT  ( base-port rx-buffer-phys -- )
    SWAP RTL-BASE !
    
    ." RTL8139 initializing at port $" RTL-BASE @ HEX U. DECIMAL CR
    
    \ Reset the chip
    RTL-RESET
    
    \ Read MAC address
    RTL-READ-MAC
    RTL-PRINT-MAC
    
    \ Initialize receiver
    RTL-RX-INIT
    
    \ Initialize transmitter
    RTL-TX-INIT
    
    \ Enable interrupts (all useful ones)
    INT-ALL RTL-INT-ENABLE
    
    \ Enable RX and TX
    RTL-ENABLE
    
    \ Check link status
    RTL-LINK? IF
        ." Link: UP at " RTL-SPEED . ." Mbps" CR
    ELSE
        ." Link: DOWN" CR
    THEN
    
    ." RTL8139 ready" CR
;

\ ============================================================================
\ PCI Auto-Detection
\ ============================================================================

\ Find RTL8139 on PCI bus
: RTL-FIND-PCI  ( -- base-port | 0 )
    32 0 DO                         \ Bus 0, scan 32 devices
        8 0 DO                      \ 8 functions per device
            0 J I 0 PCI-READ        \ Read vendor/device ID
            DUP $FFFF AND RTL-VENDOR-ID = IF
                16 RSHIFT $FFFF AND RTL-DEVICE-ID = IF
                    \ Found it! Read BAR0 for I/O base
                    0 J I $10 PCI-READ
                    $FFFC AND       \ Mask off lower 2 bits
                    UNLOOP UNLOOP EXIT
                THEN
            ELSE
                DROP
            THEN
        LOOP
    LOOP
    0                               \ Not found
;

\ Auto-initialize if found
: RTL-AUTO  ( rx-buffer-phys -- )
    RTL-FIND-PCI ?DUP IF
        SWAP RTL-INIT
    ELSE
        DROP ." RTL8139 not found on PCI bus" CR
    THEN
;

\ ============================================================================
\ Module Complete
\ ============================================================================

.( RTL8139 driver module loaded) CR
.( Usage:) CR
.(   <base-port> <rx-buffer> RTL8139-INIT   - Initialize at known port) CR
.(   <rx-buffer> RTL-AUTO                    - Auto-detect on PCI) CR
.(   RTL-LINK?                               - Check link status) CR
CR

\ End of module
