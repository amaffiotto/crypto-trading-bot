/**
 * Crypto Trading Bot - Electron Main Process
 */

const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let pythonProcess;
const API_PORT = 8765;

// Determine if running in development
const isDev = process.argv.includes('--dev');

/**
 * Start the Python API server
 */
function startPythonServer() {
    const pythonPath = isDev ? 'python3' : path.join(process.resourcesPath, 'python', 'venv', 'bin', 'python');
    const scriptPath = isDev 
        ? path.join(__dirname, '..', 'src', 'api', 'server.py')
        : path.join(process.resourcesPath, 'python', 'src', 'api', 'server.py');
    
    console.log('Starting Python API server...');
    console.log('Python path:', pythonPath);
    console.log('Script path:', scriptPath);
    
    pythonProcess = spawn(pythonPath, ['-m', 'uvicorn', 'src.api.server:app', '--host', '127.0.0.1', '--port', String(API_PORT)], {
        cwd: isDev ? path.join(__dirname, '..') : path.join(process.resourcesPath, 'python'),
        stdio: ['pipe', 'pipe', 'pipe']
    });
    
    pythonProcess.stdout.on('data', (data) => {
        console.log(`Python: ${data}`);
    });
    
    pythonProcess.stderr.on('data', (data) => {
        console.error(`Python Error: ${data}`);
    });
    
    pythonProcess.on('close', (code) => {
        console.log(`Python process exited with code ${code}`);
    });
    
    pythonProcess.on('error', (err) => {
        console.error('Failed to start Python process:', err);
    });
}

/**
 * Create the main application window
 */
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        minWidth: 1000,
        minHeight: 700,
        title: 'Crypto Trading Bot',
        backgroundColor: '#0a0a14',
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        }
    });
    
    // Load the main HTML file
    mainWindow.loadFile(path.join(__dirname, 'index.html'));
    
    // Open DevTools in development
    if (isDev) {
        mainWindow.webContents.openDevTools();
    }
    
    // Handle external links
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: 'deny' };
    });
    
    mainWindow.on('closed', () => {
        mainWindow = null;
    });
}

// App lifecycle
app.whenReady().then(() => {
    startPythonServer();
    
    // Wait a bit for the server to start
    setTimeout(createWindow, 2000);
    
    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    // Kill Python process
    if (pythonProcess) {
        pythonProcess.kill();
    }
    
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('quit', () => {
    if (pythonProcess) {
        pythonProcess.kill();
    }
});

// IPC handlers
ipcMain.handle('get-api-url', () => {
    return `http://127.0.0.1:${API_PORT}`;
});

ipcMain.handle('open-external', (event, url) => {
    shell.openExternal(url);
});

ipcMain.handle('open-file', (event, filePath) => {
    shell.openPath(filePath);
});
