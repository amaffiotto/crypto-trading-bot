#!/usr/bin/env python3
"""
Crypto Trading Bot - Main Entry Point

This is the main entry point for the crypto trading bot.
It provides CLI interface and API server for the Electron GUI.
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import ConfigManager
from src.utils.logger import setup_logger


def run_cli():
    """Run the CLI interface."""
    from src.cli.menu import CLIMenu
    
    config_manager = ConfigManager()
    cli = CLIMenu(config_manager)
    cli.run()


def run_api_server(host: str = "127.0.0.1", port: int = 8765):
    """Run the API server for Electron GUI."""
    from src.api.server import run_server
    run_server(host=host, port=port)


def main():
    """Main entry point for the application."""
    parser = argparse.ArgumentParser(
        description="Crypto Trading Bot - Backtest and trade cryptocurrencies"
    )
    parser.add_argument(
        "--api", 
        action="store_true",
        help="Start API server for Electron GUI"
    )
    parser.add_argument(
        "--cli",
        action="store_true", 
        help="Launch CLI interface (default)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="API server port (default: 8765)"
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version="Crypto Trading Bot v1.0.0"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logger()
    logger.info("Starting Crypto Trading Bot v1.0.0")
    
    try:
        if args.api:
            logger.info(f"Starting API server on port {args.port}")
            run_api_server(port=args.port)
        else:
            # Default to CLI, or ask if no args provided
            if not args.cli and not args.api:
                print("\nCrypto Trading Bot v1.0.0\n")
                print("Select mode:")
                print("  1. CLI (Command Line Interface)")
                print("  2. API (Start API server for Electron GUI)")
                print()
                
                choice = input("Enter choice (1 or 2): ").strip()
                
                if choice == "2":
                    logger.info("Starting API server")
                    run_api_server(port=args.port)
                else:
                    logger.info("Launching CLI interface")
                    run_cli()
            else:
                logger.info("Launching CLI interface")
                run_cli()
                
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        print("\n\nGoodbye!")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
