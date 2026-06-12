// User Management Module (admin only)

async function loadUserManagement() {
    const container = document.getElementById('users-content');
    if (!container) return;

    container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

    try {
        const users = await api.getUsers();

        container.innerHTML = `
            <div class="card">
                <div class="card-body">
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Name</th>
                                    <th>E-Mail</th>
                                    <th>Status</th>
                                    <th>Erstellt</th>
                                    <th style="width: 120px;"></th>
                                </tr>
                            </thead>
                            <tbody>
                                ${users.map(u => `
                                    <tr>
                                        <td>
                                            ${escapeHtml(u.display_name)}
                                            ${u.is_admin ? '<span style="font-size:0.7rem; color: var(--primary-color); margin-left:6px; font-weight:600;">Admin</span>' : ''}
                                            ${u.id === currentUser.id ? '<span style="color:var(--text-secondary); font-size:0.75rem; margin-left:4px;">(Du)</span>' : ''}
                                        </td>
                                        <td>${escapeHtml(u.email)}</td>
                                        <td>
                                            <span style="color: ${u.is_active ? 'var(--success-color)' : 'var(--text-secondary)'}; font-weight: 500;">
                                                ${u.is_active ? 'Aktiv' : 'Deaktiviert'}
                                            </span>
                                        </td>
                                        <td>${formatDate(u.created_at)}</td>
                                        <td>
                                            <div class="flex gap-1">
                                                <button class="btn btn-sm btn-secondary" data-action="showEditUserModal" data-id="${u.id}" title="Bearbeiten">
                                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                                                    </svg>
                                                </button>
                                                ${u.id !== currentUser.id ? `
                                                    <button class="btn btn-sm ${u.is_admin ? 'btn-primary' : 'btn-secondary'}"
                                                        data-action="toggleUserAdmin" data-id="${u.id}" data-value="${u.is_admin}"
                                                        title="${u.is_admin ? 'Admin-Rechte entziehen' : 'Zum Admin machen'}">
                                                        ${u.is_admin ? 'Admin' : 'User'}
                                                    </button>
                                                    <button class="btn btn-sm ${u.is_active ? 'btn-secondary' : 'btn-primary'}"
                                                        data-action="toggleUserActive" data-id="${u.id}" data-value="${u.is_active}"
                                                        title="${u.is_active ? 'Deaktivieren' : 'Aktivieren'}">
                                                        ${u.is_active ? 'Deaktivieren' : 'Aktivieren'}
                                                    </button>
                                                ` : ''}
                                            </div>
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div class="card mt-4">
                <div class="card-header">
                    <h3>Datensicherung</h3>
                </div>
                <div class="card-body">
                    <p style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 12px;">
                        Das Backup enthält die komplette Datenbank (alle Benutzer, Transaktionen, Regeln,
                        Bankverbindungen — keine PINs/Passwörter im Klartext). Beim Wiederherstellen werden
                        alle aktuellen Daten ersetzt; die bisherige Datenbank bleibt als Sicherheitskopie
                        im data-Verzeichnis liegen.
                    </p>
                    <div class="card-actions">
                        <button class="btn btn-secondary" data-action="downloadBackup">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                <polyline points="7 10 12 15 17 10"></polyline>
                                <line x1="12" y1="15" x2="12" y2="3"></line>
                            </svg>
                            Backup herunterladen
                        </button>
                        <label class="btn btn-secondary" for="restore-file-input" style="cursor: pointer;">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                <polyline points="17 8 12 3 7 8"></polyline>
                                <line x1="12" y1="3" x2="12" y2="15"></line>
                            </svg>
                            Backup wiederherstellen…
                        </label>
                        <input type="file" id="restore-file-input" accept=".db,application/octet-stream"
                               style="display: none;" data-onchange="handleRestoreFileSelected">
                    </div>
                </div>
            </div>
        `;
    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Fehler: ${escapeHtml(error.message)}</p></div>`;
    }
}

// --- Datensicherung (admin) ---

async function downloadBackup() {
    try {
        const response = await fetch('/api/backup/download');
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${response.status}`);
        }
        const blob = await response.blob();
        const dispo = response.headers.get('Content-Disposition') || '';
        const match = dispo.match(/filename="?([^";]+)"?/);

        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = match ? match[1] : 'finanzmanager-backup.db';
        link.click();
        URL.revokeObjectURL(link.href);

        showToast('Backup heruntergeladen', 'success');
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function handleRestoreFileSelected() {
    const input = document.getElementById('restore-file-input');
    const file = input.files && input.files[0];
    input.value = '';
    if (!file) return;

    const confirmed = confirm(
        `Datenbank aus "${file.name}" wiederherstellen?\n\n` +
        'ACHTUNG: Alle aktuellen Daten (alle Benutzer!) werden ersetzt. ' +
        'Die bisherige Datenbank bleibt als Sicherheitskopie im data-Verzeichnis liegen.\n\n' +
        'Danach ist eine erneute Anmeldung erforderlich.'
    );
    if (!confirmed) return;

    try {
        const formData = new FormData();
        formData.append('file', file);
        const result = await api.restoreBackup(formData);
        showToast(result.message, 'success');
        setTimeout(() => window.location.reload(), 1500);
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

function showCreateUserModal() {
    document.getElementById('user-modal-title').textContent = 'Neuer Benutzer';
    document.getElementById('user-edit-id').value = '';
    document.getElementById('user-name-input').value = '';
    document.getElementById('user-email-input').value = '';
    document.getElementById('user-email-group').style.display = '';
    document.getElementById('user-password-input').value = '';
    document.getElementById('user-password-input').required = true;
    document.getElementById('user-password-label').textContent = 'Passwort';
    document.getElementById('user-password-hint').textContent = 'Min. 12 Zeichen, Gross-/Kleinbuchstaben + Zahl';
    document.getElementById('user-modal-error').textContent = '';
    openModal('user-modal');
}

let _usersCache = [];

async function showEditUserModal(id) {
    try {
        if (_usersCache.length === 0) {
            _usersCache = await api.getUsers();
        }
        const user = _usersCache.find(u => u.id === id);
        if (!user) return;

        document.getElementById('user-modal-title').textContent = 'Benutzer bearbeiten';
        document.getElementById('user-edit-id').value = id;
        document.getElementById('user-name-input').value = user.display_name;
        document.getElementById('user-email-group').style.display = 'none';
        document.getElementById('user-password-input').value = '';
        document.getElementById('user-password-input').required = false;
        document.getElementById('user-password-label').textContent = 'Neues Passwort (leer = nicht aendern)';
        document.getElementById('user-password-hint').textContent = 'Min. 12 Zeichen, Gross-/Kleinbuchstaben + Zahl';
        document.getElementById('user-modal-error').textContent = '';
        openModal('user-modal');
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function saveUser() {
    const id = document.getElementById('user-edit-id').value;
    const displayName = document.getElementById('user-name-input').value.trim();
    const email = document.getElementById('user-email-input').value.trim();
    const password = document.getElementById('user-password-input').value;
    const errorEl = document.getElementById('user-modal-error');
    errorEl.textContent = '';

    if (!displayName) {
        errorEl.textContent = 'Bitte Name eingeben';
        return;
    }

    try {
        if (id) {
            const data = { display_name: displayName };
            if (password) data.new_password = password;
            await api.updateUser(parseInt(id), data);
            showToast('Benutzer aktualisiert', 'success');
        } else {
            if (!email) { errorEl.textContent = 'Bitte E-Mail eingeben'; return; }
            if (!password) { errorEl.textContent = 'Bitte Passwort eingeben'; return; }
            await api.createUser({ email, password, display_name: displayName });
            showToast('Benutzer erstellt', 'success');
        }
        _usersCache = [];
        closeModal('user-modal');
        loadUserManagement();
    } catch (error) {
        errorEl.textContent = error.message || 'Fehler beim Speichern';
    }
}

async function toggleUserAdmin(id, currentStatus) {
    const action = currentStatus ? 'Admin-Rechte entziehen' : 'zum Admin machen';
    if (!confirm(`Benutzer wirklich ${action}?`)) return;

    try {
        await api.updateUser(id, { is_admin: !currentStatus });
        showToast(`Benutzer ${currentStatus ? 'ist kein Admin mehr' : 'ist jetzt Admin'}`, 'success');
        _usersCache = [];
        loadUserManagement();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function toggleUserActive(id, currentStatus) {
    const action = currentStatus ? 'deaktivieren' : 'aktivieren';
    if (!confirm(`Benutzer wirklich ${action}?`)) return;

    try {
        await api.updateUser(id, { is_active: !currentStatus });
        showToast(`Benutzer ${currentStatus ? 'deaktiviert' : 'aktiviert'}`, 'success');
        _usersCache = [];
        loadUserManagement();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}
