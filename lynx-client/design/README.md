# Design mockups

Lynx-resolution (160×102) mockups rendered from the *real* FujiRealm A8 art
(`atari8-client/generated/fujirealm_art.inc` + `maps/overworld.csv`), shown at 4×.

- `mockup_A_faithful_16.png` — faithful 5-color port, 16px tiles.
- `mockup_B_enhanced_16_chosen.png` — **chosen (Option B)**: 16-color per-tile
  palettes, 10×5 viewport, HUD stats + server-message line.
- `mockup_C_wide_8.png` — 8px tiles, 20×11 wide view (rejected: detail loss).

Regenerate: `python3 design/render_mockups.py` (writes PNGs to a scratch dir;
edit the OUT path at the top). Requires Pillow.
