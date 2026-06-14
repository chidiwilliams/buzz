/**
 * electron/splash-preload.js — secure bridge for the splash window.
 * Exposes a minimal API the splash page uses to receive startup progress.
 */

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('splashAPI', {
  // Receive {percent, message} startup-stage updates from the backend.
  onStatus: (cb) =>
    ipcRenderer.on('splash:status', (_evt, payload) => cb(payload)),
  // Fired once the backend is listening and the main window is about to show.
  onReady: (cb) =>
    ipcRenderer.on('splash:ready', () => cb()),
});
