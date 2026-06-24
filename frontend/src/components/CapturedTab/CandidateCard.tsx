import { useState } from 'preact/hooks';
import type { AudioTrack, HlsCandidate, HlsStream, SubtitleTrack } from '../../models/browse_session';
import { browseSessionApi } from '../../services/browseSessionApi';
import { formatDuration } from '../../utils/duration';

interface Props {
  candidate: HlsCandidate;
  sessionId: string;
  knownCdns: string[];
}

interface TitleSuggestion {
  title: string;
  filename: string;
}

function extractOrigin(url: string): string | null {
  try {
    const u = new URL(url);
    return `${u.protocol}//${u.host}`;
  } catch {
    return null;
  }
}

export function CandidateCard({ candidate: c, sessionId, knownCdns }: Props) {
  const cdnOrigin = extractOrigin(c.url);
  const isKnownCdn = cdnOrigin !== null && knownCdns.includes(cdnOrigin);
  const [open, setOpen] = useState(false);
  const [outputName, setOutputName] = useState('');
  const [quality, setQuality] = useState('best');
  const [parallel, setParallel] = useState(4);
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState('');
  const [msgError, setMsgError] = useState(false);

  const [suggestions, setSuggestions] = useState<TitleSuggestion[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  async function openForm() {
    setOpen(true);
    setLoadingSuggestions(true);
    setSuggestions([]);
    try {
      const { titles } = await browseSessionApi.getPageTitles(sessionId);
      setSuggestions(titles);
      if (titles.length > 0 && !outputName) {
        setOutputName(titles[0].filename);
      }
    } catch {
      // non-fatal — user can type manually
    } finally {
      setLoadingSuggestions(false);
    }
  }

  async function download(e: Event) {
    e.preventDefault();
    if (!outputName.trim()) return;
    setSubmitting(true);
    setMsg('');
    try {
      const { dl_id } = await browseSessionApi.startSessionDownload(sessionId, {
        url: c.url,
        output_name: outputName.trim(),
        quality,
        parallel,
      });
      setMsg(`Download ${dl_id} started — progress visible in the Sessions tab.`);
      setMsgError(false);
      setOpen(false);
    } catch (err) {
      setMsg((err as Error).message);
      setMsgError(true);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <li class={`candidate-card${isKnownCdn ? ' candidate-card--known-cdn' : ''}`}>
      {isKnownCdn && <span class="candidate-cdn-badge">known CDN</span>}
      <div class="candidate-header">
        <span class={`candidate-type-badge ${c.type}`}>{c.type}</span>
        <span class="candidate-url" title={c.url}>
          {c.url}
        </span>
      </div>

      <div class="candidate-meta">
        {c.type === 'media' && c.duration_s != null && (
          <span class="candidate-duration">{formatDuration(c.duration_s)}</span>
        )}
        {c.type === 'master' && c.streams.length > 0 && (
          <div class="stream-tags">
            {c.streams.map((s, i) => (
              <StreamTag key={i} stream={s} />
            ))}
          </div>
        )}
        {c.type === 'master' && c.streams.length === 0 && (
          <span class="candidate-duration">master playlist</span>
        )}
        {c.audio_tracks.length > 0 && (
          <div class="meta-track-row">
            <span class="meta-track-label">Audio</span>
            <div class="meta-track-chips">
              {c.audio_tracks.map((t, i) => (
                <AudioChip key={i} track={t} />
              ))}
            </div>
          </div>
        )}
        {c.subtitle_tracks.length > 0 && (
          <div class="meta-track-row">
            <span class="meta-track-label">Subs</span>
            <div class="meta-track-chips">
              {c.subtitle_tracks.map((t, i) => (
                <SubtitleChip key={i} track={t} />
              ))}
            </div>
          </div>
        )}
      </div>

      {msg && !open && <p class={msgError ? 'msg-error' : 'msg-ok'}>{msg}</p>}

      {open ? (
        <form class="download-form" onSubmit={download}>
          <label>Output filename (without .mp4)</label>
          <input
            type="text"
            value={outputName}
            onInput={(e) => setOutputName((e.target as HTMLInputElement).value)}
            placeholder="movie-title-2024"
            required
          />
          {(loadingSuggestions || suggestions.length > 0) && (
            <div class="title-suggestions">
              {loadingSuggestions ? (
                <span class="title-suggestions-loading">Scraping page titles…</span>
              ) : (
                suggestions.map((s) => (
                  <button
                    key={s.filename}
                    type="button"
                    class="title-suggestion-btn"
                    onClick={() => setOutputName(s.filename)}
                    title={s.title}
                  >
                    {s.title}
                  </button>
                ))
              )}
            </div>
          )}
          <div class="download-form-row">
            <div>
              <label>Quality</label>
              <select
                value={quality}
                onChange={(e) => setQuality((e.target as HTMLSelectElement).value)}
              >
                <option value="best">best</option>
                <option value="worst">worst</option>
              </select>
            </div>
            <div>
              <label>Parallel</label>
              <input
                type="number"
                value={parallel}
                min={1}
                max={16}
                onInput={(e) => setParallel(Number((e.target as HTMLInputElement).value))}
              />
            </div>
          </div>
          <div class="download-form-actions">
            <button
              class="act-btn confirm-download-btn"
              type="submit"
              disabled={submitting || !outputName.trim()}
            >
              {submitting ? 'Starting…' : 'Download via session'}
            </button>
            <button
              class="act-btn abort-reschedule-btn"
              type="button"
              onClick={() => setOpen(false)}
            >
              Cancel
            </button>
          </div>
          {msg && <p class={msgError ? 'msg-error' : 'msg-ok'}>{msg}</p>}
        </form>
      ) : (
        <button class="act-btn download-btn" onClick={openForm}>
          Download →
        </button>
      )}
    </li>
  );
}

function StreamTag({ stream: s }: { stream: HlsStream }) {
  const parts: string[] = [];
  if (s.resolution) parts.push(s.resolution);
  if (s.frame_rate) parts.push(`${Math.round(s.frame_rate)}fps`);
  if (s.video_range && s.video_range !== 'SDR') parts.push(s.video_range);
  parts.push(`${Math.round(s.bandwidth / 1000)} kbps`);
  return <span class="stream-tag">{parts.join(' · ')}</span>;
}

function AudioChip({ track: t }: { track: AudioTrack }) {
  return (
    <span class={`meta-chip meta-chip--audio${t.default ? ' meta-chip--default' : ''}`}>
      {t.name}
      {t.language && t.language !== t.name && (
        <span class="meta-chip-lang">{t.language}</span>
      )}
      {t.default && <span class="meta-chip-star">★</span>}
    </span>
  );
}

function SubtitleChip({ track: t }: { track: SubtitleTrack }) {
  return (
    <span class={`meta-chip meta-chip--sub${t.forced ? ' meta-chip--forced' : ''}`}>
      {t.name}
      {t.language && t.language !== t.name && (
        <span class="meta-chip-lang">{t.language}</span>
      )}
      {t.forced && <span class="meta-chip-forced">forced</span>}
    </span>
  );
}
