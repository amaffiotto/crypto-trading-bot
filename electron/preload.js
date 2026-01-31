/**
 * Crypto Trading Bot - Preload Script
 * 
 * Provides a secure bridge between the renderer process and Node.js
 */

const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods to the renderer process
contextBridge.exposeInMainWorld('electronAPI', {
    // Get the API server URL
    getApiUrl: () => ipcRenderer.invoke('get-api-url'),
    
    // Open external URLs in default browser
    openExternal: (url) => ipcRenderer.invoke('open-external', url),
    
    // Open a file with the default application
    openFile: (filePath) => ipcRenderer.invoke('open-file', filePath),
    
    // Platform info
    platform: process.platform
});
