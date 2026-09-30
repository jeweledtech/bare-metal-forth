\ ============================================
\ CATALOG: FIRSTBOOT
\ CATEGORY: app
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: medium
\ REQUIRES: UI-CORE
\ REQUIRES: UI-EVENTS
\ REQUIRES: PCI-ENUM
\ REQUIRES: CATALOG-RESOLVER
\ ============================================
\ First-boot wizard, Try mode. Spec:
\ docs/TASK_FORTHOS_FIRSTBOOT.md s.8 steps
\ 1-3. Keyboard only, VGA text 80x25.
\ ============================================
\
\ Detect, then offer only what this machine
\ can drive; say why the rest is greyed.
\
\ Screens built here: 1 (Try or Install,
\ with gates), 2 (network detection and
\ the offline path), 4 (completion).
\ NOT built: 2a (wired address) and 3
\ (install target). Both are named on
\ screen as not built; neither is reached.
\
\ The Try path writes nothing to any disk.
\
\ Usage:
\   USING FIRSTBOOT  FIRSTBOOT-RUN
\ ============================================

VOCABULARY FIRSTBOOT
FIRSTBOOT DEFINITIONS
ALSO UI-CORE
ALSO UI-EVENTS
ALSO PCI-ENUM
ALSO CATALOG-RESOLVER

HEX
8086 CONSTANT WZ-INTEL
10EC CONSTANT WZ-REALTEK
8168 CONSTANT WZ-D8168
8139 CONSTANT WZ-D8139
8029 CONSTANT WZ-D8029
DECIMAL

8 CONSTANT ATTR-DIM
114 CONSTANT KEY-LC-R
82 CONSTANT KEY-UC-R

\ ---- Text builder ------------------------
\ One line at a time, then ADD-LABEL copies
\ it into the widget pool.
CREATE WZ-BUF 96 ALLOT
VARIABLE WZ-LEN

: WZ-CLR ( -- ) 0 WZ-LEN ! ;
: WZ-C ( c -- )
  WZ-LEN @ 90 < IF
    WZ-BUF WZ-LEN @ + C!  1 WZ-LEN +!
  ELSE DROP THEN ;
: WZ-S ( a l -- )
  DUP 0 > IF
    0 DO DUP I + C@ WZ-C LOOP
  ELSE DROP THEN DROP ;
: WZ-TXT ( -- a l ) WZ-BUF WZ-LEN @ ;

\ Lower-case copy (vocab name -> file).
: WZ-S-LC ( a l -- )
  DUP 0 > IF
    0 DO
      DUP I + C@
      DUP 65 >= OVER 90 <= AND IF
        32 +
      THEN WZ-C
    LOOP
  ELSE DROP THEN DROP ;

: WZ-HEXD ( n -- )
  15 AND DUP 9 > IF 7 + THEN 48 + WZ-C ;
: WZ-H2 ( n -- ) DUP 4 RSHIFT WZ-HEXD WZ-HEXD ;
: WZ-H4 ( n -- ) DUP 8 RSHIFT WZ-H2 WZ-H2 ;
: WZ-H8 ( n -- ) DUP 16 RSHIFT WZ-H4 WZ-H4 ;

\ Unsigned decimal, 0-999.
: WZ-N ( u -- )
  DUP 9 > IF
    DUP 99 > IF
      DUP 100 / 48 + WZ-C  100 MOD
    THEN
    DUP 10 / 48 + WZ-C  10 MOD
  THEN 48 + WZ-C ;

\ ---- PCI table entry fields --------------
\ PCI-ENUM entry: +0 bus +1 dev +2 func
\ +4 vendor(w) +6 device(w) +8 class +9 sub
: WZ-E-BDF ( e -- b d f )
  DUP C@ OVER 1+ C@ ROT 2 + C@ ;
: WZ-S-BDF ( e -- )
  DUP C@ WZ-H2  58 WZ-C
  DUP 1+ C@ WZ-H2  46 WZ-C
  2 + C@ WZ-HEXD ;
: WZ-S-ID ( e -- )
  DUP 4 + W@ WZ-H4  58 WZ-C
  6 + W@ WZ-H4 ;

\ ---- Is a vocabulary here? --------------
\ Loaded = its VOCABULARY word is in the
\ FORTH chain. On the stick = the catalog
\ lists it (loadable, not yet loaded).
\ NOT kernel FIND: it ignores its argument
\ and searches word_buffer (the last word
\ the interpreter parsed). So walk the
\ chain: header = link(4) flags+len(1) name.
HEX
28048 CONSTANT WZ-FORTH-LATEST
3F CONSTANT WZ-LENMASK
40 CONSTANT WZ-HIDDEN
DECIMAL
VARIABLE WZ-FA
VARIABLE WZ-FL
: WZ-LOADED? ( a l -- flag )
  WZ-FL ! WZ-FA !
  WZ-FORTH-LATEST @
  BEGIN DUP WHILE
    DUP 4 + C@ DUP WZ-HIDDEN AND 0= IF
      WZ-LENMASK AND WZ-FL @ = IF
        DUP 5 + WZ-FL @ WZ-FA @ WZ-FL @
        STR= IF DROP TRUE EXIT THEN
      THEN
    ELSE DROP THEN
    @
  REPEAT ;

\ 0 = absent, 1 = loaded, 2 = on stick
: WZ-VSTAT ( a l -- n )
  2DUP WZ-LOADED? IF 2DROP 1 EXIT THEN
  CATALOG-FIND IF 2DROP 2 ELSE 0 THEN ;
: WZ-S-VSTAT ( n -- )
  DUP 1 = IF DROP S" loaded" WZ-S EXIT THEN
  2 = IF S" on this stick" WZ-S
  ELSE S" not present" WZ-S THEN ;

\ ---- Greyed rows ------------------------
\ UI-CORE draws every label ATTR-NORM, so
\ greying is a repaint after FORM-RENDER.
\ Greyed rows are labels: never focusable.
CREATE WZ-GREY 25 ALLOT
: WZ-GREY-CLR ( -- ) WZ-GREY 25 0 FILL ;
: WZ-GREY! ( row -- ) WZ-GREY + 1 SWAP C! ;
: WZ-DIM-ROW ( row -- )
  80 0 DO
    I OVER VGA-AT 1+ ATTR-DIM SWAP C!
  LOOP DROP ;
: WZ-PAINT ( -- )
  25 0 DO
    WZ-GREY I + C@ IF I WZ-DIM-ROW THEN
  LOOP ;
: WZ-DRAW ( -- ) FORM-RENDER WZ-PAINT ;

\ ---- Widgets ----------------------------
\ WT-ALLOC does not clear a slot, and a
\ digit key past the last button makes
\ BUTTON-ACTIVATE run widget 0's XT. Zero
\ it on every label so that is a no-op.
: WZ-LBL ( x y a l -- ) ADD-LABEL 0 W-XT! ;
: WZ-TLBL ( x y -- ) WZ-TXT WZ-LBL ;
: WZ-BEGIN ( -- ) WT-RESET WZ-GREY-CLR ;
: WZ-TITLE ( a l -- )
  1 0 2SWAP WZ-LBL  1 ADD-DIVIDER ;
: WZ-KEYS ( a l -- )
  23 ADD-DIVIDER  1 24 2SWAP WZ-LBL ;
: WZ-FOCUS-LAST ( -- )
  WT-COUNT @ 1- FOCUS-IDX ! ;

VARIABLE WZ-SCREEN

\ ---- Storage classification -------------
\ 1 AHCI  2 NVMe  3 Intel RAID (VMD/RST)
\ 4 IDE   5 other storage
: WZ-STOR-KIND ( vendor sub progif -- k )
  OVER 6 = IF
    NIP NIP 1 = IF 1 ELSE 5 THEN EXIT
  THEN DROP
  DUP 8 = IF 2DROP 2 EXIT THEN
  DUP 4 = IF
    DROP WZ-INTEL = IF 3 ELSE 5 THEN EXIT
  THEN
  1 = IF DROP 4 EXIT THEN
  DROP 5 ;

\ First PCI entry of each kind (0 = none).
CREATE WZ-KE 24 ALLOT
: WZ-KE@ ( k -- e|0 ) 4 * WZ-KE + @ ;
: WZ-STOR-SCAN ( -- )
  WZ-KE 24 0 FILL
  PCI-COUNT @ DUP 0 > IF
    0 DO
      I PCI-ENTRY DUP 8 + C@ 1 = IF
        DUP 4 + W@ OVER 9 + C@
        2 PICK WZ-E-BDF PCI-PROGIF@
        WZ-STOR-KIND 4 * WZ-KE +
        DUP @ 0= IF ! ELSE 2DROP THEN
      ELSE DROP THEN
    LOOP
  ELSE DROP THEN ;

\ ---- Gates ------------------------------
\ Each appends "pass  why" or "FAIL  why"
\ to the line being built.

\ G-BOOT: NOT IMPLEMENTED (placeholder, like
\ screens 2a and 3). It needs two inputs
\ this kernel does not have: boot-path
\ provenance (UEFI-3's multiboot2 entry
\ supplies it) and whether the firmware
\ offers a legacy entry. "----" not "pass":
\ unmeasured must not print like passed.
\ Fail-closed, so Install stays shut; the
\ real protection today is G-DISK+G-SPACE.
: WZ-G-BOOT ( -- flag )
  S" ----  not implemented: needs boot-" WZ-S
  S" path provenance" WZ-S FALSE ;

\ G-DISK. PCI class 01 only: this names a
\ controller the disk stack can reach. Disk
\ presence behind it is screen 3's check.
: WZ-G-DISK ( -- flag )
  WZ-STOR-SCAN
  1 WZ-KE@ ?DUP IF
    S" AHCI" WZ-VSTAT IF
      S" pass  AHCI at " WZ-S DUP WZ-S-BDF
      S"   ABAR " WZ-S
      WZ-E-BDF 5 PCI-BAR@ WZ-H8 TRUE EXIT
    THEN
    S" FAIL  AHCI at " WZ-S WZ-S-BDF
    S" , no AHCI vocabulary" WZ-S
    FALSE EXIT
  THEN
  2 WZ-KE@ ?DUP IF
    S" FAIL  NVMe " WZ-S DUP WZ-S-ID
    S"  at " WZ-S WZ-S-BDF
    S"  -- no NVMe vocabulary" WZ-S
    FALSE EXIT
  THEN
  3 WZ-KE@ ?DUP IF
    S" FAIL  disks behind Intel VMD/RST " WZ-S
    WZ-S-ID FALSE EXIT
  THEN
  5 WZ-KE@ ?DUP IF
    S" FAIL  storage " WZ-S DUP WZ-S-ID
    S"  class 01/" WZ-S 9 + C@ WZ-H2
    S"  not supported" WZ-S FALSE EXIT
  THEN
  4 WZ-KE@ IF
    S" FAIL  IDE only -- not an install" WZ-S
    S"  target" WZ-S FALSE EXIT
  THEN
  S" FAIL  no storage controller found" WZ-S
  FALSE ;

\ G-SPACE. The GPT checks (GPT-ARM,
\ FREE-SLOT, FREE-EXTENT) live in INSTALL
\ and read the disk through a bound reader;
\ none of that is loaded on the Try path.
\ A full-tier caller binds an xt here:
\ ( -- flag ), appending its own reason.
\ Unbound = FAIL. Unchecked is not a pass.
VARIABLE WZ-SPACE-XT
0 WZ-SPACE-XT !
: WZ-G-SPACE ( -- flag )
  WZ-SPACE-XT @ ?DUP IF EXECUTE EXIT THEN
  S" FAIL  not checked -- needs the" WZ-S
  S"  INSTALL disk stack" WZ-S FALSE ;

\ ---- Screen 4: completion ---------------
\ Approved copy, s.7. Headline by path:
\ Try says "session is ready" (nothing was
\ installed; the approved line is false
\ there). Install (screen 3, not built)
\ sets WZ-INSTALLED for the approved line.
\ The support block (B, C) is drawn on
\ BOTH paths, unconditionally.
\ Fits 80x25 on one page.
VARIABLE WZ-INSTALLED
0 WZ-INSTALLED !
: WZ-DONE ( -- ) 1 QUIT-FLAG ! ;

: WZ-HEADLINE ( -- )
  WZ-INSTALLED @ IF
    WZ-CLR S" Your ForthOS installation" WZ-S
    S"  is complete." WZ-S 2 2 WZ-TLBL
  ELSE
    2 2 S" Your ForthOS session is ready."
    WZ-LBL
  THEN ;

: WZ-S4-A ( -- )
  WZ-HEADLINE
  WZ-CLR S" You are about to enter the" WZ-S
  S"  Forth Dimension." WZ-S 2 3 WZ-TLBL
  WZ-CLR S" Here the dictionary is the" WZ-S
  S"  system: every word you define" WZ-S
  S"  is live the" WZ-S 2 5 WZ-TLBL
  WZ-CLR S" moment you type it, and any" WZ-S
  S"  address, pointer or register" WZ-S
  S"  is yours to read" WZ-S 2 6 WZ-TLBL
  WZ-CLR S" and write. A guide to your" WZ-S
  S"  first session is at" WZ-S
  S"  docs.jeweledtech.com." WZ-S
  2 7 WZ-TLBL ;

: WZ-S4-B ( -- )
  WZ-CLR S" ForthOS is built by a small" WZ-S
  S"  team who work on it in their" WZ-S
  S"  spare time, around" WZ-S 2 9 WZ-TLBL
  WZ-CLR S" the other businesses they" WZ-S
  S"  run. Even as a volunteer" WZ-S
  S"  project there is" WZ-S 2 10 WZ-TLBL
  WZ-CLR S" bandwidth to pay for and" WZ-S
  S"  registrations to keep current." WZ-S
  S"  If you find ForthOS" WZ-S 2 11 WZ-TLBL
  WZ-CLR S" useful, a donation of any" WZ-S
  S"  amount is always appreciated" WZ-S
  S"  -- and we will be" WZ-S 2 12 WZ-TLBL
  2 13 S" forever grateful." WZ-LBL ;

: WZ-S4-C ( -- )
  WZ-CLR S" SUPPORT  patreon.com/c/" WZ-S
  S" JeweledTechbyJollyGenius" WZ-S
  2 15 WZ-TLBL
  WZ-CLR S" STAR US  github.com/" WZ-S
  S" jeweledtech/bare-metal-forth" WZ-S
  2 16 WZ-TLBL
  WZ-CLR S" EXTEND   jeweledtech.github.io/" WZ-S
  S" bare-metal-forth -- private" WZ-S
  S"  vocabularies" WZ-S 2 17 WZ-TLBL
  WZ-CLR S"          (disk stack," WZ-S
  S"  networking, full hardware," WZ-S
  S"  UBT pipeline, metacompiler)" WZ-S
  2 18 WZ-TLBL
  WZ-CLR S"          reach the parts of a" WZ-S
  S"  machine the free core leaves" WZ-S
  S"  alone." WZ-S 2 19 WZ-TLBL ;

: WZ-S4 ( -- )
  WZ-BEGIN 4 WZ-SCREEN !
  S" ForthOS First Boot -- The Forth Dimension"
  WZ-TITLE
  WZ-S4-A WZ-S4-B WZ-S4-C
  2 21 4 S" ok" ['] WZ-DONE ADD-BUTTON
  WZ-FOCUS-LAST
  WZ-CLR S"  -- press ENTER to drop into" WZ-S
  S"  the interpreter." WZ-S 6 21 WZ-TLBL
  S" ENTER continue   ESC leave to ok" WZ-KEYS ;

\ ---- Screen 2: network ------------------
\ Every class-02 PCI function gets a row.
\ Driven (a vocabulary for its exact ID is
\ loaded or on the stick): a button.
\ Otherwise a greyed label naming the gap.
\ Continue-without-network is its own full
\ path, marked DEFAULT.
\
\ Focus starts on Continue in this build
\ even when a controller is driven: the
\ address screen (2a) is not built, so a
\ driven row would be a dead end.
: WZ-NIC-VOCAB ( vendor device -- a l | 0 0 )
  SWAP WZ-REALTEK <> IF DROP 0 0 EXIT THEN
  DUP WZ-D8168 = IF DROP S" RTL8168" EXIT THEN
  DUP WZ-D8139 = IF DROP S" RTL8139" EXIT THEN
  WZ-D8029 = IF S" NE2000" EXIT THEN
  0 0 ;

VARIABLE WZ-NROW
VARIABLE WZ-NNET
VARIABLE WZ-NDRV
VARIABLE WZ-MSG
18 CONSTANT WZ-NROW-MAX

\ Forward: the driven button's action
\ rebuilds screen 2, defined below it.
VARIABLE 'WZ-S2
: WZ-DRIVEN ( -- )
  1 WZ-MSG !  'WZ-S2 @ EXECUTE ;

: WZ-S-NETKIND ( e -- )
  9 + C@
  DUP 0 = IF DROP S" Ethernet" WZ-S EXIT THEN
  DUP 128 = IF DROP S" Wi-Fi 02/80" WZ-S EXIT THEN
  S" network 02/" WZ-S WZ-H2 ;

: WZ-NET-ROW ( e -- )
  WZ-CLR DUP WZ-S-ID S"  at " WZ-S
  DUP WZ-S-BDF S"   " WZ-S
  DUP 4 + W@ OVER 6 + W@ WZ-NIC-VOCAB
  DUP IF
    2DUP WZ-S-LC S" .fth " WZ-S
    WZ-VSTAT WZ-S-VSTAT
    S" , link not probed" WZ-S DROP
    2 WZ-NROW @ 70 WZ-TXT
    ['] WZ-DRIVEN ADD-BUTTON
    1 WZ-NDRV +!
  ELSE
    2DROP DUP WZ-S-NETKIND
    9 + C@ 128 = IF
      S"  -- not yet available, no 802.11" WZ-S
      S"  vocabulary" WZ-S
    ELSE
      S"  -- not yet available, no" WZ-S
      S"  vocabulary" WZ-S
    THEN
    2 WZ-NROW @ WZ-TLBL
    WZ-NROW @ WZ-GREY!
  THEN
  1 WZ-NROW +! ;

: WZ-NET-ROWS ( -- )
  3 WZ-NROW !  0 WZ-NNET !  0 WZ-NDRV !
  PCI-COUNT @ DUP 0 > IF
    0 DO
      I PCI-ENTRY DUP 8 + C@ 2 = IF
        1 WZ-NNET +!
        WZ-NROW @ WZ-NROW-MAX < IF
          WZ-NET-ROW
        ELSE DROP THEN
      ELSE DROP THEN
    LOOP
  ELSE DROP THEN
  WZ-NNET @ 0= IF
    2 3 S" No network controllers detected."
    WZ-LBL  4 WZ-NROW !
  THEN ;

: WZ-S2 ( -- )
  WZ-BEGIN 2 WZ-SCREEN !
  S" Network" WZ-TITLE
  WZ-NET-ROWS
  WZ-NROW @ 1+ WZ-NROW !
  2 WZ-NROW @ 30
  S" Continue without a network"
  ['] WZ-S4 ADD-BUTTON WZ-FOCUS-LAST
  32 WZ-NROW @ S" DEFAULT" WZ-LBL
  WZ-CLR S" PCI functions scanned: " WZ-S
  PCI-COUNT @ WZ-N
  S"    network controllers: " WZ-S
  WZ-NNET @ WZ-N
  S"    driven: " WZ-S WZ-NDRV @ WZ-N
  1 21 WZ-TLBL
  WZ-MSG @ IF
    WZ-CLR S" Wired address setup is not" WZ-S
    S"  built yet. Choose Continue." WZ-S
    1 22 WZ-TLBL
  THEN
  WZ-CLR S" TAB next   ENTER select   R" WZ-S
  S"  rescan   ESC leave to ok" WZ-S
  WZ-TXT WZ-KEYS
  0 WZ-MSG ! ;
' WZ-S2 'WZ-S2 !

\ ---- Screen 1: Try or Install ----------
VARIABLE WZ-GATES
: WZ-GATE-ROW ( xt a l row -- )
  >R WZ-CLR WZ-S EXECUTE
  0= IF 0 WZ-GATES ! THEN
  4 R> WZ-TLBL ;

: WZ-TO-S2 ( -- ) 0 WZ-MSG ! WZ-S2 ;

: WZ-S1 ( -- )
  WZ-BEGIN 1 WZ-SCREEN !
  S" ForthOS First Boot -- Try or Install"
  WZ-TITLE
  2 3 30 S" Run ForthOS from this stick"
  ['] WZ-TO-S2 ADD-BUTTON WZ-FOCUS-LAST
  WZ-CLR S" Settings and definitions" WZ-S
  S"  last until power-off." WZ-S
  4 4 WZ-TLBL
  4 5 S" Nothing is written to any disk."
  WZ-LBL
  -1 WZ-GATES !
  ['] WZ-G-BOOT S" G-BOOT   " 9 WZ-GATE-ROW
  ['] WZ-G-DISK S" G-DISK   " 10 WZ-GATE-ROW
  ['] WZ-G-SPACE S" G-SPACE  " 11 WZ-GATE-ROW
  WZ-CLR S" Install ForthOS on this" WZ-S
  S"  machine -- " WZ-S
  WZ-GATES @ IF
    S" gates pass; install screen" WZ-S
    S"  not built yet" WZ-S
  ELSE S" unavailable" WZ-S THEN
  2 7 WZ-TLBL  7 WZ-GREY!
  S" TAB next   ENTER select   ESC leave to ok"
  WZ-KEYS ;

\ ---- The loop --------------------------
\ FORM-RUN's loop plus the grey repaint and
\ R (rescan) on screen 2; every other key
\ goes to UI-EVENTS' HANDLE-KEY.
: WZ-KEY ( key -- )
  WZ-SCREEN @ 2 = IF
    DUP KEY-LC-R = OVER KEY-UC-R = OR IF
      DROP PCI-SCAN WZ-TO-S2 EXIT
    THEN
  THEN HANDLE-KEY ;

: FIRSTBOOT-RUN ( -- )
  PCI-SCAN  0 QUIT-FLAG !  0 WZ-MSG !
  WZ-S1
  BEGIN
    WZ-DRAW
    KEY WZ-KEY
    NET-FLUSH
    QUIT-FLAG @
  UNTIL
  VGA-CLS ;

ONLY FORTH DEFINITIONS
DECIMAL
