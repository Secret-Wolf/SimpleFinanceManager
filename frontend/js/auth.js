// Authentication Module

let currentUser = null;

async function checkAuth() {
    try {
        const response = await fetch('/api/auth/me');
        if (response.ok) {
            currentUser = await response.json();
            showApp();
            return true;
        }
    } catch (e) {
        // Ignore network errors
    }

    // Try refresh
    try {
        const refreshResponse = await fetch('/api/auth/refresh', { method: 'POST' });
        if (refreshResponse.ok) {
            const data = await refreshResponse.json();
            currentUser = data.user;
            showApp();
            return true;
        }
    } catch (e) {
        // Ignore
    }

    // Check if setup is needed
    try {
        const setupResponse = await fetch('/api/auth/setup-required');
        if (setupResponse.ok) {
            const data = await setupResponse.json();
            if (data.setup_required) {
                showSetup();
                return false;
            }
        }
    } catch (e) {
        // Ignore
    }

    showLogin();
    return false;
}

function showLogin() {
    document.getElementById('login-screen').classList.remove('hidden');
    document.getElementById('setup-screen').classList.add('hidden');
    document.getElementById('app-container').classList.add('hidden');
}

function showSetup() {
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('setup-screen').classList.remove('hidden');
    document.getElementById('app-container').classList.add('hidden');
}

function showApp() {
    document.getElementById('login-screen').classList.add('hidden');
    document.getElementById('setup-screen').classList.add('hidden');
    document.getElementById('app-container').classList.remove('hidden');

    // Update user display
    const userDisplay = document.getElementById('user-display-name');
    if (userDisplay && currentUser) {
        userDisplay.textContent = currentUser.display_name;
    }

    // Show/hide admin-only elements
    document.querySelectorAll('.admin-only').forEach(el => {
        if (currentUser && currentUser.is_admin) {
            el.classList.remove('hidden');
        } else {
            el.classList.add('hidden');
        }
    });
}

async function handleLogin(e) {
    e.preventDefault();
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    const errorEl = document.getElementById('login-error');
    const submitBtn = e.target.querySelector('button[type="submit"]');

    errorEl.textContent = '';
    submitBtn.disabled = true;

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });

        if (response.ok) {
            const data = await response.json();
            currentUser = data.user;
            showApp();
            init();
        } else if (response.status === 429) {
            errorEl.textContent = 'Zu viele Versuche. Bitte warte einen Moment.';
        } else {
            const error = await response.json().catch(() => ({}));
            errorEl.textContent = error.detail || 'Login fehlgeschlagen';
        }
    } catch (error) {
        errorEl.textContent = 'Verbindungsfehler';
    } finally {
        submitBtn.disabled = false;
    }
}

async function handleSetup(e) {
    e.preventDefault();
    const email = document.getElementById('setup-email').value.trim();
    const password = document.getElementById('setup-password').value;
    const passwordConfirm = document.getElementById('setup-password-confirm').value;
    const displayName = document.getElementById('setup-name').value.trim();
    const errorEl = document.getElementById('setup-error');
    const submitBtn = e.target.querySelector('button[type="submit"]');

    errorEl.textContent = '';

    if (password !== passwordConfirm) {
        errorEl.textContent = 'Passwörter stimmen nicht überein';
        return;
    }

    submitBtn.disabled = true;

    try {
        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, display_name: displayName }),
        });

        if (response.ok) {
            currentUser = await response.json();
            showApp();
            init();
        } else {
            const error = await response.json().catch(() => ({}));
            // Handle validation errors from Pydantic
            if (error.detail && Array.isArray(error.detail)) {
                errorEl.textContent = error.detail.map(d => d.msg).join('. ');
            } else {
                errorEl.textContent = error.detail || 'Registrierung fehlgeschlagen';
            }
        }
    } catch (error) {
        errorEl.textContent = 'Verbindungsfehler';
    } finally {
        submitBtn.disabled = false;
    }
}

async function handleLogout() {
    try {
        await fetch('/api/auth/logout', { method: 'POST' });
    } catch (e) {
        // Ignore
    }
    currentUser = null;
    showLogin();
}

// User Profile
function showUserProfile() {
    if (!currentUser) return;

    document.getElementById('profile-display-name').value = currentUser.display_name || '';
    document.getElementById('profile-email').value = currentUser.email || '';

    // Clear password fields
    document.getElementById('profile-current-password').value = '';
    document.getElementById('profile-new-password').value = '';
    document.getElementById('profile-new-password-confirm').value = '';

    // Set dark mode toggle
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    document.getElementById('dark-mode-toggle').checked = isDark;

    // Populate export account dropdown
    const exportAccountSelect = document.getElementById('export-account');
    if (exportAccountSelect && typeof accounts !== 'undefined') {
        exportAccountSelect.innerHTML = `
            <option value="">Alle Konten</option>
            ${accounts.map(acc => `<option value="${acc.id}">${acc.name}${acc.bank_name ? ' (' + acc.bank_name + ')' : ''}</option>`).join('')}
        `;
    }

    openModal('user-profile-modal');
}

async function saveUserProfile() {
    const displayName = document.getElementById('profile-display-name').value.trim();
    const email = document.getElementById('profile-email').value.trim();

    if (!displayName || !email) {
        showToast('Bitte alle Felder ausfüllen', 'error');
        return;
    }

    try {
        const response = await fetch('/api/auth/me', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: displayName, email: email }),
        });

        if (response.ok) {
            currentUser = await response.json();
            const userDisplay = document.getElementById('user-display-name');
            if (userDisplay) userDisplay.textContent = currentUser.display_name;
            showToast('Profil aktualisiert', 'success');
        } else {
            const error = await response.json().catch(() => ({}));
            showToast('Fehler: ' + (error.detail || 'Unbekannter Fehler'), 'error');
        }
    } catch (error) {
        showToast('Verbindungsfehler', 'error');
    }
}

async function changeUserPassword() {
    const currentPassword = document.getElementById('profile-current-password').value;
    const newPassword = document.getElementById('profile-new-password').value;
    const confirmPassword = document.getElementById('profile-new-password-confirm').value;

    if (!currentPassword || !newPassword) {
        showToast('Bitte alle Passwortfelder ausfüllen', 'error');
        return;
    }

    if (newPassword !== confirmPassword) {
        showToast('Neue Passwörter stimmen nicht überein', 'error');
        return;
    }

    if (newPassword.length < 12) {
        showToast('Passwort muss mindestens 12 Zeichen lang sein', 'error');
        return;
    }

    try {
        const response = await fetch('/api/auth/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
        });

        if (response.ok) {
            showToast('Passwort geändert', 'success');
            document.getElementById('profile-current-password').value = '';
            document.getElementById('profile-new-password').value = '';
            document.getElementById('profile-new-password-confirm').value = '';
        } else {
            const error = await response.json().catch(() => ({}));
            let detail = error.detail;
            if (Array.isArray(detail)) {
                detail = detail.map(d => d.msg).join('. ');
            }
            showToast('Fehler: ' + (detail || 'Unbekannter Fehler'), 'error');
        }
    } catch (error) {
        showToast('Verbindungsfehler', 'error');
    }
}

// Transaction Export
async function exportTransactions() {
    const accountId = document.getElementById('export-account').value;
    const startDate = document.getElementById('export-start-date').value;
    const endDate = document.getElementById('export-end-date').value;

    const params = new URLSearchParams();
    if (accountId) params.append('account_id', accountId);
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);

    try {
        const response = await fetch(`/api/transactions/export?${params}`);
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.detail || 'Export fehlgeschlagen');
        }

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `transaktionen-export-${new Date().toISOString().split('T')[0]}.csv`;
        link.click();
        URL.revokeObjectURL(url);

        showToast('Export erstellt', 'success');
    } catch (error) {
        showToast('Fehler: ' + error.message, 'error');
    }
}

// Dark Mode
function toggleDarkMode() {
    const isDark = document.getElementById('dark-mode-toggle').checked;
    const theme = isDark ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
}

function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
}

// Initialize theme immediately (before DOM ready)
initTheme();

// Initialize auth on page load
document.addEventListener('DOMContentLoaded', async () => {
    // Bind form handlers
    const loginForm = document.getElementById('login-form');
    if (loginForm) loginForm.addEventListener('submit', handleLogin);

    const setupForm = document.getElementById('setup-form');
    if (setupForm) setupForm.addEventListener('submit', handleSetup);

    // Check authentication status
    const isAuthed = await checkAuth();
    if (isAuthed) {
        init();
    }
});
