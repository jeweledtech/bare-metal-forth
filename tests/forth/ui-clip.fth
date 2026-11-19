\ ui-clip.fth - the form engine draws only the 80x25 screen
\ (private TASK_READ_AND_REBUILD_FORMS step 9, part 3, clipping;
\ pre-registered 2026-11-18 before the first run). Before, a
\ cell off the screen wrapped: VGA-AT is col + row x 80, so
\ column 80 of row r was column 0 of row r+1. Now VGA-PUTC
\ draws nothing for a column outside 0-79 or a row outside
\ 0-24. Each case marks a cell with # (35), writes Q (81)
\ where the old wrap would have hit it, and reads the mark.
\ P1 P2: cells on the screen are still drawn. P7: a 10-wide
\ label at column 75 keeps ABCDE on row 0 and row 1 stays
\ blank (it was FGHIJ). P8: a label on row 25 draws nothing.
ONLY FORTH DEFINITIONS ALSO UI-CORE ALSO UI-EVENTS DECIMAL
: AT@ ( c r -- ch ) VGA-AT C@ ;
: MARK ( c r -- ) VGA-AT 35 SWAP C! ;
: PUT ( c r -- ) 81 7 2SWAP VGA-PUTC ;
: WIDE ( -- ) WT-RESET 75 0 S" ABCDEFGHIJ" ADD-LABEL
  FORM-RENDER ;
: LOW ( -- ) WT-RESET 0 25 S" XYZ" ADD-LABEL FORM-RENDER ;
SUITE ui-clip
T{ P1 5 3 PUT 5 3 AT@ 5 3 VGA-AT 1+ C@ -> 81 7 }T
T{ P2 79 24 PUT 79 24 AT@ -> 81 }T
T{ P3 0 1 MARK 80 0 PUT 0 1 AT@ -> 35 }T
T{ P4 0 25 MARK 0 25 PUT 0 25 AT@ -> 35 }T
T{ P5 79 0 MARK -1 1 PUT 79 0 AT@ -> 35 }T
T{ P6 0 0 MARK 80 -1 PUT 0 0 AT@ -> 35 }T
T{ P7 WIDE 79 0 AT@ 0 1 AT@ -> 69 32 }T
T{ P8 0 25 MARK LOW 0 25 AT@ -> 35 }T
END-SUITE
ONLY FORTH DEFINITIONS
