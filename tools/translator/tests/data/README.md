# Test Driver Binaries

This directory holds real-world `.sys` driver binaries for pipeline validation.
Binary files are gitignored — they must be sourced separately.

## ReactOS Serial Driver

The primary validation target is ReactOS's serial port driver (`serial.sys`),
which uses `READ_PORT_UCHAR`/`WRITE_PORT_UCHAR` for 16550 UART access.

### Sourcing from ReactOS Release ISO

1. Download a ReactOS release ISO from https://reactos.org/download/
2. Mount the ISO and extract `reactos/system32/drivers/serial.sys`
3. Place it in this directory as `serial.sys`

### Sourcing from ReactOS Build Artifacts

1. Visit https://github.com/nicedoc/reactos-artifacts or the ReactOS nightly builds
2. Download the appropriate build artifact
3. Extract `serial.sys` from the drivers directory

### Optional: Using the fetch script

```bash
../scripts/fetch-reactos-serial.sh
```

This attempts to download from ReactOS release mirrors. May require
manual intervention if download URLs change.

## Validation Workflow

Once `serial.sys` is in place:

```bash
# Run through the translator pipeline
../../bin/translator -t forth -n SERIAL-16550 serial.sys

# Compare against hand-written reference
python3 ../../scripts/compare_vocab.py \
    <(../../bin/translator -t forth -n SERIAL-16550 serial.sys) \
    ../../../../forth/dict/serial-16550.fth

# Validate with Ghidra (if installed)
# See scripts/ghidra_extract_ports.py for headless analysis
```
