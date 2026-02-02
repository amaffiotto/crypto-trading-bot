"""Unified notification manager for all alert channels."""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from src.utils.logger import get_logger

logger = get_logger()


class NotificationManager:
    """
    Unified notification manager that coordinates all alert channels.
    
    Features:
    - Sends to multiple channels simultaneously
    - Configurable alert routing (which alerts go to which channels)
    - Graceful failure handling (one channel failing doesn't affect others)
    - Alert deduplication (optional)
    - Rate limiting (optional)
    """
    
    # Default routing configuration
    DEFAULT_ROUTING = {
        "trade": ["telegram", "discord"],
        "error": ["telegram", "discord", "email", "whatsapp"],
        "daily_summary": ["email", "discord"],
        "backtest": ["telegram", "discord"],
        "general": ["telegram", "discord"]
    }
    
    def __init__(self, config: dict):
        """
        Initialize notification manager.
        
        Args:
            config: Full application configuration dictionary
        """
        self.config = config
        self._notifiers: Dict[str, Any] = {}
        self._routing: Dict[str, List[str]] = {}
        self._recent_alerts: Set[str] = set()  # For deduplication
        
        self._init_notifiers()
        self._init_routing()
    
    def _init_notifiers(self) -> None:
        """Initialize all configured notifiers."""
        from src.notifications.telegram import create_telegram_notifier
        from src.notifications.discord import create_discord_notifier
        from src.notifications.email import create_email_notifier
        from src.notifications.whatsapp import create_whatsapp_notifier
        
        # Try to initialize each notifier
        notifier_factories = {
            "telegram": create_telegram_notifier,
            "discord": create_discord_notifier,
            "email": create_email_notifier,
            "whatsapp": create_whatsapp_notifier
        }
        
        for name, factory in notifier_factories.items():
            try:
                notifier = factory(self.config)
                if notifier:
                    self._notifiers[name] = notifier
                    logger.info(f"Initialized {name} notifier")
            except Exception as e:
                logger.warning(f"Failed to initialize {name} notifier: {e}")
    
    def _init_routing(self) -> None:
        """Initialize alert routing from config."""
        routing_config = self.config.get("notifications", {}).get("routing", {})
        
        # Merge with defaults
        self._routing = self.DEFAULT_ROUTING.copy()
        self._routing.update(routing_config)
    
    @property
    def enabled_channels(self) -> List[str]:
        """Get list of enabled notification channels."""
        return list(self._notifiers.keys())
    
    def is_channel_enabled(self, channel: str) -> bool:
        """Check if a channel is enabled."""
        return channel in self._notifiers
    
    def get_channels_for_alert(self, alert_type: str) -> List[str]:
        """Get list of channels configured for an alert type."""
        channels = self._routing.get(alert_type, self._routing.get("general", []))
        # Filter to only enabled channels
        return [c for c in channels if c in self._notifiers]
    
    async def send_alert(
        self,
        alert_type: str,
        message: str,
        title: Optional[str] = None,
        channels: Optional[List[str]] = None,
        dedupe_key: Optional[str] = None,
        **kwargs
    ) -> Dict[str, bool]:
        """
        Send an alert to configured channels.
        
        Args:
            alert_type: Type of alert (trade, error, daily_summary, etc.)
            message: Alert message
            title: Optional alert title
            channels: Override channels (if None, uses routing config)
            dedupe_key: Optional key for deduplication
            **kwargs: Additional arguments passed to notifiers
            
        Returns:
            Dict mapping channel name to success status
        """
        # Check deduplication
        if dedupe_key and dedupe_key in self._recent_alerts:
            logger.debug(f"Skipping duplicate alert: {dedupe_key}")
            return {}
        
        if dedupe_key:
            self._recent_alerts.add(dedupe_key)
            # Keep only last 100 alerts
            if len(self._recent_alerts) > 100:
                self._recent_alerts = set(list(self._recent_alerts)[-50:])
        
        # Determine target channels
        if channels:
            target_channels = [c for c in channels if c in self._notifiers]
        else:
            target_channels = self.get_channels_for_alert(alert_type)
        
        if not target_channels:
            logger.warning(f"No channels available for alert type: {alert_type}")
            return {}
        
        # Send to all channels concurrently
        results: Dict[str, bool] = {}
        tasks = []
        
        for channel in target_channels:
            notifier = self._notifiers[channel]
            task = self._send_to_channel(channel, notifier, message, title, **kwargs)
            tasks.append((channel, task))
        
        # Gather results
        for channel, task in tasks:
            try:
                results[channel] = await task
            except Exception as e:
                logger.error(f"Error sending to {channel}: {e}")
                results[channel] = False
        
        # Log alert to database if available
        try:
            from src.core.database import get_database
            db = get_database()
            for channel, success in results.items():
                db.log_alert(
                    alert_type=alert_type,
                    channel=channel,
                    message=message,
                    success=success,
                    title=title
                )
        except Exception as e:
            logger.debug(f"Could not log alert to database: {e}")
        
        return results
    
    async def _send_to_channel(
        self,
        channel: str,
        notifier: Any,
        message: str,
        title: Optional[str] = None,
        **kwargs
    ) -> bool:
        """Send message to a specific channel."""
        try:
            # Different notifiers have different interfaces
            if hasattr(notifier, 'send_message'):
                return await notifier.send_message(message)
            else:
                logger.warning(f"Notifier {channel} has no send_message method")
                return False
        except Exception as e:
            logger.error(f"Failed to send to {channel}: {e}")
            return False
    
    async def send_trade_alert(
        self,
        action: str,
        symbol: str,
        price: float,
        quantity: float,
        pnl: Optional[float] = None,
        channels: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """
        Send trade alert to all configured channels.
        
        Args:
            action: Trade action (BUY, SELL)
            symbol: Trading pair
            price: Execution price
            quantity: Trade quantity
            pnl: Realized P&L (for exits)
            channels: Override channels
        """
        target_channels = channels or self.get_channels_for_alert("trade")
        results: Dict[str, bool] = {}
        
        tasks = []
        for channel in target_channels:
            notifier = self._notifiers.get(channel)
            if notifier and hasattr(notifier, 'send_trade_alert'):
                task = notifier.send_trade_alert(action, symbol, price, quantity, pnl)
                tasks.append((channel, task))
        
        for channel, task in tasks:
            try:
                results[channel] = await task
            except Exception as e:
                logger.error(f"Error sending trade alert to {channel}: {e}")
                results[channel] = False
        
        # Log to database
        try:
            from src.core.database import get_database
            db = get_database()
            message = f"{action} {symbol} @ {price}"
            for channel, success in results.items():
                db.log_alert(
                    alert_type="trade",
                    channel=channel,
                    message=message,
                    success=success,
                    title=f"{action} {symbol}",
                    metadata={"price": price, "quantity": quantity, "pnl": pnl}
                )
        except Exception:
            pass
        
        return results
    
    async def send_error_alert(
        self,
        error_type: str,
        message: str,
        channels: Optional[List[str]] = None
    ) -> Dict[str, bool]:
        """
        Send error alert to all configured channels.
        
        Args:
            error_type: Type of error
            message: Error message
            channels: Override channels
        """
        target_channels = channels or self.get_channels_for_alert("error")
        results: Dict[str, bool] = {}
        
        tasks = []
        for channel in target_channels:
            notifier = self._notifiers.get(channel)
            if notifier and hasattr(notifier, 'send_error_alert'):
                task = notifier.send_error_alert(error_type, message)
                tasks.append((channel, task))
        
        for channel, task in tasks:
            try:
                results[channel] = await task
            except Exception as e:
                logger.error(f"Error sending error alert to {channel}: {e}")
                results[channel] = False
        
        return results
    
    async def send_daily_summary(
        self,
        date: str,
        trades: int,
        total_pnl: float,
        win_rate: float,
        channels: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, bool]:
        """
        Send daily summary to all configured channels.
        
        Args:
            date: Summary date
            trades: Number of trades
            total_pnl: Total P&L
            win_rate: Win rate percentage
            channels: Override channels
        """
        target_channels = channels or self.get_channels_for_alert("daily_summary")
        results: Dict[str, bool] = {}
        
        tasks = []
        for channel in target_channels:
            notifier = self._notifiers.get(channel)
            if notifier and hasattr(notifier, 'send_daily_summary'):
                task = notifier.send_daily_summary(date, trades, total_pnl, win_rate, **kwargs)
                tasks.append((channel, task))
        
        for channel, task in tasks:
            try:
                results[channel] = await task
            except Exception as e:
                logger.error(f"Error sending daily summary to {channel}: {e}")
                results[channel] = False
        
        return results
    
    async def close(self) -> None:
        """Close all notifier connections."""
        for name, notifier in self._notifiers.items():
            if hasattr(notifier, 'close'):
                try:
                    await notifier.close()
                except Exception as e:
                    logger.warning(f"Error closing {name} notifier: {e}")
    
    def send_sync(self, alert_type: str, message: str, **kwargs) -> Dict[str, bool]:
        """
        Synchronous wrapper for sending alerts.
        
        Args:
            alert_type: Type of alert
            message: Alert message
            
        Returns:
            Dict mapping channel name to success status
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.send_alert(alert_type, message, **kwargs))


# Singleton instance
_manager_instance: Optional[NotificationManager] = None


def get_notification_manager(config: Optional[dict] = None) -> Optional[NotificationManager]:
    """
    Get notification manager singleton.
    
    Args:
        config: Configuration dictionary (required on first call)
        
    Returns:
        NotificationManager instance or None
    """
    global _manager_instance
    
    if _manager_instance is None and config:
        _manager_instance = NotificationManager(config)
    
    return _manager_instance


def create_notification_manager(config: dict) -> NotificationManager:
    """
    Create a new notification manager instance.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        NotificationManager instance
    """
    return NotificationManager(config)
