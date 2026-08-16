(function (root, factory) {
    const api = factory();
    if (typeof module === 'object' && module.exports) module.exports = api;
    root.FujiRealmTiles = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    'use strict';
    const PROJECT_VERSION = 4;
    const PROJECT_TYPE = 'fujirealm-tiles';
    const FONT_BYTES = 1024;
    const LOGICAL_TILE_COUNT = 40;
    const PLAYER_SPRITE_COUNT = 12;
    const QUADRANTS = ['tl', 'tr', 'bl', 'br'];
    // Player/Missile art for the six local-player frames. A normal-width GTIA
    // player is 8 pixels wide -- the same width as the 2x2 character sprite --
    // so a PM frame is the character art plus extra rows that overhang above
    // the tile. Two bitplanes: value 1 lights P0, 2 lights P1, 3 lights both,
    // which GTIA shows as COLPM0 OR COLPM1 under multicolor player mode.
    const PM_SPRITE_COUNT = 6;
    const PM_SPRITE_H = 24;
    const PM_TILE_ROWS = 16;
    const PM_OVERHANG = PM_SPRITE_H - PM_TILE_ROWS;
    // Bullets ride the four GTIA missiles, which are two bits wide and one
    // colour (COLPF3). Eight rows of two pixels is the entire budget. Bit 1
    // of a row is the left pixel, bit 0 the right, matching the order GTIA
    // shifts them out.
    const PM_MISSILE_H = 8;
    const BULLET_TILE_INDEX = 6;

    function assertByte(value, label) {
        if (!Number.isInteger(value) || value < 0 || value > 255) throw new Error(`${label} must be a byte`);
    }

    function validateProject(project) {
        if (!project || typeof project !== 'object' || Array.isArray(project)) throw new Error('Project root must be an object');
        if (project.version !== PROJECT_VERSION) throw new Error(`Project version must be ${PROJECT_VERSION}`);
        if (project.projectType !== PROJECT_TYPE) throw new Error(`Project type must be ${PROJECT_TYPE}`);
        if (project.mode !== 'antic4') throw new Error('FujiRealm projects must use ANTIC 4');
        const logicalTileCount = project.logicalTileCount === undefined ? LOGICAL_TILE_COUNT : project.logicalTileCount;
        if (!Number.isInteger(logicalTileCount) || logicalTileCount < 1 || logicalTileCount > 256) throw new Error('logicalTileCount must be an integer from 1 to 256');
        if (!Array.isArray(project.fontData) || project.fontData.length !== FONT_BYTES) throw new Error('fontData must contain 1024 bytes');
        project.fontData.forEach((value, index) => assertByte(value, `fontData[${index}]`));
        if (!Array.isArray(project.tileDefinitions)) throw new Error('tileDefinitions must be an array');
        const ids = new Set();
        const targets = new Set();
        for (const definition of project.tileDefinitions) {
            if (!definition || typeof definition !== 'object') throw new Error('Every tile definition must be an object');
            if (!definition.id || ids.has(definition.id)) throw new Error(`Duplicate or missing tile id: ${definition.id || ''}`);
            ids.add(definition.id);
            if (typeof definition.name !== 'string' || !definition.name) throw new Error(`Tile ${definition.id} must have a name`);
            if (!['logicalTile', 'playerSprite'].includes(definition.targetType)) throw new Error(`Tile ${definition.id} has an invalid targetType`);
            const limit = definition.targetType === 'logicalTile' ? logicalTileCount : PLAYER_SPRITE_COUNT;
            if (!Number.isInteger(definition.targetIndex) || definition.targetIndex < 0 || definition.targetIndex >= limit) throw new Error(`Tile ${definition.id} has an invalid targetIndex`);
            const target = `${definition.targetType}:${definition.targetIndex}`;
            if (targets.has(target)) throw new Error(`Duplicate runtime target: ${target}`);
            targets.add(target);
            if (!Array.isArray(definition.characters) || definition.characters.length !== 4) throw new Error(`Tile ${definition.id} must contain four character codes`);
            definition.characters.forEach((value, index) => assertByte(value, `${definition.id}.characters[${index}]`));
            if (typeof definition.visible !== 'boolean') throw new Error(`Tile ${definition.id} must declare visible`);
        }
        for (let index = 0; index < logicalTileCount; index++) if (!targets.has(`logicalTile:${index}`)) throw new Error(`Missing logicalTile:${index}`);
        for (let index = 0; index < PLAYER_SPRITE_COUNT; index++) if (!targets.has(`playerSprite:${index}`)) throw new Error(`Missing playerSprite:${index}`);
        if (!Array.isArray(project.animations)) throw new Error('animations must be an array');
        const animationIds = new Set();
        for (const animation of project.animations) {
            if (!animation.id || animationIds.has(animation.id)) throw new Error(`Duplicate or missing animation id: ${animation.id || ''}`);
            animationIds.add(animation.id);
            if (!Array.isArray(animation.frameIds) || animation.frameIds.length < 2) throw new Error(`Animation ${animation.id} needs at least two frames`);
            animation.frameIds.forEach(frameId => { if (!ids.has(frameId)) throw new Error(`Animation ${animation.id} references unknown frame ${frameId}`); });
            if (!Number.isInteger(animation.intervalMs) || animation.intervalMs < 50) throw new Error(`Animation ${animation.id} has an invalid interval`);
        }
        if (project.pmSprites !== undefined) validatePmSprites(project.pmSprites);
        if (project.pmMissile !== undefined) validatePmMissile(project.pmMissile);
        return project;
    }

    function baseCharacter(code) { return code & 0x7f; }
    function isInverse(code) { return (code & 0x80) !== 0; }
    function quadrantIndex(logicalX, logicalY) {
        if (!Number.isInteger(logicalX) || !Number.isInteger(logicalY) || logicalX < 0 || logicalX > 7 || logicalY < 0 || logicalY > 15) return -1;
        return (logicalY >= 8 ? 2 : 0) + (logicalX >= 4 ? 1 : 0);
    }
    function tilePixelAddress(definition, logicalX, logicalY) {
        const quadrant = quadrantIndex(logicalX, logicalY);
        if (quadrant < 0) return null;
        const code = definition.characters[quadrant];
        return { quadrant, code, character: baseCharacter(code), row: logicalY % 8, column: logicalX % 4 };
    }
    function readPair(fontData, character, row, column) { return (fontData[character * 8 + row] >> (6 - column * 2)) & 3; }
    function writePair(fontData, character, row, column, pair) {
        const offset = character * 8 + row;
        const shift = 6 - column * 2;
        fontData[offset] = (fontData[offset] & ~(3 << shift)) | ((pair & 3) << shift);
    }
    function displayColorIndex(definition, fontData, logicalX, logicalY) {
        const address = tilePixelAddress(definition, logicalX, logicalY);
        if (!address) return 0;
        const pair = readPair(fontData, address.character, address.row, address.column);
        return pair === 3 && isInverse(address.code) ? 4 : pair;
    }
    function paintTilePixel(definition, fontData, logicalX, logicalY, colorIndex) {
        const address = tilePixelAddress(definition, logicalX, logicalY);
        if (!address) return -1;
        if (!Number.isInteger(colorIndex) || colorIndex < 0 || colorIndex > 4) throw new Error('Color index must be 0-4');
        const pair = colorIndex === 4 ? 3 : colorIndex;
        if (colorIndex === 4) definition.characters[address.quadrant] |= 0x80;
        if (colorIndex === 3) definition.characters[address.quadrant] &= 0x7f;
        writePair(fontData, address.character, address.row, address.column, pair);
        return address.quadrant;
    }
    function assignCharacter(definition, quadrant, code) {
        if (!Number.isInteger(quadrant) || quadrant < 0 || quadrant > 3) throw new Error('Quadrant must be 0-3');
        assertByte(code, 'Character code');
        definition.characters[quadrant] = code;
    }
    function setInverse(definition, quadrant, inverse) {
        if (!Number.isInteger(quadrant) || quadrant < 0 || quadrant > 3) throw new Error('Quadrant must be 0-3');
        definition.characters[quadrant] = inverse ? definition.characters[quadrant] | 0x80 : definition.characters[quadrant] & 0x7f;
    }
    function characterUsers(project, character) {
        const base = character & 0x7f;
        const users = [];
        for (const definition of project.tileDefinitions) definition.characters.forEach((code, quadrant) => {
            if (baseCharacter(code) === base) users.push({ definition, quadrant, quadrantName: QUADRANTS[quadrant] });
        });
        return users;
    }
    function animationForTile(project, tileId) { return project.animations.find(animation => animation.frameIds.includes(tileId)) || null; }

    function playerSpriteDefinition(project, index) {
        return project.tileDefinitions.find(item => item.targetType === 'playerSprite' && item.targetIndex === index) || null;
    }

    // Read a PM frame straight out of the character art. Used to seed a
    // project that has never had PM frames edited, and by the "Reseed" action.
    function derivePmSprite(project, index) {
        const planes = { p0: new Array(PM_SPRITE_H).fill(0), p1: new Array(PM_SPRITE_H).fill(0) };
        const definition = playerSpriteDefinition(project, index);
        if (!definition) return planes;
        for (let logicalY = 0; logicalY < PM_TILE_ROWS; logicalY++) {
            for (let logicalX = 0; logicalX < 8; logicalX++) {
                const address = tilePixelAddress(definition, logicalX, logicalY);
                if (!address) continue;
                const pair = readPair(project.fontData, address.character, address.row, address.column);
                const bit = 1 << (7 - logicalX);
                // The character art sits at the bottom so it still fills its
                // tile; the spare rows overhang above it.
                const row = PM_OVERHANG + logicalY;
                if (pair & 1) planes.p0[row] |= bit;
                if (pair & 2) planes.p1[row] |= bit;
            }
        }
        return planes;
    }

    function derivePmSprites(project) {
        const sprites = [];
        for (let index = 0; index < PM_SPRITE_COUNT; index++) sprites.push(derivePmSprite(project, index));
        return sprites;
    }

    function validatePmSprites(sprites) {
        if (!Array.isArray(sprites) || sprites.length !== PM_SPRITE_COUNT) throw new Error(`pmSprites must contain ${PM_SPRITE_COUNT} frames`);
        sprites.forEach((sprite, index) => {
            if (!sprite || typeof sprite !== 'object') throw new Error(`pmSprites[${index}] must be an object`);
            for (const plane of ['p0', 'p1']) {
                if (!Array.isArray(sprite[plane]) || sprite[plane].length !== PM_SPRITE_H) throw new Error(`pmSprites[${index}].${plane} must contain ${PM_SPRITE_H} rows`);
                sprite[plane].forEach((value, row) => assertByte(value, `pmSprites[${index}].${plane}[${row}]`));
            }
        });
        return sprites;
    }

    // pmSprites is optional: a project that predates PM art simply derives it
    // from the character frames, so old projects keep loading unchanged and
    // the schema version does not have to move.
    function ensurePmSprites(project) {
        if (!project.pmSprites) project.pmSprites = derivePmSprites(project);
        return project.pmSprites;
    }

    function pmPixel(sprite, x, y) {
        if (x < 0 || x > 7 || y < 0 || y >= PM_SPRITE_H) return 0;
        const bit = 1 << (7 - x);
        return ((sprite.p0[y] & bit) ? 1 : 0) | ((sprite.p1[y] & bit) ? 2 : 0);
    }

    function setPmPixel(sprite, x, y, value) {
        if (x < 0 || x > 7 || y < 0 || y >= PM_SPRITE_H) return;
        if (!Number.isInteger(value) || value < 0 || value > 3) throw new Error('PM pixel value must be 0-3');
        const bit = 1 << (7 - x);
        sprite.p0[y] = (value & 1) ? sprite.p0[y] | bit : sprite.p0[y] & ~bit;
        sprite.p1[y] = (value & 2) ? sprite.p1[y] | bit : sprite.p1[y] & ~bit;
    }

    function logicalTileDefinition(project, index) {
        return project.tileDefinitions.find(item => item.targetType === 'logicalTile' && item.targetIndex === index) || null;
    }

    // Downsample the BULLET tile's top cell to the missile's two pixels: the
    // character bullet was eight pixels wide, so each half of a row collapses
    // to one lit pixel if any of its four were lit. That keeps the glyph's
    // vertical profile, which is the part still legible at this size.
    function derivePmMissile(project) {
        const rows = new Array(PM_MISSILE_H).fill(0);
        const definition = logicalTileDefinition(project, BULLET_TILE_INDEX);
        if (!definition) return rows;
        for (let line = 0; line < PM_MISSILE_H; line++) {
            let value = 0;
            for (let logicalX = 0; logicalX < 8; logicalX++) {
                const address = tilePixelAddress(definition, logicalX, line);
                if (!address) continue;
                if (readPair(project.fontData, address.character, address.row, address.column)) {
                    value |= logicalX < 4 ? 2 : 1;
                }
            }
            rows[line] = value;
        }
        return rows;
    }

    function validatePmMissile(rows) {
        if (!Array.isArray(rows) || rows.length !== PM_MISSILE_H) throw new Error(`pmMissile must contain ${PM_MISSILE_H} rows`);
        rows.forEach((value, index) => {
            if (!Number.isInteger(value) || value < 0 || value > 3) throw new Error(`pmMissile[${index}] must be 0-3`);
        });
        return rows;
    }

    function ensurePmMissile(project) {
        if (!project.pmMissile) project.pmMissile = derivePmMissile(project);
        return project.pmMissile;
    }

    function pmMissilePixel(rows, x, y) {
        if (x < 0 || x > 1 || y < 0 || y >= PM_MISSILE_H) return 0;
        return (rows[y] & (x === 0 ? 2 : 1)) ? 1 : 0;
    }

    function setPmMissilePixel(rows, x, y, on) {
        if (x < 0 || x > 1 || y < 0 || y >= PM_MISSILE_H) return;
        const bit = x === 0 ? 2 : 1;
        rows[y] = on ? rows[y] | bit : rows[y] & ~bit;
    }

    function clonePmSprites(project) {
        return project.pmSprites ? project.pmSprites.map(sprite => ({ p0: sprite.p0.slice(), p1: sprite.p1.slice() })) : null;
    }

    function cloneState(project) {
        return {
            fontData: project.fontData.slice(),
            characters: project.tileDefinitions.map(definition => definition.characters.slice()),
            pmSprites: clonePmSprites(project),
            pmMissile: project.pmMissile ? project.pmMissile.slice() : null
        };
    }
    function restoreState(project, state) {
        project.fontData.splice(0, project.fontData.length, ...state.fontData);
        project.tileDefinitions.forEach((definition, index) => definition.characters.splice(0, 4, ...state.characters[index]));
        if (state.pmSprites) project.pmSprites = state.pmSprites.map(sprite => ({ p0: sprite.p0.slice(), p1: sprite.p1.slice() }));
        else delete project.pmSprites;
        if (state.pmMissile) project.pmMissile = state.pmMissile.slice();
        else delete project.pmMissile;
    }
    return { PROJECT_VERSION, PROJECT_TYPE, FONT_BYTES, LOGICAL_TILE_COUNT, PLAYER_SPRITE_COUNT, QUADRANTS, PM_SPRITE_COUNT, PM_SPRITE_H, PM_TILE_ROWS, PM_OVERHANG, PM_MISSILE_H, BULLET_TILE_INDEX, validateProject, baseCharacter, isInverse, quadrantIndex, tilePixelAddress, readPair, writePair, displayColorIndex, paintTilePixel, assignCharacter, setInverse, characterUsers, animationForTile, playerSpriteDefinition, derivePmSprite, derivePmSprites, ensurePmSprites, pmPixel, setPmPixel, logicalTileDefinition, derivePmMissile, ensurePmMissile, pmMissilePixel, setPmMissilePixel, cloneState, restoreState };
});
