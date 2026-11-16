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
SUITE P9                 \ FAIL names the first failure,
T{ Q1 1 -> 1 }T          \ not the last label read
T{ Q2 1 -> 2 }T
T{ Q3 1 -> 1 }T
END-SUITE
SUITE P10
T{ P10 ALSO FORTH -> }T PREVIOUS \ search order one deeper
END-SUITE
VOCABULARY PV
SUITE P11
T{ P11 PV DEFINITIONS -> }T ONLY FORTH DEFINITIONS \ CURRENT
END-SUITE
SUITE P12
T{ P12 HEX 10 -> 16 }T DECIMAL \ BASE left at 16, not excused
END-SUITE
SUITE P13
BASES T{ P13 HEX 10 -> 17 }T DECIMAL \ excused; value miss
END-SUITE
SUITE P7
T{ P7 NOSUCHWORD -> }T   \ abort: ABORT line, hook back
END-SUITE
