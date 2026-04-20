\ ============================================
\ CATALOG: NOTEPAD-FORM
\ CATEGORY: form
\ PLATFORM: x86
\ SOURCE: hand-written
\ CONFIDENCE: high
\ ============================================
\ Form definition for ForthOS Notepad.
\ Parsed by FORM-LOAD, not by THRU/LOAD.
\ Tag/value lines, not executable Forth.
\ ============================================
FORM: notepad
LABEL: 1 0 "ForthOS Notepad"
DIVIDER: 1
CARD: 0 2 39 "File"
BUTTON: 1 3 6 "New"
BUTTON: 8 3 7 "Open"
BUTTON: 16 3 7 "Save"
BUTTON: 24 3 10 "Save As"
ENDCARD: 0 4 39
CARD: 40 2 39 "Edit"
BUTTON: 41 3 6 "Cut"
BUTTON: 48 3 7 "Copy"
BUTTON: 56 3 8 "Paste"
BUTTON: 65 3 7 "Undo"
ENDCARD: 40 4 39
DIVIDER: 5
LABEL: 1 6 "File:"
INPUT: 7 6 50 ""
DIVIDER: 7
LABEL: 1 8 "Text area (future)"
DIVIDER: 22
LABEL: 1 23 "Ln 1, Col 1"
BUTTON: 70 23 8 "Exit"
END-FORM:
