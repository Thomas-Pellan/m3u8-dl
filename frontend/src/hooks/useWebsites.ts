import { useEffect, useState } from 'preact/hooks';
import type { Website } from '../models/website';
import { API_BASE } from '../services/api';

export function useWebsites(): Website[] {
  const [websites, setWebsites] = useState<Website[]>([]);

  useEffect(() => {
    const source = new EventSource(`${API_BASE}/website-events`);
    source.addEventListener('websites', (e) => {
      setWebsites(JSON.parse((e as MessageEvent).data) as Website[]);
    });
    return () => source.close();
  }, []);

  return websites;
}