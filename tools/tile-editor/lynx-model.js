(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    root.FujiRealmLynx = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';

    // The Lynx tileset is a different animal from the ANTIC 4 project next
    // door. There is no font and no 2x2 character composition: every tile is
    // 8x8 pixels of direct CLUT indices, because Suzy draws sprites rather
    // than character cells. Pixels are stored as eight strings of eight hex
    // digits, which keeps the JSON readable and gives useful git diffs.
    const PROJECT_VERSION = 1;
    const PROJECT_TYPE = 'fujirealm-lynx-tiles';
    const TILE_W = 8;
    const TILE_H = 8;
    const PALETTE_SIZE = 16;
    const TILE_COUNT = 52;
    const PLAYER_COUNT = 12;
    // Pen 0 is the transparent pen for entity sprites, so nothing opaque may
    // be assigned to it except true black.
    const TRANSPARENT_PEN = 0;

    const HEX = '0123456789ABCDEF';

    function fail(message) { throw new Error(message); }

    function validateRows(rows, label) {
        if (!Array.isArray(rows) || rows.length !== TILE_H) fail(`${label} must have ${TILE_H} rows`);
        rows.forEach((row, y) => {
            if (typeof row !== 'string' || row.length !== TILE_W) fail(`${label} row ${y} must be ${TILE_W} hex digits`);
            for (const ch of row) if (HEX.indexOf(ch.toUpperCase()) < 0) fail(`${label} row ${y} contains non-hex "${ch}"`);
        });
    }

    function validateTileset(tileset) {
        if (!tileset || typeof tileset !== 'object' || Array.isArray(tileset)) fail('Tileset root must be an object');
        if (tileset.projectType !== PROJECT_TYPE) fail(`Tileset projectType must be ${PROJECT_TYPE}`);
        if (tileset.version !== PROJECT_VERSION) fail(`Tileset version must be ${PROJECT_VERSION}`);
        if (tileset.tileWidth !== TILE_W || tileset.tileHeight !== TILE_H) fail('Only 8x8 tiles are supported');
        if (!Array.isArray(tileset.palette) || tileset.palette.length !== PALETTE_SIZE) fail(`palette must hold ${PALETTE_SIZE} colours`);
        tileset.palette.forEach((value, index) => {
            if (typeof value !== 'string' || !/^#[0-9a-fA-F]{6}$/.test(value)) fail(`palette[${index}] must be #RRGGBB`);
        });

        if (!Array.isArray(tileset.tiles) || tileset.tiles.length !== TILE_COUNT) fail(`Expected ${TILE_COUNT} tiles`);
        const tileIndices = new Set();
        tileset.tiles.forEach(tile => {
            if (!Number.isInteger(tile.index) || tile.index < 0 || tile.index >= TILE_COUNT) fail(`Tile has an invalid index: ${tile.index}`);
            if (tileIndices.has(tile.index)) fail(`Duplicate tile index ${tile.index}`);
            tileIndices.add(tile.index);
            validateRows(tile.rows, `tile ${tile.index}`);
        });

        if (!Array.isArray(tileset.players) || tileset.players.length !== PLAYER_COUNT) fail(`Expected ${PLAYER_COUNT} player frames`);
        const playerIndices = new Set();
        tileset.players.forEach(frame => {
            if (!Number.isInteger(frame.index) || frame.index < 0 || frame.index >= PLAYER_COUNT) fail(`Player frame has an invalid index: ${frame.index}`);
            if (playerIndices.has(frame.index)) fail(`Duplicate player frame ${frame.index}`);
            playerIndices.add(frame.index);
            validateRows(frame.rows, `player ${frame.index}`);
        });

        if (!Array.isArray(tileset.entities) || !tileset.entities.length) fail('entities must be a non-empty array');
        const names = new Set();
        tileset.entities.forEach(entity => {
            if (typeof entity.name !== 'string' || !entity.name) fail('Every entity needs a name');
            if (names.has(entity.name)) fail(`Duplicate entity ${entity.name}`);
            names.add(entity.name);
            validateRows(entity.rows, `entity ${entity.name}`);
        });
        return tileset;
    }

    // A single flat list so the library, selection and undo can treat tiles,
    // player frames and entity sprites identically.
    function entries(tileset) {
        const list = [];
        tileset.tiles.slice().sort((a, b) => a.index - b.index).forEach(tile => {
            // used defaults true for files predating the flag; a tile is
            // unused only when explicitly marked so (Atari player/HUD slots
            // the Lynx never renders).
            const used = tile.used !== false;
            list.push({ key: `tile:${tile.index}`, kind: 'tile', label: tile.name || `Tile ${tile.index}`, detail: `tile ${tile.index}`, used, entry: tile });
        });
        tileset.players.slice().sort((a, b) => a.index - b.index).forEach(frame => {
            list.push({ key: `player:${frame.index}`, kind: 'player', label: `Player frame ${frame.index}`, detail: `player ${frame.index}`, used: true, entry: frame });
        });
        tileset.entities.forEach(entity => {
            list.push({ key: `entity:${entity.name}`, kind: 'entity', label: entity.name.replace(/_/g, ' '), detail: `entity ${entity.name}`, used: true, entry: entity });
        });
        return list;
    }

    function findEntry(tileset, key) {
        return entries(tileset).find(item => item.key === key) || null;
    }

    function getPixel(entry, x, y) {
        if (x < 0 || x >= TILE_W || y < 0 || y >= TILE_H) return -1;
        return parseInt(entry.rows[y][x], 16);
    }

    function setPixel(entry, x, y, value) {
        if (x < 0 || x >= TILE_W || y < 0 || y >= TILE_H) return false;
        if (!Number.isInteger(value) || value < 0 || value >= PALETTE_SIZE) fail('Pen must be 0-15');
        const row = entry.rows[y];
        if (row[x].toUpperCase() === HEX[value]) return false;
        entry.rows[y] = row.slice(0, x) + HEX[value] + row.slice(x + 1);
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
        else if (action === 'clear') next = grid.map(row => row.map(() => HEX[TRANSPARENT_PEN]));
        else fail(`Unknown transform ${action}`);
        entry.rows = next.map(row => row.join(''));
        return entry.rows;
    }

    function cloneState(tileset) {
        return entries(tileset).map(item => ({ key: item.key, rows: item.entry.rows.slice() }));
    }

    function restoreState(tileset, state) {
        const byKey = new Map(entries(tileset).map(item => [item.key, item.entry]));
        state.forEach(saved => {
            const entry = byKey.get(saved.key);
            if (entry) entry.rows = saved.rows.slice();
        });
    }

    // Suzy stores two pixels per byte with the leftmost in the high nibble,
    // and each scanline is a count byte, the pixel bytes, then a pad byte
    // that Suzy requires after byte-aligned literal data. Mirrors
    // pack_sprite() in the game's import_lynx_art.py; kept here so the
    // editor can report the exact byte cost of what is being drawn.
    function spriteBytes(entry) {
        const out = [];
        entry.rows.forEach(row => {
            out.push(TILE_W / 2 + 2);
            for (let x = 0; x < TILE_W; x += 2) {
                out.push((parseInt(row[x], 16) << 4) | parseInt(row[x + 1], 16));
            }
            out.push(0);
        });
        out.push(0);
        return out;
    }

    return {
        PROJECT_VERSION, PROJECT_TYPE, TILE_W, TILE_H, PALETTE_SIZE,
        TILE_COUNT, PLAYER_COUNT, TRANSPARENT_PEN,
        validateTileset, entries, findEntry, getPixel, setPixel, transform,
        cloneState, restoreState, spriteBytes,
    };
});
