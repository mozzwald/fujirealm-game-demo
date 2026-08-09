(function () {
    'use strict';
    const Model = globalThis.FujiRealmLynx;
    const EDITOR_SCALE = 64;   // 8x8 tile drawn at 512x512
    const TILED_SCALE = 8;     // 3x3 neighbour preview
    const UNDO_LIMIT = 60;

    const ids = [
        'tileset-input', 'load-tileset', 'save-tileset', 'undo', 'redo',
        'dirty-indicator', 'palette', 'active-pen-label', 'tiled-canvas',
        'actual-canvas', 'sprite-cost', 'entry-name', 'entry-binding',
        'editor-canvas', 'empty-state', 'library-filter', 'library-kind',
        'show-unused', 'tile-list',
    ];
    const el = {};
    ids.forEach(id => { el[id.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = document.getElementById(id); });

    let tileset = null;
    let fileName = 'lynx_tileset.json';
    let selectedKey = null;
    let activePen = 1;
    let dirty = false;
    let painting = false;
    const undoStack = [];
    const redoStack = [];

    function selected() { return tileset && selectedKey ? Model.findEntry(tileset, selectedKey) : null; }

    function setDirty(value) {
        dirty = value;
        el.dirtyIndicator.hidden = !value;
    }

    function snapshot() {
        if (!tileset) return;
        undoStack.push(Model.cloneState(tileset));
        if (undoStack.length > UNDO_LIMIT) undoStack.shift();
        redoStack.length = 0;
        updateUndoButtons();
    }

    function updateUndoButtons() {
        el.undo.disabled = !undoStack.length;
        el.redo.disabled = !redoStack.length;
    }

    function stepHistory(from, to) {
        if (!tileset || !from.length) return;
        to.push(Model.cloneState(tileset));
        Model.restoreState(tileset, from.pop());
        updateUndoButtons();
        setDirty(true);
        renderAll();
    }

    // ---------------------------------------------------------------- render

    function palette() { return tileset ? tileset.palette : []; }

    function drawEntry(ctx, entry, x, y, scale) {
        const colours = palette();
        for (let py = 0; py < Model.TILE_H; py++) {
            for (let px = 0; px < Model.TILE_W; px++) {
                ctx.fillStyle = colours[Model.getPixel(entry, px, py)] || '#000';
                ctx.fillRect(x + px * scale, y + py * scale, scale, scale);
            }
        }
    }

    function renderPalette() {
        el.palette.replaceChildren();
        palette().forEach((colour, index) => {
            const button = document.createElement('button');
            button.className = 'swatch' + (index === activePen ? ' active' : '');
            button.style.background = colour;
            button.title = `Pen ${index} — ${colour}${index === Model.TRANSPARENT_PEN ? ' (transparent on entities)' : ''}`;
            button.addEventListener('click', () => { activePen = index; renderPalette(); });
            el.palette.appendChild(button);
        });
        el.activePenLabel.textContent = `$${activePen.toString(16).toUpperCase()}`;
    }

    function renderEditor() {
        const ctx = el.editorCanvas.getContext('2d');
        const item = selected();
        ctx.fillStyle = '#121416';
        ctx.fillRect(0, 0, el.editorCanvas.width, el.editorCanvas.height);
        el.emptyState.hidden = Boolean(item);
        el.editorCanvas.style.visibility = item ? 'visible' : 'hidden';
        if (!item) return;
        drawEntry(ctx, item.entry, 0, 0, EDITOR_SCALE);
        // A grid, brightened every 4 pixels so the tile's centre is findable.
        for (let i = 0; i <= Model.TILE_W; i++) {
            ctx.strokeStyle = i % 4 === 0 ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.12)';
            ctx.beginPath();
            ctx.moveTo(i * EDITOR_SCALE + 0.5, 0);
            ctx.lineTo(i * EDITOR_SCALE + 0.5, Model.TILE_H * EDITOR_SCALE);
            ctx.moveTo(0, i * EDITOR_SCALE + 0.5);
            ctx.lineTo(Model.TILE_W * EDITOR_SCALE, i * EDITOR_SCALE + 0.5);
            ctx.stroke();
        }
    }

    function renderPreviews() {
        const item = selected();
        const tiled = el.tiledCanvas.getContext('2d');
        const actual = el.actualCanvas.getContext('2d');
        tiled.fillStyle = '#121416';
        tiled.fillRect(0, 0, el.tiledCanvas.width, el.tiledCanvas.height);
        actual.clearRect(0, 0, el.actualCanvas.width, el.actualCanvas.height);
        if (!item) { el.spriteCost.textContent = ''; return; }
        for (let ty = 0; ty < 3; ty++) {
            for (let tx = 0; tx < 3; tx++) {
                drawEntry(tiled, item.entry, tx * Model.TILE_W * TILED_SCALE, ty * Model.TILE_H * TILED_SCALE, TILED_SCALE);
            }
        }
        drawEntry(actual, item.entry, 0, 0, 1);
        el.spriteCost.textContent = `${Model.spriteBytes(item.entry).length} bytes on cart`;
    }

    function renderHeader() {
        const item = selected();
        el.entryName.textContent = item ? item.label : 'No tile selected';
        el.entryBinding.textContent = item ? item.detail : '';
    }

    function renderLibrary() {
        if (!tileset) { el.tileList.replaceChildren(); return; }
        const filter = el.libraryFilter.value.trim().toLowerCase();
        const kind = el.libraryKind.value;
        const showUnused = el.showUnused.checked;
        el.tileList.replaceChildren();
        Model.entries(tileset).forEach(item => {
            if (kind !== 'all' && item.kind !== kind) return;
            // Hide the Atari-only legacy/HUD slots unless asked for; they are
            // never rendered on the Lynx.
            if (!item.used && !showUnused) return;
            if (filter && !item.label.toLowerCase().includes(filter) && !item.detail.includes(filter)) return;
            const button = document.createElement('button');
            button.className = 'tile-item' + (item.key === selectedKey ? ' active' : '');
            const canvas = document.createElement('canvas');
            canvas.width = 48; canvas.height = 48;
            drawEntry(canvas.getContext('2d'), item.entry, 0, 0, 6);
            const text = document.createElement('span');
            text.innerHTML = `${item.label}<span class="binding">${item.detail}</span>`;
            button.append(canvas, text);
            button.addEventListener('click', () => { selectedKey = item.key; renderAll(); });
            el.tileList.appendChild(button);
        });
    }

    function renderAll() {
        renderPalette();
        renderHeader();
        renderEditor();
        renderPreviews();
        renderLibrary();
    }

    // ----------------------------------------------------------------- edits

    function pixelAt(event) {
        const rect = el.editorCanvas.getBoundingClientRect();
        const x = Math.floor((event.clientX - rect.left) / rect.width * Model.TILE_W);
        const y = Math.floor((event.clientY - rect.top) / rect.height * Model.TILE_H);
        return { x, y };
    }

    function paint(event, isNewStroke) {
        const item = selected();
        if (!item) return;
        const { x, y } = pixelAt(event);
        if (x < 0 || x >= Model.TILE_W || y < 0 || y >= Model.TILE_H) return;
        // Only snapshot when a stroke actually changes something, so undo
        // steps map to edits rather than to mouse movements.
        if (Model.getPixel(item.entry, x, y) === activePen) return;
        if (isNewStroke) snapshot();
        if (Model.setPixel(item.entry, x, y, activePen)) {
            setDirty(true);
            renderEditor();
            renderPreviews();
            renderLibrary();
        }
    }

    function pickPen(event) {
        const item = selected();
        if (!item) return;
        const { x, y } = pixelAt(event);
        const pen = Model.getPixel(item.entry, x, y);
        if (pen >= 0) { activePen = pen; renderPalette(); }
    }

    function applyTransform(action) {
        const item = selected();
        if (!item) return;
        snapshot();
        Model.transform(item.entry, action);
        setDirty(true);
        renderAll();
    }

    // ------------------------------------------------------------- load/save

    function loadTileset(value, name) {
        try {
            Model.validateTileset(value);
        } catch (error) {
            window.alert(`That file is not a usable Lynx tileset.\n\n${error.message}`);
            return;
        }
        tileset = value;
        fileName = name || fileName;
        selectedKey = Model.entries(tileset)[0].key;
        undoStack.length = 0;
        redoStack.length = 0;
        updateUndoButtons();
        setDirty(false);
        renderAll();
    }

    function saveTileset() {
        if (!tileset) return;
        const text = JSON.stringify(tileset, null, 1) + '\n';
        const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = fileName;
        link.click();
        URL.revokeObjectURL(url);
        setDirty(false);
    }

    function wire() {
        el.loadTileset.addEventListener('click', () => el.tilesetInput.click());
        el.tilesetInput.addEventListener('change', event => {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = () => {
                try {
                    loadTileset(JSON.parse(reader.result), file.name);
                } catch (error) {
                    window.alert(`Could not parse that file as JSON.\n\n${error.message}`);
                }
            };
            reader.readAsText(file);
            event.target.value = '';
        });
        el.saveTileset.addEventListener('click', saveTileset);
        el.undo.addEventListener('click', () => stepHistory(undoStack, redoStack));
        el.redo.addEventListener('click', () => stepHistory(redoStack, undoStack));

        el.editorCanvas.addEventListener('mousedown', event => {
            if (event.button === 2) { pickPen(event); return; }
            painting = true;
            paint(event, true);
        });
        el.editorCanvas.addEventListener('mousemove', event => { if (painting) paint(event, false); });
        el.editorCanvas.addEventListener('contextmenu', event => event.preventDefault());
        window.addEventListener('mouseup', () => { painting = false; });

        document.querySelectorAll('[data-transform]').forEach(button => {
            button.addEventListener('click', () => applyTransform(button.dataset.transform));
        });
        el.libraryFilter.addEventListener('input', renderLibrary);
        el.libraryKind.addEventListener('change', renderLibrary);
        el.showUnused.addEventListener('change', renderLibrary);

        window.addEventListener('keydown', event => {
            if (event.target.tagName === 'INPUT' || event.target.tagName === 'SELECT') return;
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
                event.preventDefault();
                stepHistory(event.shiftKey ? redoStack : undoStack, event.shiftKey ? undoStack : redoStack);
                return;
            }
            const digit = parseInt(event.key, 16);
            if (!Number.isNaN(digit) && event.key.length === 1) { activePen = digit; renderPalette(); }
        });

        window.addEventListener('beforeunload', event => {
            if (dirty) { event.preventDefault(); event.returnValue = ''; }
        });
    }

    wire();
    renderAll();
})();
