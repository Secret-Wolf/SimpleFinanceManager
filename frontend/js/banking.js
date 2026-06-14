// Online Banking (FinTS) Module

// Transient state for the current TAN flow (never persisted)
let _tanFlow = { connectionId: null, jobId: null, decoupled: false };
let _lastUrlSuggestion = '';
let _bankSuggestions = [];  // last bank-search results (for index-based selection)

// Suggest a FinTS endpoint based on the Bankleitzahl (editable by the user)
function suggestFintsUrl(blz) {
    blz = (blz || '').trim();
    if (blz === '50010517') return 'https://fints.ing.de/fints/';
    // Volksbanken/Raiffeisenbanken run via Atruvia; fints2 (Süd) is the common default,
    // some regions use fints1 (Nord). User can adjust.
    if (blz.length === 8) return 'https://fints2.atruvia.de/cgi-bin/hbciservlet';
    return '';
}

async function loadBanking() {
    const container = document.getElementById('banking-content');
    container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

    try {
        const connections = await api.getBankConnections();

        if (!connections || connections.length === 0) {
            container.innerHTML = `
                <div class="card" style="text-align: center; padding: 40px;">
                    <h3 style="margin-bottom: 8px;">Noch keine Bankverbindung</h3>
                    <p style="color: var(--text-secondary); margin-bottom: 16px;">
                        Lege eine FinTS-Verbindung an, um Umsätze direkt von deiner Bank abzurufen –
                        ganz ohne CSV-Export.
                    </p>
                    <button class="btn btn-primary" data-action="showAddConnectionModal">Verbindung hinzufügen</button>
                </div>`;
            return;
        }

        container.innerHTML = `
            <div class="accounts-grid">
                ${connections.map(c => `
                    <div class="card bank-conn-card">
                        <div class="conn-top">
                            <span class="bank-icon">${getBankIcon(c.name)}</span>
                            <span class="conn-name">${escapeHtml(c.name)}</span>
                            <span class="conn-badge">FinTS</span>
                        </div>
                        <div class="conn-meta">BLZ ${escapeHtml(c.bank_code)} · ${escapeHtml(c.login_name)}</div>
                        <div class="conn-foot">
                            <div class="conn-lastsync">
                                <span class="conn-lastsync-label">Letzter Abruf</span>
                                ${c.last_sync ? escapeHtml(formatDate(c.last_sync)) : 'nie'}
                            </div>
                            <div class="card-actions">
                                <button class="btn btn-primary btn-sm" data-action="startBankSync" data-id="${c.id}">Umsätze abrufen</button>
                                <button class="btn btn-secondary btn-sm" data-action="deleteBankConnectionConfirm" data-id="${c.id}" data-value="${escapeHtml(c.name)}">Löschen</button>
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>`;

    } catch (error) {
        container.innerHTML = `<div class="card"><p style="color: var(--danger-color)">Fehler: ${escapeHtml(error.message)}</p></div>`;
    }
}

// --- Add connection ----------------------------------------------------------

function showAddConnectionModal() {
    document.getElementById('bank-conn-search').value = '';
    document.getElementById('bank-conn-name').value = '';
    document.getElementById('bank-conn-blz').value = '';
    document.getElementById('bank-conn-login').value = '';
    document.getElementById('bank-conn-url').value = '';
    document.getElementById('bank-conn-error').textContent = '';
    hideBankSearchResults();
    _lastUrlSuggestion = '';

    // Attach BLZ -> URL suggestion once
    const blzInput = document.getElementById('bank-conn-blz');
    if (!blzInput.dataset.bound) {
        blzInput.addEventListener('input', () => {
            const urlInput = document.getElementById('bank-conn-url');
            // Only auto-fill if the user hasn't typed their own URL
            if (urlInput.value === '' || urlInput.value === _lastUrlSuggestion) {
                const suggestion = suggestFintsUrl(blzInput.value);
                if (suggestion) {
                    urlInput.value = suggestion;
                    _lastUrlSuggestion = suggestion;
                }
            }
        });
        blzInput.dataset.bound = '1';
    }

    openModal('bank-connection-modal');
}

// --- Bank search (Name/Ort/BLZ -> BLZ + FinTS-URL) ---------------------------

function hideBankSearchResults() {
    const box = document.getElementById('bank-search-results');
    box.innerHTML = '';
    box.classList.add('hidden');
    _bankSuggestions = [];
}

async function onBankSearchInput() {
    const query = document.getElementById('bank-conn-search').value.trim();
    const box = document.getElementById('bank-search-results');

    if (query.length < 2) {
        hideBankSearchResults();
        return;
    }

    try {
        const results = await api.searchBanks(query);
        _bankSuggestions = results;

        if (!results || results.length === 0) {
            box.innerHTML = '<div class="bank-search-empty">Keine Bank gefunden – BLZ und FinTS-URL bitte manuell eingeben.</div>';
            box.classList.remove('hidden');
            return;
        }

        box.innerHTML = results.map((b, i) => `
            <div class="bank-search-result" data-action="selectBankSuggestion" data-id="${i}">
                <div class="bank-search-name">${escapeHtml(b.name)}</div>
                <div class="bank-search-meta">${escapeHtml(b.ort)} · BLZ ${escapeHtml(b.blz)}</div>
            </div>
        `).join('');
        box.classList.remove('hidden');
    } catch (error) {
        hideBankSearchResults();
    }
}

function selectBankSuggestion(index) {
    const bank = _bankSuggestions[index];
    if (!bank) return;

    document.getElementById('bank-conn-blz').value = bank.blz;
    document.getElementById('bank-conn-url').value = bank.url;
    _lastUrlSuggestion = bank.url;

    // Pre-fill the connection name only if the user hasn't typed one yet
    const nameInput = document.getElementById('bank-conn-name');
    if (!nameInput.value.trim()) {
        nameInput.value = bank.name;
    }

    document.getElementById('bank-conn-search').value = bank.name;
    hideBankSearchResults();
    document.getElementById('bank-conn-login').focus();
}

async function saveBankConnection() {
    const errorEl = document.getElementById('bank-conn-error');
    errorEl.textContent = '';

    const data = {
        name: document.getElementById('bank-conn-name').value.trim(),
        bank_code: document.getElementById('bank-conn-blz').value.trim(),
        login_name: document.getElementById('bank-conn-login').value.trim(),
        fints_url: document.getElementById('bank-conn-url').value.trim(),
    };

    if (!data.name || !data.bank_code || !data.login_name || !data.fints_url) {
        errorEl.textContent = 'Bitte alle Felder ausfüllen.';
        return;
    }

    try {
        await api.createBankConnection(data);
        closeModal('bank-connection-modal');
        showToast('Bankverbindung gespeichert', 'success');
        loadBanking();
    } catch (error) {
        errorEl.textContent = error.message;
    }
}

async function deleteBankConnectionConfirm(id, name) {
    if (!confirm(`Bankverbindung "${name}" löschen? Bereits importierte Umsätze bleiben erhalten.`)) return;
    try {
        await api.deleteBankConnection(id);
        showToast('Bankverbindung gelöscht', 'success');
        loadBanking();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

// --- Sync (PIN -> maybe TAN) -------------------------------------------------

function startBankSync(id) {
    document.getElementById('bank-sync-connection-id').value = id;
    document.getElementById('bank-sync-pin').value = '';
    document.getElementById('bank-pin-error').textContent = '';

    // Default "from" date = 90 days ago
    const d = new Date();
    d.setDate(d.getDate() - 90);
    document.getElementById('bank-sync-from').value = formatDateInput(d);

    openModal('bank-pin-modal');
}

async function confirmBankSync() {
    const connectionId = parseInt(document.getElementById('bank-sync-connection-id').value);
    const pin = document.getElementById('bank-sync-pin').value;
    const fromDate = document.getElementById('bank-sync-from').value || null;
    const errorEl = document.getElementById('bank-pin-error');
    errorEl.textContent = '';

    if (!pin) {
        errorEl.textContent = 'Bitte PIN eingeben.';
        return;
    }

    const btn = document.querySelector('#bank-pin-modal [data-action="confirmBankSync"]');
    btn.disabled = true;
    btn.textContent = 'Verbinde...';

    try {
        const result = await api.syncBankConnection(connectionId, pin, fromDate);
        closeModal('bank-pin-modal');
        handleSyncResult(result, connectionId);
    } catch (error) {
        errorEl.textContent = error.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Abrufen';
    }
}

function handleSyncResult(result, connectionId) {
    if (result.status === 'error') {
        showToast(result.message || 'Abruf fehlgeschlagen', 'error');
        return;
    }

    if (result.status === 'done') {
        showSyncDone(result);
        return;
    }

    if (result.status === 'tan_required') {
        openTanModal(result, connectionId);
        return;
    }
}

function showSyncDone(result) {
    const imported = result.imported || 0;
    const duplicates = result.duplicates || 0;
    showToast(`Abruf erfolgreich: ${imported} neu, ${duplicates} Duplikate übersprungen`, 'success');
    loadBanking();
    // Refresh data elsewhere if visible
    if (typeof refreshNavBadge === 'function') refreshNavBadge();
    if (currentPage === 'transactions' && typeof loadTransactions === 'function') loadTransactions();
    if (currentPage === 'dashboard' && typeof loadDashboard === 'function') loadDashboard();
}

// --- TAN handling ------------------------------------------------------------

function openTanModal(result, connectionId) {
    _tanFlow = { connectionId, jobId: result.job_id, decoupled: !!result.decoupled };

    document.getElementById('bank-tan-connection-id').value = connectionId;
    document.getElementById('bank-tan-job-id').value = result.job_id;
    document.getElementById('bank-tan-challenge').textContent = result.challenge || '';
    document.getElementById('bank-tan-input').value = '';
    document.getElementById('bank-tan-error').textContent = '';
    document.getElementById('bank-tan-status').textContent = '';

    // Optional photoTAN / matrix image
    const imgWrap = document.getElementById('bank-tan-image-wrap');
    const img = document.getElementById('bank-tan-image');
    if (result.challenge_image) {
        img.src = result.challenge_image;
        imgWrap.classList.remove('hidden');
    } else {
        img.src = '';
        imgWrap.classList.add('hidden');
    }

    const inputGroup = document.getElementById('bank-tan-input-group');
    const submitBtn = document.getElementById('bank-tan-submit-btn');

    if (_tanFlow.decoupled) {
        // Approve-in-app: no TAN to type, poll for confirmation
        inputGroup.classList.add('hidden');
        submitBtn.classList.add('hidden');
        document.getElementById('bank-tan-status').textContent = 'Warte auf Freigabe in der Banking-App...';
        openModal('bank-tan-modal');
        pollDecoupledTan();
    } else {
        inputGroup.classList.remove('hidden');
        submitBtn.classList.remove('hidden');
        openModal('bank-tan-modal');
        setTimeout(() => document.getElementById('bank-tan-input').focus(), 100);
    }
}

async function confirmBankTan() {
    const tan = document.getElementById('bank-tan-input').value.trim();
    const errorEl = document.getElementById('bank-tan-error');
    errorEl.textContent = '';

    if (!tan) {
        errorEl.textContent = 'Bitte TAN eingeben.';
        return;
    }

    const btn = document.getElementById('bank-tan-submit-btn');
    btn.disabled = true;
    btn.textContent = 'Prüfe...';

    try {
        const result = await api.submitBankTan(_tanFlow.connectionId, _tanFlow.jobId, tan);
        if (result.status === 'done') {
            closeModal('bank-tan-modal');
            showSyncDone(result);
        } else if (result.status === 'tan_required') {
            // e.g. switched to decoupled confirmation
            openTanModal(result, _tanFlow.connectionId);
        } else {
            errorEl.textContent = result.message || 'TAN fehlgeschlagen';
        }
    } catch (error) {
        errorEl.textContent = error.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Bestätigen';
    }
}

async function pollDecoupledTan() {
    const jobId = _tanFlow.jobId;
    const connectionId = _tanFlow.connectionId;

    // Stop if the modal was closed or the flow changed
    const modal = document.getElementById('bank-tan-modal');
    if (!modal.classList.contains('active') || _tanFlow.jobId !== jobId) return;

    try {
        const result = await api.submitBankTan(connectionId, jobId, null);

        if (result.status === 'done') {
            closeModal('bank-tan-modal');
            showSyncDone(result);
            return;
        }
        if (result.status === 'error') {
            document.getElementById('bank-tan-error').textContent = result.message || 'Freigabe fehlgeschlagen';
            document.getElementById('bank-tan-status').textContent = '';
            return;
        }
        // still tan_required -> keep waiting (guard against stale job after re-open)
        if (_tanFlow.jobId === jobId && modal.classList.contains('active')) {
            setTimeout(pollDecoupledTan, 3000);
        }
    } catch (error) {
        document.getElementById('bank-tan-error').textContent = error.message;
    }
}
