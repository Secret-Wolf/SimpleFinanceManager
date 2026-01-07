// Categories Module

async function loadCategories() {
    const container = document.getElementById('categories-list');
    container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

    try {
        await loadCategoriesData();

        if (categories.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                    </svg>
                    <h3>Keine Kategorien</h3>
                    <p>Erstelle Standardkategorien oder füge eigene hinzu.</p>
                    <button class="btn btn-primary" onclick="initDefaultCategories()">Standardkategorien erstellen</button>
                </div>
            `;
            return;
        }

        container.innerHTML = renderCategoryTree(categories);

    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Fehler: ${error.message}</p></div>`;
    }
}

function renderCategoryTree(cats, level = 0) {
    let html = '';

    for (const cat of cats) {
        const paddingLeft = level * 24;

        html += `
            <div class="category-item ${level > 0 ? 'subcategory' : ''}" style="padding-left: ${16 + paddingLeft}px;" data-id="${cat.id}">
                <div class="color-dot" style="background-color: ${cat.color || '#888'}"></div>
                <span class="name">${cat.name}</span>
                <span class="count">${cat.transaction_count || 0}</span>
                <div class="actions">
                    <button class="btn btn-sm btn-icon" onclick="editCategory(${cat.id})" title="Bearbeiten">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                        </svg>
                    </button>
                    ${level === 0 ? `
                        <button class="btn btn-sm btn-icon" onclick="addSubcategory(${cat.id})" title="Unterkategorie hinzufügen">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="12" y1="5" x2="12" y2="19"></line>
                                <line x1="5" y1="12" x2="19" y2="12"></line>
                            </svg>
                        </button>
                    ` : ''}
                    <button class="btn btn-sm btn-icon" onclick="deleteCategory(${cat.id}, '${cat.name}')" title="Löschen">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>
                </div>
            </div>
        `;

        if (cat.children && cat.children.length > 0) {
            html += renderCategoryTree(cat.children, level + 1);
        }
    }

    return html;
}

function showAddCategoryModal() {
    document.getElementById('category-modal-title').textContent = 'Neue Kategorie';
    document.getElementById('category-form').reset();
    document.getElementById('category-id').value = '';
    document.getElementById('category-color').value = randomColor();

    // Update parent select
    document.getElementById('category-parent').innerHTML = `
        <option value="">Keine (Hauptkategorie)</option>
        ${categories.filter(c => !c.parent_id).map(c => `<option value="${c.id}">${c.name}</option>`).join('')}
    `;

    openModal('category-modal');
}

function addSubcategory(parentId) {
    const parent = flatCategories.find(c => c.id === parentId);
    if (!parent) return;

    document.getElementById('category-modal-title').textContent = `Unterkategorie zu "${parent.name}"`;
    document.getElementById('category-form').reset();
    document.getElementById('category-id').value = '';
    document.getElementById('category-color').value = adjustColor(parent.color || '#888888', -20);

    // Set parent
    document.getElementById('category-parent').innerHTML = `
        <option value="">Keine (Hauptkategorie)</option>
        ${categories.filter(c => !c.parent_id).map(c =>
            `<option value="${c.id}" ${c.id === parentId ? 'selected' : ''}>${c.name}</option>`
        ).join('')}
    `;

    openModal('category-modal');
}

async function editCategory(id) {
    const cat = flatCategories.find(c => c.id === id);
    if (!cat) return;

    document.getElementById('category-modal-title').textContent = 'Kategorie bearbeiten';
    document.getElementById('category-id').value = cat.id;
    document.getElementById('category-name').value = cat.name;
    document.getElementById('category-color').value = cat.color || '#888888';
    document.getElementById('category-budget').value = cat.budget_monthly || '';

    // Update parent select (exclude self and children)
    document.getElementById('category-parent').innerHTML = `
        <option value="">Keine (Hauptkategorie)</option>
        ${categories.filter(c => !c.parent_id && c.id !== id).map(c =>
            `<option value="${c.id}" ${c.id === cat.parent_id ? 'selected' : ''}>${c.name}</option>`
        ).join('')}
    `;

    openModal('category-modal');
}

async function saveCategory() {
    const id = document.getElementById('category-id').value;
    const name = document.getElementById('category-name').value.trim();
    const parentId = document.getElementById('category-parent').value;
    const color = document.getElementById('category-color').value;
    const budget = document.getElementById('category-budget').value;

    if (!name) {
        showToast('Bitte Namen eingeben', 'error');
        return;
    }

    const data = {
        name,
        parent_id: parentId ? parseInt(parentId) : null,
        color,
        budget_monthly: budget ? parseFloat(budget) : null
    };

    try {
        if (id) {
            await api.updateCategory(parseInt(id), data);
            showToast('Kategorie aktualisiert', 'success');
        } else {
            await api.createCategory(data);
            showToast('Kategorie erstellt', 'success');
        }

        closeModal('category-modal');
        loadCategories();
        initTransactionFilters();

    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function deleteCategory(id, name) {
    const cat = flatCategories.find(c => c.id === id);
    if (!cat) return;

    // Check if has transactions
    if (cat.transaction_count > 0) {
        // Show modal to choose what to do with transactions
        document.getElementById('delete-category-name').textContent = name;
        document.getElementById('delete-category-count').textContent = cat.transaction_count;
        document.getElementById('delete-category-id').value = id;

        // Update move-to select
        document.getElementById('delete-move-to').innerHTML = `
            <option value="">Keine (unkategorisiert)</option>
            ${flatCategories.filter(c => c.id !== id).map(c =>
                `<option value="${c.id}">${c.full_path || c.name}</option>`
            ).join('')}
        `;

        openModal('delete-category-modal');
        return;
    }

    // No transactions, simple confirm
    if (!confirm(`Kategorie "${name}" wirklich löschen?`)) return;

    try {
        await api.deleteCategory(id);
        showToast('Kategorie gelöscht', 'success');
        loadCategories();
        initTransactionFilters();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function confirmDeleteCategory() {
    const id = parseInt(document.getElementById('delete-category-id').value);
    const moveToId = document.getElementById('delete-move-to').value;

    try {
        await api.deleteCategory(id, moveToId ? parseInt(moveToId) : null);
        showToast('Kategorie gelöscht', 'success');
        closeModal('delete-category-modal');
        loadCategories();
        initTransactionFilters();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function initDefaultCategories() {
    try {
        await api.initDefaultCategories();
        showToast('Standardkategorien erstellt', 'success');
        loadCategories();
        initTransactionFilters();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}
