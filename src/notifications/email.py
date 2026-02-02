"""Email notification service via SMTP."""

import asyncio
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import List, Optional

from src.utils.logger import get_logger

logger = get_logger()


class EmailNotifier:
    """
    Sends notifications via email using SMTP.
    
    Supports Gmail, SendGrid, AWS SES, and other SMTP providers.
    
    For Gmail:
    1. Enable 2FA on your Google account
    2. Create an App Password at https://myaccount.google.com/apppasswords
    3. Use the app password as the password in config
    """
    
    def __init__(
        self,
        smtp_server: str,
        smtp_port: int,
        username: str,
        password: str,
        from_address: str,
        to_addresses: List[str],
        use_tls: bool = True
    ):
        """
        Initialize Email notifier.
        
        Args:
            smtp_server: SMTP server hostname (e.g., smtp.gmail.com)
            smtp_port: SMTP port (587 for TLS, 465 for SSL)
            username: SMTP username (usually email address)
            password: SMTP password or app password
            from_address: Sender email address
            to_addresses: List of recipient email addresses
            use_tls: Whether to use TLS (default True)
        """
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_address = from_address
        self.to_addresses = to_addresses
        self.use_tls = use_tls
    
    def _create_html_template(self, title: str, body: str, footer: str = "") -> str:
        """Create HTML email template."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px 8px 0 0;
            text-align: center;
        }}
        .content {{
            background: #f8f9fa;
            padding: 20px;
            border: 1px solid #e9ecef;
        }}
        .footer {{
            background: #343a40;
            color: #868e96;
            padding: 15px;
            border-radius: 0 0 8px 8px;
            font-size: 12px;
            text-align: center;
        }}
        .metric {{
            display: inline-block;
            background: white;
            padding: 10px 15px;
            margin: 5px;
            border-radius: 4px;
            border: 1px solid #dee2e6;
        }}
        .metric-value {{
            font-size: 18px;
            font-weight: bold;
            color: #495057;
        }}
        .metric-label {{
            font-size: 12px;
            color: #868e96;
        }}
        .positive {{ color: #28a745; }}
        .negative {{ color: #dc3545; }}
    </style>
</head>
<body>
    <div class="header">
        <h2>{title}</h2>
    </div>
    <div class="content">
        {body}
    </div>
    <div class="footer">
        {footer if footer else "Crypto Trading Bot - Automated Notification"}
    </div>
</body>
</html>
"""
    
    def send_email(
        self,
        subject: str,
        body_html: str,
        body_text: Optional[str] = None
    ) -> bool:
        """
        Send an email.
        
        Args:
            subject: Email subject
            body_html: HTML body content
            body_text: Plain text body (fallback)
            
        Returns:
            True if sent successfully
        """
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.from_address
            msg["To"] = ", ".join(self.to_addresses)
            
            # Add plain text version
            if body_text:
                msg.attach(MIMEText(body_text, "plain"))
            
            # Add HTML version
            msg.attach(MIMEText(body_html, "html"))
            
            # Connect and send
            context = ssl.create_default_context()
            
            if self.smtp_port == 465:
                # SSL connection
                with smtplib.SMTP_SSL(self.smtp_server, self.smtp_port, context=context) as server:
                    server.login(self.username, self.password)
                    server.sendmail(self.from_address, self.to_addresses, msg.as_string())
            else:
                # TLS connection
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    if self.use_tls:
                        server.starttls(context=context)
                    server.login(self.username, self.password)
                    server.sendmail(self.from_address, self.to_addresses, msg.as_string())
            
            logger.debug("Email sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
    
    async def send_message(self, text: str, subject: Optional[str] = None) -> bool:
        """
        Send a simple text message (async wrapper).
        
        Args:
            text: Message text
            subject: Email subject (defaults to "Trading Bot Alert")
            
        Returns:
            True if sent successfully
        """
        subject = subject or "Trading Bot Alert"
        html = self._create_html_template("Alert", f"<p>{text}</p>")
        
        # Run in thread to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.send_email(subject, html, text)
        )
    
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
        action_upper = action.upper()
        is_buy = action_upper == "BUY"
        color_class = "positive" if is_buy else "negative"
        
        body = f"""
        <h3 class="{color_class}">{'🟢' if is_buy else '🔴'} {action_upper} Order Executed</h3>
        <div style="margin: 20px 0;">
            <div class="metric">
                <div class="metric-value">{symbol}</div>
                <div class="metric-label">Symbol</div>
            </div>
            <div class="metric">
                <div class="metric-value">${price:,.2f}</div>
                <div class="metric-label">Price</div>
            </div>
            <div class="metric">
                <div class="metric-value">{quantity:.6f}</div>
                <div class="metric-label">Quantity</div>
            </div>
            <div class="metric">
                <div class="metric-value">${price * quantity:,.2f}</div>
                <div class="metric-label">Value</div>
            </div>
        </div>
        """
        
        if pnl is not None:
            pnl_class = "positive" if pnl >= 0 else "negative"
            body += f"""
            <div class="metric">
                <div class="metric-value {pnl_class}">${pnl:+,.2f}</div>
                <div class="metric-label">P&L</div>
            </div>
            """
        
        html = self._create_html_template(f"{action_upper} - {symbol}", body)
        subject = f"Trade Alert: {action_upper} {symbol}"
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.send_email(subject, html)
        )
    
    async def send_error_alert(self, error_type: str, message: str) -> bool:
        """
        Send error alert.
        
        Args:
            error_type: Type of error
            message: Error message
        """
        body = f"""
        <h3 class="negative">🚨 Error Detected</h3>
        <div style="margin: 20px 0;">
            <p><strong>Type:</strong> {error_type}</p>
            <p><strong>Message:</strong></p>
            <pre style="background: #f1f3f4; padding: 15px; border-radius: 4px; overflow-x: auto;">{message}</pre>
        </div>
        <p style="color: #868e96; font-size: 14px;">
            Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
        </p>
        """
        
        html = self._create_html_template("Error Alert", body)
        subject = f"[ERROR] {error_type}"
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.send_email(subject, html)
        )
    
    async def send_daily_summary(
        self,
        date: str,
        trades: int,
        total_pnl: float,
        win_rate: float,
        total_volume: float = 0
    ) -> bool:
        """
        Send daily trading summary.
        
        Args:
            date: Summary date
            trades: Number of trades
            total_pnl: Total P&L
            win_rate: Win rate percentage
            total_volume: Total trading volume
        """
        pnl_class = "positive" if total_pnl >= 0 else "negative"
        
        body = f"""
        <h3>📊 Daily Summary - {date}</h3>
        <div style="margin: 20px 0;">
            <div class="metric">
                <div class="metric-value">{trades}</div>
                <div class="metric-label">Total Trades</div>
            </div>
            <div class="metric">
                <div class="metric-value {pnl_class}">${total_pnl:+,.2f}</div>
                <div class="metric-label">Total P&L</div>
            </div>
            <div class="metric">
                <div class="metric-value">{win_rate:.1f}%</div>
                <div class="metric-label">Win Rate</div>
            </div>
            <div class="metric">
                <div class="metric-value">${total_volume:,.2f}</div>
                <div class="metric-label">Volume</div>
            </div>
        </div>
        """
        
        html = self._create_html_template(f"Daily Summary - {date}", body)
        subject = f"Trading Summary: {date} | P&L: ${total_pnl:+,.2f}"
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.send_email(subject, html)
        )
    
    def send_sync(self, text: str, subject: Optional[str] = None) -> bool:
        """
        Synchronous wrapper for sending messages.
        
        Args:
            text: Message text
            subject: Email subject
            
        Returns:
            True if sent successfully
        """
        subject = subject or "Trading Bot Alert"
        html = self._create_html_template("Alert", f"<p>{text}</p>")
        return self.send_email(subject, html, text)


def create_email_notifier(config: dict) -> Optional[EmailNotifier]:
    """
    Create Email notifier from config.
    
    Args:
        config: Configuration dictionary with email settings
        
    Returns:
        EmailNotifier instance or None if not configured
    """
    email_config = config.get("notifications", {}).get("email", {})
    
    if not email_config.get("enabled"):
        return None
    
    required_fields = ["smtp_server", "smtp_port", "username", "password", "from_address", "to_addresses"]
    
    for field in required_fields:
        if not email_config.get(field):
            logger.warning(f"Email enabled but missing {field}")
            return None
    
    return EmailNotifier(
        smtp_server=email_config["smtp_server"],
        smtp_port=email_config["smtp_port"],
        username=email_config["username"],
        password=email_config["password"],
        from_address=email_config["from_address"],
        to_addresses=email_config["to_addresses"],
        use_tls=email_config.get("use_tls", True)
    )
