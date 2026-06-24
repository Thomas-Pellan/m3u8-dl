import { useEffect, useState } from 'preact/hooks';
import type { BrowseSession } from '../models/browse_session';
import { API_BASE } from '../services/api';

export function useBrowseSessions(): BrowseSession[] {
  const [sessions, setSessions] = useState<BrowseSession[]>([]);

  useEffect(() => {
    const source = new EventSource(`${API_BASE}/session-events`);
    source.addEventListener('sessions', (e) => {
      setSessions(JSON.parse((e as MessageEvent).data));
    });
    return () => source.close();
  }, []);

  return sessions;
}
