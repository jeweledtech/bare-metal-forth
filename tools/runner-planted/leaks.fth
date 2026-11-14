\ leaks.fth - planted faults: each suite must FAIL or ABORT
DECIMAL
SUITE P1
T{ P1 1 2 -> 1 }T        \ extra stack item
END-SUITE
SUITE P2
T{ P2 7 >R -> }T R> DROP \ return stack item, cleaned after
END-SUITE
SUITE P3
T{ P3 ] -> }T            \ STATE left at 1
END-SUITE
SUITE P4
T{ P4 0 , -> }T          \ HERE moved one cell
END-SUITE
SUITE P5
T{ P5 3968 BLOCK DROP UPDATE -> }T EMPTY-BUFFERS
END-SUITE
SUITE P6
T{ P6 1 1 + -> 3 }T      \ wrong result
END-SUITE
SUITE P7
T{ P7 NOSUCHWORD -> }T   \ abort: ABORT line, hook back
END-SUITE
