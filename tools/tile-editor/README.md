# FujiRealm Tile Editor

The browser-based art tool for both FujiRealm clients. It is a plain static page
with no build step and no server: open the `.html` file directly.

| Page | Edits | Feeds |
| --- | --- | --- |
| `index.html` | `atari8-client/art/fujirealm_charsetter.json` | the Atari 8-bit ANTIC 4 tiles |
| `lynx.html` | `lynx-client/art/lynx_tileset.json` | the Atari Lynx 8x8 sprites |

The two are linked from each other's headers.

## Atari editor (`index.html`)

This is a FujiRealm-specific ANTIC 4 tile editor: it edits the 2x2 character
compositions the game uses rather than a generic screen map.

Open `index.html`, load `atari8-client/art/fujirealm_charsetter.json`, and select
an entry in the Tile Library. The centre canvas edits the complete 16x16 display
tile as an 8x16 ANTIC 4 colour-cell grid. The character editor and the full
256-code font view stay available for shared-glyph work and quadrant
reassignment.

A version 4 project contains:

- the 1 KB font;
- 52 logical tile bindings;
- 12 local/remote player frame bindings;
- six two-frame animation groups;
- the fixed FujiRealm overworld palette and library metadata.

Tile names, categories, visibility, target types, target indices, and animation
membership are runtime metadata: the game's importer rejects changes to them.
Pixel data and each tile's four character codes are what you edit.

Save over the JSON, then rebuild — the Atari Makefile regenerates the assembly
art include from the project automatically:

```sh
make -C atari8-client
```

## Lynx editor (`lynx.html`)

The Lynx tileset is a different format, not another view of the same data. The
Lynx has no character generator — Suzy draws sprites — so every tile is 8x8
pixels of direct CLUT indices, with no font and no 2x2 composition.

Load `lynx-client/art/lynx_tileset.json`. It holds the 16-colour CLUT, the
terrain tiles, 12 player frames and the entity sprites, with pixels stored as
eight strings of eight hex digits so the JSON stays readable and diffs usefully.

- Left click paints the selected pen; right click picks the pen under the
  cursor; `0`-`9` / `a`-`f` select a pen directly.
- The neighbours panel repeats the tile 3x3, which is how you catch seams on
  terrain that has to tile against itself.
- Pen 0 is transparent on entity sprites, so keep it black. See "Transparency"
  in `lynx-client/README.md` — terrain tiles treat pen 0 as opaque.

Saving downloads the JSON. Drop it back over the file and regenerate the C
arrays:

```sh
make -C lynx-client art
```

`make -C lynx-client test` verifies the checked-in arrays are current with the
tileset, so a forgotten `make art` fails the build rather than shipping stale
sprites.

The logical tile ids are shared with the Atari client and the server's terrain
stream; the id contract is `docs/TILE_ALLOCATION.md`, and the array index in
this file *is* the server's tile id.

## Tests

The pixel/model layer is unit tested and needs only node:

```sh
node --test tile-model.test.js
node --test lynx-model.test.js
```

## Offline use

`icons.css` is a local subset of [Bootstrap Icons](https://github.com/twbs/icons)
v1.11.3 (MIT), containing only the 19 icons these pages use, inlined as CSS
masks. The editor therefore needs no network connection at all.

## Credits

Built on **[Charsetter](https://www.atari.org.pl/charsetter/)**, the Atari 8-bit
font and map editor by the **4Coloreditor Team**, used with their kind
permission. Thank you!

FujiRealm's version replaces the generic font/map workflow with the game's
logical tile model, and adds the Lynx editor. The original is well worth using
in its own right for any Atari 8-bit ANTIC 2/4 work.
