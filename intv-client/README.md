# FujiRealm — Intellivision client

An [IntyBASIC](https://nanochess.org/intybasic.html) client for FujiRealm on
the **Intellivision FujiNet** platform (PiRTO II cartridge). It speaks the
same wire protocol as the Atari 8-bit and Lynx clients — `$BF`-framed
login/bootstrap, then realtime v3 (COBS framing + CRC-16/CCITT-FALSE) — to
the same live server.

Unlike the Lynx (raw serial + netstream), the Intellivision has **no
netstream**: everything runs over a plain N-device TCP connection through
the FujiNet mailbox at `$9C00`, polled with `NETCMD_STATUS`/`READ`/`WRITE`.
The server does not care — it sees one TCP stream carrying `$BF` bootstrap
bytes, then `RT3\n`, then COBS frames.

## What it looks like

- **20×10 tile viewport** (rows 0–9) — the same 20×10 world view as the
  Atari and Lynx clients, one 8×8 GRAM card per tile, color stack mode.
- **Row 10**: HUD — heart, HP/max, level, gold, PvP flag.
- **Row 11**: server messages (marquee-scrolled when longer than 20 chars),
  falling back to the active quest line.
- Dialogue pages open as a modal overlay (side button = continue/accept,
  Clear = decline).
- Everything is BACKTAB card stamping — no MOBs. Movement is tile-locked,
  and 8 sprites could never cover player + 6 entities + 4 remotes + 4 item
  drops anyway.

Controls: disc = move (8-way, one step per server tick, client-predicted),
top side button = attack (aim follows the disc, diagonals included), lower
side buttons = interact/pick up/advance dialogue, keypad 5 = PvP toggle,
keypad 9 = diagnostics line, Clear = decline dialogue.

Art is 40 GRAM cards in `art/intv_cards.json`, drawn at 1bpp with one STIC
color each in `tools/tile-editor/intv.html` and compiled to `gfx.bas` by
`tools/gen_gfx.py` — see "Art" below.

## Build

Needs `intybasic` (v1.4.2) and `as1600` (jzIntv SDK-1600) on PATH, and the
IntyBASIC library dir (prologue/epilogue) — default
`~/Workspace/IntyBASIC/intybasic/`, override with `LIBDIR=`.

```sh
make                        # -> fujirealm.bin/.cfg (SD load) + fujirealm.rom (jzIntv)
make SERVER_HOST=my.host    # bake a server endpoint (default localhost)
```

Like the other clients, the endpoint is baked at build time; copy
`config.mk.example` to `config.mk` to make it stick. Changing the host
forces a relink. `localhost` is only useful under emulation.

## Run

Real hardware: put `fujirealm.bin` + `fujirealm.cfg` on the PiRTO II SD
card. Emulation needs the FujiNet-patched jzIntv plus a fujinet-firmware
**RS232/BoIP** build (`fujinet-pc`) running on `localhost:9995`:

```sh
# terminal 1+2, from the repo root:
make run-login-server       # port 9010
make run-server             # port 9000
# terminal 3: fujinet-pc RS232 build (BoIP on 9995)
# terminal 4:
./run.sh                    # jzintv --fujinet=localhost:9995
```

Booting with no FujiNet mailbox at all (plain jzIntv) lands in an **offline
demo**: a real overworld slice with local prediction only — useful for
render/input work with zero infrastructure.

## Identity

First boot asks for a name (disc up/down cycles letters, side button
accepts), registers it with the login server, and caches
`"<name>,<token>,<host>"` in FujiNet appkey creator `$3022` / app 2 / key 1
(same creator as the Lynx client). Later boots resume silently. The host is
stored inside the record and compared with the build-time host, so pointing
at a different server forces a fresh login.

## Files

| File | Role |
| --- | --- |
| `fujirealm.bas` | boot flow, main loop |
| `frconst.bas` | constants, RAM map, **IntyBASIC coding rules** |
| `vars.bas` | every cross-module DIM (declare-before-mention) |
| `fujinet.bas` | FujiNet mailbox driver — verbatim from netcat, do not edit |
| `bootstrap.bas` | `$BF` HELLO/WELCOME/WINDOW parser (also parses login replies) |
| `rt.bas` | realtime v3 codec: COBS + CRC + builders + dispatch |
| `cache.bas` | 32×24 terrain window (ring buffer), edge/fill/commit/resync |
| `state.bas` | message handlers, prediction (ports of rt_state.c / predict.c) |
| `render.bas` | viewport repaint, object stamping, HUD, marquee, dialogue modal |
| `input.bas` | disc/buttons/keypad, movement cadence |
| `login.bas` | appkey identity, token parse, login round trip, name entry |
| `sound.bas` | PSG effects (no PLAY — it costs 28 variables) |
| `crc_tab.bas`, `gfx.bas`, `testmap.bas`, `server_cfg.bas` | generated |

## Design notes (why it looks like this)

- **Ring-buffered terrain window.** The Lynx memmoves 700+ bytes per
  TERRAIN_EDGE; at CP-1610 speed that is 4–5 frames per walk step. Here an
  edge bumps `col_off`/`row_base` and writes only the 24/32 new tiles —
  everyone reads cells through the shared `taddr` DEF FN.
- **One mailbox read per loop pass, capped at 192 bytes.** `fn_transact`
  blocks ≥1 frame, so the loop budget is one STATUS + one READ + at most
  one WRITE; all outgoing frames of a pass batch into a single `net_write`
  (COBS frames concatenate freely on TCP). FN_RX is volatile across
  transactions, so both parsers are byte-fed state machines whose partial
  frames persist in cart RAM accumulators.
- **The 64-byte zero-padded workspace is load-bearing.** Senders strip
  trailing zero payload bytes; every handler reads fixed offsets from RTWS
  after the tail is zeroed. Skipping that re-padding corrupts every short
  frame.
- **Timers count `FRAME`, never loop passes** (a pass is 2–8 frames and
  varies). Note frame-based timeouts assume real-time frames — running
  jzIntv with `--ratecontrol=0` expires the bootstrap deadline instantly.
- **Variable budget is the scarcest resource**: 215/222 8-bit and 37/47
  16-bit in use. Entity/remote/item snapshots, text buffers, and both
  terrain windows live in cart RAM (`$8100–$89BF`) via PEEK/POKE — see the
  map in `frconst.bas`, and mind the masked-PEEK rules at the top of that
  file (the v1.4.2 dropped-mask bug is real).
- Cart RAM starts at `$8100`, not `$8000`: the console's STIC alias sits at
  `$8000–$803F` and jzIntv's layered bus can let it shadow cart RAM.
- ROM is split `$5000–$6FFF` + `$A000–$B7FF` (`ASM ORG $A000` before the
  boot-only modules and generated data). **Check `fujirealm.cfg` after
  growing the code**: IntyBASIC silently spills past `$6FFF` into unsafe
  `$7000`, and past `$B7FF` sits a GRAM alias.

## Regenerating the generated files

```sh
make art                                        # art/intv_cards.json -> gfx.bas
make check-art                                  # fail if gfx.bas is stale
python3 tools/gen_crc.py > crc_tab.bas          # CRC-16 tables (self-testing)
python3 tools/gen_testmap.py > testmap.bas      # offline demo terrain
```

`gfx.bas` is a real make dependency of the build, so editing the art and
running `make` is enough; `check-art` runs from the repo root as part of
`make test`.

### Art

The source of truth is **`art/intv_cards.json`**, edited in the browser at
`tools/tile-editor/intv.html` (see that directory's README). It holds the 40
GRAM cards as 8x8 1bpp bitmaps plus one STIC color each, which is the whole
color model here: the screen is in color-stack mode with every entry black,
so the background is always black and the BACKTAB word carries the cell's
foreground color. That is also why the three player cards are reused for
remote players — only the word's color changes.

`tools/gen_gfx.py` compiles the project to `gfx.bas`; `tools/intv_cards.py`
holds the schema, the runtime bindings (tile id -> card, entity species,
item drops) and the word encoder, and is the Python twin of the editor's
`intv-model.js`. Bindings are generated metadata: both sides refuse a
project file that edits them.

`tools/convert_tiles.py` is the **bootstrap** that produced the first
version of the JSON by reducing each 16-color Lynx tile to a 1bpp mask plus
a color — terrain by luminance threshold, objects by corner-sampled
background removal, with hand corrections in `OVERRIDES`/`HAND_TILES`. It is
no longer part of the build, and `--seed` overwrites hand-drawn art with the
derived version, so run it only to start over:

```sh
python3 tools/convert_tiles.py --preview        # ASCII proofs to stderr
python3 tools/convert_tiles.py --seed           # DISCARDS hand-drawn art
```

## Status / not yet done

Tested end-to-end against the live server under jzIntv + fujinet-pc:
bootstrap, movement/prediction/corrections, edge scrolling with acks in
both axes, forced-desync resync → full window fill → commit, live tile
updates, HUD/messages/quests, multi-page dialogue with accept/decline.

Not yet exercised on real PiRTO II hardware. Deferred: shot tracer
visuals, inventory overlay, per-map palette variants (cave tiles have their
own colors already), NET_STATS telemetry, walk animation frames.
