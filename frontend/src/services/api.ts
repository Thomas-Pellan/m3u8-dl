export const API_BASE = import.meta.env.VITE_API_URL ?? '/api';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (res.status === 204) return undefined as T;
  const body = (await res.json().catch(() => ({}))) as { detail?: string };
  if (!res.ok) throw new ApiError(res.status, body.detail ?? res.statusText);
  return body as T;
}

export const api = {
  suggestNames: (url: string) =>
    request<{ candidates: string[] }>(`/suggest-names?${new URLSearchParams({ url })}`),

  startCapture: (data: FormData) =>
    request<{ job_id: string }>('/capture', { method: 'POST', body: data }),

  retryJob: (id: string) => request<{ job_id: string }>(`/jobs/${id}/retry`, { method: 'POST' }),

  deleteJob: (id: string) => request<void>(`/jobs/${id}`, { method: 'DELETE' }),

  rescheduleJob: (id: string, scheduledAt: string) => {
    const fd = new FormData();
    fd.append('scheduled_at', scheduledAt);
    return request<{ job_id: string }>(`/jobs/${id}/reschedule`, { method: 'PATCH', body: fd });
  },
};
