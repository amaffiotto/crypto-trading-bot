"""Exchange management module using ccxt."""

import asyncio
from typing import Any, Dict, List, Optional
import ccxt
import ccxt.async_support as ccxt_async

from src.utils.logger import get_logger

logger = get_logger()


# List of popular exchanges supported
SUPPORTED_EXCHANGES = [
    "binance",
    "kraken", 
    "coinbase",
    "kucoin",
    "bybit",
    "okx",
    "bitfinex",
    "huobi",
    "gate",
    "mexc"
]


class ExchangeManager:
    """Manages connections to cryptocurrency exchanges via ccxt."""
    
    TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
    
    def __init__(self):
        """Initialize exchange manager."""
        self._exchanges: Dict[str, ccxt.Exchange] = {}
        self._async_exchanges: Dict[str, ccxt_async.Exchange] = {}
    
    @staticmethod
    def get_supported_exchanges() -> List[str]:
        """Get list of supported exchanges."""
        return SUPPORTED_EXCHANGES
    
    @staticmethod
    def get_all_exchanges() -> List[str]:
        """Get list of all available exchanges in ccxt."""
        return ccxt.exchanges
    
    def connect(self, exchange_id: str, api_key: str = "", 
                api_secret: str = "", sandbox: bool = False) -> ccxt.Exchange:
        """
        Connect to an exchange.
        
        Args:
            exchange_id: Exchange identifier (e.g., 'binance')
            api_key: API key for authenticated requests
            api_secret: API secret for authenticated requests
            sandbox: Use testnet/sandbox mode if available
            
        Returns:
            Connected exchange instance
        """
        if exchange_id in self._exchanges:
            return self._exchanges[exchange_id]
        
        try:
            exchange_class = getattr(ccxt, exchange_id)
            
            config = {
                'enableRateLimit': True,
                'timeout': 30000,
            }
            
            if api_key and api_secret:
                config['apiKey'] = api_key
                config['secret'] = api_secret
            
            exchange = exchange_class(config)
            
            if sandbox and exchange.has.get('sandbox'):
                exchange.set_sandbox_mode(True)
                logger.info(f"Sandbox mode enabled for {exchange_id}")
            
            self._exchanges[exchange_id] = exchange
            logger.info(f"Connected to {exchange_id}")
            
            return exchange
            
        except AttributeError:
            raise ValueError(f"Unknown exchange: {exchange_id}")
        except Exception as e:
            logger.error(f"Error connecting to {exchange_id}: {e}")
            raise
    
    async def connect_async(self, exchange_id: str, api_key: str = "",
                            api_secret: str = "", sandbox: bool = False) -> ccxt_async.Exchange:
        """
        Connect to an exchange asynchronously.
        
        Args:
            exchange_id: Exchange identifier
            api_key: API key
            api_secret: API secret
            sandbox: Use sandbox mode
            
        Returns:
            Async exchange instance
        """
        if exchange_id in self._async_exchanges:
            return self._async_exchanges[exchange_id]
        
        try:
            exchange_class = getattr(ccxt_async, exchange_id)
            
            config = {
                'enableRateLimit': True,
                'timeout': 30000,
            }
            
            if api_key and api_secret:
                config['apiKey'] = api_key
                config['secret'] = api_secret
            
            exchange = exchange_class(config)
            
            if sandbox and exchange.has.get('sandbox'):
                exchange.set_sandbox_mode(True)
            
            self._async_exchanges[exchange_id] = exchange
            logger.info(f"Connected to {exchange_id} (async)")
            
            return exchange
            
        except Exception as e:
            logger.error(f"Error connecting to {exchange_id}: {e}")
            raise
    
    def get_exchange(self, exchange_id: str) -> Optional[ccxt.Exchange]:
        """Get a connected exchange instance."""
        return self._exchanges.get(exchange_id)
    
    def disconnect(self, exchange_id: str) -> None:
        """Disconnect from an exchange."""
        if exchange_id in self._exchanges:
            del self._exchanges[exchange_id]
            logger.info(f"Disconnected from {exchange_id}")
    
    async def close_async(self) -> None:
        """Close all async exchange connections."""
        for exchange_id, exchange in self._async_exchanges.items():
            await exchange.close()
            logger.info(f"Closed async connection to {exchange_id}")
        self._async_exchanges.clear()
    
    def fetch_markets(self, exchange_id: str) -> List[Dict[str, Any]]:
        """
        Fetch available markets from an exchange.
        
        Args:
            exchange_id: Exchange identifier
            
        Returns:
            List of market information dictionaries
        """
        exchange = self.get_exchange(exchange_id)
        if not exchange:
            exchange = self.connect(exchange_id)
        
        markets = exchange.load_markets()
        return list(markets.values())
    
    def get_symbols(self, exchange_id: str, quote_currency: str = "USDT") -> List[str]:
        """
        Get trading symbols for an exchange filtered by quote currency.
        
        Args:
            exchange_id: Exchange identifier
            quote_currency: Quote currency to filter by (e.g., 'USDT', 'BTC')
            
        Returns:
            List of trading symbols
        """
        markets = self.fetch_markets(exchange_id)
        symbols = []
        
        for market in markets:
            if market.get('quote') == quote_currency and market.get('active', True):
                symbols.append(market['symbol'])
        
        return sorted(symbols)
    
    def fetch_ticker(self, exchange_id: str, symbol: str) -> Dict[str, Any]:
        """
        Fetch current ticker for a symbol.
        
        Args:
            exchange_id: Exchange identifier
            symbol: Trading pair (e.g., 'BTC/USDT')
            
        Returns:
            Ticker information
        """
        exchange = self.get_exchange(exchange_id)
        if not exchange:
            exchange = self.connect(exchange_id)
        
        return exchange.fetch_ticker(symbol)
    
    def fetch_ohlcv(self, exchange_id: str, symbol: str, timeframe: str = '1h',
                    since: Optional[int] = None, limit: int = 500) -> List[List]:
        """
        Fetch OHLCV (candlestick) data.
        
        Args:
            exchange_id: Exchange identifier
            symbol: Trading pair
            timeframe: Candlestick timeframe
            since: Start timestamp in milliseconds
            limit: Maximum number of candles
            
        Returns:
            List of OHLCV data [timestamp, open, high, low, close, volume]
        """
        exchange = self.get_exchange(exchange_id)
        if not exchange:
            exchange = self.connect(exchange_id)
        
        if timeframe not in self.TIMEFRAMES:
            raise ValueError(f"Invalid timeframe: {timeframe}. Supported: {self.TIMEFRAMES}")
        
        return exchange.fetch_ohlcv(symbol, timeframe, since, limit)
    
    def get_exchange_timeframes(self, exchange_id: str) -> List[str]:
        """Get supported timeframes for an exchange."""
        exchange = self.get_exchange(exchange_id)
        if not exchange:
            exchange = self.connect(exchange_id)
        
        return list(exchange.timeframes.keys()) if hasattr(exchange, 'timeframes') else self.TIMEFRAMES
    
    def fetch_balance(self, exchange_id: str) -> Dict[str, Any]:
        """
        Fetch account balance.
        
        Args:
            exchange_id: Exchange identifier
            
        Returns:
            Balance information
        """
        exchange = self.get_exchange(exchange_id)
        if not exchange:
            raise ValueError(f"Not connected to {exchange_id}")
        
        if not exchange.apiKey:
            raise ValueError(f"API keys required for {exchange_id}")
        
        return exchange.fetch_balance()
    
    def create_order(self, exchange_id: str, symbol: str, order_type: str,
                     side: str, amount: float, price: Optional[float] = None) -> Dict[str, Any]:
        """
        Create an order on the exchange.
        
        Args:
            exchange_id: Exchange identifier
            symbol: Trading pair
            order_type: 'market' or 'limit'
            side: 'buy' or 'sell'
            amount: Order amount
            price: Price for limit orders
            
        Returns:
            Order information
        """
        exchange = self.get_exchange(exchange_id)
        if not exchange:
            raise ValueError(f"Not connected to {exchange_id}")
        
        if not exchange.apiKey:
            raise ValueError(f"API keys required for {exchange_id}")
        
        return exchange.create_order(symbol, order_type, side, amount, price)
