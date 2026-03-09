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
                                                <button class="btn btn-sm btn-secondary" onclick="showEditUserModal(${u.id})" title="Bearbeiten">
                                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                                        <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                                                    </svg>
                                                </button>
                                                ${u.id !== currentUser.id ? `
                                                    <button class="btn btn-sm ${u.is_admin ? 'btn-primary' : 'btn-secondary'}"
                                                        onclick="toggleUserAdmin(${u.id}, ${u.is_admin})"
                                                        title="${u.is_admin ? 'Admin-Rechte entziehen' : 'Zum Admin machen'}">
                                                        ${u.is_admin ? 'Admin' : 'User'}
                                                    </button>
                                                    <button class="btn btn-sm ${u.is_active ? 'btn-secondary' : 'btn-primary'}"
                                                        onclick="toggleUserActive(${u.id}, ${u.is_active})"
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
        `;
    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Fehler: ${escapeHtml(error.message)}</p></div>`;
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
