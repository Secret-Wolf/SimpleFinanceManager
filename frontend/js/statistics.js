// Statistics Module

let categoryChart = null;
let timeChart = null;
let customStatsStartDate = null;
let customStatsEndDate = null;

async function loadStatistics() {
    await Promise.all([
        loadCategoryStats(),
        loadTimeStats()
    ]);
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
        const stats = await api.getStatsByCategory(params);

        // Render chart
        renderCategoryChart(stats.categories.filter(c => c.total > 0).slice(0, 10));

        // Render table
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
                    ${stats.categories.filter(c => c.total > 0).map(cat => `
                        <tr>
                            <td>
                                <span class="category-badge">
                                    <span class="dot" style="background-color: ${cat.category_color || '#888'}"></span>
                                    ${cat.category_name}
                                </span>
                            </td>
                            <td class="text-right amount negative">${formatCurrency(cat.total)}</td>
                            <td class="text-right">${formatCurrency(cat.average_monthly)}</td>
                            <td class="text-right">${cat.transaction_count}</td>
                        </tr>
                    `).join('')}
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
        container.innerHTML = `<p style="color: var(--danger-color)">Fehler: ${error.message}</p>`;
    }
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
        const stats = await api.getStatsOverTime(params);
        renderTimeChart(stats.data);
    } catch (error) {
        container.innerHTML = `<p style="color: var(--danger-color)">Fehler: ${error.message}</p>`;
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
                        <div class="bar" style="width: ${(cat.total / maxValue) * 100}%; background-color: ${cat.category_color || '#888'}"></div>
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
                height: 200px;
                gap: 4px;
                padding: 20px 0;
            }
            .time-bar-group {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                height: 100%;
            }
            .time-bars {
                flex: 1;
                display: flex;
                align-items: flex-end;
                gap: 2px;
                width: 100%;
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
        const stats = await api.getStatsByCategory(params);

        // Create CSV
        let csv = 'Kategorie;Summe;Durchschnitt/Monat;Anzahl\n';

        for (const cat of stats.categories) {
            csv += `"${cat.category_name}";${cat.total};${cat.average_monthly};${cat.transaction_count}\n`;
        }

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
