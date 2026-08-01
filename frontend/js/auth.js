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
    // Offene Modals schließen (z.B. Profil beim Logout oder bei Session-Ablauf),
    // sonst bleiben sie über dem Login-Screen liegen und sperren den Body-Scroll
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
    document.body.style.overflow = '';

    // 2FA-Feld zurücksetzen (wird erst nach Passwort-Prüfung wieder eingeblendet)
    const totpGroup = document.getElementById('login-totp-group');
    if (totpGroup) {
        totpGroup.classList.add('hidden');
        document.getElementById('login-totp').value = '';
    }

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
    const totpGroup = document.getElementById('login-totp-group');
    const totpInput = document.getElementById('login-totp');

    errorEl.textContent = '';
    submitBtn.disabled = true;

    const body = { email, password };
    if (!totpGroup.classList.contains('hidden') && totpInput.value.trim()) {
        body.totp_code = totpInput.value.trim();
    }

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        if (response.ok) {
            const data = await response.json();

            // Passwort ok, aber 2FA aktiv: Code-Feld einblenden und erneut senden lassen
            if (data.totp_required) {
                totpGroup.classList.remove('hidden');
                totpInput.value = '';
                totpInput.focus();
                errorEl.textContent = 'Bitte den 2FA-Code aus deiner Authenticator-App eingeben.';
                return;
            }

            totpGroup.classList.add('hidden');
            totpInput.value = '';
            currentUser = data.user;
            showApp();
            init();
        } else if (response.status === 429) {
            errorEl.textContent = 'Zu viele Versuche. Bitte warte einen Moment.';
        } else {
            const error = await response.json().catch(() => ({}));
            errorEl.textContent = error.detail || 'Login fehlgeschlagen';
            if (!totpGroup.classList.contains('hidden')) {
                totpInput.value = '';
                totpInput.focus();
            }
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
    showLogin();  // schließt auch ein evtl. offenes Profil-Modal
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

    // 2FA-Status laden (asynchron, blockiert das Modal nicht)
    refreshTotpStatus();

    openModal('user-profile-modal');
}

// --- Zwei-Faktor-Authentifizierung (TOTP) ------------------------------------

let _totpEnabled = false;
let _totpMode = 'enable'; // 'enable' | 'disable'

async function refreshTotpStatus() {
    const textEl = document.getElementById('totp-status-text');
    const hintEl = document.getElementById('totp-status-hint');
    const btn = document.getElementById('totp-toggle-btn');
    if (!textEl) return;

    try {
        const status = await api.getTotpStatus();
        _totpEnabled = status.enabled;
        if (status.enabled) {
            textEl.textContent = '2FA ist aktiv ✓';
            hintEl.textContent = `${status.recovery_codes_remaining} Recovery-Codes übrig`;
            btn.textContent = '2FA deaktivieren';
            btn.classList.remove('btn-primary');
            btn.classList.add('btn-danger');
        } else {
            textEl.textContent = '2FA ist nicht aktiv';
            hintEl.textContent = 'Empfohlen: schützt den Login zusätzlich zum Passwort.';
            btn.textContent = '2FA einrichten';
            btn.classList.add('btn-primary');
            btn.classList.remove('btn-danger');
        }
    } catch (e) {
        textEl.textContent = '2FA-Status nicht verfügbar';
        hintEl.textContent = '';
    }
}

function showTotpStep(step) {
    ['start', 'verify', 'recovery'].forEach(s => {
        document.getElementById('totp-step-' + s).classList.toggle('hidden', s !== step);
    });
}

function startTotpFlow() {
    _totpMode = _totpEnabled ? 'disable' : 'enable';

    document.getElementById('totp-modal-title').textContent =
        _totpMode === 'enable' ? '2FA einrichten' : '2FA deaktivieren';
    document.getElementById('totp-start-text').textContent = _totpMode === 'enable'
        ? 'Bestätige zunächst dein Passwort, um die Einrichtung zu starten.'
        : 'Zum Deaktivieren Passwort und einen gültigen 2FA-Code (oder Recovery-Code) eingeben.';
    document.getElementById('totp-password').value = '';
    document.getElementById('totp-disable-code').value = '';
    document.getElementById('totp-verify-code').value = '';
    document.getElementById('totp-modal-error').textContent = '';
    document.getElementById('totp-disable-code-group').classList.toggle('hidden', _totpMode === 'enable');

    const nextBtn = document.getElementById('totp-next-btn');
    nextBtn.dataset.action = 'submitTotpStart';
    nextBtn.textContent = _totpMode === 'enable' ? 'Weiter' : '2FA deaktivieren';
    nextBtn.classList.remove('hidden');
    document.getElementById('totp-cancel-btn').textContent = 'Abbrechen';

    showTotpStep('start');
    openModal('totp-modal');
    setTimeout(() => document.getElementById('totp-password').focus(), 100);
}

async function submitTotpStart() {
    const password = document.getElementById('totp-password').value;
    const errorEl = document.getElementById('totp-modal-error');
    errorEl.textContent = '';

    if (!password) {
        errorEl.textContent = 'Bitte Passwort eingeben.';
        return;
    }

    try {
        if (_totpMode === 'enable') {
            const data = await api.setupTotp(password);
            // QR-SVG kommt vom eigenen Server (Server-generiert, kein User-Input)
            document.getElementById('totp-qr').innerHTML = data.qr_svg;
            document.getElementById('totp-secret').textContent = data.secret;
            showTotpStep('verify');
            const nextBtn = document.getElementById('totp-next-btn');
            nextBtn.dataset.action = 'submitTotpVerify';
            nextBtn.textContent = 'Aktivieren';
            setTimeout(() => document.getElementById('totp-verify-code').focus(), 100);
        } else {
            const code = document.getElementById('totp-disable-code').value.trim();
            if (!code) {
                errorEl.textContent = 'Bitte 2FA-Code eingeben.';
                return;
            }
            await api.disableTotp(password, code);
            closeModal('totp-modal');
            showToast('2FA deaktiviert', 'success');
            refreshTotpStatus();
        }
    } catch (error) {
        errorEl.textContent = error.message;
    }
}

async function submitTotpVerify() {
    const code = document.getElementById('totp-verify-code').value.trim();
    const errorEl = document.getElementById('totp-modal-error');
    errorEl.textContent = '';

    if (!code) {
        errorEl.textContent = 'Bitte den Code aus der App eingeben.';
        return;
    }

    try {
        const result = await api.enableTotp(code);
        document.getElementById('totp-recovery-codes').textContent = result.recovery_codes.join('\n');
        showTotpStep('recovery');
        document.getElementById('totp-next-btn').classList.add('hidden');
        document.getElementById('totp-cancel-btn').textContent = 'Fertig';
        showToast('2FA aktiviert', 'success');
        refreshTotpStatus();
    } catch (error) {
        errorEl.textContent = error.message;
    }
}

function copyRecoveryCodes() {
    const text = document.getElementById('totp-recovery-codes').textContent;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
            () => showToast('Recovery-Codes kopiert', 'success'),
            () => showToast('Kopieren nicht möglich — bitte manuell notieren', 'error')
        );
    } else {
        showToast('Kopieren nicht möglich — bitte manuell notieren', 'error');
    }
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

// Dark Mode — default follows the OS; a manual toggle stores an explicit override.
function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    // PWA: Statusleisten-/Titelleistenfarbe mitziehen (muss --bg-primary entsprechen)
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'dark' ? '#172033' : '#ffffff');
}

function systemPrefersDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function effectiveTheme() {
    const saved = localStorage.getItem('theme'); // 'light' | 'dark' | null (=> follow system)
    if (saved === 'light' || saved === 'dark') return saved;
    return systemPrefersDark() ? 'dark' : 'light';
}

function toggleDarkMode() {
    const isDark = document.getElementById('dark-mode-toggle').checked;
    const theme = isDark ? 'dark' : 'light';
    applyTheme(theme);
    localStorage.setItem('theme', theme); // explicit user override
}

function initTheme() {
    applyTheme(effectiveTheme());
    // While following the system (no explicit override), react to OS theme changes live.
    if (window.matchMedia) {
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        const onChange = () => {
            if (!localStorage.getItem('theme')) applyTheme(systemPrefersDark() ? 'dark' : 'light');
        };
        if (mq.addEventListener) mq.addEventListener('change', onChange);
        else if (mq.addListener) mq.addListener(onChange); // older browsers
    }
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
