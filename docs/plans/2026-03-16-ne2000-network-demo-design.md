# Design: NE2000 Network Demo — Dictionary Sharing Over Raw Ethernet

**Date:** 2026-03-16
**Status:** Draft
**Prerequisites:** PCI-ENUM (tested), NE2000 vocab (tested), HARDWARE (tested)
**Depends on:** NE2000 word-level tests passing (35/35 as of today)

---

## Goal

Demonstrate bare-metal dictionary sharing between two QEMU instances over raw Ethernet frames using the NE2000 NIC vocabulary. This closes the historical Forth pattern: "zip the dictionary, share it, recipient unzips and runs." No TCP/IP stack needed for the initial demo.

---

## Architecture

### Minimum viable demo

Two QEMU instances connected via a socket-based virtual network:
- **Sender**: Has a vocabulary loaded, sends its block data as raw Ethernet frames
- **Receiver**: Receives frames, writes them to block storage, loads via THRU

### QEMU networking setup

```
# Create socket pair for direct Ethernet connection
# Instance A (sender):
qemu-system-i386 ... -nic model=ne2k_pci,socket,listen=:5555

# Instance B (receiver):
qemu-system-i386 ... -nic model=ne2k_pci,socket,connect=:5555
```

Alternative: use `-netdev socket` backend for more control:
```
# Instance A:
-netdev socket,id=net0,listen=:5555 -device ne2k_pci,netdev=net0

# Instance B:
-netdev socket,id=net0,connect=127.0.0.1:5555 -device ne2k_pci,netdev=net0
```

### Frame format (raw Ethernet, no IP/TCP)

```
Offset  Size  Field
0       6     Destination MAC (broadcast: FF:FF:FF:FF:FF:FF)
6       6     Source MAC
12      2     EtherType (custom: 0x88B5 = IEEE local experimental)
14      2     Command: 0x0001=BLOCK_DATA, 0x0002=BLOCK_REQ
16      2     Block number (0-1023)
18      2     Offset within block (0-1023, for fragmentation)
20      2     Length of payload (bytes, max 1024)
22      N     Payload (block data, padded to even byte)
```

A full 1KB Forth block fits in a single Ethernet frame (1024 + 22 = 1046 bytes, well under the 1500-byte MTU).

### Vocabulary: NET-DICT (new)

```forth
VOCABULARY NET-DICT
NET-DICT DEFINITIONS

\ --- Send a block over the network ---
: BLOCK-SEND ( blk# -- )
    \ Read block into buffer, build frame, NE2K-SEND
;

\ --- Receive and store a block ---
: BLOCK-RECV ( -- blk# | -1 )
    \ Check NE2K-RECV?, parse frame, write to block buffer
;

\ --- Send a range of blocks ---
: BLOCKS-SEND ( first last -- )
    1+ SWAP DO I BLOCK-SEND LOOP
;

\ --- Receive until done ---
: BLOCKS-RECV ( -- count )
    0 BEGIN BLOCK-RECV DUP -1 <> WHILE DROP 1+ REPEAT DROP
;

FORTH DEFINITIONS
```

---

## Implementation phases

### Phase 1: Raw frame send/receive (1 session)

1. Add `NE2K-BUILD-FRAME` and `NE2K-PARSE-FRAME` to NE2000 vocab (or create NET-DICT)
2. Verify frame send between two QEMU instances using Python bridge script
3. Test: sender sends 6-byte payload, receiver reads it back

### Phase 2: Block transfer protocol (1 session)

1. Implement BLOCK-SEND: read block buffer, wrap in frame, NE2K-SEND
2. Implement BLOCK-RECV: NE2K-RECV?, parse frame, write block buffer, UPDATE
3. Test: send block 2 from instance A, verify block 2 on instance B matches

### Phase 3: Dictionary sharing demo (1 session)

1. Implement BLOCKS-SEND / BLOCKS-RECV for range transfers
2. Full demo: Instance A has PIT-TIMER loaded (blocks 151-155), sends to instance B
3. Instance B receives, does THRU, verifies vocabulary works
4. Automated test with two QEMU instances and Python orchestrator

---

## Testing strategy

### Test infrastructure

A Python orchestrator script (`tests/test_ne2000_network.py`) that:
1. Starts two QEMU instances with socket-paired NE2000 NICs
2. Connects to both via serial TCP
3. Loads NE2000 + NET-DICT on both
4. Runs NE2K-INIT on both
5. Sends blocks from A, receives on B
6. Verifies block content matches

### Test cases

1. **Frame roundtrip**: Send raw bytes A→B, verify receipt
2. **Single block transfer**: Send block N from A, verify identical on B
3. **Vocabulary transfer**: Send PIT-TIMER blocks from A, THRU on B, verify words work
4. **MAC discovery**: Both instances print MAC, verify different addresses

---

## Risk assessment

| Risk | Mitigation |
|------|-----------|
| NE2000 DMA timing | Use polling (BEGIN NE-ISR NE@ ... UNTIL), no IRQ dependency |
| Frame corruption | Verify with checksum in frame header (future enhancement) |
| Block alignment | 1KB blocks fit in single Ethernet frame, no fragmentation needed |
| QEMU socket flakiness | Retry with timeout, test on both listen/connect sides |
| NE2K-RECV? blocking | Poll with timeout counter, bail if no packet after N iterations |

---

## Success criteria

1. Two QEMU instances exchange a raw Ethernet frame
2. A complete 1KB Forth block transfers correctly between instances
3. A transferred vocabulary (received via THRU) produces working words on the receiver
4. Automated test passes reliably in CI (make test-network)

---

## Notes

- The NE2000 NIC is byte-oriented DMA (NE2K-DMA-RD/WR use byte loops). For 1KB blocks this is fast enough. Word-oriented DMA is a future optimization.
- No ARP/IP/TCP needed. Raw Ethernet with a custom EtherType is the simplest possible protocol and perfectly aligned with the "radical simplicity" philosophy.
- The historical Forth dictionary sharing pattern used serial links or floppy disks. Ethernet is a natural evolution — same concept, faster medium.
- `>R` usage in NE2K-SEND: currently uses `>R`/`R@`/`R>` outside DO/LOOP, which is safe. If we add DMA inside a loop, switch to VARIABLE pattern per established convention.
