#!/usr/bin/env python3
"""
Build script for creating standalone executables.

Usage:
    python build.py                 # Build for current platform
    python build.py --platform all  # Build for all platforms (requires CI)
    python build.py --gui           # Build GUI version only
    python build.py --cli           # Build CLI version only
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def get_platform_name():
    """Get current platform name."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    elif system == "windows":
        return "windows"
    else:
        return "linux"


def build_executable(entry_point: str, name: str, icon: str = None, 
                     console: bool = True, onefile: bool = True):
    """
    Build executable using PyInstaller.
    
    Args:
        entry_point: Main Python script
        name: Output executable name
        icon: Path to icon file (optional)
        console: Show console window
        onefile: Create single file executable
    """
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", name,
        "--clean",
        "--noconfirm"
    ]
    
    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")
    
    if not console:
        cmd.append("--windowed")
    
    if icon and Path(icon).exists():
        cmd.extend(["--icon", icon])
    
    # Add data files
    cmd.extend([
        "--add-data", f"config{os.pathsep}config",
        "--add-data", f"README.md{os.pathsep}."
    ])
    
    # Hidden imports for dynamic modules
    hidden_imports = [
        "ccxt",
        "pandas",
        "numpy",
        "plotly",
        "ta",
        "rich",
        "questionary",
        "customtkinter",
        "yaml",
        "loguru",
        "aiohttp"
    ]
    
    for module in hidden_imports:
        cmd.extend(["--hidden-import", module])
    
    # Add entry point
    cmd.append(entry_point)
    
    print(f"Building {name}...")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    
    if result.returncode != 0:
        print(f"Build failed with code {result.returncode}")
        sys.exit(1)
    
    print(f"Build complete: dist/{name}")


def clean_build():
    """Clean build artifacts."""
    dirs_to_clean = ["build", "dist", "__pycache__"]
    files_to_clean = ["*.spec"]
    
    for dir_name in dirs_to_clean:
        path = Path(dir_name)
        if path.exists():
            shutil.rmtree(path)
            print(f"Removed: {dir_name}")
    
    for pattern in files_to_clean:
        for file_path in Path(".").glob(pattern):
            file_path.unlink()
            print(f"Removed: {file_path}")


def create_launcher():
    """Create a launcher script that lets user choose CLI or GUI."""
    launcher_content = '''#!/usr/bin/env python3
"""Launcher script for Crypto Trading Bot."""

import sys

def main():
    print("\\n🚀 Crypto Trading Bot\\n")
    print("Select interface:")
    print("1. CLI (Command Line)")
    print("2. GUI (Graphical)")
    print("3. Exit\\n")
    
    choice = input("Enter choice (1-3): ").strip()
    
    if choice == "1":
        from src.main import main as cli_main
        cli_main()
    elif choice == "2":
        from src.gui.app import run_gui
        run_gui()
    elif choice == "3":
        print("Goodbye!")
        sys.exit(0)
    else:
        print("Invalid choice")
        main()

if __name__ == "__main__":
    main()
'''
    
    launcher_path = Path("launcher.py")
    launcher_path.write_text(launcher_content)
    print(f"Created: {launcher_path}")
    return str(launcher_path)


def main():
    parser = argparse.ArgumentParser(description="Build Crypto Trading Bot executables")
    parser.add_argument("--platform", choices=["windows", "macos", "linux", "all", "current"],
                       default="current", help="Target platform")
    parser.add_argument("--gui", action="store_true", help="Build GUI version only")
    parser.add_argument("--cli", action="store_true", help="Build CLI version only")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts")
    parser.add_argument("--onedir", action="store_true", help="Create directory instead of single file")
    
    args = parser.parse_args()
    
    if args.clean:
        clean_build()
        print("Clean complete")
        return
    
    current_platform = get_platform_name()
    print(f"Current platform: {current_platform}")
    
    if args.platform == "all":
        print("Note: Cross-platform building requires CI/CD or virtual machines")
        print(f"Building for current platform: {current_platform}")
    
    # Determine what to build
    build_cli = True
    build_gui = True
    
    if args.cli:
        build_gui = False
    if args.gui:
        build_cli = False
    
    onefile = not args.onedir
    
    # Build CLI version
    if build_cli:
        build_executable(
            entry_point="src/main.py",
            name="crypto-bot-cli",
            console=True,
            onefile=onefile
        )
    
    # Build GUI version
    if build_gui:
        build_executable(
            entry_point="src/gui/app.py",
            name="crypto-bot-gui",
            console=False,
            onefile=onefile
        )
    
    # Build combined launcher
    if build_cli and build_gui:
        launcher = create_launcher()
        build_executable(
            entry_point=launcher,
            name="crypto-bot",
            console=True,
            onefile=onefile
        )
        Path(launcher).unlink()  # Clean up launcher
    
    print("\n✅ Build complete!")
    print(f"Executables are in: {Path('dist').absolute()}")
    
    # Platform-specific notes
    if current_platform == "macos":
        print("\nNote for macOS: You may need to allow the app in Security & Privacy settings")
    elif current_platform == "windows":
        print("\nNote for Windows: You may need to allow the app through Windows Defender")


if __name__ == "__main__":
    main()
