import { useEffect, useState } from 'preact/hooks';
import { API_BASE } from '../services/api';

export function useSessionScreen(sessionId: string | null): string | null {
  const [frame, setFrame] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionId) {
      setFrame(null);
      return;
    }
    const source = new EventSource(`${API_BASE}/sessions/${sessionId}/screen`);
    source.addEventListener('screenshot', (e) => setFrame((e as MessageEvent).data));
    return () => source.close();
  }, [sessionId]);

  return frame;
}
