/**
 * electron/main.js — Electron main process for Buzz Renamer
 *
 * Responsibilities:
 *  1. Spawn the Python WebSocket backend (renamer_server.py or bundled exe)
 *  2. Read the PORT:<n> line from the backend's stdout
 *  3. Create the BrowserWindow and pass the port via query string
 *  4. Kill the backend when the window closes
 */

const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');

// Suppress harmless "Gpu Cache Creation failed" / "Unable to move the cache"
// warnings that appear on Windows when the shader cache folder is inaccessible.
app.commandLine.appendSwitch('disable-gpu-shader-disk-cache');
app.commandLine.appendSwitch('disable-background-networking');

const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

// ─── Dev vs Production detection ────────────────────────────────────────────
// isDevMode: true when running unpackaged (npm start) — uses venv python
// showDevTools: only true when --dev flag is explicitly passed
const isDevMode    = !app.isPackaged;
const showDevTools = process.argv.includes('--dev');

// ─── Resolve paths ───────────────────────────────────────────────────────────
function getPythonBackendArgs() {
  if (isDevMode) {
    // Development: use the venv python + module invocation from project root
    const projectRoot = path.resolve(__dirname, '../../');
    const venvPython = process.platform === 'win32'
      ? path.join(projectRoot, '.venv', 'Scripts', 'python.exe')
      : path.join(projectRoot, '.venv', 'bin', 'python');

    const pythonExe = fs.existsSync(venvPython) ? venvPython : 'python';
    return {
      exe: pythonExe,
      args: [path.join(projectRoot, 'renamer_launcher.py')],
      cwd: projectRoot,
    };
  } else {
    // Production: use the bundled renamer_backend.exe
    const backendDir = path.join(process.resourcesPath, 'renamer_backend');
    const backendExe = path.join(backendDir, 'renamer_backend.exe');
    return { exe: backendExe, args: [], cwd: backendDir };
  }
}

// ─── State ──────────────────────────────────────────────────────────────────
let mainWindow = null;
let backendProcess = null;
let backendPort = null;

// ─── Backend launcher ────────────────────────────────────────────────────────
function launchBackend() {
  return new Promise((resolve, reject) => {
    const { exe, args, cwd } = getPythonBackendArgs();

    console.log(`[main] Spawning backend: ${exe} ${args.join(' ')}`);
    console.log(`[main] CWD: ${cwd}`);

    backendProcess = spawn(exe, args, {
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });

    // Read PORT:<n> from stdout — resolve only once
    let stdoutBuf = '';
    let portResolved = false;
    const onStdout = (chunk) => {
      stdoutBuf += chunk.toString();
      if (portResolved) return;
      const match = stdoutBuf.match(/PORT:(\d+)/);
      if (match) {
        portResolved = true;
        backendPort = parseInt(match[1], 10);
        console.log(`[main] Backend ready on port ${backendPort}`);
        backendProcess.stdout.off('data', onStdout); // stop listening
        resolve(backendPort);
      }
    };
    backendProcess.stdout.on('data', onStdout);

    backendProcess.stderr.on('data', (chunk) => {
      // Forward backend stderr to terminal in dev mode
      if (isDevMode) process.stderr.write('[backend] ' + chunk);
    });

    backendProcess.on('error', (err) => {
      console.error('[main] Backend spawn error:', err);
      reject(err);
    });

    backendProcess.on('exit', (code, signal) => {
      console.log(`[main] Backend exited: code=${code} signal=${signal}`);
      backendProcess = null;
    });

    // Timeout if backend doesn't start in 120 s
    // (PyQt6 + torch imports can take 60–90 s on first run)
    setTimeout(() => reject(new Error('Backend startup timeout')), 120_000);
  });
}

// ─── Window creation ─────────────────────────────────────────────────────────
function createWindow(port) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    frame: false,          // custom title bar
    transparent: false,
    backgroundColor: '#0f1117',
    titleBarStyle: 'hidden',
    icon: path.join(__dirname, '..', 'build', 'icon.ico'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const rendererPath = path.join(__dirname, '..', 'renderer', 'index.html');
  mainWindow.loadFile(rendererPath, { query: { port: String(port) } });

  if (showDevTools) {
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  }

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ─── IPC handlers (native dialogs) ───────────────────────────────────────────
ipcMain.handle('dialog:openFolder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Select audio folder',
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('dialog:openModelFile', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    title: 'Select Whisper model (.bin)',
    filters: [
      { name: 'Whisper GGML models', extensions: ['bin'] },
      { name: 'All files', extensions: ['*'] },
    ],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle('dialog:openUndoLog', async (_, folder) => {
  const result = await dialog.showOpenDialog(mainWindow, {
    defaultPath: folder,
    properties: ['openFile'],
    title: 'Select undo log',
    filters: [{ name: 'Undo logs', extensions: ['json'] }],
  });
  return result.canceled ? null : result.filePaths[0];
});

// Window controls (custom title bar)
ipcMain.on('window:minimize', () => mainWindow?.minimize());
ipcMain.on('window:maximize', () => {
  if (mainWindow?.isMaximized()) mainWindow.unmaximize();
  else mainWindow?.maximize();
});
ipcMain.on('window:close', () => mainWindow?.close());

// ─── App lifecycle ────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  // Show a lightweight loading window immediately so the user
  // isn't staring at nothing while PyQt6/torch imports (can take ~60 s)
  const splash = new BrowserWindow({
    width: 380,
    height: 200,
    frame: false,
    alwaysOnTop: true,
    resizable: false,
    backgroundColor: '#0f1117',
    webPreferences: { nodeIntegration: true, contextIsolation: false },
  });
  splash.loadURL('data:text/html,<body style="margin:0;background:#0f1117;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:Inter,sans-serif;color:#e8eaf6"><svg width="40" height="40" viewBox="0 0 24 24" fill="none"><path d="M3 12 Q6 6 9 12 Q12 18 15 12 Q18 6 21 12" stroke="url(#g)" stroke-width="2.5" stroke-linecap="round"/><defs><linearGradient id="g" x1="3" y1="12" x2="21" y2="12" gradientUnits="userSpaceOnUse"><stop stop-color="#8b5cf6"/><stop offset="1" stop-color="#06b6d4"/></linearGradient></defs></svg><h2 style="margin:16px 0 8px;font-size:18px;font-weight:600">Buzz Renamer</h2><p style="color:#8892b0;font-size:13px;margin:0">Starting up — loading AI models…</p></body>');

  try {
    const port = await launchBackend();
    splash.close();
    createWindow(port);
  } catch (err) {
    splash.close();
    console.error('[main] Failed to start backend:', err);
    dialog.showErrorBox(
      'Backend failed to start',
      `Could not launch the Python backend.\n\n${err.message}\n\n` +
      (isDevMode
        ? 'Make sure the venv is activated and buzz package is installed.'
        : 'Try reinstalling Buzz Renamer.')
    );
    app.quit();
  }
});

app.on('window-all-closed', () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && backendPort) {
    createWindow(backendPort);
  }
});

app.on('before-quit', () => {
  if (backendProcess) {
    backendProcess.kill();
  }
});
