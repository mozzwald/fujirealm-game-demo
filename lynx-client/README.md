# FujiRealm — Atari Lynx Client

The **Atari Lynx** client, talking to FujiNet over **ComLynx**. It uses the
*same* game server as the Atari 8-bit client and speaks the *same* wire
protocol (`$BF` bootstrap + realtime v3 COBS/CRC-16 frames) — only the
transport driver and the graphics engine are Lynx-specific.

This directory is self-contained: source, build, art pipeline, and host tests.

## Why a separate client

The Atari Netstream handler (`atari8-client/netstream/`) is POKEY-serial code
and cannot run on the Lynx. The two machines share almost nothing at the
hardware level:

| | Atari 8-bit client | Lynx client |
| --- | --- | --- |
| CPU | 6502 | 65C02 (WDC), up to 4 MHz |
| Graphics | ANTIC mode 4 char cells, 2×2 tiles, 5 colors | Suzy sprite blitter, no tile modes, 16 colors of 4096 |
| Screen | 40×24 chars (320×192) | 160×102, 4bpp framebuffer, double-buffered |
| Net link | POKEY serial -> FujiNet SIO, TCP | Mikey UART -> FujiNet ComLynx, **raw netstream over TCP** |
| Toolchain | MADS assembler | cc65 (`cl65 -t lynx`), mostly C |

What is shared and reused unchanged: the **server**, the **protocol**
(`docs/PROTOCOL.md`), and the **art source of truth** (the tile-editor project
in `atari8-client/art/`), which is re-exported to Lynx sprites instead of an
ANTIC font.

## Transport: raw ComLynx -> TCP

FujiNet-Lynx exposes a NetStream device (`fujinet-firmware/lib/device/comlynx/
netstream.cpp`). With `redeye_mode = false` it is a **raw byte pipe**. The
current plan is to select **TCP** with the FujiNet netstream init flag byte, so
the Lynx uses the existing FujiRealm server (`fujinet.online:9000` by default,
overridable -- see "Pointing the cart at a server") rather than adding a UDP
server path.

- Init command target: Fuji device `0x70`, command `0xF0`, port, host string,
  trailing NUL, then a flag byte.
- Flag bit `0x01` selects TCP. Flag bit `0x02` asks FujiNet to send the
  `REGISTER` preamble on connect. Flag bit `0x04` enables redeye mode; the game
  keeps this clear for raw netstream.
- The cart sends `SERVER_HOST:HYBRID_SERVER_PORT` with flags `0x03`
  (TCP + REGISTER + raw mode).

The "redeye" mode of the same device is for bridging *native* Lynx link-cable
multiplayer and is unrelated to this client — we always run it raw.

## Graphics: Option B (enhanced 16-color, 16×16 tiles)

Chosen direction (see the design preview rendered from the real game art):

- **10×5 tile viewport** (160×80) of 16×16 tiles.
- **Per-sprite palettes**: each tile/sprite remaps its 4 pens into a shared
  16-color CLUT, so grass/water/trees/UI each get true color — the Lynx's big
  win over the Atari's 5 shared registers.
- **22px HUD**: three full-width rows drawn with a compact 4×5 bitmap font
  (the A8 font reused its ASCII letter slots for tile art, so the Lynx ships
  its own text font) — a stats row (hearts / gold / level), a line for server
  `MESSAGE` packets, and the active quest from `QUEST_UPDATE`.
- Player, beavers, goblins, and bullets are Suzy sprites (hardware collision
  available as a hint; the server stays authoritative).

## Toolchain

- **cc65** `cl65 -t lynx`. Mostly C; small assembly/inline only where it earns
  its keep (UART ISR fast path, blit setup).
- cc65 ships a ComLynx serial driver (`lynx-comlynx.ser`) and `<lynx.h>` /
  `<_mikey.h>` register definitions — the client builds on these rather than
  from scratch.
- Output is a `.lnx` cartridge image for emulators / flashcart.

## Testing reality

**There is no FujiNet-capable Lynx emulator.** Runtime validation against real
FujiNet is manual, on hardware (Lynx + FujiNet-Lynx + flashcart). To keep
development fast without hardware in the loop, early phases build a host-side
**host-side protocol tests** and existing hybrid-server tests so framing,
bootstrap assembly, and connection transitions can be exercised without the
cart. Non-network logic (COBS/CRC codec, art conversion, map math) is
unit-tested natively on the host.

## Layout

```
lynx-client/
  README.md            this file
  src/                 cc65 C/ASM sources
  art/                 Lynx tileset + generated sprite arrays
  tools/               art importer, host tests, cc65 header stubs
  design/              resolution mockups behind the graphics decision
  Makefile             cl65 build + host tests
```

## Picking a name

The cart has no keyboard, so the player's name is entered on a slot-machine
picker: up/down spins the slot through `A-Z 0-9`, A commits the character and
moves on, B deletes, and A on the empty slot (`_`) starts the game. Eight
characters maximum, uppercase only -- the 4x5 font has no lowercase, and a
comma would break the AppKey record, which is comma-delimited.

It is shown only when there is no name to use: a first boot, a cart rebuilt
against a different `SERVER_HOST`, or a name the login server reports as
already taken (which re-prompts up to three times, pre-filled with what was
typed). Otherwise the name comes out of the AppKey record and the cart boots
straight into the game without asking.

The decision logic is in `src/nameentry.c` with no I/O in it, so it is
host-tested (`tools/host_tests.c`) like the dialogue modal's; `main.c` owns
only the screen and the joypad. The screen reuses the dialogue modal's line
renderer and its single shared `msg_sprite`, so it costs no sprite RAM.

## What the client does

After loading or creating its AppKey identity, the cart bootstraps the 32x24
terrain window, enters realtime on the same TCP stream, and opens a live 10x5
Suzy-rendered viewport. The D-pad predicts one legal tile locally while the
server stays authoritative and corrects through `WORLD_STATE`. `WORLD_STATE`
moves the local player and enemies and mutates terrain; `REMOTE_PLAYERS` draws
other live clients; `HUD_UPDATE`, `MESSAGE` and `QUEST_UPDATE` fill the three
4x5 text HUD rows. A fires in the aimed direction, one of eight including the
diagonals; B sends the pickup/interact counter. `DIALOGUE_PAGE` opens a
full-screen modal for story scenes, where A advances or accepts and B declines.

The client keeps a bounded queue of locally accepted moves and replays the
unacknowledged ones over each `WORLD_STATE` using its `echo_client_seq`
(`src/predict.c`), so a correction does not rubber-band the player. The terrain
cache follows the player: `TERRAIN_EDGE` strips shift the active 32x24 array in
place and are acknowledged with `CACHE_STEP_ACK`, while gaps too large to patch
incrementally fall back to a full `RESYNC_REQUEST` / `WINDOW_ROW` /
`WINDOW_COMMIT` transfer assembled in a separate buffer, so a partial window is
never rendered (`src/bootstrap.c`).

The starter dungeon works the same way: stepping onto the cave entrance
triggers a server `MAP_CHANGE`, the client freezes input behind an
`ENTERING...` banner while the new map streams in on the same connection as a
full `WINDOW_ROW` fill, then sends `MAP_READY` and cuts to the cave. Walking
onto the exit returns by the same path. This needs no cave-specific art: unlike
the Atari client, which swaps character tables, the Lynx cave tiles are
distinct logical ids already present in the shared tile set, and the 16-colour
CLUT already carries the stone colours.

One protocol subtlety worth knowing: the server's cache-step revision counter
is never rewound by a resync, so the edge that follows one can carry any
revision. The client therefore trusts the next geometrically adjacent edge as a
fresh baseline once it has requested a resync (`revision_trust_next` in `struct
bootstrap_state`) rather than demanding strict revision continuity — without
that, recovery loops re-requesting resyncs forever.

## What real hardware taught us

There is no FujiNet-capable Lynx emulator, so every one of these was found by
running the cart on a real Lynx. They are the most transferable part of this
directory: if you are writing a networked Lynx client, you will meet them too.

**Suzy needs a byte-aligned scanline pad — and then draws it.** Each scanline
of a tile is a count byte, 8 pixel bytes, and a zero pad byte Suzy requires
(without it it consumes the next line's count as pixel data). But the pad also
*renders*, so a tile paints 18 pixels into a 16-pixel cell, spilling 2 pixels
of pen 0 into its neighbour. See "Rendering" below for how the renderer hides
that.

**Never call `clock()` on this target.** cc65's `clock.s` registers a VBL
interruptor whose handler returns with carry indeterminate (its `clc` is
commented out), which can stop the interrupt chain before the TGI driver's
`irq` clears `SWAPREQUEST`. The page then never becomes visible and
`tgi_busy()` stalls the main loop — the display simply dies.

**Do not pace anything on the frame loop.** Counting loop iterations stretches
with render cost, because the loop rate is not stable. Movement is paced by
`WORLD_STATE` arrivals instead: the server emits one per 10 Hz tick, so it is
real time, immune to render cost, wrap-safe as a plain inequality, needs no
hardware timer, and gives exactly one step per tick.

**10 steps/s is a ceiling, not a compromise.** The server applies only the
newest `PLAYER_STATE` per tick, so faster stepping coalesces — and a
right-then-down pair inside one tick reaches the server as a diagonal delta
whose side-tile check fails against a wall, producing a correction and a hard
snap. Stepping once per server tick keeps deltas cardinal. For the same reason
a *perpendicular* turn waits for its cadence slot, so the two axes land in
different ticks; a *reversal* along the current axis steps immediately, since
it cannot produce a diagonal delta however the steps coalesce.

Before that cadence existed, holding the D-pad produced ~60 steps and packets
per second against a 10 Hz server. That wasted uplink on a half-duplex link and
overran the 8-entry prediction queue every ~130 ms, whose overflow path cleared
the queue and snapped the player backward — the "pause, then jump forward"
feel. Queue overflow is now plain backpressure that leaves predicted moves
intact.

**Drain the UART inside every wait loop.** The per-frame `while (tgi_busy())`
blit wait spun without reading the link, overflowing the ComLynx driver's
256-byte hardware RX ring during row bursts. Any spin that can outlast a packet
has to pump the receiver.

**Bound every retry and every send.** The client re-sent a full
`RESYNC_REQUEST` every ~0.75 s for the entire duration of a window fill, and an
unbounded ComLynx TX wait could stop the main loop permanently. Realtime sends
now time out and retry; status redraws wait for their VBL swap, and both pages
are cleared before live rendering, so the bootstrap/game transition is
synchronised.

## Build

```bash
make clean test all
```

`make art` regenerates the checked-in Lynx sprite arrays from the tileset;
`make test` verifies those arrays are current with their source, runs the host
and render tests, and lints the two Lynx-only files with gcc. `make room`
prints how much of the MAIN segment is left.

### Pointing the cart at a server

The server endpoint is baked in at build time, using the same variable names
the Atari client's Makefile takes:

```bash
make SERVER_HOST=192.168.1.120                    # local server, default ports
make SERVER_HOST=myhost.local HYBRID_SERVER_PORT=9000 LOGIN_SERVER_PORT=9010
```

Defaults are `localhost`, `9000` (realtime) and `9010` (login) -- a real Lynx
cannot reach `localhost`, so always build with your own `SERVER_HOST`. Every
build prints the endpoint it baked in, and changing any of the three forces a
relink -- make dependencies track files rather than variables, so without that
a second `make` with a different host would be a no-op and quietly leave the
old address in the cart.

`SERVER_HOST` is limited to 31 characters. It is checked at compile time
(`server_host_fits_the_wire` in `main.c`), because the host goes into a SIO
command payload whose length is a single byte and into the 64-byte FujiNet
appkey value.

The cached login token is tagged with the host that issued it, stored as
`<username>,<token>,<host>`. A token is only meaningful to the server that
issued it, so a record written by a different `SERVER_HOST` is rejected and
the cart logs in again from scratch -- otherwise switching to a local server
would reuse the previous server's token, skip the login, and then fail to
authenticate with no obvious cause. Records written before the host was
recorded are rejected the same way, so the first build after this change
re-logs in once.

Run the matching server from the repository root:

```bash
make run-server
```

## Art workflow

`art/lynx_tileset.json` is the source of truth for Lynx pixel art. It holds
the 16-colour CLUT, 52 terrain tiles, 12 player frames and the entity
sprites, each as eight strings of eight hex digits. The 52 logical tile ids
are shared with the Atari client and the server's terrain stream; the id
contract is `docs/TILE_ALLOCATION.md`, and the array index here
*is* the server's tile id.

```
charsetter lynx.html  --edit-->  art/lynx_tileset.json  --make art-->  art/lynx_art.c
```

Edit it in the FujiRealm tile editor's Lynx page (`lynx.html` in the
charsetter repo), save over the file, and run `make art`.

The tileset was seeded from the Atari art by
`tools/export_lynx_tileset.py`, which halves each 16x8 ANTIC block to 8x8
and maps its pen values into the CLUT. That is a starting point, not the
destination: 8x8 art wants different choices than art drawn for 16x16 cells.
**A full re-seed overwrites hand-drawn work**, so it refuses unless given
`--force`, and it is deliberately not part of `make art`.

When the Atari side adds logical tiles, merge instead of re-seeding:

```
python3 tools/export_lynx_tileset.py --merge                    # add what's missing
python3 tools/export_lynx_tileset.py --merge --reseed-tiles 9,37-39
```

`--merge` seeds only slots the tileset does not have and preserves the rest
byte for byte; `--reseed-tiles` additionally re-converts slots that were
*repurposed* rather than added (slot 9 went from Beaver Hurt to Snake, and
37-39 became Town NPC / Grix / Warden Key). Names and `used` flags
always refresh from the Atari project, so a repurposed slot relabels itself in
the editor without touching pixels. `--dry-run` reports what would change.

`import_lynx_art.py` falls back to converting the Atari art directly if the
tileset file is absent, so a fresh checkout without it still builds.

### Transparency: pen 0 is not always transparent

Two sprite kinds treat pen 0 differently, which decides how backgrounds
should be drawn:

- **Entity sprites** (the tileset's `entities` list: `item_gold`,
  `item_sticks`, `item_herb`, `item_potion`, `item_key`, plus the bestiary --
  beaver, snake, bat, slime, goblin, gorvak, wilhelm) are drawn with a
  transparent sprite type, so **pen 0 is transparent** and the terrain shows
  through. Give these a pen-0 background and they look right on grass, cave
  floor, anywhere.
- **Terrain tiles** are copied flat into the framebuffer, so **pen 0 is an
  opaque colour** (CLUT index 0, black). A terrain tile with a pen-0
  background renders a black square, not transparency. Object tiles that need
  ground showing through (herb, grave, the named NPCs, the Floodworks props)
  are precomposed over the tile they stand on at build time — see
  `OBJECT_TILE_BASE` in `tools/import_lynx_art.py`.

A few terrain tiles are objects sitting on grass -- the herb and the grave.
So that they can use a pen-0 background and still show grass rather than
black, the renderer composites them: it draws a grass tile first, then the
object tile with the transparent sprite type on top
(`tile_is_grass_object` in `render.c`). Add a tile id there to give it the
same treatment. Ordinary full-cell terrain (water, road, cave floor/wall)
should keep an opaque background and is not composited.

During bootstrap, the eight boxes, left to right, are:

1. ComLynx serial open.
2. Cached AppKey loaded (yellow on a first run is expected -- and a first run
   is where the name picker appears; see below).
3. Identity token ready, from AppKey or login.
4. Identity persisted or already cached.
5. Realtime TCP netstream enabled.
6. Valid `WELCOME` received.
7. Complete 24-row `WINDOW` assembled.
8. Valid realtime `WORLD_STATE` received after authentication.

On a cached-AppKey reboot, all eight should be green before the live viewport
replaces the bootstrap screen. No Lynx emulator is installed on the current
PATH, so the corrected display transition, sustained movement, tile columns,
remote visibility, and A/B actions remain a real-hardware check.

If bootstrap fails, the bars are replaced by a hexadecimal diagnostic screen:

- `R` — 24-bit received-row mask; success is `FFFFFF`.
- `S` — Lynx driver serial status: `80` RX ring overflow, `10` parity error,
  `08` UART overrun, `04` framing error, `02` break (values may combine).
- `T` — low 12 bits of the total raw bytes accepted by the application receive
  ring during bootstrap. This is diagnostic only; no byte count controls the
  protocol state. A normal run may show the 12-byte HELLO echo in addition to
  server packets.
- `P` — number of `$BF` parser errors.
- `L` — last parser error: `1` version, `2` length, `3` checksum.
- `E` — bootstrap validation error: `1` WELCOME length, `2` WELCOME version,
  `3` short WINDOW, `4` WINDOW geometry, `5` tile count/length, `6` changed
  tick/origin.
- `W` — number of checksum-valid `WINDOW` packets parsed.
- `B` — bytes retained in the persistent `$BF` parser when reception stopped.

## Rendering: dirty-tile terrain

Terrain sprites use a Suzy `BACKGROUND` type, for which pen 0 is an ordinary
colour rather than transparency, so every one of a tile's 256 pixels is
written. Measured cost is about 2 us per written pixel — the same rate as
entity sprites, which use a transparent type and so write only their ~70
non-zero pixels. Cost tracks pixels written, not the number of draw calls:
cc65's `draw_sprite` puts the CPU to sleep (`stz CPUSLEEP`) for the whole
blit, so per-call overhead is minor and SCB chaining would buy little.

Since a repainted terrain cell is opaque, it fully erases whatever was drawn
over it. So the viewport only needs a full 50-tile repaint when the camera
scrolls, the window origin moves, or a terrain cell changes. Otherwise the
renderer repaints just the cells that entities covered the last time that
page was drawn, and redraws the entities. That is a handful of tiles instead
of fifty while the player is stationary.

A dirty row is repainted as a **run from its leftmost dirty column to the
right edge**, not cell by cell. Each scanline of a tile is a count byte,
8 pixel bytes, and a zero pad byte that Suzy requires (without it Suzy
consumes the next line's count as pixel data) but also renders — so a tile
paints 18 pixels into a 16 pixel cell, spilling 2 pixels of pen 0 into its
neighbour. A full redraw hides that because the next tile immediately covers
it; repainting an isolated cell leaves a black column on its right edge.
Painting a run left to right means each spill is covered by the following
tile, and the last one falls off screen.

Both of those are tracked twice over, once per alternating page: a change
must reach both buffers, and each page's stale entity rows are its own. The
failure mode if that bookkeeping is wrong is sprite trails.

The saving is largest standing still and smallest while walking, since every
step scrolls the camera and forces a full repaint anyway.

## Measuring frame cost and link quality

The cart carries three runtime buttons read straight from Suzy, because
cc65's joystick driver masks the Option buttons out of `SUZY.joystick` and
Pause is not in the joystick register at all (it is bit 0 of
`SUZY.switches`, which nothing else in the runtime reads).

- **Option1** cycles the diagnostic line: off -> performance -> link -> off.
- **Option2** toggles PvP (the server edge-detects the counter it bumps).
- **Pause** cycles the render layers: `M0` everything, `M1` no terrain,
  `M2` no terrain and no entities. Leaving a mode forces a full repaint, so
  M1/M2's deliberate smears do not linger into M0 readings.

Performance page: `M0 F18 W10 P2 C3 E12 R1`

| | meaning |
| --- | --- |
| `F` | frames/s. Derived from the server's 10 Hz `WORLD_STATE` stream (ten of them is one second), so it needs no local timer. |
| `W` | `WORLD_STATE`/s. Should sit at the 10 Hz server tick; lower means the output budget is dropping coalesced updates. |
| `P` | predicted moves awaiting acknowledgement. |
| `C` | corrections (hard snaps) since boot. |
| `E` | terrain edges applied. `R` resync requests sent — a climbing `R` is what an "invisible wall" looks like from inside the client. |

Link page: `M0 X4 T320 S0`

| | meaning |
| --- | --- |
| `X` | frames/s rejected for bad CRC, length or version. |
| `T` | realtime bytes/s transmitted. `SER_PUT` disables the receive interrupt for the whole transmission, so deaf time is `T * 11 / 62500` seconds — `T=320` is about 5.6% of every second unable to receive. |
| `S` | sticky serial status: `80` ring overflow, `10` parity, `08` overrun, `04` framing. Non-zero means bytes were genuinely lost. |

`M1` and `M2` look wrong, because nothing fully erases the previous frame.
They are for pricing the terrain blits by difference, not for playing:
terrain cost = `1/F(M0) - 1/F(M1)`, read while **walking**, since that is
when every frame is a full repaint.

There used to be an `M3` that drew terrain at half scale, to settle whether
tile cost was dominated by the number of Suzy calls or the number of pixels
written. It was answered — per-call, which is why terrain is now a CPU
framebuffer copy rather than one Suzy blit per cell — and the answer is why terrain is a
framebuffer copy today. `M3` scaled the Suzy terrain blits,
which no longer exist, so it went away with them.

### What the readings mean

Read `F` in `M0`, `M1` and `M2`, both standing still and walking:

- If `F` climbs sharply from `M0` to `M1`, the tile blits dominate and the
  fix is render-side (SCB chaining, so Suzy walks one linked list instead of
  50 separate start/wait cycles).
- If `F` barely moves between `M0` and `M1` but still collapses when
  walking, drawing is not the problem. Check the link page: `X` or `S`
  rising with `T` means our own transmissions are corrupting reception,
  because ComLynx is half duplex and the driver cannot receive while it
  sends. The fix is then to transmit less and to defer transmission until
  the line is quiet, not to touch the renderer.
