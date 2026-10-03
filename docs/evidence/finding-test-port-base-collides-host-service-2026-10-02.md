# FINDING — the path-derived TEST_PORT_BASE puts test-firstboot's monitor on a port a host service holds (2026-10-02)

Recorded against master (`0209c1e`). Not fixed here. Owner to sequence.

## Observed

`test-firstboot` fails before its guest starts:

```
qemu-system-i386: -monitor tcp:127.0.0.1:8889,server=on,wait=off: Failed to find an available port: Address already in use
make: *** [Makefile:632: test-firstboot] Error 1
```

Port 8889 is held by `velociraptor.service`. It is a root-owned unit in
`system.slice`, active since 2026-09-26 16:19:38, eight seconds after boot. The
listener is on 127.0.0.1:8889 (socket inode 21132). That same inode was
listening on every check this session (17:5x, 19:24, 19:25, 19:38).

## Mechanism

The port is **not hard-coded**. The recipe uses `$$(($(TEST_PORT_BASE)+89))`,
and `TEST_PORT_BASE` is derived from the checkout path (`Makefile:281`):

```make
TEST_PORT_BASE ?= $(shell b=$$(printf '%s' "$(CURDIR)" | cksum | cut -d' ' -f1); echo $$(( 2200 + (b % 34) * 200 )))
```

So whether a tree collides depends on the directory it is checked out in:

| Checkout path | Base | firstboot monitor |
|---|---|---|
| `~/projects/forthos` (main) | 8400 | 8489 |
| `.worktrees/killbypid` | 8800 | **8889: collides** |
| `.worktrees/master-0209c1e` | 2400 | 2489 |

## Discriminating run (same inputs, port base swapped)

Same image on both trees (`combined.img` `52aae44b…`, a fresh build in each tree;
the two builds are byte-identical):

| | `TEST_PORT_BASE=8800` | `TEST_PORT_BASE=2400` |
|---|---|---|
| branch `harness-killbypid` | bind fails, Error 1 | lan 38/38, offline 38/38 |
| master `0209c1e` | bind fails, Error 1 | lan 38/38, offline 38/38 |

The red follows the port base, not the tree.

## Other bases that hit a host listener on this machine

Listeners outside the test suite in 2200–8999 (snapshot 2026-10-02 ~20:00), and
the base+offset each one lands on:

| Port | Base + offset | Holder | Offset used by a recipe? |
|---|---|---|---|
| 8889 | 8800 +89 | velociraptor.service | yes (`test-firstboot` lan monitor) |
| 8000–8003 | 8000 +0..+3 | velociraptor.service, container runtime | yes |
| 3000 | 3000 +0 | container runtime | yes |
| 4000 | 4000 +0 | container runtime | yes |
| 5455 | 5400 +55 | container runtime | yes (`Makefile:841`) |
| 5678 | 5600 +78 | container runtime | yes |

So 6 of the 34 possible bases are unsafe on this host. Which tree draws one
depends on its path.

## Not fixed

Candidate directions, for the owner: §5 step 5 of
`TASK_HARNESS_KILL_BY_PID.md`, where a recipe refuses to start when its port
is already bound, so a collision fails with a clear message rather than a QEMU
error. Or have the base derivation skip bases whose window has a listener.

## Related

- `TASK_HARNESS_KILL_BY_PID.md` §5 step 5 (refuse when port bound)
- `65a5cdd` (introduced the path-derived `TEST_PORT_BASE`)
