"""Telegram notification service."""

import asyncio
from typing import Optional
import aiohttp

from src.utils.logger import get_logger

logger = get_logger()


class TelegramNotifier:
    """
    Sends notifications via Telegram Bot API.
    
    To use this:
    1. Create a bot with @BotFather on Telegram
    2. Get your bot token
    3. Start a chat with your bot
    4. Get your chat ID (use @userinfobot or similar)
    """
    
    API_URL = "https://api.telegram.org/bot{token}/{method}"
    
    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize Telegram notifier.
        
        Args:
            bot_token: Telegram bot token from @BotFather
            chat_id: Chat ID to send messages to
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
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
    
    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a text message.
        
        Args:
            text: Message text (supports HTML formatting)
            parse_mode: Parse mode (HTML or Markdown)
            
        Returns:
            True if sent successfully
        """
        try:
            session = await self._get_session()
            url = self.API_URL.format(token=self.bot_token, method="sendMessage")
            
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    logger.debug("Telegram message sent successfully")
                    return True
                else:
                    error = await response.text()
                    logger.error(f"Telegram API error: {error}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False
    
    async def send_trade_alert(self, action: str, symbol: str, price: float,
                               quantity: float, pnl: Optional[float] = None) -> bool:
        """
        Send a trade alert.
        
        Args:
            action: Trade action (BUY, SELL)
            symbol: Trading pair
            price: Execution price
            quantity: Trade quantity
            pnl: Realized P&L (for exits)
        """
        emoji = "🟢" if action.upper() == "BUY" else "🔴"
        
        message = f"""
{emoji} <b>{action.upper()}</b> {symbol}

📊 <b>Trade Details:</b>
• Price: ${price:,.2f}
• Quantity: {quantity:.6f}
• Value: ${price * quantity:,.2f}
"""
        
        if pnl is not None:
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            message += f"\n{pnl_emoji} <b>P&L:</b> ${pnl:+,.2f}"
        
        return await self.send_message(message)
    
    async def send_backtest_summary(self, strategy: str, symbol: str,
                                     total_return: float, trades: int,
                                     win_rate: float) -> bool:
        """
        Send backtest summary notification.
        
        Args:
            strategy: Strategy name
            symbol: Trading pair
            total_return: Total return percentage
            trades: Number of trades
            win_rate: Win rate percentage
        """
        emoji = "🎯" if total_return >= 0 else "⚠️"
        
        message = f"""
{emoji} <b>Backtest Complete</b>

📈 <b>Strategy:</b> {strategy}
💱 <b>Symbol:</b> {symbol}

<b>Results:</b>
• Return: {total_return:+.2f}%
• Trades: {trades}
• Win Rate: {win_rate:.1f}%
"""
        
        return await self.send_message(message)
    
    async def send_error_alert(self, error_type: str, message: str) -> bool:
        """
        Send error alert.
        
        Args:
            error_type: Type of error
            message: Error message
        """
        alert = f"""
🚨 <b>Error Alert</b>

<b>Type:</b> {error_type}
<b>Message:</b> {message}
"""
        
        return await self.send_message(alert)
    
    def send_sync(self, text: str) -> bool:
        """
        Synchronous wrapper for sending messages.
        
        Args:
            text: Message text
            
        Returns:
            True if sent successfully
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.send_message(text))


def create_telegram_notifier(config: dict) -> Optional[TelegramNotifier]:
    """
    Create Telegram notifier from config.
    
    Args:
        config: Configuration dictionary with telegram settings
        
    Returns:
        TelegramNotifier instance or None if not configured
    """
    telegram_config = config.get("notifications", {}).get("telegram", {})
    
    if not telegram_config.get("enabled"):
        return None
    
    bot_token = telegram_config.get("bot_token")
    chat_id = telegram_config.get("chat_id")
    
    if not bot_token or not chat_id:
        logger.warning("Telegram enabled but missing bot_token or chat_id")
        return None
    
    return TelegramNotifier(bot_token, chat_id)
