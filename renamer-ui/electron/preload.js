/**
 * electron/preload.js — Context bridge between renderer and main process.
 * Exposes a safe, minimal API to the renderer via window.electronAPI.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Native dialogs
  openFolder:     ()       => ipcRenderer.invoke('dialog:openFolder'),
  openModelFile:  ()       => ipcRenderer.invoke('dialog:openModelFile'),
  openUndoLog:    (folder) => ipcRenderer.invoke('dialog:openUndoLog', folder),

  // Window controls (custom title bar)
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close:    () => ipcRenderer.send('window:close'),
});
