# FujiRealm — CoCo 3 client

A [CMOC](http://perso.b2b2c.ca/~sarrazip/dev/cmoc.html) C client for the
Tandy Color Computer 3, drawn in 16×16 tiles and sprites in 16 colors.

It speaks the same protocol as the other clients over a plain N: TCP
connection through FujiNet's DriveWire interface (no netstream), polling for
data.

## What it needs

- A CoCo 3 with **128K or 512K**. With 512K the GIME scrolls the screen in
  hardware, so movement is noticeably smoother; with 128K there is no room
  for that, and the whole view is redrawn whenever it scrolls.
- A FujiNet for the CoCo (bitbanger or Becker-style), or XRoar with a
  FujiNet-PC.
- An RGB or composite monitor; the palette is chosen on first run and F1
  switches it.

## Build

cmoc and decb are not on the host PATH; build through `defoogi`:

```sh
defoogi make coco SERVER_HOST=192.168.1.100    # from the repo root
```

The output is `FUJIRLM3.dsk`. `make artview` builds `ARTVIEW.dsk`, a boot
disk that shows every tile and sprite with its use. Like the other clients,
the endpoint is baked in at build time; copy `config.mk.example` to
`config.mk` to make it stick. A host saved from the setup screen (F2)
overrides it at runtime. The first build clones and builds
fujinet-lib-experimental into `_cache/`.

The sound effects are defined in `tools/sound_gen.py`; `make sndtest` builds
`SNDTEST.dsk`, a boot disk that plays each one.

The art is drawn in `tools/artgen`; `./artgen.py --help` shows how it writes
the tileset and `src/palette.c`. `tools/tile-editor/coco.html` can touch it
up, but regenerating overwrites those edits.

## Run

Mount `FUJIRLM3.dsk` and boot: AUTOEXEC runs `FUJIRLM3`, which asks for the
display type on first run, logs in (or resumes), then loads the game,
`FRPLAY`.

## Controls

| Key | Action |
| --- | --- |
| Arrows / WASD, or joystick | Move |
| SPACE or joystick button | Fire (a stick's first button press only selects it) |
| ENTER | Talk, pick up, accept |
| H / M / I | Help, map, inventory |
| P | Toggle PvP |
| V | Walk speed |
| F1 | RGB / composite palette |
| F2 | Sound on / off (a note at the end of the HUD's top line) |
| BREAK | Exit to BASIC; in a dialogue, decline |
