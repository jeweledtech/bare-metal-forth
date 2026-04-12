\ ============================================
\ CATALOG: AUDIO
\ CATEGORY: audio
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0x42-0x43 (PIT), 0x61 (speaker)
\ MMIO: AC97 BAR, HDA BAR
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( US-DELAY )
\ REQUIRES: PCI-ENUM ( PCI-FIND PCI-BAR@ )
\ ============================================
\
\ Audio output: PC speaker, AC97, Intel HDA.
\ Track A: PIT Ch2 square wave (BEEP/TONE)
\ Track B: AC97 PCM DMA (QEMU 8086:2415)
\ Track C: HDA CORB/RIRB (HP 04:03:00 class)
\
\ Usage:
\   USING AUDIO
\   DECIMAL 440 200 BEEP
\   PLAY-SCALE
\   AUDIO-INIT AUDIO-TEST
\
\ ============================================

VOCABULARY AUDIO
AUDIO DEFINITIONS
ALSO HARDWARE
ALSO PCI-ENUM
HEX

\ ============================================
\ Audio mode flag
\ ============================================
\ 0=none 1=speaker 2=AC97 3=HDA
VARIABLE AUDIO-MODE
0 AUDIO-MODE !

\ ============================================
\ Track A: PC Speaker
\ ============================================
\ PIT Ch2 generates square wave frequency.
\ Port 61 bits 0+1 gate PIT to speaker.

42 CONSTANT PIT-CH2
43 CONSTANT PIT-CMD
61 CONSTANT SPKR-PORT

\ PIT command: ch2, lo/hi byte, mode 3 (sq)
B6 CONSTANT PIT-CH2-CMD

\ PIT clock = 1193182 Hz (decimal)
\ Divisor = 1193182 / freq

VARIABLE PF-DIV
: PIT-FREQ! ( hz -- )
    PIT-CH2-CMD PIT-CMD OUTB
    DECIMAL 1193182 SWAP / HEX
    PF-DIV !
    PF-DIV @ FF AND PIT-CH2 OUTB
    PF-DIV @ 8 RSHIFT PIT-CH2 OUTB
;

: SPEAKER-ON ( -- )
    SPKR-PORT INB 3 OR SPKR-PORT OUTB
;

: SPEAKER-OFF ( -- )
    SPKR-PORT INB FC AND SPKR-PORT OUTB
;

: BEEP ( hz ms -- )
    SWAP PIT-FREQ!
    SPEAKER-ON
    DECIMAL 1000 * HEX US-DELAY
    SPEAKER-OFF
;

: TONE ( hz ms -- ) BEEP ;

\ ---- MIDI note table (C4=261 to B5=988) ----
\ 24 entries, 4 bytes each (cells via , )
\ Index: 0=C4, 9=A4(440), 12=C5, 23=B5
CREATE CHROMATIC
    DECIMAL
    261 , 277 , 293 , 311 ,
    329 , 349 , 370 , 392 ,
    415 , 440 , 466 , 494 ,
    523 , 554 , 587 , 622 ,
    659 , 698 , 740 , 784 ,
    831 , 880 , 932 , 988 ,
    HEX

\ NOTE ( midi# ms -- )
\ midi# 60=C4 through 83=B5
: NOTE ( midi# ms -- )
    SWAP 3C -
    DUP 0< IF 2DROP EXIT THEN
    DUP 17 > IF 2DROP EXIT THEN
    CELLS CHROMATIC + @
    SWAP BEEP
;

: PLAY-SCALE ( -- )
    DECIMAL
    261 200 BEEP
    293 200 BEEP
    329 200 BEEP
    349 200 BEEP
    392 200 BEEP
    440 200 BEEP
    494 200 BEEP
    523 300 BEEP
    HEX
;

\ ============================================
\ Track B: AC97 (QEMU, PCI 8086:2415)
\ ============================================
\ BAR0 = mixer (NAMBAR), BAR1 = bus master
\ (NABMBAR). Both are I/O port ranges.

2415 CONSTANT AC97-DEV-ID
8086 CONSTANT AC97-VEN-ID

VARIABLE AC97-NAMBAR
VARIABLE AC97-NABMBAR
VARIABLE AC97-B
VARIABLE AC97-D
VARIABLE AC97-F

: AC97-FIND ( -- ok? )
    AC97-VEN-ID AC97-DEV-ID PCI-FIND
    DUP IF
        DROP AC97-F ! AC97-D ! AC97-B !
        -1
    THEN
;

: AC97-BARS ( -- )
    AC97-B @ AC97-D @ AC97-F @ 0
    PCI-BAR@
    AC97-NAMBAR !
    AC97-B @ AC97-D @ AC97-F @ 1
    PCI-BAR@
    AC97-NABMBAR !
;

\ ---- Mixer register access (word-wide) ----
: AC97-MIX@ ( reg -- val )
    AC97-NAMBAR @ + INW
;

: AC97-MIX! ( val reg -- )
    AC97-NAMBAR @ + OUTW
;

: AC97-RESET ( -- )
    0 0 AC97-MIX!
    DECIMAL 100000 HEX US-DELAY
;

: AC97-VOL! ( vol -- )
    DUP 8 LSHIFT OR
    02 AC97-MIX!
;

: AC97-PCM-VOL! ( vol -- )
    DUP 8 LSHIFT OR
    18 AC97-MIX!
;

: AC97-RATE! ( hz -- )
    2A AC97-MIX!
;

\ ---- Bus Master DMA ----
\ BDL: 32 entries * 8 bytes = 256 bytes
\ PCM buffers: 32 * 1KB = 32KB
\ Memory: 0x80000-0x88100

80000 CONSTANT BDL-BASE
80100 CONSTANT PCM-BUF-BASE
400   CONSTANT PCM-BUF-SIZE

\ BDL entry: phys_addr(4) + samples:flags(4)
VARIABLE BDL-TMP
: BDL-ENTRY! ( phys samples entry# -- )
    8 * BDL-BASE +
    BDL-TMP !
    BDL-TMP @ !
    PCM-BUF-SIZE 1 RSHIFT
    BDL-TMP @ 4 + !
;

: BDL-INIT ( -- )
    20 0 DO
        I PCM-BUF-SIZE *
        PCM-BUF-BASE +
        PCM-BUF-SIZE 1 RSHIFT
        I BDL-ENTRY!
    LOOP
;

\ ---- PCM output control ----
\ NABMBAR offsets: 10=BDL base, 15=LVI,
\ 16=status, 1B=control

: PCM-BDL-LOAD ( -- )
    BDL-BASE AC97-NABMBAR @ 10 + OUTL
;

: PCM-LVI! ( n -- )
    AC97-NABMBAR @ 15 + OUTB
;

: PCM-STATUS ( -- word )
    AC97-NABMBAR @ 16 + INW
;

: PCM-START ( -- )
    PCM-BDL-LOAD
    1F PCM-LVI!
    1 AC97-NABMBAR @ 1B + OUTB
;

: PCM-STOP ( -- )
    0 AC97-NABMBAR @ 1B + OUTB
;

\ Enable bus master via PCI command register
: AC97-ENABLE ( -- )
    AC97-B @ AC97-D @ AC97-F @
    PCI-ENABLE
;

: AC97-INIT ( -- ok? )
    AC97-FIND 0= IF 0 EXIT THEN
    AC97-BARS
    AC97-ENABLE
    AC97-RESET
    0 AC97-VOL!
    0 AC97-PCM-VOL!
    DECIMAL 44100 HEX AC97-RATE!
    BDL-INIT
    2 AUDIO-MODE !
    -1
;

\ ============================================
\ Track C: Intel HDA (class 04:03:00)
\ ============================================
\ MMIO via PCI BAR0. CORB/RIRB ring buffers
\ for codec verbs. Stream descriptors for DMA.

VARIABLE HDA-BAR
0 HDA-BAR !
VARIABLE HDA-B VARIABLE HDA-D VARIABLE HDA-F

\ HDA detection by class code (04:03:00)
\ PCI-FIND matches vendor:device, so we scan
\ manually for class code match.
VARIABLE HDA-OK

: HDA-FIND ( -- ok? )
    0 HDA-OK !
    4 0 DO
        20 0 DO
            J I 0 8 PCI-READ
            8 RSHIFT
            40300 = IF
                J HDA-B !
                I HDA-D !
                0 HDA-F !
                -1 HDA-OK !
                UNLOOP UNLOOP
                HDA-OK @ EXIT
            THEN
        LOOP
    LOOP
    0
;

: HDA-BARS ( -- )
    HDA-B @ HDA-D @ HDA-F @ 0
    PCI-BAR@
    HDA-BAR !
;

\ ---- MMIO register access ----
: HDA@ ( reg -- val )
    HDA-BAR @ + @
;

: HDA! ( val reg -- )
    HDA-BAR @ + !
;

: HDAB@ ( reg -- byte )
    HDA-BAR @ + C@
;

: HDAB! ( byte reg -- )
    HDA-BAR @ + C!
;

\ ---- Controller reset ----
: HDA-RESET ( -- )
    0 0C HDA!
    DECIMAL 100000 HEX US-DELAY
    1 0C HDA!
    DECIMAL 100000 HEX US-DELAY
    10 0 DO
        8 HDA@ 0<> IF
            UNLOOP EXIT
        THEN
        DECIMAL 10000 HEX US-DELAY
    LOOP
;

\ ---- CORB/RIRB ring buffers ----
\ Place at 0x82000 and 0x83000
82000 CONSTANT CORB-BASE
83000 CONSTANT RIRB-BASE

: HDA-CORB-INIT ( -- )
    CORB-BASE 40 HDA!
    0 44 HDA!
    8000 4A HDA!
    0 48 HDA!
    2 4C HDAB!
;

: HDA-RIRB-INIT ( -- )
    RIRB-BASE 50 HDA!
    0 54 HDA!
    8000 58 HDA!
    1 5A HDA!
    2 5C HDAB!
;

\ ---- Codec verb send/receive ----
VARIABLE CORB-WP
0 CORB-WP !

: HDA-VERB! ( verb -- )
    CORB-WP @ 1+ FF AND
    DUP CORB-WP !
    DUP DUP + DUP +
    CORB-BASE + ROT SWAP !
    CORB-WP @ 48 HDA!
;

: HDA-RESP@ ( -- resp )
    20 0 DO
        58 HDA@ FF AND
        CORB-WP @ = IF
            CORB-WP @ 8 *
            RIRB-BASE + @
            UNLOOP EXIT
        THEN
        DECIMAL 1000 HEX US-DELAY
    LOOP
    FFFFFFFF
;

\ ---- Stream descriptor (stream 1) ----
\ Offsets from HDA BAR: 0x80=SD0CTL,
\ 0x88=SD0CBL, 0x8C=SD0LVI, 0x92=SD0FMT,
\ 0x98=SD0BDPL, 0x9C=SD0BDPU

: HDA-STREAM-INIT ( -- )
    BDL-BASE 98 HDA!
    0 9C HDA!
    PCM-BUF-SIZE 20 * 88 HDA!
    1F 8C HDAB!
    4011 92 HDA!
;

: HDA-STREAM-START ( -- )
    2 80 HDAB!
;

: HDA-STREAM-STOP ( -- )
    0 80 HDAB!
;

\ Enable bus master
: HDA-ENABLE ( -- )
    HDA-B @ HDA-D @ HDA-F @
    PCI-ENABLE
;

: HDA-INIT ( -- ok? )
    HDA-FIND 0= IF 0 EXIT THEN
    HDA-BARS
    HDA-ENABLE
    HDA-RESET
    HDA-CORB-INIT
    HDA-RIRB-INIT
    HDA-STREAM-INIT
    3 AUDIO-MODE !
    -1
;

\ ============================================
\ PCM sample generation
\ ============================================

: SILENCE ( buf -- )
    PCM-BUF-SIZE 0 FILL
;

\ ============================================
\ Auto-detect and demo
\ ============================================

: AUDIO-INIT ( -- )
    ." Audio: "
    HDA-INIT IF
        ." HDA ok" CR EXIT
    THEN
    AC97-INIT IF
        ." AC97 ok" CR EXIT
    THEN
    1 AUDIO-MODE !
    ." Speaker" CR
;

: AUDIO-TEST ( -- )
    AUDIO-MODE @ 0= IF
        ." No audio" CR EXIT
    THEN
    DECIMAL 440 200 BEEP HEX
    ." 440Hz done" CR
;

: AUDIO-STATUS ( -- )
    ." Mode: "
    AUDIO-MODE @ DECIMAL . HEX CR
;

PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
