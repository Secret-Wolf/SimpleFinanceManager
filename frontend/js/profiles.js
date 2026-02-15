// Profiles Module

let profiles = [];

async function loadProfilesData() {
    try {
        profiles = await api.getProfiles();
    } catch (error) {
        console.error('Failed to load profiles:', error);
        profiles = [];
    }
}

async function loadProfilesDropdown() {
    await loadProfilesData();
    const dropdown = document.getElementById('global-profile-filter');

    if (dropdown && profiles.length > 0) {
        dropdown.innerHTML = `
            <option value="">Alle Profile</option>
            ${profiles.map(p => `
                <option value="${p.id}" style="color: ${p.color}">${p.name}${p.is_admin ? ' (Admin)' : ''}</option>
            `).join('')}
            <option value="shared">Gemeinsamer Haushalt</option>
        `;

        // Show profile selector only if there are multiple profiles
        const selector = document.querySelector('.profile-selector');
        if (selector) {
            selector.style.display = profiles.length > 1 ? 'block' : 'none';
        }
    }
}

function onProfileFilterChange() {
    const dropdown = document.getElementById('global-profile-filter');
    const value = dropdown.value;

    if (value === 'shared') {
        selectedProfileId = null;
        sharedMode = true;
    } else {
        selectedProfileId = value ? parseInt(value) : null;
        sharedMode = false;
    }

    // Update account dropdown to show only accounts from this profile
    updateAccountsForProfile();

    // Reload current page
    switch (currentPage) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'transactions':
            transactionFilters.page = 1;
            loadTransactions();
            refreshNavBadge();
            break;
        case 'statistics':
            loadStatistics();
            refreshNavBadge();
            break;
        default:
            refreshNavBadge();
            break;
    }
}

async function updateAccountsForProfile() {
    try {
        const allAccounts = await api.getAccounts();
        const dropdown = document.getElementById('global-account-filter');

        let filteredAccounts = allAccounts;
        if (selectedProfileId) {
            filteredAccounts = allAccounts.filter(a => a.profile_id === selectedProfileId);
        }

        if (dropdown) {
            dropdown.innerHTML = `
                <option value="">Alle Konten</option>
                ${filteredAccounts.map(acc => `
                    <option value="${acc.id}">${acc.name}${acc.bank_name ? ' (' + acc.bank_name + ')' : ''}</option>
                `).join('')}
            `;
        }

        // Reset account filter
        selectedAccountId = null;

        const selector = document.querySelector('.account-selector');
        if (selector) {
            selector.style.display = filteredAccounts.length > 1 ? 'block' : 'none';
        }

        accounts = filteredAccounts;
    } catch (error) {
        console.error('Failed to update accounts for profile:', error);
    }
}

// Profile Management Page
async function loadProfileManagement() {
    const container = document.getElementById('profiles-content');
    if (!container) return;

    container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

    try {
        await loadProfilesData();
        const allAccounts = await api.getAccounts();

        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <h3>Profile verwalten</h3>
                    <button class="btn btn-primary btn-sm" onclick="showAddProfileModal()">Profil erstellen</button>
                </div>
                <div class="card-body">
                    ${profiles.length === 0 ? '<p style="color: var(--text-secondary)">Keine Profile vorhanden</p>' : `
                        <div class="profiles-grid">
                            ${profiles.map(p => `
                                <div class="profile-card" style="border-left: 4px solid ${p.color}">
                                    <div class="profile-header">
                                        <div>
                                            <strong>${p.name}</strong>
                                            ${p.is_admin ? '<span class="badge badge-admin">Admin</span>' : ''}
                                        </div>
                                        <div class="flex gap-2">
                                            <button class="btn btn-sm btn-icon" onclick="showEditProfileModal(${p.id})" title="Bearbeiten">
                                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                                                </svg>
                                            </button>
                                            ${!p.is_admin ? `
                                                <button class="btn btn-sm btn-icon" onclick="deleteProfile(${p.id})" title="Löschen">
                                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                        <polyline points="3 6 5 6 21 6"></polyline>
                                                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                                    </svg>
                                                </button>
                                            ` : ''}
                                        </div>
                                    </div>
                                    <div class="profile-accounts">
                                        <small style="color: var(--text-secondary)">Konten:</small>
                                        ${allAccounts.filter(a => a.profile_id === p.id).map(a => `
                                            <span class="account-chip">${a.name}</span>
                                        `).join('') || '<span style="color: var(--text-muted); font-size: 0.8rem">Keine Konten zugewiesen</span>'}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    `}
                </div>
            </div>

            <div class="card mt-4">
                <div class="card-header">
                    <h3>Konten-Zuordnung</h3>
                </div>
                <div class="card-body">
                    <p style="color: var(--text-secondary); margin-bottom: 16px;">Weise Konten einem Profil zu, um persönliche Finanzen zu trennen.</p>
                    ${allAccounts.map(acc => `
                        <div class="account-assignment" style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px; padding: 8px; border-radius: var(--radius-sm); background: var(--bg-secondary);">
                            <span style="flex: 1; font-weight: 500;">${acc.name} ${acc.bank_name ? '(' + acc.bank_name + ')' : ''}</span>
                            <select class="form-control" style="width: 200px;" onchange="assignAccountProfile(${acc.id}, this.value)">
                                <option value="0">Nicht zugeordnet</option>
                                ${profiles.map(p => `
                                    <option value="${p.id}" ${acc.profile_id === p.id ? 'selected' : ''}>${p.name}</option>
                                `).join('')}
                            </select>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Fehler: ${error.message}</p></div>`;
    }
}

function showAddProfileModal() {
    document.getElementById('profile-modal-title').textContent = 'Neues Profil';
    document.getElementById('profile-id').value = '';
    document.getElementById('profile-name').value = '';
    document.getElementById('profile-color').value = '#2563eb';
    openModal('profile-modal');
}

async function showEditProfileModal(id) {
    try {
        const profile = await api.getProfile(id);
        document.getElementById('profile-modal-title').textContent = 'Profil bearbeiten';
        document.getElementById('profile-id').value = profile.id;
        document.getElementById('profile-name').value = profile.name;
        document.getElementById('profile-color').value = profile.color;
        openModal('profile-modal');
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function saveProfile() {
    const id = document.getElementById('profile-id').value;
    const name = document.getElementById('profile-name').value.trim();
    const color = document.getElementById('profile-color').value;

    if (!name) {
        showToast('Bitte Name eingeben', 'error');
        return;
    }

    try {
        if (id) {
            await api.updateProfile(parseInt(id), { name, color });
            showToast('Profil aktualisiert', 'success');
        } else {
            await api.createProfile({ name, color });
            showToast('Profil erstellt', 'success');
        }
        closeModal('profile-modal');
        await loadProfilesDropdown();
        loadProfileManagement();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function deleteProfile(id) {
    if (!confirm('Profil wirklich löschen? Die zugeordneten Konten werden entkoppelt.')) return;

    try {
        await api.deleteProfile(id);
        showToast('Profil gelöscht', 'success');
        await loadProfilesDropdown();
        loadProfileManagement();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function assignAccountProfile(accountId, profileId) {
    try {
        await api.updateAccount(accountId, { profile_id: parseInt(profileId) });
        showToast('Konto zugeordnet', 'success');
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}
