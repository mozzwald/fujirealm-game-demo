# FujiRealm — Amiga Client

FujiRealm for any Amiga from an A500 up: **Kickstart/Workbench 1.3 and later,
68000**, playing on the same live server as the Atari 8-bit and Lynx clients,
over **FujiNet NIO** (`fujinet-nio.device`).

Same server, same wire protocol (`$BF` bootstrap + realtime v3 COBS/CRC-16),
same logical tile ids. The protocol codec, bootstrap, terrain cache,
movement prediction and dialogue logic are **compiled straight from
`../lynx-client/src`** (`bootstrap.c`, `rt_state.c`, `predict.c`,
`dlgmodal.c`), so the two clients share one copy of the hard-won parts.
What is Amiga-specific is the transport, the screen, the controls and the
main loop.

## Playing

Double-click the **FujiRealm** icon (the hero facing a goblin), or run
`FujiRealm` from the Shell. If `fujinet-nio.device` is not already resident,
FujiRealm loads it itself from `DEVS:`, `NIO:` or the current directory
(`LoadSeg` + `InitResident`, as `fujinet-load-resident` does). A title
screen spells FUJINET REALMS in the game's own tiles; any key, click or
fire continues (it times out after 15 s). The first run asks for a name
(1–8 letters or digits), logs in, and caches the identity in
`S:FujiRealm.id` as `name,token,host` — the Lynx appkey record, in a file.
A record from a different server is ignored and you log in afresh.

| Key | |
| --- | --- |
| Cursor keys, keypad 8/2/4/6 (7/9/1/3 diagonal), joystick in port 2 | Move / aim |
| Space, joystick fire | Shoot (in the aimed direction, diagonals too) |
| Return | Use: pick up, talk, accept |
| P | Toggle PvP |
| Esc | Quit (in a dialogue: decline) |
| Left mouse button (click or hold) | Walk to the pointer, stepping around a blocked diagonal; click yourself to Use |
| Right mouse button | Shoot toward the pointer (nearest of eight directions) |

`FujiRealm D` (any argument) replaces the key help with a link line:
bytes received/sent, polls, prediction corrections, resyncs, bad frames.

## How it differs from the Lynx

**Transport: NIO TCP instead of Netstream.** The Lynx switches its ComLynx
link into a raw TCP pipe. On the Amiga every read or write is a FujiBus
exchange through `fujinet-nio.device` (`src/net.c`): `fn_tcp_open`,
`fn_write`, `fn_read`, with the sequential stream offsets NIO TCP requires.
A read costs one serial round trip (~20 ms measured), so the link is polled
at a bounded rate (at least every 60 ms, draining back-to-back when data is
waiting) rather than every loop. The server needs no changes: it strips the
optional `REGISTER` preamble only when present, and `HELLO` asks for the
default link profile (2,000 B/s), well inside a NIO serial link. The login
exchange (port 9010) and the realtime stream (port 9000) are the same bytes
the other clients send.

**Timers run on the clock.** The Lynx counts frames because its loop is
paced by the blit. This loop is paced by network round trips, so heartbeats,
retries, shot steps and animation use `DateStamp`. Movement is still paced
by `WORLD_STATE` arrivals, exactly as on the Lynx (one step per 10 Hz tick).

**Graphics.** A 320×200, 16-colour lores screen: the Lynx's 20×10 tile view
at 16×16 (its 8×8 art doubled), over a 40-line HUD in the ROM topaz font.
`tools/amiga_art.py` converts `lynx-client/art/lynx_tileset.json` to planar
tiles and masked sprites, reusing the Lynx importer's object-over-ground
compositing and per-map palette tints. Terrain is kept in a retained layer
repainted only when the view scrolls or a cell changes; entities are
cookie-cut onto a compose buffer with `BltMaskBitMapRastPort` (present in
1.3) and copied to the screen after `WaitTOF`.

**Title screen.** `src/splash.c` builds FUJINET / REALMS from a 4×5 block
font on a 40×25 grid of the native 8×8 tiles (`art_tiles8`): water and
sandstone faces, extruded two cells deep in grey stone and black for the 3D
look, over a meadow with the cast standing on a road. The water shimmers by
cycling two palette entries, so animation costs the 68000 almost nothing.

**Icon.** `tools/mkicon.py` draws `FujiRealm.info` from the same tileset
(player frame and goblin sprite, scaled for hires pixels) in the four
Workbench 1.3 colours, as a tool icon with a 16 KB stack.

**Kickstart 1.3 safety.** `-mcrt=nix13` puts the 1.3 NDK headers first, so a
2.0-only call fails to compile. No floating point. `snprintf` only: with
`-lamiga` on the link line, `sprintf` resolves to amiga.lib's `RawDoFmt`
wrapper (no `%u`, 16-bit `%d`).

## Building

```sh
make NIO_WORKSPACE=/path/to/fujinet-nio-workspace    # build/FujiRealm, build/netprobe
make SERVER_HOST=my.host                             # another server, as the other clients
make test                                            # host tests
```

Needs bebbo's `m68k-amigaos-gcc` and a fujinet-nio-workspace checkout (for
fujinet-nio-lib). Defaults to `fujinet.online:9000`, login `9010`.

`build/netprobe` is a link check: it opens TCP through NIO, sends the
server's smoke probe byte, times the echo and measures the per-poll cost.

## Tested

On Workbench 1.3.3 / Kickstart 34.5 / A500 (68000) under Amiberry, with the
POSIX FujiNet NIO, against the live `fujinet.online` server: new-name login,
bootstrap (WELCOME + 24 rows), realtime entry, the overworld rendered with
the HUD, walking with camera scroll and server-accepted moves, turning and
firing.

Not yet exercised: map transitions (caves), dialogue scenes, PvP, item
pickup, long sessions, a real A500 with a FujiNet.

Two fixes elsewhere made this possible: a macOS POSIX NIO bug that failed
every `tcp://` connect (stale `errno` in the connect poll), and the
fujinet-nio-driver `DOSBase` fix for Kickstart 1.3.
