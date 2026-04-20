# ENDCARD: Signature Change (2026-04-20)

## Change

The `ENDCARD:` tag in `.def` form files changed from 2 to 3 parameters:

**Old**: `ENDCARD: <y> <w>`
**New**: `ENDCARD: <x> <y> <w>`

## Reason

`ADD-CARD-ED` previously hardcoded `0 W-X!`, so all card-end
borders rendered at column 0 regardless of the card's position.
Cards starting at column 40+ had their bottom border at column 0.

## Files Changed

- `forth/dict/ui-core.fth`: `ADD-CARD-ED` now accepts `( x y w -- )`
- `forth/dict/ui-parser.fth`: `BUILD-CARD-ED` parses 3 ints
- `forth/dict/notepad-form.fth`: Updated both ENDCARD lines

## For .def Authors

When writing new form definitions with CARD/ENDCARD pairs,
the ENDCARD x-coordinate should match the CARD x-coordinate:

```
CARD: 40 2 39 "Edit"
  BUTTON: 41 3 6 "Cut"
ENDCARD: 40 4 39
```
