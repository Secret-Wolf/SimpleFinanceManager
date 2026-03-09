// Event Handlers - Replaces inline onclick/onchange/oninput for CSP compliance
// Uses event delegation so it works with dynamically generated content too.

(function () {
    'use strict';

    // --- Click Delegation ---
    document.addEventListener('click', function (e) {
        // Modal close (X) buttons – close nearest modal-overlay
        var closeBtn = e.target.closest('.modal-close');
        if (closeBtn) {
            var modal = closeBtn.closest('.modal-overlay');
            if (modal) closeModal(modal.id);
            return;
        }

        // data-close-modal buttons (cancel buttons)
        var closeModalBtn = e.target.closest('[data-close-modal]');
        if (closeModalBtn) {
            closeModal(closeModalBtn.dataset.closeModal);
            return;
        }

        // data-action buttons
        var actionEl = e.target.closest('[data-action]');
        if (!actionEl) return;

        var action = actionEl.dataset.action;

        // Check custom handlers first
        if (CLICK_ACTIONS[action]) {
            CLICK_ACTIONS[action](actionEl);
            return;
        }

        // Fallback: call global function by name with extracted params
        if (typeof window[action] === 'function') {
            var args = extractArgs(actionEl);
            window[action].apply(null, args);
        }
    });

    // Extract arguments from data attributes in order
    function extractArgs(el) {
        var args = [];
        if (el.dataset.id !== undefined) args.push(parseValue(el.dataset.id));
        if (el.dataset.value !== undefined) args.push(parseValue(el.dataset.value));
        if (el.dataset.arg2 !== undefined) args.push(parseValue(el.dataset.arg2));
        return args;
    }

    function parseValue(v) {
        if (v === 'true') return true;
        if (v === 'false') return false;
        if (v !== '' && !isNaN(v)) return Number(v);
        return v;
    }

    // Custom click handlers for complex actions
    var CLICK_ACTIONS = {
        clearSelection: function () {
            selectedTransactions.clear();
            updateBulkActions();
            loadTransactions();
        },
        saveAndCloseTransactionDetail: function () {
            saveTransactionDetails();
            closeModal('transaction-detail-modal');
        },
        removeSplitPart: function (el) {
            el.closest('.split-part').remove();
            updateSplitRemaining();
        },
        removeToast: function (el) {
            var toast = el.closest('.toast');
            if (toast) toast.remove();
        },
        navigateToTransactionsUncategorized: function () {
            navigateTo('transactions');
            document.getElementById('uncategorized-filter').checked = true;
            loadTransactions();
        },
        viewSharedExpenses: function (el) {
            var id = parseInt(el.dataset.id);
            var memberCount = parseInt(el.dataset.memberCount || '2');
            viewSharedExpenses(id, memberCount);
        },
        handleLeaveHousehold: function (el) {
            handleLeaveHousehold(parseInt(el.dataset.id), parseInt(el.dataset.userId));
        },
        handleRemoveMember: function (el) {
            handleRemoveMember(parseInt(el.dataset.id), parseInt(el.dataset.userId));
        },
        setQuickPeriod: function (el) {
            setQuickPeriod(el.dataset.value);
        },
        showAccountDetail: function (el) {
            showAccountDetail(parseInt(el.dataset.id));
        },
        navigateTo: function (el) {
            navigateTo(el.dataset.value);
        }
    };

    // --- Change Delegation ---
    document.addEventListener('change', function (e) {
        var el = e.target.closest('[data-onchange]');
        if (!el) return;

        var action = el.dataset.onchange;
        if (action === 'changeHouseholdExpensesPeriod') {
            changeHouseholdExpensesPeriod(
                el.value,
                parseInt(el.dataset.householdId),
                parseInt(el.dataset.memberCount),
                el.dataset.householdName || ''
            );
            return;
        }
        if (action === 'applyTransactionFilters') {
            applyTransactionFilters();
            return;
        }
        if (typeof window[action] === 'function') {
            window[action]();
        }
    });

    // --- Input Delegation ---
    var _debounceTimers = {};
    document.addEventListener('input', function (e) {
        var el = e.target.closest('[data-oninput]');
        if (!el) return;

        var action = el.dataset.oninput;
        var debounceMs = parseInt(el.dataset.debounce || '0');

        if (debounceMs > 0) {
            var key = el.id || action;
            clearTimeout(_debounceTimers[key]);
            _debounceTimers[key] = setTimeout(function () {
                if (typeof window[action] === 'function') window[action]();
            }, debounceMs);
        } else {
            if (typeof window[action] === 'function') window[action]();
        }
    });

    // --- Static element listeners by ID ---
    document.addEventListener('DOMContentLoaded', function () {
        bind('change', 'global-account-filter', function () { onAccountFilterChange(); });
        bind('change', 'tx-start-date', function () { applyTransactionFilters(); });
        bind('change', 'tx-end-date', function () { applyTransactionFilters(); });
        bind('change', 'tx-category-filter', function () { applyTransactionFilters(); });
        bind('change', 'tx-amount-type', function () { applyTransactionFilters(); });
        bind('change', 'uncategorized-filter', function () { applyTransactionFilters(); });
        bind('change', 'shared-filter', function () { applyTransactionFilters(); });
        bind('change', 'stats-period', function () { changeStatsPeriod(); });
        bind('change', 'detail-shared', function () { onSharedCheckboxChange(); });
        bind('change', 'dark-mode-toggle', function () { toggleDarkMode(); });

        // Search input with debounce
        var searchEl = document.getElementById('tx-search');
        if (searchEl) {
            var timer;
            searchEl.addEventListener('input', function () {
                clearTimeout(timer);
                timer = setTimeout(function () { applyTransactionFilters(); }, 300);
            });
        }

        // Select all transactions checkbox
        var selectAllCheckbox = document.getElementById('select-all-tx');
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', function () {
                selectAllTransactions();
            });
        }
    });

    function bind(event, id, fn) {
        var el = document.getElementById(id);
        if (el) el.addEventListener(event, fn);
    }
})();
