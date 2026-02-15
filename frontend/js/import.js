// Import Module

function initImportPage() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');

    // Populate import profile dropdown
    populateImportProfileDropdown();

    // Drag and drop events
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            handleFileUpload(files[0]);
        }
    });

    dropzone.addEventListener('click', () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileUpload(e.target.files[0]);
        }
    });

    // Load import history
    loadImportHistory();
}

async function handleFileUpload(file) {
    if (!file.name.endsWith('.csv')) {
        showToast('Nur CSV-Dateien werden unterstützt', 'error');
        return;
    }

    const dropzone = document.getElementById('dropzone');
    const bankFormat = document.getElementById('bank-format').value;
    const importProfileSelect = document.getElementById('import-profile');
    // Use import dropdown value, fallback to global profile filter
    const profileId = (importProfileSelect && importProfileSelect.value) ? importProfileSelect.value : (selectedProfileId || null);
    const originalContent = dropzone.innerHTML;

    dropzone.innerHTML = `
        <div class="spinner"></div>
        <h4>Importiere ${file.name}...</h4>
        <p style="font-size: 0.875rem; color: var(--text-secondary);">Format: ${getBankFormatName(bankFormat)}</p>
    `;

    try {
        const result = await api.uploadCSV(file, bankFormat, true, profileId || null);

        dropzone.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="var(--success-color)" stroke-width="2" style="width: 48px; height: 48px;">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                <polyline points="22 4 12 14.01 9 11.01"></polyline>
            </svg>
            <h4>Import erfolgreich!</h4>
            <p>
                ${result.transactions_new} neu importiert<br>
                ${result.transactions_duplicate} Duplikate übersprungen<br>
                ${result.transactions_error > 0 ? `${result.transactions_error} Fehler` : ''}
            </p>
            <button class="btn btn-primary mt-4" onclick="navigateTo('transactions')">Transaktionen anzeigen</button>
        `;

        // Refresh import history
        loadImportHistory();

        // Reset after 10 seconds
        setTimeout(() => {
            dropzone.innerHTML = originalContent;
        }, 10000);

    } catch (error) {
        dropzone.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="var(--danger-color)" stroke-width="2" style="width: 48px; height: 48px;">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="15" y1="9" x2="9" y2="15"></line>
                <line x1="9" y1="9" x2="15" y2="15"></line>
            </svg>
            <h4>Import fehlgeschlagen</h4>
            <p>${error.message}</p>
            <button class="btn btn-secondary mt-4" onclick="resetDropzone()">Erneut versuchen</button>
        `;
    }
}

function resetDropzone() {
    const dropzone = document.getElementById('dropzone');
    dropzone.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
            <polyline points="17 8 12 3 7 8"></polyline>
            <line x1="12" y1="3" x2="12" y2="15"></line>
        </svg>
        <h4>CSV-Datei hierher ziehen</h4>
        <p>oder klicken zum Auswählen</p>
        <p style="margin-top: 12px; font-size: 0.75rem;">Unterstützt: Volksbank, ING</p>
    `;
}

function getBankFormatName(format) {
    const names = {
        'auto': 'Automatisch erkennen',
        'volksbank': 'Volksbank / VR-Bank',
        'ing': 'ING'
    };
    return names[format] || format;
}

async function loadImportHistory() {
    const container = document.getElementById('import-history');

    try {
        const imports = await api.getImports(10);

        if (imports.length === 0) {
            container.innerHTML = '<p style="color: var(--text-secondary); text-align: center;">Noch keine Importe</p>';
            return;
        }

        container.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Datum</th>
                        <th>Datei</th>
                        <th>Neu</th>
                        <th>Duplikate</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    ${imports.map(imp => `
                        <tr>
                            <td>${formatDate(imp.import_date)}</td>
                            <td>${imp.filename || '-'}</td>
                            <td>${imp.transactions_new}</td>
                            <td>${imp.transactions_duplicate}</td>
                            <td>
                                <span style="color: ${getStatusColor(imp.status)}">
                                    ${getStatusText(imp.status)}
                                </span>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;

    } catch (error) {
        container.innerHTML = `<p style="color: var(--danger-color)">Fehler: ${error.message}</p>`;
    }
}

function getStatusColor(status) {
    switch (status) {
        case 'success': return 'var(--success-color)';
        case 'partial': return 'var(--warning-color)';
        case 'failed': return 'var(--danger-color)';
        default: return 'var(--text-secondary)';
    }
}

function getStatusText(status) {
    switch (status) {
        case 'success': return 'Erfolgreich';
        case 'partial': return 'Teilweise';
        case 'failed': return 'Fehlgeschlagen';
        default: return status;
    }
}

function populateImportProfileDropdown() {
    const dropdown = document.getElementById('import-profile');
    if (!dropdown || !profiles || profiles.length === 0) return;

    dropdown.innerHTML = `
        <option value="">Kein Profil</option>
        ${profiles.map(p => `
            <option value="${p.id}" ${selectedProfileId === p.id ? 'selected' : ''}>${p.name}${p.is_admin ? ' (Admin)' : ''}</option>
        `).join('')}
    `;
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    // Check if import page exists and init
    if (document.getElementById('dropzone')) {
        initImportPage();
    }
});
