# Finding: QEMU HMP echoes commands character-by-character, so a naive `0x..` scan over the monitor buffer overcounts — 2026-08-11

## Scope

This is a property of **QEMU's HMP monitor**, not of any ForthOS
harness. Anyone writing a monitor-output parser needs it. Recorded
with its measurement method so the conclusion can be re-derived
rather than trusted.

## Context

`tests/test_g6_chain.py` reads VGA text memory through the QEMU
monitor (`xp /4000bx 0xb8000`) as a crash-forensics oracle. Two
parsers existed: the original `read_vga_text`, which filtered to
lines shaped `<hex-addr>: 0x.. 0x..`, and a faster `MonFast.vga`
which re-implemented the parse and dropped that filter, counting
completion with a bare `re.findall(rb'0x[0-9a-f]{2}', raw)` against
a threshold of 4000.

A code review diagnosed this as an off-by-one: the echoed command
`xp /4000bx 0xb8000` contains `0xb8`, so the loop was said to break
at 3999. **That diagnosis is wrong**, and a fix built on it would
have been wrong while appearing green.

## Measurement

- **QEMU:** `qemu-system-i386` 8.2.2 (Debian 1:8.2.2+ds-0ubuntu1.18)
- **Setup:** `qemu-system-i386 -display none -monitor
  tcp:127.0.0.1:4711,server=on,wait=off -daemonize`
  (no disk, no BIOS interaction needed — the effect is in the
  monitor's line editor, not the guest)
- **Sent:** `xp /4000bx 0xb8000\n`, then drained the socket to a
  1.5 s idle gap.
- **Counted two ways:** naive `re.findall(rb'0x[0-9a-f]{2}', raw)`
  over the whole buffer, versus an address-anchored filter that
  accepts only lines matching `^<hex-addr>:` and scans the RHS only.
- Repeated with **two** `sendall` of the same command before the
  drain, to test whether the effect scales.
- Repeated across **three monitor transports** (TCP, unix socket,
  stdio-to-a-pipe) to test whether the effect is transport-specific.
- Probe scripts inlined in the appendices below — do not rely on
  `/tmp`.

## Results

Two different anchored counts appear below because they measure
different functions. **Line filter** accepts every line shaped
`<hex-addr>:` (all dumps in the buffer). **Dump anchored** also
resets the cell list at the base address, yielding the LAST dump
alone. The shipped parser does both; the distinction matters only
when a buffer holds more than one dump.

| Buffer contents | naive | line filter | dump anchored | phantom delta |
|---|---|---|---|---|
| ONE `xp /4000bx` dump | **4004** | 4000 | 4000 | **+4** |
| TWO dumps, one buffer | **8008** | 8000 | 4000 | **+8** |

Phantom matches scale at **4 per echo**, not 1. The `dump anchored`
column is what the shipped code returns.

### Transport independence

Measured with `xp /64bx 0xb8000` (64 real cells) on QEMU 8.2.2:

| Monitor transport | naive | line filter | phantom delta | `\x1b[K` in buffer |
|---|---|---|---|---|
| `tcp:127.0.0.1:PORT` | 68 | 64 | +4 | yes |
| `unix:/path.sock` | 68 | 64 | +4 | yes |
| `stdio` (pipe, not a tty) | 68 | 64 | +4 | yes |

Identical on all three. Notably QEMU emits the ANSI redraw sequences
**even when stdout is a pipe with no terminal negotiation**, so this
is not a termcap or TTY-detection behaviour — it is unconditional in
the HMP line editor. The claim "property of HMP, not of a transport"
is therefore measured, not assumed.

## Mechanism

The HMP monitor is line-edited and **redraws the whole command line
on every keystroke**. The raw echo for a single command begins:

```
b'x\x1b[K\x1b[Dxp\x1b[K\x1b[D\x1b[Dxp \x1b[K\x1b[D\x1b[D\x1b[Dxp /\x1b[K
  ...\x1b[Dxp /4000\x1b[K...'
```

`\x1b[K` is erase-to-end-of-line and `\x1b[D` is cursor-left. So the
buffer contains every **progressive prefix** of the typed command.
As the address `0xb8000` is typed out, the buffer accumulates
`0xb8`, `0xb80`, `0xb800`, `0xb8000` — and `re.findall(rb'0x[0-9a-f]{2}')`
matches the leading `0xb8` of each. Four prefixes contain a
two-hex-digit run after `0x`; hence four phantom matches.

## Why the off-by-one "fix" would have been wrong

1. The real delta is 4, not 1 — a `>= 4001` threshold still breaks
   early.
2. **No constant correction survives both cases.** One echo costs 4,
   two echoes cost 8. Any buffer that retains a previous echo
   changes the correction factor. The bug is not arithmetic.
3. The correct fix is the **filter**, which the original parser
   already had: only lines shaped `<hex-addr>: 0x.. 0x..` contribute,
   RHS only. Measured **exactly 4000 and 8000** in the two cases —
   the echo cannot contribute at all, at any repetition count.

## Second-order consequence: truncation and parity are one bug

The early break does not merely undercount; it **leaves unread bytes
in the socket**, which prepend to the next sample. If that residue is
an odd number of `0x..` tokens, a subsequent `[::2]` stride reads the
screen off the **attribute** bytes instead of the character bytes,
decoding as garbage. Reproduced at recv-chunk granularity: the naive
form broke at 3997 anchored cells, left 3 (odd) tokens unread, and
the next sample parsed 3994 and decoded off the attribute plane.

So "counts wrong" and "reads the wrong byte plane" are the same
defect, not two.

## Resolution

`tests/test_g6_chain.py` now has ONE parser, `parse_vga_cells`, used
by both the slow and fast paths:

- **Address-anchored line filter** (restored to the fast path).
- **Dump anchoring:** the cell list RESETS on any line whose address
  equals the base, so a buffer still holding an earlier, possibly
  half-read dump yields the LAST dump alone — always starting on a
  char byte. This makes the parity hazard *structurally* impossible
  rather than arithmetically avoided.
- Threshold and command string both derive from one
  `VGA_DUMP_BYTES` constant, so they cannot drift apart.

Note the two anchored figures measure different things: the
**line filter alone** yields 8000 for a two-dump buffer (both dumps);
**dump anchoring** yields 4000 (the last dump only). The latter is
the intended behaviour for a screen oracle — you want the freshest
complete screen, not a concatenation of two.

## Generalization worth carrying

This is the third defect in the G6 arc whose proposed fix was an
adjustment to a number, where the actual defect was a **missing
invariant underneath** it:

- **Bug #33** — not a bad range check; an unset sentinel
  (`FS-SLOT` defaulted to 0, so GPT slot 0 looked valid).
- **`search --part-uuid`** — not a version floor to raise; a mode
  that has never existed in any GRUB.
- **This** — not a miscount to correct; a deleted echo defense.

When a review hands you arithmetic, ask what the arithmetic was
standing in for.

---

## Appendix A — count probe (one echo vs two)

Produces the first results table. Needs only `qemu-system-i386`; no
guest image, no ForthOS build.

```python
import socket, subprocess, time, re
MON = 4711
subprocess.run(['pkill', '-9', '-f', '[q]emu.*4711'], capture_output=True)
time.sleep(1)
subprocess.run(['qemu-system-i386', '-display', 'none', '-monitor',
                f'tcp:127.0.0.1:{MON},server=on,wait=off',
                '-daemonize'], check=True)
time.sleep(2)
s = socket.socket(); s.settimeout(5); s.connect(('127.0.0.1', MON))
time.sleep(0.5)


def drain(sk, t=1.5):
    sk.settimeout(t); out = b''
    try:
        while True:
            d = sk.recv(65536)
            if not d:
                break
            out += d
    except Exception:
        pass
    return out


def anchored(raw, base=0xb8000, reset=True):
    """reset=True -> dump anchoring; reset=False -> line filter only."""
    cells = []
    for line in raw.splitlines():
        addr, sep, rest = line.partition(b':')
        a = addr.strip()
        if not sep or not re.fullmatch(rb'0x0*[0-9a-f]+|[0-9a-f]+', a):
            continue
        bs = re.findall(rb'0x([0-9a-f]{2})', rest)
        if not bs:
            continue
        if reset and int(a, 16) == base:
            cells = []
        cells += bs
    return cells


drain(s)
CMD = b'xp /4000bx 0xb8000\n'
s.sendall(CMD); time.sleep(3); raw1 = drain(s, 2.0)
s.sendall(CMD); s.sendall(CMD); time.sleep(5); raw2 = drain(s, 2.0)
for tag, raw in (('ONE', raw1), ('TWO', raw2)):
    naive = len(re.findall(rb'0x[0-9a-f]{2}', raw))
    print(f'{tag}: naive={naive} '
          f'line-filter={len(anchored(raw, reset=False))} '
          f'dump-anchored={len(anchored(raw))}')
for line in raw1.splitlines()[:4]:
    if b'xp' in line:
        print('ECHO repr:', repr(line[:160]))
        break
s.close()
subprocess.run(['pkill', '-9', '-f', '[q]emu.*4711'], capture_output=True)
```

Expected on QEMU 8.2.2:
```
ONE: naive=4004 line-filter=4000 dump-anchored=4000
TWO: naive=8008 line-filter=8000 dump-anchored=4000
ECHO repr: b'x\x1b[K\x1b[Dxp\x1b[K\x1b[D\x1b[Dxp \x1b[K...'
```

## Appendix B — transport probe (TCP vs unix vs stdio)

Produces the transport-independence table. **Standalone** — it
redefines its own helpers, so it can be pasted and run on its own
without Appendix A.

**Note the dump size: this probe uses `xp /64bx`, not `/4000bx`.**
The phantom count is still exactly **+4**, because the phantoms come
from the progressive prefixes of the *address* `0xb8000` being
redrawn — `0xb8`, `0xb80`, `0xb800`, `0xb8000` — and not from the
byte count at all. A reader reproducing this with any dump size
should still see +4; seeing four with a 64-byte dump is expected,
not a coincidence. (Changing the *base address* is what would move
the number.)

**Cleanup is by PID, not by `pkill`.** An earlier draft used
`pkill -9 -f '[q]emu.*hmpmon'`. The `[q]` bracket trick stops the
pattern matching *grep itself*, but it does not stop it matching the
**invoking shell**, whose command line contains the pattern text
verbatim when the probe is run inline via `bash -c`. Measured
2026-08-11: that `pkill` killed the calling shell along with QEMU.
Spawning without `-daemonize` and calling `pr.kill()` removes the
class of problem rather than escaping around it.

```python
import socket, subprocess, time, re, os

CMD = b'xp /64bx 0xb8000\n'


def drain(sk, t=1.5):
    sk.settimeout(t); out = b''
    try:
        while True:
            d = sk.recv(65536)
            if not d:
                break
            out += d
    except Exception:
        pass
    return out


def counts(raw, base=0xb8000):
    """(naive, line-filter) -- the two columns of the table."""
    naive = len(re.findall(rb'0x[0-9a-f]{2}', raw))
    cells = []
    for line in raw.splitlines():
        addr, sep, rest = line.partition(b':')
        a = addr.strip()
        if not sep or not re.fullmatch(rb'0x0*[0-9a-f]+|[0-9a-f]+', a):
            continue
        cells += re.findall(rb'0x([0-9a-f]{2})', rest)
    return naive, len(cells)


def spawn(*monitor):
    """No -daemonize: we keep the PID and kill it directly, so
    cleanup never depends on a pkill pattern (which can match the
    invoking shell's own command line)."""
    return subprocess.Popen(
        ['qemu-system-i386', '-display', 'none', '-monitor', *monitor],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --- TCP ---
pr = spawn('tcp:127.0.0.1:4712,server=on,wait=off')
try:
    time.sleep(2)
    s = socket.socket(); s.settimeout(5); s.connect(('127.0.0.1', 4712))
    time.sleep(0.5); drain(s)
    s.sendall(CMD); time.sleep(2); raw = drain(s)
    print('TCP  ', counts(raw), 'esc[K:', b'\x1b[K' in raw)
    s.close()
finally:
    pr.kill(); pr.wait(timeout=10)

# --- UNIX socket ---
p = '/tmp/hmpmon.sock'
if os.path.exists(p):
    os.unlink(p)
pr = spawn(f'unix:{p},server=on,wait=off')
try:
    time.sleep(2)
    u = socket.socket(socket.AF_UNIX); u.settimeout(5); u.connect(p)
    time.sleep(0.5); drain(u)
    u.sendall(CMD); time.sleep(2); raw = drain(u)
    print('UNIX ', counts(raw), 'esc[K:', b'\x1b[K' in raw)
    u.close()
finally:
    pr.kill(); pr.wait(timeout=10)
    if os.path.exists(p):
        os.unlink(p)

# --- STDIO (pipe, deliberately NOT a tty) ---
pr = subprocess.Popen(
    ['qemu-system-i386', '-display', 'none', '-monitor', 'stdio'],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL)
time.sleep(2)
pr.stdin.write(CMD); pr.stdin.flush(); time.sleep(2)
# communicate() with a timeout, NOT a bare read(): if QEMU fails to
# exit, this raises instead of hanging the probe forever.
try:
    raw, _ = pr.communicate(b'quit\n', timeout=15)
except subprocess.TimeoutExpired:
    pr.kill()
    raw, _ = pr.communicate()
    raise
print('STDIO', counts(raw), 'esc[K:', b'\x1b[K' in raw)
```

Expected on QEMU 8.2.2 — `(naive, line-filter)`:
```
TCP   (68, 64) esc[K: True
UNIX  (68, 64) esc[K: True
STDIO (68, 64) esc[K: True
```

The stdio case is the load-bearing one: stdout is a pipe, so there is
no terminal to negotiate with, and QEMU emits the redraw anyway.
