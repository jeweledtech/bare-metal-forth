\ ui-clip.fth - the form engine draws only the 80x25 screen
\ PRELOAD: DIALOG
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
\ UI-VIEW (step 9 part 3b, scrolling; pre-registered 2026-11-18
\ before the first run). The kernel gives the arrow keys as
\ 128-131 (Up Down Left Right; 128-143 is the navigation
\ block). In DIALOG-RUN Up and Down move the view a row, Left
\ and Right 8 columns; VGA-PUTC draws a form's cell (c, r) at
\ (c - VIEW-X, r - VIEW-Y). The view stays within 0..R-80 and
\ 0..B-25, R the form's right (x + the larger of w and the
\ text + 2), B its bottom (y + 1, a LIST y + h). VFORM: WIDE
\ at column 85 (R 91, view x 0-11), LOW on row 30 (B 31, view
\ y 0-6). A run starts at 0 0; VGA-CLS ignores the view.
ALSO DIALOG
: VFORM ( -- ) WT-RESET 85 0 S" WIDE" ADD-LABEL
  0 30 S" LOW" ADD-LABEL ;
: SMALL ( -- ) WT-RESET 0 0 S" HI" ADD-LABEL ;
: VXY ( -- x y ) VIEW-X @ VIEW-Y @ ;
: DOWNS ( -- ) 7 0 DO KEY-DOWN DR-KEY LOOP ;
SUITE ui-view
T{ V1 KEY-UP KEY-DOWN KEY-LEFT KEY-RIGHT -> 128 129 130 131 }T
T{ V2 VFORM 5 VIEW-X ! IDCANCEL DR-START VXY -> 0 0 }T
T{ V3 KEY-RIGHT DR-KEY VXY -> 8 0 }T
T{ V4 KEY-RIGHT DR-KEY VXY -> 11 0 }T
T{ V5 FORM-RENDER 74 0 AT@ 73 0 AT@ -> 87 32 }T
T{ V6 KEY-LEFT DR-KEY VXY -> 3 0 }T
T{ V7 KEY-LEFT DR-KEY VXY -> 0 0 }T
T{ V8 KEY-DOWN DR-KEY KEY-UP DR-KEY KEY-UP DR-KEY VXY -> 0 0 }T
T{ V9 DOWNS VXY -> 0 6 }T
T{ V10 FORM-RENDER 0 24 AT@ -> 76 }T
T{ V11 79 24 MARK VGA-CLS 79 24 AT@ -> 32 }T
T{ V12 KEY-ESC DR-KEY DR-ID @ DR-DONE @ -> 2 -1 }T
T{ V13 SMALL IDCANCEL DR-START KEY-RIGHT DR-KEY KEY-DOWN DR-KEY
  VXY -> 0 0 }T
END-SUITE
ONLY FORTH DEFINITIONS
