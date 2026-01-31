/**
 * Crypto Trading Bot - API Client
 */

class ApiClient {
    constructor() {
        this.baseUrl = 'http://127.0.0.1:8765';
        this.connected = false;
    }
    
    /**
     * Initialize the API client
     */
    async init() {
        // Get API URL from Electron if available
        if (window.electronAPI) {
            try {
                this.baseUrl = await window.electronAPI.getApiUrl();
            } catch (e) {
                console.log('Using default API URL');
            }
        }
        
        // Check connection
        await this.checkConnection();
    }
    
    /**
     * Check if API server is connected
     */
    async checkConnection() {
        try {
            const response = await this.get('/api/health');
            this.connected = response && response.status === 'ok';
            return this.connected;
        } catch (error) {
            this.connected = false;
            return false;
        }
    }
    
    /**
     * Make a GET request
     */
    async get(endpoint) {
        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error(`GET ${endpoint} failed:`, error);
            throw error;
        }
    }
    
    /**
     * Make a POST request
     */
    async post(endpoint, data = {}) {
        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(data)
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || `HTTP ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error(`POST ${endpoint} failed:`, error);
            throw error;
        }
    }
    
    /**
     * Make a DELETE request
     */
    async delete(endpoint) {
        try {
            const response = await fetch(`${this.baseUrl}${endpoint}`, {
                method: 'DELETE',
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error(`DELETE ${endpoint} failed:`, error);
            throw error;
        }
    }
    
    // ============== Strategies ==============
    
    async getStrategies() {
        return await this.get('/api/strategies');
    }
    
    async getStrategy(name) {
        return await this.get(`/api/strategies/${encodeURIComponent(name)}`);
    }
    
    // ============== Exchanges ==============
    
    async getExchanges() {
        return await this.get('/api/exchanges');
    }
    
    async addExchange(config) {
        return await this.post('/api/exchanges', config);
    }
    
    async removeExchange(exchangeId) {
        return await this.delete(`/api/exchanges/${exchangeId}`);
    }
    
    // ============== Backtest ==============
    
    async startBacktest(config) {
        return await this.post('/api/backtest', config);
    }
    
    async getBacktestStatus(jobId) {
        return await this.get(`/api/backtest/${jobId}`);
    }
    
    async listBacktests() {
        return await this.get('/api/backtest');
    }
    
    // ============== Live Trading ==============
    
    async startLiveTrading(config) {
        return await this.post('/api/live/start', config);
    }
    
    async stopLiveTrading() {
        return await this.post('/api/live/stop');
    }
    
    async getLiveStatus() {
        return await this.get('/api/live/status');
    }
    
    async getLiveTrades() {
        return await this.get('/api/live/trades');
    }
    
    async getLiveBalance() {
        return await this.get('/api/live/balance');
    }
    
    // ============== Data ==============
    
    async getSymbols(exchangeId) {
        return await this.get(`/api/symbols/${exchangeId}`);
    }
    
    async getTimeframes() {
        return await this.get('/api/timeframes');
    }
}

// Global API client instance
const api = new ApiClient();
