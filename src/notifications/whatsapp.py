"""WhatsApp notification service via Twilio."""

import asyncio
from typing import List, Optional

from src.utils.logger import get_logger

logger = get_logger()


class WhatsAppNotifier:
    """
    Sends notifications via WhatsApp using Twilio API.
    
    To use this:
    1. Create a Twilio account at https://www.twilio.com
    2. Get your Account SID and Auth Token from the console
    3. Set up WhatsApp sandbox or get an approved WhatsApp Business number
    4. For sandbox: Join by sending "join <sandbox-keyword>" to +1 415 523 8886
    
    Note: Twilio WhatsApp sandbox is free for testing but has limitations.
    For production, you need a WhatsApp Business API approved number.
    """
    
    API_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    
    def __init__(
        self,
        account_sid: str,
        auth_token: str,
        from_number: str,
        to_numbers: List[str]
    ):
        """
        Initialize WhatsApp notifier.
        
        Args:
            account_sid: Twilio Account SID
            auth_token: Twilio Auth Token
            from_number: WhatsApp sender number (format: whatsapp:+14155238886)
            to_numbers: List of recipient numbers (format: whatsapp:+1234567890)
        """
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number
        self.to_numbers = to_numbers
        self._session = None
    
    async def _get_session(self):
        """Get or create aiohttp session."""
        if self._session is None:
            import aiohttp
            auth = aiohttp.BasicAuth(self.account_sid, self.auth_token)
            self._session = aiohttp.ClientSession(auth=auth)
        return self._session
    
    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def send_message(self, text: str) -> bool:
        """
        Send a WhatsApp message to all configured recipients.
        
        Args:
            text: Message text (max 1600 characters)
            
        Returns:
            True if sent to at least one recipient successfully
        """
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp not installed. Run: pip install aiohttp")
            return False
        
        # Truncate message if too long
        if len(text) > 1600:
            text = text[:1597] + "..."
        
        session = await self._get_session()
        url = self.API_URL.format(account_sid=self.account_sid)
        
        success_count = 0
        
        for to_number in self.to_numbers:
            try:
                data = {
                    "From": self.from_number,
                    "To": to_number,
                    "Body": text
                }
                
                async with session.post(url, data=data) as response:
                    if response.status in (200, 201):
                        logger.debug(f"WhatsApp message sent to {to_number}")
                        success_count += 1
                    else:
                        error = await response.text()
                        logger.error(f"Twilio API error for {to_number}: {error}")
                        
            except Exception as e:
                logger.error(f"Error sending WhatsApp to {to_number}: {e}")
        
        return success_count > 0
    
    async def send_trade_alert(
        self,
        action: str,
        symbol: str,
        price: float,
        quantity: float,
        pnl: Optional[float] = None
    ) -> bool:
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
{emoji} *{action.upper()}* {symbol}

📊 *Trade Details:*
• Price: ${price:,.2f}
• Quantity: {quantity:.6f}
• Value: ${price * quantity:,.2f}
"""
        
        if pnl is not None:
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            message += f"\n{pnl_emoji} *P&L:* ${pnl:+,.2f}"
        
        return await self.send_message(message)
    
    async def send_error_alert(self, error_type: str, message: str) -> bool:
        """
        Send error alert.
        
        Args:
            error_type: Type of error
            message: Error message
        """
        # Truncate error message if too long
        if len(message) > 500:
            message = message[:497] + "..."
        
        alert = f"""
🚨 *Error Alert*

*Type:* {error_type}
*Message:* {message}
"""
        
        return await self.send_message(alert)
    
    async def send_daily_summary(
        self,
        date: str,
        trades: int,
        total_pnl: float,
        win_rate: float
    ) -> bool:
        """
        Send daily trading summary.
        
        Args:
            date: Summary date
            trades: Number of trades
            total_pnl: Total P&L
            win_rate: Win rate percentage
        """
        emoji = "📈" if total_pnl >= 0 else "📉"
        
        message = f"""
📅 *Daily Summary - {date}*

{emoji} *Results:*
• Total Trades: {trades}
• Total P&L: ${total_pnl:+,.2f}
• Win Rate: {win_rate:.1f}%
"""
        
        return await self.send_message(message)
    
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


def create_whatsapp_notifier(config: dict) -> Optional[WhatsAppNotifier]:
    """
    Create WhatsApp notifier from config.
    
    Args:
        config: Configuration dictionary with whatsapp settings
        
    Returns:
        WhatsAppNotifier instance or None if not configured
    """
    wa_config = config.get("notifications", {}).get("whatsapp", {})
    
    if not wa_config.get("enabled"):
        return None
    
    account_sid = wa_config.get("twilio_account_sid")
    auth_token = wa_config.get("twilio_auth_token")
    from_number = wa_config.get("from_number")
    to_numbers = wa_config.get("to_numbers", [])
    
    if not account_sid or not auth_token:
        logger.warning("WhatsApp enabled but missing Twilio credentials")
        return None
    
    if not from_number:
        logger.warning("WhatsApp enabled but missing from_number")
        return None
    
    if not to_numbers:
        logger.warning("WhatsApp enabled but no to_numbers configured")
        return None
    
    return WhatsAppNotifier(
        account_sid=account_sid,
        auth_token=auth_token,
        from_number=from_number,
        to_numbers=to_numbers
    )
