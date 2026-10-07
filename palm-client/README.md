# FujiRealm — Palm OS Client

FujiRealm for Palm OS (**FN Realm** in the launcher, creator `ADFR`), on the
same live server as the Atari 8-bit, Lynx, Amiga and CoCo 3 clients, through
**FujiNet's N1: device**. The setup screen selects one of four links:
Legacy cradle (Palm OS 3.3+), USB Library (Handspring Visor USB cradle),
BuiltIn SerLib, or Serial Library. The named libraries use the old Palm
Serial Manager and work on Palm OS 3.1. See
[fujinet-palm](https://github.com/dillera/fujinet-palm) for the Visor USB
bridge and FujiNet hardware setup.

Same server, same wire protocol (`$BF` bootstrap + realtime v3 COBS/CRC-16),
same logical tile ids. The protocol, bootstrap, terrain cache, movement
prediction and dialogue logic are compiled straight from `../lynx-client/src`,
and the login record from `../amiga-client/src/identity.c`.

## Playing

Everything is done with the stylus. Enter a name (1–8 letters or digits)
and a server, then tap **Play**; the first time, the client logs in and keeps
the token in its preferences.

| Tap | |
| --- | --- |
| The map (or hold and steer) | Walk there, routing around walls, trees and water; keeps going after the pen lifts |
| A person | Walk over and talk to them |
| A monster (or right beside it) | Shoot at it; with PvP on, tap a player |
| Yourself, or the text under the map | Use — Enter on the other clients: talk, pick up, accept |
| Anywhere in a conversation | Read on; a quest offer has **Accept** / **Decline** (tapping the text accepts) |
| Menu | Toggle PvP, Link Statistics (position, bytes, polls), Leave the Realm; Help: How to Play, Talking & Quests, About |

Items are picked up by walking over them. The setup screen saves one of two
hardware button layouts; the middle scroll buttons move up/down in both:

| Layout | Date Book | Contacts / Address | To Do | Memo / Notepad |
| --- | --- | --- | --- | --- |
| Prism (new installs) | Use | Left | Right | Fire |
| Original (existing installs) | Left | Right | Fire | Use |

The buttons are read by physical position, so either layout can be chosen on
a Prism or Palm IIIx. Existing preferences keep their original mapping until
you select Prism on the setup screen.

## Building

```sh
make                        # build/FujiRealm.prc (4 greys)
make GFX_DEPTH=1            # black and white
make GFX_DEPTH=8            # colour, for OS 3.5+ colour Palms (IIIc, m505...)
make SERVER_HOST=my.host    # bake another default server in
make install FUJINET=<ip>   # queue the .prc on FujiNet's SD card; HotSync to install
```

Each build is also copied to `build/FujiRealm-<depth>bpp.prc`. The build runs
in the `fujinet-palm-toolchain` Docker image (override with `IMAGE=palmdev`).
It compiles the FujiBus framing and N: driver from the sibling
`fujinet-texasHoldEm/palm/common` checkout (`FUJINET_HOLDEM` can override its
path). `src/fnlink.c` adds the four port choices while keeping the small
legacy network driver. This linked Palm build includes GPL-3.0 code; see
`THIRD-PARTY-NOTICES.md`. Art is converted on the host by `tools/palm_art.py`.

On a Visor with a USB cradle, choose **USB Library** before tapping Play.
Run `visorbridge.js` and FujiNet-PC, or connect the cradle to the supported
ESP32-S3 USB host firmware, as described in `fujinet-palm/README.md`. On an
emulator, choose **Serial Library**. For a serial HotSync cradle connected
directly to FujiNet, choose **Legacy cradle** on Palm OS 3.3+.

| `GFX_DEPTH` | Art | Screen |
| --- | --- | --- |
| 2 (default) | the Lynx tiles, each hand-mapped to four greys | 2 bpp, any OS 3.x Palm |
| 1 | the grey art taken to 1 bit, ground and NPCs redrawn by hand | 1 bpp |
| 8 | the Lynx tiles and palette, with its per-map tints | 8 bpp, OS 3.5+ colour |

**Code-section data.** m68k-palmos-gcc keeps `const` data in `.text`, which
only code in the same file can reach (PC-relative). A reference from another
file is compiled A5-relative and on a real Palm reads unrelated memory — this
once garbled every tile and every step. So the art is `#include`d into
`gfx.c`, `FujiRealm.c` keeps its own step tables, and the build runs
`tools/check_segments.sh`, which fails on any such cross-file reference. The
whole app is one code segment, so `.text` must stay under 32 KB (the colour
build is closest).

## Testing in an emulator

`tools/emulator/` holds a playtest rig: CloudpilotEmu (which emulates the
Palm III/IIIx/IIIc/V, m100, m505 and more, with grey and colour LCDs) with
its cradle serial port bridged through a socat pty pair to FujiNet-PC (the
RS232 build of FujiNetMicro), so the client talks to a real FujiNet and the
live server exactly as it does on a device.

`cloudpilot-serial-and-scripting.patch` (against cloudpilot-emu `064d5d5`)
adds to the native app:

* `--serial <tty>`: bridge the cradle UART to a host tty or pty;
* CLI commands `screenshot <png>` (the LCD at 1:1, through the Dragonball's
  grey palette), `tap <x> <y>`, `pen down <x> <y>` / `pen up`,
  `button <app1..4|up|down|power|cradle> [press|release|click]`,
  `key <text>` (`\b`, `\n` escapes).

Layout (paths the scripts assume, side by side in one directory):

```
emulators/cloudpilot-emu   git clone, patched; cd src && make bin
emulators/roms             ROM images (e.g. Palm-V-3.3-en.rom, Palm-IIIc-4.0-en.rom)
emulators/fnpc             FujiNet-PC: fujinet, data/, SD/, fnconfig.ini with
                           [Serial] port=<run>/fn-tty, [BOIP] enabled=0,
                           [HotSync] enabled=0, [Modem] modem_enabled=0
emulators/run              emu.sh, rig.sh, and the cmd FIFO
```

```sh
./rig.sh ../roms/Palm-V-3.3-en.rom          # or a saved session image
echo "install .../build/FujiRealm.prc" > cmd
echo 'launch "FN Realm"' > cmd
echo "button app2 press" > cmd; sleep 1; echo "button app2 release" > cmd
echo "screenshot shot.png" > cmd
echo "save-image palm-v.img" > cmd           # skip setup and login next time
./reenter.sh .../build/FujiRealm-8bpp.prc    # soft reset, reinstall, launch, Play
```

The patch also runs the emulated CPU in 0.5 ms slices with the serial
bridge pumped between them, so FujiBus round trips are not held to one per
60 Hz frame.

`socat.log` has a hex dump of every byte on the cradle line. FujiNet-PC
needs the IEXTEN fix in `lib/hardware/TTYChannel.cpp` (FujiNetMicro): with
extended input processing on, the tty swallows `0x16` and `0x0F`, which
corrupts FujiBus packets.
