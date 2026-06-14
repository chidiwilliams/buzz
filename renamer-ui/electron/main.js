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
// onStatus({percent, message}) is called for each STATUS:<pct>:<msg> line the
// backend prints during its (slow) import/startup, so the splash can show real
// progress. Resolves with the port once the backend prints PORT:<n>.
function launchBackend({ onStatus } = {}) {
  return new Promise((resolve, reject) => {
    const { exe, args, cwd } = getPythonBackendArgs();

    console.log(`[main] Spawning backend: ${exe} ${args.join(' ')}`);
    console.log(`[main] CWD: ${cwd}`);

    backendProcess = spawn(exe, args, {
      cwd,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });

    // Parse stdout line-by-line for STATUS:<pct>:<msg> (progress) and
    // PORT:<n> (ready). Resolve the port only once.
    let stdoutBuf = '';
    let consumed = 0;       // index up to which we've parsed whole lines
    let portResolved = false;
    const onStdout = (chunk) => {
      stdoutBuf += chunk.toString();

      // Emit a status update for each complete STATUS line.
      let nl;
      while ((nl = stdoutBuf.indexOf('\n', consumed)) !== -1) {
        const line = stdoutBuf.slice(consumed, nl).trim();
        consumed = nl + 1;
        if (onStatus && line.startsWith('STATUS:')) {
          const rest = line.slice('STATUS:'.length);
          const sep = rest.indexOf(':');
          const pct = parseInt(rest.slice(0, sep), 10);
          const message = rest.slice(sep + 1);
          onStatus({ percent: Number.isNaN(pct) ? undefined : pct, message });
        }
      }

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
  // Show a lightweight loading window immediately so the user isn't staring
  // at nothing while PyQt6/torch imports (can take ~60 s). It displays real
  // startup progress fed from the backend's STATUS lines.
  const splash = new BrowserWindow({
    width: 440,
    height: 300,
    frame: false,
    alwaysOnTop: true,
    resizable: false,
    transparent: false,
    backgroundColor: '#0f1117',
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'splash-preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  splash.loadFile(path.join(__dirname, '..', 'renderer', 'splash.html'));
  splash.once('ready-to-show', () => splash.show());

  // Buffer status updates that arrive before the splash page has loaded,
  // then flush them so no early stage is lost.
  let splashLoaded = false;
  const pending = [];
  const sendSplash = (channel, payload) => {
    if (!splash || splash.isDestroyed()) return;
    if (!splashLoaded) { pending.push([channel, payload]); return; }
    splash.webContents.send(channel, payload);
  };
  splash.webContents.once('did-finish-load', () => {
    splashLoaded = true;
    for (const [c, p] of pending) splash.webContents.send(c, p);
    pending.length = 0;
  });

  try {
    const port = await launchBackend({
      onStatus: (s) => sendSplash('splash:status', s),
    });
    // Backend is up — animate the bar to 100%, then swap to the main window.
    sendSplash('splash:ready');
    await new Promise((r) => setTimeout(r, 650));
    if (splash && !splash.isDestroyed()) splash.close();
    createWindow(port);
  } catch (err) {
    if (splash && !splash.isDestroyed()) splash.close();
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
