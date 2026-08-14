' gfx.bas -- GRAM cards + color tables (GENERATED FILE, edit the art in
' tools/tile-editor/intv.html; regenerate: make art, or python3 tools/gen_gfx.py > gfx.bas)
' Source art: art/intv_cards.json. 40 of 64 GRAM cards used.

' gfx_init: one-time GRAM load. Each DEFINE takes effect on the next video
' frame, so every DEFINE is followed by WAIT (max 16 cards per DEFINE).
gfx_init: PROCEDURE
    DEFINE 0, 16, gfx_b0 : WAIT
    DEFINE 16, 16, gfx_b16 : WAIT
    DEFINE 32, 8, gfx_b32 : WAIT
END

gfx_b0:
' GRAM 0 <- tile 0 Grass (field, fg DARKGREEN)
    BITMAP "########"
    BITMAP "#.##.###"
    BITMAP "########"
    BITMAP "########"
    BITMAP "########"
    BITMAP "###.####"
    BITMAP "#####.##"
    BITMAP "########"
' GRAM 1 <- tile 2 Tree Full (object, fg DARKGREEN)
    BITMAP "........"
    BITMAP "..####.."
    BITMAP ".######."
    BITMAP ".######."
    BITMAP "..####.."
    BITMAP "...##..."
    BITMAP "...##..."
    BITMAP "..####.."
' GRAM 2 <- tile 3 Herb (object, fg YELGREEN)
    BITMAP "........"
    BITMAP "........"
    BITMAP "...##..."
    BITMAP "..####.."
    BITMAP "...##..."
    BITMAP ".#.##.#."
    BITMAP "..####.."
    BITMAP "...##..."
' GRAM 3 <- tile 4 Tree Damaged (object, fg DARKGREEN)
    BITMAP "........"
    BITMAP "..##.#.."
    BITMAP ".######."
    BITMAP ".#.####."
    BITMAP "..###..."
    BITMAP "...##..."
    BITMAP "....#..."
    BITMAP "..###..."
' GRAM 4 <- tile 5 Tree Stump (object, fg BROWN)
    BITMAP "........"
    BITMAP ".#..#..."
    BITMAP "........"
    BITMAP "........"
    BITMAP "........"
    BITMAP ".######."
    BITMAP "########"
    BITMAP ".######."
' GRAM 5 <- tile 6 Bullet (object, fg YELLOW)
    BITMAP "........"
    BITMAP "...##..."
    BITMAP "..####.."
    BITMAP ".######."
    BITMAP ".######."
    BITMAP "..####.."
    BITMAP "...##..."
    BITMAP "........"
' GRAM 6 <- tile 7 Border (field, fg DARKGREEN)
    BITMAP "########"
    BITMAP "########"
    BITMAP "########"
    BITMAP "########"
    BITMAP "########"
    BITMAP "########"
    BITMAP "########"
    BITMAP "########"
' GRAM 7 <- tile 8 Beaver (object, fg BROWN)
    BITMAP "..####.."
    BITMAP ".######."
    BITMAP ".######."
    BITMAP ".######."
    BITMAP "..####.."
    BITMAP "########"
    BITMAP ".######."
    BITMAP "..#..#.."
' GRAM 8 <- tile 9 Snake (object, fg YELGREEN)
    BITMAP "..#####."
    BITMAP ".######."
    BITMAP "######.."
    BITMAP "##..##.."
    BITMAP "##......"
    BITMAP "##...###"
    BITMAP "###.##.."
    BITMAP ".#####.."
' GRAM 9 <- tile 10 Road (field, fg BROWN)
    BITMAP "##.##.##"
    BITMAP "#.##.###"
    BITMAP ".#####.#"
    BITMAP "###.###."
    BITMAP ".######."
    BITMAP "##.##.##"
    BITMAP "#.####.#"
    BITMAP "###..###"
' GRAM 10 <- tile 11 Water (field, fg CYAN)
    BITMAP "..#...#."
    BITMAP "##.###.#"
    BITMAP ".###.###"
    BITMAP "##.###.#"
    BITMAP "..#...#."
    BITMAP "##.###.#"
    BITMAP ".###.###"
    BITMAP "##.###.#"
' GRAM 11 <- tile 12 Building (hand, fg TAN)
    BITMAP "...##..."
    BITMAP "..####.."
    BITMAP ".######."
    BITMAP "########"
    BITMAP ".######."
    BITMAP ".##..##."
    BITMAP ".##.###."
    BITMAP ".######."
' GRAM 12 <- tile 13 Cave Entrance (field, fg TAN)
    BITMAP "########"
    BITMAP "#..##..#"
    BITMAP "#..##..#"
    BITMAP "########"
    BITMAP "########"
    BITMAP "#..##..#"
    BITMAP "#..##..#"
    BITMAP "########"
' GRAM 13 <- tile 14 Grave (object, fg GREY)
    BITMAP "...###.."
    BITMAP "..#####."
    BITMAP ".#######"
    BITMAP ".#######"
    BITMAP ".#######"
    BITMAP ".#######"
    BITMAP ".#######"
    BITMAP ".#######"
' GRAM 14 <- tile 15 Cave Floor (field, fg GREY)
    BITMAP "........"
    BITMAP "........"
    BITMAP ".#...#.."
    BITMAP "........"
    BITMAP "........"
    BITMAP "........"
    BITMAP ".#...#.."
    BITMAP "........"
' GRAM 15 <- tile 16 Cave Wall (field, fg TAN)
    BITMAP "########"
    BITMAP "#.###.##"
    BITMAP ".#######"
    BITMAP "###.#.#."
    BITMAP "########"
    BITMAP "#.###.##"
    BITMAP "####.###"
    BITMAP "###.###."
gfx_b16:
' GRAM 16 <- tile 17 Cave Exit (field, fg GREY)
    BITMAP "########"
    BITMAP "#..##..#"
    BITMAP "#..##..#"
    BITMAP "########"
    BITMAP "########"
    BITMAP "#..##..#"
    BITMAP "#..##..#"
    BITMAP "########"
' GRAM 17 <- tile 34 Gold (object, fg YELLOW)
    BITMAP "........"
    BITMAP "..####.."
    BITMAP ".######."
    BITMAP "########"
    BITMAP "########"
    BITMAP ".######."
    BITMAP "........"
    BITMAP "........"
' GRAM 18 <- tile 35 Sticks (object, fg BROWN)
    BITMAP ".#......"
    BITMAP ".#...#.."
    BITMAP ".##..#.."
    BITMAP "..#..#.#"
    BITMAP "#.#.##.#"
    BITMAP "#.#.#..#"
    BITMAP "#.#.#.##"
    BITMAP "..#.#.#."
' GRAM 19 <- tile 36 Hostile Goblin (object, fg DARKGREEN)
    BITMAP ".######."
    BITMAP "########"
    BITMAP "########"
    BITMAP ".######."
    BITMAP "...##..."
    BITMAP ".######."
    BITMAP "..####.."
    BITMAP ".##..##."
' GRAM 20 <- tile 37 Town NPC (Generic) (object, fg BROWN)
    BITMAP ".####..."
    BITMAP ".####..."
    BITMAP "######.."
    BITMAP ".####..."
    BITMAP ".####..."
    BITMAP ".####..."
    BITMAP ".#..#..."
    BITMAP "##..##.."
' GRAM 21 <- tile 38 Grix (object, fg DARKGREEN)
    BITMAP "..####.."
    BITMAP ".######."
    BITMAP ".######."
    BITMAP "..####.."
    BITMAP ".######."
    BITMAP ".######."
    BITMAP "..####.."
    BITMAP ".##..##."
' GRAM 22 <- tile 39 Warden Key (object, fg YELLOW)
    BITMAP "...##..."
    BITMAP "..#..#.."
    BITMAP "..#..#.."
    BITMAP "...##..."
    BITMAP "...#...."
    BITMAP "...###.."
    BITMAP "...#...."
    BITMAP "...###.."
' GRAM 23 <- tile 40 Daniel (object, fg BROWN)
    BITMAP ".####.##"
    BITMAP ".####.##"
    BITMAP "..##..#."
    BITMAP "#######."
    BITMAP ".####.#."
    BITMAP ".####.#."
    BITMAP ".#..#.#."
    BITMAP "##..##.."
' GRAM 24 <- tile 41 Wilhelm (object, fg BROWN)
    BITMAP ".####..."
    BITMAP ".####..."
    BITMAP "..##..##"
    BITMAP "..######"
    BITMAP "..#####."
    BITMAP "..##..#."
    BITMAP ".####..."
    BITMAP ".##.##.."
' GRAM 25 <- tile 42 Lucian (object, fg DARKGREEN)
    BITMAP ".#######"
    BITMAP ".#######"
    BITMAP ".#######"
    BITMAP ".#######"
    BITMAP ".#######"
    BITMAP ".#######"
    BITMAP ".##....#"
    BITMAP ".#..##.."
' GRAM 26 <- tile 43 Nerissa (object, fg RED)
    BITMAP "..####.."
    BITMAP ".######."
    BITMAP ".######."
    BITMAP ".#.##.#."
    BITMAP "...##..."
    BITMAP ".######."
    BITMAP "..####.."
    BITMAP ".##..##."
' GRAM 27 <- tile 44 Slime 0 (object, fg YELGREEN)
    BITMAP "........"
    BITMAP "........"
    BITMAP "..####.."
    BITMAP ".#.##.#."
    BITMAP "########"
    BITMAP "########"
    BITMAP ".##..##."
    BITMAP "..####.."
' GRAM 28 <- tile 45 Slime 1 (object, fg YELGREEN)
    BITMAP "..####.."
    BITMAP ".#.##.#."
    BITMAP ".#.##.#."
    BITMAP "##.##.##"
    BITMAP "########"
    BITMAP "###..###"
    BITMAP ".##..##."
    BITMAP "..####.."
' GRAM 29 <- tile 46 Bat 0 (object, fg BROWN)
    BITMAP "..#..#.."
    BITMAP "#.####.#"
    BITMAP "#.####.#"
    BITMAP "#..##..#"
    BITMAP "########"
    BITMAP "########"
    BITMAP "#..##..#"
    BITMAP "...##..."
' GRAM 30 <- tile 47 Bat 1 (object, fg BROWN)
    BITMAP "..#..#.."
    BITMAP "..####.."
    BITMAP "..####.."
    BITMAP "#..##..#"
    BITMAP "#..##..#"
    BITMAP "########"
    BITMAP "########"
    BITMAP "#..##..#"
' GRAM 31 <- tile 48 Gorvak (object, fg DARKGREEN)
    BITMAP ".######."
    BITMAP "########"
    BITMAP "########"
    BITMAP ".######."
    BITMAP "...##..."
    BITMAP "########"
    BITMAP ".######."
    BITMAP "###..###"
gfx_b32:
' GRAM 32 <- tile 49 Deep Pump (object, fg BROWN)
    BITMAP "...##..."
    BITMAP "...##..."
    BITMAP "########"
    BITMAP "########"
    BITMAP "########"
    BITMAP ".######."
    BITMAP ".######."
    BITMAP ".######."
' GRAM 33 <- tile 50 Pump Controls (object, fg CYAN)
    BITMAP "........"
    BITMAP ".##....."
    BITMAP ".##....."
    BITMAP ".##.####"
    BITMAP ".##.####"
    BITMAP ".##.####"
    BITMAP ".##.####"
    BITMAP "########"
' GRAM 34 <- tile 51 Wilhelm Working (object, fg BROWN)
    BITMAP ".####..."
    BITMAP ".####..."
    BITMAP "..##...."
    BITMAP "..######"
    BITMAP "..###.##"
    BITMAP "..##...."
    BITMAP ".####..."
    BITMAP ".##.##.."
' GRAM 35 <- player front
    BITMAP "..####.."
    BITMAP ".######."
    BITMAP "..####.."
    BITMAP "..####.."
    BITMAP "########"
    BITMAP "..####.."
    BITMAP ".##..##."
    BITMAP ".##..##."
' GRAM 36 <- player right
    BITMAP "...##..."
    BITMAP "..####.."
    BITMAP "...##..."
    BITMAP ".######."
    BITMAP "...##..."
    BITMAP "..###..."
    BITMAP "..####.."
    BITMAP "....##.."
' GRAM 37 <- player left
    BITMAP "...##..."
    BITMAP "..####.."
    BITMAP "...##..."
    BITMAP ".######."
    BITMAP "...##..."
    BITMAP "...###.."
    BITMAP "..####.."
    BITMAP "..##...."
' GRAM 38 <- item potion
    BITMAP "..####.."
    BITMAP "..####.."
    BITMAP ".######."
    BITMAP "########"
    BITMAP "########"
    BITMAP "########"
    BITMAP "########"
    BITMAP ".######."
' GRAM 39 <- HUD heart
    BITMAP ".##..##."
    BITMAP "########"
    BITMAP "########"
    BITMAP "########"
    BITMAP ".######."
    BITMAP "..####.."
    BITMAP "...##..."
    BITMAP "........"

' tile_word: BACKTAB word (GRAM card + fg color, color-stack mode) per
' logical tile id 0-51. Unused/legacy ids render as blank (word 0).
tile_word:
    DATA $0804,$0000,$080C,$1816,$081C,$1823,$082E,$0834	' ids 0-7
    DATA $183B,$1846,$184B,$1851,$085B,$0863,$1868,$1870	' ids 8-15
    DATA $087B,$1880,$0000,$0000,$0000,$0000,$0000,$0000	' ids 16-23
    DATA $0000,$0000,$0000,$0000,$0000,$0000,$0000,$0000	' ids 24-31
    DATA $0000,$0000,$088E,$1893,$089C,$18A3,$08AC,$08B6	' ids 32-39
    DATA $18BB,$18C3,$08CC,$08D2,$18DE,$18E6,$18EB,$18F3	' ids 40-47
    DATA $08FC,$1903,$1909,$1913	' ids 48-51

' ply_word/rem_word: facing 0-7 -> player BACKTAB word (local white,
' remote orange; same GRAM cards, recolored via the word).
ply_word:
    DATA $091F,$091F,$092F,$0927,$092F,$0927,$092F,$0927
rem_word:
    DATA $191A,$191A,$192A,$1922,$192A,$1922,$192A,$1922

' kind_tile: WORLD_STATE entity species 1-8 -> tile id for its card
' (index 0 unused; bat/slime renderers add the FRAME anim bit).
kind_tile:
    DATA 0,8,9,46,44,36,48,41,51

' item_word: ITEM_DROPS item_id 0-7 -> BACKTAB word.
' 1 gold, 2 sticks, 3 herb, 4 potion, 5 warden key, 6 oil sample, 7 rust sample.
item_word:
    DATA $0000,$088E,$1893,$1816,$0934,$08B6,$1932,$1930

' hud_word: HUD glyph words (index 0 = heart). A DATA table rather than a
' CONST so files compiled before this one can reference it.
hud_word:
    DATA $093A

