import { fetchRunning, fetchQueued, fetchHistory, fetchLogs, fetchExecutorOutput, fetchHistoryOutput, } from './api';
let currentPage = 1;
let lastLogId = 0;
let logLevel = 'INFO';
let userScrolled = false;
let cachedRunning = [];
let cachedHistory = [];
let lastRunningFetch = 0;
let viewMode = 'log';
let selectedRepo = null;
let selectedNotificationId = null;
let selectedTimestamp = null;
let lastOutputId = 0;
const MAX_LOG_LINES = 1000;
const SPLIT_STORAGE_KEY = 'agent0-split-ratio';
function escapeHtml(text) {
    const el = document.createElement('span');
    el.textContent = text;
    return el.innerHTML;
}
function formatDuration(seconds) {
    if (seconds < 60)
        return `${Math.round(seconds)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m ${s}s`;
}
function statusBadge(status) {
    const cls = status === 'success' ? 'badge-success' : status === 'timeout' ? 'badge-timeout' : 'badge-failure';
    return `<span class="badge ${cls}">${escapeHtml(status)}</span>`;
}
function switchToLog() {
    viewMode = 'log';
    selectedRepo = null;
    selectedNotificationId = null;
    selectedTimestamp = null;
    lastOutputId = 0;
    document.getElementById('log-output').innerHTML = '';
    lastLogId = 0;
    userScrolled = false;
    updatePanelHeader();
    renderHistory(cachedHistory);
    refreshLogs();
}
function switchToExecutor(repo) {
    viewMode = 'executor';
    selectedRepo = repo;
    selectedNotificationId = null;
    selectedTimestamp = null;
    lastOutputId = 0;
    document.getElementById('log-output').innerHTML = '';
    userScrolled = false;
    updatePanelHeader();
    renderHistory(cachedHistory);
    refreshExecutorOutput();
}
function switchToHistory(notificationId, repo, timestamp) {
    viewMode = 'history';
    selectedRepo = repo;
    selectedNotificationId = notificationId;
    selectedTimestamp = timestamp;
    lastOutputId = 0;
    document.getElementById('log-output').innerHTML = '';
    userScrolled = false;
    updatePanelHeader();
    renderHistory(cachedHistory);
    refreshHistoryOutput();
}
function updatePanelHeader() {
    const headerEl = document.querySelector('.log-header');
    if (viewMode === 'executor' && selectedRepo) {
        headerEl.innerHTML = `
      <h2 class="heading-clickable" id="switch-to-log">Executor: ${escapeHtml(selectedRepo)}</h2>
      <span class="mode-hint">click heading to return to log</span>
    `;
        document.getElementById('switch-to-log').addEventListener('click', switchToLog);
    }
    else if (viewMode === 'history' && selectedRepo) {
        headerEl.innerHTML = `
      <h2 class="heading-clickable" id="switch-to-log">History: ${escapeHtml(selectedRepo)}</h2>
      <span class="mode-hint">click heading to return to log</span>
    `;
        document.getElementById('switch-to-log').addEventListener('click', switchToLog);
    }
    else {
        headerEl.innerHTML = `
      <h2>Log</h2>
      <select id="log-level">
        <option value="DEBUG" ${logLevel === 'DEBUG' ? 'selected' : ''}>DEBUG</option>
        <option value="INFO" ${logLevel === 'INFO' ? 'selected' : ''}>INFO</option>
        <option value="WARNING" ${logLevel === 'WARNING' ? 'selected' : ''}>WARNING</option>
        <option value="ERROR" ${logLevel === 'ERROR' ? 'selected' : ''}>ERROR</option>
      </select>
    `;
        initLogLevelFilter();
    }
}
function renderRunning(tasks) {
    cachedRunning = tasks;
    lastRunningFetch = Date.now();
    if (viewMode === 'executor' && selectedRepo) {
        const stillRunning = tasks.some(t => t.repo === selectedRepo);
        if (!stillRunning) {
            switchToLog();
        }
    }
    const el = document.getElementById('running');
    if (tasks.length === 0) {
        el.innerHTML = '<p class="empty">No running tasks</p>';
        return;
    }
    const rows = tasks.map((t, i) => `
    <tr class="row-clickable ${viewMode === 'executor' && selectedRepo === t.repo ? 'row-active' : ''}">
      <td>${escapeHtml(t.repo)}</td>
      <td>${escapeHtml(t.event_type)}</td>
      <td><a href="https://github.com/${t.repo}/issues/${t.number}" target="_blank" class="ref-link" onclick="event.stopPropagation()">#${t.number}</a></td>
      <td>${escapeHtml(t.trigger_user)}</td>
      <td title="${escapeHtml(t.trigger_text)}">${escapeHtml(t.trigger_text.slice(0, 60))}</td>
      <td class="elapsed-cell" data-idx="${i}">${formatDuration(t.elapsed_seconds)}</td>
    </tr>
  `).join('');
    el.innerHTML = `
    <table>
      <thead><tr>
        <th>Repo</th><th>Event</th><th>Ref</th><th>User</th><th>Trigger</th><th>Elapsed</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
    const trs = el.querySelectorAll('tbody tr');
    trs.forEach((tr, i) => {
        tr.addEventListener('click', () => {
            switchToExecutor(tasks[i].repo);
            renderRunning(cachedRunning);
        });
    });
}
function tickElapsed() {
    if (cachedRunning.length === 0)
        return;
    const drift = (Date.now() - lastRunningFetch) / 1000;
    const cells = document.querySelectorAll('.elapsed-cell');
    cells.forEach(cell => {
        const idx = parseInt(cell.dataset.idx || '0', 10);
        const task = cachedRunning[idx];
        if (task) {
            cell.textContent = formatDuration(task.elapsed_seconds + drift);
        }
    });
}
function renderQueued(tasks) {
    const el = document.getElementById('queued');
    if (tasks.length === 0) {
        el.innerHTML = '<p class="empty">No queued tasks</p>';
        return;
    }
    const rows = tasks.map(t => `
    <tr>
      <td>${escapeHtml(t.repo)}</td>
      <td>${escapeHtml(t.event_type)}</td>
      <td><a href="https://github.com/${t.repo}/issues/${t.number}" target="_blank" class="ref-link">#${t.number}</a></td>
      <td>${escapeHtml(t.trigger_user)}</td>
      <td title="${escapeHtml(t.trigger_text)}">${escapeHtml(t.trigger_text.slice(0, 60))}</td>
      <td>${t.position}</td>
    </tr>
  `).join('');
    el.innerHTML = `
    <table>
      <thead><tr>
        <th>Repo</th><th>Event</th><th>Ref</th><th>User</th><th>Trigger</th><th>Position</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}
function renderHistory(entries) {
    cachedHistory = entries;
    const el = document.getElementById('history');
    if (entries.length === 0) {
        el.innerHTML = '<p class="empty">No history</p>';
        return;
    }
    const rows = entries.map(e => `
    <tr class="row-clickable ${viewMode === 'history' && selectedTimestamp === e.timestamp ? 'row-active' : ''}">
      <td>${escapeHtml(e.timestamp.slice(0, 19))}</td>
      <td>${escapeHtml(e.repo)}</td>
      <td>${escapeHtml(e.event_type)}</td>
      <td><a href="https://github.com/${e.repo}/issues/${e.reference}" target="_blank" class="ref-link" onclick="event.stopPropagation()">#${e.reference}</a></td>
      <td>${escapeHtml(e.trigger_user)}</td>
      <td>${statusBadge(e.status)}</td>
      <td>${formatDuration(e.duration_seconds)}</td>
      <td>${e.input_tokens + e.output_tokens}</td>
      <td>$${e.cost_usd.toFixed(4)}</td>
    </tr>
  `).join('');
    el.innerHTML = `
    <table>
      <thead><tr>
        <th>Time</th><th>Repo</th><th>Event</th><th>Ref</th><th>User</th><th>Status</th><th>Duration</th><th>Tokens</th><th>Cost</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
    const trs = el.querySelectorAll('tbody tr');
    trs.forEach((tr, i) => {
        tr.addEventListener('click', () => {
            const e = entries[i];
            switchToHistory(e.notification_id, e.repo, e.timestamp);
        });
    });
    const pag = document.getElementById('pagination');
    pag.innerHTML = `
    <button id="prev-page" ${currentPage <= 1 ? 'disabled' : ''}>Previous</button>
    <span>Page ${currentPage}</span>
    <button id="next-page" ${entries.length < 50 ? 'disabled' : ''}>Next</button>
  `;
    document.getElementById('prev-page')?.addEventListener('click', () => {
        if (currentPage > 1) {
            currentPage--;
            refreshTasks();
        }
    });
    document.getElementById('next-page')?.addEventListener('click', () => {
        if (entries.length >= 50) {
            currentPage++;
            refreshTasks();
        }
    });
}
function appendLogEntry(entry) {
    const container = document.getElementById('log-output');
    const line = document.createElement('div');
    line.className = `log-line log-${entry.level}`;
    line.textContent = `${entry.timestamp} ${entry.level} ${entry.logger} ${entry.message}`;
    container.appendChild(line);
    while (container.children.length > MAX_LOG_LINES) {
        container.removeChild(container.firstChild);
    }
    if (!userScrolled) {
        container.scrollTop = container.scrollHeight;
    }
}
function appendOutputLine(text) {
    const container = document.getElementById('log-output');
    const line = document.createElement('div');
    line.className = 'log-line log-executor';
    line.textContent = text;
    container.appendChild(line);
    while (container.children.length > MAX_LOG_LINES) {
        container.removeChild(container.firstChild);
    }
    if (!userScrolled) {
        container.scrollTop = container.scrollHeight;
    }
}
function initLogScroll() {
    const container = document.getElementById('log-output');
    container.addEventListener('scroll', () => {
        const atBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 30;
        userScrolled = !atBottom;
    });
}
async function refreshTasks() {
    const status = document.getElementById('status');
    try {
        const [running, queued, history] = await Promise.all([
            fetchRunning(),
            fetchQueued(),
            fetchHistory(currentPage),
        ]);
        renderRunning(running);
        renderQueued(queued);
        renderHistory(history);
        status.textContent = 'connected';
        status.className = 'status status-ok';
    }
    catch {
        status.textContent = 'disconnected';
        status.className = 'status status-error';
    }
}
async function refreshLogs() {
    try {
        const data = await fetchLogs(lastLogId, logLevel);
        for (const entry of data.entries) {
            appendLogEntry(entry);
        }
        lastLogId = data.last_id;
    }
    catch {
        // silent — task refresh handles status indicator
    }
}
async function refreshExecutorOutput() {
    if (!selectedRepo)
        return;
    try {
        const data = await fetchExecutorOutput(selectedRepo, lastOutputId);
        for (const entry of data.entries) {
            appendOutputLine(entry.text);
        }
        lastOutputId = data.last_id;
    }
    catch {
        // silent
    }
}
async function refreshHistoryOutput() {
    if (!selectedNotificationId || !selectedTimestamp)
        return;
    try {
        const data = await fetchHistoryOutput(selectedNotificationId, selectedTimestamp);
        for (const entry of data.entries) {
            appendOutputLine(entry.text);
        }
    }
    catch {
        // silent
    }
}
async function refreshRightPanel() {
    if (viewMode === 'executor' && selectedRepo) {
        await refreshExecutorOutput();
    }
    else if (viewMode === 'history') {
        // history output is static, no polling needed
    }
    else {
        await refreshLogs();
    }
}
function initLogLevelFilter() {
    const select = document.getElementById('log-level');
    if (!select)
        return;
    select.value = logLevel;
    select.addEventListener('change', () => {
        logLevel = select.value;
        lastLogId = 0;
        document.getElementById('log-output').innerHTML = '';
        refreshLogs();
    });
}
function initDivider() {
    const divider = document.getElementById('panel-divider');
    const main = document.querySelector('main');
    let dragging = false;
    const saved = localStorage.getItem(SPLIT_STORAGE_KEY);
    if (saved) {
        const ratio = parseFloat(saved);
        if (ratio > 0.15 && ratio < 0.85) {
            main.style.gridTemplateColumns = `${ratio}fr 6px ${1 - ratio}fr`;
        }
    }
    divider.addEventListener('mousedown', (e) => {
        e.preventDefault();
        dragging = true;
        divider.classList.add('dragging');
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    });
    document.addEventListener('mousemove', (e) => {
        if (!dragging)
            return;
        const rect = main.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const ratio = Math.min(0.85, Math.max(0.15, x / rect.width));
        main.style.gridTemplateColumns = `${ratio}fr 6px ${1 - ratio}fr`;
        localStorage.setItem(SPLIT_STORAGE_KEY, ratio.toString());
    });
    document.addEventListener('mouseup', () => {
        if (!dragging)
            return;
        dragging = false;
        divider.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
    });
}
initDivider();
initLogScroll();
initLogLevelFilter();
refreshTasks();
refreshLogs();
setInterval(refreshTasks, 10_000);
setInterval(refreshRightPanel, 2_000);
setInterval(tickElapsed, 1_000);
