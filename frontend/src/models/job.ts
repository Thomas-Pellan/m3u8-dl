export type JobStatus = 'pending' | 'running' | 'scheduled' | 'done' | 'error';

export interface Job {
  id: string;
  status: JobStatus;
  url: string;
  output_name: string;
  mode: string;
  quality: string;
  parallel: number;
  started_at: string;
  scheduled_at: string | null;
  progress: number | null;
  error: string | null;
  output: string | null;
  logs: string[];
}

export const BADGE_CLASS: Record<JobStatus, string> = {
  pending: 'p',
  running: 'r',
  done: 'd',
  error: 'e',
  scheduled: 'p',
};
