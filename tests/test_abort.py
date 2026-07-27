#!/usr/bin/env python3
"""Kernel gate for ABORT and ABORT" (Forth-83 error exit).

ABORT" is the substrate prerequisite for the INSTALL vocabulary's
allowlist: SAFE-WRITE expresses its refusal with it, so a silent
failure here would turn a refusal into a fall-through write.  The
fail-closed direction is therefore tested explicitly:

  - the TRUE path must print, empty the stack, and NOT run the rest
    of the definition;
  - the FALSE path must print nothing and leave the stack intact.

Parsing discipline follows tests/test_survey_layouts.py: values are
compared as exact integers and "could not determine" is a failure,
never a pass.  The kernel prints "WORD ?" for an undefined word and
then KEEPS EXECUTING the rest of the line, so a substring match can
be satisfied by leftover stack junk.
"""
import re
import socket
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4483

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(10)
for attempt in range(20):
    try:
        s.connect(('127.0.0.1', PORT))
        break
    except (ConnectionRefusedError, OSError):
        time.sleep(0.5)
else:
    print("FAIL: connect")
    sys.exit(1)

time.sleep(2)
try:
    while True:
        s.recv(4096)
except Exception:
    pass


def send(cmd, wait=1.0):
    s.sendall((cmd + '\r').encode())
    time.sleep(wait)
    s.settimeout(2)
    resp = b''
    while True:
        try:
            d = s.recv(4096)
            if not d:
                break
            resp += d
        except Exception:
            break
    return resp.decode('ascii', errors='replace')


def body_of(raw):
    """Drop the echoed input line.

    The echo repeats the command, so scanning the whole response
    would read the command's own characters as though the kernel
    had printed them.
    """
    return raw.split('\n', 1)[1] if '\n' in raw else raw


def val(expr, wait=1.5):
    """Evaluate expr and return its printed integer, or None."""
    raw = send(f'DECIMAL {expr} .', wait)
    body = body_of(raw)
    if '?' in body:
        return None, raw
    nums = re.findall(r'-?\d+', body)
    return (int(nums[-1]) if nums else None), raw


PASS = FAIL = 0


def check(name, ok, detail=''):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f'  PASS: {name}')
    else:
        FAIL += 1
        print(f'  FAIL: {name} -- {detail}' if detail else
              f'  FAIL: {name}')


def expect(name, expr, want):
    v, raw = val(expr)
    check(f'{name} ({expr} = {want})', v is not None and v == want,
          f'got {v!r} from {raw.strip()[-90:]!r}')


def alive():
    """Interpreter still responds to a fresh computation."""
    v, _ = val('7 6 *')
    return v == 42


# ---------------------------------------------------------------
print("\nTest 1: ABORT\" compiles (word exists)")
send('DECIMAL', 0.5)
r = send(': T-AF 0 ABORT" boom" 42 ; ', 1.5)
check('definition using ABORT" compiles without ?',
      '?' not in body_of(r), repr(r.strip()[-90:]))

# ---------------------------------------------------------------
print("\nTest 2: FALSE path is transparent")
r = send('T-AF .', 1.5)
b = body_of(r)
nums = re.findall(r'-?\d+', b)
check('FALSE path leaves 42', bool(nums) and int(nums[-1]) == 42,
      f'got {nums!r} from {b.strip()[-90:]!r}')
check('FALSE path prints nothing', 'boom' not in b,
      repr(b.strip()[-90:]))
expect('stack clean after FALSE path', 'DEPTH', 0)

# ---------------------------------------------------------------
print("\nTest 3: TRUE path fires")
send(': T-AT 1 ABORT" boom" 99 ; ', 1.5)
r = send('T-AT', 2.0)
b = body_of(r)
check('TRUE path prints the message', 'boom' in b,
      repr(b.strip()[-90:]))
check('TRUE path does NOT run the rest of the definition',
      '99' not in b, repr(b.strip()[-90:]))
check('interpreter alive after abort', alive())
expect('stack empty after abort', 'DEPTH', 0)

# ---------------------------------------------------------------
print("\nTest 4: abort empties a non-empty stack")
# Junk must not survive: SAFE-WRITE's refusal leaves buf and lba
# on the stack at the moment it fires.
r = send('11 22 33 T-AT', 2.0)
check('abort with junk on stack prints message',
      'boom' in body_of(r), repr(body_of(r).strip()[-90:]))
expect('junk discarded by abort', 'DEPTH', 0)
check('interpreter alive after discarding junk', alive())

# ---------------------------------------------------------------
print("\nTest 5: abort unwinds nested calls")
# The return stack is several frames deep when it fires; ABORT
# resets it rather than returning through the callers.
send(': T-INNER 1 ABORT" deep" ; ', 1.5)
send(': T-MID T-INNER 77 ; ', 1.5)
send(': T-OUTER T-MID 88 ; ', 1.5)
r = send('T-OUTER', 2.0)
b = body_of(r)
check('nested abort prints the message', 'deep' in b,
      repr(b.strip()[-90:]))
check('nested abort skips both callers tails',
      '77' not in b and '88' not in b, repr(b.strip()[-90:]))
expect('stack empty after nested abort', 'DEPTH', 0)
check('interpreter alive after nested abort', alive())

# ---------------------------------------------------------------
print("\nTest 6: bare ABORT")
r = send('1 2 3 ABORT', 2.0)
check('bare ABORT does not wedge the interpreter', alive())
expect('bare ABORT empties the stack', 'DEPTH', 0)

# ---------------------------------------------------------------
print("\nTest 7: compilation state reset")
# An abort mid-definition must leave STATE interpreting, or every
# later line is silently compiled into a dangling definition.
expect('STATE is interpreting after aborts', 'STATE @', 0)
check('can still define after aborts',
      '?' not in body_of(send(': T-AFTER 5 5 + ; ', 1.5)))
expect('post-abort definition runs', 'T-AFTER', 10)

print(f'\nPassed: {PASS}/{PASS + FAIL}')
s.close()
sys.exit(0 if FAIL == 0 else 1)
