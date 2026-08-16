(function () {
    'use strict';

    const Model = window.FujiRealmTiles;
    const PALETTE_NAMES = ['COLBAK', 'COLPF0', 'COLPF1', 'COLPF2', 'COLPF3'];
    const PALETTE_HEX = [0x00, 0xc8, 0x24, 0x0e, 0x4a];
    const PALETTE_CSS = ['#0F0F0F', '#6EAF3C', '#833B28', '#EFEFEF', '#E08CE0'];
    // PM sprite colors, matching pm_color0/pm_color1 in fujirealm.asm. The
    // third entry is what GTIA shows where P0 and P1 overlap: the bitwise OR
    // of the two color register values, $28 | $06 = $2E.
    const PM_COLOR_NAMES = ['Transparent', 'COLPM0', 'COLPM1', 'Overlap'];
    const PM_COLOR_HEX = [null, 0x28, 0x06, 0x2e];
    const PM_COLOR_CSS = ['#161616', '#C86818', '#585858', '#F0A040'];
    const PM_SCALE_X = 32;
    const PM_SCALE_Y = 24;
    const PM_MISSILE_SCALE_X = 64;
    const PM_MISSILE_SCALE_Y = 48;
    const STORAGE_KEY = 'fujirealm_tile_editor_v4';
    const MAX_UNDO = 200;

    const elements = Object.fromEntries([
        'project-input', 'font-input', 'load-project', 'save-project', 'load-font', 'save-font',
        'save-font-png', 'undo', 'redo', 'dirty-indicator', 'palette', 'character-canvas',
        'active-char-label', 'character-users', 'font-canvas', 'font-name', 'tile-name',
        'tile-binding', 'tile-canvas', 'empty-state', 'quadrant-buttons', 'assign-character',
        'inverse-toggle', 'tile-coordinate', 'status-text', 'tile-search', 'category-filter',
        'tile-list', 'animation-controls', 'animation-play', 'animation-frames', 'message-dialog',
        'dialog-title', 'dialog-message', 'pm-canvas', 'pm-bar', 'pm-colors', 'pm-reseed', 'pm-toggle', 'pm-toggle-label'
    ].map(id => [id, document.getElementById(id)]));

    let project = null;
    let projectFileName = 'fujirealm_v6_charsetter.json';
    let selectedTileId = null;
    let selectedQuadrant = 0;
    let activeCharacter = 0;
    let activeColor = 1;
    let dirty = false;
    let drawingTile = false;
    let drawingCharacter = false;
    let strokeVisited = new Set();
    let undoStack = [];
    let redoStack = [];
    let animationTimer = null;
    let animation = null;
    let animationFrame = 0;
    let pmEditing = false;
    let pmColor = 1;
    let drawingPm = false;

    function showMessage(title, message) {
        elements['dialog-title'].textContent = title;
        elements['dialog-message'].textContent = message;
        elements['message-dialog'].showModal();
    }

    function setStatus(message) {
        elements['status-text'].textContent = message;
    }

    function setDirty(value) {
        dirty = value;
        elements['dirty-indicator'].hidden = !dirty;
        if (project) {
            try { localStorage.setItem(STORAGE_KEY, JSON.stringify(project)); } catch (_) { }
        }
    }

    function snapshotForUndo() {
        if (!project) return;
        undoStack.push(Model.cloneState(project));
        if (undoStack.length > MAX_UNDO) undoStack.shift();
        redoStack = [];
        updateUndoButtons();
    }

    function updateUndoButtons() {
        elements.undo.disabled = !project || undoStack.length === 0;
        elements.redo.disabled = !project || redoStack.length === 0;
    }

    function restoreFrom(stack, destination) {
        if (!project || stack.length === 0) return;
        destination.push(Model.cloneState(project));
        Model.restoreState(project, stack.pop());
        setDirty(true);
        renderAll();
        updateUndoButtons();
    }

    function selectedDefinition() {
        return project ? project.tileDefinitions.find(item => item.id === selectedTileId) || null : null;
    }

    function previewDefinition() {
        if (!project || !animation || !animationTimer) return selectedDefinition();
        return project.tileDefinitions.find(item => item.id === animation.frameIds[animationFrame]) || selectedDefinition();
    }

    function currentPalette() {
        return project && Array.isArray(project.paletteA4) ? project.paletteA4 : PALETTE_CSS;
    }

    function drawCharacter(ctx, code, x, y, scale) {
        const fontData = project ? project.fontData : Array(1024).fill(0);
        const character = Model.baseCharacter(code);
        const inverse = Model.isInverse(code);
        const palette = currentPalette();
        ctx.fillStyle = palette[0];
        ctx.fillRect(x, y, 8 * scale, 8 * scale);
        for (let row = 0; row < 8; row++) {
            for (let column = 0; column < 4; column++) {
                const pair = Model.readPair(fontData, character, row, column);
                const color = pair === 3 && inverse ? 4 : pair;
                ctx.fillStyle = palette[color];
                ctx.fillRect(x + column * 2 * scale, y + row * scale, 2 * scale, scale);
            }
        }
    }

    function drawTile(ctx, definition, x, y, scale) {
        if (!project || !definition) return;
        drawCharacter(ctx, definition.characters[0], x, y, scale);
        drawCharacter(ctx, definition.characters[1], x + 8 * scale, y, scale);
        drawCharacter(ctx, definition.characters[2], x, y + 8 * scale, scale);
        drawCharacter(ctx, definition.characters[3], x + 8 * scale, y + 8 * scale, scale);
    }

    function renderPalette() {
        elements.palette.replaceChildren();
        PALETTE_NAMES.forEach((name, index) => {
            const button = document.createElement('button');
            button.className = `swatch${index === activeColor ? ' active' : ''}`;
            button.style.background = currentPalette()[index];
            button.title = `${name} $${PALETTE_HEX[index].toString(16).padStart(2, '0').toUpperCase()}`;
            button.innerHTML = `<span>${name}</span>`;
            button.addEventListener('click', () => { activeColor = index; renderPalette(); });
            elements.palette.appendChild(button);
        });
    }

    function renderCharacterEditor() {
        const canvas = elements['character-canvas'];
        const ctx = canvas.getContext('2d');
        ctx.imageSmoothingEnabled = false;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        drawCharacter(ctx, activeCharacter, 0, 0, 32);
        ctx.strokeStyle = 'rgba(255,255,255,.10)';
        ctx.lineWidth = 1;
        for (let x = 64; x < 256; x += 64) { ctx.beginPath(); ctx.moveTo(x + .5, 0); ctx.lineTo(x + .5, 256); ctx.stroke(); }
        for (let y = 32; y < 256; y += 32) { ctx.beginPath(); ctx.moveTo(0, y + .5); ctx.lineTo(256, y + .5); ctx.stroke(); }
        elements['active-char-label'].textContent = `$${activeCharacter.toString(16).padStart(2, '0').toUpperCase()}`;
        if (!project) {
            elements['character-users'].textContent = '';
            return;
        }
        const users = Model.characterUsers(project, activeCharacter);
        const visible = users.filter(user => user.definition.visible);
        elements['character-users'].textContent = visible.length
            ? visible.map(user => `${user.definition.name} ${user.quadrantName.toUpperCase()}`).join(' · ')
            : 'No visible tile uses this character';
    }

    function renderFont() {
        const canvas = elements['font-canvas'];
        const ctx = canvas.getContext('2d');
        ctx.imageSmoothingEnabled = false;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (let index = 0; index < 256; index++) {
            const column = index % 16;
            const row = Math.floor(index / 16);
            drawCharacter(ctx, index, column * 18 + 1, row * 18 + 1, 2);
        }
        const column = activeCharacter % 16;
        const row = Math.floor(activeCharacter / 16);
        ctx.strokeStyle = '#ef7d21';
        ctx.lineWidth = 2;
        ctx.strokeRect(column * 18 + 1, row * 18 + 1, 16, 16);
        elements['font-name'].textContent = project ? project.fontName || '' : '';
    }

    function renderTileCanvas() {
        const canvas = elements['tile-canvas'];
        const ctx = canvas.getContext('2d');
        ctx.imageSmoothingEnabled = false;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        const definition = previewDefinition();
        elements['empty-state'].hidden = Boolean(definition);
        canvas.hidden = !definition;
        if (!definition) return;
        const palette = currentPalette();
        for (let logicalY = 0; logicalY < 16; logicalY++) {
            for (let logicalX = 0; logicalX < 8; logicalX++) {
                ctx.fillStyle = palette[Model.displayColorIndex(definition, project.fontData, logicalX, logicalY)];
                ctx.fillRect(logicalX * 64, logicalY * 32, 64, 32);
            }
        }
        ctx.strokeStyle = 'rgba(255,255,255,.12)';
        ctx.lineWidth = 1;
        for (let x = 64; x < 512; x += 64) { ctx.beginPath(); ctx.moveTo(x + .5, 0); ctx.lineTo(x + .5, 512); ctx.stroke(); }
        for (let y = 32; y < 512; y += 32) { ctx.beginPath(); ctx.moveTo(0, y + .5); ctx.lineTo(512, y + .5); ctx.stroke(); }
        ctx.strokeStyle = '#ef7d21';
        ctx.lineWidth = 4;
        ctx.beginPath(); ctx.moveTo(256, 0); ctx.lineTo(256, 512); ctx.moveTo(0, 256); ctx.lineTo(512, 256); ctx.stroke();
        if (!animationTimer) {
            const qx = selectedQuadrant % 2;
            const qy = Math.floor(selectedQuadrant / 2);
            ctx.strokeStyle = '#55a7e8';
            ctx.lineWidth = 5;
            ctx.strokeRect(qx * 256 + 3, qy * 256 + 3, 250, 250);
        }
    }

    function renderQuadrants() {
        const definition = selectedDefinition();
        elements['quadrant-buttons'].replaceChildren();
        Model.QUADRANTS.forEach((name, index) => {
            const button = document.createElement('button');
            button.className = `quadrant-button${index === selectedQuadrant ? ' active' : ''}`;
            const code = definition ? definition.characters[index] : 0;
            button.textContent = `${name.toUpperCase()} $${code.toString(16).padStart(2, '0').toUpperCase()}`;
            button.disabled = !definition;
            button.addEventListener('click', () => selectQuadrant(index));
            elements['quadrant-buttons'].appendChild(button);
        });
        elements['assign-character'].disabled = !definition;
        elements['inverse-toggle'].disabled = !definition;
        elements['inverse-toggle'].checked = definition ? Model.isInverse(definition.characters[selectedQuadrant]) : false;
    }

    function renderAnimationControls() {
        stopAnimation(false);
        animation = project && selectedTileId ? Model.animationForTile(project, selectedTileId) : null;
        elements['animation-controls'].hidden = !animation;
        elements['animation-frames'].replaceChildren();
        if (!animation) return;
        animationFrame = Math.max(0, animation.frameIds.indexOf(selectedTileId));
        animation.frameIds.forEach((frameId, index) => {
            const button = document.createElement('button');
            button.className = `frame-button${frameId === selectedTileId ? ' active' : ''}`;
            button.textContent = String(index + 1);
            button.title = project.tileDefinitions.find(item => item.id === frameId).name;
            button.addEventListener('click', () => selectTile(frameId));
            elements['animation-frames'].appendChild(button);
        });
    }

    function renderTileHeader() {
        const definition = selectedDefinition();
        elements['tile-name'].textContent = definition ? definition.name : 'No project loaded';
        elements['tile-binding'].textContent = definition ? `${definition.targetType} ${definition.targetIndex}` : '';
    }

    function tileFilterMatches(definition) {
        const query = elements['tile-search'].value.trim().toLowerCase();
        const category = elements['category-filter'].value;
        return (!query || definition.name.toLowerCase().includes(query)) && (!category || definition.category === category);
    }

    function renderLibrary(rebuildCategories = false) {
        elements['tile-list'].replaceChildren();
        if (!project) return;
        const visible = project.tileDefinitions.filter(item => item.visible);
        if (rebuildCategories) {
            const selected = elements['category-filter'].value;
            const categories = [...new Set(visible.map(item => item.category))];
            elements['category-filter'].innerHTML = '<option value="">All categories</option>';
            categories.forEach(category => elements['category-filter'].add(new Option(category, category)));
            elements['category-filter'].value = categories.includes(selected) ? selected : '';
        }
        visible.filter(tileFilterMatches).forEach(definition => {
            const button = document.createElement('button');
            button.className = `tile-item${definition.id === selectedTileId ? ' active' : ''}`;
            const canvas = document.createElement('canvas');
            canvas.width = 48; canvas.height = 48;
            const label = document.createElement('div');
            label.innerHTML = `<strong></strong><span></span>`;
            label.querySelector('strong').textContent = definition.name;
            label.querySelector('span').textContent = `${definition.targetType} ${definition.targetIndex}`;
            button.append(canvas, label);
            button.addEventListener('click', () => selectTile(definition.id));
            elements['tile-list'].appendChild(button);
            drawTile(canvas.getContext('2d'), definition, 0, 0, 3);
        });
    }

    // The six local-player frames and the bullet are the only art the client
    // draws with Player/Missile graphics; everything else is characters.
    function pmFrameIndex(definition) {
        if (!definition || definition.targetType !== 'playerSprite') return -1;
        return definition.targetIndex < Model.PM_SPRITE_COUNT ? definition.targetIndex : -1;
    }

    function pmMode(definition) {
        if (pmFrameIndex(definition) >= 0) return 'sprite';
        if (definition && definition.targetType === 'logicalTile' && definition.targetIndex === Model.BULLET_TILE_INDEX) return 'missile';
        return null;
    }

    // Read-only view of the current PM frame. A project with no stored PM art
    // derives it from the characters on the fly, so editing the character
    // sprite keeps updating the PM sprite until the PM art is edited directly
    // -- materializing it on a mere render would silently break that link.
    function selectedPmSprite() {
        if (!project) return null;
        const index = pmFrameIndex(previewDefinition());
        if (index < 0) return null;
        return project.pmSprites ? project.pmSprites[index] : Model.derivePmSprite(project, index);
    }

    // Writable view: this is where a project stops deriving its PM art.
    function editablePmSprite() {
        if (!project) return null;
        const index = pmFrameIndex(selectedDefinition());
        if (index < 0) return null;
        return Model.ensurePmSprites(project)[index];
    }

    function pmAvailable() {
        return pmMode(previewDefinition()) !== null;
    }

    function renderPmColors() {
        elements['pm-colors'].replaceChildren();
        PM_COLOR_NAMES.forEach((name, value) => {
            const button = document.createElement('button');
            button.className = `quadrant-button${value === pmColor ? ' active' : ''}`;
            button.style.borderColor = PM_COLOR_CSS[value];
            button.textContent = PM_COLOR_HEX[value] === null
                ? name
                : `${name} $${PM_COLOR_HEX[value].toString(16).padStart(2, '0').toUpperCase()}`;
            button.addEventListener('click', () => { pmColor = value; renderPmColors(); });
            elements['pm-colors'].appendChild(button);
        });
    }

    function renderPmCanvas() {
        const canvas = elements['pm-canvas'];
        const mode = pmMode(previewDefinition());
        const showing = mode !== null && pmEditing;
        elements['pm-bar'].hidden = mode === null;
        elements['pm-toggle'].checked = pmEditing;
        elements['pm-toggle-label'].textContent = mode === 'missile' ? 'Edit PM missile' : 'Edit PM sprite';
        canvas.hidden = !showing;
        elements['tile-canvas'].hidden = showing || !previewDefinition();
        if (!showing) return;
        if (mode === 'missile') { renderPmMissileCanvas(); return; }
        canvas.width = 8 * PM_SCALE_X;
        canvas.height = Model.PM_SPRITE_H * PM_SCALE_Y;
        elements['pm-colors'].hidden = false;
        renderPmColors();
        const sprite = selectedPmSprite();
        const ctx = canvas.getContext('2d');
        ctx.imageSmoothingEnabled = false;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (let y = 0; y < Model.PM_SPRITE_H; y++) {
            for (let x = 0; x < 8; x++) {
                ctx.fillStyle = PM_COLOR_CSS[Model.pmPixel(sprite, x, y)];
                ctx.fillRect(x * PM_SCALE_X, y * PM_SCALE_Y, PM_SCALE_X, PM_SCALE_Y);
            }
        }
        ctx.strokeStyle = 'rgba(255,255,255,.12)';
        ctx.lineWidth = 1;
        for (let x = PM_SCALE_X; x < canvas.width; x += PM_SCALE_X) { ctx.beginPath(); ctx.moveTo(x + .5, 0); ctx.lineTo(x + .5, canvas.height); ctx.stroke(); }
        for (let y = PM_SCALE_Y; y < canvas.height; y += PM_SCALE_Y) { ctx.beginPath(); ctx.moveTo(0, y + .5); ctx.lineTo(canvas.width, y + .5); ctx.stroke(); }
        // Where the tile the player stands in begins: rows above this line
        // overhang it and draw over whatever terrain is behind.
        const tileTop = Model.PM_OVERHANG * PM_SCALE_Y;
        ctx.strokeStyle = '#ef7d21';
        ctx.lineWidth = 3;
        ctx.beginPath(); ctx.moveTo(0, tileTop + .5); ctx.lineTo(canvas.width, tileTop + .5); ctx.stroke();
    }

    // A missile is two bits wide in a single colour, so there is nothing to
    // pick: left click lights a pixel, right click clears it.
    function renderPmMissileCanvas() {
        const canvas = elements['pm-canvas'];
        canvas.width = 2 * PM_MISSILE_SCALE_X;
        canvas.height = Model.PM_MISSILE_H * PM_MISSILE_SCALE_Y;
        elements['pm-colors'].hidden = true;
        const rows = project.pmMissile || Model.derivePmMissile(project);
        const ctx = canvas.getContext('2d');
        ctx.imageSmoothingEnabled = false;
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (let y = 0; y < Model.PM_MISSILE_H; y++) {
            for (let x = 0; x < 2; x++) {
                ctx.fillStyle = Model.pmMissilePixel(rows, x, y) ? currentPalette()[4] : PM_COLOR_CSS[0];
                ctx.fillRect(x * PM_MISSILE_SCALE_X, y * PM_MISSILE_SCALE_Y, PM_MISSILE_SCALE_X, PM_MISSILE_SCALE_Y);
            }
        }
        ctx.strokeStyle = 'rgba(255,255,255,.12)';
        ctx.lineWidth = 1;
        for (let x = PM_MISSILE_SCALE_X; x < canvas.width; x += PM_MISSILE_SCALE_X) { ctx.beginPath(); ctx.moveTo(x + .5, 0); ctx.lineTo(x + .5, canvas.height); ctx.stroke(); }
        for (let y = PM_MISSILE_SCALE_Y; y < canvas.height; y += PM_MISSILE_SCALE_Y) { ctx.beginPath(); ctx.moveTo(0, y + .5); ctx.lineTo(canvas.width, y + .5); ctx.stroke(); }
    }

    function editPmMissileAt(event) {
        const rows = Model.ensurePmMissile(project);
        const point = canvasPoint(event, elements['pm-canvas']);
        const x = Math.floor(point.x / PM_MISSILE_SCALE_X);
        const y = Math.floor(point.y / PM_MISSILE_SCALE_Y);
        if (x < 0 || x > 1 || y < 0 || y >= Model.PM_MISSILE_H) return;
        const key = `pmm:${x}:${y}`;
        if (strokeVisited.has(key)) return;
        strokeVisited.add(key);
        Model.setPmMissilePixel(rows, x, y, !(event.buttons === 2 || event.button === 2));
        setDirty(true);
        elements['tile-coordinate'].textContent = `X=${x} Y=${y}`;
        renderPmCanvas();
    }

    function editPmAt(event) {
        if (pmMode(selectedDefinition()) === 'missile') { editPmMissileAt(event); return; }
        const sprite = editablePmSprite();
        if (!sprite) return;
        const point = canvasPoint(event, elements['pm-canvas']);
        const x = Math.floor(point.x / PM_SCALE_X);
        const y = Math.floor(point.y / PM_SCALE_Y);
        if (x < 0 || x > 7 || y < 0 || y >= Model.PM_SPRITE_H) return;
        const key = `pm:${x}:${y}`;
        if (strokeVisited.has(key)) return;
        strokeVisited.add(key);
        Model.setPmPixel(sprite, x, y, event.buttons === 2 || event.button === 2 ? 0 : pmColor);
        setDirty(true);
        elements['tile-coordinate'].textContent = `X=${x} Y=${y}`;
        renderPmCanvas();
        renderLibrary();
    }

    function reseedPmSprite() {
        const definition = selectedDefinition();
        const mode = pmMode(definition);
        if (!mode) return;
        snapshotForUndo();
        if (mode === 'missile') {
            project.pmMissile = Model.derivePmMissile(project);
            setStatus('PM missile reseeded from the BULLET tile');
        } else {
            const index = pmFrameIndex(definition);
            Model.ensurePmSprites(project)[index] = Model.derivePmSprite(project, index);
            setStatus('PM frame reseeded from the character art');
        }
        setDirty(true);
        renderPmCanvas();
    }

    function renderAll() {
        renderPalette();
        renderCharacterEditor();
        renderFont();
        renderTileHeader();
        renderTileCanvas();
        renderPmCanvas();
        renderQuadrants();
        renderLibrary();
    }

    function selectQuadrant(index) {
        stopAnimation();
        selectedQuadrant = index;
        const definition = selectedDefinition();
        if (definition) activeCharacter = definition.characters[index];
        renderCharacterEditor(); renderFont(); renderQuadrants(); renderTileCanvas();
    }

    function selectTile(id) {
        stopAnimation();
        selectedTileId = id;
        selectedQuadrant = 0;
        const definition = selectedDefinition();
        if (definition) activeCharacter = definition.characters[0];
        renderAnimationControls();
        renderAll();
    }

    function stopAnimation(render = true) {
        if (animationTimer) clearInterval(animationTimer);
        animationTimer = null;
        const icon = elements['animation-play'].querySelector('i');
        if (icon) icon.className = 'bi bi-play-fill';
        if (render && project) renderTileCanvas();
    }

    function toggleAnimation() {
        if (!animation) return;
        if (animationTimer) { stopAnimation(); return; }
        elements['animation-play'].querySelector('i').className = 'bi bi-pause-fill';
        animationTimer = setInterval(() => {
            animationFrame = (animationFrame + 1) % animation.frameIds.length;
            renderTileCanvas();
        }, animation.intervalMs);
        renderTileCanvas();
    }

    function canvasPoint(event, canvas) {
        const rect = canvas.getBoundingClientRect();
        return { x: (event.clientX - rect.left) * canvas.width / rect.width, y: (event.clientY - rect.top) * canvas.height / rect.height };
    }

    function editTileAt(event) {
        let definition = previewDefinition();
        if (!definition) return;
        if (animationTimer) {
            const frameId = animation.frameIds[animationFrame];
            stopAnimation(false);
            selectedTileId = frameId;
            definition = selectedDefinition();
            renderAnimationControls();
        }
        const point = canvasPoint(event, elements['tile-canvas']);
        const logicalX = Math.floor(point.x / 64);
        const logicalY = Math.floor(point.y / 32);
        const key = `${logicalX}:${logicalY}`;
        if (strokeVisited.has(key)) return;
        strokeVisited.add(key);
        const color = event.buttons === 2 || event.button === 2 ? 0 : activeColor;
        selectedQuadrant = Model.paintTilePixel(definition, project.fontData, logicalX, logicalY, color);
        activeCharacter = definition.characters[selectedQuadrant];
        setDirty(true);
        renderAll();
    }

    function editCharacterAt(event) {
        if (!project) return;
        const point = canvasPoint(event, elements['character-canvas']);
        const column = Math.floor(point.x / 64);
        const row = Math.floor(point.y / 32);
        if (column < 0 || column > 3 || row < 0 || row > 7) return;
        const key = `${column}:${row}`;
        if (strokeVisited.has(key)) return;
        strokeVisited.add(key);
        const color = event.buttons === 2 || event.button === 2 ? 0 : activeColor;
        const pair = color === 4 ? 3 : color;
        Model.writePair(project.fontData, Model.baseCharacter(activeCharacter), row, column, pair);
        const definition = selectedDefinition();
        if (definition && Model.baseCharacter(definition.characters[selectedQuadrant]) === Model.baseCharacter(activeCharacter)) {
            if (color === 4) Model.setInverse(definition, selectedQuadrant, true);
            if (color === 3) Model.setInverse(definition, selectedQuadrant, false);
            activeCharacter = definition.characters[selectedQuadrant];
        }
        setDirty(true);
        renderAll();
    }

    function manipulateCharacter(action) {
        if (!project) return;
        stopAnimation(); snapshotForUndo();
        const base = Model.baseCharacter(activeCharacter);
        const offset = base * 8;
        const bytes = project.fontData.slice(offset, offset + 8);
        if (action === 'up') bytes.push(bytes.shift());
        if (action === 'down') bytes.unshift(bytes.pop());
        if (action === 'left') for (let i = 0; i < 8; i++) bytes[i] = ((bytes[i] << 2) | (bytes[i] >> 6)) & 0xff;
        if (action === 'right') for (let i = 0; i < 8; i++) bytes[i] = ((bytes[i] >> 2) | (bytes[i] << 6)) & 0xff;
        if (action === 'mirror-h') for (let i = 0; i < 8; i++) {
            let result = 0;
            for (let pair = 0; pair < 4; pair++) result |= ((bytes[i] >> (pair * 2)) & 3) << (6 - pair * 2);
            bytes[i] = result;
        }
        if (action === 'mirror-v') bytes.reverse();
        if (action === 'clear') bytes.fill(0);
        project.fontData.splice(offset, 8, ...bytes);
        setDirty(true); renderAll();
    }

    function loadProjectObject(value, fileName, restored = false) {
        try {
            Model.validateProject(value);
        } catch (error) {
            if (value && value.version === 3) throw new Error('This is a Charsetter v3 map project. Re-export FujiRealm art to create the required v4 tile project.');
            throw error;
        }
        stopAnimation(false);
        project = JSON.parse(JSON.stringify(value));
        project.paletteHex = PALETTE_HEX.slice();
        project.paletteA4 = PALETTE_CSS.slice();
        projectFileName = fileName || projectFileName;
        const first = project.tileDefinitions.find(item => item.visible);
        selectedTileId = first ? first.id : null;
        selectedQuadrant = 0;
        activeCharacter = first ? first.characters[0] : 0;
        undoStack = []; redoStack = [];
        setDirty(false);
        renderLibrary(true);
        renderAnimationControls();
        renderAll(); updateUndoButtons();
        setStatus(restored ? 'Restored local workspace' : 'Project loaded');
    }

    function download(data, type, fileName) {
        const anchor = document.createElement('a');
        anchor.href = URL.createObjectURL(new Blob([data], { type }));
        anchor.download = fileName;
        anchor.click();
        setTimeout(() => URL.revokeObjectURL(anchor.href), 1000);
    }

    function saveProject() {
        if (!project) return;
        project.paletteHex = PALETTE_HEX.slice();
        project.paletteA4 = PALETTE_CSS.slice();
        download(JSON.stringify(project, null, 2) + '\n', 'application/json', projectFileName);
        setDirty(false); setStatus('Project saved');
    }

    function saveFont() {
        if (!project) return;
        download(new Uint8Array(project.fontData), 'application/octet-stream', project.fontName || 'fujirealm_v6_charsetter.fnt');
    }

    function saveFontPng() {
        if (!project) return;
        const canvas = document.createElement('canvas');
        canvas.width = 128; canvas.height = 64;
        const ctx = canvas.getContext('2d');
        for (let index = 0; index < 128; index++) drawCharacter(ctx, index, (index % 16) * 8, Math.floor(index / 16) * 8, 1);
        const anchor = document.createElement('a');
        anchor.download = (project.fontName || 'fujirealm').replace(/\.fnt$/i, '') + '.png';
        anchor.href = canvas.toDataURL('image/png'); anchor.click();
    }

    function wireEvents() {
        elements['load-project'].addEventListener('click', () => {
            if (!dirty || confirm('Discard unsaved changes and load another project?')) elements['project-input'].click();
        });
        elements['project-input'].addEventListener('change', event => {
            const file = event.target.files[0]; if (!file) return;
            const reader = new FileReader();
            reader.onload = () => { try { loadProjectObject(JSON.parse(reader.result), file.name); } catch (error) { showMessage('Project Error', error.message); } };
            reader.readAsText(file); event.target.value = '';
        });
        elements['save-project'].addEventListener('click', saveProject);
        elements['load-font'].addEventListener('click', () => elements['font-input'].click());
        elements['font-input'].addEventListener('change', event => {
            const file = event.target.files[0]; if (!file || !project) return;
            const reader = new FileReader();
            reader.onload = () => {
                const bytes = new Uint8Array(reader.result);
                if (bytes.length !== 1024) { showMessage('Font Error', `Expected 1024 bytes, found ${bytes.length}.`); return; }
                snapshotForUndo(); project.fontData.splice(0, 1024, ...bytes); project.fontName = file.name; setDirty(true); renderAll();
            };
            reader.readAsArrayBuffer(file); event.target.value = '';
        });
        elements['save-font'].addEventListener('click', saveFont);
        elements['save-font-png'].addEventListener('click', saveFontPng);
        elements.undo.addEventListener('click', () => restoreFrom(undoStack, redoStack));
        elements.redo.addEventListener('click', () => restoreFrom(redoStack, undoStack));
        elements['animation-play'].addEventListener('click', toggleAnimation);
        elements['assign-character'].addEventListener('click', () => {
            const definition = selectedDefinition(); if (!definition) return;
            stopAnimation(); snapshotForUndo(); Model.assignCharacter(definition, selectedQuadrant, activeCharacter); setDirty(true); renderAll();
        });
        elements['inverse-toggle'].addEventListener('change', event => {
            const definition = selectedDefinition(); if (!definition) return;
            stopAnimation(); snapshotForUndo(); Model.setInverse(definition, selectedQuadrant, event.target.checked); activeCharacter = definition.characters[selectedQuadrant]; setDirty(true); renderAll();
        });
        elements['tile-search'].addEventListener('input', () => renderLibrary());
        elements['category-filter'].addEventListener('change', () => renderLibrary());
        document.querySelectorAll('[data-char-action]').forEach(button => button.addEventListener('click', () => manipulateCharacter(button.dataset.charAction)));

        elements['font-canvas'].addEventListener('mousedown', event => {
            const point = canvasPoint(event, elements['font-canvas']);
            activeCharacter = Math.max(0, Math.min(255, Math.floor(point.y / 18) * 16 + Math.floor(point.x / 18)));
            renderCharacterEditor(); renderFont();
        });
        elements['tile-canvas'].addEventListener('contextmenu', event => event.preventDefault());
        elements['tile-canvas'].addEventListener('mousedown', event => { if (!project) return; drawingTile = true; strokeVisited.clear(); snapshotForUndo(); editTileAt(event); });
        elements['tile-canvas'].addEventListener('mousemove', event => {
            const point = canvasPoint(event, elements['tile-canvas']);
            elements['tile-coordinate'].textContent = `X=${Math.max(0, Math.min(7, Math.floor(point.x / 64)))} Y=${Math.max(0, Math.min(15, Math.floor(point.y / 32)))}`;
            if (drawingTile) editTileAt(event);
        });
        elements['character-canvas'].addEventListener('contextmenu', event => event.preventDefault());
        elements['character-canvas'].addEventListener('mousedown', event => { if (!project) return; drawingCharacter = true; strokeVisited.clear(); snapshotForUndo(); editCharacterAt(event); });
        elements['character-canvas'].addEventListener('mousemove', event => { if (drawingCharacter) editCharacterAt(event); });
        elements['pm-toggle'].addEventListener('change', event => { pmEditing = event.target.checked; stopAnimation(false); renderAll(); });
        elements['pm-reseed'].addEventListener('click', reseedPmSprite);
        elements['pm-canvas'].addEventListener('contextmenu', event => event.preventDefault());
        elements['pm-canvas'].addEventListener('mousedown', event => { if (!project) return; drawingPm = true; strokeVisited.clear(); snapshotForUndo(); editPmAt(event); });
        elements['pm-canvas'].addEventListener('mousemove', event => { if (drawingPm) editPmAt(event); });
        window.addEventListener('mouseup', () => { drawingTile = false; drawingCharacter = false; drawingPm = false; strokeVisited.clear(); });
        window.addEventListener('keydown', event => {
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); saveProject(); }
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') { event.preventDefault(); restoreFrom(undoStack, redoStack); }
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') { event.preventDefault(); restoreFrom(redoStack, undoStack); }
        });
        window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
    }

    function init() {
        wireEvents(); renderAll(); updateUndoButtons();
        const projectUrl = new URLSearchParams(window.location.search).get('project');
        if (projectUrl) {
            fetch(projectUrl)
                .then(response => {
                    if (!response.ok) throw new Error(`Project request failed with HTTP ${response.status}`);
                    return response.json();
                })
                .then(value => loadProjectObject(value, projectUrl.split('/').pop()))
                .catch(error => showMessage('Project Error', error.message));
            return;
        }
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) loadProjectObject(JSON.parse(saved), projectFileName, true);
        } catch (_) { localStorage.removeItem(STORAGE_KEY); }
    }

    init();
})();
