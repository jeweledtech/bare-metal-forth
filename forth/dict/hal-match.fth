\ ============================================
\ CATALOG: HAL-MATCH
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ REQUIRES: SMBIOS ( SM-FIND SM-STR SM-MEM= )
\ CONFIDENCE: medium
\ ============================================
\
\ Per-machine bindings, matched from SMBIOS
\ type 1 (manufacturer, product: exact).
\ An entry, as you would type it:
\   : X-IDS S" Maker" S" Product" ;
\   X-IDS MATCH-ENTRY
\   BINDS FB-BASE MY-BASE
\   X-NOTE MATCH-NOTE  ( a line, no bind )
\ Loading entries binds nothing: only
\ MATCH-BIND does, printing each BIND it
\ runs. No match: the defaults stay.
\ docs/TASK_HAL_MACHINE.md.
\
\   MATCH-BIND   bind for this machine
\   MATCH-LIST   every entry, its binds
\ ============================================

VOCABULARY HAL-MATCH
HAL-MATCH DEFINITIONS
ALSO HAL
ALSO SMBIOS
HEX

' FB-BASE @ CONSTANT DOVEC-CODE
VARIABLE MT-HEAD

: MT-ALIGN ( -- ) HERE @ 3 + -4 AND HERE ! ;
: MT-COUNT ( c-addr -- addr len )
    DUP 1+ SWAP C@ ;
\ The word buffer ' just parsed: NUL-ended.
: MT-WORD ( -- addr len )
    ADDR-WORD-BUF DUP
    BEGIN DUP C@ WHILE 1+ REPEAT OVER - ;
\ A counted copy at HERE, then aligned.
: MT-STR, ( addr len -- )
    DUP C, DUP 0> IF
        0 DO DUP I + C@ C, LOOP
    ELSE DROP THEN DROP MT-ALIGN ;

\ An entry: link, bindings, manufacturer
\ and product (counted, each aligned).
: MATCH-ENTRY ( m-a m-u p-a p-u -- )
    MT-ALIGN HERE @ MT-HEAD @ , 0 ,
    MT-HEAD ! 2SWAP MT-STR, MT-STR, ;
: ME-BINDS ( e -- addr ) 4 + ;
: ME-MAN ( e -- c-addr ) 8 + ;
: ME-PROD ( e -- c-addr )
    ME-MAN DUP C@ 1+ + 3 + -4 AND ;

\ A binding: link, vector, word, the
\ word's name (counted), in written order.
: MT-APPEND ( b list -- )
    BEGIN DUP @ WHILE @ REPEAT ! ;
: BINDS ( "vector" "word" -- )
    MT-HEAD @ 0= IF
        ." BINDS: no MATCH-ENTRY" CR EXIT
    THEN
    ' DUP @ DOVEC-CODE <> IF
        ." BINDS: " MT-WORD TYPE
        ."  is not a HAL vector" CR
        DROP ' DROP EXIT
    THEN
    ' MT-ALIGN HERE @ >R 0 , SWAP , ,
    MT-WORD MT-STR,
    R> MT-HEAD @ ME-BINDS MT-APPEND ;
\ A note: a binding with vector 0, its
\ text where the name goes. Printed in
\ written order; it binds nothing.
: MATCH-NOTE ( addr len -- )
    MT-HEAD @ 0= IF
        2DROP ." MATCH-NOTE: no MATCH-ENTRY"
        CR EXIT
    THEN
    MT-ALIGN HERE @ >R 0 , 0 , 0 ,
    MT-STR, R> MT-HEAD @ ME-BINDS MT-APPEND ;

: .BINDING ( b -- )
    DUP 4 + @ 0= IF
        ." Note: " 0C + MT-COUNT TYPE EXIT
    THEN
    ." ' " DUP 0C + MT-COUNT TYPE
    ."  BIND " 4 + @ HAL-NAME TYPE ;

\ ---- Matching ----
VARIABLE MS-S
: MS-FIELD ( off -- addr len )
    MS-S @ SWAP OVER + C@ SM-STR ;
: .MS ( -- )
    4 MS-FIELD TYPE ."  / " 5 MS-FIELD TYPE ;
: MT-STR= ( addr len c-addr -- flag )
    MT-COUNT ROT OVER <> IF
        2DROP DROP 0 EXIT
    THEN
    ?DUP IF SM-MEM= ELSE 2DROP -1 THEN ;
: ME-HIT? ( e -- flag )
    4 MS-FIELD 2 PICK ME-MAN MT-STR=
    SWAP 5 MS-FIELD ROT ME-PROD MT-STR=
    AND ;
\ The newest entry that matches, or 0.
: MT-FIND ( -- e|0 )
    MT-HEAD @
    BEGIN DUP WHILE
        DUP ME-HIT? IF EXIT THEN @
    REPEAT ;

: MATCH-BIND ( -- )
    1 SM-FIND ?DUP 0= IF
        ." No SMBIOS type 1: the defaults stay"
        CR EXIT
    THEN MS-S !
    MT-FIND ?DUP 0= IF
        ." No machine entry for " .MS
        ." : the defaults stay" CR EXIT
    THEN
    ." Machine: " .MS CR
    ME-BINDS @
    BEGIN ?DUP WHILE
        DUP .BINDING CR DUP 4 + @ IF
            DUP 8 + @ OVER 4 + @ HAL-SET
        THEN @
    REPEAT ;

: MATCH-LIST ( -- )
    MT-HEAD @ DUP 0= IF
        DROP ." No machine entries" CR EXIT
    THEN
    BEGIN ?DUP WHILE
        DUP ME-MAN MT-COUNT TYPE ."  / "
        DUP ME-PROD MT-COUNT TYPE CR
        DUP ME-BINDS @
        BEGIN ?DUP WHILE
            SPACE SPACE DUP .BINDING CR @
        REPEAT
        @
    REPEAT ;

ONLY FORTH DEFINITIONS
DECIMAL
