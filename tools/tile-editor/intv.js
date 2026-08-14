(function () {
    'use strict';
    const Model = globalThis.FujiRealmIntv;
    const EDITOR_SCALE = 64;   // 8x8 card drawn at 512x512
    const TILED_SCALE = 8;     // 3x3 neighbour preview
    const UNDO_LIMIT = 60;
    const BACKGROUND = '#000000';   // the colour stack is all black on this target

    const ids = [
        'project-input', 'load-project', 'save-project', 'import-bitmap', 'export-bitmap',
        'undo', 'redo', 'dirty-indicator', 'palette', 'active-color-label', 'tiled-canvas',
        'actual-canvas', 'card-word', 'gram-budget', 'entry-name', 'entry-binding',
        'editor-canvas', 'empty-state', 'library-filter', 'library-kind', 'tile-list',
        'bitmap-dialog', 'bitmap-title', 'bitmap-hint', 'bitmap-text', 'bitmap-apply',
        'message-dialog', 'message-text',
    ];
    const el = {};
    ids.forEach(id => { el[id.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = document.getElementById(id); });

    let project = null;
    let fileName = 'intv_cards.json';
    let selectedKey = null;
    let dirty = false;
    let painting = 0;          // 0 = not painting, 1 = setting, -1 = clearing
    const undoStack = [];
    const redoStack = [];

    function selected() { return project && selectedKey ? Model.findEntry(project, selectedKey) : null; }

    function showMessage(text) {
        el.messageText.textContent = text;
        el.messageDialog.showModal();
    }

    function setDirty(value) {
        dirty = value;
        el.dirtyIndicator.hidden = !value;
    }

    function snapshot() {
        if (!project) return;
        undoStack.push(Model.cloneState(project));
        if (undoStack.length > UNDO_LIMIT) undoStack.shift();
        redoStack.length = 0;
        updateUndoButtons();
    }

    function updateUndoButtons() {
        el.undo.disabled = !undoStack.length;
        el.redo.disabled = !redoStack.length;
    }

    function stepHistory(from, to) {
        if (!project || !from.length) return;
        to.push(Model.cloneState(project));
        Model.restoreState(project, from.pop());
        updateUndoButtons();
        setDirty(true);
        renderAll();
    }

    // ---------------------------------------------------------------- render

    function palette() { return project ? project.palette : []; }

    function colorName(index) {
        const names = project && project.colorNames;
        return names && names[index] ? names[index] : `colour ${index}`;
    }

    // Every set pixel is the card's one colour; every clear pixel is the black
    // background. That is the whole of Intellivision colour in one function.
    function drawEntry(ctx, entry, x, y, scale) {
        const fg = palette()[entry.color] || '#FFFFFF';
        ctx.fillStyle = BACKGROUND;
        ctx.fillRect(x, y, Model.CARD_W * scale, Model.CARD_H * scale);
        ctx.fillStyle = fg;
        for (let py = 0; py < Model.CARD_H; py++) {
            for (let px = 0; px < Model.CARD_W; px++) {
                if (Model.getPixel(entry, px, py)) ctx.fillRect(x + px * scale, y + py * scale, scale, scale);
            }
        }
    }

    function renderPalette() {
        el.palette.replaceChildren();
        const item = selected();
        palette().forEach((colour, index) => {
            const button = document.createElement('button');
            const active = item && item.entry.color === index;
            button.className = 'swatch' + (active ? ' active' : '');
            button.style.background = colour;
            if (index === Model.BACKGROUND_COLOR) {
                button.disabled = true;
                button.title = `${colorName(index)} — the background; a card in it would be invisible`;
            } else {
                button.title = `${colorName(index)} (${index}) — ${colour}`;
                button.addEventListener('click', () => applyColor(index));
            }
            el.palette.appendChild(button);
        });
        el.activeColorLabel.textContent = item ? `${colorName(item.entry.color)} (${item.entry.color})` : '';
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
        // A grid, brightened every 4 pixels so the card's centre is findable.
        for (let i = 0; i <= Model.CARD_W; i++) {
            ctx.strokeStyle = i % 4 === 0 ? 'rgba(255,255,255,0.35)' : 'rgba(255,255,255,0.12)';
            ctx.beginPath();
            ctx.moveTo(i * EDITOR_SCALE + 0.5, 0);
            ctx.lineTo(i * EDITOR_SCALE + 0.5, Model.CARD_H * EDITOR_SCALE);
            ctx.moveTo(0, i * EDITOR_SCALE + 0.5);
            ctx.lineTo(Model.CARD_W * EDITOR_SCALE, i * EDITOR_SCALE + 0.5);
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
        if (!item) { el.cardWord.textContent = ''; el.gramBudget.textContent = ''; return; }
        for (let ty = 0; ty < 3; ty++) {
            for (let tx = 0; tx < 3; tx++) {
                drawEntry(tiled, item.entry, tx * Model.CARD_W * TILED_SCALE, ty * Model.CARD_H * TILED_SCALE, TILED_SCALE);
            }
        }
        drawEntry(actual, item.entry, 0, 0, 1);
        el.cardWord.textContent = `BACKTAB word ${Model.hexWord(Model.backtabWord(item.entry))}`;
        el.gramBudget.textContent = `GRAM ${Model.CARD_COUNT}/${Model.GRAM_CAPACITY} cards`;
    }

    function renderHeader() {
        const item = selected();
        el.entryName.textContent = item ? item.label : 'No card selected';
        el.entryBinding.textContent = item ? item.detail : '';
    }

    function renderLibrary() {
        if (!project) { el.tileList.replaceChildren(); return; }
        const filter = el.libraryFilter.value.trim().toLowerCase();
        const kind = el.libraryKind.value;
        el.tileList.replaceChildren();
        Model.entries(project).forEach(item => {
            if (kind !== 'all' && item.kind !== kind) return;
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
        const x = Math.floor((event.clientX - rect.left) / rect.width * Model.CARD_W);
        const y = Math.floor((event.clientY - rect.top) / rect.height * Model.CARD_H);
        return { x, y };
    }

    function paint(event, value, isNewStroke) {
        const item = selected();
        if (!item) return;
        const { x, y } = pixelAt(event);
        if (x < 0 || x >= Model.CARD_W || y < 0 || y >= Model.CARD_H) return;
        // Only snapshot when a stroke actually changes something, so undo steps
        // map to edits rather than to mouse movements.
        if (Model.getPixel(item.entry, x, y) === value) return;
        if (isNewStroke) snapshot();
        if (Model.setPixel(item.entry, x, y, value)) {
            setDirty(true);
            renderEditor();
            renderPreviews();
            renderLibrary();
        }
    }

    function applyColor(index) {
        const item = selected();
        if (!item || item.entry.color === index) return;
        snapshot();
        Model.setColor(item.entry, index);
        setDirty(true);
        renderAll();
    }

    function applyTransform(action) {
        const item = selected();
        if (!item) return;
        snapshot();
        Model.transform(item.entry, action);
        setDirty(true);
        renderAll();
    }

    // ------------------------------------------------- BITMAP interchange

    let bitmapMode = null;

    function openImport() {
        const item = selected();
        if (!item) return;
        bitmapMode = 'import';
        el.bitmapTitle.textContent = `Import BITMAP into ${item.label}`;
        el.bitmapHint.textContent = 'Paste 8 rows, as BITMAP "…" lines or bare rows of # and . (1 and 0 also work).';
        el.bitmapText.value = '';
        el.bitmapText.readOnly = false;
        el.bitmapApply.hidden = false;
        el.bitmapDialog.showModal();
    }

    function openExport() {
        const item = selected();
        if (!item || !project) return;
        bitmapMode = 'export';
        el.bitmapTitle.textContent = 'BITMAP text';
        el.bitmapHint.textContent = 'The selected card, then every card, in the notation gfx.bas uses.';
        const all = Model.entries(project)
            .map(other => `' GRAM ${other.entry.index} <- ${other.label}\n${Model.toBitmapText(other.entry)}`)
            .join('\n');
        el.bitmapText.value = `' ${item.label}\n${Model.toBitmapText(item.entry)}\n\n' --- all ${Model.CARD_COUNT} cards ---\n${all}\n`;
        el.bitmapText.readOnly = true;
        el.bitmapApply.hidden = true;
        el.bitmapDialog.showModal();
        el.bitmapText.select();
    }

    function applyBitmap() {
        const item = selected();
        if (!item || bitmapMode !== 'import') return;
        let rows;
        try {
            rows = Model.fromBitmapText(el.bitmapText.value);
        } catch (error) {
            showMessage(`That is not a usable BITMAP block.\n\n${error.message}`);
            return;
        }
        snapshot();
        item.entry.rows = rows;
        setDirty(true);
        renderAll();
    }

    // ------------------------------------------------------------- load/save

    function loadProject(value, name) {
        try {
            Model.validateProject(value);
        } catch (error) {
            showMessage(`That file is not a usable Intellivision card project.\n\n${error.message}`);
            return;
        }
        project = value;
        fileName = name || fileName;
        selectedKey = Model.entries(project)[0].key;
        undoStack.length = 0;
        redoStack.length = 0;
        updateUndoButtons();
        setDirty(false);
        renderAll();
    }

    function saveProject() {
        if (!project) return;
        const text = JSON.stringify(project, null, 1) + '\n';
        const url = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = fileName;
        link.click();
        URL.revokeObjectURL(url);
        setDirty(false);
    }

    function wire() {
        el.loadProject.addEventListener('click', () => el.projectInput.click());
        el.projectInput.addEventListener('change', event => {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = () => {
                try {
                    loadProject(JSON.parse(reader.result), file.name);
                } catch (error) {
                    showMessage(`Could not parse that file as JSON.\n\n${error.message}`);
                }
            };
            reader.readAsText(file);
            event.target.value = '';
        });
        el.saveProject.addEventListener('click', saveProject);
        el.importBitmap.addEventListener('click', openImport);
        el.exportBitmap.addEventListener('click', openExport);
        el.bitmapDialog.addEventListener('close', () => {
            if (el.bitmapDialog.returnValue === 'apply') applyBitmap();
        });
        el.undo.addEventListener('click', () => stepHistory(undoStack, redoStack));
        el.redo.addEventListener('click', () => stepHistory(redoStack, undoStack));

        el.editorCanvas.addEventListener('mousedown', event => {
            painting = event.button === 2 ? -1 : 1;
            paint(event, painting > 0 ? 1 : 0, true);
        });
        el.editorCanvas.addEventListener('mousemove', event => {
            if (painting) paint(event, painting > 0 ? 1 : 0, false);
        });
        el.editorCanvas.addEventListener('contextmenu', event => event.preventDefault());
        window.addEventListener('mouseup', () => { painting = 0; });

        document.querySelectorAll('[data-transform]').forEach(button => {
            button.addEventListener('click', () => applyTransform(button.dataset.transform));
        });
        el.libraryFilter.addEventListener('input', renderLibrary);
        el.libraryKind.addEventListener('change', renderLibrary);

        window.addEventListener('keydown', event => {
            if (event.target.tagName === 'INPUT' || event.target.tagName === 'SELECT'
                || event.target.tagName === 'TEXTAREA') return;
            if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
                event.preventDefault();
                stepHistory(event.shiftKey ? redoStack : undoStack, event.shiftKey ? undoStack : redoStack);
                return;
            }
            if (event.key === ' ') { event.preventDefault(); applyTransform('invert'); }
        });

        window.addEventListener('beforeunload', event => {
            if (dirty) { event.preventDefault(); event.returnValue = ''; }
        });
    }

    wire();
    renderAll();
})();
