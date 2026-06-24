import { useState } from 'preact/hooks';
import type { BrowseSession, SessionDownload } from '../../models/browse_session';
import { useBrowseSessions } from '../../hooks/useBrowseSessions';
import { browseSessionApi } from '../../services/browseSessionApi';

export function SessionsTab() {
  const sessions = useBrowseSessions();

  if (sessions.length === 0) {
    return (
      <p class="sessions-empty">
        No browser sessions yet. Open a session in the Captured tab to get started.
      </p>
    );
  }

  return (
    <div class="sessions-list">
      {sessions.map((s) => (
        <SessionRow key={s.id} session={s} />
      ))}
    </div>
  );
}

function SessionRow({ session: s }: { session: BrowseSession }) {
  const [confirmKill, setConfirmKill] = useState(false);
  const [busy, setBusy] = useState(false);

  const isActive = s.status === 'opening' || s.status === 'active';
  const activeDownloads = s.downloads.filter(
    (d) => d.status === 'running' || d.status === 'assembling',
  );

  async function handleClose() {
    setBusy(true);
    try {
      await browseSessionApi.closeSession(s.id);
    } finally {
      setBusy(false);
    }
  }

  async function handleForceClose() {
    setBusy(true);
    try {
      await browseSessionApi.forceCloseSession(s.id);
    } finally {
      setBusy(false);
      setConfirmKill(false);
    }
  }

  return (
    <div class={`session-row${isActive ? ' session-row--active' : ''}`}>
      <div class="session-row-header">
        <span class={`session-status-badge session-status--${s.status}`}>{s.status}</span>
        {s.close_when_done && (
          <span class="session-closing-badge">closing after download</span>
        )}
        <span class="session-row-url" title={s.url}>{s.url}</span>
        <span class="session-row-id">#{s.id}</span>
      </div>

      {s.downloads.length > 0 && (
        <div class="session-downloads">
          {s.downloads.map((dl) => (
            <DownloadRow key={dl.id} dl={dl} sessionId={s.id} />
          ))}
        </div>
      )}

      {isActive && (
        <div class="session-row-actions">
          {s.close_when_done ? (
            confirmKill ? (
              <>
                <span class="session-kill-warning">
                  Force closing will cancel {activeDownloads.length} active download
                  {activeDownloads.length !== 1 ? 's' : ''}
                </span>
                <button
                  class="act-btn force-close-btn"
                  onClick={handleForceClose}
                  disabled={busy}
                >
                  Confirm kill
                </button>
                <button
                  class="act-btn scroll-btn"
                  onClick={() => setConfirmKill(false)}
                  disabled={busy}
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                class="act-btn force-close-btn"
                onClick={() => setConfirmKill(true)}
                disabled={busy}
              >
                Force close
              </button>
            )
          ) : confirmKill ? (
            <>
              {activeDownloads.length > 0 && (
                <span class="session-kill-warning">
                  {activeDownloads.length} download{activeDownloads.length !== 1 ? 's' : ''} in
                  progress — close now?
                </span>
              )}
              <button
                class="act-btn force-close-btn"
                onClick={handleForceClose}
                disabled={busy}
              >
                Confirm kill
              </button>
              <button
                class="act-btn scroll-btn"
                onClick={() => setConfirmKill(false)}
                disabled={busy}
              >
                Cancel
              </button>
            </>
          ) : (
            <>
              {activeDownloads.length === 0 ? (
                <button class="act-btn close-session-btn" onClick={handleClose} disabled={busy}>
                  Close session
                </button>
              ) : (
                <button class="act-btn close-session-btn" onClick={handleClose} disabled={busy}>
                  Close after downloads
                </button>
              )}
              <button
                class="act-btn force-close-btn"
                onClick={() => setConfirmKill(true)}
                disabled={busy}
              >
                Force kill
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

const DL_LOG_LINES = 3;

function DownloadRow({ dl, sessionId }: { dl: SessionDownload; sessionId: string }) {
  const isActive = dl.status === 'running' || dl.status === 'assembling';
  const [confirmed, setConfirmed] = useState(false);
  const [askDelete, setAskDelete] = useState(false);
  const [busy, setBusy] = useState(false);

  const statusLabel =
    dl.status === 'assembling'
      ? 'assembling'
      : dl.status === 'done'
        ? 'done'
        : dl.status === 'error'
          ? 'error'
          : dl.status === 'cancelled'
            ? 'cancelled'
            : `${dl.progress}%`;

  const visibleLogs = (dl.logs ?? []).slice(-DL_LOG_LINES);

  async function handleOk() {
    setBusy(true);
    try {
      await browseSessionApi.confirmDownload(sessionId, dl.id, true, false);
      setConfirmed(true);
    } catch {
      // non-fatal — buttons stay visible
    } finally {
      setBusy(false);
    }
  }

  async function handleNotOk(deleteFile: boolean) {
    setBusy(true);
    try {
      await browseSessionApi.confirmDownload(sessionId, dl.id, false, deleteFile);
      setConfirmed(true);
    } catch {
      // non-fatal
    } finally {
      setBusy(false);
      setAskDelete(false);
    }
  }

  return (
    <div class={`dl-row dl-row--${dl.status}`}>
      <span class={`dl-status-dot dl-dot--${dl.status}`} />
      <span class="dl-name">{dl.output_name}</span>
      {isActive && dl.total_segments > 0 && (
        <span class="dl-segments">
          {dl.done_segments}/{dl.total_segments} segs
        </span>
      )}
      <span class="dl-label">{statusLabel}</span>
      {isActive && (
        <div class="dl-bar-wrap">
          <div
            class={`dl-bar dl-bar--${dl.status}`}
            style={{ width: `${dl.status === 'assembling' ? 100 : dl.progress}%` }}
          />
        </div>
      )}
      {visibleLogs.length > 0 && (
        <div class="dl-logs">
          {visibleLogs.map((line, i) => (
            <span key={i} class="dl-log-line">{line}</span>
          ))}
        </div>
      )}
      {dl.status === 'error' && dl.error && (
        <span class="dl-error" title={dl.error}>
          {dl.error.slice(0, 120)}
        </span>
      )}
      {dl.status === 'done' && !confirmed && (
        <div class="dl-confirm-row">
          {askDelete ? (
            <>
              <span class="dl-confirm-question">Delete output file?</span>
              <button
                class="act-btn dl-confirm-yes-btn"
                onClick={() => handleNotOk(true)}
                disabled={busy}
              >
                Yes, delete
              </button>
              <button
                class="act-btn dl-confirm-no-btn"
                onClick={() => handleNotOk(false)}
                disabled={busy}
              >
                No, keep
              </button>
            </>
          ) : (
            <>
              <button
                class="act-btn dl-ok-btn"
                onClick={handleOk}
                disabled={busy}
                title="Download is correct — keep CDN"
              >
                ✓ OK
              </button>
              <button
                class="act-btn dl-wrong-btn"
                onClick={() => setAskDelete(true)}
                disabled={busy}
                title="Wrong content — remove CDN"
              >
                ✗ Wrong
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
