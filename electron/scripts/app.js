/**
 * Crypto Trading Bot - Main Application Logic
 */

// State
let currentPage = 'dashboard';
let strategies = [];
let currentBacktestJob = null;
let livePollingInterval = null;

// DOM Elements
const connectionStatus = document.getElementById('connectionStatus');
const navItems = document.querySelectorAll('.nav-item');
const pages = document.querySelectorAll('.page');

// ============== Initialization ==============

document.addEventListener('DOMContentLoaded', async () => {
    console.log('Initializing Crypto Trading Bot...');
    
    // Initialize API client
    await initializeApi();
    
    // Setup navigation
    setupNavigation();
    
    // Load initial data
    await loadStrategies();
    await loadExchanges();
    await updateDashboardStats();
    
    // Setup event listeners
    setupBacktestEvents();
    setupLiveEvents();
    setupExchangeEvents();
});

/**
 * Initialize API connection
 */
async function initializeApi() {
    await api.init();
    updateConnectionStatus();
    
    // Retry connection every 5 seconds if not connected
    setInterval(async () => {
        if (!api.connected) {
            await api.checkConnection();
            updateConnectionStatus();
        }
    }, 5000);
}

/**
 * Update connection status indicator
 */
function updateConnectionStatus() {
    const dot = connectionStatus.querySelector('.status-dot');
    const text = connectionStatus.querySelector('span:last-child');
    
    if (api.connected) {
        dot.classList.add('connected');
        dot.classList.remove('disconnected');
        text.textContent = 'Connected';
    } else {
        dot.classList.remove('connected');
        dot.classList.add('disconnected');
        text.textContent = 'Connecting...';
    }
}

// ============== Navigation ==============

function setupNavigation() {
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const page = item.dataset.page;
            navigateTo(page);
        });
    });
}

function navigateTo(pageName) {
    // Update nav items
    navItems.forEach(item => {
        item.classList.toggle('active', item.dataset.page === pageName);
    });
    
    // Update pages
    pages.forEach(page => {
        page.classList.toggle('active', page.id === `page-${pageName}`);
    });
    
    currentPage = pageName;
}

// ============== Dashboard ==============

async function updateDashboardStats() {
    try {
        const strategyCount = document.getElementById('strategyCount');
        const exchangeCount = document.getElementById('exchangeCount');
        const backtestCount = document.getElementById('backtestCount');
        
        strategyCount.textContent = strategies.length;
        
        const exchanges = await api.getExchanges();
        exchangeCount.textContent = exchanges.configured.length;
        
        const backtests = await api.listBacktests();
        backtestCount.textContent = backtests.length;
    } catch (error) {
        console.error('Failed to load dashboard stats:', error);
    }
}

// ============== Strategies ==============

async function loadStrategies() {
    try {
        strategies = await api.getStrategies();
        populateStrategySelects();
        renderStrategiesList();
    } catch (error) {
        console.error('Failed to load strategies:', error);
        strategies = [];
    }
}

function populateStrategySelects() {
    const selects = [
        document.getElementById('btStrategy'),
        document.getElementById('liveStrategy')
    ];
    
    selects.forEach(select => {
        if (!select) return;
        
        select.innerHTML = '';
        
        // Recommended strategies first
        const recommended = strategies.filter(s => s.recommended);
        const others = strategies.filter(s => !s.recommended);
        
        if (recommended.length > 0) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = '★ Recommended Strategies';
            recommended.forEach(strategy => {
                const option = document.createElement('option');
                option.value = strategy.name;
                option.textContent = `★ ${strategy.name}`;
                optgroup.appendChild(option);
            });
            select.appendChild(optgroup);
        }
        
        if (others.length > 0) {
            const optgroup = document.createElement('optgroup');
            optgroup.label = 'Other Strategies';
            others.forEach(strategy => {
                const option = document.createElement('option');
                option.value = strategy.name;
                option.textContent = strategy.name;
                optgroup.appendChild(option);
            });
            select.appendChild(optgroup);
        }
    });
}

function renderStrategiesList() {
    const container = document.getElementById('strategiesList');
    
    if (strategies.length === 0) {
        container.innerHTML = '<p class="loading">No strategies available</p>';
        return;
    }
    
    // Group strategies by category
    const byCategory = {
        simple: strategies.filter(s => s.category === 'simple'),
        basic: strategies.filter(s => s.category === 'basic'),
        intermediate: strategies.filter(s => s.category === 'intermediate'),
        advanced: strategies.filter(s => s.category === 'advanced')
    };
    
    const categoryLabels = {
        simple: '⭐ Simple & Proven (START HERE)',
        basic: '📚 Basic (Educational)',
        intermediate: '📊 Intermediate',
        advanced: '🔬 Advanced (Complex)'
    };
    
    const marketTypeIcons = {
        trending: '📈',
        ranging: '↔️',
        any: '🔄'
    };
    
    let html = `
        <div class="strategies-intro">
            <h3>Trading Strategies Guide</h3>
            <p>★ <strong>Recommended strategies</strong> are research-backed with proven profitability in backtests.
            Basic strategies are educational - good for learning but may not be profitable.</p>
        </div>
    `;
    
    for (const [category, strats] of Object.entries(byCategory)) {
        if (strats.length === 0) continue;
        
        html += `
            <div class="strategy-category">
                <h3 class="category-title">${categoryLabels[category]}</h3>
                <div class="strategy-grid">
        `;
        
        strats.forEach(strategy => {
            const marketIcon = marketTypeIcons[strategy.market_type] || '🔄';
            const recommendedBadge = strategy.recommended 
                ? '<span class="badge recommended">★ RECOMMENDED</span>' 
                : '';
            
            html += `
                <div class="strategy-card ${strategy.recommended ? 'recommended' : ''}">
                    <div class="strategy-header">
                        <h4>${strategy.name}</h4>
                        ${recommendedBadge}
                    </div>
                    <p class="strategy-description">${strategy.description}</p>
                    <div class="strategy-meta">
                        <span class="market-type">${marketIcon} ${strategy.market_type} markets</span>
                        <span class="version">v${strategy.version}</span>
                    </div>
                    <div class="strategy-params">
                        <strong>Parameters:</strong> ${Object.keys(strategy.params).join(', ')}
                    </div>
                </div>
            `;
        });
        
        html += `
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

// ============== Backtest ==============

function setupBacktestEvents() {
    const btnRunBacktest = document.getElementById('btnRunBacktest');
    const btnOpenReport = document.getElementById('btnOpenReport');
    
    btnRunBacktest.addEventListener('click', runBacktest);
    btnOpenReport.addEventListener('click', openBacktestReport);
}

async function runBacktest() {
    const btnRunBacktest = document.getElementById('btnRunBacktest');
    const progressContainer = document.getElementById('backtestProgress');
    const resultsContainer = document.getElementById('backtestResults');
    
    // Get form values
    const config = {
        strategy: document.getElementById('btStrategy').value,
        exchange: document.getElementById('btExchange').value,
        symbol: document.getElementById('btSymbol').value,
        timeframe: document.getElementById('btTimeframe').value,
        period_days: parseInt(document.getElementById('btPeriod').value),
        initial_capital: parseFloat(document.getElementById('btCapital').value),
        fee_percent: parseFloat(document.getElementById('btFee').value)
    };
    
    // Validate
    if (!config.strategy) {
        alert('Please select a strategy');
        return;
    }
    
    // Disable button and show progress
    btnRunBacktest.disabled = true;
    btnRunBacktest.textContent = 'Running...';
    progressContainer.classList.remove('hidden');
    resultsContainer.classList.add('hidden');
    
    try {
        // Start backtest
        const job = await api.startBacktest(config);
        currentBacktestJob = job;
        
        // Poll for status
        pollBacktestStatus(job.job_id);
        
    } catch (error) {
        alert(`Failed to start backtest: ${error.message}`);
        btnRunBacktest.disabled = false;
        btnRunBacktest.textContent = 'Run Backtest';
        progressContainer.classList.add('hidden');
    }
}

async function pollBacktestStatus(jobId) {
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const btnRunBacktest = document.getElementById('btnRunBacktest');
    const progressContainer = document.getElementById('backtestProgress');
    const resultsContainer = document.getElementById('backtestResults');
    
    const poll = async () => {
        try {
            const status = await api.getBacktestStatus(jobId);
            
            // Update progress
            progressFill.style.width = `${status.progress * 100}%`;
            progressText.textContent = status.message;
            
            if (status.status === 'completed') {
                // Show results
                displayBacktestResults(status);
                progressContainer.classList.add('hidden');
                resultsContainer.classList.remove('hidden');
                btnRunBacktest.disabled = false;
                btnRunBacktest.textContent = 'Run Backtest';
                currentBacktestJob = status;
                await updateDashboardStats();
                
            } else if (status.status === 'failed') {
                alert(`Backtest failed: ${status.message}`);
                progressContainer.classList.add('hidden');
                btnRunBacktest.disabled = false;
                btnRunBacktest.textContent = 'Run Backtest';
                
            } else {
                // Continue polling
                setTimeout(poll, 500);
            }
            
        } catch (error) {
            console.error('Failed to get backtest status:', error);
            setTimeout(poll, 1000);
        }
    };
    
    poll();
}

function displayBacktestResults(status) {
    const result = status.result;
    
    // Update result values
    const returnEl = document.getElementById('resultReturn');
    returnEl.textContent = `${result.total_return.toFixed(2)}%`;
    returnEl.className = `result-value ${result.total_return >= 0 ? 'positive' : 'negative'}`;
    
    document.getElementById('resultSharpe').textContent = result.sharpe_ratio.toFixed(2);
    
    const ddEl = document.getElementById('resultDrawdown');
    ddEl.textContent = `${result.max_drawdown.toFixed(2)}%`;
    ddEl.className = 'result-value negative';
    
    document.getElementById('resultWinRate').textContent = `${result.win_rate.toFixed(1)}%`;
    document.getElementById('resultTrades').textContent = result.total_trades;
    document.getElementById('resultProfitFactor').textContent = result.profit_factor.toFixed(2);
}

function openBacktestReport() {
    if (currentBacktestJob && currentBacktestJob.report_path) {
        if (window.electronAPI) {
            window.electronAPI.openFile(currentBacktestJob.report_path);
        } else {
            window.open(`file://${currentBacktestJob.report_path}`, '_blank');
        }
    }
}

// ============== Live Trading ==============

function setupLiveEvents() {
    const btnStart = document.getElementById('btnStartLive');
    const btnStop = document.getElementById('btnStopLive');
    
    btnStart.addEventListener('click', startLiveTrading);
    btnStop.addEventListener('click', stopLiveTrading);
    
    // Check live status periodically
    checkLiveStatus();
    setInterval(checkLiveStatus, 5000);
}

async function startLiveTrading() {
    const config = {
        strategy: document.getElementById('liveStrategy').value,
        exchange: document.getElementById('liveExchange').value,
        symbol: document.getElementById('liveSymbol').value,
        timeframe: document.getElementById('liveTimeframe').value,
        mode: document.getElementById('liveMode').value,
        position_size: parseFloat(document.getElementById('livePositionSize').value) / 100,
        check_interval: parseInt(document.getElementById('liveCheckInterval').value) || 60,
        initial_balance: parseFloat(document.getElementById('liveInitialBalance').value) || 10000
    };
    
    // Warn for live mode
    if (config.mode === 'live') {
        const confirmed = confirm(
            'WARNING: You are about to start LIVE trading with real money!\n\n' +
            'Make sure you have configured your exchange API keys correctly.\n\n' +
            'Are you sure you want to continue?'
        );
        if (!confirmed) return;
    }
    
    try {
        await api.startLiveTrading(config);
        updateLiveUI(true);
        startLivePolling();
        addLogEntry(`Started ${config.mode} trading: ${config.strategy} on ${config.symbol} (${config.timeframe})`, 'info');
    } catch (error) {
        alert(`Failed to start live trading: ${error.message}`);
    }
}

function addLogEntry(message, type = 'info') {
    const container = document.getElementById('logContainer');
    const logDiv = document.getElementById('liveLog');
    
    // Show log container
    logDiv.classList.remove('hidden');
    
    // Remove empty message if exists
    const emptyMsg = container.querySelector('.log-empty');
    if (emptyMsg) emptyMsg.remove();
    
    // Create entry
    const entry = document.createElement('div');
    entry.className = `log-entry signal-${type}`;
    
    const time = new Date().toLocaleTimeString();
    entry.innerHTML = `<span class="time">[${time}]</span> ${message}`;
    
    // Add at top
    container.insertBefore(entry, container.firstChild);
    
    // Keep max 50 entries
    while (container.children.length > 50) {
        container.removeChild(container.lastChild);
    }
}

async function stopLiveTrading() {
    try {
        await api.stopLiveTrading();
        updateLiveUI(false);
        stopLivePolling();
    } catch (error) {
        alert(`Failed to stop live trading: ${error.message}`);
    }
}

async function checkLiveStatus() {
    try {
        const status = await api.getLiveStatus();
        updateLiveUI(status.running, status);
    } catch (error) {
        console.error('Failed to check live status:', error);
    }
}

function updateLiveUI(running, status = null) {
    const btnStart = document.getElementById('btnStartLive');
    const btnStop = document.getElementById('btnStopLive');
    const statusDot = document.getElementById('liveStatusDot');
    const statusText = document.getElementById('liveStatusText');
    const statsContainer = document.getElementById('liveStats');
    const logContainer = document.getElementById('liveLog');
    
    btnStart.disabled = running;
    btnStop.disabled = !running;
    
    statusDot.classList.toggle('connected', running);
    statusDot.classList.toggle('disconnected', !running);
    statusText.textContent = running ? 'Running' : 'Stopped';
    
    if (running) {
        statsContainer.classList.remove('hidden');
        logContainer.classList.remove('hidden');
    }
    
    if (running && status) {
        document.getElementById('livePnL').textContent = `$${status.session_pnl.toFixed(2)}`;
        document.getElementById('liveTradesCount').textContent = status.trades_count;
        document.getElementById('livePosition').textContent = status.position ? 
            `${status.position.side} ${status.position.size}` : 'None';
    } else if (!running) {
        statsContainer.classList.add('hidden');
    }
}

let lastTradesCount = 0;

function startLivePolling() {
    if (livePollingInterval) return;
    
    livePollingInterval = setInterval(async () => {
        try {
            const status = await api.getLiveStatus();
            updateLiveUI(status.running, status);
            
            // Check for new trades
            if (status.running && status.trades_count > lastTradesCount) {
                const trades = await api.getLiveTrades();
                if (trades.trades && trades.trades.length > 0) {
                    const newTrade = trades.trades[0];
                    const pnlStr = newTrade.pnl ? ` (PnL: $${newTrade.pnl.toFixed(2)})` : '';
                    addLogEntry(
                        `${newTrade.side.toUpperCase()} ${newTrade.quantity.toFixed(6)} @ $${newTrade.price.toFixed(2)}${pnlStr}`,
                        newTrade.side === 'buy' ? 'buy' : 'sell'
                    );
                }
                lastTradesCount = status.trades_count;
            }
            
            // Update balance
            const balance = await api.getLiveBalance();
            if (balance.balance) {
                document.getElementById('liveBalance').textContent = `$${balance.balance.toFixed(2)}`;
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 2000);
}

function stopLivePolling() {
    if (livePollingInterval) {
        clearInterval(livePollingInterval);
        livePollingInterval = null;
    }
}

// ============== Exchanges ==============

function setupExchangeEvents() {
    const btnAdd = document.getElementById('btnAddExchange');
    btnAdd.addEventListener('click', addExchange);
}

async function loadExchanges() {
    try {
        const data = await api.getExchanges();
        renderExchangesList(data.configured);
    } catch (error) {
        console.error('Failed to load exchanges:', error);
    }
}

function renderExchangesList(configured) {
    const container = document.getElementById('exchangesList');
    
    if (configured.length === 0) {
        container.innerHTML = '<p>No exchanges configured</p>';
        return;
    }
    
    container.innerHTML = configured.map(exchange => `
        <div class="exchange-item">
            <span class="name">${exchange}</span>
            <button class="btn btn-danger btn-sm" onclick="removeExchange('${exchange}')">
                Remove
            </button>
        </div>
    `).join('');
}

async function addExchange() {
    const config = {
        exchange_id: document.getElementById('newExchangeId').value,
        api_key: document.getElementById('newApiKey').value,
        api_secret: document.getElementById('newApiSecret').value,
        sandbox: document.getElementById('newSandbox').checked
    };
    
    if (!config.api_key || !config.api_secret) {
        alert('Please enter API Key and Secret');
        return;
    }
    
    try {
        await api.addExchange(config);
        
        // Clear form
        document.getElementById('newApiKey').value = '';
        document.getElementById('newApiSecret').value = '';
        
        // Reload list
        await loadExchanges();
        await updateDashboardStats();
        
        alert('Exchange added successfully!');
    } catch (error) {
        alert(`Failed to add exchange: ${error.message}`);
    }
}

async function removeExchange(exchangeId) {
    if (!confirm(`Remove ${exchangeId}?`)) return;
    
    try {
        await api.removeExchange(exchangeId);
        await loadExchanges();
        await updateDashboardStats();
    } catch (error) {
        alert(`Failed to remove exchange: ${error.message}`);
    }
}
