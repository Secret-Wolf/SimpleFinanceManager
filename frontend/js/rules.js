// Rules Module

// Zuletzt geladene Regeln (für Gruppen-Datalist und das "Regeln anwenden"-Modal)
let allRules = [];

async function loadRules() {
    const container = document.getElementById('rules-list');
    container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

    try {
        const rules = await api.getRules();
        allRules = rules;

        if (rules.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
                    </svg>
                    <h3>Keine Regeln</h3>
                    <p>Erstelle Regeln, um Transaktionen automatisch zu kategorisieren.</p>
                    <button class="btn btn-primary" data-action="showAddRuleModal">Regel erstellen</button>
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
                            <th>Gruppe</th>
                            <th>Kriterien</th>
                            <th>Kategorie</th>
                            <th>Status</th>
                            <th>Aktionen</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rules.map(rule => `
                            <tr data-id="${rule.id}" class="${rule.is_active ? '' : 'rule-row-inactive'}">
                                <td>${rule.priority}</td>
                                <td>${escapeHtml(rule.name || '-')}</td>
                                <td>
                                    ${rule.group_name ? `<span class="rule-group-badge">${escapeHtml(rule.group_name)}</span>` : '<span style="color: var(--text-muted)">–</span>'}
                                </td>
                                <td>
                                    ${getRuleCriteriaText(rule)}
                                </td>
                                <td>
                                    ${rule.category ? `
                                        <span class="category-badge">
                                            <span class="dot" style="background-color: ${safeColor(rule.category.color)}"></span>
                                            ${escapeHtml(rule.category.name)}
                                        </span>
                                    ` : '-'}
                                </td>
                                <td>
                                    <span class="rule-status ${rule.is_active ? 'active' : 'inactive'}" title="${rule.is_active ? 'Regel ist aktiv' : 'Regel ist inaktiv'}">
                                        <span class="status-dot"></span>${rule.is_active ? 'Aktiv' : 'Inaktiv'}
                                    </span>
                                    ${rule.assign_shared ? '<span class="shared-badge" title="Markiert als gemeinsam" style="margin-left: 4px;">G</span>' : ''}
                                </td>
                                <td>
                                    <div class="flex gap-2">
                                        <button class="btn btn-sm btn-icon" data-action="editRule" data-id="${rule.id}" title="Bearbeiten">
                                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                                                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
                                            </svg>
                                        </button>
                                        <button class="btn btn-sm btn-icon" data-action="toggleRule" data-id="${rule.id}" data-value="${!rule.is_active}" title="${rule.is_active ? 'Deaktivieren' : 'Aktivieren'}">
                                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                                ${rule.is_active ?
                                                    '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="9" x2="15" y2="15"></line><line x1="15" y1="9" x2="9" y2="15"></line>' :
                                                    '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline>'
                                                }
                                            </svg>
                                        </button>
                                        <button class="btn btn-sm btn-icon" data-action="deleteRule" data-id="${rule.id}" title="Löschen">
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
        container.innerHTML = `<div class="empty-state"><p>Fehler: ${escapeHtml(error.message)}</p></div>`;
    }
}

function getRuleCriteriaText(rule) {
    const criteria = [];

    if (rule.match_counterpart_name) {
        criteria.push(`Empfänger: "${escapeHtml(rule.match_counterpart_name)}"`);
    }
    if (rule.match_counterpart_iban) {
        criteria.push(`IBAN: ${escapeHtml(rule.match_counterpart_iban)}`);
    }
    if (rule.match_purpose) {
        criteria.push(`Verwendungszweck: "${escapeHtml(rule.match_purpose)}"`);
    }
    if (rule.match_booking_type) {
        criteria.push(`Buchungsart: ${escapeHtml(rule.match_booking_type)}`);
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

// Distinct group names of the user's rules (for datalist + apply modal)
function getRuleGroups() {
    const groups = [];
    for (const rule of allRules) {
        if (rule.group_name && !groups.includes(rule.group_name)) {
            groups.push(rule.group_name);
        }
    }
    return groups.sort((a, b) => a.localeCompare(b, 'de'));
}

function updateRuleGroupDatalist() {
    const datalist = document.getElementById('rule-group-datalist');
    if (datalist) {
        datalist.innerHTML = getRuleGroups().map(g => `<option value="${escapeHtml(g)}"></option>`).join('');
    }
}

function showAddRuleModal() {
    document.getElementById('rule-modal-title').textContent = 'Neue Regel';
    document.getElementById('rule-form').reset();
    document.getElementById('rule-id').value = '';
    document.getElementById('rule-active').checked = true;
    document.getElementById('rule-assign-shared').checked = false;
    updateRuleGroupDatalist();

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
        document.getElementById('rule-group').value = rule.group_name || '';
        updateRuleGroupDatalist();
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
    const groupName = document.getElementById('rule-group').value.trim();
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
        group_name: groupName,  // "" löscht die Gruppe (PATCH: null = keine Änderung)
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

// --- "Regeln anwenden" mit Auswahl (Regel-Sets) ---

async function showApplyRulesModal() {
    // Make sure we have the latest rules (button is also reachable right after page load)
    if (allRules.length === 0) {
        try {
            allRules = await api.getRules();
        } catch (error) {
            showToast('Fehler: ' + error.message, 'error');
            return;
        }
    }

    const activeRules = allRules.filter(r => r.is_active);
    const container = document.getElementById('apply-rules-selection');

    if (activeRules.length === 0) {
        container.innerHTML = '<p style="color: var(--text-muted);">Keine aktiven Regeln vorhanden.</p>';
    } else {
        // Gruppieren: benannte Gruppen alphabetisch, "Ohne Gruppe" zuletzt
        const groups = new Map();
        for (const rule of activeRules) {
            const key = rule.group_name || '';
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(rule);
        }
        const sortedKeys = [...groups.keys()].sort((a, b) => {
            if (a === '') return 1;
            if (b === '') return -1;
            return a.localeCompare(b, 'de');
        });

        container.innerHTML = sortedKeys.map((key, index) => {
            const rules = groups.get(key);
            const groupKey = `g${index}`;
            return `
                <div class="apply-rules-group">
                    <label class="apply-rules-group-header">
                        <input type="checkbox" checked data-action="toggleApplyRulesGroup" data-group-key="${groupKey}">
                        <strong>${key ? escapeHtml(key) : 'Ohne Gruppe'}</strong>
                        <span class="apply-rules-group-count">${rules.length}</span>
                    </label>
                    <div class="apply-rules-group-rules">
                        ${rules.map(rule => `
                            <label class="apply-rules-rule">
                                <input type="checkbox" checked class="apply-rule-checkbox" value="${rule.id}"
                                       data-action="syncApplyRulesGroup" data-group-key="${groupKey}">
                                <span>${escapeHtml(rule.name || getPlainRuleCriteria(rule))}</span>
                                ${rule.category ? `
                                    <span class="category-badge">
                                        <span class="dot" style="background-color: ${safeColor(rule.category.color)}"></span>
                                        ${escapeHtml(rule.category.name)}
                                    </span>
                                ` : ''}
                            </label>
                        `).join('')}
                    </div>
                </div>
            `;
        }).join('');
    }

    document.getElementById('apply-rules-overwrite').checked = false;
    openModal('apply-rules-modal');
}

// Kurzbeschreibung für Regeln ohne Namen (reiner Text, wird escaped eingesetzt)
function getPlainRuleCriteria(rule) {
    if (rule.match_counterpart_name) return `Empfänger: ${rule.match_counterpart_name}`;
    if (rule.match_purpose) return `Zweck: ${rule.match_purpose}`;
    if (rule.match_counterpart_iban) return `IBAN: ${rule.match_counterpart_iban}`;
    if (rule.match_booking_type) return `Buchungsart: ${rule.match_booking_type}`;
    return `Regel #${rule.id}`;
}

// Gruppen-Checkbox schaltet alle Regeln der Gruppe (called via CLICK_ACTIONS)
function toggleApplyRulesGroup(el) {
    const groupKey = el.dataset.groupKey;
    document.querySelectorAll(`.apply-rule-checkbox[data-group-key="${groupKey}"]`)
        .forEach(cb => { cb.checked = el.checked; });
}

// Regel-Checkbox aktualisiert den Zustand ihrer Gruppen-Checkbox
function syncApplyRulesGroup(el) {
    const groupKey = el.dataset.groupKey;
    const boxes = [...document.querySelectorAll(`.apply-rule-checkbox[data-group-key="${groupKey}"]`)];
    const groupBox = document.querySelector(`input[data-action="toggleApplyRulesGroup"][data-group-key="${groupKey}"]`);
    if (!groupBox) return;
    const checkedCount = boxes.filter(cb => cb.checked).length;
    groupBox.checked = checkedCount === boxes.length;
    groupBox.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
}

async function confirmApplyRules() {
    const selectedIds = [...document.querySelectorAll('.apply-rule-checkbox:checked')]
        .map(cb => parseInt(cb.value));

    if (selectedIds.length === 0) {
        showToast('Bitte mindestens eine Regel auswählen', 'error');
        return;
    }

    const overwrite = document.getElementById('apply-rules-overwrite').checked;
    const totalActive = allRules.filter(r => r.is_active).length;
    // Alles ausgewählt → ohne Einschränkung anwenden (wie bisher)
    const ruleIds = selectedIds.length === totalActive ? null : selectedIds;

    try {
        const result = await api.applyRules(overwrite, ruleIds);
        showToast(result.message, 'success');
        closeModal('apply-rules-modal');

        if (currentPage === 'dashboard') {
            loadDashboard();
        }
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}
