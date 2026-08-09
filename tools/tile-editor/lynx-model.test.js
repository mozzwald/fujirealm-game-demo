const test = require('node:test');
const assert = require('node:assert');
const Lynx = require('./lynx-model.js');

function rows(fill = '0') { return Array.from({ length: 8 }, () => fill.repeat(8)); }

function makeTileset() {
    return {
        version: 1,
        projectType: 'fujirealm-lynx-tiles',
        tileWidth: 8,
        tileHeight: 8,
        palette: Array.from({ length: 16 }, (_, i) => `#${i.toString(16).repeat(6)}`),
        tiles: Array.from({ length: Lynx.TILE_COUNT }, (_, index) => ({ index, name: `Tile ${index}`, rows: rows() })),
        players: Array.from({ length: Lynx.PLAYER_COUNT }, (_, index) => ({ index, rows: rows() })),
        entities: [{ name: 'beaver', rows: rows() }],
    };
}

test('accepts a well-formed tileset', () => {
    assert.doesNotThrow(() => Lynx.validateTileset(makeTileset()));
});

test('rejects the wrong project type, size and palette', () => {
    const wrongType = makeTileset(); wrongType.projectType = 'fujirealm-tiles';
    assert.throws(() => Lynx.validateTileset(wrongType), /projectType/);

    const wrongSize = makeTileset(); wrongSize.tileWidth = 16;
    assert.throws(() => Lynx.validateTileset(wrongSize), /8x8/);

    const shortPalette = makeTileset(); shortPalette.palette.pop();
    assert.throws(() => Lynx.validateTileset(shortPalette), /16 colours/);

    const badColour = makeTileset(); badColour.palette[3] = 'red';
    assert.throws(() => Lynx.validateTileset(badColour), /#RRGGBB/);
});

test('rejects malformed pixel rows', () => {
    const shortRows = makeTileset(); shortRows.tiles[0].rows = rows().slice(1);
    assert.throws(() => Lynx.validateTileset(shortRows), /8 rows/);

    const shortRow = makeTileset(); shortRow.tiles[0].rows[2] = '123';
    assert.throws(() => Lynx.validateTileset(shortRow), /8 hex digits/);

    const notHex = makeTileset(); notHex.tiles[0].rows[2] = '1234567Z';
    assert.throws(() => Lynx.validateTileset(notHex), /non-hex/);
});

test('rejects duplicate targets', () => {
    const dupTile = makeTileset(); dupTile.tiles[1].index = 0;
    assert.throws(() => Lynx.validateTileset(dupTile), /Duplicate tile index/);

    const dupEntity = makeTileset();
    dupEntity.entities.push({ name: 'beaver', rows: rows() });
    assert.throws(() => Lynx.validateTileset(dupEntity), /Duplicate entity/);
});

test('enumerates tiles, player frames and entities as one list', () => {
    const tileset = makeTileset();
    const list = Lynx.entries(tileset);
    assert.strictEqual(list.length, Lynx.TILE_COUNT + Lynx.PLAYER_COUNT + 1);
    assert.strictEqual(list[0].key, 'tile:0');
    assert.strictEqual(list[Lynx.TILE_COUNT].key, 'player:0');
    assert.strictEqual(list[Lynx.TILE_COUNT + Lynx.PLAYER_COUNT].key, 'entity:beaver');
    assert.strictEqual(Lynx.findEntry(tileset, 'player:3').entry.index, 3);
    assert.strictEqual(Lynx.findEntry(tileset, 'nope:1'), null);
});

test('reads and writes pixels, reporting whether anything changed', () => {
    const entry = { rows: rows() };
    assert.strictEqual(Lynx.getPixel(entry, 0, 0), 0);
    assert.strictEqual(Lynx.setPixel(entry, 3, 2, 15), true);
    assert.strictEqual(Lynx.getPixel(entry, 3, 2), 15);
    assert.strictEqual(entry.rows[2], '000F0000');
    // Painting the same pen again is a no-op, so the caller can skip an undo
    // snapshot and a redraw while dragging across one cell.
    assert.strictEqual(Lynx.setPixel(entry, 3, 2, 15), false);
    assert.strictEqual(Lynx.getPixel(entry, 8, 0), -1);
    assert.strictEqual(Lynx.setPixel(entry, 0, 9, 1), false);
    assert.throws(() => Lynx.setPixel(entry, 0, 0, 16), /0-15/);
});

test('transforms shift, mirror and clear', () => {
    const entry = { rows: rows() };
    Lynx.setPixel(entry, 0, 0, 5);
    Lynx.transform(entry, 'right');
    assert.strictEqual(Lynx.getPixel(entry, 1, 0), 5);
    Lynx.transform(entry, 'left');
    assert.strictEqual(Lynx.getPixel(entry, 0, 0), 5);
    Lynx.transform(entry, 'down');
    assert.strictEqual(Lynx.getPixel(entry, 0, 1), 5);
    Lynx.transform(entry, 'mirror-h');
    assert.strictEqual(Lynx.getPixel(entry, 7, 1), 5);
    Lynx.transform(entry, 'mirror-v');
    assert.strictEqual(Lynx.getPixel(entry, 7, 6), 5);
    Lynx.transform(entry, 'clear');
    assert.strictEqual(Lynx.getPixel(entry, 7, 6), 0);
    assert.throws(() => Lynx.transform(entry, 'sideways'), /Unknown transform/);
});

test('undo state round-trips every entry', () => {
    const tileset = makeTileset();
    const state = Lynx.cloneState(tileset);
    Lynx.setPixel(tileset.tiles[5], 1, 1, 9);
    Lynx.setPixel(tileset.entities[0], 2, 2, 7);
    Lynx.restoreState(tileset, state);
    assert.strictEqual(Lynx.getPixel(tileset.tiles[5], 1, 1), 0);
    assert.strictEqual(Lynx.getPixel(tileset.entities[0], 2, 2), 0);
});

test('encodes the sprite bytes the game expects', () => {
    const entry = { rows: rows() };
    Lynx.setPixel(entry, 0, 0, 2);
    Lynx.setPixel(entry, 1, 0, 3);
    const bytes = Lynx.spriteBytes(entry);
    // 8 scanlines of (count + 4 pixel bytes + pad), then a terminator.
    assert.strictEqual(bytes.length, 8 * 6 + 1);
    assert.strictEqual(bytes[0], 6);
    // Leftmost pixel in the high nibble.
    assert.strictEqual(bytes[1], 0x23);
    assert.strictEqual(bytes[5], 0);
    assert.strictEqual(bytes[bytes.length - 1], 0);
});
