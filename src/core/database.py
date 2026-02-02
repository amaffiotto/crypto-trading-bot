"""SQLite database module for persistent storage."""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger()


class DatabaseManager:
    """
    Manages SQLite database connections and operations.
    
    Thread-safe with connection pooling per thread.
    """
    
    SCHEMA_VERSION = 1
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file. Defaults to data/trading.db
        """
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = Path(__file__).parent.parent.parent / "data" / "trading.db"
        
        # Thread-local storage for connections
        self._local = threading.local()
        self._lock = threading.Lock()
        
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize schema
        self._init_schema()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable foreign keys
            self._local.connection.execute("PRAGMA foreign_keys = ON")
        return self._local.connection
    
    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor with auto-commit."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            cursor.close()
    
    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self.get_cursor() as cursor:
            # Schema version table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
            """)
            
            # Check current version
            cursor.execute("SELECT MAX(version) FROM schema_version")
            row = cursor.fetchone()
            current_version = row[0] if row[0] else 0
            
            if current_version < self.SCHEMA_VERSION:
                self._run_migrations(cursor, current_version)
    
    def _run_migrations(self, cursor: sqlite3.Cursor, from_version: int) -> None:
        """Run database migrations."""
        logger.info(f"Running database migrations from v{from_version} to v{self.SCHEMA_VERSION}")
        
        if from_version < 1:
            self._migration_v1(cursor)
        
        # Record schema version
        cursor.execute(
            "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?)",
            (self.SCHEMA_VERSION, datetime.now().isoformat())
        )
        logger.info(f"Database migrated to v{self.SCHEMA_VERSION}")
    
    def _migration_v1(self, cursor: sqlite3.Cursor) -> None:
        """Initial schema - v1."""
        
        # Trades table - stores all executed trades
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                order_type TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                fee REAL DEFAULT 0,
                pnl REAL,
                mode TEXT NOT NULL,
                strategy TEXT,
                exchange TEXT,
                timeframe TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Journal entries table - user notes on trades
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER,
                timestamp TEXT NOT NULL,
                symbol TEXT,
                entry_type TEXT NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                tags TEXT,
                market_conditions TEXT,
                lessons_learned TEXT,
                rating INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (trade_id) REFERENCES trades(id)
            )
        """)
        
        # Alerts log table - record of sent notifications
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alerts_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                channel TEXT NOT NULL,
                title TEXT,
                message TEXT NOT NULL,
                success INTEGER NOT NULL,
                error_message TEXT,
                metadata TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for common queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_timestamp ON journal_entries(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_journal_trade_id ON journal_entries(trade_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts_log(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts_log(alert_type)")
    
    # ============== Trade Operations ==============
    
    def insert_trade(
        self,
        timestamp: datetime,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float,
        fee: float = 0,
        pnl: Optional[float] = None,
        mode: str = "paper",
        strategy: Optional[str] = None,
        exchange: Optional[str] = None,
        timeframe: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Insert a trade record.
        
        Returns:
            Trade ID
        """
        import json
        
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO trades 
                (timestamp, symbol, side, order_type, quantity, price, fee, pnl, 
                 mode, strategy, exchange, timeframe, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp.isoformat(),
                symbol,
                side,
                order_type,
                quantity,
                price,
                fee,
                pnl,
                mode,
                strategy,
                exchange,
                timeframe,
                json.dumps(metadata) if metadata else None
            ))
            return cursor.lastrowid
    
    def get_trades(
        self,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get trades with optional filters."""
        import json
        
        query = "SELECT * FROM trades WHERE 1=1"
        params = []
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        if strategy:
            query += " AND strategy = ?"
            params.append(strategy)
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            trades = []
            for row in rows:
                trade = dict(row)
                if trade.get('metadata'):
                    trade['metadata'] = json.loads(trade['metadata'])
                trades.append(trade)
            
            return trades
    
    def get_trade_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get aggregated trade statistics."""
        query = """
            SELECT 
                COUNT(*) as total_trades,
                SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                SUM(COALESCE(pnl, 0)) as total_pnl,
                SUM(fee) as total_fees,
                AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                AVG(CASE WHEN pnl < 0 THEN pnl END) as avg_loss,
                MAX(pnl) as largest_win,
                MIN(pnl) as largest_loss
            FROM trades
            WHERE 1=1
        """
        params = []
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())
        
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
            
            if row:
                total = row['total_trades'] or 0
                wins = row['winning_trades'] or 0
                return {
                    'total_trades': total,
                    'winning_trades': wins,
                    'losing_trades': row['losing_trades'] or 0,
                    'win_rate': (wins / total * 100) if total > 0 else 0,
                    'total_pnl': row['total_pnl'] or 0,
                    'total_fees': row['total_fees'] or 0,
                    'avg_win': row['avg_win'] or 0,
                    'avg_loss': row['avg_loss'] or 0,
                    'largest_win': row['largest_win'] or 0,
                    'largest_loss': row['largest_loss'] or 0
                }
            
            return {}
    
    # ============== Journal Operations ==============
    
    def insert_journal_entry(
        self,
        content: str,
        entry_type: str = "note",
        trade_id: Optional[int] = None,
        timestamp: Optional[datetime] = None,
        symbol: Optional[str] = None,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        market_conditions: Optional[str] = None,
        lessons_learned: Optional[str] = None,
        rating: Optional[int] = None
    ) -> int:
        """
        Insert a journal entry.
        
        Returns:
            Entry ID
        """
        import json
        
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO journal_entries
                (trade_id, timestamp, symbol, entry_type, title, content, tags,
                 market_conditions, lessons_learned, rating)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_id,
                (timestamp or datetime.now()).isoformat(),
                symbol,
                entry_type,
                title,
                content,
                json.dumps(tags) if tags else None,
                market_conditions,
                lessons_learned,
                rating
            ))
            return cursor.lastrowid
    
    def update_journal_entry(
        self,
        entry_id: int,
        **updates
    ) -> bool:
        """Update a journal entry."""
        import json
        
        allowed_fields = {
            'content', 'title', 'tags', 'market_conditions', 
            'lessons_learned', 'rating', 'entry_type'
        }
        
        fields_to_update = {k: v for k, v in updates.items() if k in allowed_fields}
        
        if not fields_to_update:
            return False
        
        if 'tags' in fields_to_update:
            fields_to_update['tags'] = json.dumps(fields_to_update['tags'])
        
        set_clause = ", ".join(f"{k} = ?" for k in fields_to_update.keys())
        set_clause += ", updated_at = ?"
        
        values = list(fields_to_update.values())
        values.append(datetime.now().isoformat())
        values.append(entry_id)
        
        with self.get_cursor() as cursor:
            cursor.execute(
                f"UPDATE journal_entries SET {set_clause} WHERE id = ?",
                values
            )
            return cursor.rowcount > 0
    
    def get_journal_entries(
        self,
        trade_id: Optional[int] = None,
        symbol: Optional[str] = None,
        entry_type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get journal entries with optional filters."""
        import json
        
        query = "SELECT * FROM journal_entries WHERE 1=1"
        params = []
        
        if trade_id:
            query += " AND trade_id = ?"
            params.append(trade_id)
        
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)
        
        if entry_type:
            query += " AND entry_type = ?"
            params.append(entry_type)
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())
        
        if tags:
            # Search for any of the tags
            tag_conditions = " OR ".join(["tags LIKE ?" for _ in tags])
            query += f" AND ({tag_conditions})"
            params.extend([f'%"{tag}"%' for tag in tags])
        
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            entries = []
            for row in rows:
                entry = dict(row)
                if entry.get('tags'):
                    entry['tags'] = json.loads(entry['tags'])
                entries.append(entry)
            
            return entries
    
    def delete_journal_entry(self, entry_id: int) -> bool:
        """Delete a journal entry."""
        with self.get_cursor() as cursor:
            cursor.execute("DELETE FROM journal_entries WHERE id = ?", (entry_id,))
            return cursor.rowcount > 0
    
    # ============== Alert Log Operations ==============
    
    def log_alert(
        self,
        alert_type: str,
        channel: str,
        message: str,
        success: bool,
        title: Optional[str] = None,
        error_message: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Log a sent alert/notification.
        
        Returns:
            Log entry ID
        """
        import json
        
        with self.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO alerts_log
                (timestamp, alert_type, channel, title, message, success, error_message, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                alert_type,
                channel,
                title,
                message,
                1 if success else 0,
                error_message,
                json.dumps(metadata) if metadata else None
            ))
            return cursor.lastrowid
    
    def get_alert_logs(
        self,
        alert_type: Optional[str] = None,
        channel: Optional[str] = None,
        success_only: bool = False,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get alert logs with optional filters."""
        import json
        
        query = "SELECT * FROM alerts_log WHERE 1=1"
        params = []
        
        if alert_type:
            query += " AND alert_type = ?"
            params.append(alert_type)
        
        if channel:
            query += " AND channel = ?"
            params.append(channel)
        
        if success_only:
            query += " AND success = 1"
        
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        with self.get_cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                log = dict(row)
                log['success'] = bool(log['success'])
                if log.get('metadata'):
                    log['metadata'] = json.loads(log['metadata'])
                logs.append(log)
            
            return logs
    
    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None


# Singleton instance
_db_instance: Optional[DatabaseManager] = None
_db_lock = threading.Lock()


def get_database(db_path: Optional[str] = None) -> DatabaseManager:
    """
    Get database manager singleton.
    
    Args:
        db_path: Optional path to database file
        
    Returns:
        DatabaseManager instance
    """
    global _db_instance
    
    with _db_lock:
        if _db_instance is None:
            _db_instance = DatabaseManager(db_path)
        return _db_instance
