"""
Process supervisor for auto-restart on crash.

Wraps the trading bot process and automatically restarts it if it crashes.
Includes exponential backoff to prevent restart loops.
"""

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional

from src.utils.logger import get_logger

logger = get_logger()


@dataclass
class RestartConfig:
    """Configuration for restart behavior."""
    max_restarts: int = 5  # Maximum restarts in window
    restart_window: int = 300  # Window in seconds (5 minutes)
    initial_delay: float = 1.0  # Initial delay before restart
    max_delay: float = 60.0  # Maximum delay between restarts
    backoff_multiplier: float = 2.0  # Exponential backoff multiplier


@dataclass
class ProcessState:
    """Tracks process state and restart history."""
    restart_count: int = 0
    last_restart: Optional[datetime] = None
    restart_times: List[datetime] = None
    current_delay: float = 1.0
    
    def __post_init__(self):
        if self.restart_times is None:
            self.restart_times = []


class ProcessSupervisor:
    """
    Supervises a process and automatically restarts on crash.
    
    Features:
    - Automatic restart on exit
    - Exponential backoff to prevent restart loops
    - Crash logging and notification
    - Graceful shutdown handling
    
    Usage:
        supervisor = ProcessSupervisor(
            command=["python", "-m", "src.api.server"],
            restart_config=RestartConfig(max_restarts=5)
        )
        supervisor.start()
    """
    
    def __init__(
        self,
        command: List[str],
        restart_config: Optional[RestartConfig] = None,
        working_dir: Optional[str] = None,
        on_crash: Optional[Callable[[int, str], None]] = None,
        on_restart: Optional[Callable[[int], None]] = None
    ):
        """
        Initialize supervisor.
        
        Args:
            command: Command to run as list (e.g., ["python", "-m", "src.api.server"])
            restart_config: Configuration for restart behavior
            working_dir: Working directory for the process
            on_crash: Callback when process crashes (exit_code, output)
            on_restart: Callback when process restarts (restart_count)
        """
        self.command = command
        self.config = restart_config or RestartConfig()
        self.working_dir = working_dir or os.getcwd()
        self.on_crash = on_crash
        self.on_restart = on_restart
        
        self._process: Optional[subprocess.Popen] = None
        self._state = ProcessState(current_delay=self.config.initial_delay)
        self._running = False
        self._shutdown_requested = False
        
        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)
    
    def _handle_signal(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self._shutdown_requested = True
        self.stop()
    
    def _should_restart(self) -> bool:
        """Check if we should restart based on config."""
        if self._shutdown_requested:
            return False
        
        now = datetime.now()
        
        # Clean old restart times outside window
        window_start = now.timestamp() - self.config.restart_window
        self._state.restart_times = [
            t for t in self._state.restart_times 
            if t.timestamp() > window_start
        ]
        
        # Check if we've exceeded max restarts in window
        if len(self._state.restart_times) >= self.config.max_restarts:
            logger.error(
                f"Max restarts ({self.config.max_restarts}) exceeded in "
                f"{self.config.restart_window}s window. Stopping."
            )
            return False
        
        return True
    
    def _wait_with_backoff(self) -> None:
        """Wait with exponential backoff before restart."""
        delay = self._state.current_delay
        logger.info(f"Waiting {delay:.1f}s before restart...")
        
        time.sleep(delay)
        
        # Increase delay for next restart
        self._state.current_delay = min(
            delay * self.config.backoff_multiplier,
            self.config.max_delay
        )
    
    def _reset_backoff(self) -> None:
        """Reset backoff after successful run."""
        self._state.current_delay = self.config.initial_delay
    
    def _start_process(self) -> subprocess.Popen:
        """Start the supervised process."""
        logger.info(f"Starting process: {' '.join(self.command)}")
        
        process = subprocess.Popen(
            self.command,
            cwd=self.working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        return process
    
    def _log_output(self, process: subprocess.Popen) -> str:
        """Log process output and capture last lines for crash report."""
        output_lines = []
        max_lines = 50  # Keep last 50 lines for crash report
        
        try:
            for line in process.stdout:
                line = line.rstrip()
                print(line)  # Forward to stdout
                output_lines.append(line)
                if len(output_lines) > max_lines:
                    output_lines.pop(0)
        except Exception as e:
            logger.warning(f"Error reading process output: {e}")
        
        return "\n".join(output_lines)
    
    def start(self) -> None:
        """
        Start supervising the process.
        
        This method blocks until shutdown is requested or max restarts exceeded.
        """
        self._running = True
        self._shutdown_requested = False
        
        logger.info("Supervisor starting...")
        
        while self._running:
            # Start the process
            self._process = self._start_process()
            start_time = datetime.now()
            
            # Monitor process output
            last_output = self._log_output(self._process)
            
            # Wait for process to exit
            exit_code = self._process.wait()
            
            # Check if this was a graceful shutdown
            if self._shutdown_requested:
                logger.info("Process stopped due to shutdown request")
                break
            
            # Process crashed or exited unexpectedly
            runtime = (datetime.now() - start_time).total_seconds()
            logger.warning(
                f"Process exited with code {exit_code} after {runtime:.1f}s"
            )
            
            # Record restart time
            self._state.restart_times.append(datetime.now())
            self._state.restart_count += 1
            
            # Call crash callback
            if self.on_crash:
                try:
                    self.on_crash(exit_code, last_output)
                except Exception as e:
                    logger.error(f"Error in crash callback: {e}")
            
            # Send crash notification
            self._send_crash_notification(exit_code, last_output)
            
            # If process ran for a while, reset backoff
            if runtime > self.config.restart_window:
                self._reset_backoff()
            
            # Check if we should restart
            if not self._should_restart():
                self._running = False
                break
            
            # Wait before restart
            self._wait_with_backoff()
            
            # Call restart callback
            if self.on_restart:
                try:
                    self.on_restart(self._state.restart_count)
                except Exception as e:
                    logger.error(f"Error in restart callback: {e}")
            
            logger.info(f"Restarting process (attempt {self._state.restart_count})...")
        
        logger.info("Supervisor stopped")
    
    def stop(self) -> None:
        """Stop the supervised process gracefully."""
        self._running = False
        self._shutdown_requested = True
        
        if self._process and self._process.poll() is None:
            logger.info("Sending SIGTERM to process...")
            self._process.terminate()
            
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Process didn't terminate, sending SIGKILL...")
                self._process.kill()
                self._process.wait()
    
    def _send_crash_notification(self, exit_code: int, output: str) -> None:
        """Send notification about crash."""
        try:
            from src.core.config import ConfigManager
            from src.notifications.manager import create_notification_manager
            
            config = ConfigManager()
            manager = create_notification_manager(config._config)
            
            if manager:
                import asyncio
                
                message = (
                    f"🚨 Trading Bot Crashed!\n\n"
                    f"Exit code: {exit_code}\n"
                    f"Restart count: {self._state.restart_count}\n"
                    f"Last output:\n{output[-500:]}"  # Last 500 chars
                )
                
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                loop.run_until_complete(
                    manager.send_error_alert("Process Crash", message)
                )
        except Exception as e:
            logger.warning(f"Could not send crash notification: {e}")
    
    @property
    def is_running(self) -> bool:
        """Check if supervisor is running."""
        return self._running
    
    @property
    def process_running(self) -> bool:
        """Check if supervised process is running."""
        return self._process is not None and self._process.poll() is None
    
    @property
    def restart_count(self) -> int:
        """Get total restart count."""
        return self._state.restart_count


def run_with_supervisor(
    command: Optional[List[str]] = None,
    max_restarts: int = 5,
    restart_window: int = 300
) -> None:
    """
    Convenience function to run a command with supervisor.
    
    Args:
        command: Command to run. Defaults to API server.
        max_restarts: Maximum restarts in window
        restart_window: Time window for restart counting (seconds)
    """
    if command is None:
        command = [sys.executable, "-m", "src.api.server"]
    
    config = RestartConfig(
        max_restarts=max_restarts,
        restart_window=restart_window
    )
    
    supervisor = ProcessSupervisor(command=command, restart_config=config)
    supervisor.start()


if __name__ == "__main__":
    # Run the API server with supervision
    run_with_supervisor()
