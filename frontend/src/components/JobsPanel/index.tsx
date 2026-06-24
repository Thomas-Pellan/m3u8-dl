import type { Job } from '../../models/job';
import { api } from '../../services/api';
import { JobRow } from './JobRow';

interface Props {
  jobs: Job[];
}

export function JobsPanel({ jobs }: Props) {
  async function flush() {
    await Promise.all(
      jobs
        .filter((j) => j.status === 'done' || j.status === 'error')
        .map((j) => api.deleteJob(j.id).catch(console.error)),
    );
  }

  return (
    <div class="card">
      <div class="jh">
        <span class="card-title">Jobs</span>
        <button type="button" class="btn-flush" onClick={flush}>
          Flush done/errors
        </button>
        <span class="jh-tick">
          {jobs.length > 0 ? `${jobs.length} job${jobs.length > 1 ? 's' : ''}` : ''}
        </span>
      </div>
      {jobs.length === 0 ? (
        <p class="empty">No jobs yet.</p>
      ) : (
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>URL</th>
                <th>Output file</th>
                <th>Started</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <JobRow key={j.id} job={j} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
