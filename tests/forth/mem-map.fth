\ mem-map.fth - fixed regions where docs/ARCHITECTURE.md puts
\ them. FE-BUF, NOTEPAD's file buffer (64 KB), is reserved at
\ 0x210000-0x21FFFF: outside the dictionary 0x30000-0x80000
\ and outside the DMA pool 0x100000-0x200000 (owner
\ 2026-11-27). Each range check takes the buffer's first and
\ last byte. All values decimal.
ONLY FORTH DEFINITIONS ALSO FILE-EDITOR DECIMAL
SUITE MEM-MAP
\ T-IN?: lo <= a < hi.
: T-IN? ( a lo hi -- f ) >R OVER > 0= SWAP R> < AND ;
: T-FB ( lo hi -- f-first f-last ) 2DUP FE-BUF ROT ROT T-IN?
  >R FE-BUF MAX-FILE + 1- ROT ROT T-IN? R> SWAP ;
T{ MM1 196608 524288 T-FB -> 0 0 }T
T{ MM2 1048576 2097152 T-FB -> 0 0 }T
T{ MM3 FE-BUF MAX-FILE -> 2162688 65536 }T
END-SUITE
ONLY FORTH DEFINITIONS
