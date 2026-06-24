import type { BrowseSession } from '../../models/browse_session';
import { useBrowseSessions } from '../../hooks/useBrowseSessions';
import { useWebsites } from '../../hooks/useWebsites';
import { browseSessionApi } from '../../services/browseSessionApi';
import { BrowserViewer } from './BrowserViewer';
import { CandidatePanel } from './CandidatePanel';
import { SessionForm } from './SessionForm';

function extractOrigin(url: string): string | null {
  try {
    const u = new URL(url);
    return `${u.protocol}//${u.host}`;
  } catch {
    return null;
  }
}

export function CapturedTab() {
  const sessions = useBrowseSessions();
  const websites = useWebsites();
  const active = sessions.find((s) => s.status === 'opening' || s.status === 'active') ?? null;
  const lastFailed = !active ? (sessions.find((s) => s.status === 'error') ?? null) : null;

  const knownCdns: string[] = (() => {
    if (!active) return [];
    const activeOrigin = extractOrigin(active.url);
    if (!activeOrigin) return [];
    const site = websites.find((w) => w.url === activeOrigin);
    return site?.cdns ?? [];
  })();

  async function handleClose() {
    if (!active) return;
    await browseSessionApi.closeSession(active.id).catch(console.error);
  }

  if (active) {
    return (
      <div class="captured-stack">
        <BrowserViewer session={active} onClose={handleClose} />
        <CandidatePanel candidates={active.candidates} sessionId={active.id} knownCdns={knownCdns} />
      </div>
    );
  }

  return (
    <>
      {lastFailed && <SessionErrorBanner session={lastFailed} />}
      <SessionForm onCreated={() => {}} />
    </>
  );
}

function SessionErrorBanner({ session }: { session: BrowseSession }) {
  return (
    <div class="session-error-banner">
      <span class="session-error-label">Last session failed</span>
      <span class="session-error-url">{session.url}</span>
      {session.error && <p class="session-error-msg">{session.error}</p>}
    </div>
  );
}
