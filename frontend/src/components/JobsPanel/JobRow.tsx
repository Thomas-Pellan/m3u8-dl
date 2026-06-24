import { useEffect, useRef } from 'preact/hooks';
import { BADGE_CLASS, type Job } from '../../models/job';
import { api } from '../../services/api';
import { logColor } from '../../utils/log';

export function JobRow({ job: j }: { job: Job }) {
  const logsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logsRef.current) logsRef.current.scrollTop = logsRef.current.scrollHeight;
  }, [j.logs.length]);

  async function retry() {
    await api.retryJob(j.id).catch(console.error);
  }

  async function clear() {
    await api.deleteJob(j.id).catch(console.error);
  }

  return (
    <tr>
      <td class="c-id">{j.id}</td>
      <td class="c-url" title={j.url}>
        {j.url}
      </td>
      <td class="c-name">{j.output_name}</td>
      <td class="c-time">{j.started_at.replace('T', ' ')}</td>
      <td class="c-st">
        <span class={`badge ${BADGE_CLASS[j.status]}`}>{j.status}</span>
        {j.status === 'running' && j.progress != null && <span class="pct">{j.progress}%</span>}
        {j.error && <div class="err">{j.error}</div>}
        {j.status === 'error' && (
          <div class="job-actions">
            <button class="act-btn retry-btn" onClick={retry}>
              Retry
            </button>
            <button class="act-btn clear-btn" onClick={clear}>
              Clear
            </button>
          </div>
        )}
        {j.output && <div class="out">✓ {j.output}</div>}
        {j.logs.length > 0 && (
          <div class="logs" ref={logsRef}>
            {j.logs.map((line, i) => (
              <span key={i} style={{ color: logColor(line) }}>
                {line}
              </span>
            ))}
          </div>
        )}
      </td>
    </tr>
  );
}
