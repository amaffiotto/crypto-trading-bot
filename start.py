#!/usr/bin/env python3
"""
Crypto Trading Bot - One-Click Launcher

This script starts both the API server and the Electron GUI automatically.
Just run: python3 start.py
"""

import subprocess
import sys
import os
import time
import signal
from pathlib import Path

# Colors for terminal output
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RED = "\033[91m"
RESET = "\033[0m"

def print_banner():
    print(f"""
{BLUE}╔═══════════════════════════════════════════════════════════╗
║                                                               ║
║            CRYPTO TRADING BOT v1.0.0                         ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝{RESET}
""")

def check_dependencies():
    """Check if all dependencies are installed."""
    print(f"{YELLOW}Checking dependencies...{RESET}")
    
    # Check Python packages
    try:
        import fastapi
        import uvicorn
        print(f"  {GREEN}✓{RESET} FastAPI installed")
    except ImportError:
        print(f"  {RED}✗{RESET} FastAPI not installed. Run: pip install fastapi uvicorn")
        return False
    
    # Check Node.js
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  {GREEN}✓{RESET} Node.js {result.stdout.strip()}")
        else:
            raise Exception()
    except:
        print(f"  {RED}✗{RESET} Node.js not installed. Download from https://nodejs.org")
        return False
    
    # Check Electron dependencies
    electron_path = Path(__file__).parent / "electron"
    node_modules = electron_path / "node_modules"
    
    if not node_modules.exists():
        print(f"  {YELLOW}!{RESET} Electron dependencies not installed. Installing...")
        subprocess.run(["npm", "install"], cwd=electron_path)
        print(f"  {GREEN}✓{RESET} Electron dependencies installed")
    else:
        print(f"  {GREEN}✓{RESET} Electron dependencies ready")
    
    return True

def main():
    print_banner()
    
    # Check dependencies
    if not check_dependencies():
        print(f"\n{RED}Please install missing dependencies and try again.{RESET}")
        sys.exit(1)
    
    print(f"\n{GREEN}Starting Crypto Trading Bot...{RESET}\n")
    
    # Get paths
    root_path = Path(__file__).parent
    electron_path = root_path / "electron"
    
    # Start API server in background
    print(f"{BLUE}[1/2]{RESET} Starting API server on http://127.0.0.1:8765 ...")
    
    api_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.server:app", 
         "--host", "127.0.0.1", "--port", "8765", "--log-level", "warning"],
        cwd=root_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for API to start
    time.sleep(2)
    
    if api_process.poll() is not None:
        print(f"{RED}Failed to start API server!{RESET}")
        stderr = api_process.stderr.read().decode()
        print(stderr)
        sys.exit(1)
    
    print(f"  {GREEN}✓{RESET} API server running (PID: {api_process.pid})")
    
    # Start Electron
    print(f"{BLUE}[2/2]{RESET} Starting Electron GUI...")
    
    electron_process = subprocess.Popen(
        ["npm", "start"],
        cwd=electron_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    print(f"  {GREEN}✓{RESET} Electron GUI starting...")
    print(f"\n{GREEN}Bot is running! Close the window to stop.{RESET}\n")
    
    # Handle Ctrl+C
    def cleanup(signum=None, frame=None):
        print(f"\n{YELLOW}Shutting down...{RESET}")
        electron_process.terminate()
        api_process.terminate()
        print(f"{GREEN}Goodbye!{RESET}")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    # Wait for Electron to close
    try:
        electron_process.wait()
    except:
        pass
    
    # Cleanup
    cleanup()

if __name__ == "__main__":
    main()
