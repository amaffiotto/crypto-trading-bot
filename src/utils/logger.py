"""Logging configuration using loguru."""

import sys
from pathlib import Path
from loguru import logger

# Global logger instance
_logger_configured = False


def setup_logger(log_level: str = "INFO", log_file: bool = True) -> logger:
    """
    Setup and configure the logger.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_file: Whether to also log to file
        
    Returns:
        Configured logger instance
    """
    global _logger_configured
    
    if _logger_configured:
        return logger
    
    # Remove default handler
    logger.remove()
    
    # Console handler with colors
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True
    )
    
    # File handler
    if log_file:
        log_dir = Path(__file__).parent.parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        
        logger.add(
            log_dir / "bot_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="1 day",
            retention="30 days",
            compression="zip"
        )
    
    _logger_configured = True
    return logger


def get_logger():
    """Get the configured logger instance."""
    global _logger_configured
    if not _logger_configured:
        setup_logger()
    return logger
