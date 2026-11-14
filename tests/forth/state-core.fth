\ state-core.fth - the mentor's list: stacks, buffers, state
DECIMAL
: T-RT ( -- 1 ) 1 >R R> ;
SUITE state-core
T{ S1 -> }T                  \ empty in, empty out
T{ S2 1 2 3 -> 1 2 3 }T      \ values come back in order
T{ S3 DEPTH -> 0 }T          \ stack empty at case start
T{ S4 1 2 DEPTH -> 1 2 2 }T  \ DEPTH counts items
T{ S5 5 DUP DROP -> 5 }T     \ no leftover
T{ S6 T-RT -> 1 }T           \ return stack balanced
T{ S7 STATE @ -> 0 }T        \ interpreting
T{ S8 SP@ SP@ - -> 4 }T      \ one cell is 4 bytes
T{ S9 BLK @ 0= -> 0 }T       \ loading from a block
T{ S10 KB-RING-COUNT @ -> 0 }T \ keyboard ring empty
T{ S11 RP@ RP@ - -> 0 }T     \ RP@ is stable
T{ S12 T-DIRTY -> 0 }T       \ no dirty block buffer
END-SUITE
ONLY FORTH DEFINITIONS
