\ hang.fth - an endless case: no RESULT line may print
DECIMAL
: T-HANG BEGIN 0 UNTIL ;
SUITE P8
T{ P8 T-HANG -> }T
END-SUITE
