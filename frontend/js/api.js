// API Client for Finanzmanager

const API_BASE = '/api';

class ApiClient {
    async request(endpoint, options = {}) {
        const url = `${API_BASE}${endpoint}`;

        const config = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };

        if (options.body && typeof options.body === 'object' && !(options.body instanceof FormData)) {
            config.body = JSON.stringify(options.body);
        }

        if (options.body instanceof FormData) {
            delete config.headers['Content-Type'];
        }

        try {
            const response = await fetch(url, config);

            if (!response.ok) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }

    // Transactions
    async getTransactions(params = {}) {
        const query = new URLSearchParams();
        Object.entries(params).forEach(([key, value]) => {
            if (value !== null && value !== undefined && value !== '') {
                query.append(key, value);
            }
        });
        return this.request(`/transactions?${query}`);
    }

    async getTransaction(id) {
        return this.request(`/transactions/${id}`);
    }

    async updateTransaction(id, data) {
        return this.request(`/transactions/${id}`, {
            method: 'PATCH',
            body: data
        });
    }

    async deleteTransaction(id) {
        return this.request(`/transactions/${id}`, {
            method: 'DELETE'
        });
    }

    async splitTransaction(id, parts) {
        return this.request(`/transactions/${id}/split`, {
            method: 'POST',
            body: { parts }
        });
    }

    async bulkCategorize(transactionIds, categoryId) {
        return this.request(`/transactions/bulk-categorize?category_id=${categoryId}`, {
            method: 'POST',
            body: transactionIds
        });
    }

    async createManualTransaction(data) {
        return this.request('/transactions/manual', {
            method: 'POST',
            body: data
        });
    }

    // Categories
    async getCategories(flat = false) {
        return this.request(`/categories?flat=${flat}`);
    }

    async getCategory(id) {
        return this.request(`/categories/${id}`);
    }

    async createCategory(data) {
        return this.request('/categories', {
            method: 'POST',
            body: data
        });
    }

    async updateCategory(id, data) {
        return this.request(`/categories/${id}`, {
            method: 'PATCH',
            body: data
        });
    }

    async deleteCategory(id, moveToId = null) {
        const query = moveToId ? `?move_to_category_id=${moveToId}` : '';
        return this.request(`/categories/${id}${query}`, {
            method: 'DELETE'
        });
    }

    async initDefaultCategories() {
        return this.request('/categories/init-defaults', {
            method: 'POST'
        });
    }

    // Rules
    async getRules() {
        return this.request('/rules');
    }

    async getRule(id) {
        return this.request(`/rules/${id}`);
    }

    async createRule(data) {
        return this.request('/rules', {
            method: 'POST',
            body: data
        });
    }

    async updateRule(id, data) {
        return this.request(`/rules/${id}`, {
            method: 'PATCH',
            body: data
        });
    }

    async deleteRule(id) {
        return this.request(`/rules/${id}`, {
            method: 'DELETE'
        });
    }

    async applyRules() {
        return this.request('/rules/apply', {
            method: 'POST'
        });
    }

    async createRuleFromTransaction(transactionId, categoryId, matchType = 'counterpart_name') {
        return this.request(`/rules/from-transaction/${transactionId}?category_id=${categoryId}&match_type=${matchType}`, {
            method: 'POST'
        });
    }

    // Import
    async uploadCSV(file, autoCategorize = true) {
        const formData = new FormData();
        formData.append('file', file);

        return this.request(`/import?auto_categorize=${autoCategorize}`, {
            method: 'POST',
            body: formData
        });
    }

    async getImports(limit = 20) {
        return this.request(`/import?limit=${limit}`);
    }

    // Statistics
    async getDashboardSummary() {
        return this.request('/stats/summary');
    }

    async getStatsByCategory(params = {}) {
        const query = new URLSearchParams(params);
        return this.request(`/stats/by-category?${query}`);
    }

    async getStatsOverTime(params = {}) {
        const query = new URLSearchParams(params);
        return this.request(`/stats/over-time?${query}`);
    }
}

// Export singleton instance
const api = new ApiClient();
