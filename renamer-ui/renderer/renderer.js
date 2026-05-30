/**
 * renderer/renderer.js — Buzz Renamer frontend logic
 *
 * Connects to the Python WebSocket backend, wires up all UI interactions,
 * and streams rename plans into the table as they arrive.
 */

'use strict';

// ─── Read WebSocket port from URL query string ────────────────────────────────
const params   = new URLSearchParams(window.location.search);
const WS_PORT  = params.get('port');

// ─── State ────────────────────────────────────────────────────────────────────
let ws            = null;
let plans         = [];   // Array of plan objects from the server
let isRunning     = false;

// ─── DOM references ───────────────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const folderInput       = $('folder-input');
const modelTypeEl       = $('model-type');
const modelSizeEl       = $('model-size');
const modelPathInput    = $('model-path-input');
const languageEl        = $('language');
const trimSeconds       = $('trim-seconds');
const firstWords        = $('first-words');
const maxLength         = $('max-length');
const keepPrefix        = $('keep-prefix');
const collisionStrategy = $('collision-strategy');
const initialPrompt     = $('initial-prompt');

const btnBrowseFolder = $('btn-browse-folder');
const btnBrowseModel  = $('btn-browse-model');
const btnPreview      = $('btn-preview');
const btnCancel       = $('btn-cancel');
const btnApply        = $('btn-apply');
const btnUndo         = $('btn-undo');

const statusDot       = $('status-dot');
const statusText      = $('status-text');
const progressWrapper = $('progress-wrapper');
const progressFill    = $('progress-fill');
const progressLabel   = $('progress-label');

const emptyState      = $('empty-state');
const fileTable       = $('file-table');
const tableBody       = $('table-body');
const logOutput       = $('log-output');
const logPane         = $('log-pane');

const sectionModelSize = $('section-model-size');
const sectionModelPath = $('section-model-path');

// ─── Toast container ─────────────────────────────────────────────────────────
const toastContainer = document.createElement('div');
toastContainer.className = 'toast-container';
document.body.appendChild(toastContainer);

// ─── Utilities ────────────────────────────────────────────────────────────────
function showToast(message, type = 'info', durationMs = 4000) {
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toastContainer.appendChild(toast);
  setTimeout(() => toast.remove(), durationMs);
}

function setStatus(label, dotClass) {
  statusText.textContent = label;
  statusDot.className = `status-dot ${dotClass}`;
}

function formatTime(seconds) {
  return seconds < 10 ? `${seconds.toFixed(1)}s` : `${Math.round(seconds)}s`;
}

function now() {
  return new Date().toLocaleTimeString('en-US', { hour12: false });
}

// ─── Log pane ─────────────────────────────────────────────────────────────────
function appendLog(message, level = 'info') {
  const line = document.createElement('span');
  line.className = 'log-line';
  line.innerHTML =
    `<span class="log-ts">[${now()}]</span>` +
    `<span class="log-${level}">${escHtml(message)}</span>`;
  logOutput.appendChild(line);
  logOutput.scrollTop = logOutput.scrollHeight;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

$('btn-clear-log').addEventListener('click', () => { logOutput.innerHTML = ''; });

// ─── Title bar ────────────────────────────────────────────────────────────────
$('btn-minimize').addEventListener('click', () => window.electronAPI.minimize());
$('btn-maximize').addEventListener('click', () => window.electronAPI.maximize());
$('btn-close'   ).addEventListener('click', () => window.electronAPI.close());

// ─── Settings panel ──────────────────────────────────────────────────────────
const settingsOverlay = $('settings-overlay');
const settingShowLog  = $('setting-show-log');
const settingReduceGpu= $('setting-reduce-gpu');
const settingForceCpu = $('setting-force-cpu');

// Load settings from localStorage
function loadSettings() {
  const showLog   = localStorage.getItem('showLog')   !== 'false'; // default true
  const reduceGpu = localStorage.getItem('reduceGpu') === 'true';  // default false
  const forceCpu  = localStorage.getItem('forceCpu')  === 'true';  // default false

  settingShowLog.checked   = showLog;
  settingReduceGpu.checked = reduceGpu;
  settingForceCpu.checked  = forceCpu;

  applyLogVisibility(showLog);
}

function applyLogVisibility(visible) {
  if (visible) {
    logPane.classList.remove('log-hidden');
    logPane.style.height = '';
  } else {
    logPane.classList.add('log-hidden');
  }
}

settingShowLog.addEventListener('change', () => {
  const v = settingShowLog.checked;
  localStorage.setItem('showLog', v);
  applyLogVisibility(v);
});

settingReduceGpu.addEventListener('change', () => {
  localStorage.setItem('reduceGpu', settingReduceGpu.checked);
});
settingForceCpu.addEventListener('change', () => {
  localStorage.setItem('forceCpu', settingForceCpu.checked);
});

$('btn-settings').addEventListener('click', () => {
  settingsOverlay.style.display = 'block';
});
$('btn-close-settings').addEventListener('click', () => {
  settingsOverlay.style.display = 'none';
});
settingsOverlay.addEventListener('click', e => {
  if (e.target === settingsOverlay) settingsOverlay.style.display = 'none';
});
// Prevent clicks inside the panel from closing it
$('settings-panel').addEventListener('click', e => e.stopPropagation());

// ─── Initial prompt collapsible ──────────────────────────────────────────────
const togglePrompt = $('toggle-prompt');
const promptBody   = $('prompt-body');

togglePrompt.addEventListener('click', () => {
  const expanded = togglePrompt.getAttribute('aria-expanded') === 'true';
  togglePrompt.setAttribute('aria-expanded', !expanded);
  promptBody.style.display = expanded ? 'none' : 'block';
});

// ─── Model type ↔ UI sections ────────────────────────────────────────────────
const WHISPER_CPP_VALUE = 'Whisper.cpp';

function updateModelSections() {
  const type = modelTypeEl.value;
  const needsPath  = type === WHISPER_CPP_VALUE;
  const hasSizes   = ['Whisper', 'Whisper.cpp', 'Faster Whisper'].includes(type);
  sectionModelPath.style.display = needsPath  ? '' : 'none';
  sectionModelSize.style.display = hasSizes   ? '' : 'none';
}
modelTypeEl.addEventListener('change', updateModelSections);

// ─── Native dialog bindings ───────────────────────────────────────────────────
btnBrowseFolder.addEventListener('click', async () => {
  const p = await window.electronAPI.openFolder();
  if (p) {
    folderInput.value = p;
    send({ cmd: 'list_files', directory: p });
  }
});

btnBrowseModel.addEventListener('click', async () => {
  const p = await window.electronAPI.openModelFile();
  if (p) modelPathInput.value = p;
});

// ─── Build config payload ─────────────────────────────────────────────────────
function buildConfig() {
  return {
    model_type:           modelTypeEl.value,
    model_size:           modelSizeEl.value,
    model_path:           modelPathInput.value.trim(),
    language:             languageEl.value || null,
    trim_seconds:         parseFloat(trimSeconds.value) || 5.0,
    first_words:          parseInt(firstWords.value, 10) || 6,
    max_filename_len:     parseInt(maxLength.value, 10) || 50,
    keep_numeric_prefix:  keepPrefix.checked,
    collision_strategy:   collisionStrategy.value,
    initial_prompt:       initialPrompt.value.trim(),
  };
}

// ─── Button state ─────────────────────────────────────────────────────────────
function updateButtons() {
  const anyChanges = plans.some(p => p.will_change);
  btnPreview.disabled = isRunning;
  btnCancel.disabled  = !isRunning;
  btnApply.disabled   = isRunning || !anyChanges;
  btnUndo.disabled    = isRunning;
}

// ─── Table rendering ─────────────────────────────────────────────────────────
const STATUS_BADGE = {
  ready:   '<span class="status-badge badge-ready">✓ Ready</span>',
  error:   '<span class="status-badge badge-error">✗ Error</span>',
  skipped: '<span class="status-badge badge-skipped">— Skipped</span>',
  applied: '<span class="status-badge badge-applied">★ Applied</span>',
  pending: '<span class="status-badge badge-pending">· Pending</span>',
};

function renderRow(plan, animate = false, flash = false) {
  const isNoChange = plan.status === 'ready' && !plan.will_change;
  const isPending  = plan.status === 'pending';

  const proposedDisplay = isPending
    ? '—'
    : (plan.proposed_path
        ? plan.proposed_path.split(/[/\\]/).pop()
        : (isNoChange ? '(already correct)' : ''));

  const tr = document.createElement('tr');
  tr.dataset.originalPath = plan.original_path;

  // Row CSS class for status tint
  tr.classList.add(`status-${plan.status}`);
  if (animate) tr.classList.add('row-new');
  if (flash)   tr.classList.add('row-flash-ready');

  const originalName = plan.original_path.split(/[/\\]/).pop();
  const snippet = plan.transcript
    ? (plan.transcript.length > 100
        ? plan.transcript.slice(0, 100) + '…'
        : plan.transcript)
    : (plan.error || '');

  // Arrow cell: only show → when there's a change
  const arrowHtml = (!isPending && plan.will_change) ? '→' : '';

  // Proposed cell input
  const inputDisabled = isPending || plan.status !== 'ready' || isNoChange;
  const inputClass    = isPending ? 'pending-placeholder' : '';

  tr.innerHTML = `
    <td>${STATUS_BADGE[plan.status] || plan.status}</td>
    <td><div class="original-name" title="${escHtml(plan.original_path)}">${escHtml(originalName)}</div></td>
    <td class="col-arrow">${arrowHtml}</td>
    <td class="proposed-cell">
      <input
        type="text"
        class="${inputClass}"
        value="${escHtml(proposedDisplay)}"
        ${inputDisabled ? 'disabled' : ''}
        data-original-path="${escHtml(plan.original_path)}"
        title="${inputDisabled ? '' : 'Double-click to edit'}"
      />
    </td>
    <td><div class="transcript-snippet" title="${escHtml(plan.transcript)}">${escHtml(snippet)}</div></td>
    <td class="time-cell">${plan.duration_sec > 0 ? formatTime(plan.duration_sec) : '—'}</td>
  `;

  // Wire up inline edit
  const input = tr.querySelector('input[type="text"]');
  if (input && !input.disabled) {
    input.addEventListener('change', (e) => {
      const newVal = e.target.value.trim();
      if (!newVal) return;
      const stem = newVal.includes('.') ? newVal.replace(/\.[^.]+$/, '') : newVal;
      const ext  = plan.original_path.includes('.')
        ? '.' + plan.original_path.split('.').pop()
        : '';
      plan.proposed_name = stem;
      plan.proposed_path = plan.original_path.replace(/[^/\\]+$/, '') + stem + ext;
      plan.will_change   = plan.proposed_path !== plan.original_path;
      e.target.value     = stem + ext;
      // update arrow cell
      const arrowCell = tr.querySelector('.col-arrow');
      if (arrowCell) arrowCell.textContent = plan.will_change ? '→' : '';
      updateButtons();
    });
  }

  // Right-click context menu
  tr.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    showContextMenu(e.clientX, e.clientY, plan, tr);
  });

  return tr;
}

function rebuildTable() {
  tableBody.innerHTML = '';
  if (plans.length === 0) {
    fileTable.style.display = 'none';
    emptyState.style.display = 'flex';
    return;
  }
  emptyState.style.display = 'none';
  fileTable.style.display  = 'table';
  plans.forEach(p => tableBody.appendChild(renderRow(p)));
}

function appendPlanRow(plan) {
  if (plans.length === 0) {
    emptyState.style.display = 'none';
    fileTable.style.display  = 'table';
  }
  const tr = renderRow(plan, true);
  tableBody.appendChild(tr);
  tr.addEventListener('animationend', () => tr.classList.remove('row-new'), { once: true });
}

// Update an existing row in-place (pending→ready transition with flash)
function updateExistingRow(plan) {
  const existingRow = tableBody.querySelector(
    `tr[data-original-path="${CSS.escape(plan.original_path)}"]`
  );
  const wasFlash = plan.status === 'ready';
  const newTr = renderRow(plan, false, wasFlash);
  if (existingRow) {
    existingRow.replaceWith(newTr);
    if (wasFlash) {
      newTr.addEventListener('animationend', () => newTr.classList.remove('row-flash-ready'), { once: true });
    }
  } else {
    tableBody.appendChild(newTr);
  }
}

// ─── Context menu ─────────────────────────────────────────────────────────────
let activeCtxMenu = null;

function showContextMenu(x, y, plan, tr) {
  if (activeCtxMenu) activeCtxMenu.remove();

  const menu = document.createElement('div');
  menu.className = 'ctx-menu';
  menu.style.left = `${x}px`;
  menu.style.top  = `${y}px`;

  const items = [
    { label: '✏️  Edit proposed name', action: () => {
        const input = tr.querySelector('input[type="text"]');
        if (input) { input.disabled = false; input.classList.remove('pending-placeholder'); input.focus(); input.select(); }
      }
    },
    { label: '↩️  Reset to AI suggestion', action: () => {
        if (plan.transcript) {
          const words = plan.transcript.split(/\s+/).slice(0, parseInt(firstWords.value, 10)).join(' ');
          const stem  = words.toLowerCase().replace(/[^\w\s-]/g, '').replace(/\s+/g, '_').replace(/_+/g, '_').slice(0, parseInt(maxLength.value, 10)).replace(/^_+|_+$/, '');
          if (stem) {
            const ext = plan.original_path.includes('.') ? '.' + plan.original_path.split('.').pop() : '';
            plan.proposed_name = stem;
            plan.proposed_path = plan.original_path.replace(/[^/\\]+$/, '') + stem + ext;
            plan.will_change   = true;
            plan.status        = 'ready';
            const newTr = renderRow(plan);
            tr.replaceWith(newTr);
            updateButtons();
          }
        }
      }
    },
    { label: '🚫  Skip this file', action: () => {
        plan.status    = 'skipped';
        plan.error     = 'user skipped';
        plan.will_change = false;
        const newTr = renderRow(plan);
        tr.replaceWith(newTr);
        updateButtons();
      }, className: 'danger'
    },
  ];

  items.forEach(item => {
    const div = document.createElement('div');
    div.className = `ctx-item${item.className ? ' ' + item.className : ''}`;
    div.textContent = item.label;
    div.addEventListener('click', () => { item.action(); menu.remove(); activeCtxMenu = null; });
    menu.appendChild(div);
  });

  document.body.appendChild(menu);
  activeCtxMenu = menu;

  // Auto-close
  const closer = (e) => {
    if (!menu.contains(e.target)) { menu.remove(); activeCtxMenu = null; document.removeEventListener('click', closer, true); }
  };
  setTimeout(() => document.addEventListener('click', closer, true), 0);
}

// ─── WebSocket connection & message handling ───────────────────────────────────
function connect() {
  if (!WS_PORT) {
    setStatus('No port specified', 'error');
    appendLog('ERROR: No WebSocket port found in URL. Backend may have failed to start.', 'error');
    return;
  }

  setStatus('Connecting…', '');
  ws = new WebSocket(`ws://127.0.0.1:${WS_PORT}`);

  ws.addEventListener('open', () => {
    setStatus('Connected', 'connected');
    appendLog('Connected to Buzz backend.', 'info');
    send({ cmd: 'list_models' });
    send({ cmd: 'list_languages' });
  });

  ws.addEventListener('close', () => {
    setStatus('Disconnected', 'error');
    appendLog('Connection closed.', 'warn');
    ws = null;
    setTimeout(connect, 2000);
  });

  ws.addEventListener('error', () => {
    setStatus('Connection error', 'error');
  });

  ws.addEventListener('message', (e) => {
    let msg;
    try { msg = JSON.parse(e.data); }
    catch { return; }
    handleServerEvent(msg);
  });
}

function send(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

// ─── Language dropdown (populated dynamically) ────────────────────────────────
function populateLanguages(languages) {
  // Keep the "Detect automatically" option at the top
  languageEl.innerHTML = '<option value="">Detect automatically</option>';
  languages.forEach(lang => {
    const opt = document.createElement('option');
    opt.value       = lang.code;
    opt.textContent = `${lang.name} (${lang.code})`;
    if (lang.code === 'en') opt.selected = true;
    languageEl.appendChild(opt);
  });
}

// ─── Model dropdowns ──────────────────────────────────────────────────────────
let _modelsData = [];

function populateModelDropdowns(models) {
  _modelsData = models;
  modelTypeEl.innerHTML = '';
  models.forEach(m => {
    const opt = document.createElement('option');
    opt.value       = m.type;
    opt.textContent = m.type;
    modelTypeEl.appendChild(opt);
  });
  // Default to Whisper.cpp if available
  const cppOpt = [...modelTypeEl.options].find(o => o.value === WHISPER_CPP_VALUE);
  if (cppOpt) modelTypeEl.value = WHISPER_CPP_VALUE;

  updateModelSections();
  updateSizeDropdown();
}

function updateSizeDropdown() {
  const type  = modelTypeEl.value;
  const model = _modelsData.find(m => m.type === type);
  modelSizeEl.innerHTML = '';
  if (model && model.sizes.length > 0) {
    model.sizes.forEach(s => {
      const opt = document.createElement('option');
      opt.value       = s.size;
      opt.textContent = s.downloaded ? `${s.label} ✓` : s.label;
      modelSizeEl.appendChild(opt);
    });
    // Default to base
    const baseOpt = [...modelSizeEl.options].find(o => o.value === 'base');
    if (baseOpt) modelSizeEl.value = 'base';
  }
}

modelTypeEl.addEventListener('change', () => {
  updateModelSections();
  updateSizeDropdown();
});

// ─── Preview ─────────────────────────────────────────────────────────────────
btnPreview.addEventListener('click', () => {
  const folder = folderInput.value.trim();
  if (!folder) {
    showToast('Please select an audio folder first.', 'error');
    return;
  }

  // Keep the existing file listing but reset statuses to pending
  isRunning = true;
  progressFill.style.width = '0%';
  progressWrapper.style.display = 'flex';
  progressLabel.textContent = '0 / ?';
  setStatus('Starting…', 'running');

  // If we already have a file listing, reset each row to pending
  if (plans.length > 0) {
    plans.forEach(p => {
      p.status        = 'pending';
      p.transcript    = '';
      p.proposed_name = null;
      p.proposed_path = null;
      p.will_change   = false;
      p.duration_sec  = 0;
      p.error         = '';
    });
    rebuildTable();
  } else {
    tableBody.innerHTML = '';
    fileTable.style.display = 'none';
    emptyState.style.display = 'flex';
  }

  updateButtons();

  send({
    cmd: 'start_preview',
    directory: folder,
    config: buildConfig(),
  });
});

// ─── Cancel ───────────────────────────────────────────────────────────────────
btnCancel.addEventListener('click', () => {
  if (isRunning) send({ cmd: 'cancel' });
});

// ─── Apply ────────────────────────────────────────────────────────────────────
btnApply.addEventListener('click', () => {
  const toApply = plans.filter(p => p.status === 'ready' && p.will_change);
  if (toApply.length === 0) {
    showToast('No changes to apply.', 'info');
    return;
  }

  const confirmed = confirm(
    `Apply ${toApply.length} rename(s)?\n` +
    `An undo log will be saved in the source folder.`
  );
  if (!confirmed) return;

  isRunning = true;
  updateButtons();
  setStatus('Applying renames…', 'running');

  send({
    cmd: 'apply_renames',
    folder: folderInput.value.trim(),
    plans: plans,
  });
});

// ─── Undo ─────────────────────────────────────────────────────────────────────
btnUndo.addEventListener('click', () => {
  const folder = folderInput.value.trim();
  if (!folder) {
    showToast('Please select the folder containing the undo log.', 'error');
    return;
  }
  const confirmed = confirm('Reverse the last batch of renames in this folder?');
  if (!confirmed) return;

  send({ cmd: 'undo', folder });
});

// ─── Download Models modal ────────────────────────────────────────────────────
const modalModels       = $('modal-models');
const btnShowModels     = $('btn-show-models');
const btnCloseModels    = $('btn-close-models');
const btnStartDownload  = $('btn-start-download');
const btnCancelDownload = $('btn-cancel-download');
const dlModelType       = $('dl-model-type');
const dlModelSize       = $('dl-model-size');
const dlProgressArea    = $('dl-progress-area');
const dlProgressFill    = $('dl-progress-fill');
const dlProgressLabel   = $('dl-progress-label');
const dlBytesLabel      = $('dl-bytes-label');
const dlStatusMsg       = $('dl-status-msg');

const SIZE_LABELS = {
  'tiny': 'Tiny (~75 MB)', 'tiny.en': 'Tiny English (~75 MB)',
  'base': 'Base (~150 MB)', 'base.en': 'Base English (~150 MB)',
  'small': 'Small (~500 MB)', 'small.en': 'Small English (~500 MB)',
  'medium': 'Medium (~1.5 GB)', 'medium.en': 'Medium English (~1.5 GB)',
  'large': 'Large v1 (~3 GB)', 'large-v2': 'Large v2 (~3 GB)',
  'large-v3': 'Large v3 (~3 GB)', 'large-v3-turbo': 'Turbo (~1.5 GB)',
};

function refreshDownloadSizeDropdown() {
  const selectedType = dlModelType.value;
  const modelData = _modelsData.find(m => m.type === selectedType);
  dlModelSize.innerHTML = '';
  if (modelData && modelData.sizes.length > 0) {
    modelData.sizes.forEach(s => {
      if (s.size === 'custom' || s.size === 'lumii') return;
      const opt = document.createElement('option');
      opt.value = s.size;
      const label = SIZE_LABELS[s.size] || s.size;
      opt.textContent = s.downloaded ? `${label}  ✓` : label;
      if (s.downloaded) opt.style.color = '#34d399';
      dlModelSize.appendChild(opt);
    });
    const baseOpt = [...dlModelSize.options].find(o => o.value === 'base');
    if (baseOpt) dlModelSize.value = 'base';
  }
}

dlModelType.addEventListener('change', refreshDownloadSizeDropdown);

function openModelsModal() {
  modalModels.style.display = 'flex';
  dlProgressArea.style.display = 'none';
  dlStatusMsg.style.display = 'none';
  dlStatusMsg.className = 'dl-status-msg';
  dlProgressFill.style.width = '0%';
  dlProgressFill.classList.remove('indeterminate');
  dlProgressLabel.textContent = '0%';
  dlBytesLabel.textContent = '';
  btnStartDownload.disabled = false;
  btnCancelDownload.style.display = 'none';
  refreshDownloadSizeDropdown();
}

function closeModelsModal() { modalModels.style.display = 'none'; }

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

btnShowModels.addEventListener('click', openModelsModal);
btnCloseModels.addEventListener('click', closeModelsModal);
modalModels.addEventListener('click', e => { if (e.target === modalModels) closeModelsModal(); });

btnStartDownload.addEventListener('click', () => {
  dlProgressArea.style.display = 'block';
  dlStatusMsg.style.display = 'none';
  dlProgressFill.classList.remove('indeterminate');
  dlProgressFill.style.width = '0%';
  dlProgressLabel.textContent = '0%';
  dlBytesLabel.textContent = '';
  btnStartDownload.disabled = true;
  btnCancelDownload.style.display = 'inline-flex';
  appendLog(`Starting download: ${dlModelType.value} / ${dlModelSize.value}`, 'info');
  send({ cmd: 'download_model', model_type: dlModelType.value, model_size: dlModelSize.value, hugging_face_model_id: '' });
});

btnCancelDownload.addEventListener('click', () => {
  send({ cmd: 'cancel_download' });
  btnCancelDownload.style.display = 'none';
  btnStartDownload.disabled = false;
  dlProgressFill.classList.remove('indeterminate');
  dlStatusMsg.style.display = 'block';
  dlStatusMsg.className = 'dl-status-msg error';
  dlStatusMsg.textContent = 'Download cancelled.';
});

// ─── WebSocket message handler ────────────────────────────────────────────────
function handleServerEvent(msg) {
  switch (msg.event) {

    case 'ready':
      appendLog('Backend ready.', 'info');
      break;

    case 'models':
      populateModelDropdowns(msg.models);
      break;

    case 'languages':
      populateLanguages(msg.languages);
      break;

    case 'log':
      appendLog(msg.message, msg.level || 'info');
      break;

    case 'files_listed': {
      // Show files immediately in the table as "pending" before transcription starts
      plans = [];
      tableBody.innerHTML = '';
      if (!msg.files || msg.files.length === 0) {
        fileTable.style.display = 'none';
        emptyState.style.display = 'flex';
        appendLog('No audio files found in that folder.', 'warn');
        break;
      }
      emptyState.style.display = 'none';
      fileTable.style.display  = 'table';
      msg.files.forEach((filePath, i) => {
        const plan = {
          original_path: filePath,
          proposed_path: null,
          proposed_name: null,
          status:        'pending',
          transcript:    '',
          will_change:   false,
          duration_sec:  0,
          error:         '',
        };
        plans.push(plan);
        // Stagger animation for nicer entrance
        const tr = renderRow(plan, true);
        tr.style.animationDelay = `${i * 25}ms`;
        tableBody.appendChild(tr);
        tr.addEventListener('animationend', () => tr.classList.remove('row-new'), { once: true });
      });
      appendLog(`Found ${msg.files.length} audio file(s). Click Preview Renames to transcribe.`, 'info');
      progressWrapper.style.display = 'none';
      setStatus(`${msg.files.length} file(s) ready`, 'connected');
      updateButtons();
      break;
    }

    case 'progress': {
      const { done, total, plan } = msg;
      progressWrapper.style.display = 'flex';
      progressFill.style.width = `${Math.round((done / total) * 100)}%`;
      progressLabel.textContent = `${done} / ${total}`;
      setStatus(`Transcribing ${done}/${total}…`, 'running');

      const existingIdx = plans.findIndex(p => p.original_path === plan.original_path);
      if (existingIdx >= 0) {
        plans[existingIdx] = plan;
        updateExistingRow(plan);
      } else {
        plans.push(plan);
        appendPlanRow(plan);
      }
      break;
    }

    case 'preview_done':
      plans     = msg.plans;
      isRunning = false;
      progressFill.style.width = '100%';
      setStatus(`Done — ${plans.length} file(s)`, 'connected');
      appendLog(`Preview complete. ${plans.filter(p => p.status === 'ready').length} file(s) ready to rename.`, 'info');
      rebuildTable();
      updateButtons();
      break;

    case 'apply_done': {
      const s = msg.summary;
      isRunning = false;
      rebuildTable();
      updateButtons();
      showToast(
        `Renamed ${s.applied_count} file(s). Skipped: ${s.skipped_count}. Errors: ${s.error_count}.`,
        s.error_count > 0 ? 'error' : 'success'
      );
      appendLog(`Applied: ${s.applied_count}, skipped: ${s.skipped_count}, errors: ${s.error_count}.`, 'info');
      btnUndo.disabled = false;
      break;
    }

    case 'undo_done': {
      const r = msg.result;
      showToast(
        `Reverted ${r.reverted_count} file(s).${r.failed_count > 0 ? ` Failed: ${r.failed_count}.` : ''}`,
        r.failed_count > 0 ? 'error' : 'success'
      );
      appendLog(`Undo: reverted ${r.reverted_count}, failed ${r.failed_count}.`, 'info');
      plans = [];
      rebuildTable();
      updateButtons();
      break;
    }

    case 'download_progress': {
      const { downloaded, total, percent, elapsed } = msg;
      dlProgressArea.style.display = 'block';
      if (percent === -1 || total === 0) {
        dlProgressFill.classList.add('indeterminate');
        dlProgressFill.style.width = '';
        dlProgressLabel.textContent = elapsed ? `Downloading… ${elapsed}` : 'Downloading…';
        dlBytesLabel.textContent = 'HuggingFace download in progress';
      } else {
        dlProgressFill.classList.remove('indeterminate');
        dlProgressFill.style.width = `${percent}%`;
        dlProgressLabel.textContent = `${percent}%`;
        if (total > 0) dlBytesLabel.textContent = `${formatBytes(downloaded)} / ${formatBytes(total)}`;
      }
      break;
    }

    case 'download_done':
      dlProgressFill.classList.remove('indeterminate');
      dlProgressFill.style.width = '100%';
      dlProgressLabel.textContent = '100%';
      btnStartDownload.disabled = false;
      btnCancelDownload.style.display = 'none';
      dlStatusMsg.style.display = 'block';
      dlStatusMsg.className = 'dl-status-msg success';
      dlStatusMsg.textContent = `Download complete! Saved to: ${msg.model_path}`;
      appendLog(`Model downloaded: ${msg.model_path}`, 'info');
      showToast('Model downloaded successfully!', 'success');
      send({ cmd: 'list_models' }); // refresh checkmarks
      break;

    case 'error':
      appendLog(`ERROR: ${msg.message}`, 'error');
      showToast(msg.message, 'error');
      isRunning = false;
      updateButtons();
      setStatus('Error', 'error');
      break;
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────
loadSettings();
updateButtons();
updateModelSections();
connect();
