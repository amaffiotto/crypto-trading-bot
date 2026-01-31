"""Discord notification service via webhooks."""

import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any
import aiohttp

from src.utils.logger import get_logger

logger = get_logger()


class DiscordNotifier:
    """
    Sends notifications via Discord webhooks.
    
    To use this:
    1. Go to your Discord server settings > Integrations > Webhooks
    2. Create a new webhook
    3. Copy the webhook URL
    """
    
    def __init__(self, webhook_url: str, username: str = "Trading Bot"):
        """
        Initialize Discord notifier.
        
        Args:
            webhook_url: Discord webhook URL
            username: Bot username to display
        """
        self.webhook_url = webhook_url
        self.username = username
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def send_message(self, content: str = "", 
                           embeds: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Send a message to Discord.
        
        Args:
            content: Plain text content
            embeds: List of embed objects
            
        Returns:
            True if sent successfully
        """
        try:
            session = await self._get_session()
            
            payload = {
                "username": self.username,
                "content": content
            }
            
            if embeds:
                payload["embeds"] = embeds
            
            async with session.post(self.webhook_url, json=payload) as response:
                if response.status in (200, 204):
                    logger.debug("Discord message sent successfully")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"Discord webhook error: {error}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending Discord message: {e}")
            return False
    
    async def send_trade_alert(self, action: str, symbol: str, price: float,
                               quantity: float, pnl: Optional[float] = None) -> bool:
        """
        Send a trade alert with embed.
        
        Args:
            action: Trade action (BUY, SELL)
            symbol: Trading pair
            price: Execution price
            quantity: Trade quantity
            pnl: Realized P&L (for exits)
        """
        color = 0x00FF00 if action.upper() == "BUY" else 0xFF0000
        
        fields = [
            {"name": "Symbol", "value": symbol, "inline": True},
            {"name": "Price", "value": f"${price:,.2f}", "inline": True},
            {"name": "Quantity", "value": f"{quantity:.6f}", "inline": True},
            {"name": "Value", "value": f"${price * quantity:,.2f}", "inline": True}
        ]
        
        if pnl is not None:
            pnl_color = "🟢" if pnl >= 0 else "🔴"
            fields.append({
                "name": "P&L", 
                "value": f"{pnl_color} ${pnl:+,.2f}", 
                "inline": True
            })
        
        embed = {
            "title": f"{'🟢' if action.upper() == 'BUY' else '🔴'} {action.upper()} Order Executed",
            "color": color,
            "fields": fields,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return await self.send_message(embeds=[embed])
    
    async def send_backtest_summary(self, strategy: str, symbol: str,
                                     timeframe: str, total_return: float,
                                     trades: int, win_rate: float,
                                     sharpe: float, max_dd: float) -> bool:
        """
        Send backtest summary with detailed embed.
        
        Args:
            strategy: Strategy name
            symbol: Trading pair
            timeframe: Data timeframe
            total_return: Total return percentage
            trades: Number of trades
            win_rate: Win rate percentage
            sharpe: Sharpe ratio
            max_dd: Max drawdown percentage
        """
        color = 0x00FF00 if total_return >= 0 else 0xFF5555
        
        embed = {
            "title": "📊 Backtest Results",
            "color": color,
            "fields": [
                {"name": "Strategy", "value": strategy, "inline": True},
                {"name": "Symbol", "value": symbol, "inline": True},
                {"name": "Timeframe", "value": timeframe, "inline": True},
                {"name": "Total Return", "value": f"{total_return:+.2f}%", "inline": True},
                {"name": "Total Trades", "value": str(trades), "inline": True},
                {"name": "Win Rate", "value": f"{win_rate:.1f}%", "inline": True},
                {"name": "Sharpe Ratio", "value": f"{sharpe:.2f}", "inline": True},
                {"name": "Max Drawdown", "value": f"-{max_dd:.2f}%", "inline": True}
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": "Crypto Trading Bot"}
        }
        
        return await self.send_message(embeds=[embed])
    
    async def send_error_alert(self, error_type: str, message: str) -> bool:
        """
        Send error alert.
        
        Args:
            error_type: Type of error
            message: Error message
        """
        embed = {
            "title": "🚨 Error Alert",
            "color": 0xFF0000,
            "fields": [
                {"name": "Type", "value": error_type, "inline": True},
                {"name": "Message", "value": message[:1024], "inline": False}
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return await self.send_message(embeds=[embed])
    
    async def send_daily_summary(self, date: str, trades: int,
                                  total_pnl: float, win_rate: float) -> bool:
        """
        Send daily trading summary.
        
        Args:
            date: Summary date
            trades: Number of trades
            total_pnl: Total P&L
            win_rate: Win rate percentage
        """
        color = 0x00FF00 if total_pnl >= 0 else 0xFF5555
        
        embed = {
            "title": f"📅 Daily Summary - {date}",
            "color": color,
            "fields": [
                {"name": "Total Trades", "value": str(trades), "inline": True},
                {"name": "Total P&L", "value": f"${total_pnl:+,.2f}", "inline": True},
                {"name": "Win Rate", "value": f"{win_rate:.1f}%", "inline": True}
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return await self.send_message(embeds=[embed])
    
    def send_sync(self, content: str) -> bool:
        """
        Synchronous wrapper for sending messages.
        
        Args:
            content: Message content
            
        Returns:
            True if sent successfully
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.send_message(content))


def create_discord_notifier(config: dict) -> Optional[DiscordNotifier]:
    """
    Create Discord notifier from config.
    
    Args:
        config: Configuration dictionary with discord settings
        
    Returns:
        DiscordNotifier instance or None if not configured
    """
    discord_config = config.get("notifications", {}).get("discord", {})
    
    if not discord_config.get("enabled"):
        return None
    
    webhook_url = discord_config.get("webhook_url")
    
    if not webhook_url:
        logger.warning("Discord enabled but missing webhook_url")
        return None
    
    return DiscordNotifier(webhook_url)
