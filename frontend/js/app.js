// Main Application

// State
let currentPage = 'dashboard';
let categories = [];
let flatCategories = [];
let selectedAccountId = null; // null = Alle Konten
let selectedProfileId = null; // null = Alle Profile
let sharedMode = false; // true = "Gemeinsamer Haushalt" view
let accounts = [];

// Navigation
function navigateTo(page) {
    currentPage = page;

    // Update nav
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
        if (item.dataset.page === page) {
            item.classList.add('active');
        }
    });

    // Update content
    document.querySelectorAll('.page').forEach(p => {
        p.classList.add('hidden');
    });
    const pageEl = document.getElementById(`page-${page}`);
    if (pageEl) {
        pageEl.classList.remove('hidden');
    }

    // Load page data
    switch (page) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'transactions':
            loadTransactions();
            break;
        case 'categories':
            loadCategories();
            break;
        case 'rules':
            loadRules();
            break;
        case 'accounts':
            loadAccounts();
            break;
        case 'import':
            // Import page doesn't need initial load
            break;
        case 'statistics':
            loadStatistics();
            break;
        case 'profiles':
            loadProfileManagement();
            break;
    }
}

// Initialize
async function init() {
    // Load categories for global use
    await loadCategoriesData();

    // Load profiles and populate filter dropdown
    await loadProfilesDropdown();

    // Load accounts and populate filter dropdown
    await loadAccountsDropdown();

    // Set up navigation
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', () => {
            navigateTo(item.dataset.page);
        });
    });

    // Initialize default categories if needed
    if (categories.length === 0) {
        try {
            await api.initDefaultCategories();
            await loadCategoriesData();
        } catch (e) {
            console.log('Categories may already exist');
        }
    }

    // Load dashboard
    navigateTo('dashboard');

    // Set up keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        switch (e.key) {
            case 'i':
                navigateTo('import');
                break;
            case 'f':
                const searchInput = document.querySelector('#page-transactions .search-input input');
                if (searchInput && currentPage === 'transactions') {
                    searchInput.focus();
                    e.preventDefault();
                }
                break;
        }
    });
}

// Load categories data
async function loadCategoriesData() {
    try {
        categories = await api.getCategories();
        flatCategories = flattenCategories(categories);

        // Update all category dropdowns
        updateCategoryDropdowns();
    } catch (error) {
        console.error('Failed to load categories:', error);
        categories = [];
        flatCategories = [];
    }
}

// Update all category filter dropdowns
function updateCategoryDropdowns() {
    const categoryFilter = document.getElementById('tx-category-filter');
    const bulkCategory = document.getElementById('bulk-category');
    const options = generateCategoryOptions(categories);

    if (categoryFilter) {
        categoryFilter.innerHTML = `<option value="">Alle Kategorien</option>${options}`;
    }

    if (bulkCategory) {
        bulkCategory.innerHTML = `<option value="">Kategorie wählen</option>${options}`;
    }
}

// Dashboard
async function loadDashboard() {
    const container = document.getElementById('dashboard-content');
    container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

    try {
        const summary = await api.getDashboardSummary(selectedAccountId, selectedProfileId);

        const incomeChange = percentChange(summary.income_current_month, summary.income_previous_month);
        const expenseChange = percentChange(summary.expenses_current_month, summary.expenses_previous_month);

        const sharedExpenses = summary.shared_expenses_current_month || 0;

        container.innerHTML = `
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="label">Kontostand</div>
                    <div class="value ${summary.current_balance >= 0 ? 'positive' : 'negative'}">
                        ${summary.current_balance !== null ? formatCurrency(summary.current_balance) : '-'}
                    </div>
                </div>
                <div class="stat-card">
                    <div class="label">Einnahmen (Monat)</div>
                    <div class="value positive">${formatCurrency(summary.income_current_month)}</div>
                    ${incomeChange !== null ? `<div class="change ${incomeChange >= 0 ? 'up' : 'down'}">${formatPercent(incomeChange)} zum Vormonat</div>` : ''}
                </div>
                <div class="stat-card">
                    <div class="label">Ausgaben (Monat)</div>
                    <div class="value negative">${formatCurrency(summary.expenses_current_month)}</div>
                    ${expenseChange !== null ? `<div class="change ${expenseChange <= 0 ? 'up' : 'down'}">${formatPercent(-expenseChange)} zum Vormonat</div>` : ''}
                </div>
                <div class="stat-card" style="cursor:pointer" onclick="navigateTo('transactions'); document.getElementById('uncategorized-filter').checked = true; loadTransactions();">
                    <div class="label">Unkategorisiert</div>
                    <div class="value" style="color: var(--warning-color)">${summary.uncategorized_count}</div>
                </div>
                ${sharedExpenses !== 0 ? `
                <div class="stat-card shared-card">
                    <div class="label">Gemeinsame Ausgaben (Monat)</div>
                    <div class="value negative">${formatCurrency(sharedExpenses)}</div>
                    <div class="change" style="color: var(--text-secondary)">Pro Person: ~${formatCurrency(sharedExpenses / 2)}</div>
                </div>
                ` : ''}
            </div>

            <div class="flex gap-4" style="flex-wrap: wrap;">
                <div class="card" style="flex: 1; min-width: 300px;">
                    <div class="card-header">
                        <h3>Top Ausgaben</h3>
                    </div>
                    <div class="card-body">
                        ${summary.top_categories.length > 0 ? `
                            <div class="category-list">
                                ${summary.top_categories.map(cat => `
                                    <div class="category-item">
                                        <div class="color-dot" style="background-color: ${cat.category_color || '#888'}"></div>
                                        <span class="name">${cat.category_name}</span>
                                        <span class="amount negative">${formatCurrency(cat.total)}</span>
                                    </div>
                                `).join('')}
                            </div>
                        ` : '<p class="text-center" style="color: var(--text-secondary)">Keine Daten</p>'}
                    </div>
                </div>

                <div class="card" style="flex: 2; min-width: 400px;">
                    <div class="card-header">
                        <h3>Letzte Transaktionen</h3>
                        <button class="btn btn-sm btn-secondary" onclick="navigateTo('transactions')">Alle anzeigen</button>
                    </div>
                    <div class="card-body">
                        ${summary.recent_transactions.length > 0 ? `
                            <div class="table-container">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Datum</th>
                                            <th>Empfänger</th>
                                            <th>Kategorie</th>
                                            <th class="text-right">Betrag</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${summary.recent_transactions.map(tx => `
                                            <tr>
                                                <td>${formatDate(tx.booking_date)}</td>
                                                <td>${truncate(tx.counterpart_name || tx.booking_type || '-', 30)}</td>
                                                <td>
                                                    ${tx.category ? `
                                                        <span class="category-badge">
                                                            <span class="dot" style="background-color: ${tx.category.color || '#888'}"></span>
                                                            ${tx.category.name}
                                                        </span>
                                                    ` : '<span class="category-badge uncategorized">Unkategorisiert</span>'}
                                                </td>
                                                <td class="text-right amount ${tx.amount >= 0 ? 'positive' : 'negative'}">
                                                    ${formatCurrency(tx.amount)}
                                                </td>
                                            </tr>
                                        `).join('')}
                                    </tbody>
                                </table>
                            </div>
                        ` : '<p class="text-center" style="color: var(--text-secondary)">Keine Transaktionen</p>'}
                    </div>
                </div>
            </div>
        `;

        // Update nav badge
        updateNavBadge(summary.uncategorized_count);

    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>Fehler beim Laden: ${error.message}</p></div>`;
    }
}

function updateNavBadge(count) {
    const badge = document.querySelector('.nav-badge');
    if (badge) {
        if (count > 0) {
            badge.textContent = count;
            badge.classList.remove('hidden');
        } else {
            badge.classList.add('hidden');
        }
    }
}

async function refreshNavBadge() {
    try {
        const summary = await api.getDashboardSummary(selectedAccountId, selectedProfileId);
        updateNavBadge(summary.uncategorized_count);
    } catch (e) {
        // Silently fail
    }
}

// Load accounts into global filter dropdown
async function loadAccountsDropdown() {
    try {
        accounts = await api.getAccounts();
        const dropdown = document.getElementById('global-account-filter');

        if (dropdown && accounts.length > 0) {
            dropdown.innerHTML = `
                <option value="">Alle Konten</option>
                ${accounts.map(acc => `
                    <option value="${acc.id}">${acc.name}${acc.bank_name ? ' (' + acc.bank_name + ')' : ''}</option>
                `).join('')}
            `;

            // Show the selector only if there are multiple accounts
            const selector = document.querySelector('.account-selector');
            if (selector) {
                if (accounts.length > 1) {
                    selector.style.display = 'block';
                } else {
                    selector.style.display = 'none';
                }
            }
        }
    } catch (error) {
        console.error('Failed to load accounts:', error);
        accounts = [];
    }
}

// Handle account filter change
function onAccountFilterChange() {
    const dropdown = document.getElementById('global-account-filter');
    const value = dropdown.value;

    selectedAccountId = value ? parseInt(value) : null;

    // Update header to show selected account
    updateAccountHeader();

    // Reload current page data with new filter
    switch (currentPage) {
        case 'dashboard':
            loadDashboard();
            break;
        case 'transactions':
            transactionFilters.page = 1; // Reset to first page
            loadTransactions();
            break;
        case 'statistics':
            loadStatistics();
            break;
    }
}

// Update account indicator in header (optional visual feedback)
function updateAccountHeader() {
    const dropdown = document.getElementById('global-account-filter');
    const selectedOption = dropdown.options[dropdown.selectedIndex];

    // Could add visual indication of selected account
    // For now, the dropdown itself shows the selection
}

// Helper to get current account ID for API calls
function getSelectedAccountId() {
    return selectedAccountId;
}

// Start app when DOM is ready
document.addEventListener('DOMContentLoaded', init);
