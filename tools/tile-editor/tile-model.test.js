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
