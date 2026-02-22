# ghidra_extract_ports.py — Ghidra headless script for port I/O extraction
#
# Runs as a Ghidra Jython script (analyzeHeadless post-script).
# Finds all IN/OUT instructions and READ_PORT_*/WRITE_PORT_* API calls,
# outputs them in a format comparable to the translator's output.
#
# Usage (headless):
#   analyzeHeadless /tmp/ghidra_project proj_name \
#     -import serial.sys \
#     -postScript ghidra_extract_ports.py \
#     -scriptPath /path/to/scripts/
#
# Output format (printed to console):
#   PORT_READ  0x3F8  func_name  address
#   PORT_WRITE 0x3F9  func_name  address
#   API_CALL   READ_PORT_UCHAR  func_name  address
#
# Copyright (c) 2026 Jolly Genius Inc.

# Ghidra Jython imports (available in Ghidra's script environment)
# @category DriverAnalysis

from ghidra.program.model.listing import CodeUnit
from ghidra.program.model.scalar import Scalar

HAL_PORT_APIS = {
    'READ_PORT_UCHAR', 'READ_PORT_USHORT', 'READ_PORT_ULONG',
    'WRITE_PORT_UCHAR', 'WRITE_PORT_USHORT', 'WRITE_PORT_ULONG',
    'READ_PORT_BUFFER_UCHAR', 'READ_PORT_BUFFER_USHORT', 'READ_PORT_BUFFER_ULONG',
    'WRITE_PORT_BUFFER_UCHAR', 'WRITE_PORT_BUFFER_USHORT', 'WRITE_PORT_BUFFER_ULONG',
}

def get_function_name(addr):
    """Get the function name containing this address."""
    func = getFunctionContaining(addr)
    if func:
        return func.getName()
    return "unknown"

def extract_port_io():
    """Find all IN/OUT instructions in the binary."""
    listing = currentProgram.getListing()
    mem = currentProgram.getMemory()

    # Iterate over all instructions
    inst_iter = listing.getInstructions(True)
    while inst_iter.hasNext():
        inst = inst_iter.next()
        mnemonic = inst.getMnemonicString().upper()
        addr = inst.getAddress()
        func_name = get_function_name(addr)

        if mnemonic == 'IN':
            # IN AL, imm8 or IN AL, DX
            if inst.getNumOperands() >= 2:
                op = inst.getOpObjects(1)
                if op and len(op) > 0 and isinstance(op[0], Scalar):
                    port = op[0].getUnsignedValue()
                    print("PORT_READ  0x%X  %s  %s" % (port, func_name, addr))
                else:
                    print("PORT_READ  DX  %s  %s" % (func_name, addr))

        elif mnemonic == 'OUT':
            # OUT imm8, AL or OUT DX, AL
            if inst.getNumOperands() >= 1:
                op = inst.getOpObjects(0)
                if op and len(op) > 0 and isinstance(op[0], Scalar):
                    port = op[0].getUnsignedValue()
                    print("PORT_WRITE 0x%X  %s  %s" % (port, func_name, addr))
                else:
                    print("PORT_WRITE DX  %s  %s" % (func_name, addr))

def extract_api_calls():
    """Find all calls to HAL port I/O APIs."""
    listing = currentProgram.getListing()
    ref_mgr = currentProgram.getReferenceManager()
    symbol_table = currentProgram.getSymbolTable()

    # Look for imported symbols matching HAL port APIs
    for sym in symbol_table.getExternalSymbols():
        name = sym.getName()
        if name in HAL_PORT_APIS:
            # Find all references to this symbol
            refs = ref_mgr.getReferencesTo(sym.getAddress())
            for ref in refs:
                from_addr = ref.getFromAddress()
                func_name = get_function_name(from_addr)
                print("API_CALL   %s  %s  %s" % (name, func_name, from_addr))

# Main
print("=" * 60)
print("Port I/O Extraction Report")
print("Binary: %s" % currentProgram.getName())
print("=" * 60)
print("")
print("--- Direct Port I/O (IN/OUT instructions) ---")
extract_port_io()
print("")
print("--- HAL Port API Calls ---")
extract_api_calls()
print("")
print("--- End Report ---")
