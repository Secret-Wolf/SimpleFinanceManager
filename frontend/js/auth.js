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
