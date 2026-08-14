# Tile and Glyph Allocation

The canonical editable source is `atari8-client/art/fujirealm_charsetter.json`; runtime tables are generated from that project.

The logical tile IDs below are a shared contract, but each client owns its own art, because the hardware differs too much to share pixels: `lynx-client/art/lynx_tileset.json` holds 8x8 4bpp sprites, and `intv-client/art/intv_cards.json` holds 8x8 1bpp GRAM cards with one STIC colour each. All three are edited in `tools/tile-editor/`. The Intellivision draws only the 35 IDs the terrain stream actually uses — IDs 1 and 18-33 are dead legacy slots and have no card.

## Logical tile IDs

| ID    | Name                               | Character codes (TL, TR, BL, BR) | Ownership                                                 |
| ----- | ---------------------------------- | -------------------------------- | --------------------------------------------------------- |
| 0     | Grass                              | 34, 35, 36, 37                   | Existing                                                  |
| 1     | Local Player Front 0 (legacy tile) | 38, 39, 40, 41                   | Internal; use sprite frames instead                       |
| 2     | Tree Full                          | 62, 63, 64, 65                   | Existing                                                  |
| 3     | Herb                               | 194, 195, 196, 197               | Existing, bit-7 recolor                                   |
| 4     | Tree Damaged                       | 70, 71, 72, 73                   | Existing                                                  |
| 5     | Tree Stump                         | 74, 75, 76, 77                   | Existing                                                  |
| 6     | Bullet                             | 78, 79, 0, 0                     | Runtime draws only TL/TR                                  |
| 7     | Border                             | 82, 83, 84, 85                   | Existing                                                  |
| 8     | Beaver                             | 86, 87, 88, 89                   | Single state; no hurt tile                                |
| 9     | Snake                              | 90, 91, 92, 93                   | Dedicated                                                 |
| 10    | Road                               | 94, 95, 96, 97                   | Existing                                                  |
| 11    | Water                              | 11 repeated                      | Dedicated repeated pattern                                |
| 12    | Building                           | 12 repeated                      | Dedicated repeated pattern                                |
| 13    | Cave Entrance                      | 13 repeated                      | Dedicated repeated pattern                                |
| 14    | Grave                              | 14, 15, 32, 81                   | Dedicated                                                 |
| 15    | Cave Floor                         | 0 repeated                       | Intentional shared blank                                  |
| 16    | Cave Wall                          | 16 repeated                      | Dedicated repeated pattern                                |
| 17    | Cave Exit                          | 17 repeated                      | Dedicated repeated pattern                                |
| 18-33 | Legacy HUD/player logical entries  | Internal aliases                 | Hidden and never rendered as world tiles                  |
| 34    | Gold                               | 98 repeated                      | Existing                                                  |
| 35    | Sticks                             | 99 repeated                      | Existing                                                  |
| 36    | Hostile Goblin                     | 100, 101, 102, 103               | Existing                                                  |
| 37    | Town NPC (Generic)                 | 104, 105, 106, 107               | Dedicated                                                 |
| 38    | Grix                               | 108, 109, 110, 111               | Dedicated                                                 |
| 39    | Warden Key                         | 254 repeated                     | Single glyph duplicated 2x2                               |
| 40    | Daniel                             | 112, 113, 114, 115               | Dedicated                                                 |
| 41    | Wilhelm                            | 116, 117, 118, 119               | Dedicated                                                 |
| 42    | Lucian                             | 120, 121, 122, 123               | Dedicated                                                 |
| 43    | Nerissa                            | 124, 125, 127, 80                | Dedicated                                                 |
| 44    | Slime 0                            | 1, 2, 5, 6                       | Six-glyph animation owner                                 |
| 45    | Slime 1                            | 3, 4, 5, 6                       | Shares only fixed lower pair with frame 0                 |
| 46    | Bat 0                              | 18, 19, 20, 21                   | Eight-glyph animation owner                               |
| 47    | Bat 1                              | 22, 23, 24, 25                   | Four separate frame-1 glyphs                              |
| 48    | Pumpmaster Gorvak                  | 7, 8, 9, 10                      | Four dedicated glyphs                                     |
| 49    | Deep Pump                          | 26, 27, 28, 29                   | Dedicated                                                 |
| 50    | Pump Controls                      | 30, 31, 30, 31                   | Dedicated repeated control-panel pair                     |
| 51    | Wilhelm Working                    | 116, 83, 118, 85                 | Shares Wilhelm's left pair; editable alternate right pair |

Character values above 127 set the ANTIC 4 character-code color-select bit;  
their glyph index is the low seven bits.

## Physical glyph budget

- 0: cave floor and unused bullet lower cells
- 1-6: Slime (four upper-frame glyphs plus fixed lower pair)
- 7-10: Pumpmaster Gorvak
- 11-13: water, building, and cave entrance
- 14-15: Grave upper pair
- 16-17: cave wall and cave exit
- 18-25: Bat (four glyphs per animation frame)
- 26-29: Deep Pump
- 30-31: Pump Controls
- 32: Grave lower-left
- 33: HUD separator blank
- 34-37: grass
- 38-61: local-player frames; remote frames intentionally reuse these bitmaps
- 62-77: tree/herb/stump terrain
- 78-79: high projectile upper pair
- 80: Nerissa lower-right
- 81: Grave lower-right
- 82, 84: border (each intentionally repeated across its column)
- 83, 85: Wilhelm Working alternate right pair
- 86-89: beaver
- 90-93: snake
- 94-97: road
- 98-99: gold/sticks
- 100-103: hostile goblin
- 104-107: generic town NPC
- 108-111: Grix
- 112-115: Daniel
- 116-119: Wilhelm
- 120-123: Lucian
- 124-125: Nerissa upper pair
- 126: Warden Key
- 127: Nerissa lower-left

All 128 glyphs now have an audited runtime owner. No two distinct visible  
logical tiles share bitmap storage. The only sharing is intentional:

- Slime frames share their fixed lower pair.
- Remote-player frames reuse local-player bitmaps with character bit 7 set.
- Blank/repeated-pattern tiles reuse a glyph only within the same visual  
identity.
- Wilhelm's two frames share the fixed left pair and use separate right-side  
glyphs. Border's duplicate columns were collapsed to free glyphs 83 and 85.

The old custom-font `2-9` digits (glyphs 18-25) and `B`, `L`, `S`, colon  
(glyphs 26-29) were safe to reclaim: inventories, modals, and HUD text select  
the OS font before drawing those screen codes. The old mini-art in glyphs  
1-10 and 14-15 had no runtime table owner. Glyphs 11-13 and 16-17 were retained  
because they are live terrain mappings. The old remote-player-only glyphs  
108-125 were reclaimed after remote frames were bound to the local-player  
bitmap frames.

The active 52-entry tables occupy `$4F00-$4FCF`, leaving 48 bytes before the  
fixed 1 KB font at `$5000-$53FF`. The high overworld copy starts at `$8030`;  
cave labels alias it instead of duplicating an identical 204-byte table.

## Art constraints

- Keep logical IDs, names, categories, and animation bindings unchanged.
- Beaver has one art state. Damage feedback is a local blink, not another tile.
- Slime frames 44 and 45 must keep identical BL/BR characters; edit only TL/TR  
between frames.
- Bat frames 46 and 47 are client-timed; no animation frame is sent by server.
- Bullet ID 6 reserves only TL/TR. BL/BR must remain zero because the runtime  
restores and preserves the lower terrain cells.
- Warden Key ID 39 deliberately repeats one glyph in all four quadrants.
- Deep Pump owns four glyphs. Pump Controls owns two and intentionally repeats  
its pair on the lower row.
- Wilhelm Working (logical ID 51) must retain `116,83,118,85`; edit glyphs 83  
and 85 for the working pose while keeping the shared left side unchanged.
- There are no unallocated glyphs. Do not reassign a character without updating  
this ownership sheet and the automated 128-glyph audit.
