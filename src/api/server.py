"""
FastAPI server for Crypto Trading Bot.

Provides REST API endpoints for the Electron GUI.
"""

import asyncio
import os
import psutil
import secrets
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from src.core.config import ConfigManager
from src.core.exchange import ExchangeManager
from src.core.data_manager import DataManager
from src.core.database import get_database
from src.strategies.registry import StrategyRegistry
from src.backtesting.engine import BacktestEngine
from src.backtesting.metrics import MetricsCalculator
from src.backtesting.report import ReportGenerator
from src.trading.live_engine import LiveTradingEngine, TradingMode
from src.utils.logger import get_logger

logger = get_logger()

# Server start time for uptime tracking
SERVER_START_TIME = datetime.now()

# Initialize FastAPI app
app = FastAPI(
    title="Crypto Trading Bot API",
    description="REST API for crypto trading bot operations",
    version="1.0.0"
)

# Enable CORS for Electron app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
config = ConfigManager()
registry = StrategyRegistry()
registry.load_builtin()

# API Key Security
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(api_key_header)
) -> Optional[str]:
    """
    Verify API key if authentication is enabled.
    
    Exempt paths: /api/health, /docs, /openapi.json
    """
    # Check if auth is enabled
    auth_enabled = config.get("api.auth_enabled", False)
    
    if not auth_enabled:
        return None
    
    # Exempt certain paths
    exempt_paths = ["/api/health", "/docs", "/openapi.json", "/redoc"]
    if any(request.url.path.startswith(path) for path in exempt_paths):
        return None
    
    # Get configured API key
    configured_key = config.get("api.api_key") or os.environ.get("TRADING_BOT_API_KEY")
    
    if not configured_key:
        # No key configured, allow access but warn
        logger.warning("API auth enabled but no API key configured")
        return None
    
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Provide X-API-Key header."
        )
    
    if not secrets.compare_digest(api_key, configured_key):
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )
    
    return api_key

# Backtest state
backtest_jobs: Dict[str, Dict[str, Any]] = {}

# Live trading state
live_engine: Optional[LiveTradingEngine] = None
live_thread: Optional[threading.Thread] = None
live_strategy: Optional[Any] = None
live_params: Dict[str, str] = {}


def _get_exchanges_config(cfg: ConfigManager) -> Dict[str, Any]:
    """
    Normalize exchanges config to a dict keyed by exchange id.
    Handles both list format (old/CLI) and dict format (API).
    """
    raw = cfg.get("exchanges")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list) and raw:
        result = {}
        for item in raw:
            if isinstance(item, dict) and item.get("name"):
                name = item["name"]
                result[name] = {
                    "api_key": item.get("api_key", ""),
                    "api_secret": item.get("api_secret", ""),
                    "sandbox": item.get("sandbox", False),
                }
        return result
    return {}


# ============== Request/Response Models ==============

class BacktestRequest(BaseModel):
    strategy: str
    exchange: str
    symbol: str
    timeframe: str
    period_days: int = 30
    initial_capital: float = 10000
    fee_percent: float = 0.1
    strategy_params: Optional[Dict[str, Any]] = None


class BacktestStatus(BaseModel):
    job_id: str
    status: str  # pending, running, completed, failed
    progress: float
    message: str
    result: Optional[Dict[str, Any]] = None
    report_path: Optional[str] = None


class LiveTradingRequest(BaseModel):
    strategy: str
    exchange: str
    symbol: str
    timeframe: str
    mode: str = "paper"  # paper, dry_run, live
    position_size: float = 0.1
    check_interval: int = 60
    initial_balance: float = 10000  # Paper trading initial balance


class LiveStatus(BaseModel):
    running: bool
    mode: Optional[str] = None
    strategy: Optional[str] = None
    symbol: Optional[str] = None
    position: Optional[Dict[str, Any]] = None
    session_pnl: float = 0.0
    trades_count: int = 0


class ExchangeConfig(BaseModel):
    exchange_id: str
    api_key: str
    api_secret: str
    sandbox: bool = True


class StrategyInfo(BaseModel):
    name: str
    description: str
    version: str
    params: Dict[str, Any]
    category: str = "basic"
    recommended: bool = False
    market_type: str = "trending"


# Strategy metadata (category, recommendation, market type)
STRATEGY_METADATA = {
    # Simple proven strategies (BEST FOR BEGINNERS)
    "Simple Trend": {"category": "simple", "recommended": True, "market_type": "trending"},
    "Momentum RSI": {"category": "simple", "recommended": True, "market_type": "any"},
    # Basic strategies (educational)
    "MA Crossover": {"category": "basic", "recommended": False, "market_type": "trending"},
    "RSI Strategy": {"category": "basic", "recommended": False, "market_type": "ranging"},
    "MACD Strategy": {"category": "basic", "recommended": False, "market_type": "trending"},
    "Bollinger Bands": {"category": "basic", "recommended": False, "market_type": "ranging"},
    # Intermediate
    "Trend Momentum": {"category": "intermediate", "recommended": False, "market_type": "trending"},
    "Mean Reversion": {"category": "intermediate", "recommended": False, "market_type": "ranging"},
    "SuperTrend": {"category": "intermediate", "recommended": False, "market_type": "trending"},
    "Grid Trading": {"category": "intermediate", "recommended": False, "market_type": "ranging"},
    "DCA Strategy": {"category": "intermediate", "recommended": False, "market_type": "any"},
    "Triple EMA": {"category": "intermediate", "recommended": False, "market_type": "trending"},
    "Breakout": {"category": "intermediate", "recommended": False, "market_type": "trending"},
    # Advanced (more complex)
    "ADX BB Trend": {"category": "advanced", "recommended": False, "market_type": "trending"},
    "Donchian Breakout": {"category": "advanced", "recommended": False, "market_type": "trending"},
    "Regime Filter": {"category": "advanced", "recommended": False, "market_type": "any"},
    "Multi Confirm": {"category": "advanced", "recommended": False, "market_type": "any"},
    "Volatility Breakout": {"category": "advanced", "recommended": False, "market_type": "trending"},
}


# ============== Strategy Endpoints ==============

@app.get("/api/strategies", response_model=List[StrategyInfo])
async def get_strategies(_: str = Depends(verify_api_key)):
    """Get list of available trading strategies with metadata."""
    strategies = []
    for name, strategy_class in registry.get_all().items():
        instance = strategy_class()
        meta = STRATEGY_METADATA.get(instance.name, {})
        strategies.append(StrategyInfo(
            name=instance.name,
            description=instance.description,
            version=instance.version,
            params=instance.default_params(),
            category=meta.get("category", "basic"),
            recommended=meta.get("recommended", False),
            market_type=meta.get("market_type", "any")
        ))
    # Sort: recommended first, then by category
    strategies.sort(key=lambda s: (not s.recommended, s.category, s.name))
    return strategies


@app.get("/api/strategies/{name}")
async def get_strategy(name: str, _: str = Depends(verify_api_key)):
    """Get details of a specific strategy."""
    strategy_class = registry.get(name)
    if not strategy_class:
        raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found")
    
    instance = strategy_class()
    return {
        "name": instance.name,
        "description": instance.description,
        "version": instance.version,
        "params": instance.default_params(),
        "param_schema": instance.get_param_schema()
    }


# ============== Exchange Endpoints ==============

@app.get("/api/exchanges")
async def get_exchanges(_: str = Depends(verify_api_key)):
    """Get list of configured exchanges."""
    configured = _get_exchanges_config(config)
    return {
        "configured": list(configured.keys()),
        "available": ["binance", "coinbase", "kraken", "kucoin", "bybit", "okx"]
    }


@app.post("/api/exchanges")
async def add_exchange(exchange_config: ExchangeConfig, _: str = Depends(verify_api_key)):
    """Add or update an exchange configuration."""
    exchanges = _get_exchanges_config(config)
    exchanges[exchange_config.exchange_id] = {
        "api_key": exchange_config.api_key,
        "api_secret": exchange_config.api_secret,
        "sandbox": exchange_config.sandbox
    }
    config.set("exchanges", exchanges)
    config.save()
    return {"status": "ok", "message": f"Exchange {exchange_config.exchange_id} configured"}


@app.delete("/api/exchanges/{exchange_id}")
async def remove_exchange(exchange_id: str, _: str = Depends(verify_api_key)):
    """Remove an exchange configuration."""
    exchanges = _get_exchanges_config(config)
    if exchange_id in exchanges:
        del exchanges[exchange_id]
        config.set("exchanges", exchanges)
        config.save()
        return {"status": "ok", "message": f"Exchange {exchange_id} removed"}
    raise HTTPException(status_code=404, detail=f"Exchange '{exchange_id}' not found")


# ============== Backtest Endpoints ==============

def run_backtest_job(job_id: str, request: BacktestRequest):
    """Background task to run backtest."""
    job = backtest_jobs[job_id]
    
    try:
        job["status"] = "running"
        job["message"] = "Connecting to exchange..."
        job["progress"] = 0.1
        
        # Get strategy
        strategy_class = registry.get(request.strategy)
        if not strategy_class:
            raise ValueError(f"Strategy '{request.strategy}' not found")
        
        params = request.strategy_params or {}
        strategy = strategy_class(**params)
        
        # Download data
        job["message"] = "Downloading historical data..."
        job["progress"] = 0.2
        
        data_manager = DataManager()
        df, status_msg = data_manager.download_for_backtest(
            exchange=request.exchange,
            symbol=request.symbol,
            timeframe=request.timeframe,
            days=request.period_days
        )
        
        if df is None or df.empty:
            raise ValueError(f"No data available for {request.symbol}")
        
        # Run backtest
        job["message"] = "Running backtest simulation..."
        job["progress"] = 0.4
        
        def progress_callback(current, total):
            if total > 0:
                pct = current / total
                job["progress"] = 0.4 + (pct * 0.4)
        
        engine = BacktestEngine(
            initial_capital=request.initial_capital,
            fee_percent=request.fee_percent
        )
        
        result = engine.run(
            strategy=strategy,
            data=df,
            symbol=request.symbol,
            timeframe=request.timeframe,
            progress_callback=progress_callback
        )
        
        # Calculate metrics
        job["message"] = "Calculating metrics..."
        job["progress"] = 0.85
        
        calculator = MetricsCalculator()
        metrics = calculator.calculate(result)
        
        # Generate report
        job["message"] = "Generating report..."
        job["progress"] = 0.95
        
        generator = ReportGenerator()
        report_path = generator.generate(result, metrics)
        
        # Complete
        job["status"] = "completed"
        job["progress"] = 1.0
        job["message"] = "Backtest completed"
        # Calculate total fees from trades
        total_fees = sum(t.fee for t in result.trades)
        
        job["result"] = {
            "total_return": metrics.total_return_pct,
            "sharpe_ratio": metrics.sharpe_ratio,
            "max_drawdown": metrics.max_drawdown,
            "total_trades": metrics.total_trades,
            "win_rate": metrics.win_rate,
            "profit_factor": metrics.profit_factor,
            "final_capital": result.final_capital,
            "total_fees": total_fees
        }
        job["report_path"] = report_path
        
    except Exception as e:
        logger.exception(f"Backtest job {job_id} failed")
        job["status"] = "failed"
        job["message"] = str(e)
        job["progress"] = 0


@app.post("/api/backtest", response_model=BacktestStatus)
async def start_backtest(request: BacktestRequest, background_tasks: BackgroundTasks, _: str = Depends(verify_api_key)):
    """Start a backtest job."""
    job_id = str(uuid.uuid4())[:8]
    
    backtest_jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress": 0.0,
        "message": "Queued...",
        "result": None,
        "report_path": None,
        "request": request.dict()
    }
    
    # Run in background thread (not asyncio because of blocking operations)
    thread = threading.Thread(target=run_backtest_job, args=(job_id, request))
    thread.start()
    
    return BacktestStatus(**backtest_jobs[job_id])


@app.get("/api/backtest/{job_id}", response_model=BacktestStatus)
async def get_backtest_status(job_id: str, _: str = Depends(verify_api_key)):
    """Get status of a backtest job."""
    if job_id not in backtest_jobs:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return BacktestStatus(**backtest_jobs[job_id])


@app.get("/api/backtest")
async def list_backtests(_: str = Depends(verify_api_key)):
    """List all backtest jobs."""
    return [BacktestStatus(**job) for job in backtest_jobs.values()]


# ============== Live Trading Endpoints ==============

@app.post("/api/live/start")
async def start_live_trading(request: LiveTradingRequest, _: str = Depends(verify_api_key)):
    """Start live trading."""
    global live_engine, live_thread, live_strategy, live_params
    
    if live_engine and live_engine._running:
        raise HTTPException(status_code=400, detail="Live trading already running")
    
    try:
        # Get strategy
        strategy_class = registry.get(request.strategy)
        if not strategy_class:
            raise HTTPException(status_code=404, detail=f"Strategy '{request.strategy}' not found")
        
        strategy = strategy_class()
        
        # Map mode
        mode_map = {
            "paper": TradingMode.PAPER,
            "dry_run": TradingMode.DRY_RUN,
            "live": TradingMode.LIVE
        }
        mode = mode_map.get(request.mode, TradingMode.PAPER)
        
        # Create engine
        live_engine = LiveTradingEngine(config=config, mode=mode)
        
        # Set paper balance if paper mode
        if mode == TradingMode.PAPER:
            quote = request.symbol.split('/')[1] if '/' in request.symbol else 'USDT'
            live_engine.set_paper_balance(quote, request.initial_balance)
        
        # Store params for status
        live_params = {
            "strategy": request.strategy,
            "symbol": request.symbol,
            "exchange": request.exchange
        }
        live_strategy = strategy
        
        # Start in background thread
        def run_live():
            asyncio.run(live_engine.run_strategy(
                strategy=strategy,
                exchange_id=request.exchange,
                symbol=request.symbol,
                timeframe=request.timeframe,
                position_size=request.position_size,
                check_interval=request.check_interval
            ))
        
        live_thread = threading.Thread(target=run_live, daemon=True)
        live_thread.start()
        
        return {"status": "ok", "message": "Live trading started"}
        
    except Exception as e:
        logger.exception("Failed to start live trading")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/live/stop")
async def stop_live_trading(_: str = Depends(verify_api_key)):
    """Stop live trading."""
    global live_engine
    
    if not live_engine or not live_engine._running:
        raise HTTPException(status_code=400, detail="Live trading not running")
    
    live_engine.stop()
    return {"status": "ok", "message": "Live trading stopped"}


@app.get("/api/live/status", response_model=LiveStatus)
async def get_live_status(_: str = Depends(verify_api_key)):
    """Get live trading status."""
    if not live_engine:
        return LiveStatus(running=False)
    
    status = live_engine.get_status()
    return LiveStatus(
        running=status.get("running", False),
        mode=status.get("mode"),
        strategy=live_params.get("strategy"),
        symbol=live_params.get("symbol"),
        position=status.get("position"),
        session_pnl=status.get("session_pnl", 0.0),
        trades_count=status.get("trades_count", 0)
    )


@app.get("/api/live/trades")
async def get_live_trades(_: str = Depends(verify_api_key)):
    """Get recent trades from live trading session."""
    if not live_engine:
        return {"trades": []}
    
    trades = []
    for t in live_engine.trade_history[-20:]:  # Last 20 trades
        trades.append({
            "timestamp": t.timestamp.isoformat(),
            "symbol": t.symbol,
            "side": t.side,
            "quantity": t.quantity,
            "price": t.price,
            "pnl": t.pnl,
            "mode": t.mode
        })
    
    return {"trades": trades}


@app.get("/api/live/balance")
async def get_live_balance(_: str = Depends(verify_api_key)):
    """Get current balance for live/paper trading."""
    if not live_engine:
        return {"balance": 0, "currency": "USDT"}
    
    # Get quote currency from symbol
    symbol = live_params.get("symbol", "BTC/USDT")
    quote = symbol.split('/')[1] if '/' in symbol else 'USDT'
    
    balance = live_engine.get_balance(live_params.get("exchange", "binance"), quote)
    
    return {
        "balance": balance,
        "currency": quote,
        "mode": live_engine.mode.value
    }


# ============== Journal Endpoints ==============

class JournalEntryCreate(BaseModel):
    content: str
    entry_type: str = "note"  # note, trade_review, lesson, market_analysis
    trade_id: Optional[int] = None
    symbol: Optional[str] = None
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    market_conditions: Optional[str] = None
    lessons_learned: Optional[str] = None
    rating: Optional[int] = None  # 1-5


class JournalEntryUpdate(BaseModel):
    content: Optional[str] = None
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    market_conditions: Optional[str] = None
    lessons_learned: Optional[str] = None
    rating: Optional[int] = None
    entry_type: Optional[str] = None


@app.get("/api/journal")
async def get_journal_entries(
    trade_id: Optional[int] = None,
    symbol: Optional[str] = None,
    entry_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    _: str = Depends(verify_api_key)
):
    """Get journal entries with optional filters."""
    try:
        db = get_database()
        entries = db.get_journal_entries(
            trade_id=trade_id,
            symbol=symbol,
            entry_type=entry_type,
            limit=limit,
            offset=offset
        )
        return {"entries": entries, "count": len(entries)}
    except Exception as e:
        logger.exception("Error fetching journal entries")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/journal")
async def create_journal_entry(
    entry: JournalEntryCreate,
    _: str = Depends(verify_api_key)
):
    """Create a new journal entry."""
    try:
        db = get_database()
        entry_id = db.insert_journal_entry(
            content=entry.content,
            entry_type=entry.entry_type,
            trade_id=entry.trade_id,
            symbol=entry.symbol,
            title=entry.title,
            tags=entry.tags,
            market_conditions=entry.market_conditions,
            lessons_learned=entry.lessons_learned,
            rating=entry.rating
        )
        return {"status": "ok", "entry_id": entry_id}
    except Exception as e:
        logger.exception("Error creating journal entry")
        raise HTTPException(status_code=500, detail=str(e))


@app.patch("/api/journal/{entry_id}")
async def update_journal_entry(
    entry_id: int,
    entry: JournalEntryUpdate,
    _: str = Depends(verify_api_key)
):
    """Update a journal entry."""
    try:
        db = get_database()
        updates = entry.dict(exclude_unset=True)
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        success = db.update_journal_entry(entry_id, **updates)
        
        if not success:
            raise HTTPException(status_code=404, detail="Entry not found")
        
        return {"status": "ok", "entry_id": entry_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error updating journal entry")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/journal/{entry_id}")
async def delete_journal_entry(
    entry_id: int,
    _: str = Depends(verify_api_key)
):
    """Delete a journal entry."""
    try:
        db = get_database()
        success = db.delete_journal_entry(entry_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Entry not found")
        
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error deleting journal entry")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Trade History Endpoints ==============

@app.get("/api/trades/history")
async def get_trade_history(
    symbol: Optional[str] = None,
    strategy: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _: str = Depends(verify_api_key)
):
    """Get historical trades from database."""
    try:
        db = get_database()
        trades = db.get_trades(
            symbol=symbol,
            strategy=strategy,
            limit=limit,
            offset=offset
        )
        return {"trades": trades, "count": len(trades)}
    except Exception as e:
        logger.exception("Error fetching trade history")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trades/stats")
async def get_trade_stats(_: str = Depends(verify_api_key)):
    """Get aggregated trade statistics."""
    try:
        db = get_database()
        stats = db.get_trade_stats()
        return stats
    except Exception as e:
        logger.exception("Error fetching trade stats")
        raise HTTPException(status_code=500, detail=str(e))


# ============== Data Endpoints ==============

@app.get("/api/symbols/{exchange_id}")
async def get_symbols(exchange_id: str, _: str = Depends(verify_api_key)):
    """Get available trading symbols for an exchange."""
    try:
        exchange = ExchangeManager()
        exchange.connect(exchange_id)
        markets = exchange.exchange.load_markets()
        
        # Filter for popular pairs
        symbols = [s for s in markets.keys() if "/USDT" in s or "/USD" in s]
        return {"symbols": sorted(symbols)[:100]}  # Limit to 100
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/timeframes")
async def get_timeframes(_: str = Depends(verify_api_key)):
    """Get available timeframes."""
    return {
        "timeframes": ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"]
    }


# ============== Health Check ==============

@app.get("/api/health")
async def health_check():
    """Basic health check endpoint (no auth required)."""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@app.get("/api/health/detailed")
async def health_check_detailed(_: str = Depends(verify_api_key)):
    """
    Detailed health check with system status.
    
    Returns:
        - System status (memory, CPU)
        - Live trading engine status
        - Active backtest jobs
        - Exchange connectivity
        - Database status
        - Uptime
    """
    health_data = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "uptime_seconds": (datetime.now() - SERVER_START_TIME).total_seconds(),
        "components": {}
    }
    
    # System metrics
    try:
        process = psutil.Process()
        health_data["system"] = {
            "memory_mb": round(process.memory_info().rss / 1024 / 1024, 2),
            "memory_percent": round(process.memory_percent(), 2),
            "cpu_percent": round(process.cpu_percent(interval=0.1), 2),
            "threads": process.num_threads()
        }
    except Exception as e:
        health_data["system"] = {"error": str(e)}
    
    # Live trading engine status
    if live_engine:
        status = live_engine.get_status()
        health_data["components"]["live_trading"] = {
            "status": "running" if status.get("running") else "stopped",
            "mode": status.get("mode"),
            "trades_count": status.get("trades_count", 0),
            "has_position": status.get("position") is not None
        }
    else:
        health_data["components"]["live_trading"] = {"status": "not_initialized"}
    
    # Backtest jobs status
    active_jobs = sum(1 for j in backtest_jobs.values() if j["status"] in ("pending", "running"))
    completed_jobs = sum(1 for j in backtest_jobs.values() if j["status"] == "completed")
    failed_jobs = sum(1 for j in backtest_jobs.values() if j["status"] == "failed")
    
    health_data["components"]["backtesting"] = {
        "active_jobs": active_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "total_jobs": len(backtest_jobs)
    }
    
    # Database status
    try:
        db = get_database()
        stats = db.get_trade_stats()
        health_data["components"]["database"] = {
            "status": "connected",
            "total_trades": stats.get("total_trades", 0),
            "path": str(db.db_path)
        }
    except Exception as e:
        health_data["components"]["database"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Exchange connectivity (check configured exchanges)
    configured_exchanges = _get_exchanges_config(config)
    exchange_status = {}
    
    for exchange_id in list(configured_exchanges.keys())[:3]:  # Limit to 3 exchanges
        try:
            em = ExchangeManager()
            em.connect(exchange_id)
            # Try to fetch markets as a connectivity test
            em.exchange.load_markets()
            exchange_status[exchange_id] = "connected"
        except Exception as e:
            exchange_status[exchange_id] = f"error: {str(e)[:50]}"
    
    health_data["components"]["exchanges"] = exchange_status
    
    # Notification channels
    try:
        from src.notifications.manager import get_notification_manager
        manager = get_notification_manager(config._config)
        if manager:
            health_data["components"]["notifications"] = {
                "enabled_channels": manager.enabled_channels
            }
    except Exception:
        health_data["components"]["notifications"] = {"status": "not_configured"}
    
    # Determine overall status
    if health_data.get("system", {}).get("error"):
        health_data["status"] = "degraded"
    
    return health_data


# ============== Server Runner ==============

def run_server(host: str = "127.0.0.1", port: int = 8765):
    """Run the FastAPI server."""
    import uvicorn
    logger.info(f"Starting API server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
