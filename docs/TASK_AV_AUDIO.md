# TASK: AUDIO Vocabulary — AC97 (QEMU) + Intel HDA (HP)
# Phase A/V Phase 2 of 4: Audio Foundation

## Context

GRAPHICS (Phase 1) proved the A/V pattern: thin vocabulary over HARDWARE
primitives, TAQOZ-compatible naming, REQUIRES: chain. AUDIO follows the
same structure. The goal is bare-metal audio output from ForthOS — no OS
audio stack, no HAL, direct register writes to the sound hardware.

Two hardware targets:
- QEMU: Intel AC97 (PCI 8086:2415) — simple, MMIO mixer + I/O PCM port
- HP 15-bs0xx: Intel HDA (PCI 8086:9D70 or similar Sunrise Point) —
  already detected by AUTO-DETECT, 10 hardware functions extracted from
  HDAudBus.sys via UBT pipeline

TAQOZ used bit-bashed SPI audio at 8MB/s for SD card music playback.
ForthOS targets AC97/HDA DMA ring buffers for PCM output — a different
mechanism but the same philosophy: write samples directly to hardware,
gate with a timer, no OS involvement.

The immediate deliverable for the A/V demo is: `BEEP` (audible tone from
ForthOS) and `PLAY-NOTE` (frequency + duration). Full PCM streaming is
Phase 2b. The demo needs sound — even a square wave via the PC speaker
gate (port 0x61 + PIT channel 2) counts as audio and validates the path.

## Repository

~/projects/forthos (github.com/jeweledtech/bare-metal-forth)

## Two-Track Implementation

### Track A — PC Speaker (immediate, zero dependencies)

The PC speaker is the simplest possible audio path. It's always present,
works in QEMU, works on HP, no PCI required:

- PIT Channel 2 (port 0x42/0x43) generates the tone frequency
- Port 0x61 bit 0 = PIT gate, bit 1 = speaker enable
- US-DELAY (already in HARDWARE vocab) for duration

This is what beep.sys does. The UBT pipeline extracted 2-4 hardware
functions from beep.sys: PIT channel 2 frequency write + speaker gate.

Track A words: `SPEAKER-ON`, `SPEAKER-OFF`, `BEEP` (freq ms --),
`TONE` (freq ms --), `NOTE` (midi# ms --), `PLAY-SCALE` (demo)

### Track B — AC97 PCM streaming (QEMU primary audio path)

AC97 is the QEMU default audio device. It provides:
- BAR0: I/O port base for PCM output registers (Bus Master DMA)
- BAR1: I/O port base for mixer registers (volume, sample rate)
- IRQ: configurable via PCI (INT line)

AC97 Bus Master uses descriptor lists (BDL) — a ring of buffer
descriptors each pointing to a PCM sample buffer. The hardware DMAs
from these buffers autonomously once armed. ForthOS on bare metal owns
the physical addresses directly (no MDL/virtual memory indirection).

Track B words: `AC97-INIT`, `AC97-RESET`, `AC97-VOL!`, `AC97-RATE!`,
`PCM-BDL-INIT`, `PCM-BUF-WRITE`, `PCM-START`, `PCM-STOP`,
`PCM-STATUS`

### Track C — Intel HDA (HP hardware path)

HDA is significantly more complex than AC97 — it uses CORB/RIRB
ring buffers to send codec verbs, stream descriptors for DMA, and
requires codec enumeration before audio output. The 10 hardware
functions from HDAudBus.sys are the foundation.

Track C is Phase 2b — implement Track A first (demo blocker), Track B
second (QEMU streaming), Track C third (HP hardware audio).

Track C words: `HDA-INIT`, `HDA-RESET`, `HDA-VERB!`, `HDA-VERB@`,
`HDA-CODEC-ENUM`, `HDA-STREAM-INIT`, `HDA-STREAM-START`,
`HDA-STREAM-STOP`

## Block Assignment

Blocks 280–319 — AUDIO vocabulary
  280     : Catalog header + PC speaker constants (PIT Ch2 + port 0x61)
  281     : SPEAKER-ON SPEAKER-OFF BEEP TONE (Track A complete)
  282     : NOTE (MIDI# to frequency) PLAY-SCALE demo
  283     : AC97 PCI detection + BAR0/BAR1 base address words
  284     : AC97 mixer words (reset, volume, sample rate)
  285     : AC97 Bus Master DMA: BDL init + buffer descriptor words
  286     : AC97 PCM output: PCM-START PCM-STOP PCM-STATUS
  287     : PCM sample generation: SILENCE SQUARE-WAVE SAWTOOTH
  288     : HDA MMIO base + CORB/RIRB ring buffer words
  289     : HDA codec verb send/receive + codec enumeration
  290     : HDA stream descriptor init + DMA start/stop
  291     : AUDIO-INIT (auto-detect AC97 vs HDA) + AUDIO-TEST
  292–319 : Reserved (ADSR envelope, FM synthesis, WAV player)

## Critical Constraints (same as all vocabs)

1. 64-character line limit — hard limit from Forth block format
2. No 2* — use DUP + instead
3. No " in Forth-83 — use DECIMAL 34 CONSTANT QC + QC EMIT
4. Short strings under 6 chars in ." corrupt state — pad to 6+
5. Every vocab: ONLY FORTH DEFINITIONS at end
6. ALSO/PREVIOUS must be matched
7. HEX/DECIMAL bleed — document every mode switch
8. Verify every word against forth.asm before using
9. OUTB is ( byte port -- ) — NOT ( port byte )
10. INB is ( port -- byte )
11. @ is 32-bit, C@ is 8-bit — use correctly for MMIO
12. No 2>R/2R@ in kernel — use VARIABLE for multi-value saves

## Kernel Words Available (verified in forth.asm)

Port I/O:  INB OUTB INW OUTW INL OUTL C@-PORT C!-PORT @-PORT !-PORT
Memory:    @ ! C@ C! MOVE FILL HERE ALLOT ,
Stack:     DUP DROP SWAP OVER ROT NIP 2DUP 2DROP
Arith:     + - * / MOD NEGATE ABS DUP + (for 2*)
Compare:   = < > 0= 0< AND OR XOR INVERT
Control:   IF ELSE THEN DO LOOP BEGIN UNTIL WHILE REPEAT EXIT
Compiler:  : ; CONSTANT VARIABLE CREATE IMMEDIATE ' EXECUTE LITERAL
Blocks:    BLOCK BUFFER UPDATE SAVE-BUFFERS FLUSH LOAD THRU
Vocab:     VOCABULARY DEFINITIONS ALSO PREVIOUS ONLY FORTH USING ORDER
HARDWARE:  US-DELAY PCI-READ PCI-WRITE IRQ-CONNECT IRQ-DISCONNECT
           C@-MMIO C!-MMIO @-MMIO !-MMIO PCI-SCAN

## Part 1: forth/dict/audio.fth

### Block 280 — Catalog header + PC speaker constants

```forth
\ CATALOG: AUDIO
\ CATEGORY: audio
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: 0x40-0x43 (PIT), 0x61 (speaker)
\ MMIO: AC97 BAR1 (mixer), HDA MMIO (codec)
\ CONFIDENCE: high
\ REQUIRES: HARDWARE ( US-DELAY PCI-READ )
\ REQUIRES: PCI-ENUM ( PCI-FIND )
VOCABULARY AUDIO
AUDIO DEFINITIONS
HEX
\ PIT channel 2 (tone generation)
42 CONSTANT PIT-CH2-PORT     \ Counter 2 I/O
43 CONSTANT PIT-CMD-PORT     \ Mode/command register
61 CONSTANT SPKR-PORT        \ PC speaker gate + misc
\ PIT command: ch2, lo/hi byte, square wave (mode 3)
B6 CONSTANT PIT-CH2-CMD      \ 10110110b
\ AC97 PCI IDs (QEMU)
2415 CONSTANT AC97-DEVICE     \ Intel 82801AA AC97
8086 CONSTANT AC97-VENDOR
\ HDA PCI vendor
8086 CONSTANT HDA-VENDOR
\ Audio mode flag (0=none, 1=speaker, 2=AC97, 3=HDA)
VARIABLE AUDIO-MODE
0 AUDIO-MODE !
\ AC97 BAR addresses (filled by AC97-INIT)
VARIABLE AC97-NAMBAR          \ mixer BAR (word-wide regs)
VARIABLE AC97-NABMBAR         \ bus master BAR (PCM DMA)
```

### Block 281 — PC Speaker words (Track A — demo blocker)

The i8254 PIT Channel 2 generates a square wave at the given frequency.
Port 0x43 accepts a command byte; port 0x42 takes the 16-bit divisor
(PIT clock = 1193182 Hz, divisor = 1193182 / frequency).

Stack note: For PIT-FREQ!, the divisor goes to port 0x42 in two bytes
(lo byte first, then hi byte). This is straightforward with the byte
port words already in the kernel.

```forth
\ PIT-FREQ! ( hz -- ) Set PIT channel 2 frequency
: PIT-FREQ! ( hz -- )
  PIT-CH2-CMD PIT-CMD-PORT OUTB  \ set mode: ch2 sq wave
  DECIMAL 1193182 SWAP / HEX    \ divisor = 1193182/hz
  DUP FF AND PIT-CH2-PORT OUTB   \ low byte
  8 RSHIFT PIT-CH2-PORT OUTB     \ high byte
;

\ SPEAKER-ON ( -- ) Enable PC speaker
: SPEAKER-ON ( -- )
  SPKR-PORT INB 3 OR SPKR-PORT OUTB
;

\ SPEAKER-OFF ( -- ) Disable PC speaker
: SPEAKER-OFF ( -- )
  SPKR-PORT INB FC AND SPKR-PORT OUTB
;

\ BEEP ( hz ms -- ) Beep at frequency for duration
: BEEP ( hz ms -- )
  SWAP PIT-FREQ!
  SPEAKER-ON
  DECIMAL 1000 * US-DELAY HEX  \ ms to us
  SPEAKER-OFF
;

\ TONE is an alias for BEEP (TAQOZ naming compatibility)
: TONE ( hz ms -- ) BEEP ;
```

### Block 282 — NOTE + demo (MIDI# to Hz)

MIDI note to frequency: f = 440 * 2^((n-69)/12)
Forth-83 has no floating point, so use a lookup table for the chromatic
scale. Middle C (MIDI 60) = 261 Hz. We store a 24-entry table covering
two octaves (C4 to B5, MIDI 60-83) which covers the demo range.

```forth
\ 12-tone chromatic scale from C4=261Hz to B4=494Hz
\ (one octave, integer Hz approximations)
CREATE CHROMATIC
  261 , 277 , 293 , 311 , 329 , 349 ,  \ C D E F G A (approx)
  370 , 392 , 415 , 440 , 466 , 494 ,  \ B and sharps
  523 , 554 , 587 , 622 , 659 , 698 ,  \ C5-F5
  740 , 784 , 831 , 880 , 932 , 988 ,  \ G5-B5

\ NOTE ( midi# ms -- ) Play MIDI note (60-83) for ms duration
: NOTE ( midi# ms -- )
  SWAP 3C -              \ offset from C4 (MIDI 60 = 3C hex)
  DUP 0< IF 2DROP EXIT THEN  \ below range: skip
  DUP 18 >= IF 2DROP EXIT THEN  \ above range: skip
  DUP + CHROMATIC +      \ addr = CHROMATIC + offset*2 (cells)
  @ SWAP BEEP
;

\ PLAY-SCALE ( -- ) Demo: C major scale ascending
: PLAY-SCALE ( -- )
  DECIMAL
  261 200 BEEP    ( C4 )
  293 200 BEEP    ( D4 )
  329 200 BEEP    ( E4 )
  349 200 BEEP    ( F4 )
  392 200 BEEP    ( G4 )
  440 200 BEEP    ( A4 )
  494 200 BEEP    ( B4 )
  523 300 BEEP    ( C5 )
  HEX
;
```

NOTE: CREATE stores cells (4 bytes each). DUP + = 2* for cell offset.
Verify CHROMATIC addressing: offset 0 → address CHROMATIC+0 → 261.
If DUP + gives wrong result check endianness of , (comma) in kernel.

### Block 283 — AC97 PCI detection + BAR words

AC97 has two BARs:
- BAR0 (NAMBAR, 0x10 in PCI config): Native Audio Mixer port base
  Word-wide I/O registers: master volume, PCM volume, sample rate, etc.
- BAR1 (NABMBAR, 0x14): Native Audio Bus Master port base
  Controls DMA: PCM OUT buffer descriptor list, status, position

Both BARs are I/O port ranges (not MMIO) on most AC97 implementations.

```forth
\ AC97-FIND ( -- found? ) Detect AC97 via PCI scan
\ Searches buses 0-3 for vendor 8086 device 2415
VARIABLE AC97-BUS  0 AC97-BUS !
VARIABLE AC97-DEV  0 AC97-DEV !

: AC97-FIND ( -- found? )
  4 0 DO                      \ 4 buses
    20 0 DO                   \ 32 devices
      J I 0 0 PCI-READ        \ read vendor:device
      FFFF AND AC97-VENDOR =  \ vendor matches?
      IF
        J I 0 0 PCI-READ
        10 RSHIFT AC97-DEVICE =  \ device matches?
        IF
          J AC97-BUS !
          I AC97-DEV !
          TRUE UNLOOP UNLOOP EXIT
        THEN
      ELSE DROP
      THEN
    LOOP
  LOOP
  FALSE
;

\ AC97-BARS ( -- ) Read BAR0+BAR1 into variables
: AC97-BARS ( -- )
  AC97-BUS @ AC97-DEV @ 0 10 PCI-READ  \ BAR0
  FFFC AND AC97-NAMBAR !
  AC97-BUS @ AC97-DEV @ 0 14 PCI-READ  \ BAR1
  FFFC AND AC97-NABMBAR !
;
```

NOTE: UNLOOP exits a DO/LOOP cleanly before EXIT — verify it exists in
the kernel (it should as it's Forth-83). If not, use a flag variable.

### Block 284 — AC97 mixer words

AC97 mixer registers are word-wide (16-bit) at offsets from NAMBAR.
Key registers:
  0x02 = Master Volume (left/right, 6-bit each, 0=max, 63=mute)
  0x18 = PCM Out Volume
  0x2A = PCM Front DAC Rate (sample rate in Hz, e.g. 0xAC44 = 44100)
  0x00 = Reset (write any value to reset codec)

```forth
\ AC97-MIX@ ( reg -- val ) Read mixer register (word)
: AC97-MIX@ ( reg -- val )
  AC97-NAMBAR @ + INW
;

\ AC97-MIX! ( val reg -- ) Write mixer register (word)
: AC97-MIX! ( val reg -- )
  AC97-NAMBAR @ + OUTW
;

\ AC97-RESET ( -- ) Reset AC97 codec
: AC97-RESET ( -- )
  0 0 AC97-MIX!             \ write 0 to reset register
  DECIMAL 100 1000 * US-DELAY HEX  \ wait 100ms
;

\ AC97-VOL! ( vol -- ) Set master volume (0=max, 3F=mute)
: AC97-VOL! ( vol -- )
  DUP 8 LSHIFT OR           \ same value for L and R channels
  02 AC97-MIX!
;

\ AC97-PCM-VOL! ( vol -- ) Set PCM out volume
: AC97-PCM-VOL! ( vol -- )
  DUP 8 LSHIFT OR 18 AC97-MIX!
;

\ AC97-RATE! ( hz -- ) Set DAC sample rate
: AC97-RATE! ( hz -- )
  2A AC97-MIX!
;
```

NOTE: INW is ( port -- word ) and OUTW is ( word port -- ).
Verify this matches the kernel convention before writing. The HARDWARE
vocab has @-PORT and W@-PORT — check which naming the kernel uses.

### Block 285 — AC97 Bus Master DMA: BDL init

The AC97 Bus Master DMA uses a Buffer Descriptor List (BDL).
Each entry is 8 bytes: physical_address (4 bytes) + sample_count:flags
(4 bytes). Up to 32 entries in the list (indices 0-31, ring buffer).

NABMBAR offsets for PCM output (PCO = PCM Out):
  0x10 = PCO Buffer Descriptor List Base Address (32-bit phys addr)
  0x14 = PCO Current Entry Number
  0x15 = PCO Last Valid Entry (LVI) — index of last valid descriptor
  0x16 = PCO Status Register
  0x18 = PCO Position in Current Buffer
  0x1B = PCO Control Register

```forth
\ BDL buffer: 32 entries * 8 bytes = 256 bytes
\ Place at a fixed physical address above kernel space
\ 0x60000 = 384KB — well above kernel (0x7E00-0x2FFFF) + dict (0x30000)
60000 CONSTANT BDL-BASE
\ Each PCM sample buffer: 4KB (2048 16-bit stereo samples at 44100 Hz)
\ = ~23ms of audio per buffer
1000 CONSTANT PCM-BUF-SIZE    \ 4096 bytes per buffer
\ Place PCM buffers above BDL
61000 CONSTANT PCM-BUF-BASE   \ 32 buffers * 4096 = 128KB needed

\ BDL-ENTRY! ( phys-addr samples flags entry# -- )
\ Write one BDL entry
: BDL-ENTRY! ( phys samples flags n -- )
  8 * BDL-BASE +            \ entry address in BDL
  >R                        \ save entry addr
  R@ !                      \ write physical address
  ROT 10 LSHIFT ROT OR      \ samples:flags dword
  R> 4 + !                  \ write samples+flags
;

\ BDL-INIT ( -- ) Initialize BDL with PCM-BUF-SIZE buffers
: BDL-INIT ( -- )
  20 0 DO                   \ 32 entries (0x20 = 32 decimal)
    I PCM-BUF-SIZE * PCM-BUF-BASE +  \ buffer phys addr
    PCM-BUF-SIZE DUP +      \ sample count (2 bytes/sample)
    0                       \ flags: 0 (no IOC)
    I                       \ entry number
    BDL-ENTRY!
  LOOP
;
```

### Block 286 — AC97 PCM output control

```forth
\ PCM-BDL-LOAD ( -- ) Load BDL base into hardware
: PCM-BDL-LOAD ( -- )
  BDL-BASE AC97-NABMBAR @ 10 + !-PORT  \ write phys addr
;

\ PCM-LVI! ( n -- ) Set Last Valid Index
: PCM-LVI! ( n -- )
  AC97-NABMBAR @ 15 + OUTB
;

\ PCM-STATUS ( -- word ) Read PCM output status
: PCM-STATUS ( -- word )
  AC97-NABMBAR @ 16 + INW
;

\ PCM-START ( -- ) Arm and start PCM DMA
: PCM-START ( -- )
  PCM-BDL-LOAD
  1F PCM-LVI!               \ 31 = last valid entry
  1 AC97-NABMBAR @ 1B + OUTB  \ set RPBM (run/pause bus master)
;

\ PCM-STOP ( -- ) Stop PCM DMA
: PCM-STOP ( -- )
  0 AC97-NABMBAR @ 1B + OUTB
;

\ AC97-INIT ( -- ok? ) Full AC97 initialization sequence
: AC97-INIT ( -- ok? )
  AC97-FIND 0= IF FALSE EXIT THEN
  AC97-BARS
  AC97-RESET
  0 AC97-VOL!               \ max volume
  0 AC97-PCM-VOL!           \ max PCM volume
  DECIMAL 44100 HEX
  AC97-RATE!                \ 44100 Hz sample rate
  BDL-INIT
  2 AUDIO-MODE !
  TRUE
;
```

### Block 287 — PCM sample generation

Simple PCM data generators for test tones. These fill one PCM buffer
with a waveform at the given frequency. 16-bit signed stereo (L+R
interleaved = 4 bytes per sample frame).

```forth
VARIABLE PCM-PHASE          \ current waveform phase
0 PCM-PHASE !

\ SILENCE ( buf -- ) Fill buffer with silence (zeros)
: SILENCE ( buf -- )
  PCM-BUF-SIZE 0 FILL
;

\ SQUARE-WAVE ( freq buf -- ) Fill buffer with square wave
\ 44100 Hz, 16-bit signed, amplitude 0x2000
: SQUARE-WAVE ( freq buf -- )
  SWAP                      \ buf freq
  DECIMAL 44100 SWAP / HEX  \ period = 44100/freq (samples)
  SWAP                      \ period buf
  PCM-BUF-SIZE DUP + 0 DO   \ loop over bytes (2 per sample)
    PCM-PHASE @ OVER <      \ phase < half-period?
    IF 2000 ELSE E000 THEN  \ +8192 or -8192
    OVER I + W!             \ write left channel
    OVER I 2 + + W!         \ write right channel
    PCM-PHASE @ 1 + DUP     \ increment phase
    OVER >= IF DROP 0 THEN  \ wrap at period
    PCM-PHASE !
    4 +LOOP                 \ advance 4 bytes per frame
  2DROP
;
```

NOTE: W! writes a 16-bit word. Verify this exists in kernel or use
two C! calls. If W! is absent: `DUP FF AND OVER C!  8 RSHIFT SWAP
1+ C!` is the fallback.

### Block 288 — HDA MMIO base

Intel HDA (High Definition Audio) uses MMIO-mapped registers, not
I/O ports. The MMIO base comes from PCI BAR0. On HP 15-bs0xx the
device ID is typically 9D70 (Sunrise Point-LP HD Audio, 8086:9D70).

HDA MMIO register map (offsets from HDABAR):
  0x08 = STATESTS — codec status (which codecs responded)
  0x0C = GCTL — global control (CRST bit = codec reset)
  0x18 = WAKEEN — wake enable
  0x20 = INTCTL — interrupt control
  0x40 = CORBLBASE — CORB lower base (physical addr)
  0x44 = CORBUBASE — CORB upper base (must be 0 for <4GB)
  0x48 = CORBWP — CORB write pointer
  0x4A = CORBRP — CORB read pointer
  0x4C = CORBCTL — CORB control
  0x50 = RIRBLBASE — RIRB lower base
  0x54 = RIRBUBASE — RIRB upper base
  0x58 = RIRBWP — RIRB write pointer
  0x5A = RINTCNT — response interrupt count
  0x5C = RIRBCTL — RIRB control

```forth
\ HDA PCI IDs (multiple variants — scan by vendor only)
VARIABLE HDA-BAR            \ MMIO base address
0 HDA-BAR !
VARIABLE HDA-BUS  0 HDA-BUS !
VARIABLE HDA-DEV  0 HDA-DEV !

\ HDA-FIND ( -- found? ) Find HDA by class code (04:03:00)
\ Class 04h = Multimedia, Subclass 03h = HDA, ProgIF 00h
: HDA-FIND ( -- found? )
  4 0 DO
    20 0 DO
      J I 0 8 PCI-READ      \ class:subclass:progif:rev
      FFFFFF00 AND           \ mask revision
      40300 00 = IF          \ class 04:03:00
        J HDA-BUS !
        I HDA-DEV !
        TRUE UNLOOP UNLOOP EXIT
      THEN
    LOOP
  LOOP
  FALSE
;

\ HDA-BARS ( -- ) Read HDA BAR0 MMIO address
: HDA-BARS ( -- )
  HDA-BUS @ HDA-DEV @ 0 10 PCI-READ  \ BAR0
  FFFFFFF0 AND HDA-BAR !
;

\ HDA@ ( reg -- val ) Read HDA MMIO register (32-bit)
: HDA@ ( reg -- val )
  HDA-BAR @ + @
;

\ HDA! ( val reg -- ) Write HDA MMIO register (32-bit)
: HDA! ( val reg -- )
  HDA-BAR @ + !
;

\ HDAB@ ( reg -- byte ) Read HDA MMIO byte
: HDAB@ ( reg -- byte )
  HDA-BAR @ + C@
;

\ HDAB! ( byte reg -- ) Write HDA MMIO byte
: HDAB! ( byte reg -- )
  HDA-BAR @ + C!
;
```

NOTE: For HDA, the class code search is more reliable than device ID
because Intel changes the device ID across chipset generations. The
class/subclass 04:03 is constant for all HDA implementations.

### Block 289 — HDA CORB/RIRB + codec verb

HDA communicates with codecs via verbs sent through the CORB (Command
Outbound Ring Buffer) and responses received via RIRB (Response Inbound
Ring Buffer). Each CORB entry is a 32-bit verb; each RIRB entry is 64
bits (response + codec address).

The verb format is: codec_addr:3 | node_id:8 | verb:12 | payload:8

```forth
\ CORB/RIRB buffers — place above BDL space
62000 CONSTANT CORB-BASE    \ 256 entries * 4 bytes = 1KB
63000 CONSTANT RIRB-BASE    \ 256 entries * 8 bytes = 2KB

\ HDA-CORB-INIT ( -- ) Initialize CORB ring buffer
: HDA-CORB-INIT ( -- )
  CORB-BASE 40 HDA!         \ CORBLBASE = physical addr
  0 44 HDA!                 \ CORBUBASE = 0 (below 4GB)
  FFFF 4A HDA!              \ reset CORB read pointer
  0 48 HDA!                 \ CORB write pointer = 0
  2 4C HDAB!                \ CORBRUN: start CORB DMA
;

\ HDA-RIRB-INIT ( -- ) Initialize RIRB ring buffer
: HDA-RIRB-INIT ( -- )
  RIRB-BASE 50 HDA!         \ RIRBLBASE = physical addr
  0 54 HDA!                 \ RIRBUBASE = 0
  FFFF 58 HDA!              \ reset RIRB write pointer
  1 5A HDA!                 \ RINTCNT = respond every 1 entry
  2 5C HDAB!                \ RIRRRUN: start RIRB DMA
;

\ HDA-VERB! ( verb -- ) Send a codec verb via CORB
VARIABLE CORB-WP  0 CORB-WP !

: HDA-VERB! ( verb -- )
  CORB-WP @ 1 + FF AND      \ increment and wrap write pointer
  DUP CORB-WP !
  OVER DUP +                \ offset = wp * 4 (cell size)
  CORB-BASE + !             \ write verb to CORB
  CORB-WP @ 48 HDA!         \ update hardware write pointer
;

\ HDA-RESP@ ( -- resp ) Read last RIRB response (poll)
: HDA-RESP@ ( -- resp )
  20 0 DO                   \ poll up to 32 times
    58 HDA@ FF AND CORB-WP @ =  \ RIRBWP == CORBWP?
    IF
      CORB-WP @ 8 * RIRB-BASE +  \ RIRB entry addr
      @                     \ read 32-bit response (low half)
      UNLOOP EXIT
    THEN
    DECIMAL 1000 US-DELAY HEX
  LOOP
  FFFF FFFF                 \ timeout: return 0xFFFFFFFF
;
```

### Block 290 — HDA stream descriptor + full init

```forth
\ HDA stream descriptor base (Stream 1 = PCM out, offset 0x80)
\ SD0CTL (0x80), SD0STS (0x83), SD0LPIB (0x84), SD0CBL (0x88)
\ SD0LVI (0x8C), SD0FMT (0x92), SD0BDPL (0x98), SD0BDPU (0x9C)

\ HDA-STREAM-INIT ( -- ) Init stream 1 for 44100 16-bit stereo
: HDA-STREAM-INIT ( -- )
  BDL-BASE 98 HDA!          \ BD list physical addr (reuse AC97 BDL)
  0 9C HDA!                 \ upper 32 bits = 0
  PCM-BUF-SIZE 20 * 88 HDA! \ CBL = buffer size * 32 entries
  1F 8C HDAB!               \ LVI = 31 (last valid index)
  4011 92 HDA!              \ FMT: 44100Hz, 16-bit, stereo
;

\ HDA-STREAM-START ( -- ) Start stream 1 DMA
: HDA-STREAM-START ( -- )
  2 80 HDAB!                \ SD0CTL: stream enable
;

\ HDA-STREAM-STOP ( -- ) Stop stream 1 DMA
: HDA-STREAM-STOP ( -- )
  0 80 HDAB!
;

\ HDA-RESET ( -- ) Full controller reset
: HDA-RESET ( -- )
  0 C HDA!                  \ GCTL: clear CRST
  DECIMAL 100 1000 * US-DELAY HEX
  1 C HDA!                  \ GCTL: set CRST
  DECIMAL 100 1000 * US-DELAY HEX
  \ Wait for codec(s) to appear
  10 0 DO
    8 HDA@ 0<> IF UNLOOP EXIT THEN
    DECIMAL 1000 US-DELAY HEX
  LOOP
;

\ HDA-INIT ( -- ok? ) Full HDA initialization
: HDA-INIT ( -- ok? )
  HDA-FIND 0= IF FALSE EXIT THEN
  HDA-BARS
  HDA-RESET
  HDA-CORB-INIT
  HDA-RIRB-INIT
  HDA-STREAM-INIT
  3 AUDIO-MODE !
  TRUE
;
```

### Block 291 — AUDIO-INIT (auto-detect) + AUDIO-TEST

```forth
\ AUDIO-INIT ( -- ) Auto-detect and initialize best available audio
: AUDIO-INIT ( -- )
  ." Audio: " CR
  HDA-INIT IF
    ." HDA ok " CR EXIT
  THEN
  AC97-INIT IF
    ." AC97 ok " CR EXIT
  THEN
  \ Fall back to PC speaker
  1 AUDIO-MODE !
  ." Speaker" CR
;

\ AUDIO-TEST ( -- ) Quick audio self-test based on mode
: AUDIO-TEST ( -- )
  AUDIO-MODE @ 0= IF
    ." No audio device" CR EXIT
  THEN
  AUDIO-MODE @ 1 = IF
    DECIMAL 440 200 BEEP    \ A4 for 200ms
    HEX EXIT
  THEN
  \ AC97 or HDA: fill first PCM buffer with 440Hz square wave
  DECIMAL 440 PCM-BUF-BASE SQUARE-WAVE HEX
  ." PCM buffer loaded" CR
;

\ NET-FLUSH wrapper: ensure audio config string ends properly
: AUDIO-STATUS ( -- )
  ." Mode: " AUDIO-MODE @ . CR
;

ONLY FORTH DEFINITIONS
```

## Part 2: tests/test_audio.py

Follow the socket-based pattern of test_graphics.py. 12 test cases:

```python
def test_audio_load():
    """AUDIO vocabulary loads without errors"""

def test_using_audio():
    """USING AUDIO adds to search order"""

def test_pit_constants():
    """PIT port constants are correct (42, 43, 61)"""

def test_speaker_on_off():
    """SPEAKER-ON sets port 0x61 bits, SPEAKER-OFF clears them"""
    # Read port 0x61 before/after, verify bits 0-1

def test_beep_runs():
    """BEEP 440 100 completes without crash, stack clean"""
    # 100ms beep, fast enough to not slow test suite

def test_play_scale():
    """PLAY-SCALE runs and returns clean stack"""

def test_chromatic_table():
    """CHROMATIC table: index 0 = 261 (C4), index 9 = 440 (A4)"""
    # CHROMATIC 0 + @ . → 261
    # CHROMATIC 18 + @ . → 440

def test_ac97_constants():
    """AC97 vendor/device constants defined"""
    # AC97-VENDOR = 0x8086, AC97-DEVICE = 0x2415

def test_audio_mode_var():
    """AUDIO-MODE variable initialized to 0"""

def test_bdl_base():
    """BDL-BASE = 0x60000, PCM-BUF-BASE = 0x61000"""

def test_audio_init():
    """AUDIO-INIT runs without crash (speaker fallback in QEMU)"""
    # QEMU may not have AC97 or HDA depending on launch flags
    # Speaker fallback always works

def test_audio_test():
    """AUDIO-TEST produces a beep and clean stack in QEMU"""
    # With speaker fallback, this is a 440Hz beep
```

## Part 3: QEMU launch flags for AC97

The default QEMU launch in Makefile may not include AC97. Add:

```makefile
# For AUDIO tests: add -soundhw ac97 or -device AC97
QEMU_AUDIO_FLAGS = -device AC97 -audiodev none,id=audio0
```

The `-audiodev none,id=audio0` suppresses audio output to the host
while still emulating the AC97 hardware registers — correct for testing.

Check the current Makefile QEMU invocation and add these flags to the
test-audio target. The existing `make test` should not require audio —
only the audio-specific test target needs AC97 flags.

## Part 4: Memory map check

The BDL at 0x60000 and PCM buffers at 0x61000 must not collide with
any existing ForthOS allocation. Current memory map:

```
0x00000 - 0x003FF   IVT
0x00400 - 0x004FF   BIOS data area
0x07C00 - 0x07DFF   Boot sector
0x07E00 - 0x0FFFF   Kernel code (~55KB used, ~10KB headroom)
0x10000 - 0x1FFFF   Data stack (grows down)
0x20000 - 0x2FFFF   Return stack (grows down)
0x28000 - 0x291FF   System variables + block buffers
0x29C00 - 0x29C3F   ISR_HOOK_TABLE (16 slots * 4 bytes)
0x30000 - 0x7FFFF   Dictionary (~320KB)
0x60000             ← BDL-BASE (proposed)
0x61000             ← PCM-BUF-BASE (proposed)
0xA0000             GFX framebuffer (Mode 13h)
0xB8000             VGA text buffer
```

0x60000 is within the dictionary range (0x30000-0x7FFFF). This is a
COLLISION. The BDL and PCM buffers need to go above 0x80000.

CORRECTED allocation:
```
80000 CONSTANT BDL-BASE      \ 512KB — above dictionary
81000 CONSTANT PCM-BUF-BASE  \ 516KB — 32 buffers * 4KB = 128KB
                              \ PCM buffers end at 0xA1000
                              \ safe gap before 0xA0000 framebuffer
```

WAIT — 0xA0000 is the Mode 13h framebuffer. PCM buffers at 0x81000 +
128KB = 0xA1000 would OVERLAP the framebuffer. The graphics framebuffer
starts at 0xA0000 and extends 64KB to 0xAFFFF.

FINAL corrected allocation (DMA buffers must be below VGA):
```
\ Place DMA buffers between dictionary end and VGA
\ Dictionary: 0x30000-0x7FFFF (512KB)
\ Safe zone: 0x80000-0x9FFFF (128KB available)
80000 CONSTANT BDL-BASE      \ 512KB
80100 CONSTANT PCM-BUF-BASE  \ 512KB + 256 (BDL is 32*8=256 bytes)
\ 32 PCM buffers * 4096 bytes = 128KB → ends at 0xA0100
```

Still tight. The cleanest solution: use smaller PCM buffers (1KB each):
```
400 CONSTANT PCM-BUF-SIZE    \ 1KB per buffer (512 samples, ~11ms)
80000 CONSTANT BDL-BASE      \ 256 bytes for 32 BDL entries
80100 CONSTANT PCM-BUF-BASE  \ 32 * 1024 = 32KB → ends at 0x88100
```

This leaves 0x88100-0x9FFFF clear. Use PCM-BUF-SIZE = 0x400 throughout.
Document this collision analysis prominently in the source file.

## Sequence of Events for Claude Code

1. Verify memory map collision analysis above against current forth.asm
   constants and dictionary size. Confirm BDL-BASE=0x80000 is safe.

2. Create forth/dict/audio.fth using Track A first (blocks 280-282),
   then Track B (283-287), then Track C (288-291).

3. Line-length check:
   ```bash
   awk 'length > 64 {print NR": "length": "$0}' forth/dict/audio.fth
   ```

4. Update QEMU Makefile target for audio tests:
   - Add test-audio target with -device AC97 -audiodev none,id=audio0
   - Do NOT add AC97 to the default test target (avoid breaking existing)

5. Create tests/test_audio.py

6. Build and run:
   ```bash
   make clean && make && make blocks && make write-catalog
   make write-catalog 2>&1 | grep AUDIO
   python3 tests/test_audio.py [port]
   ```

7. Full regression — all existing tests must still pass:
   ```bash
   make test
   ```

8. Commit:
   ```
   Add AUDIO vocabulary: PC speaker + AC97 + Intel HDA

   Track A: PC speaker via PIT Ch2 + port 0x61
   - SPEAKER-ON SPEAKER-OFF BEEP TONE
   - NOTE (MIDI# lookup, 2-octave table)
   - PLAY-SCALE demo word

   Track B: AC97 Bus Master DMA (QEMU 8086:2415)
   - AC97-FIND AC97-BARS AC97-RESET AC97-VOL! AC97-RATE!
   - BDL-INIT PCM-START PCM-STOP PCM-STATUS
   - SQUARE-WAVE SILENCE PCM sample generators

   Track C: Intel HDA MMIO (HP Sunrise Point)
   - HDA-FIND (class code 04:03:00 search)
   - HDA-RESET CORB/RIRB init HDA-VERB! HDA-RESP@
   - HDA-STREAM-INIT HDA-STREAM-START HDA-STREAM-STOP

   AUDIO-INIT: auto-detect HDA → AC97 → speaker fallback
   AUDIO-MODE variable: 0=none 1=speaker 2=AC97 3=HDA
   Blocks 280-291, 12/12 tests passing
   Memory: BDL at 0x80000, PCM bufs at 0x80100 (safe zone)
   ```

## Implementation Pitfalls

### OUTW vs OUTB for AC97 mixer
AC97 mixer registers are WORD-wide (16-bit). Use OUTW ( word port -- )
not OUTB. INW is ( port -- word ). Verify the kernel has INW/OUTW —
they're in the hardware vocab but check forth.asm directly.

### HDA MMIO vs I/O ports
HDA uses MMIO (@ ! C@) at the BAR0 address — NOT I/O ports (INB OUTB).
This is the opposite of AC97. A common mistake is mixing them.

### CORB verb format
The full HDA verb is 32 bits: caddr(3) | nid(8) | verb(12) | payload(9).
Getting this wrong silently sends verbs to the wrong node. For initial
codec enumeration, use caddr=0, nid=0 (root node), verb=F00 (get params).

### UNLOOP in nested DO/LOOP
UNLOOP cleans up the DO/LOOP machinery before EXIT. Without UNLOOP before
EXIT from within a DO/LOOP, the return stack is corrupted. Verify UNLOOP
exists in the kernel — it's Forth standard but double-check.

### AC97 warm reset vs cold reset
Writing 0 to mixer register 0x00 is a warm reset (codec stays powered).
If the codec doesn't respond after warm reset, try toggling the ACLINK
reset (NABMBAR+0x2C bit 1). QEMU's AC97 emulation responds to warm reset.

### BDL physical addresses
In ForthOS bare metal with identity paging, virtual address = physical
address. BDL-BASE and PCM-BUF-BASE are used directly as physical
addresses in hardware descriptor fields. No VIRT>PHYS translation needed.

### The 64-char line limit and MMIO register comments
HDA has many registers with long descriptive names. Comments will be
tempting but must stay within the line budget. Use register offset
numbers in comments, not full names: `\ 0x40 = CORBLBASE` fits.

## Connection to A/V Phases

Phase 1 (GRAPHICS): pixel primitives, VSYNC, TAQOZ naming ✓ done
Phase 2 (this task): AUDIO — speaker + AC97 + HDA, TONE, NOTE, BEEP
Phase 3 (VIDEO): TAQOZ BMV360.TASK port, BMP frame loop, AV loop
Phase 4 (AV-SYNC): IRQ-driven audio DMA fill during video frame display

The SQUARE-WAVE word in Block 287 is the bridge to Phase 3 — it fills
PCM buffers the same way BLIT-FRAME fills video framebuffer rows. The
AV-SYNC compositor will call both in a synchronized frame loop.
