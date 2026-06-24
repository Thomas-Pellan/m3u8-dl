import type { Job } from '../../models/job';
import { api } from '../../services/api';
import { ScheduledRow } from './ScheduledRow';

interface Props {
  jobs: Job[];
}

export function ScheduledPanel({ jobs }: Props) {
  const schedCount = jobs.filter((j) => j.status === 'scheduled').length;

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
        <span class="card-title">Scheduled</span>
        <button type="button" class="btn-flush" onClick={flush}>
          Flush done/errors
        </button>
        <span class="jh-tick">{schedCount > 0 ? `${schedCount} / 10` : ''}</span>
      </div>
      {jobs.length === 0 ? (
        <p class="empty">No scheduled jobs.</p>
      ) : (
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>URL</th>
                <th>Output file</th>
                <th>Scheduled for</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <ScheduledRow key={j.id} job={j} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
