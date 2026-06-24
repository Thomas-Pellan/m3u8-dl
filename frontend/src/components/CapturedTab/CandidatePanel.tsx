import { useState } from 'preact/hooks';
import type { HlsCandidate } from '../../models/browse_session';
import { browseSessionApi } from '../../services/browseSessionApi';
import { CandidateCard } from './CandidateCard';

interface Props {
  candidates: HlsCandidate[];
  sessionId: string;
  knownCdns: string[];
}

export function CandidatePanel({ candidates, sessionId, knownCdns }: Props) {
  const [flushing, setFlushing] = useState(false);

  async function handleFlush() {
    setFlushing(true);
    try {
      await browseSessionApi.clearCandidates(sessionId);
    } finally {
      setFlushing(false);
    }
  }

  return (
    <div class="candidate-panel">
      <div class="candidate-panel-title">
        Intercepted playlists
        {candidates.length > 0 && <span class="candidate-count">{candidates.length}</span>}
        {candidates.length > 0 && (
          <button class="candidate-flush-btn" onClick={handleFlush} disabled={flushing}>
            {flushing ? 'Clearing…' : 'Clear'}
          </button>
        )}
      </div>
      {candidates.length === 0 ? (
        <p class="candidate-empty">
          No HLS playlists intercepted yet. Start the video playback in the browser viewer.
        </p>
      ) : (
        <ul class="candidate-list">
          {candidates.map((c) => (
            <CandidateCard key={c.url} candidate={c} sessionId={sessionId} knownCdns={knownCdns} />
          ))}
        </ul>
      )}
    </div>
  );
}
