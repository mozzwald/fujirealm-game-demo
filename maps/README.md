# Editable map layout

`overworld.csv`, `cave.csv`, and `pvp_realm.csv` are the full 128x96 tile  
grids for the maps, one cell per tile. Row 0 and column 0 are index labels for  
orientation, not data -- don't edit them.

Edit a cell and set it to one of the codes below (case-sensitive), then  
run from the repo root:

```
python3 tools/import_map_csv.py
```

This regenerates `v6/server/world_layout_data.py`, which is what the  
server actually loads at runtime (restart the server to pick up changes).  
Do not hand-edit `world_layout_data.py` -- it gets overwritten every time  
the import script runs.

If you want to re-export the current layout instead (e.g. to discard CSV  
edits and start over from what's live), run `python3 tools/export_map_csv.py`.

## Legend

### overworld.csv

| Code      | Meaning                                                                                                                               |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| *(blank)* | Grass                                                                                                                                 |
| `T`       | Tree                                                                                                                                  |
| `H`       | Herb                                                                                                                                  |
| `R`       | Road                                                                                                                                  |
| `U`       | Building                                                                                                                              |
| `W`       | Water (blocking obstacle)                                                                                                             |
| `O`       | Initial spawn point -- where a brand-new player first appears; exactly one required                                                  |
| `X`       | Grave / death-respawn point -- exactly one required (separate from `O`)                                                              |
| `C`       | Cave entrance -- exactly one required                                                                                                 |
| `P`       | PvP realm entrance -- exactly one required                                                                                            |
| `DAN`     | Daniel's position -- exactly one required                                                                                             |
| `GRX`     | Grix's position -- exactly one required                                                                                               |
| `NER`     | Nerissa's position                                                                                                                    |
| `WIL`     | Wilhelm's workshop/start position                                                                                                     |
| `LUC`     | Lucian's lookout position                                                                                                             |
| `KEY`     | Warden Key landmark                                                                                                                   |
| `WBD`     | Wilhelm's bridge destination                                                                                                          |
| `F`       | Legacy alias for `DAN` on import only                                                                                                 |
| `N`       | Legacy alias for `GRX` on import only                                                                                                 |
| `=`       | Completed bridge deck cell -- ROAD terrain, masked as WATER per-player until that player repairs the bridge. May repeat (multi-cell). |
| `V`       | Beaver spawn point                                                                                                                    |
| `G`       | Goblin spawn point                                                                                                                    |
| `S`       | Snake spawn point *(provisional -- The Dam Below)*                                                                                    |
| `M`       | Slime spawn point *(provisional -- The Dam Below)*                                                                                    |
| `B`       | Bat spawn point *(provisional -- The Dam Below)*                                                                                      |
| `#`       | Map border -- always regenerated automatically, don't bother editing                                                                  |

### cave.csv

| Code      | Meaning                                                   |
| --------- | --------------------------------------------------------- |
| *(blank)* | Solid rock (cave wall)                                    |
| `.`       | Cave floor                                                |
| `H`       | Herb (restores 1 HP when walked over)                     |
| `C`       | Cave exit (back to the overworld) -- exactly one required |
| `V`       | Beaver spawn point                                        |
| `G`       | Goblin spawn point                                        |
| `B`       | Bat spawn point *(provisional -- The Dam Below)*          |
| `GOR`     | Gorvak's home / boss marker                               |
| `DPC`     | Deep Pump controls                                        |
| `#`       | Map border -- always regenerated automatically            |

### pvp_realm.csv

| Code      | Meaning                                             |
| --------- | --------------------------------------------------- |
| *(blank)* | Grass                                               |
| `T`       | Tree                                                |
| `H`       | Herb (restores 1 HP when walked over)               |
| `R`       | Road                                                |
| `U`       | Building                                            |
| `W`       | Water (blocking obstacle)                           |
| `E`       | Realm entry / respawn point -- exactly one required |
| `P`       | Exit back to the overworld -- exactly one required  |
| `V`       | Beaver spawn point                                  |
| `G`       | Goblin spawn point                                  |
| `#`       | Map border -- always regenerated automatically      |

## The Dam Below story metadata

The bridge marker `=` fully round-trips (importer emits  
`OVERWORLD_BRIDGE_TILES`; the server masks those cells as WATER per-player until  
repair). The `S`/`M`/`B` enemy species codes are live. The story-anchor markers  
above also round-trip through export/import and regenerate  
`v6/server/world_layout_data.py`.

Content that a single cell cannot express lives in `v6/maps/story_layout.json`.  
Current schema:

```json
{
  "wilhelm_escort_path": {
    "map": "overworld",
    "points": [[10, 10], [11, 10]]
  },
  "bridge_defense_region": null,
  "snake_region": null,
  "slime_region": null,
  "gorvak_room_region": null,
  "gorvak_summon_points": {
    "map": "cave",
    "points": []
  }
}
```

Rules:

- `wilhelm_escort_path.map` must stay `"overworld"`.
- If `wilhelm_escort_path.points` is non-empty, it must move one tile at a time.
- If both `WIL` and `WBD` exist in `overworld.csv`, the Wilhelm path must start  
at `WIL` and end at `WBD`.
- Coordinates are `[column,row]`
- Regions are either `null` or `{ "map", "x1", "y1", "x2", "y2" }` with  
inclusive bounds.
- `gorvak_summon_points.map` must stay `"cave"`.

The importer validates this sidecar on every run and emits the resulting  
metadata into `world_layout_data.py` for later story phases.

## Known limitations

- **Tree health state** isn't tracked in the CSV -- every tree imports as  
a fresh, undamaged tree regardless of what state it was in when  
exported. This only matters if you export mid-session; a fresh export  
right after import always shows all trees undamaged anyway.
- **The cave's arrival point** (where you land when walking in from the  
overworld cave entrance) isn't separately editable via the CSV -- it's  
a fixed interior point, distinct from the cave exit (`C`) you *can*  
move. Moving `C` in `cave.csv` only changes where the exit is, not  
where you arrive.
- **The PvP realm's arrival point** is controlled by the `E` marker in  
`pvp_realm.csv`. The player also respawns there after dying in the  
realm. The `P` marker is the exit back to the overworld.
- **Beaver/goblin spawn *order*** isn't preserved across a round-trip  
(the import script assigns them in grid-scan order, not the order they  
happened to be listed in before). This has no gameplay effect, but if  
you ever see a test or tool that assumes a specific beaver is  
`game.beavers[N]` for a fixed `N`, that assumption is fragile against  
re-imports for exactly this reason.
