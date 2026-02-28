// Household Management Module

async function loadHouseholdManagement() {
    const container = document.getElementById('households-content');
    const invitesContainer = document.getElementById('household-invites');
    if (!container) return;

    container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

    try {
        // Load invites and households in parallel
        const [households, invites] = await Promise.all([
            api.getHouseholds(),
            api.getHouseholdInvites()
        ]);

        // Render pending invites
        if (invites.length > 0) {
            invitesContainer.classList.remove('hidden');
            invitesContainer.innerHTML = `
                <div class="card" style="border-left: 4px solid var(--warning-color);">
                    <div class="card-header">
                        <h3>Offene Einladungen</h3>
                    </div>
                    <div class="card-body">
                        ${invites.map(inv => `
                            <div class="flex items-center justify-between" style="padding: 8px 0; border-bottom: 1px solid var(--border-color);">
                                <div>
                                    <strong>${escapeHtml(inv.household_name || 'Haushalt')}</strong>
                                    <span style="color: var(--text-secondary); margin-left: 8px;">
                                        Eingeladen von ${escapeHtml(inv.invited_by_name || 'Unbekannt')}
                                    </span>
                                </div>
                                <div class="flex gap-2">
                                    <button class="btn btn-sm btn-primary" onclick="handleAcceptInvite(${inv.id})">Annehmen</button>
                                    <button class="btn btn-sm btn-secondary" onclick="handleDeclineInvite(${inv.id})">Ablehnen</button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        } else {
            invitesContainer.classList.add('hidden');
            invitesContainer.innerHTML = '';
        }

        // Render households
        if (households.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>Du bist noch in keinem Haushalt.</p>
                    <p style="color: var(--text-secondary); margin-top: 8px;">
                        Erstelle einen Haushalt und lade andere Benutzer ein, um gemeinsame Ausgaben zu tracken.
                    </p>
                </div>
            `;
            return;
        }

        container.innerHTML = households.map(h => `
            <div class="card" style="margin-bottom: 16px;">
                <div class="card-header flex justify-between items-center">
                    <h3>${escapeHtml(h.name)}</h3>
                    <div class="flex gap-2">
                        <button class="btn btn-sm btn-primary" onclick="showInviteModal(${h.id})">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                                <circle cx="8.5" cy="7" r="4"></circle>
                                <line x1="20" y1="8" x2="20" y2="14"></line>
                                <line x1="23" y1="11" x2="17" y2="11"></line>
                            </svg>
                            Einladen
                        </button>
                        <button class="btn btn-sm btn-secondary" onclick="viewSharedExpenses(${h.id})">
                            Gemeinsame Ausgaben
                        </button>
                    </div>
                </div>
                <div class="card-body">
                    <div class="table-container">
                        <table>
                            <thead>
                                <tr>
                                    <th>Mitglied</th>
                                    <th>E-Mail</th>
                                    <th>Rolle</th>
                                    <th>Beigetreten</th>
                                    <th style="width: 80px;"></th>
                                </tr>
                            </thead>
                            <tbody>
                                ${h.members.map(m => `
                                    <tr>
                                        <td>
                                            ${escapeHtml(m.user_display_name || 'Unbekannt')}
                                            ${m.user_id === currentUser.id ? '<span style="color:var(--text-secondary); font-size:0.75rem; margin-left:4px;">(Du)</span>' : ''}
                                        </td>
                                        <td>${escapeHtml(m.user_email || '')}</td>
                                        <td>
                                            <span style="color: ${m.role === 'admin' ? 'var(--primary-color)' : 'var(--text-secondary)'}; font-weight: 500;">
                                                ${m.role === 'admin' ? 'Admin' : 'Mitglied'}
                                            </span>
                                        </td>
                                        <td>${formatDate(m.joined_at)}</td>
                                        <td>
                                            ${m.user_id === currentUser.id ? `
                                                <button class="btn btn-sm btn-secondary" onclick="handleLeaveHousehold(${h.id}, ${m.user_id})" title="Verlassen">
                                                    Verlassen
                                                </button>
                                            ` : (h.created_by === currentUser.id ? `
                                                <button class="btn btn-sm btn-secondary" onclick="handleRemoveMember(${h.id}, ${m.user_id})" title="Entfernen">
                                                    Entfernen
                                                </button>
                                            ` : '')}
                                        </td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `).join('');

    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Fehler: ${escapeHtml(error.message)}</p></div>`;
    }
}

function showCreateHouseholdModal() {
    document.getElementById('household-name-input').value = '';
    document.getElementById('household-modal-error').textContent = '';
    openModal('household-modal');
}

async function saveHousehold() {
    const name = document.getElementById('household-name-input').value.trim();
    const errorEl = document.getElementById('household-modal-error');
    errorEl.textContent = '';

    if (!name) {
        errorEl.textContent = 'Bitte Name eingeben';
        return;
    }

    try {
        await api.createHousehold({ name });
        showToast('Haushalt erstellt', 'success');
        closeModal('household-modal');
        loadHouseholdManagement();
    } catch (error) {
        errorEl.textContent = error.message || 'Fehler beim Erstellen';
    }
}

function showInviteModal(householdId) {
    document.getElementById('invite-household-id').value = householdId;
    document.getElementById('invite-email-input').value = '';
    document.getElementById('invite-modal-error').textContent = '';
    openModal('invite-modal');
}

async function sendInvite() {
    const householdId = parseInt(document.getElementById('invite-household-id').value);
    const email = document.getElementById('invite-email-input').value.trim();
    const errorEl = document.getElementById('invite-modal-error');
    errorEl.textContent = '';

    if (!email) {
        errorEl.textContent = 'Bitte E-Mail eingeben';
        return;
    }

    try {
        await api.inviteToHousehold(householdId, email);
        showToast('Einladung gesendet', 'success');
        closeModal('invite-modal');
    } catch (error) {
        errorEl.textContent = error.message || 'Fehler beim Einladen';
    }
}

async function handleAcceptInvite(inviteId) {
    try {
        await api.acceptInvite(inviteId);
        showToast('Einladung angenommen', 'success');
        loadHouseholdManagement();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function handleDeclineInvite(inviteId) {
    try {
        await api.declineInvite(inviteId);
        showToast('Einladung abgelehnt', 'success');
        loadHouseholdManagement();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function handleLeaveHousehold(householdId, userId) {
    if (!confirm('Haushalt wirklich verlassen?')) return;

    try {
        await api.leaveHousehold(householdId, userId);
        showToast('Haushalt verlassen', 'success');
        loadHouseholdManagement();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function handleRemoveMember(householdId, userId) {
    if (!confirm('Mitglied wirklich entfernen?')) return;

    try {
        await api.leaveHousehold(householdId, userId);
        showToast('Mitglied entfernt', 'success');
        loadHouseholdManagement();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

function viewSharedExpenses(householdId) {
    // Navigate to statistics page with household filter
    navigateTo('statistics');
    // Set household filter if the statistics page supports it
    const event = new CustomEvent('household-filter', { detail: { householdId } });
    document.dispatchEvent(event);
}
