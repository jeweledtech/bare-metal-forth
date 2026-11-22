\ key-nav.fth - the navigation keys and KEY-MODS
\ (private TASK_READ_AND_REBUILD_FORMS, the key-code scheme;
\ owner's rulings 2026-11-21, pre-registered before the run).
\ KEY gives Home 132, End 133, Page Up 134, Page Down 135,
\ Insert 136, Delete 137. KEY-MODS ( -- addr ) is a byte
\ latched by each key KEY returns: 1 Shift, 2 Ctrl, 0 for
\ serial bytes. After E0 a Shift code (2A AA 36 B6) is the
\ fake Shift of a gray key with Num Lock on, and is ignored.
\ The number pad decodes as its gray twin (owner: as it is).
\ Each case feeds scancodes into the ring buffer, reads KEY
\ and KEY-MODS, then KN-OFF releases Ctrl and Shift and
\ feeds a Space, read and dropped, so the ring ends empty.
\ SUITE comes first, so an abort here is a RESULT line.
ONLY FORTH DEFINITIONS DECIMAL
SUITE KEY-NAV
: KN> ( sc -- ) KB-RING-BUF KB-RING-TAIL @
  KB-RING-COUNT @ + 15 AND + C! 1 KB-RING-COUNT +! ;
: KN-K ( -- code mods ) KEY KEY-MODS C@ ;
HEX
: KN-OFF ( -- ) 9D KN> AA KN> B6 KN> 39 KN> KEY DROP ;
: KN-E ( sc -- ) E0 KN> KN> ;
: KN-C ( sc -- ) 1D KN> KN-E ;
DECIMAL
T{ N1 71 KN-E KN-K KN-OFF -> 132 0 }T  \ Home
T{ N2 79 KN-E KN-K KN-OFF -> 133 0 }T  \ End
T{ N3 73 KN-E KN-K KN-OFF -> 134 0 }T  \ Page Up
T{ N4 81 KN-E KN-K KN-OFF -> 135 0 }T  \ Page Down
T{ N5 82 KN-E KN-K KN-OFF -> 136 0 }T  \ Insert
T{ N6 83 KN-E KN-K KN-OFF -> 137 0 }T  \ Delete
T{ N7 72 KN-E KN-K KN-OFF -> 128 0 }T  \ gray Up, as before
T{ N8 75 KN-C KN-K KN-OFF -> 130 2 }T  \ Ctrl+Left
T{ N9 77 KN-C KN-K KN-OFF -> 131 2 }T  \ Ctrl+Right
T{ N10 71 KN-C KN-K KN-OFF -> 132 2 }T \ Ctrl+Home
T{ N11 79 KN-C KN-K KN-OFF -> 133 2 }T \ Ctrl+End
T{ N12 29 KN> 28 KN> KN-K KN-OFF -> 13 2 }T \ Ctrl+Enter
T{ N13 29 KN> 157 KN> 75 KN-E KN-K KN-OFF -> 130 0 }T
T{ N14 42 KN> 80 KN> KN-K KN-OFF -> 129 1 }T \ Shift+Down
T{ N15 42 KN-E 72 KN-E KN-K KN-OFF -> 128 0 }T \ fake Shift
T{ N16 42 KN> 75 KN-E KN-K KN-OFF -> 130 1 }T \ real Shift
T{ N17 30 KN> KN-K KN-OFF -> 97 0 }T   \ a
T{ N18 71 KN> KN-K KN-OFF -> 132 0 }T  \ number pad 7
END-SUITE
ONLY FORTH DEFINITIONS
