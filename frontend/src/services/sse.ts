import type { Job } from '../models/job';
import { API_BASE } from './api';

export function connectJobsStream(onJobs: (jobs: Job[]) => void): () => void {
  const source = new EventSource(`${API_BASE}/events`);

  source.addEventListener('jobs', (e) => {
    onJobs(JSON.parse((e as MessageEvent<string>).data) as Job[]);
  });

  return () => source.close();
}
