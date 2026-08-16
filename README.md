# FujiRealm

A small server-authoritative multiplayer RPG for 8-bit Atari hardware, playing  
over [FujiNet](https://fujinet.online). One Python server, two clients; an  
**Atari 8-bit** client in 6502 assembly and an **Atari Lynx** client in C, both  
speaking the same wire protocol to the same live world.

If you want to build a networked game for retro hardware  
and you are staring at a blank file wondering how any of this fits together,  
how a 6502 client stays in sync with a server, what to do when the link drops  
half a packet, how to keep a 16 KB machine and a 64 KB machine agreeing about  
the same map, this is a complete, working answer you can take apart. It is MIT  
licensed precisely so you can lift whatever is useful.

```
                    ┌──────────────────────┐
                    │   server (Python)    │  authoritative world,
                    │  hybrid_server.py    │  10 Hz tick, no game
                    └──────────┬───────────┘  logic in the clients
                     TCP       │       TCP
              ┌────────────────┴────────────────┐
              │                                 │
     ┌────────┴─────────┐             ┌─────────┴────────┐
     │  FujiNet (SIO)   │             │ FujiNet (ComLynx)│
     │  POKEY serial    │             │   Mikey UART     │
     └────────┬─────────┘             └─────────┬────────┘
     ┌────────┴─────────┐             ┌─────────┴────────┐
     │  Atari 800/XL/XE │             │    Atari Lynx    │
     │  MADS assembly   │             │   cc65 / C       │
     │  ANTIC 4 tiles   │             │   Suzy sprites   │
     └──────────────────┘             └──────────────────┘
```

## What's in the box

| Path             | What it is                                                                                                                                    |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `server/`        | The authoritative game server: world, entities, quests, combat, persistence, and the realtime protocol. Pure Python 3, standard library only. |
| `atari8-client/` | Atari 8-bit client. MADS assembly, ANTIC mode 4, 2×2 tiles, talks to FujiNet over POKEY serial via a vendored Netstream handler.              |
| `lynx-client/`   | Atari Lynx client. cc65 C with a little assembly, Suzy sprite renderer, talks to FujiNet over ComLynx.                                        |
| `tools/`         | Shared build and art tooling, plus `tile-editor/`, the browser tile editor that both clients' art comes from.                                 |
| `maps/`          | The world as editable CSV grids. `tools/import_map_csv.py` compiles them into the server.                                                     |
| `docs/`          | The wire protocol, the Atari memory map, and the shared tile-id contract.                                                                     |

The two clients share the **server**, the **protocol**, and the **logical tile**  
**ids**. Everything else (renderer, transport driver, input, memory layout) is  
per-machine, and the differences are the interesting part.

## Prerequisites

| Tool                                | For                       | Needed                  |
| ----------------------------------- | ------------------------- | ----------------------- |
| `python3` (3.10+)                   | server, tools             | always                  |
| [`mads`](https://mads.atari8.info/) | Atari 8-bit client        | to build the XEX        |
| [`cc65`](https://cc65.github.io/)   | Lynx client               | to build the cart       |
| `dir2atr` (AtariSIO)                | bootable disk image       | `make atr` only         |
| `gcc`/`cc`                          | Lynx host tests           | `make test` only        |
| `node`                              | tile editor tests         | `make test-editor` only |
| Pillow                              | Lynx art previews/mockups | optional                |

To actually play you need FujiNet hardware: a FujiNet for the Atari 8-bit, or a  
FujiNet-Lynx plus a flashcart for the Lynx. There is no FujiNet-capable Lynx  
emulator (yet), so Lynx changes are validated on real hardware.

## Build

```sh
make            # both clients
make atari      # Atari 8-bit only  -> atari8-client/fujirealm.xex
make lynx       # Lynx only         -> lynx-client/fujirealm.lnx
make atr        # bootable disk     -> atari8-client/fujirealm.atr
make clean
```

Both clients bake their server address in at build time, using the same  
variable names:

```sh
make SERVER_HOST=192.168.1.100
make SERVER_HOST=myhost.local HYBRID_SERVER_PORT=9000 LOGIN_SERVER_PORT=9010
```

The default is `localhost`, which is only useful for emulator/host testing, a  
real Atari or Lynx cannot reach it, so **build with your own `SERVER_HOST**`  
**before flashing anything**. Each build prints the endpoint it baked in. To  
avoid passing it every time:

```sh
cp atari8-client/config.mk.example atari8-client/config.mk   # then edit
cp lynx-client/config.mk.example  lynx-client/config.mk
```

`config.mk` is git-ignored. Changing the host forces a relink rather than  
silently leaving the old address in the binary. `SERVER_HOST` is limited to 31  
characters; the Lynx client checks that at compile time.

The Atari client draws the local player with Player/Missile graphics: three  
sprite colours that cost nothing from the four playfield colours, a sprite  
taller than its tile, and pixel-smooth movement between tiles. Bullets ride the  
four missiles. All of it lives in otherwise-unused RAM at `$A000-$BFFF`, so it  
needs BASIC disabled, which the `.atr` boot does. To fall back to the original  
2×2 character sprite:

```sh
make atari PMG_PLAYER=0
```

## Run the server

Two ports: a login/bootstrap port and the realtime port.

```sh
make run-login-server    # default 9010 -- login, identity, saved progress
make run-server          # default 9000 -- bootstrap + realtime, one socket
```

A client connects to the login server first, gets a token that FujiNet caches  
in an appkey, then bootstraps and enters realtime mode on the game port. Player  
progress lives in `server/sessions.json`, which is created on first run and  
never committed, `server/sessions.example.json` shows the shape.

Two more, for bring-up rather than play:

```sh
make run-smoke-server        # accepts FujiNet REGISTER, echoes a probe byte
make run-bootstrap-server    # byte-stream-only server, bootstrap protocol alone
```

## Test

```sh
make test            # server + tools + Lynx host tests
make test-server     # the server suite on its own
make test-lynx       # Lynx host tests, render tests, and lint
make test-editor     # tile editor model tests (needs node)
```

The Lynx client's non-hardware logic, protocol codec, prediction queue,  
terrain cache, renderer bookkeeping, is compiled natively and unit tested on  
the host, which is what makes a machine with no emulator tractable to work on.

## Art

`tools/tile-editor/` is a static browser page; open it directly, no server.

```
tile-editor/index.html  →  atari8-client/art/fujirealm_charsetter.json  →  make atari
tile-editor/lynx.html   →  lynx-client/art/lynx_tileset.json            →  make -C lynx-client art
```

Both clients draw from the same set of logical tile ids, and the server streams  
those ids, the id contract is `docs/TILE_ALLOCATION.md`. See  
`tools/tile-editor/README.md` for the workflow, including the Lynx's pen-0  
transparency rules.

The world maps are CSV. Edit `maps/*.csv`, then:

```sh
python3 tools/import_map_csv.py     # CSV -> server/world_layout_data.py
python3 tools/export_map_csv.py     # the other direction
```

`maps/README.md` has the full legend.

## Reading order

If you are here to learn how it works rather than to build it:

1. `docs/PROTOCOL.md` — the wire format, both phases.
2. `server/protocol.py` — that format in code, encoders and decoders together.
3. `server/hybrid_server.py` — the connection lifecycle: bootstrap, auth,
  realtime, the output scheduler, and the terrain-cache machinery that keeps a  
   client's map in sync over a link with a few KB/s to spare.
4. `lynx-client/README.md` — a candid engineering log of what went wrong on
  real hardware and why the fixes look the way they do. The most useful part  
   of this repository if you are about to do something similar.
5. `docs/MEMORY_LAYOUT.md` — where every byte lives on the Atari 8-bit.

## Credits and license

FujiRealm is MIT licensed — see `LICENSE`. Use it, fork it, ship a game with  
it; attribution in your source is all that is asked.

- The Atari client's network handler is derived from **Altirra**'s replacement  
850 firmware by **Avery Lee**.
- The tile editor is built on **[Charsetter](https://www.atari.org.pl/charsetter/)**  
by Dely, used with their kind permission — thank you!
- The Lynx client is built with **cc65**; the Atari client with **MADS**.
- None of this exists without **[FujiNet](https://fujinet.online)**.

Full details, and what each asks of you if you redistribute, are in  
`THIRD-PARTY-NOTICES.md`.
