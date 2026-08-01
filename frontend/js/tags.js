// Tags Module (Schlagworte für Transaktionen, z.B. "Steuerrelevant")

let userTags = [];
let detailTags = []; // Tag-Zuweisung der aktuell im Detail-Modal geöffneten Transaktion

const TAG_COLOR_PALETTE = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316'];

async function loadTagsData() {
    try {
        userTags = await api.getTags();
    } catch (e) {
        userTags = [];
    }
    updateTagControls();
}

// Options/Datalist per DOM-API befüllen (escapeHtml escapt keine Quotes,
// Tag-Namen dürfen daher nie in HTML-Attribute interpoliert werden)
function updateTagControls() {
    const filter = document.getElementById('tx-tag-filter');
    if (filter) {
        const current = filter.value;
        filter.innerHTML = '';
        filter.appendChild(new Option('Alle Tags', ''));
        userTags.forEach(t => filter.appendChild(new Option(t.name, String(t.id))));
        filter.value = current; // Auswahl erhalten (fällt auf '' zurück, wenn Tag weg)
        if (filter.value !== current) filter.value = '';
    }

    const bulk = document.getElementById('bulk-tag');
    if (bulk) {
        bulk.innerHTML = '';
        bulk.appendChild(new Option('Tag wählen', ''));
        userTags.forEach(t => bulk.appendChild(new Option(t.name, String(t.id))));
    }

    const datalist = document.getElementById('tag-suggestions');
    if (datalist) {
        datalist.innerHTML = '';
        userTags.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.name;
            datalist.appendChild(opt);
        });
    }
}

function pickTagColor() {
    return TAG_COLOR_PALETTE[userTags.length % TAG_COLOR_PALETTE.length];
}

// Tag anhand des Namens finden oder neu anlegen (case-insensitive)
async function ensureTagByName(name) {
    const existing = userTags.find(t => t.name.toLowerCase() === name.toLowerCase());
    if (existing) return existing;
    const tag = await api.createTag({ name: name, color: pickTagColor() });
    await loadTagsData();
    return tag;
}

// Chip-Element bauen (Name als textContent — nie als HTML)
function buildTagChip(tag, options = {}) {
    const chip = document.createElement('span');
    chip.className = 'tag-chip' + (options.small ? ' tag-chip-sm' : '');
    chip.style.setProperty('--tag-color', safeColor(tag.color, '#10b981'));
    chip.appendChild(document.createTextNode(tag.name));
    if (options.removeAction) {
        const btn = document.createElement('button');
        btn.className = 'tag-chip-remove';
        btn.title = 'Entfernen';
        btn.textContent = '×';
        btn.dataset.action = options.removeAction;
        btn.dataset.id = String(tag.id);
        chip.appendChild(btn);
    }
    return chip;
}

// --- Tags im Transaktions-Detail-Modal ---------------------------------------

function renderDetailTags() {
    const box = document.getElementById('detail-tags-list');
    if (!box) return;
    box.innerHTML = '';
    if (detailTags.length === 0) {
        const empty = document.createElement('span');
        empty.className = 'tag-chips-empty';
        empty.textContent = 'Keine Tags';
        box.appendChild(empty);
        return;
    }
    detailTags.forEach(t => box.appendChild(buildTagChip(t, { removeAction: 'removeTagFromCurrentTransaction' })));
}

async function addTagToCurrentTransaction() {
    const input = document.getElementById('detail-tag-input');
    const name = input.value.trim();
    if (!name) return;

    try {
        const tag = await ensureTagByName(name);
        if (!detailTags.find(t => t.id === tag.id)) {
            detailTags.push(tag);
        }
        input.value = '';
        renderDetailTags();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

function removeTagFromCurrentTransaction(tagId) {
    detailTags = detailTags.filter(t => t.id !== tagId);
    renderDetailTags();
}

// --- Bulk-Zuweisung (Mehrfachauswahl in der Transaktionsliste) ---------------

async function bulkAssignTag() {
    const select = document.getElementById('bulk-tag');
    const tagId = select.value;
    if (!tagId) {
        showToast('Bitte Tag wählen', 'error');
        return;
    }
    if (selectedTransactions.size === 0) return;

    try {
        const result = await api.bulkTagTransactions([...selectedTransactions], parseInt(tagId));
        showToast(result.message, 'success');
        selectedTransactions.clear();
        updateBulkActions();
        loadTransactions();
        loadTagsData(); // Zähler aktualisieren
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

// --- Tags-Verwaltung (Modal) -------------------------------------------------

function showTagsModal() {
    document.getElementById('new-tag-name').value = '';
    renderTagsModalList();
    openModal('tags-modal');
    // Zähler im Hintergrund aktualisieren
    loadTagsData().then(renderTagsModalList);
}

function renderTagsModalList() {
    const box = document.getElementById('tags-modal-list');
    if (!box) return;
    box.innerHTML = '';

    if (userTags.length === 0) {
        const p = document.createElement('p');
        p.style.color = 'var(--text-secondary)';
        p.style.fontSize = '0.875rem';
        p.textContent = 'Noch keine Tags angelegt.';
        box.appendChild(p);
        return;
    }

    userTags.forEach(t => {
        const row = document.createElement('div');
        row.className = 'tag-row';

        row.appendChild(buildTagChip(t));

        const count = document.createElement('span');
        count.className = 'tag-row-count';
        count.textContent = `${t.transaction_count || 0} Transaktionen`;
        row.appendChild(count);

        const actions = document.createElement('span');
        actions.className = 'tag-row-actions';

        const renameBtn = document.createElement('button');
        renameBtn.className = 'btn btn-sm btn-secondary';
        renameBtn.textContent = 'Umbenennen';
        renameBtn.dataset.action = 'renameTag';
        renameBtn.dataset.id = String(t.id);
        actions.appendChild(renameBtn);

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn btn-sm btn-danger';
        deleteBtn.textContent = 'Löschen';
        deleteBtn.dataset.action = 'deleteTagConfirm';
        deleteBtn.dataset.id = String(t.id);
        actions.appendChild(deleteBtn);

        row.appendChild(actions);
        box.appendChild(row);
    });
}

async function createTagFromModal() {
    const input = document.getElementById('new-tag-name');
    const name = input.value.trim();
    if (!name) return;

    try {
        await api.createTag({ name: name, color: pickTagColor() });
        input.value = '';
        await loadTagsData();
        renderTagsModalList();
        showToast('Tag angelegt', 'success');
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function renameTag(tagId) {
    const tag = userTags.find(t => t.id === tagId);
    if (!tag) return;

    const name = prompt('Neuer Name für das Tag:', tag.name);
    if (!name || !name.trim() || name.trim() === tag.name) return;

    try {
        await api.updateTag(tagId, { name: name.trim() });
        await loadTagsData();
        renderTagsModalList();
        showToast('Tag umbenannt', 'success');
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function deleteTagConfirm(tagId) {
    const tag = userTags.find(t => t.id === tagId);
    if (!tag) return;

    const count = tag.transaction_count || 0;
    const hint = count > 0 ? `\n\nDie Zuweisung zu ${count} Transaktionen wird entfernt; die Transaktionen selbst bleiben erhalten.` : '';
    if (!confirm(`Tag "${tag.name}" löschen?${hint}`)) return;

    try {
        await api.deleteTag(tagId);
        await loadTagsData();
        renderTagsModalList();
        showToast('Tag gelöscht', 'success');
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}
