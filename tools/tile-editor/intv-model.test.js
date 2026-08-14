const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const Intv = require('./intv-model.js');

const PROJECT_PATH = path.join(__dirname, '../../intv-client/art/intv_cards.json');
const USED_TILES = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17,
    34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51];

function rows(fill = '.') { return Array.from({ length: 8 }, () => fill.repeat(8)); }

function makeProject() {
    return {
        projectType: 'fujirealm-intv-cards',
        version: 1,
        cardWidth: 8,
        cardHeight: 8,
        cardCount: Intv.CARD_COUNT,
        palette: Array.from({ length: 16 }, (_, i) => `#${i.toString(16).repeat(6)}`),
        colorNames: Array.from({ length: 16 }, (_, i) => `C${i}`),
        cards: Array.from({ length: Intv.CARD_COUNT }, (_, index) => (
            index < USED_TILES.length
                ? { index, kind: 'tile', name: `Tile ${index}`, tile: USED_TILES[index], seedRule: 'field', color: 7, rows: rows() }
                : { index, kind: 'player', name: `Card ${index}`, color: 7, rows: rows() }
        )),
        bindings: {},
    };
}

test('accepts a well-formed project', () => {
    assert.doesNotThrow(() => Intv.validateProject(makeProject()));
});

test('rejects the wrong project type, version and card size', () => {
    const wrongType = makeProject(); wrongType.projectType = 'fujirealm-lynx-tiles';
    assert.throws(() => Intv.validateProject(wrongType), /projectType/);

    const wrongVersion = makeProject(); wrongVersion.version = 2;
    assert.throws(() => Intv.validateProject(wrongVersion), /version/);

    const wrongSize = makeProject(); wrongSize.cardWidth = 16;
    assert.throws(() => Intv.validateProject(wrongSize), /8x8/);

    const shortDeck = makeProject(); shortDeck.cards.pop();
    assert.throws(() => Intv.validateProject(shortDeck), /40 cards/);
});

test('rejects malformed pixel rows', () => {
    const shortRows = makeProject(); shortRows.cards[0].rows = rows().slice(1);
    assert.throws(() => Intv.validateProject(shortRows), /8 rows/);

    const shortRow = makeProject(); shortRow.cards[0].rows[2] = '###';
    assert.throws(() => Intv.validateProject(shortRow), /8 characters/);

    // Hex digits are the Lynx notation; on a 1bpp target they are a mistake.
    const hexRow = makeProject(); hexRow.cards[0].rows[2] = '01234567';
    assert.throws(() => Intv.validateProject(hexRow), /expected/);
});

test('rejects a card colour of black, which would be invisible', () => {
    const black = makeProject(); black.cards[3].color = 0;
    assert.throws(() => Intv.validateProject(black), /invisible/);

    const outOfRange = makeProject(); outOfRange.cards[3].color = 16;
    assert.throws(() => Intv.validateProject(outOfRange), /0-15/);
});

test('rejects a card whose index does not match its position', () => {
    const shuffled = makeProject(); shuffled.cards[5].index = 6;
    assert.throws(() => Intv.validateProject(shuffled), /index/);
});

test('entries expose every card with its binding', () => {
    const project = makeProject();
    const list = Intv.entries(project);
    assert.strictEqual(list.length, Intv.CARD_COUNT);
    assert.strictEqual(list[0].key, 'card:0');
    assert.match(list[0].detail, /tile 0 → GRAM 0/);
    assert.strictEqual(Intv.findEntry(project, 'card:7').entry.index, 7);
    assert.strictEqual(Intv.findEntry(project, 'card:999'), null);
});

test('pixels read and write as 0/1', () => {
    const card = makeProject().cards[0];
    assert.strictEqual(Intv.getPixel(card, 0, 0), 0);
    assert.strictEqual(Intv.setPixel(card, 3, 2, 1), true);
    assert.strictEqual(Intv.getPixel(card, 3, 2), 1);
    assert.strictEqual(Intv.setPixel(card, 3, 2, 1), false, 'no-op writes report no change');
    assert.strictEqual(card.rows[2], '...#....');
    assert.strictEqual(Intv.getPixel(card, -1, 0), -1);
    assert.strictEqual(Intv.setPixel(card, 8, 0, 1), false);
});

test('setColor refuses the background colour', () => {
    const card = makeProject().cards[0];
    assert.strictEqual(Intv.setColor(card, 9), true);
    assert.strictEqual(card.color, 9);
    assert.strictEqual(Intv.setColor(card, 9), false);
    assert.throws(() => Intv.setColor(card, 0), /background/);
    assert.throws(() => Intv.setColor(card, 16), /0-15/);
});

test('undo state round-trips both pixels and colour', () => {
    const project = makeProject();
    const saved = Intv.cloneState(project);
    Intv.setPixel(project.cards[4], 1, 1, 1);
    Intv.setColor(project.cards[4], 12);
    assert.strictEqual(Intv.getPixel(project.cards[4], 1, 1), 1);
    Intv.restoreState(project, saved);
    assert.strictEqual(Intv.getPixel(project.cards[4], 1, 1), 0);
    assert.strictEqual(project.cards[4].color, 7);
});

test('transforms shift, mirror, invert and clear', () => {
    const project = makeProject();
    const card = project.cards[0];
    Intv.setPixel(card, 0, 0, 1);
    Intv.transform(card, 'right');
    assert.strictEqual(card.rows[0], '.#......');
    Intv.transform(card, 'left');
    assert.strictEqual(card.rows[0], '#.......');
    Intv.transform(card, 'mirror-h');
    assert.strictEqual(card.rows[0], '.......#');
    Intv.transform(card, 'down');
    assert.strictEqual(card.rows[1], '.......#');
    Intv.transform(card, 'invert');
    assert.strictEqual(card.rows[1], '#######.');
    Intv.transform(card, 'clear');
    assert.deepStrictEqual(card.rows, rows());
    assert.throws(() => Intv.transform(card, 'rotate'), /Unknown transform/);
});

test('backtabWord matches the words in the shipped gfx.bas', () => {
    // From intv-client/gfx.bas tile_word: id 0 (Grass) is GRAM 0 / DARKGREEN(4)
    // and id 8 (Beaver) is GRAM 7 / a pastel colour, which exercises bit 12.
    assert.strictEqual(Intv.backtabWord({ index: 0, color: 4 }), 0x0804);
    assert.strictEqual(Intv.backtabWord({ index: 7, color: 11 }), 0x183B);
    assert.strictEqual(Intv.backtabWord({ index: 39, color: 2 }), 0x093A);
    assert.strictEqual(Intv.hexWord(0x0804), '$0804');
});

test('BITMAP text round-trips', () => {
    const card = makeProject().cards[0];
    Intv.setPixel(card, 0, 0, 1);
    Intv.setPixel(card, 7, 7, 1);
    const text = Intv.toBitmapText(card);
    assert.match(text, /^ {4}BITMAP "#\.{7}"/);
    assert.deepStrictEqual(Intv.fromBitmapText(text), card.rows);
});

test('BITMAP import accepts bare rows, 1/0 notation and trailing comments', () => {
    const bare = ['#.......', '........', '........', '........',
                  '........', '........', '........', '.......#'].join('\n');
    assert.strictEqual(Intv.fromBitmapText(bare)[0], '#.......');

    const binary = Array.from({ length: 8 }, (_, i) => (i ? '00000000' : '10000000')).join('\n');
    assert.strictEqual(Intv.fromBitmapText(binary)[0], '#.......');

    const commented = Array.from({ length: 8 },
        () => '    BITMAP "########"\t\' a comment').join('\n');
    assert.strictEqual(Intv.fromBitmapText(commented)[3], '########');
});

test('BITMAP import rejects the wrong number of rows and bad widths', () => {
    assert.throws(() => Intv.fromBitmapText('    BITMAP "########"'), /Found 1 bitmap rows/);
    assert.throws(() => Intv.fromBitmapText(
        Array.from({ length: 8 }, () => '    BITMAP "###"').join('\n')), /3 pixels/);
});

// The checked-in art is the contract between this editor and the Python
// generator: if one side drifts, this is where it shows up first.
test('the shipped art/intv_cards.json validates', { skip: !fs.existsSync(PROJECT_PATH) }, () => {
    const project = JSON.parse(fs.readFileSync(PROJECT_PATH, 'utf8'));
    assert.doesNotThrow(() => Intv.validateProject(project));
    assert.strictEqual(project.cards.length, Intv.CARD_COUNT);
    const grass = project.cards.find(card => card.kind === 'tile' && card.tile === 0);
    assert.strictEqual(Intv.backtabWord(grass), 0x0804, 'Grass must still compile to $0804');
});
