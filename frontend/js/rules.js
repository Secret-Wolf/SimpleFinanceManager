// Rules Module

async function loadRules() {
    const container = document.getElementById('rules-list');
    container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

    try {
        const rules = await api.getRules();

        if (rules.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
                    </svg>
                    <h3>Keine Regeln</h3>
                    <p>Erstelle Regeln, um Transaktionen automatisch zu kategorisieren.</p>
                    <button class="btn btn-primary" onclick="showAddRuleModal()">Regel erstellen</button>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Priorität</th>
                            <th>Name</th>
                            <th>Kriterien</th>
                            <th>Kategorie</th>
                            <th>Status</th>
                            <th>Aktionen</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rules.map(rule => `
                            <tr data-id="${rule.id}">
                                <td>${rule.priority}</td>
                                <td>${rule.name || '-'}</td>
                                <td>
                                    ${getRuleCriteriaText(rule)}
                                </td>
                                <td>
                                    ${rule.category ? `
                                        <span class="category-badge">
                                            <span class="dot" style="background-color: ${rule.category.color || '#888'}"></span>
                                            ${rule.category.name}
                                        </span>
                                    ` : '-'}
                                </td>
                                <td>
                                    <span style="color: ${rule.is_active ? 'var(--success-color)' : 'var(--text-muted)'}">
                                        ${rule.is_active ? 'Aktiv' : 'Inaktiv'}
                                    </span>
                                    ${rule.assign_shared ? '<span class="shared-badge" title="Markiert als gemeinsam" style="margin-left: 4px;">G</span>' : ''}
                                </td>
                                <td>
                                    <div class="flex gap-2">
                                        <button class="btn btn-sm btn-icon" onclick="editRule(${rule.id})" title="Bearbeiten">
                                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                                            </svg>
                                        </button>
                                        <button class="btn btn-sm btn-icon" onclick="toggleRule(${rule.id}, ${!rule.is_active})" title="${rule.is_active ? 'Deaktivieren' : 'Aktivieren'}">
                                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                ${rule.is_active ?
                                                    '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="9" x2="15" y2="15"></line><line x1="15" y1="9" x2="9" y2="15"></line>' :
                                                    '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>'
                                                }
                                            </svg>
                                        </button>
                                        <button class="btn btn-sm btn-icon" onclick="deleteRule(${rule.id})" title="Löschen">
                                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                <polyline points="3 6 5 6 21 6"></polyline>
                                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                                            </svg>
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;

    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Fehler: ${error.message}</p></div>`;
    }
}

function getRuleCriteriaText(rule) {
    const criteria = [];

    if (rule.match_counterpart_name) {
        criteria.push(`Empfänger: "${rule.match_counterpart_name}"`);
    }
    if (rule.match_counterpart_iban) {
        criteria.push(`IBAN: ${rule.match_counterpart_iban}`);
    }
    if (rule.match_purpose) {
        criteria.push(`Verwendungszweck: "${rule.match_purpose}"`);
    }
    if (rule.match_booking_type) {
        criteria.push(`Buchungsart: ${rule.match_booking_type}`);
    }
    if (rule.match_amount_min !== null || rule.match_amount_max !== null) {
        const min = rule.match_amount_min !== null ? formatCurrency(rule.match_amount_min) : '-';
        const max = rule.match_amount_max !== null ? formatCurrency(rule.match_amount_max) : '-';
        criteria.push(`Betrag: ${min} bis ${max}`);
    }

    return criteria.length > 0 ?
        `<small style="color: var(--text-secondary)">${criteria.join('<br>')}</small>` :
        '<small style="color: var(--text-muted)">Keine Kriterien</small>';
}

function showAddRuleModal() {
    document.getElementById('rule-modal-title').textContent = 'Neue Regel';
    document.getElementById('rule-form').reset();
    document.getElementById('rule-id').value = '';
    document.getElementById('rule-active').checked = true;
    document.getElementById('rule-assign-shared').checked = false;

    // Update category select
    document.getElementById('rule-assign-category').innerHTML = `
        <option value="">Kategorie wählen</option>
        ${generateCategoryOptions(categories)}
    `;

    openModal('rule-modal');
}

async function editRule(id) {
    try {
        const rule = await api.getRule(id);

        document.getElementById('rule-modal-title').textContent = 'Regel bearbeiten';
        document.getElementById('rule-id').value = rule.id;
        document.getElementById('rule-name').value = rule.name || '';
        document.getElementById('rule-priority').value = rule.priority || 0;
        document.getElementById('rule-counterpart').value = rule.match_counterpart_name || '';
        document.getElementById('rule-iban').value = rule.match_counterpart_iban || '';
        document.getElementById('rule-purpose').value = rule.match_purpose || '';
        document.getElementById('rule-booking-type').value = rule.match_booking_type || '';
        document.getElementById('rule-amount-min').value = rule.match_amount_min || '';
        document.getElementById('rule-amount-max').value = rule.match_amount_max || '';
        document.getElementById('rule-active').checked = rule.is_active;
        document.getElementById('rule-assign-shared').checked = rule.assign_shared || false;

        // Update category select
        document.getElementById('rule-assign-category').innerHTML = `
            <option value="">Kategorie wählen</option>
            ${generateCategoryOptions(categories, rule.assign_category_id)}
        `;

        openModal('rule-modal');

    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function saveRule() {
    const id = document.getElementById('rule-id').value;
    const name = document.getElementById('rule-name').value.trim();
    const priority = parseInt(document.getElementById('rule-priority').value) || 0;
    const categoryId = document.getElementById('rule-assign-category').value;
    const isActive = document.getElementById('rule-active').checked;

    const counterpart = document.getElementById('rule-counterpart').value.trim();
    const iban = document.getElementById('rule-iban').value.trim();
    const purpose = document.getElementById('rule-purpose').value.trim();
    const bookingType = document.getElementById('rule-booking-type').value.trim();
    const amountMin = document.getElementById('rule-amount-min').value;
    const amountMax = document.getElementById('rule-amount-max').value;

    if (!categoryId) {
        showToast('Bitte Kategorie wählen', 'error');
        return;
    }

    // Check at least one criterion
    if (!counterpart && !iban && !purpose && !bookingType && !amountMin && !amountMax) {
        showToast('Mindestens ein Kriterium erforderlich', 'error');
        return;
    }

    const assignShared = document.getElementById('rule-assign-shared').checked;

    const data = {
        name: name || null,
        priority,
        assign_category_id: parseInt(categoryId),
        is_active: isActive,
        assign_shared: assignShared,
        match_counterpart_name: counterpart || null,
        match_counterpart_iban: iban || null,
        match_purpose: purpose || null,
        match_booking_type: bookingType || null,
        match_amount_min: amountMin ? parseFloat(amountMin) : null,
        match_amount_max: amountMax ? parseFloat(amountMax) : null
    };

    try {
        if (id) {
            await api.updateRule(parseInt(id), data);
            showToast('Regel aktualisiert', 'success');
        } else {
            await api.createRule(data);
            showToast('Regel erstellt', 'success');
        }

        closeModal('rule-modal');
        loadRules();

    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function toggleRule(id, active) {
    try {
        await api.updateRule(id, { is_active: active });
        showToast(`Regel ${active ? 'aktiviert' : 'deaktiviert'}`, 'success');
        loadRules();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function deleteRule(id) {
    if (!confirm('Regel wirklich löschen?')) return;

    try {
        await api.deleteRule(id);
        showToast('Regel gelöscht', 'success');
        loadRules();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function applyAllRules() {
    try {
        const result = await api.applyRules();
        showToast(result.message, 'success');

        // Refresh dashboard if visible
        if (currentPage === 'dashboard') {
            loadDashboard();
        }
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}
