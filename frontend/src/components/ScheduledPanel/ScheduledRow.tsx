import { useState } from 'preact/hooks';
import { BADGE_CLASS, type Job } from '../../models/job';
import { api } from '../../services/api';
import { formatShortDateTime, toDatetimeLocal } from '../../utils/date';

export function ScheduledRow({ job: j }: { job: Job }) {
  const [rescheduling, setRescheduling] = useState(false);
  const [rescheduleVal, setRescheduleVal] = useState(
    j.scheduled_at ? toDatetimeLocal(j.scheduled_at) : '',
  );

  async function cancel() {
    await api.deleteJob(j.id).catch(console.error);
  }

  async function clear() {
    await api.deleteJob(j.id).catch(console.error);
  }

  async function confirmReschedule() {
    if (!rescheduleVal) return;
    try {
      await api.rescheduleJob(j.id, new Date(rescheduleVal).toISOString());
      setRescheduling(false);
    } catch (err) {
      alert(`Reschedule failed: ${(err as Error).message}`);
    }
  }

  return (
    <tr>
      <td class="c-id">{j.id}</td>
      <td class="c-url" title={j.url}>
        {j.url}
      </td>
      <td class="c-name">{j.output_name}</td>
      <td class="c-sched-at">{j.scheduled_at ? formatShortDateTime(j.scheduled_at) : '—'}</td>
      <td class="c-st">
        {j.status === 'scheduled' ? (
          rescheduling ? (
            <div class="reschedule-form">
              <input
                type="datetime-local"
                class="reschedule-input"
                value={rescheduleVal}
                onInput={(e) => setRescheduleVal((e.target as HTMLInputElement).value)}
              />
              <div class="reschedule-btns">
                <button class="act-btn confirm-reschedule-btn" onClick={confirmReschedule}>
                  Confirm
                </button>
                <button class="act-btn abort-reschedule-btn" onClick={() => setRescheduling(false)}>
                  Abort
                </button>
              </div>
            </div>
          ) : (
            <div class="sched-actions">
              <button class="act-btn reschedule-btn" onClick={() => setRescheduling(true)}>
                Reschedule
              </button>
              <button class="act-btn cancel-sched-btn" onClick={cancel}>
                Cancel
              </button>
            </div>
          )
        ) : (
          <>
            <span class={`badge ${BADGE_CLASS[j.status]}`}>{j.status}</span>
            {j.status === 'running' && j.progress != null && <span class="pct">{j.progress}%</span>}
            {j.error && <div class="err">{j.error}</div>}
            {(j.status === 'done' || j.status === 'error') && (
              <div class="sched-post-actions">
                <button class="act-btn clear-sched-btn" onClick={clear}>
                  Clear
                </button>
              </div>
            )}
          </>
        )}
      </td>
    </tr>
  );
}
