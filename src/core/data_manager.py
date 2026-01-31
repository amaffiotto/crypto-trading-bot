"""Data management module for OHLCV data with caching."""

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple
import pandas as pd

from src.core.exchange import ExchangeManager
from src.utils.logger import get_logger

logger = get_logger()


class DataManager:
    """Manages OHLCV data downloading, caching, and retrieval."""
    
    SUPPORTED_TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']
    
    # Timeframe to milliseconds mapping
    TIMEFRAME_MS = {
        '1m': 60 * 1000,
        '5m': 5 * 60 * 1000,
        '15m': 15 * 60 * 1000,
        '1h': 60 * 60 * 1000,
        '4h': 4 * 60 * 60 * 1000,
        '1d': 24 * 60 * 60 * 1000,
        '1w': 7 * 24 * 60 * 60 * 1000,
    }
    
    def __init__(self, cache_dir: Optional[str] = None, 
                 exchange_manager: Optional[ExchangeManager] = None):
        """
        Initialize data manager.
        
        Args:
            cache_dir: Directory for caching data. Defaults to data/ohlcv
            exchange_manager: ExchangeManager instance
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path(__file__).parent.parent.parent / "data" / "ohlcv"
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.exchange_manager = exchange_manager or ExchangeManager()
    
    def _get_cache_path(self, exchange: str, symbol: str, timeframe: str) -> Path:
        """Get the cache file path for a specific data request."""
        # Replace / in symbol with _
        safe_symbol = symbol.replace('/', '_')
        exchange_dir = self.cache_dir / exchange
        exchange_dir.mkdir(exist_ok=True)
        return exchange_dir / f"{safe_symbol}_{timeframe}.parquet"
    
    def _load_cache(self, cache_path: Path) -> Optional[pd.DataFrame]:
        """Load cached data from parquet file."""
        if cache_path.exists():
            try:
                df = pd.read_parquet(cache_path)
                logger.debug(f"Loaded {len(df)} rows from cache: {cache_path}")
                return df
            except Exception as e:
                logger.warning(f"Error reading cache {cache_path}: {e}")
        return None
    
    def _save_cache(self, df: pd.DataFrame, cache_path: Path) -> None:
        """Save data to parquet cache."""
        try:
            df.to_parquet(cache_path, index=False)
            logger.debug(f"Saved {len(df)} rows to cache: {cache_path}")
        except Exception as e:
            logger.warning(f"Error saving cache {cache_path}: {e}")
    
    def _fetch_ohlcv_batch(self, exchange: str, symbol: str, timeframe: str,
                           since: int, until: int, progress_callback=None) -> pd.DataFrame:
        """
        Fetch OHLCV data in batches (handles exchange limits).
        
        Args:
            exchange: Exchange identifier
            symbol: Trading pair
            timeframe: Candlestick timeframe
            since: Start timestamp in milliseconds
            until: End timestamp in milliseconds
            progress_callback: Optional callback for progress updates
            
        Returns:
            DataFrame with OHLCV data
        """
        all_data = []
        current = since
        batch_size = 1000  # Most exchanges limit to 1000 candles per request
        timeframe_ms = self.TIMEFRAME_MS[timeframe]
        
        total_candles = (until - since) // timeframe_ms
        fetched = 0
        
        while current < until:
            try:
                data = self.exchange_manager.fetch_ohlcv(
                    exchange, symbol, timeframe, 
                    since=current, limit=batch_size
                )
                
                if not data:
                    break
                
                all_data.extend(data)
                fetched += len(data)
                
                if progress_callback:
                    progress = min(100, int(fetched / total_candles * 100))
                    progress_callback(progress, fetched, total_candles)
                
                # Move to next batch
                last_timestamp = data[-1][0]
                if last_timestamp <= current:
                    break
                current = last_timestamp + timeframe_ms
                
                # Rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error fetching data: {e}")
                break
        
        if not all_data:
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
        
        return df
    
    def get_ohlcv(self, exchange: str, symbol: str, timeframe: str,
                  start: datetime, end: Optional[datetime] = None,
                  use_cache: bool = True, progress_callback=None) -> pd.DataFrame:
        """
        Get OHLCV data for a symbol, using cache when available.
        
        Args:
            exchange: Exchange identifier (e.g., 'binance')
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candlestick timeframe (e.g., '1h')
            start: Start datetime
            end: End datetime (defaults to now)
            use_cache: Whether to use cached data
            progress_callback: Optional callback(progress_pct, fetched, total)
            
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        if timeframe not in self.SUPPORTED_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}. Use: {self.SUPPORTED_TIMEFRAMES}")
        
        if end is None:
            end = datetime.now()
        
        since_ms = int(start.timestamp() * 1000)
        until_ms = int(end.timestamp() * 1000)
        
        cache_path = self._get_cache_path(exchange, symbol, timeframe)
        cached_df = self._load_cache(cache_path) if use_cache else None
        
        if cached_df is not None and not cached_df.empty:
            # Check if cache covers the requested range
            cache_start = cached_df['timestamp'].min().timestamp() * 1000
            cache_end = cached_df['timestamp'].max().timestamp() * 1000
            
            # If cache covers the range, filter and return
            if cache_start <= since_ms and cache_end >= until_ms:
                mask = (cached_df['timestamp'] >= start) & (cached_df['timestamp'] <= end)
                logger.info(f"Using cached data for {symbol} ({len(cached_df[mask])} candles)")
                return cached_df[mask].reset_index(drop=True)
            
            # Partial cache - need to fetch missing data
            logger.info(f"Cache partial hit for {symbol}, fetching missing data...")
            
            # Fetch older data if needed
            if since_ms < cache_start:
                older_df = self._fetch_ohlcv_batch(
                    exchange, symbol, timeframe, 
                    since_ms, int(cache_start), progress_callback
                )
                if not older_df.empty:
                    cached_df = pd.concat([older_df, cached_df], ignore_index=True)
            
            # Fetch newer data if needed
            if until_ms > cache_end:
                newer_df = self._fetch_ohlcv_batch(
                    exchange, symbol, timeframe,
                    int(cache_end), until_ms, progress_callback
                )
                if not newer_df.empty:
                    cached_df = pd.concat([cached_df, newer_df], ignore_index=True)
            
            # Deduplicate and sort
            cached_df = cached_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
            
            # Save updated cache
            self._save_cache(cached_df, cache_path)
            
            # Return filtered range
            mask = (cached_df['timestamp'] >= start) & (cached_df['timestamp'] <= end)
            return cached_df[mask].reset_index(drop=True)
        
        # No cache - fetch all data
        logger.info(f"Downloading {symbol} data from {exchange} ({timeframe})...")
        df = self._fetch_ohlcv_batch(exchange, symbol, timeframe, since_ms, until_ms, progress_callback)
        
        if not df.empty and use_cache:
            self._save_cache(df, cache_path)
        
        return df
    
    def get_available_data(self) -> dict:
        """
        Get information about cached data.
        
        Returns:
            Dictionary with cache information per exchange/symbol
        """
        info = {}
        
        for exchange_dir in self.cache_dir.iterdir():
            if exchange_dir.is_dir():
                exchange_name = exchange_dir.name
                info[exchange_name] = {}
                
                for cache_file in exchange_dir.glob("*.parquet"):
                    try:
                        df = pd.read_parquet(cache_file)
                        symbol_tf = cache_file.stem  # e.g., "BTC_USDT_1h"
                        info[exchange_name][symbol_tf] = {
                            'rows': len(df),
                            'start': df['timestamp'].min().isoformat(),
                            'end': df['timestamp'].max().isoformat(),
                            'size_mb': cache_file.stat().st_size / (1024 * 1024)
                        }
                    except Exception:
                        pass
        
        return info
    
    def clear_cache(self, exchange: Optional[str] = None, 
                    symbol: Optional[str] = None) -> int:
        """
        Clear cached data.
        
        Args:
            exchange: Specific exchange to clear (or all if None)
            symbol: Specific symbol to clear (or all if None)
            
        Returns:
            Number of files deleted
        """
        deleted = 0
        
        if exchange:
            exchange_dir = self.cache_dir / exchange
            if exchange_dir.exists():
                if symbol:
                    safe_symbol = symbol.replace('/', '_')
                    for f in exchange_dir.glob(f"{safe_symbol}_*.parquet"):
                        f.unlink()
                        deleted += 1
                else:
                    for f in exchange_dir.glob("*.parquet"):
                        f.unlink()
                        deleted += 1
        else:
            for f in self.cache_dir.rglob("*.parquet"):
                f.unlink()
                deleted += 1
        
        logger.info(f"Cleared {deleted} cache files")
        return deleted
    
    def download_for_backtest(self, exchange: str, symbol: str, timeframe: str,
                              days: int = 365, progress_callback=None) -> Tuple[pd.DataFrame, str]:
        """
        Download data for backtesting.
        
        Args:
            exchange: Exchange identifier
            symbol: Trading pair
            timeframe: Candlestick timeframe
            days: Number of days of historical data
            progress_callback: Progress callback function
            
        Returns:
            Tuple of (DataFrame, status_message)
        """
        end = datetime.now()
        start = end - timedelta(days=days)
        
        try:
            df = self.get_ohlcv(exchange, symbol, timeframe, start, end, 
                               use_cache=True, progress_callback=progress_callback)
            
            if df.empty:
                return df, f"No data available for {symbol} on {exchange}"
            
            msg = f"Downloaded {len(df)} candles from {df['timestamp'].min()} to {df['timestamp'].max()}"
            logger.info(msg)
            return df, msg
            
        except Exception as e:
            error_msg = f"Error downloading data: {e}"
            logger.error(error_msg)
            return pd.DataFrame(), error_msg
