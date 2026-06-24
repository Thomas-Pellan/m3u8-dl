import type { Website } from '../models/website';
import { API_BASE, ApiError } from './api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (res.status === 204) return undefined as T;
  const body = (await res.json().catch(() => ({}))) as { detail?: string };
  if (!res.ok) throw new ApiError(res.status, body.detail ?? res.statusText);
  return body as T;
}

export type OpenSessionResult =
  | { action: 'created'; session_id: string }
  | { action: 'deferred'; message: string };

export const websiteApi = {
  getAll: () => request<Website[]>('/websites'),

  updateRating: (id: number, rating: number) =>
    request<{ ok: boolean }>(`/websites/${id}/rating`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    }),

  setWorking: (id: number, working: boolean) =>
    request<{ ok: boolean }>(`/websites/${id}/working`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ working }),
    }),

  flushNotWorking: () =>
    request<{ deleted: number }>('/websites/flush', { method: 'DELETE' }),

  flushCdns: (id: number) =>
    request<{ flushed: number }>(`/websites/${id}/cdns`, { method: 'DELETE' }),

  delete: (id: number) => request<void>(`/websites/${id}`, { method: 'DELETE' }),

  openSession: (id: number) =>
    request<OpenSessionResult>(`/websites/${id}/open-session`, { method: 'POST' }),
};
