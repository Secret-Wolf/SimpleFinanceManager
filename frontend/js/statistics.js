// Statistics Module

let categoryChart = null;
let timeChart = null;
let customStatsStartDate = null;
let customStatsEndDate = null;

async function loadStatistics() {
    const tasks = [loadCategoryStats(), loadTimeStats(), loadSharedSummary(), loadBudgetStats()];
    await Promise.all(tasks);
}

// Budgets: Budget vs. Ist des aktuellen Monats (Ausgaben inkl. Unterkategorien)
async function loadBudgetStats() {
    const section = document.getElementById('budget-section');
    const container = document.getElementById('budget-content');
    if (!section || !container) return;

    try {
        const stats = await api.getBudgetStats();

        if (!stats.items || stats.items.length === 0) {
            section.style.display = 'none';
            return;
        }

        const months = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
                        'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
        document.getElementById('budget-section-title').textContent =
            `Budgets – ${months[stats.month - 1]} ${stats.year}`;

        const rows = stats.items.map(item => {
            const percent = parseFloat(item.percent);
            const barClass = percent >= 100 ? 'over' : (percent >= 80 ? 'warn' : 'ok');
            const remaining = parseFloat(item.remaining);
            const remainingText = remaining >= 0
                ? `${formatCurrency(item.remaining)} übrig`
                : `${formatCurrency(Math.abs(remaining))} überzogen`;

            return `
                <div class="budget-row">
                    <div class="budget-row-header">
                        <span class="category-badge" title="${escapeHtml(item.full_path || item.category_name)}">
                            <span class="dot" style="background-color: ${safeColor(item.category_color)}"></span>
                            ${escapeHtml(item.category_name)}
                        </span>
                        <span class="budget-row-values">
                            ${formatCurrency(item.spent)} von ${formatCurrency(item.budget)}
                            · <span class="budget-remaining ${remaining < 0 ? 'over' : ''}">${remainingText}</span>
                        </span>
                    </div>
                    <div class="budget-bar-track">
                        <div class="budget-bar ${barClass}" style="width: ${Math.min(percent, 100)}%"></div>
                    </div>
                </div>
            `;
        }).join('');

        const totalPercent = parseFloat(stats.total_budget) > 0
            ? (parseFloat(stats.total_spent) / parseFloat(stats.total_budget)) * 100 : 0;

        container.innerHTML = rows + `
            <div class="budget-row" style="border-top: 1px solid var(--border-color); padding-top: 12px; margin-bottom: 0;">
                <div class="budget-row-header" style="font-weight: 600;">
                    <span>Gesamt</span>
                    <span class="budget-row-values">${formatCurrency(stats.total_spent)} von ${formatCurrency(stats.total_budget)} (${totalPercent.toFixed(0)}%)</span>
                </div>
            </div>
        `;

        section.style.display = 'block';

    } catch (error) {
        section.style.display = 'none';
    }
}

function changeStatsPeriod() {
    const period = document.getElementById('stats-period').value;
    const customDatesDiv = document.getElementById('stats-custom-dates');

    if (period === 'custom') {
        customDatesDiv.style.display = 'flex';
        // Set default dates to current month if not already set
        if (!document.getElementById('stats-start-date').value) {
            const today = new Date();
            const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
            document.getElementById('stats-start-date').value = firstDay.toISOString().split('T')[0];
            document.getElementById('stats-end-date').value = today.toISOString().split('T')[0];
        }
        // Don't load stats yet - wait for user to click "Anwenden"
    } else {
        customDatesDiv.style.display = 'none';
        customStatsStartDate = null;
        customStatsEndDate = null;
        loadStatistics();
    }
}

function applyCustomStatsPeriod() {
    const startDate = document.getElementById('stats-start-date').value;
    const endDate = document.getElementById('stats-end-date').value;

    if (!startDate || !endDate) {
        showToast('Bitte Start- und Enddatum angeben', 'error');
        return;
    }

    if (new Date(startDate) > new Date(endDate)) {
        showToast('Startdatum muss vor Enddatum liegen', 'error');
        return;
    }

    customStatsStartDate = startDate;
    customStatsEndDate = endDate;
    loadStatistics();
}

async function loadCategoryStats() {
    const container = document.getElementById('category-chart-container');
    const tableContainer = document.getElementById('category-stats-table');
    const period = document.getElementById('stats-period').value;

    container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

    try {
        const params = { period };
        if (period === 'custom' && customStatsStartDate && customStatsEndDate) {
            params.start_date = customStatsStartDate;
            params.end_date = customStatsEndDate;
        }
        // Add account filter if selected
        if (selectedAccountId) {
            params.account_id = selectedAccountId;
        }
        const stats = await api.getStatsByCategory(params);

        // Render chart (top-level categories with rolled-up subtree totals)
        renderCategoryChart(stats.categories.filter(c => c.total > 0).slice(0, 10));

        // Render table (subtree rows indented below their parents)
        tableContainer.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Kategorie</th>
                        <th class="text-right">Summe</th>
                        <th class="text-right">Durchschnitt/Monat</th>
                        <th class="text-right">Anzahl</th>
                    </tr>
                </thead>
                <tbody>
                    ${renderCategoryStatsRows(stats.categories)}
                </tbody>
                <tfoot>
                    <tr style="font-weight: 600;">
                        <td>Gesamt</td>
                        <td class="text-right amount negative">${formatCurrency(stats.total_expenses)}</td>
                        <td></td>
                        <td></td>
                    </tr>
                </tfoot>
            </table>
        `;

        // Summary
        document.getElementById('stats-income').textContent = formatCurrency(stats.total_income);
        document.getElementById('stats-expenses').textContent = formatCurrency(stats.total_expenses);
        document.getElementById('stats-balance').textContent = formatCurrency(stats.total_income - stats.total_expenses);
        document.getElementById('stats-balance').className = `value ${stats.total_income >= stats.total_expenses ? 'positive' : 'negative'}`;

    } catch (error) {
        container.innerHTML = `<p style="color: var(--danger-color)">Fehler: ${escapeHtml(error.message)}</p>`;
    }
}

// Recursive table rows: parents show rolled-up subtree totals, children are indented
function renderCategoryStatsRows(cats, level = 0) {
    let html = '';

    for (const cat of cats) {
        if (!(cat.total > 0)) continue;

        const hasChildren = cat.children && cat.children.some(c => c.total > 0);
        html += `
            <tr${level > 0 ? ' class="stats-subcategory-row"' : ''}>
                <td>
                    <span class="category-badge" style="margin-left: ${level * 20}px;">
                        <span class="dot" style="background-color: ${safeColor(cat.category_color)}"></span>
                        ${escapeHtml(cat.category_name)}
                    </span>
                    ${hasChildren && level === 0 ? '<small style="color: var(--text-muted); margin-left: 6px;">inkl. Unterkategorien</small>' : ''}
                </td>
                <td class="text-right amount negative">${formatCurrency(cat.total)}</td>
                <td class="text-right">${formatCurrency(cat.average_monthly)}</td>
                <td class="text-right">${cat.transaction_count}</td>
            </tr>
        `;

        if (cat.children && cat.children.length > 0) {
            html += renderCategoryStatsRows(cat.children, level + 1);
        }
    }

    return html;
}

async function loadTimeStats() {
    const container = document.getElementById('time-chart-container');
    const period = document.getElementById('stats-period').value;

    container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

    try {
        const params = { period };
        if (period === 'custom' && customStatsStartDate && customStatsEndDate) {
            params.start_date = customStatsStartDate;
            params.end_date = customStatsEndDate;
        }
        // Add account filter if selected
        if (selectedAccountId) {
            params.account_id = selectedAccountId;
        }
        const stats = await api.getStatsOverTime(params);
        renderTimeChart(stats.data);
    } catch (error) {
        container.innerHTML = `<p style="color: var(--danger-color)">Fehler: ${escapeHtml(error.message)}</p>`;
    }
}

function renderCategoryChart(data) {
    const container = document.getElementById('category-chart-container');

    if (data.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary)">Keine Daten vorhanden</p>';
        return;
    }

    // Simple bar chart using CSS
    const maxValue = Math.max(...data.map(d => d.total));

    container.innerHTML = `
        <div class="simple-bar-chart">
            ${data.map(cat => `
                <div class="bar-row">
                    <div class="bar-label">${truncate(cat.category_name, 15)}</div>
                    <div class="bar-container">
                        <div class="bar" style="width: ${(cat.total / maxValue) * 100}%; background-color: ${safeColor(cat.category_color)}"></div>
                    </div>
                    <div class="bar-value">${formatCurrency(cat.total)}</div>
                </div>
            `).join('')}
        </div>
    `;

    // Add styles if not exists
    if (!document.getElementById('chart-styles')) {
        const style = document.createElement('style');
        style.id = 'chart-styles';
        style.textContent = `
            .simple-bar-chart {
                padding: 10px 0;
            }
            .bar-row {
                display: flex;
                align-items: center;
                margin-bottom: 12px;
            }
            .bar-label {
                width: 120px;
                font-size: 0.875rem;
                color: var(--text-secondary);
            }
            .bar-container {
                flex: 1;
                height: 24px;
                background-color: var(--bg-secondary);
                border-radius: var(--radius-sm);
                overflow: hidden;
            }
            .bar {
                height: 100%;
                border-radius: var(--radius-sm);
                transition: width 0.3s ease;
            }
            .bar-value {
                width: 100px;
                text-align: right;
                font-size: 0.875rem;
                font-weight: 500;
            }
            .time-chart {
                display: flex;
                align-items: flex-end;
                gap: 4px;
                padding: 4px 0 0 0;
            }
            .time-bar-group {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
            }
            .time-bars {
                display: flex;
                align-items: flex-end;
                gap: 2px;
                width: 100%;
                height: 160px;
            }
            .time-bar {
                flex: 1;
                border-radius: 2px 2px 0 0;
                min-height: 2px;
            }
            .time-bar.income {
                background-color: var(--success-color);
            }
            .time-bar.expense {
                background-color: var(--danger-color);
            }
            .time-label {
                font-size: 0.75rem;
                color: var(--text-muted);
                margin-top: 8px;
                white-space: nowrap;
            }
        `;
        document.head.appendChild(style);
    }
}

function renderTimeChart(data) {
    const container = document.getElementById('time-chart-container');

    if (data.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary)">Keine Daten vorhanden</p>';
        return;
    }

    const maxValue = Math.max(
        ...data.map(d => Math.max(parseFloat(d.income) || 0, parseFloat(d.expenses) || 0))
    );

    container.innerHTML = `
        <div class="time-chart">
            ${data.map(point => `
                <div class="time-bar-group">
                    <div class="time-bars">
                        <div class="time-bar income" style="height: ${maxValue > 0 ? (parseFloat(point.income) / maxValue) * 100 : 0}%" title="Einnahmen: ${formatCurrency(point.income)}"></div>
                        <div class="time-bar expense" style="height: ${maxValue > 0 ? (parseFloat(point.expenses) / maxValue) * 100 : 0}%" title="Ausgaben: ${formatCurrency(point.expenses)}"></div>
                    </div>
                    <div class="time-label">${formatTimeLabel(point.date)}</div>
                </div>
            `).join('')}
        </div>
        <div class="flex justify-between mt-4" style="font-size: 0.875rem;">
            <div class="flex items-center gap-2">
                <div style="width: 12px; height: 12px; background-color: var(--success-color); border-radius: 2px;"></div>
                <span>Einnahmen</span>
            </div>
            <div class="flex items-center gap-2">
                <div style="width: 12px; height: 12px; background-color: var(--danger-color); border-radius: 2px;"></div>
                <span>Ausgaben</span>
            </div>
        </div>
    `;
}

function formatTimeLabel(dateStr) {
    if (!dateStr) return '';

    // Handle different formats
    if (dateStr.includes('-W')) {
        // Week format: 2024-W01
        return dateStr.replace('-W', '/KW');
    }

    if (dateStr.match(/^\d{4}-\d{2}$/)) {
        // Month format: 2024-01
        const [year, month] = dateStr.split('-');
        const months = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
        return months[parseInt(month) - 1];
    }

    if (dateStr.match(/^\d{4}-\d{2}-\d{2}$/)) {
        // Day format: 2024-01-15
        const date = new Date(dateStr);
        return `${date.getDate()}.${date.getMonth() + 1}.`;
    }

    return dateStr;
}

async function exportStats() {
    const period = document.getElementById('stats-period').value;

    try {
        const params = { period };
        if (period === 'custom' && customStatsStartDate && customStatsEndDate) {
            params.start_date = customStatsStartDate;
            params.end_date = customStatsEndDate;
        }
        // Add account filter if selected
        if (selectedAccountId) {
            params.account_id = selectedAccountId;
        }
        const stats = await api.getStatsByCategory(params);

        // Create CSV (subtrees flattened with full path, totals rolled up)
        let csv = 'Kategorie;Summe;Durchschnitt/Monat;Anzahl\n';

        const writeRows = (cats, parentPath) => {
            for (const cat of cats) {
                const path = parentPath ? `${parentPath} > ${cat.category_name}` : cat.category_name;
                csv += `${csvCell(path)};${cat.total};${cat.average_monthly};${cat.transaction_count}\n`;
                if (cat.children && cat.children.length > 0) {
                    writeRows(cat.children, path);
                }
            }
        };
        writeRows(stats.categories, '');

        csv += `\n"Einnahmen gesamt";${stats.total_income};\n`;
        csv += `"Ausgaben gesamt";${stats.total_expenses};\n`;
        csv += `"Bilanz";${stats.total_income - stats.total_expenses};\n`;

        // Download
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `finanzmanager-statistik-${period}.csv`;
        link.click();

        showToast('Export erstellt', 'success');

    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

async function loadSharedSummary() {
    const section = document.getElementById('shared-summary-section');
    const container = document.getElementById('shared-summary-content');
    if (!container || !section) return;

    try {
        const period = document.getElementById('stats-period').value;
        const params = { period };
        if (period === 'custom' && customStatsStartDate && customStatsEndDate) {
            params.start_date = customStatsStartDate;
            params.end_date = customStatsEndDate;
        }

        const summary = await api.getSharedSummary(params);

        // Hide section if no shared expenses exist
        if (!summary.total_shared_expenses || parseFloat(summary.total_shared_expenses) === 0) {
            section.style.display = 'none';
            return;
        }

        section.style.display = 'block';

        const memberCount = summary.by_profile ? summary.by_profile.length : 1;
        const perPerson = summary.total_shared_expenses / Math.max(memberCount, 1);

        container.innerHTML = `
            <div class="stats-grid" style="margin-bottom: 20px;">
                <div class="stat-card shared-card">
                    <div class="label">Gemeinsame Ausgaben gesamt</div>
                    <div class="value negative">${formatCurrency(summary.total_shared_expenses)}</div>
                </div>
                <div class="stat-card">
                    <div class="label">Pro Person (${memberCount})</div>
                    <div class="value negative">${formatCurrency(perPerson)}</div>
                </div>
            </div>

            ${summary.by_profile && summary.by_profile.length > 0 ? `
                <h4 style="margin-bottom: 12px; color: var(--text-secondary);">Wer hat bezahlt?</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin-bottom: 20px;">
                    ${summary.by_profile.map(p => `
                        <div class="stat-card" style="border-left: 4px solid ${p.profile_color || '#2563eb'};">
                            <div class="label">${escapeHtml(p.profile_name)}</div>
                            <div class="value negative" style="font-size: 1.1rem;">${formatCurrency(p.total_paid)}</div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}

            ${summary.by_category && summary.by_category.length > 0 ? `
                <h4 style="margin-bottom: 12px; color: var(--text-secondary);">Nach Kategorie</h4>
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
                                            <span class="dot" style="background-color: ${safeColor(cat.category_color)}"></span>
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
        `;

    } catch (error) {
        section.style.display = 'none';
    }
}
