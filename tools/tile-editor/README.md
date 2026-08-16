# FujiRealm Tile Editor

The browser-based art tool for both FujiRealm clients. It is a plain static page
with no build step and no server: open the `.html` file directly.

| Page | Edits | Feeds |
| --- | --- | --- |
| `index.html` | `atari8-client/art/fujirealm_charsetter.json` | the Atari 8-bit ANTIC 4 tiles |
| `lynx.html` | `lynx-client/art/lynx_tileset.json` | the Atari Lynx 8x8 sprites |
| `intv.html` | `intv-client/art/intv_cards.json` | the Intellivision GRAM cards |

Each is linked from the others' headers.

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

### Player/Missile sprite

The six **local** player frames are drawn by the client as a Player/Missile
sprite rather than characters (`PMG_PLAYER=1`, the default). Select one of them
and tick **Edit PM sprite** to swap the centre canvas for the PM grid: 8 pixels
wide by 24 rows, with an orange line marking the top of the tile the player
stands in — the rows above it overhang and draw over the terrain behind.

A pixel has four values rather than five: transparent, `COLPM0`, `COLPM1`, and
the overlap, which GTIA shows as the bitwise OR of the two colour registers.
That is where the extra colour comes from: the PM sprite does not spend any of
the four playfield colours the terrain needs. Right-click erases.

PM art is optional in the project file. Until you edit it, it is derived from
the character frames below it, so editing the 2x2 character sprite keeps the
PM sprite in step. The first PM edit stores the frames explicitly and that link
stops; **Reseed From Characters** re-derives the selected frame on demand.

Remote players are still character art — there are only four GTIA players, and
this client renders up to twelve of them.

### Bullet missile

Bullets ride the four GTIA missiles (M0 local, M1-M3 the remote tracers).
Select the **Bullet** tile and tick **Edit PM missile** for its grid.

A missile is two bits wide in a single colour, so that is the whole budget:
eight rows of two pixels, drawn in `COLPF3`. There is no colour to pick — left
click lights a pixel, right click clears it. The two pixels are 2 colour clocks
each at the double width the client uses, so the missile covers one character
cell, the left half of the two the character bullet used to fill.

Like the PM sprite this is optional and derived until edited, here by
downsampling the Bullet tile's top cell: each half of a row lights one pixel if
any of its four pixels were lit, which keeps the glyph's vertical profile and
discards horizontal detail that cannot survive at two pixels wide. Editing the
Bullet tile's characters therefore keeps updating the missile until you draw on
the missile directly.

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

## Intellivision editor (`intv.html`)

The most constrained of the three. A GRAM card is 8x8 and **1bpp** — there is no
per-pixel colour at all. The screen runs in colour-stack mode with every entry
black, so the background is always black and each BACKTAB word carries one STIC
colour for the whole cell. A card is therefore a shape plus a single colour, and
that is exactly what the editor gives you.

Load `intv-client/art/intv_cards.json`. It holds the 40 cards: 35 terrain and
entity cards (one per streamed tile id), three player frames, the potion, and the
HUD heart.

- Left click sets a pixel, right click clears it, space inverts the card.
- The palette selects the **card's** colour, not a pen. Colour 0 is disabled
  because it is the background — a card painted in it would be invisible.
- The actual-size panel shows the BACKTAB word the card compiles to and the GRAM
  budget (40 of the STIC's 64 cards are in use).
- The neighbours panel repeats the card 3x3 for checking terrain seams.
- The two file icons import and export IntyBASIC `BITMAP "…"` text, so a card can
  be pasted straight in from — or out to — `gfx.bas` or any other IntyBASIC
  source. Import also accepts bare rows and `1`/`0` notation.

Because one colour has to carry a whole cell, the useful moves here are different
from the other two editors: silhouette and internal contrast do all the work, and
a shape that reads at 8x8 in a single colour usually wants *fewer* set pixels
than the derived art has.

Saving downloads the JSON. Drop it back over the file and rebuild:

```sh
make -C intv-client art     # regenerate gfx.bas
```

`make -C intv-client check-art` verifies the checked-in `gfx.bas` is current with
the art, so a forgotten `make art` fails rather than shipping stale cards.

The `bindings` block (which card draws which tile, entity species, item drops)
is runtime metadata owned by `intv-client/tools/intv_cards.py`: the editor shows
it and both the browser and the generator reject a file that edits it. Pixels and
colours are what you change.

## Tests

The pixel/model layer is unit tested and needs only node:

```sh
node --test tile-model.test.js
node --test lynx-model.test.js
node --test intv-model.test.js
```

Or `make test-editor` from the repo root, which runs all three.

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
