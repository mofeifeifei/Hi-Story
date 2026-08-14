type ApiOptions = Omit<RequestInit, "body"> & { body?: unknown };

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function api<T = unknown>(path: string, options: ApiOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body !== undefined) headers.set("Content-Type", "application/json");
  if (window.__HI_STORY_TOKEN__) headers.set("X-HiStory-Token", window.__HI_STORY_TOKEN__);

  const response = await fetch(path, {
    ...options,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  const payload = await response.json().catch(() => ({ ok: false, error: "服务返回了无法识别的数据。" }));
  if (!response.ok || !payload.ok) {
    throw new ApiError(payload.error || `请求失败（${response.status}）`, response.status);
  }
  return payload.data as T;
}

export function createTaskId(kind: string): string {
  return `${kind}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function cancelTask(taskId: string): Promise<void> {
  await api(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" });
}
