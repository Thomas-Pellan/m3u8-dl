import { useEffect, useState } from 'preact/hooks';
import type { Job } from '../models/job';
import { connectJobsStream } from '../services/sse';

export function useJobs(): Job[] {
  const [jobs, setJobs] = useState<Job[]>([]);

  useEffect(() => connectJobsStream(setJobs), []);

  return jobs;
}
