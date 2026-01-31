# Crypto Trading Bot - Electron GUI

Modern desktop application for the Crypto Trading Bot.

## Development

### Prerequisites

- Node.js 18+
- Python 3.10+ with dependencies installed

### Setup

```bash
# Install Node dependencies
cd electron
npm install

# Start Python API server (in another terminal)
cd ..
python3 -m uvicorn src.api.server:app --host 127.0.0.1 --port 8765

# Start Electron app in dev mode
npm run dev
```

### Build

```bash
# Build for current platform
npm run build

# Build for specific platform
npm run build:mac
npm run build:win
npm run build:linux
```

Built applications will be in the `dist/` folder.

## Architecture

- **Main Process** (`main.js`): Manages window and spawns Python backend
- **Preload** (`preload.js`): Secure bridge between Node and renderer
- **Renderer** (`index.html`, `scripts/`, `styles/`): UI layer
- **Python API** (`../src/api/server.py`): FastAPI backend for trading operations
