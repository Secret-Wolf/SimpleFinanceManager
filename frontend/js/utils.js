// Utility Functions

// Format currency in German format
function formatCurrency(amount, currency = 'EUR') {
    const num = parseFloat(amount) || 0;
    return new Intl.NumberFormat('de-DE', {
        style: 'currency',
        currency: currency
    }).format(num);
}

// Format date in German format
function formatDate(dateStr) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return new Intl.DateTimeFormat('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
    }).format(date);
}

// Format date for input fields (YYYY-MM-DD)
function formatDateInput(date) {
    if (!date) return '';
    const d = new Date(date);
    return d.toISOString().split('T')[0];
}

// Parse German date string
function parseGermanDate(dateStr) {
    if (!dateStr) return null;
    const parts = dateStr.split('.');
    if (parts.length !== 3) return null;
    return new Date(parts[2], parts[1] - 1, parts[0]);
}

// Get period dates
function getPeriodDates(period) {
    const today = new Date();
    let start, end;

    switch (period) {
        case 'week':
            const dayOfWeek = today.getDay() || 7;
            start = new Date(today);
            start.setDate(today.getDate() - dayOfWeek + 1);
            end = today;
            break;

        case 'month':
            start = new Date(today.getFullYear(), today.getMonth(), 1);
            end = today;
            break;

        case 'quarter':
            const quarter = Math.floor(today.getMonth() / 3);
            start = new Date(today.getFullYear(), quarter * 3, 1);
            end = today;
            break;

        case 'year':
            start = new Date(today.getFullYear(), 0, 1);
            end = today;
            break;

        default:
            start = new Date(today.getFullYear(), today.getMonth(), 1);
            end = today;
    }

    return {
        start: formatDateInput(start),
        end: formatDateInput(end)
    };
}

// Truncate text
function truncate(str, length = 50) {
    if (!str) return '';
    if (str.length <= length) return str;
    return str.substring(0, length) + '...';
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Show toast notification
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container') || createToastContainer();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;margin-left:auto;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
        </button>
    `;

    container.appendChild(toast);

    // Auto remove after 5 seconds
    setTimeout(() => {
        toast.remove();
    }, 5000);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
    return container;
}

// Modal functions
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
        document.body.style.overflow = '';
    }
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal-overlay')) {
        e.target.classList.remove('active');
        document.body.style.overflow = '';
    }
});

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const activeModal = document.querySelector('.modal-overlay.active');
        if (activeModal) {
            activeModal.classList.remove('active');
            document.body.style.overflow = '';
        }
    }
});

// Generate category select options
function generateCategoryOptions(categories, selectedId = null, level = 0) {
    let html = '';

    for (const cat of categories) {
        const prefix = level > 0 ? '&nbsp;&nbsp;'.repeat(level) + '↳ ' : '';
        const selected = cat.id === selectedId ? 'selected' : '';
        html += `<option value="${cat.id}" ${selected}>${prefix}${cat.name}</option>`;

        if (cat.children && cat.children.length > 0) {
            html += generateCategoryOptions(cat.children, selectedId, level + 1);
        }
    }

    return html;
}

// Build flat category list from tree
function flattenCategories(categories, result = []) {
    for (const cat of categories) {
        result.push(cat);
        if (cat.children && cat.children.length > 0) {
            flattenCategories(cat.children, result);
        }
    }
    return result;
}

// Calculate percentage change
function percentChange(current, previous) {
    if (!previous || previous === 0) return null;
    return ((current - previous) / Math.abs(previous)) * 100;
}

// Format percentage
function formatPercent(value) {
    if (value === null) return '-';
    const prefix = value > 0 ? '+' : '';
    return `${prefix}${value.toFixed(1)}%`;
}

// Color utilities
function adjustColor(color, amount) {
    const clamp = (num) => Math.min(255, Math.max(0, num));

    let hex = color.replace('#', '');
    if (hex.length === 3) {
        hex = hex.split('').map(c => c + c).join('');
    }

    const num = parseInt(hex, 16);
    const r = clamp((num >> 16) + amount);
    const g = clamp(((num >> 8) & 0x00FF) + amount);
    const b = clamp((num & 0x0000FF) + amount);

    return `#${(1 << 24 | r << 16 | g << 8 | b).toString(16).slice(1)}`;
}

// Random color generator
function randomColor() {
    const colors = [
        '#EF4444', '#F97316', '#F59E0B', '#EAB308', '#84CC16',
        '#22C55E', '#10B981', '#14B8A6', '#06B6D4', '#0EA5E9',
        '#3B82F6', '#6366F1', '#8B5CF6', '#A855F7', '#D946EF',
        '#EC4899', '#F43F5E'
    ];
    return colors[Math.floor(Math.random() * colors.length)];
}
