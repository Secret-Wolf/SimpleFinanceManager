// Household Management Module

let activeHouseholdExpensesId = null;
let householdExpensesPeriod = 'year';

async function loadHouseholdManagement() {
    const container = document.getElementById('households-content');
    const invitesContainer = document.getElementById('household-invites');
    const expensesContainer = document.getElementById('household-expenses');
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
                                    <button class="btn btn-sm btn-primary" data-action="handleAcceptInvite" data-id="${inv.id}">Annehmen</button>
                                    <button class="btn btn-sm btn-secondary" data-action="handleDeclineInvite" data-id="${inv.id}">Ablehnen</button>
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
                        <button class="btn btn-sm btn-primary" data-action="showInviteModal" data-id="${h.id}">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                                <circle cx="8.5" cy="7" r="4"></circle>
                                <line x1="20" y1="8" x2="20" y2="14"></line>
                                <line x1="23" y1="11" x2="17" y2="11"></line>
                            </svg>
                            Einladen
                        </button>
                        <button class="btn btn-sm btn-secondary" data-action="viewSharedExpenses" data-id="${h.id}" data-member-count="${h.members ? h.members.length : 2}">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="18" y1="20" x2="18" y2="10"></line>
                                <line x1="12" y1="20" x2="12" y2="4"></line>
                                <line x1="6" y1="20" x2="6" y2="14"></line>
                            </svg>
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
                                                <button class="btn btn-sm btn-secondary" data-action="handleLeaveHousehold" data-id="${h.id}" data-user-id="${m.user_id}" title="Verlassen">
                                                    Verlassen
                                                </button>
                                            ` : (h.created_by === currentUser.id ? `
                                                <button class="btn btn-sm btn-secondary" data-action="handleRemoveMember" data-id="${h.id}" data-user-id="${m.user_id}" title="Entfernen">
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

        // If we had an active expenses view, refresh it
        if (activeHouseholdExpensesId) {
            const household = households.find(h => h.id === activeHouseholdExpensesId);
            if (household) {
                loadSharedExpensesView(activeHouseholdExpensesId, household.members.length, household.name);
            }
        }

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
        if (activeHouseholdExpensesId === householdId) {
            closeSharedExpensesView();
        }
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

// ---- Shared Expenses View ----

function viewSharedExpenses(householdId, memberCount) {
    // Find household name from DOM
    const households = document.querySelectorAll('#households-content .card');
    let householdName = 'Haushalt';
    households.forEach(card => {
        const h3 = card.querySelector('h3');
        const btn = card.querySelector(`[data-action="viewSharedExpenses"][data-id="${householdId}"]`);
        if (h3 && btn) {
            householdName = h3.textContent;
        }
    });

    activeHouseholdExpensesId = householdId;
    householdExpensesPeriod = 'year';
    loadSharedExpensesView(householdId, memberCount, householdName);
}

function closeSharedExpensesView() {
    activeHouseholdExpensesId = null;
    const container = document.getElementById('household-expenses');
    container.classList.add('hidden');
    container.innerHTML = '';
}

function changeHouseholdExpensesPeriod(period, householdId, memberCount, householdName) {
    householdExpensesPeriod = period;
    loadSharedExpensesView(householdId, memberCount, householdName);
}

async function loadSharedExpensesView(householdId, memberCount, householdName) {
    const container = document.getElementById('household-expenses');
    container.classList.remove('hidden');
    container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

    // Scroll to top of expenses view
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });

    try {
        const params = {
            period: householdExpensesPeriod,
            household_id: householdId
        };
        const summary = await api.getSharedSummary(params);

        const periodLabels = {
            week: 'Diese Woche',
            month: 'Dieser Monat',
            last_month: 'Letzter Monat',
            quarter: 'Dieses Quartal',
            year: 'Dieses Jahr'
        };

        const perPerson = memberCount > 0 ? summary.total_shared_expenses / memberCount : summary.total_shared_expenses;

        container.innerHTML = `
            <div class="card" style="border-left: 4px solid var(--primary-color);">
                <div class="card-header flex justify-between items-center">
                    <div>
                        <h3>Gemeinsame Ausgaben - ${escapeHtml(householdName)}</h3>
                    </div>
                    <div class="flex gap-2 items-center">
                        <select class="form-control" style="width: auto;" data-onchange="changeHouseholdExpensesPeriod" data-household-id="${householdId}" data-member-count="${memberCount}" data-household-name="${escapeHtml(householdName)}">
                            ${Object.entries(periodLabels).map(([val, label]) =>
                                `<option value="${val}" ${val === householdExpensesPeriod ? 'selected' : ''}>${label}</option>`
                            ).join('')}
                        </select>
                        <button class="btn btn-sm btn-secondary" data-action="closeSharedExpensesView" title="Schliessen">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <line x1="18" y1="6" x2="6" y2="18"></line>
                                <line x1="6" y1="6" x2="18" y2="18"></line>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="card-body">
                    <!-- Summary Cards -->
                    <div class="stats-grid" style="margin-bottom: 20px;">
                        <div class="stat-card">
                            <div class="label">Gesamt</div>
                            <div class="value negative">${formatCurrency(summary.total_shared_expenses)}</div>
                        </div>
                        <div class="stat-card">
                            <div class="label">Pro Person (${memberCount})</div>
                            <div class="value negative">${formatCurrency(perPerson)}</div>
                        </div>
                    </div>

                    <!-- Who paid what -->
                    ${summary.by_profile && summary.by_profile.length > 0 ? `
                        <h4 style="margin-bottom: 12px; color: var(--text-secondary);">Wer hat bezahlt?</h4>
                        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 20px;">
                            ${summary.by_profile.map(p => {
                                const diff = p.total_paid - perPerson;
                                const diffLabel = diff > 0
                                    ? `<span style="color: var(--danger-color);">+${formatCurrency(diff)} zu viel</span>`
                                    : diff < 0
                                    ? `<span style="color: var(--success-color);">${formatCurrency(Math.abs(diff))} weniger</span>`
                                    : `<span style="color: var(--text-secondary);">Ausgeglichen</span>`;
                                return `
                                    <div class="stat-card" style="border-left: 4px solid ${p.profile_color || '#2563eb'};">
                                        <div class="label">${escapeHtml(p.profile_name)}</div>
                                        <div class="value negative" style="font-size: 1.1rem;">${formatCurrency(p.total_paid)}</div>
                                        <div style="font-size: 0.8rem; margin-top: 4px;">${diffLabel}</div>
                                    </div>
                                `;
                            }).join('')}
                        </div>

                        <!-- Settlement suggestion -->
                        ${renderSettlement(summary.by_profile, perPerson)}
                    ` : '<p style="color: var(--text-secondary);">Noch keine gemeinsamen Ausgaben markiert.</p>'}

                    <!-- By category -->
                    ${summary.by_category && summary.by_category.length > 0 ? `
                        <h4 style="margin: 20px 0 12px; color: var(--text-secondary);">Nach Kategorie</h4>
                        <div class="table-container">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Kategorie</th>
                                        <th class="text-right">Summe</th>
                                        <th class="text-right">Anzahl</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${summary.by_category.map(cat => `
                                        <tr>
                                            <td>
                                                <span class="category-badge">
                                                    <span class="dot" style="background-color: ${cat.category_color || '#888'}"></span>
                                                    ${escapeHtml(cat.category_name)}
                                                </span>
                                            </td>
                                            <td class="text-right amount negative">${formatCurrency(cat.total)}</td>
                                            <td class="text-right">${cat.transaction_count}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;

    } catch (error) {
        container.innerHTML = `
            <div class="card" style="border-left: 4px solid var(--danger-color);">
                <div class="card-header flex justify-between items-center">
                    <h3>Gemeinsame Ausgaben</h3>
                    <button class="btn btn-sm btn-secondary" data-action="closeSharedExpensesView">Schliessen</button>
                </div>
                <div class="card-body">
                    <p style="color: var(--danger-color);">Fehler: ${escapeHtml(error.message)}</p>
                </div>
            </div>
        `;
    }
}

function renderSettlement(byProfile, perPerson) {
    if (!byProfile || byProfile.length < 2) return '';

    // Calculate who owes whom
    const balances = byProfile.map(p => ({
        name: p.profile_name,
        diff: p.total_paid - perPerson  // positive = overpaid, negative = underpaid
    }));

    const overpaid = balances.filter(b => b.diff > 0.01).sort((a, b) => b.diff - a.diff);
    const underpaid = balances.filter(b => b.diff < -0.01).sort((a, b) => a.diff - b.diff);

    if (overpaid.length === 0 || underpaid.length === 0) return '';

    // Simple settlement: match overpaid with underpaid
    const settlements = [];
    let oi = 0, ui = 0;
    const oRemaining = overpaid.map(o => o.diff);
    const uRemaining = underpaid.map(u => Math.abs(u.diff));

    while (oi < overpaid.length && ui < underpaid.length) {
        const amount = Math.min(oRemaining[oi], uRemaining[ui]);
        if (amount > 0.01) {
            settlements.push({
                from: underpaid[ui].name,
                to: overpaid[oi].name,
                amount: amount
            });
        }
        oRemaining[oi] -= amount;
        uRemaining[ui] -= amount;
        if (oRemaining[oi] < 0.01) oi++;
        if (uRemaining[ui] < 0.01) ui++;
    }

    if (settlements.length === 0) return '';

    return `
        <div style="background: var(--bg-secondary); border-radius: var(--radius-md); padding: 16px; margin-bottom: 16px;">
            <h4 style="margin-bottom: 12px; color: var(--text-secondary);">Ausgleich</h4>
            ${settlements.map(s => `
                <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0;">
                    <strong>${escapeHtml(s.from)}</strong>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-secondary)" stroke-width="2">
                        <line x1="5" y1="12" x2="19" y2="12"></line>
                        <polyline points="12 5 19 12 12 19"></polyline>
                    </svg>
                    <strong>${escapeHtml(s.to)}</strong>
                    <span class="amount" style="margin-left: auto; font-weight: 600; color: var(--primary-color);">
                        ${formatCurrency(s.amount)}
                    </span>
                </div>
            `).join('')}
        </div>
    `;
}
