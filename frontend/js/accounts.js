// Accounts Module

async function loadAccounts() {
    const container = document.getElementById('accounts-list');
    const totalBalanceEl = document.getElementById('total-balance');
    const accountCountEl = document.getElementById('account-count');

    try {
        const data = await api.getAccountsSummary();

        // Update summary
        totalBalanceEl.textContent = formatCurrency(data.total_balance);
        totalBalanceEl.className = `value ${data.total_balance >= 0 ? 'positive' : 'negative'}`;
        accountCountEl.textContent = data.account_count;

        if (data.accounts.length === 0) {
            container.innerHTML = `
                <div class="card" style="grid-column: 1 / -1; text-align: center; padding: 40px;">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="width: 64px; height: 64px; margin: 0 auto 16px; opacity: 0.5;">
                        <rect x="2" y="4" width="20" height="16" rx="2"></rect>
                        <path d="M7 15h0M2 9h20"></path>
                    </svg>
                    <h3 style="margin-bottom: 8px;">Noch keine Konten</h3>
                    <p style="color: var(--text-secondary);">Importiere eine CSV-Datei, um dein erstes Konto anzulegen.</p>
                    <button class="btn btn-primary mt-4" data-action="navigateTo" data-value="import">CSV importieren</button>
                </div>
            `;
            return;
        }

        container.innerHTML = data.accounts.map(account => `
            <div class="card account-card" data-action="showAccountDetail" data-id="${account.id}">
                <div class="account-header">
                    <div class="account-bank">
                        <span class="bank-icon">${getBankIcon(account.bank_name)}</span>
                        <span class="bank-name">${escapeHtml(account.bank_name || 'Unbekannte Bank')}</span>
                    </div>
                    <span class="account-type-badge">${escapeHtml(getAccountTypeName(account.account_type))}</span>
                </div>
                <div class="account-name">${escapeHtml(account.name)}</div>
                <div class="account-iban">${escapeHtml(formatIban(account.iban))}</div>
                <div class="account-balance ${account.balance >= 0 ? 'positive' : 'negative'}">
                    ${account.balance !== null ? formatCurrency(account.balance) : 'Kein Saldo'}
                </div>
                <div class="account-stats">
                    <div class="account-stat">
                        <span class="stat-label">Transaktionen</span>
                        <span class="stat-value">${account.transaction_count}</span>
                    </div>
                    <div class="account-stat">
                        <span class="stat-label">Einnahmen (Monat)</span>
                        <span class="stat-value positive">${formatCurrency(account.income_this_month)}</span>
                    </div>
                    <div class="account-stat">
                        <span class="stat-label">Ausgaben (Monat)</span>
                        <span class="stat-value negative">${formatCurrency(account.expenses_this_month)}</span>
                    </div>
                </div>
            </div>
        `).join('');

    } catch (error) {
        container.innerHTML = `<div class="card" style="grid-column: 1 / -1;"><p style="color: var(--danger-color)">Fehler: ${escapeHtml(error.message)}</p></div>`;
    }
}

function getBankIcon(bankName) {
    if (!bankName) return '🏦';

    const name = bankName.toLowerCase();
    if (name.includes('ing')) return '🦁';
    if (name.includes('volksbank') || name.includes('vr')) return '🏛️';
    if (name.includes('sparkasse')) return '🔴';
    if (name.includes('commerzbank')) return '🟡';
    if (name.includes('deutsche bank')) return '🔵';
    if (name.includes('dkb')) return '💳';
    if (name.includes('n26')) return '📱';
    if (name.includes('comdirect')) return '📊';
    return '🏦';
}

function getAccountTypeName(type) {
    const types = {
        'giro': 'Girokonto',
        'savings': 'Sparkonto',
        'credit': 'Kreditkarte',
        'depot': 'Depot'
    };
    return types[type] || type || 'Konto';
}

function formatIban(iban) {
    if (!iban) return '-';
    // Format: DE75 5001 0517 5456 5425 61
    return iban.replace(/(.{4})/g, '$1 ').trim();
}

async function showAccountDetail(accountId) {
    try {
        const account = await api.getAccount(accountId);

        // Set global account filter
        selectedAccountId = accountId;

        // Update dropdown to match
        const dropdown = document.getElementById('global-account-filter');
        if (dropdown) {
            dropdown.value = accountId;
        }

        // Reset transaction filters page
        transactionFilters.page = 1;

        // Navigate to transactions (will use selectedAccountId)
        navigateTo('transactions');

        showToast(`Transaktionen für "${account.name}" werden angezeigt`, 'info');

    } catch (error) {
        showToast('Fehler beim Laden der Kontodetails', 'error');
    }
}

function showCreateAccountModal() {
    document.getElementById('create-account-name').value = '';
    document.getElementById('create-account-type').value = 'giro';
    openModal('create-account-modal');
}

async function saveNewAccount() {
    const name = document.getElementById('create-account-name').value.trim();
    const accountType = document.getElementById('create-account-type').value;

    if (!name) {
        showToast('Bitte Kontoname eingeben', 'error');
        return;
    }

    try {
        await api.createAccount({ name, account_type: accountType });
        showToast('Konto erstellt', 'success');
        closeModal('create-account-modal');
        loadAccounts();
        await loadAccountsDropdown();
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}
