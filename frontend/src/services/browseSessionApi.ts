import { API_BASE, ApiError } from './api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (res.status === 204) return undefined as T;
  const body = (await res.json().catch(() => ({}))) as { detail?: string };
  if (!res.ok) throw new ApiError(res.status, body.detail ?? res.statusText);
  return body as T;
}

export const browseSessionApi = {
  createSession: (url: string) => {
    const fd = new FormData();
    fd.append('url', url);
    return request<{ session_id: string }>('/sessions', { method: 'POST', body: fd });
  },

  closeSession: (id: string) => request<void>(`/sessions/${id}`, { method: 'DELETE' }),

  forceCloseSession: (id: string) => request<void>(`/sessions/${id}/force`, { method: 'DELETE' }),

  deleteSession: (id: string) => request<void>(`/sessions/${id}/delete`, { method: 'DELETE' }),

  sendAction: (id: string, action: Record<string, unknown>) =>
    request<{ ok: boolean }>(`/sessions/${id}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(action),
    }),

  flushProfile: () => request<void>('/sessions/profile', { method: 'DELETE' }),

  getPageTitles: (id: string) =>
    request<{ titles: { title: string; filename: string }[] }>(`/sessions/${id}/page-titles`),

  clearCandidates: (id: string) =>
    request<void>(`/sessions/${id}/candidates`, { method: 'DELETE' }),

  startSessionDownload: (
    id: string,
    payload: { url: string; output_name: string; quality: string; parallel: number },
  ) =>
    request<{ dl_id: string }>(`/sessions/${id}/download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),

  confirmDownload: (
    sessionId: string,
    dlId: string,
    ok: boolean,
    deleteFile: boolean,
  ) =>
    request<{ ok: boolean }>(`/sessions/${sessionId}/downloads/${dlId}/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ok, delete_file: deleteFile }),
    }),
};
