\ ============================================
\ CATALOG: VIDEO
\ CATEGORY: video
\ PLATFORM: x86
\ SOURCE: hand-written
\ PORTS: none (uses GRAPHICS/AUDIO ports)
\ MMIO: GFX-FB (via GRAPHICS)
\ CONFIDENCE: high
\ REQUIRES: GRAPHICS ( BLIT-ROW VSYNC-WAIT )
\ REQUIRES: AUDIO ( BEEP )
\ ============================================
\
\ Block-based video playback. TAQOZ BMV360.TASK
\ port for ForthOS. Reads frames from Forth
\ blocks, blits to VGA framebuffer, VSYNC-gated.
\
\ Usage:
\   USING VIDEO
\   500 VID-START !
\   500 45 VIDEO-PLAY-15
\   TV
\
\ ============================================

VOCABULARY VIDEO
VIDEO DEFINITIONS
ALSO GRAPHICS
ALSO AUDIO
HEX

\ ============================================
\ Frame geometry constants
\ ============================================
DECIMAL
320 CONSTANT VID-WIDTH
200 CONSTANT VID-HEIGHT
HEX
FA00 CONSTANT VID-FRAME-BYTES
3F   CONSTANT VID-FRAME-BLKS
4D42 CONSTANT BMP-MAGIC

\ Playback state
VARIABLE VID-START
0 VID-START !
VARIABLE VID-FRAME
0 VID-FRAME !
VARIABLE VID-PLAYING
0 VID-PLAYING !

\ ============================================
\ Frame-to-block mapping
\ ============================================

: FRAME-ADDR ( frame# -- blk# )
    VID-FRAME-BLKS * VID-START @ +
;

\ ============================================
\ Row blitting with block-boundary handling
\ ============================================
\ A 320-byte row may span two 1024-byte blocks
\ when block_offset > 704 (1024 - 320 = 2C0h).
\
\ For each row:
\   byte_off = row * 320
\   blk_idx  = byte_off / 1024
\   blk_off  = byte_off mod 1024
\   if blk_off + 320 <= 1024: single CMOVE
\   else: two CMOVEs across block boundary

VARIABLE BR-BLK
VARIABLE BR-OFF
VARIABLE BR-DST
VARIABLE BR-N1

: BLIT-ROW-AT ( row# start-blk# -- )
    SWAP VID-WIDTH *
    DUP 400 / ROT + BR-BLK !
    400 MOD BR-OFF !
    \ dst = GFX-FB + row * VID-WIDTH
    \ (already computed as VID-WIDTH * above)
    \ recompute: row * VID-WIDTH
    \ Actually: byte_off = row*320, so
    \ dst = GFX-FB + byte_off - blk_idx*1024
    \ Simpler: use row directly
;

\ Let me redo this cleanly with variables
VARIABLE BA-ROW

: BLIT-ROW-AT ( row# start-blk# -- )
    SWAP BA-ROW !
    BA-ROW @ VID-WIDTH *
    DUP 400 /
    ROT + BR-BLK !
    400 MOD BR-OFF !
    BA-ROW @ VID-WIDTH * GFX-FB +
    BR-DST !
    BR-OFF @ 2C0 > IF
        \ Row spans two blocks
        400 BR-OFF @ -
        BR-N1 !
        \ First part: BR-N1 bytes from block
        BR-BLK @ BLOCK BR-OFF @ +
        BR-DST @
        BR-N1 @ CMOVE
        \ Second part: remainder from next block
        BR-BLK @ 1+ BLOCK
        BR-DST @ BR-N1 @ +
        VID-WIDTH BR-N1 @ - CMOVE
    ELSE
        \ Fits in one block
        BR-BLK @ BLOCK BR-OFF @ +
        BA-ROW @ BLIT-ROW
    THEN
;

\ ============================================
\ Full frame blit
\ ============================================

: BLIT-FRAME ( start-blk# -- )
    VID-HEIGHT 0 DO
        I OVER BLIT-ROW-AT
    LOOP
    DROP
;

\ ============================================
\ BMP magic check
\ ============================================

: BMV-CHECK ( blk# -- ok? )
    BLOCK W@ BMP-MAGIC =
;

\ ============================================
\ Frame playback loop
\ ============================================

VARIABLE FL-FPS
VARIABLE FL-N
VARIABLE FL-BLK

: FRAME-LOOP ( start-blk nframes fps -- )
    FL-FPS ! FL-N ! FL-BLK !
    !POST
    1 VID-PLAYING !
    FL-N @ 0 DO
        FL-BLK @ I VID-FRAME-BLKS * +
        BLIT-FRAME
        VSYNC-WAIT
        VID-PLAYING @ 0= IF
            LEAVE
        THEN
    LOOP
    !TVOFF
    0 VID-PLAYING !
;

\ ============================================
\ High-level playback words
\ ============================================

: VIDEO-PLAY ( start-blk nframes -- )
    DECIMAL 30 HEX FRAME-LOOP
;

: VIDEO-PLAY-15 ( start-blk nframes -- )
    DECIMAL 15 HEX FRAME-LOOP
;

\ SLIDESHOW: show each frame, wait for KEY
: SLIDESHOW ( start-blk nframes -- )
    !POST SWAP
    0 DO
        DUP I VID-FRAME-BLKS * +
        BLIT-FRAME
        KEY DROP
    LOOP
    DROP !TVOFF
;

\ TAQOZ-compatible name (exact)
: BMV360.TASK ( start-blk nframes -- )
    VIDEO-PLAY-15
;

\ TV: play from VID-START default location
: TV ( -- )
    VID-START @ 0= IF
        ." Set VID-START" CR EXIT
    THEN
    VID-START @
    DECIMAL 45 HEX
    VIDEO-PLAY-15
;

\ ============================================
\ Info and diagnostics
\ ============================================

: VIDEO-INFO ( start-blk -- )
    ." VIDEO start=" . CR
    ." Frame blks: "
    VID-FRAME-BLKS DECIMAL . HEX CR
    ." Frame bytes: "
    VID-FRAME-BYTES DECIMAL . HEX CR
    ." 15fps = 66ms/frame" CR
    ." 30fps = 33ms/frame" CR
;

\ ============================================
\ Test frame generator
\ ============================================
\ Writes gradient pattern to blocks at
\ VID-START. Uses BUFFER (no read) + UPDATE.

VARIABLE TF-OFF
VARIABLE TF-BLK

: VIDEO-TEST-FRAME ( -- )
    VID-START @ 0= IF
        ." Set VID-START" CR EXIT
    THEN
    0 TF-OFF !
    VID-START @ TF-BLK !
    VID-HEIGHT 0 DO
        VID-WIDTH 0 DO
            TF-OFF @ 400 MOD 0= IF
                TF-OFF @ 0<> IF
                    UPDATE
                    TF-BLK @ 1+ TF-BLK !
                THEN
            THEN
            J I + FF AND
            TF-BLK @ BUFFER
            TF-OFF @ 400 MOD + C!
            TF-OFF @ 1+ TF-OFF !
        LOOP
    LOOP
    UPDATE
    SAVE-BUFFERS
    ." Test frame ok" CR
;

PREVIOUS PREVIOUS
FORTH DEFINITIONS
DECIMAL
