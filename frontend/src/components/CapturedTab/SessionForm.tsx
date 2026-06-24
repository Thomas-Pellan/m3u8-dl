import { useState } from 'preact/hooks';
import { z } from 'zod';
import { browseSessionApi } from '../../services/browseSessionApi';

const schema = z.object({ url: z.string().min(1, 'URL is required').url('Must be a valid URL') });

interface Props {
  onCreated: (sessionId: string) => void;
}

export function SessionForm({ onCreated }: Props) {
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const [urlError, setUrlError] = useState('');
  const [loading, setLoading] = useState(false);
  const [flushing, setFlushing] = useState(false);
  const [flushed, setFlushed] = useState(false);

  async function submit(e: Event) {
    e.preventDefault();
    const result = schema.safeParse({ url: url.trim() });
    if (!result.success) {
      setUrlError(result.error.issues[0]?.message ?? 'Invalid URL');
      return;
    }
    setUrlError('');
    setError('');
    setLoading(true);
    try {
      const { session_id } = await browseSessionApi.createSession(url.trim());
      onCreated(session_id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function handleFlush(e: Event) {
    e.preventDefault();
    setFlushing(true);
    setFlushed(false);
    try {
      await browseSessionApi.flushProfile();
      setFlushed(true);
      setTimeout(() => setFlushed(false), 3000);
    } catch {
      // ignore
    } finally {
      setFlushing(false);
    }
  }

  return (
    <div class="card">
      <div class="card-title">Open browser session</div>
      <form onSubmit={submit}>
        <label>
          Page URL <span class="req">*</span>
        </label>
        <input
          type="url"
          value={url}
          onInput={(e) => {
            setUrl((e.target as HTMLInputElement).value);
            if (urlError) setUrlError('');
          }}
          placeholder="https://example.com/watch/movie"
          class={urlError ? 'input-invalid' : ''}
        />
        {urlError && <p class="field-error">{urlError}</p>}
        <p class="session-hint">
          A headless browser will open the page. Interact with it from the viewer to trigger stream
          playback — the backend will intercept any HLS playlists automatically.
        </p>
        <button class="btn" type="submit" disabled={loading}>
          {loading ? 'Opening browser…' : 'Open browser →'}
        </button>
        {error && <p class="msg-error">{error}</p>}
      </form>
      <div class="profile-flush">
        <button class="flush-btn" type="button" onClick={handleFlush} disabled={flushing}>
          {flushing ? 'Resetting…' : flushed ? 'Profile reset ✓' : 'Reset browser profile'}
        </button>
        <p class="flush-hint">
          Clears saved cookies and site data. Use this if a site starts detecting the browser.
        </p>
      </div>
    </div>
  );
}
