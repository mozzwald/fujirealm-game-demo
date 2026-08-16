const test = require('node:test');
const assert = require('node:assert/strict');
const model = require('./tile-model.js');

function project() {
    const tileDefinitions = [];
    for (let index = 0; index < 51; index++) tileDefinitions.push({ id: `logical-${index}`, name: `Logical ${index}`, category: 'Terrain', targetType: 'logicalTile', targetIndex: index, characters: [1, 2, 3, 4], visible: index === 0 });
    for (let index = 0; index < 12; index++) tileDefinitions.push({ id: `sprite-${index}`, name: `Sprite ${index}`, category: 'Player', targetType: 'playerSprite', targetIndex: index, characters: [5, 6, 7, 8], visible: true });
    return { version: 4, projectType: 'fujirealm-tiles', mode: 'antic4', logicalTileCount: 51, fontData: Array(1024).fill(0), tileDefinitions, animations: [{ id: 'walk', name: 'Walk', frameIds: ['sprite-0', 'sprite-1'], intervalMs: 250 }] };
}

test('validates the complete runtime binding set', () => {
    assert.equal(model.validateProject(project()).tileDefinitions.length, 63);
    const missing = project();
    missing.tileDefinitions.pop();
    assert.throws(() => model.validateProject(missing), /Missing playerSprite:11/);
});
test('defaults legacy projects to 40 logical tiles', () => {
    const value = project();
    delete value.logicalTileCount;
    value.tileDefinitions = value.tileDefinitions.filter(definition => definition.targetType !== 'logicalTile' || definition.targetIndex < 40);
    assert.equal(model.validateProject(value).tileDefinitions.length, 52);
});
test('maps the 8x16 logical grid to four characters', () => {
    const definition = project().tileDefinitions[0];
    assert.deepEqual(model.tilePixelAddress(definition, 0, 0), { quadrant: 0, code: 1, character: 1, row: 0, column: 0 });
    assert.equal(model.tilePixelAddress(definition, 7, 0).quadrant, 1);
    assert.equal(model.tilePixelAddress(definition, 0, 15).quadrant, 2);
    assert.equal(model.tilePixelAddress(definition, 7, 15).quadrant, 3);
});
test('paints ANTIC 4 pairs and controls inverse color per quadrant', () => {
    const value = project();
    const definition = value.tileDefinitions[0];
    model.paintTilePixel(definition, value.fontData, 0, 0, 4);
    assert.equal(definition.characters[0], 0x81);
    assert.equal(value.fontData[8], 0xc0);
    assert.equal(model.displayColorIndex(definition, value.fontData, 0, 0), 4);
    model.paintTilePixel(definition, value.fontData, 0, 0, 3);
    assert.equal(definition.characters[0], 1);
    assert.equal(model.displayColorIndex(definition, value.fontData, 0, 0), 3);
});
test('assigns quadrant characters and reports shared users', () => {
    const value = project();
    model.assignCharacter(value.tileDefinitions[0], 2, 0xfe);
    assert.equal(value.tileDefinitions[0].characters[2], 0xfe);
    const users = model.characterUsers(value, 0x7e);
    assert.equal(users.length, 1);
    assert.equal(users[0].quadrantName, 'bl');
});
test('snapshots and restores font and composition', () => {
    const value = project();
    const state = model.cloneState(value);
    value.fontData[0] = 255;
    value.tileDefinitions[0].characters[0] = 99;
    model.restoreState(value, state);
    assert.equal(value.fontData[0], 0);
    assert.equal(value.tileDefinitions[0].characters[0], 1);
});

test('derives PM frames from the character art', () => {
    const value = project();
    // Glyph 5 is the top-left character of every player sprite here.
    value.fontData[5 * 8] = 0b01_10_11_00;
    const sprite = model.derivePmSprite(value, 0);
    assert.equal(sprite.p0.length, model.PM_SPRITE_H);
    // The character art sits below the overhang rows, which stay blank.
    assert.deepEqual(sprite.p0.slice(0, model.PM_OVERHANG), Array(model.PM_OVERHANG).fill(0));
    assert.equal(sprite.p0[model.PM_OVERHANG], 0b1010_0000);
    assert.equal(sprite.p1[model.PM_OVERHANG], 0b0110_0000);
});
test('reads and writes PM pixels across both planes', () => {
    const value = project();
    const sprite = model.ensurePmSprites(value)[0];
    model.setPmPixel(sprite, 3, 10, 3);
    assert.equal(model.pmPixel(sprite, 3, 10), 3);
    assert.equal(sprite.p0[10], 0b0001_0000);
    assert.equal(sprite.p1[10], 0b0001_0000);
    model.setPmPixel(sprite, 3, 10, 2);
    assert.equal(model.pmPixel(sprite, 3, 10), 2);
    assert.equal(sprite.p0[10], 0);
    model.setPmPixel(sprite, 3, 10, 0);
    assert.equal(model.pmPixel(sprite, 3, 10), 0);
    assert.throws(() => model.setPmPixel(sprite, 3, 10, 4), /must be 0-3/);
});
test('treats stored PM art as optional and validates it when present', () => {
    const value = project();
    assert.equal(model.validateProject(value).pmSprites, undefined);
    model.ensurePmSprites(value);
    assert.equal(model.validateProject(value).pmSprites.length, model.PM_SPRITE_COUNT);
    value.pmSprites[1].p0.pop();
    assert.throws(() => model.validateProject(value), /pmSprites\[1\].p0 must contain/);
});
test('undo captures PM edits and unwinds materialization', () => {
    const value = project();
    const before = model.cloneState(value);
    const sprite = model.ensurePmSprites(value)[2];
    model.setPmPixel(sprite, 0, 0, 1);
    const after = model.cloneState(value);
    model.restoreState(value, before);
    assert.equal(value.pmSprites, undefined);
    model.restoreState(value, after);
    assert.equal(model.pmPixel(value.pmSprites[2], 0, 0), 1);
});

test('downsamples the BULLET tile to the missile two pixels', () => {
    const value = project();
    const bullet = model.logicalTileDefinition(value, model.BULLET_TILE_INDEX);
    // Glyph 1 is this tile's top-left character, 3 its bottom-left.
    value.fontData[1 * 8 + 5] = 0b00_00_00_11; // rightmost pixel of the left half
    value.fontData[2 * 8 + 6] = 0b11_00_00_00; // leftmost pixel of the right half
    assert.equal(bullet.characters[0], 1);
    const rows = model.derivePmMissile(value);
    assert.equal(rows.length, model.PM_MISSILE_H);
    assert.equal(rows[5], 2, 'left half lit sets bit 1');
    assert.equal(rows[6], 1, 'right half lit sets bit 0');
    assert.equal(rows[0], 0);
});
test('reads and writes missile pixels', () => {
    const value = project();
    const rows = model.ensurePmMissile(value);
    model.setPmMissilePixel(rows, 0, 3, true);
    assert.equal(model.pmMissilePixel(rows, 0, 3), 1);
    assert.equal(model.pmMissilePixel(rows, 1, 3), 0);
    assert.equal(rows[3], 2);
    model.setPmMissilePixel(rows, 1, 3, true);
    assert.equal(rows[3], 3);
    model.setPmMissilePixel(rows, 0, 3, false);
    assert.equal(rows[3], 1);
});
test('treats stored missile art as optional and validates it', () => {
    const value = project();
    assert.equal(model.validateProject(value).pmMissile, undefined);
    model.ensurePmMissile(value);
    assert.equal(model.validateProject(value).pmMissile.length, model.PM_MISSILE_H);
    value.pmMissile[2] = 4;
    assert.throws(() => model.validateProject(value), /pmMissile\[2\] must be 0-3/);
});
test('undo unwinds missile edits and materialization', () => {
    const value = project();
    const before = model.cloneState(value);
    model.setPmMissilePixel(model.ensurePmMissile(value), 1, 0, true);
    const after = model.cloneState(value);
    model.restoreState(value, before);
    assert.equal(value.pmMissile, undefined);
    model.restoreState(value, after);
    assert.equal(model.pmMissilePixel(value.pmMissile, 1, 0), 1);
});
