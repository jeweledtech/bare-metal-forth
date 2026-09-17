# Pre-registration: red (g), unbounded read past the code buffer (2026-09-17)

Written BEFORE the tests were run. Outcome appended below the line.

## Where it came from

The operand differential's third control (nmap_service.exe) printed
`covered=32057 of 32056 bytes`: the decoder consumed one byte past the
end of the section. Owner ruling 2026-09-16: not incidental. This tool
reads .sys/.dll/.exe files of unknown provenance; an unbounded read
driven by input bytes is a crash on a malformed file and worse on a
crafted one. A defect class, with a red and a place in the order.

## Mechanism (read from code)

`src/decoders/x86_decoder.c` 27-56: `has_bytes(dec, n)` exists and
`x86_decode_one` calls it for the opcode byte (line 193) and in 13
other places, but the byte readers themselves (`eat`, `read_u16`,
`read_i32`, hence `read_i8`/`read_u32`) index `dec->code[dec->offset]`
with no check. An instruction whose immediate or displacement extends
past `code_size` is read from whatever follows the buffer, and
`dec->offset` ends past `code_size`.

## Tests (added to test_x86_decoder.c and to xfail_names)

Both feed a buffer that ends inside the instruction. Ghidra is not the
oracle here (it produces no instruction for a truncated one); the
oracle is the buffer length itself. Pass state, named: the decoder
returns 0 (the existing "error/end" contract in x86_decoder.h line
203) and leaves `dec->offset` ≤ `code_size`; `x86_decode_range`
already stops on 0.

| test | buffer | asserts | predicted first failing assertion | why |
|---|---|---|---|---|
| `x64_RED_truncated_imm32_refused` | `E8 01` (CALL rel32 with 1 of 4 immediate bytes), code_size 2 | returns 0; `dec.offset` ≤ 2 | "truncated imm32: decoder returned 5 for a 2-byte buffer" | line 757 `read_i32` after an opcode-only `has_bytes` |
| `x64_RED_truncated_disp32_refused` | `8B 05 12` (MOV r32,[disp32] with 1 of 4 displacement bytes), code_size 3 | returns 0; `dec.offset` ≤ 3 | "truncated disp32: decoder returned 6 for a 3-byte buffer" | `decode_modrm` line 117 `read_i32` unchecked |

Both in 32-bit mode (the class is mode-independent; the differential
observed it on a PE32 control). The 64-bit helper is not needed.

## Prediction

Both RED on the named assertion. Any GREEN means a bound exists that
the code read did not show; stop and find it.

---

## Outcome (appended after the run)

`make test-x86` → pass=48 xfail=9 fail=0 xpass=0 (tests=57), exit 0.
Log with input hashes: `docs/evidence/x64-reds-g-red-2026-09-17.log`.

| test | observed first failure | matches prediction |
|---|---|---|
| `x64_RED_truncated_imm32_refused` | `truncated imm32: decoder returned nonzero for a 2-byte buffer (read past the end)` | yes |
| `x64_RED_truncated_disp32_refused` | `truncated disp32: decoder returned nonzero for a 3-byte buffer (read past the end)` | yes |

No green; the class is on the XFAIL list (nine names). The fix belongs
in the byte readers (bounds-check in `eat`/`read_u16`/`read_i32` with
a refusal path back to `x86_decode_one` returning 0), decoder-only:
the lifter and the range loop already treat 0 as end.
