# TASK — HAL: the NET-SEND contract (2026-10-13)

Owner, 2026-10-13 (after the stick decision), item 2: next in the HAL
order, the NET-SEND contract, then NET-DATA. No-plan flow; commit without
pushing.
- NET-SEND goes on the binding layer over the RTL8168's existing send path.
- HAL-LIST shows it bound on a machine with the NIC.
- With no NIC, the vector is unbound, and a call says so by name.
- QEMU only. Pad cost reported.
Follows docs/TASK_HAL_DISPLAY.md (the binding layer) and
docs/TASK_HAL_BLOCK.md (the block contract).

## Facts (read from the code)

- The binding layer (hal.fth, kernel DOVEC): calling an unbound vector
  already prints `<name>: HAL vector not bound` and takes the abort path an
  undefined word takes. No kernel change is needed for "says so by name".
- RTL8168 (rtl8168.fth, paid, embedded after hal.fth): RTL8168-INIT sets
  RTL-FOUND and RTL-BASE only when it finds the card; RTL8168-TX ( len -- )
  sends TX-BUF (0x1000 bytes), polls the descriptor's OWN bit for 100 ms
  and prints `TX timeout`, returning nothing.
- **QEMU has no RTL8168 model** (its NICs: ne2k_pci, rtl8139, e1000,
  ...). In QEMU the RTL8168 binding can show only its no-card side.
- NE2000 (ne2000.fth, block-loaded) drives QEMU's ne2k_pci; LOG-HARNESS
  and NET-DICT send through NE2K-SEND ( addr len -- ), which starts the
  transmit and returns nothing. NET-DATA (next) runs over it in QEMU.
- **Name clash:** NET-DICT already has a word NET-SEND ( first last -- )
  that sends blocks. The HAL's NET-SEND lives in the HAL vocabulary; the two
  never share a search order in today's code, but a reader can confuse
  them. Left for NET-DATA (it reworks NET-DICT's send).

## Design

- **The contract, in hal.fth:**
  `NET-SEND ( addr len -- ior )`: send one Ethernet frame: destination,
  source, type, payload, without the FCS. len 14 to 1514; a frame shorter
  than 60 goes out zero-padded to 60. ior 0 = handed to the card (and,
  where the card reports it, sent); 1 = refused or failed. Unbound until a
  NIC driver's init finds its card.
  `NET-LEN-OK? ( len -- flag )`: 14 to 1514, for the drivers.
- **RTL8168:** `RTL8168-TX? ( len -- ior )` is RTL8168-TX with a result
  (0 sent, 1 timed out, still printing `TX timeout`); RTL8168-TX keeps its
  stack effect over it. `RTL8168-SEND ( addr len -- ior )` copies the frame
  into TX-BUF (zero-padded to 60) and sends it. RTL8168-INIT, once it has
  found and set up the card, binds NET-SEND to RTL8168-SEND and prints
  `NET-SEND -> RTL8168-SEND`.
- **NE2000:** `NE2K-NET-SEND ( addr len -- ior )`, the same over
  NE2K-SEND (ior 0 once the transmit is started: NE2K-SEND does not wait for
  it). NE2K-INIT, once it has found the card, binds NET-SEND to it and
  prints `NET-SEND -> NE2K-NET-SEND`. NE2K-SEND moves above NE2K-INIT
  (unchanged) so the init can name it.
- Binding is passive: nothing is sent by binding. On the HP, AUTO-DETECT's
  RTL8168-INIT will bind it at boot.

## Gates

test-hal-net (QEMU, BIOS image, floppy + IDE blocks, two boots):
- Boot A, ne2k_pci on a dgram netdev with QEMU's filter-dump writing a pcap:
  - A0 NE2000 block-loads; HAL-LIST before init: `NET-SEND -> unbound`.
  - A1 NE2K-INIT prints `NET-SEND -> NE2K-NET-SEND`; HAL-LIST shows
    NE2K-NET-SEND's XT.
  - A2 a 64-byte frame (broadcast, the card's MAC, type 88B5, a marker
    payload) through NET-SEND: ior 0, and the pcap holds exactly those 64
    bytes.
  - A3 a 20-byte frame: ior 0; on the wire 60 bytes, the 20 then zeros.
  - A4 lengths 13 and 1515: ior 1, no frame added to the pcap.
  - A5 RTL8168-INIT here (no RTL8168): `RTL8168 not found`; NET-SEND still
    NE2K-NET-SEND's.
  - A6 DEPTH 0.
- Boot B, no NIC (`-nic none`):
  - N1 HAL-LIST: `NET-SEND -> unbound`.
  - N2 RTL8168-INIT and NE2K-INIT find nothing and bind nothing; calling
    NET-SEND prints `NET-SEND: HAL vector not bound`.
  - N3 DEPTH 0.
- Not covered in QEMU: RTL8168-SEND and RTL8168-TX? never run (no card
  model); on the HP, `HAL-LIST` after boot shows whether it bound.

## Results

Evidence: ~/forthos-evidence/2026-10-13-hal-net/ (predictions before the red).
- **Red** (image d0258de8): 2/10, every check as predicted (A6, N3 pass).
  One miss: I wrote the denominator as 11; the test has 10 check sites.
- **Green** (image ae05cb9a): 10/10, two runs, 9.9 s (T_HAL_NET 20):

| check | result |
|---|---|
| A0 | NE2000 loads; `NET-SEND -> unbound` before init |
| A1 | NE2K-INIT prints `NET-SEND -> NE2K-NET-SEND`; HAL-LIST shows its XT |
| A2 | ior 0; the pcap's first 88B5 frame is the 64 bytes sent |
| A3 | ior 0; on the wire 60 bytes: the 20 sent, then zeros |
| A4 | 13 and 1515: ior 1; the pcap holds exactly two 88B5 frames |
| A5 | `RTL8168 not found`; NET-SEND still NE2K-NET-SEND's |
| N1 | no NIC: `NET-SEND -> unbound` |
| N2 | both inits find nothing; `NET-SEND: HAL vector not bound` |
| A6 / N3 | DEPTH 0 |

- **Cost:** no kernel change; the embedded hal.fth and rtl8168.fth grew:
  kernel pad 303 B (8,604 B free, was 8,907).
- **Not covered:** RTL8168-SEND, RTL8168-TX? and RTL8168-INIT's bind never
  run in QEMU (no RTL8168 model). On the HP, AUTO-DETECT's RTL8168-INIT
  should print `NET-SEND -> RTL8168-SEND` and HAL-LIST show it: for the
  owner's session.
