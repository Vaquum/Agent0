export async function fetchRunning() {
    const res = await fetch('/api/tasks/running');
    if (!res.ok)
        throw new Error(`HTTP ${res.status}`);
    return res.json();
}
export async function fetchQueued() {
    const res = await fetch('/api/tasks/queued');
    if (!res.ok)
        throw new Error(`HTTP ${res.status}`);
    return res.json();
}
export async function fetchHistory(page = 1, perPage = 50) {
    const res = await fetch(`/api/tasks/history?page=${page}&per_page=${perPage}`);
    if (!res.ok)
        throw new Error(`HTTP ${res.status}`);
    return res.json();
}
export async function fetchLogs(after = 0, level = 'INFO') {
    const res = await fetch(`/api/logs?after=${after}&level=${level}`);
    if (!res.ok)
        throw new Error(`HTTP ${res.status}`);
    return res.json();
}
export async function fetchExecutorOutput(repoKey, after = 0) {
    const res = await fetch(`/api/tasks/running/${repoKey}/output?after=${after}`);
    if (!res.ok)
        throw new Error(`HTTP ${res.status}`);
    return res.json();
}
export async function fetchHistoryOutput(notificationId, timestamp) {
    const params = new URLSearchParams({ timestamp });
    const url = `/api/tasks/history/${notificationId}/output?${params}`;
    const res = await fetch(url);
    if (!res.ok)
        throw new Error(`HTTP ${res.status}`);
    return res.json();
}
