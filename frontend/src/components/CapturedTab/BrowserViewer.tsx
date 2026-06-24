import { useEffect, useRef, useState } from 'preact/hooks';
import type { BrowseSession, SessionDownload } from '../../models/browse_session';
import { browseSessionApi } from '../../services/browseSessionApi';
import { useSessionScreen } from '../../hooks/useSessionScreen';

interface Props {
  session: BrowseSession;
  onClose: () => void;
}

export function BrowserViewer({ session, onClose }: Props) {
  const frame = useSessionScreen(session.status === 'active' ? session.id : null);
  const [navUrl, setNavUrl] = useState('');
  const [clicking, setClicking] = useState(false);
  const [confirmKill, setConfirmKill] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const screenRef = useRef<HTMLDivElement>(null);
  const resizeDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Tracks whether we've synced the viewport at least once for this session
  const sentInitialRef = useRef(false);

  const activeDownloads = session.downloads.filter(
    (d) => d.status === 'running' || d.status === 'assembling',
  );

  function sendViewportResize() {
    const el = screenRef.current;
    if (!el || session.status !== 'active') return;
    const { width, height } = el.getBoundingClientRect();
    // Skip until the div has grown beyond its CSS min-height placeholder
    if (width < 100 || height < 100) return;
    browseSessionApi
      .sendAction(session.id, { type: 'resize', width: Math.round(width), height: Math.round(height) })
      .catch(() => {});
  }

  // Send the first resize once the initial screenshot has loaded — that's when
  // the div gets its real height (img width:100% / height:auto expands the container).
  useEffect(() => {
    if (!frame || sentInitialRef.current) return;
    sentInitialRef.current = true;
    // One tick so the browser paints the img and getBoundingClientRect is accurate
    const t = setTimeout(sendViewportResize, 50);
    return () => clearTimeout(t);
  }, [!!frame]);

  // Track subsequent container/window resizes (debounced)
  useEffect(() => {
    const el = screenRef.current;
    if (!el || session.status !== 'active') return;
    const ro = new ResizeObserver(() => {
      if (!sentInitialRef.current) return; // wait for first frame
      if (resizeDebounce.current) clearTimeout(resizeDebounce.current);
      resizeDebounce.current = setTimeout(sendViewportResize, 400);
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (resizeDebounce.current) clearTimeout(resizeDebounce.current);
    };
  }, [session.id, session.status]);

  async function handleImgClick(e: MouseEvent) {
    if (!imgRef.current || session.status !== 'active') return;
    const rect = imgRef.current.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setClicking(true);
    try {
      await browseSessionApi.sendAction(session.id, { type: 'click', x, y });
    } finally {
      setClicking(false);
    }
  }

  async function navigate(e: Event) {
    e.preventDefault();
    if (!navUrl.trim()) return;
    await browseSessionApi.sendAction(session.id, { type: 'navigate', url: navUrl.trim() });
    setNavUrl('');
  }

  async function goBack() {
    await browseSessionApi.sendAction(session.id, { type: 'back' });
  }

  async function scroll(delta: number) {
    await browseSessionApi.sendAction(session.id, { type: 'scroll', delta_y: delta });
  }

  async function handleForceClose() {
    await browseSessionApi.forceCloseSession(session.id).catch(console.error);
    setConfirmKill(false);
  }

  return (
    <div class="browser-viewer">
      <div class="viewer-toolbar">
        <span class="viewer-url" title={session.url}>
          {session.url}
        </span>
        {session.close_when_done ? (
          <div class="viewer-kill-row">
            {confirmKill ? (
              <>
                <span class="viewer-kill-warning">Force close will cancel downloads</span>
                <button class="act-btn force-close-btn" onClick={handleForceClose}>
                  Confirm kill
                </button>
                <button class="act-btn scroll-btn" onClick={() => setConfirmKill(false)}>
                  Cancel
                </button>
              </>
            ) : (
              <button class="act-btn force-close-btn" onClick={() => setConfirmKill(true)}>
                Force close
              </button>
            )}
          </div>
        ) : (
          <button class="act-btn close-session-btn" onClick={onClose}>
            Close session
          </button>
        )}
      </div>

      {session.close_when_done && activeDownloads.length > 0 && (
        <div class="viewer-close-deferred">
          <span class="viewer-close-deferred-label">Session will close after download —</span>
          <div class="viewer-close-deferred-dls">
            {activeDownloads.map((dl) => (
              <DeferredDownloadLine key={dl.id} dl={dl} />
            ))}
          </div>
        </div>
      )}

      {session.error && session.status === 'active' && (
        <div class="viewer-nav-warning">
          <span class="viewer-nav-warning-label">Navigation failed —</span>
          {session.error}
        </div>
      )}

      <div class="viewer-screen" ref={screenRef}>
        {session.status === 'opening' && <div class="viewer-placeholder">Opening browser…</div>}
        {session.status === 'active' && !frame && (
          <div class="viewer-placeholder">Waiting for first frame…</div>
        )}
        {frame && (
          <img
            ref={imgRef}
            src={`data:image/jpeg;base64,${frame}`}
            alt="Browser viewport"
            class={`viewer-img${clicking ? ' viewer-clicking' : ''}`}
            onClick={handleImgClick}
          />
        )}
        {session.status === 'error' && (
          <div class="viewer-error">
            <span class="viewer-error-label">Session error</span>
            {session.error && <p class="viewer-error-msg">{session.error}</p>}
          </div>
        )}
      </div>

      {session.status === 'active' && (
        <div class="viewer-controls">
          <form class="viewer-nav" onSubmit={navigate}>
            <input
              type="url"
              class="viewer-nav-input"
              value={navUrl}
              onInput={(e) => setNavUrl((e.target as HTMLInputElement).value)}
              placeholder="Navigate to URL…"
            />
            <button type="submit" class="act-btn nav-btn" disabled={!navUrl.trim()}>
              Go
            </button>
          </form>
          <div class="viewer-scroll-btns">
            <button class="act-btn scroll-btn" onClick={goBack}>
              ← Back
            </button>
            <button class="act-btn scroll-btn" onClick={() => scroll(-300)}>
              ↑ Scroll up
            </button>
            <button class="act-btn scroll-btn" onClick={() => scroll(300)}>
              ↓ Scroll down
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function DeferredDownloadLine({ dl }: { dl: SessionDownload }) {
  const label = dl.status === 'assembling' ? 'assembling…' : `${dl.progress}%`;
  return (
    <span class="viewer-close-deferred-dl">
      <span class="viewer-close-deferred-name">{dl.output_name}</span>
      <span class="viewer-close-deferred-pct">{label}</span>
    </span>
  );
}
