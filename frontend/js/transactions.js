// Transactions Module

let transactionFilters = {
    page: 1,
    per_page: 50,
    sort_by: 'booking_date',
    sort_order: 'desc',
    search: '',
    start_date: '',
    end_date: '',
    category_id: '',
    amount_type: '',
    uncategorized_only: false
};

let selectedTransactions = new Set();

async function loadTransactions() {
    const container = document.getElementById('transactions-table');
    const paginationContainer = document.getElementById('transactions-pagination');

    container.innerHTML = '<tr><td colspan="6"><div class="loading-overlay"><div class="spinner"></div></div></td></tr>';

    try {
        const params = { ...transactionFilters };
        if (!params.search) delete params.search;
        if (!params.start_date) delete params.start_date;
        if (!params.end_date) delete params.end_date;
        if (!params.category_id) delete params.category_id;
        if (!params.amount_type) delete params.amount_type;

        // Add account filter if selected
        if (selectedAccountId) {
            params.account_id = selectedAccountId;
        }

        const result = await api.getTransactions(params);

        if (result.items.length === 0) {
            container.innerHTML = `
                <tr>
                    <td colspan="6">
                        <div class="empty-state">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path>
                                <polyline points="13 2 13 9 20 9"></polyline>
                            </svg>
                            <h3>Keine Transaktionen</h3>
                            <p>Importiere eine CSV-Datei, um zu beginnen.</p>
                            <button class="btn btn-primary" onclick="navigateTo('import')">CSV importieren</button>
                        </div>
                    </td>
                </tr>
            `;
            paginationContainer.innerHTML = '';
            return;
        }

        container.innerHTML = result.items.map(tx => `
            <tr data-id="${tx.id}">
                <td>
                    <input type="checkbox" class="checkbox tx-checkbox" data-id="${tx.id}"
                        ${selectedTransactions.has(tx.id) ? 'checked' : ''}>
                </td>
                <td>${formatDate(tx.booking_date)}</td>
                <td>
                    <div>${truncate(tx.counterpart_name || tx.booking_type || '-', 35)}</div>
                    <div style="font-size: 0.75rem; color: var(--text-muted)">${truncate(tx.purpose || '', 50)}</div>
                </td>
                <td>
                    <select class="form-control category-select" data-id="${tx.id}" style="min-width: 150px;">
                        <option value="">Unkategorisiert</option>
                        ${generateCategoryOptions(categories, tx.category_id)}
                    </select>
                </td>
                <td class="text-right amount ${tx.amount >= 0 ? 'positive' : 'negative'}">
                    ${formatCurrency(tx.amount)}
                </td>
                <td>
                    <button class="btn btn-sm btn-icon" onclick="showTransactionDetails(${tx.id})" title="Details">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="12" y1="16" x2="12" y2="12"></line>
                            <line x1="12" y1="8" x2="12.01" y2="8"></line>
                        </svg>
                    </button>
                </td>
            </tr>
        `).join('');

        // Set up category change handlers
        container.querySelectorAll('.category-select').forEach(select => {
            select.addEventListener('change', async (e) => {
                const id = parseInt(e.target.dataset.id);
                const categoryId = e.target.value ? parseInt(e.target.value) : 0;

                try {
                    await api.updateTransaction(id, { category_id: categoryId });
                    showToast('Kategorie aktualisiert', 'success');
                } catch (error) {
                    showToast('Fehler: ' + error.message, 'error');
                    loadTransactions();
                }
            });
        });

        // Set up checkbox handlers
        container.querySelectorAll('.tx-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const id = parseInt(e.target.dataset.id);
                if (e.target.checked) {
                    selectedTransactions.add(id);
                } else {
                    selectedTransactions.delete(id);
                }
                updateBulkActions();
            });
        });

        // Pagination
        renderPagination(paginationContainer, result);

    } catch (error) {
        container.innerHTML = `<tr><td colspan="6" class="text-center">Fehler: ${error.message}</td></tr>`;
    }
}

function renderPagination(container, result) {
    if (result.pages <= 1) {
        container.innerHTML = '';
        return;
    }

    let html = '<div class="pagination">';

    // Previous button
    html += `<button ${result.page === 1 ? 'disabled' : ''} onclick="changePage(${result.page - 1})">←</button>`;

    // Page numbers
    const maxVisible = 5;
    let start = Math.max(1, result.page - Math.floor(maxVisible / 2));
    let end = Math.min(result.pages, start + maxVisible - 1);

    if (end - start < maxVisible - 1) {
        start = Math.max(1, end - maxVisible + 1);
    }

    if (start > 1) {
        html += `<button onclick="changePage(1)">1</button>`;
        if (start > 2) html += '<span style="padding: 8px">...</span>';
    }

    for (let i = start; i <= end; i++) {
        html += `<button class="${i === result.page ? 'active' : ''}" onclick="changePage(${i})">${i}</button>`;
    }

    if (end < result.pages) {
        if (end < result.pages - 1) html += '<span style="padding: 8px">...</span>';
        html += `<button onclick="changePage(${result.pages})">${result.pages}</button>`;
    }

    // Next button
    html += `<button ${result.page === result.pages ? 'disabled' : ''} onclick="changePage(${result.page + 1})">→</button>`;

    html += '</div>';
    html += `<div class="text-center mt-4" style="color: var(--text-secondary); font-size: 0.875rem;">
        ${result.total} Transaktionen
    </div>`;

    container.innerHTML = html;
}

function changePage(page) {
    transactionFilters.page = page;
    loadTransactions();
}

function applyTransactionFilters() {
    const search = document.getElementById('tx-search').value;
    const startDate = document.getElementById('tx-start-date').value;
    const endDate = document.getElementById('tx-end-date').value;
    const category = document.getElementById('tx-category-filter').value;
    const amountType = document.getElementById('tx-amount-type').value;
    const uncategorized = document.getElementById('uncategorized-filter').checked;

    transactionFilters = {
        ...transactionFilters,
        page: 1,
        search,
        start_date: startDate,
        end_date: endDate,
        category_id: category,
        amount_type: amountType,
        uncategorized_only: uncategorized
    };

    loadTransactions();
}

function setQuickPeriod(period) {
    const dates = getPeriodDates(period);
    document.getElementById('tx-start-date').value = dates.start;
    document.getElementById('tx-end-date').value = dates.end;
    applyTransactionFilters();
}

function updateBulkActions() {
    const bulkBar = document.getElementById('bulk-actions');
    const countEl = document.getElementById('selected-count');

    if (selectedTransactions.size > 0) {
        bulkBar.classList.remove('hidden');
        countEl.textContent = selectedTransactions.size;
    } else {
        bulkBar.classList.add('hidden');
    }
}

async function bulkCategorize() {
    const categoryId = document.getElementById('bulk-category').value;
    if (!categoryId) {
        showToast('Bitte Kategorie auswählen', 'error');
        return;
    }

    try {
        await api.bulkCategorize([...selectedTransactions], parseInt(categoryId));
        showToast(`${selectedTransactions.size} Transaktionen kategorisiert`, 'success');
        selectedTransactions.clear();
        updateBulkActions();
        loadTransactions();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

function selectAllTransactions() {
    const checkboxes = document.querySelectorAll('.tx-checkbox');
    const allChecked = [...checkboxes].every(cb => cb.checked);

    checkboxes.forEach(cb => {
        const id = parseInt(cb.dataset.id);
        if (allChecked) {
            cb.checked = false;
            selectedTransactions.delete(id);
        } else {
            cb.checked = true;
            selectedTransactions.add(id);
        }
    });

    updateBulkActions();
}

async function showTransactionDetails(id) {
    try {
        const tx = await api.getTransaction(id);

        document.getElementById('detail-date').textContent = formatDate(tx.booking_date);
        document.getElementById('detail-counterpart').textContent = tx.counterpart_name || '-';
        document.getElementById('detail-iban').textContent = tx.counterpart_iban || '-';
        document.getElementById('detail-type').textContent = tx.booking_type || '-';
        document.getElementById('detail-purpose').textContent = tx.purpose || '-';
        document.getElementById('detail-amount').textContent = formatCurrency(tx.amount);
        document.getElementById('detail-amount').className = `amount ${tx.amount >= 0 ? 'positive' : 'negative'}`;

        // Notes
        const notesInput = document.getElementById('detail-notes');
        notesInput.value = tx.notes || '';
        notesInput.dataset.id = tx.id;

        // Split button
        const splitBtn = document.getElementById('split-btn');
        if (tx.is_split_parent || tx.parent_transaction_id) {
            splitBtn.classList.add('hidden');
        } else {
            splitBtn.classList.remove('hidden');
            splitBtn.onclick = () => showSplitModal(tx);
        }

        // Create rule button
        document.getElementById('create-rule-btn').onclick = () => showCreateRuleModal(tx);

        openModal('transaction-detail-modal');

    } catch (error) {
        showToast('Fehler beim Laden: ' + error.message, 'error');
    }
}

async function saveTransactionNotes() {
    const notesInput = document.getElementById('detail-notes');
    const id = parseInt(notesInput.dataset.id);
    const notes = notesInput.value;

    try {
        await api.updateTransaction(id, { notes });
        showToast('Notiz gespeichert', 'success');
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

// Split Transaction Modal
function showSplitModal(tx) {
    closeModal('transaction-detail-modal');

    document.getElementById('split-original-amount').textContent = formatCurrency(Math.abs(tx.amount));
    document.getElementById('split-transaction-id').value = tx.id;

    // Reset split parts
    const container = document.getElementById('split-parts');
    container.innerHTML = '';
    addSplitPart();

    updateSplitRemaining();
    openModal('split-modal');
}

function addSplitPart() {
    const container = document.getElementById('split-parts');
    const index = container.children.length;

    const part = document.createElement('div');
    part.className = 'split-part';
    part.style.cssText = 'display: flex; gap: 12px; margin-bottom: 12px; align-items: center;';
    part.innerHTML = `
        <input type="number" step="0.01" class="form-control split-amount" placeholder="Betrag" style="width: 120px;" oninput="updateSplitRemaining()">
        <select class="form-control split-category" style="flex: 1;">
            <option value="">Kategorie wählen</option>
            ${generateCategoryOptions(categories)}
        </select>
        <button class="btn btn-icon btn-danger" onclick="this.parentElement.remove(); updateSplitRemaining();" title="Entfernen">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
        </button>
    `;

    container.appendChild(part);
}

function updateSplitRemaining() {
    const originalText = document.getElementById('split-original-amount').textContent;
    const original = parseFloat(originalText.replace(/[^\d,-]/g, '').replace(',', '.')) || 0;

    let total = 0;
    document.querySelectorAll('.split-amount').forEach(input => {
        total += parseFloat(input.value) || 0;
    });

    const remaining = original - total;
    document.getElementById('split-remaining').textContent = formatCurrency(remaining);
    document.getElementById('split-remaining').style.color = Math.abs(remaining) < 0.01 ? 'var(--success-color)' : 'var(--danger-color)';
}

async function saveSplit() {
    const txId = parseInt(document.getElementById('split-transaction-id').value);

    const parts = [];
    const partElements = document.querySelectorAll('.split-part');

    for (const el of partElements) {
        const amount = parseFloat(el.querySelector('.split-amount').value);
        const categoryId = parseInt(el.querySelector('.split-category').value);

        if (!amount || !categoryId) {
            showToast('Bitte alle Felder ausfüllen', 'error');
            return;
        }

        parts.push({ amount, category_id: categoryId });
    }

    if (parts.length < 2) {
        showToast('Mindestens 2 Teile erforderlich', 'error');
        return;
    }

    try {
        await api.splitTransaction(txId, parts);
        showToast('Transaktion aufgeteilt', 'success');
        closeModal('split-modal');
        loadTransactions();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

// Create Rule Modal
function showCreateRuleModal(tx) {
    closeModal('transaction-detail-modal');

    document.getElementById('rule-from-tx-id').value = tx.id;
    document.getElementById('rule-preview-name').textContent = tx.counterpart_name || '-';
    document.getElementById('rule-preview-iban').textContent = tx.counterpart_iban || '-';
    document.getElementById('rule-preview-purpose').textContent = truncate(tx.purpose || '-', 50);

    // Reset category select
    document.getElementById('rule-category').innerHTML = `
        <option value="">Kategorie wählen</option>
        ${generateCategoryOptions(categories)}
    `;

    openModal('create-rule-modal');
}

async function saveRuleFromTransaction() {
    const txId = parseInt(document.getElementById('rule-from-tx-id').value);
    const categoryId = parseInt(document.getElementById('rule-category').value);
    const matchType = document.getElementById('rule-match-type').value;

    if (!categoryId) {
        showToast('Bitte Kategorie wählen', 'error');
        return;
    }

    try {
        await api.createRuleFromTransaction(txId, categoryId, matchType);
        showToast('Regel erstellt', 'success');
        closeModal('create-rule-modal');

        // Categorize this transaction
        await api.updateTransaction(txId, { category_id: categoryId });
        loadTransactions();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

// Manual Entry Modal
function showManualEntryModal() {
    // Reset form
    document.getElementById('manual-entry-form').reset();

    // Set default date to today
    document.getElementById('manual-date').value = formatDateInput(new Date());

    // Set default type to expense
    document.getElementById('manual-type-expense').checked = true;

    // Populate category select
    document.getElementById('manual-category').innerHTML = `
        <option value="">Keine Kategorie</option>
        ${generateCategoryOptions(categories)}
    `;

    openModal('manual-entry-modal');
}

async function saveManualEntry() {
    const bookingDate = document.getElementById('manual-date').value;
    const amountInput = parseFloat(document.getElementById('manual-amount').value);
    const description = document.getElementById('manual-description').value.trim();
    const categoryId = document.getElementById('manual-category').value;
    const notes = document.getElementById('manual-notes').value.trim();
    const isIncome = document.getElementById('manual-type-income').checked;

    // Validation
    if (!bookingDate) {
        showToast('Bitte Datum eingeben', 'error');
        return;
    }

    if (!amountInput || amountInput <= 0) {
        showToast('Bitte gültigen Betrag eingeben', 'error');
        return;
    }

    if (!description) {
        showToast('Bitte Beschreibung eingeben', 'error');
        return;
    }

    // Amount: positive for income, negative for expense
    const amount = isIncome ? amountInput : -amountInput;

    const data = {
        booking_date: bookingDate,
        amount: amount,
        description: description,
        category_id: categoryId ? parseInt(categoryId) : null,
        notes: notes || null
    };

    try {
        await api.createManualTransaction(data);
        showToast('Eintrag erstellt', 'success');
        closeModal('manual-entry-modal');
        loadTransactions();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

