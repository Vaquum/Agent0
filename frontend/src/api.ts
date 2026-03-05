export interface RunningTask {
  repo: string;
  event_type: string;
  number: number;
  trigger_user: string;
  trigger_text: string;
  started_at: string;
  elapsed_seconds: number;
}

export interface QueuedTask {
  repo: string;
  event_type: string;
  number: number;
  trigger_user: string;
  trigger_text: string;
  position: number;
}

export interface HistoryEntry {
  timestamp: string;
  notification_id: string;
  event_type: string;
  repo: string;
  reference: number;
  trigger_user: string;
  trigger_text: string;
  action_taken: string;
  status: string;
  response: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  duration_seconds: number;
  error: string | null;
}

export interface LogEntry {
  id: number;
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

export interface LogResponse {
  entries: LogEntry[];
  last_id: number;
}

export async function fetchRunning(): Promise<RunningTask[]> {
  const res = await fetch('/api/tasks/running');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchQueued(): Promise<QueuedTask[]> {
  const res = await fetch('/api/tasks/queued');
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchHistory(page: number = 1, perPage: number = 50): Promise<HistoryEntry[]> {
  const res = await fetch(`/api/tasks/history?page=${page}&per_page=${perPage}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchLogs(after: number = 0, level: string = 'INFO'): Promise<LogResponse> {
  const res = await fetch(`/api/logs?after=${after}&level=${level}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export interface ExecutorOutputEntry {
  id: number;
  text: string;
}

export interface ExecutorOutputResponse {
  entries: ExecutorOutputEntry[];
  last_id: number;
}

export async function fetchExecutorOutput(
  repoKey: string,
  after: number = 0,
): Promise<ExecutorOutputResponse> {
  const res = await fetch(`/api/tasks/running/${repoKey}/output?after=${after}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function fetchHistoryOutput(
  notificationId: string,
  timestamp: string,
): Promise<ExecutorOutputResponse> {
  const params = new URLSearchParams({timestamp});
  const url = `/api/tasks/history/${notificationId}/output?${params}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
