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
    const message = payload.error || `请求失败（${response.status}）`;
    const error = new ApiError(message, response.status);
    if (message === "AI 请求已取消。" || message.startsWith("任务已停止")) error.name = "AbortError";
    throw error;
  }
  return payload.data as T;
}

export function createTaskId(kind: string): string {
  return `${kind}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export async function cancelTask(taskId: string): Promise<void> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 4; attempt += 1) {
    try {
      await api(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, { method: "POST" });
      return;
    } catch (error) {
      lastError = error;
      const registrationRace = error instanceof ApiError && error.status === 400 && error.message.includes("任务不存在");
      if (!registrationRace || attempt === 3) throw error;
      await new Promise((resolve) => window.setTimeout(resolve, 120 * (attempt + 1)));
    }
  }
  throw lastError;
}
