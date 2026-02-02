"""Notification services module."""

from src.notifications.telegram import TelegramNotifier, create_telegram_notifier
from src.notifications.discord import DiscordNotifier, create_discord_notifier
from src.notifications.email import EmailNotifier, create_email_notifier
from src.notifications.whatsapp import WhatsAppNotifier, create_whatsapp_notifier
from src.notifications.manager import (
    NotificationManager,
    create_notification_manager,
    get_notification_manager
)

__all__ = [
    'TelegramNotifier',
    'create_telegram_notifier',
    'DiscordNotifier',
    'create_discord_notifier',
    'EmailNotifier',
    'create_email_notifier',
    'WhatsAppNotifier',
    'create_whatsapp_notifier',
    'NotificationManager',
    'create_notification_manager',
    'get_notification_manager',
]
