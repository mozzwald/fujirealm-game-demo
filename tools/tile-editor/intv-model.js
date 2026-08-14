(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    root.FujiRealmIntv = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    // The Intellivision is the most constrained of the three targets. A GRAM
    // card is 8x8 and 1bpp -- there is no per-pixel colour at all. The screen
    // runs in colour-stack mode with every entry black (MODE 0,0,0,0,0 in
    // fujirealm.bas), so the background is always black and each BACKTAB word
    // carries one STIC foreground colour for the whole cell. Hence a card here
    // is a shape plus a single colour index, and why the three player cards can
    // be reused for remote players just by recolouring the word.
    //
    // This file is the browser twin of intv-client/tools/intv_cards.py; the
    // validation rules and backtabWord() must stay in step with it.
    const PROJECT_VERSION = 1;
    const PROJECT_TYPE = 'fujirealm-intv-cards';
    const CARD_W = 8;
    const CARD_H = 8;
    const CARD_COUNT = 40;
    const GRAM_CAPACITY = 64;
    const PALETTE_SIZE = 16;
    // Colour 0 is black, which is the background: a card painted in it would be
    // invisible, so the editor never offers it as a card colour.
    const BACKGROUND_COLOR = 0;
    const KINDS = ['tile', 'player', 'item', 'hud'];

    const SET = '#';
    const CLEAR = '.';

    function fail(message) { throw new Error(message); }

    function validateRows(rows, label) {
        if (!Array.isArray(rows) || rows.length !== CARD_H) fail(`${label} must have ${CARD_H} rows`);
        rows.forEach((row, y) => {
            if (typeof row !== 'string' || row.length !== CARD_W) fail(`${label} row ${y} must be ${CARD_W} characters`);
            for (const ch of row) if (ch !== SET && ch !== CLEAR) fail(`${label} row ${y} contains "${ch}", expected "${SET}" or "${CLEAR}"`);
        });
    }

    function validateProject(project) {
        if (!project || typeof project !== 'object' || Array.isArray(project)) fail('Project root must be an object');
        if (project.projectType !== PROJECT_TYPE) fail(`projectType must be ${PROJECT_TYPE}`);
        if (project.version !== PROJECT_VERSION) fail(`version must be ${PROJECT_VERSION}`);
        if (project.cardWidth !== CARD_W || project.cardHeight !== CARD_H) fail(`Only ${CARD_W}x${CARD_H} cards are supported`);
        if (!Array.isArray(project.palette) || project.palette.length !== PALETTE_SIZE) fail(`palette must hold ${PALETTE_SIZE} STIC colours`);
        project.palette.forEach((value, index) => {
            if (typeof value !== 'string' || !/^#[0-9a-fA-F]{6}$/.test(value)) fail(`palette[${index}] must be #RRGGBB`);
        });
        if (!Array.isArray(project.cards) || project.cards.length !== CARD_COUNT) fail(`Expected ${CARD_COUNT} cards`);
        if (!project.bindings || typeof project.bindings !== 'object') fail('bindings must be an object');

        project.cards.forEach((card, slot) => {
            const label = `card ${slot}`;
            if (card.index !== slot) fail(`${label}: index must equal its position`);
            if (!KINDS.includes(card.kind)) fail(`${label}: kind must be one of ${KINDS.join(', ')}`);
            if (!Number.isInteger(card.color) || card.color < 0 || card.color >= PALETTE_SIZE) fail(`${label}: color must be a STIC index 0-15`);
            if (card.color === BACKGROUND_COLOR) fail(`${label}: color 0 is the black background, so the card would be invisible`);
            validateRows(card.rows, label);
            if (card.kind === 'tile' && !Number.isInteger(card.tile)) fail(`${label}: a tile card needs a tile id`);
        });
        return project;
    }

    // One flat list so the library, selection and undo can treat every card the
    // same way, whatever it draws. Same shape as the Lynx model's entries().
    function entries(project) {
        return project.cards.map(card => ({
            key: `card:${card.index}`,
            kind: card.kind,
            label: card.name,
            detail: card.kind === 'tile'
                ? `tile ${card.tile} → GRAM ${card.index}`
                : `GRAM ${card.index}`,
            used: true,
            entry: card,
        }));
    }

    function findEntry(project, key) {
        return entries(project).find(item => item.key === key) || null;
    }

    function getPixel(entry, x, y) {
        if (x < 0 || x >= CARD_W || y < 0 || y >= CARD_H) return -1;
        return entry.rows[y][x] === SET ? 1 : 0;
    }

    function setPixel(entry, x, y, value) {
        if (x < 0 || x >= CARD_W || y < 0 || y >= CARD_H) return false;
        const ch = value ? SET : CLEAR;
        const row = entry.rows[y];
        if (row[x] === ch) return false;
        entry.rows[y] = row.slice(0, x) + ch + row.slice(x + 1);
        return true;
    }

    function setColor(entry, index) {
        if (!Number.isInteger(index) || index < 0 || index >= PALETTE_SIZE) fail('Colour must be 0-15');
        if (index === BACKGROUND_COLOR) fail('Colour 0 is the black background; the card would be invisible');
        if (entry.color === index) return false;
        entry.color = index;
        return true;
    }

    function transform(entry, action) {
        const grid = entry.rows.map(row => row.split(''));
        let next;
        if (action === 'left') next = grid.map(row => row.slice(1).concat(row[0]));
        else if (action === 'right') next = grid.map(row => [row[row.length - 1]].concat(row.slice(0, -1)));
        else if (action === 'up') next = grid.slice(1).concat([grid[0]]);
        else if (action === 'down') next = [grid[grid.length - 1]].concat(grid.slice(0, -1));
        else if (action === 'mirror-h') next = grid.map(row => row.slice().reverse());
        else if (action === 'mirror-v') next = grid.slice().reverse();
        else if (action === 'invert') next = grid.map(row => row.map(c => (c === SET ? CLEAR : SET)));
        else if (action === 'clear') next = grid.map(row => row.map(() => CLEAR));
        else fail(`Unknown transform ${action}`);
        entry.rows = next.map(row => row.join(''));
        return entry.rows;
    }

    // Undo carries the colour as well as the pixels: on this target the colour
    // is as much a part of the art as the shape.
    function cloneState(project) {
        return entries(project).map(item => ({
            key: item.key, rows: item.entry.rows.slice(), color: item.entry.color,
        }));
    }

    function restoreState(project, state) {
        const byKey = new Map(entries(project).map(item => [item.key, item.entry]));
        state.forEach(saved => {
            const entry = byKey.get(saved.key);
            if (!entry) return;
            entry.rows = saved.rows.slice();
            entry.color = saved.color;
        });
    }

    // The BACKTAB word the card compiles to: bit 11 selects GRAM, bits 3-10 the
    // card, bits 0-2 the colour's low three bits, bit 12 its high bit (the
    // pastel half). Mirrors word() in intv-client/tools/intv_cards.py.
    function backtabWord(entry) {
        let w = 0x0800 + entry.index * 8 + (entry.color & 7);
        if (entry.color >= 8) w += 0x1000;
        return w;
    }

    function hexWord(value) {
        return '$' + value.toString(16).toUpperCase().padStart(4, '0');
    }

    // --- IntyBASIC BITMAP interchange ---------------------------------------
    // The rows are stored in exactly the notation BITMAP takes, so a card can be
    // pasted straight out of (or into) gfx.bas and any other IntyBASIC source.

    function toBitmapText(entry) {
        return entry.rows.map(row => `    BITMAP "${row}"`).join('\n');
    }

    function fromBitmapText(text) {
        const rows = [];
        String(text).split('\n').forEach(line => {
            const quoted = line.match(/BITMAP\s*"([^"]*)"/i);
            // Accept bare rows too, so pasting 8 lines of ####.... just works.
            const bare = quoted ? null : line.trim().match(/^([#.01]{8})\s*(?:'.*)?$/);
            if (!quoted && !bare) return;
            let row = (quoted ? quoted[1] : bare[1]).trim();
            row = row.replace(/1/g, SET).replace(/0/g, CLEAR);
            if (row.length !== CARD_W) fail(`"${row}" is ${row.length} pixels, expected ${CARD_W}`);
            for (const ch of row) if (ch !== SET && ch !== CLEAR) fail(`"${row}" contains "${ch}"`);
            rows.push(row);
        });
        if (rows.length !== CARD_H) fail(`Found ${rows.length} bitmap rows, expected ${CARD_H}`);
        return rows;
    }

    return {
        PROJECT_VERSION, PROJECT_TYPE, CARD_W, CARD_H, CARD_COUNT, GRAM_CAPACITY,
        PALETTE_SIZE, BACKGROUND_COLOR, KINDS, SET, CLEAR,
        validateProject, entries, findEntry, getPixel, setPixel, setColor, transform,
        cloneState, restoreState, backtabWord, hexWord, toBitmapText, fromBitmapText,
    };
});
