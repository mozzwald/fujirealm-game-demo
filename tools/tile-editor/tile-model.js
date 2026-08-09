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
    function cloneState(project) { return { fontData: project.fontData.slice(), characters: project.tileDefinitions.map(definition => definition.characters.slice()) }; }
    function restoreState(project, state) {
        project.fontData.splice(0, project.fontData.length, ...state.fontData);
        project.tileDefinitions.forEach((definition, index) => definition.characters.splice(0, 4, ...state.characters[index]));
    }
    return { PROJECT_VERSION, PROJECT_TYPE, FONT_BYTES, LOGICAL_TILE_COUNT, PLAYER_SPRITE_COUNT, QUADRANTS, validateProject, baseCharacter, isInverse, quadrantIndex, tilePixelAddress, readPair, writePair, displayColorIndex, paintTilePixel, assignCharacter, setInverse, characterUsers, animationForTile, cloneState, restoreState };
});
