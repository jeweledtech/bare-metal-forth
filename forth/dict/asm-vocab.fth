\ ============================================
\ CATALOG: ASM-VOCAB
\ CATEGORY: system
\ PLATFORM: x86
\ SOURCE: hand-written
\ STATUS: STUB - pending LMI manual recovery
\ CONFIDENCE: low
\ REQUIRES: X86-ASM ( register names )
\ ============================================
\
\ LMI-pattern inline assembler vocabulary.
\ Enables CODE...END-CODE definitions that
\ assemble directly into the live dictionary.
\
\ THIS IS A DESIGN PLACEHOLDER. Do not
\ implement until the physical LMI manual
\ has been recovered and reviewed.
\ See docs/LMI_REFERENCE.md for background.
\
\ Usage (planned):
\   USING ASM-VOCAB
\   CODE MY-DOUBLE  ( n -- 2n )
\       EAX POP,
\       EAX EAX ADD,
\       EAX PUSH,
\       NEXT,
\   END-CODE
\
\ ============================================

VOCABULARY ASM-VOCAB
ASM-VOCAB DEFINITIONS
HEX

\ ---- Stub marker ----
\ This vocabulary is intentionally empty.
\ Word signatures below document the
\ planned API based on LMI Forth patterns.

\ ============================================
\ CODE / END-CODE — defining words
\ ============================================
\ CODE ( "name" -- )
\   Create dictionary entry, switch to
\   assembly mode. HERE becomes the
\   target for opcode emission.
\
\ END-CODE ( -- )
\   Finalize CODE definition. Verify
\   stack discipline, switch back to
\   normal interpretation mode.

\ ============================================
\ Opcode Emitters (postfix notation)
\ ============================================
\ In LMI style, operands precede the
\ instruction comma-word:
\
\ EAX PUSH,        \ PUSH EAX
\ EAX POP,         \ POP EAX
\ EAX EBX MOV,     \ MOV EBX, EAX
\ # 42 EAX MOV,    \ MOV EAX, 42
\ EAX 0 [EBP] MOV, \ MOV [EBP+0], EAX
\
\ Planned comma-words:
\ MOV,  ( src dst -- )
\ ADD,  ( src dst -- )
\ SUB,  ( src dst -- )
\ AND,  ( src dst -- )
\ OR,   ( src dst -- )
\ XOR,  ( src dst -- )
\ CMP,  ( src dst -- )
\ TEST, ( src dst -- )
\ PUSH, ( src -- )
\ POP,  ( dst -- )
\ INC,  ( dst -- )
\ DEC,  ( dst -- )
\ NOT,  ( dst -- )
\ NEG,  ( dst -- )
\ SHL,  ( count dst -- )
\ SHR,  ( count dst -- )
\ SAR,  ( count dst -- )
\ CALL, ( target -- )
\ JMP,  ( target -- )
\ RET,  ( -- )
\ NOP,  ( -- )
\ CLI,  ( -- )
\ STI,  ( -- )
\ INT,  ( vector -- )
\ IN,   ( port dst -- )
\ OUT,  ( src port -- )
\ NEXT, ( -- )  \ Forth NEXT macro

\ ============================================
\ Addressing Modes
\ ============================================
\ #      ( n -- imm )   Immediate
\ [EBP]  ( off -- mem ) EBP-relative
\ [ESI]  ( off -- mem ) ESI-relative
\ [EDI]  ( off -- mem ) EDI-relative
\ []     ( addr -- mem ) Absolute

\ ============================================
\ Structured Control Flow
\ ============================================
\ LMI's most powerful innovation: assembly
\ control flow mirrors Forth high-level
\ structures. Branch offsets calculated
\ automatically including forward refs.
\
\ 0= IF,    ... ELSE, ... THEN,
\ 0<> IF,   ... THEN,
\ CS IF,    ... THEN,
\ BEGIN,    ... 0= UNTIL,
\ BEGIN,    ... 0<> WHILE, ... REPEAT,
\
\ Planned:
\ IF,     ( cc -- orig )
\ ELSE,   ( orig -- orig' )
\ THEN,   ( orig -- )
\ BEGIN,  ( -- dest )
\ UNTIL,  ( cc dest -- )
\ WHILE,  ( cc dest -- orig dest )
\ REPEAT, ( orig dest -- )

\ ============================================
\ Condition Codes for Control Flow
\ ============================================
\ 0=   ( -- cc ) Zero / Equal
\ 0<>  ( -- cc ) Not zero / Not equal
\ CS   ( -- cc ) Carry set / Below
\ CC   ( -- cc ) Carry clear / Above=
\ 0<   ( -- cc ) Sign set / Negative
\ 0>=  ( -- cc ) Sign clear / Positive
\ <    ( -- cc ) Less than (signed)
\ >=   ( -- cc ) Greater or equal
\ <=   ( -- cc ) Less or equal
\ >    ( -- cc ) Greater than (signed)

\ ============================================
\ Labels and Forward References
\ ============================================
\ LMI supported symbolic labels with
\ automatic forward reference resolution.
\ Details pending manual recovery.
\
\ Possible API:
\ LABEL: ( "name" -- ) Define label here
\ GOTO,  ( "name" -- ) Jump to label

\ ============================================
\ DISASM — machine-level disassembler
\ ============================================
\ Separate from ASM but closely related.
\ Decodes x86 machine code to mnemonics.
\
\ ' word DISASM         \ disasm one word
\ addr1 addr2 DISASM-RANGE \ disasm range
\
\ Implementation requires x86 opcode
\ decode tables — significant work.
\ See docs/LMI_REFERENCE.md for details.

." ASM-VOCAB stub loaded" CR
." (pending LMI manual recovery)" CR

FORTH DEFINITIONS
DECIMAL
