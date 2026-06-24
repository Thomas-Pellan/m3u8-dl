import { useState } from 'preact/hooks';
import { useWebsites } from '../../hooks/useWebsites';
import type { Website } from '../../models/website';
import { websiteApi } from '../../services/websiteApi';
import { formatShortDateTime } from '../../utils/date';

interface Props {
  onNavigateToCaptured: () => void;
}

export function WebsitesTab({ onNavigateToCaptured }: Props) {
  const websites = useWebsites();
  const [notice, setNotice] = useState('');
  const [noticeError, setNoticeError] = useState(false);
  const [flushing, setFlushing] = useState(false);
  const [flushingCdnsFor, setFlushingCdnsFor] = useState<number | null>(null);

  function showNotice(msg: string, isError = false) {
    setNotice(msg);
    setNoticeError(isError);
    setTimeout(() => setNotice(''), 5000);
  }

  async function handleRating(website: Website, rating: number) {
    try {
      await websiteApi.updateRating(website.id, rating);
    } catch (err) {
      showNotice(`Error: ${(err as Error).message}`, true);
    }
  }

  async function handleToggleWorking(website: Website) {
    try {
      await websiteApi.setWorking(website.id, !website.working);
    } catch (err) {
      showNotice(`Error: ${(err as Error).message}`, true);
    }
  }

  async function handleFlush() {
    setFlushing(true);
    try {
      const { deleted } = await websiteApi.flushNotWorking();
      showNotice(`Removed ${deleted} broken website${deleted !== 1 ? 's' : ''}.`);
    } catch (err) {
      showNotice(`Error: ${(err as Error).message}`, true);
    } finally {
      setFlushing(false);
    }
  }

  async function handleOpenSession(website: Website) {
    try {
      const result = await websiteApi.openSession(website.id);
      if (result.action === 'created') {
        onNavigateToCaptured();
      } else {
        showNotice(result.message);
      }
    } catch (err) {
      showNotice(`Error: ${(err as Error).message}`, true);
    }
  }

  async function handleFlushCdns(website: Website) {
    setFlushingCdnsFor(website.id);
    try {
      const { flushed } = await websiteApi.flushCdns(website.id);
      showNotice(`Flushed ${flushed} CDN${flushed !== 1 ? 's' : ''} for ${website.name}.`);
    } catch (err) {
      showNotice(`Error: ${(err as Error).message}`, true);
    } finally {
      setFlushingCdnsFor(null);
    }
  }

  async function handleDelete(website: Website) {
    try {
      await websiteApi.delete(website.id);
    } catch (err) {
      showNotice(`Error: ${(err as Error).message}`, true);
    }
  }

  const notWorkingCount = websites.filter((w) => !w.working).length;

  return (
    <div class="card">
      <div class="websites-header">
        <div class="card-title">Websites</div>
        {notWorkingCount > 0 && (
          <button class="btn-flush" onClick={handleFlush} disabled={flushing}>
            {flushing ? 'Flushing…' : `Flush broken (${notWorkingCount})`}
          </button>
        )}
      </div>

      {notice && <p class={noticeError ? 'msg-error' : 'msg-info'}>{notice}</p>}

      {websites.length === 0 ? (
        <p class="websites-empty">
          No websites recorded yet. Start a download from Simple or Captured mode to see history
          here.
        </p>
      ) : (
        <div class="websites-list">
          {websites.map((website) => (
            <WebsiteRow
              key={website.id}
              website={website}
              onRating={handleRating}
              onToggleWorking={handleToggleWorking}
              onFlushCdns={handleFlushCdns}
              flushingCdns={flushingCdnsFor === website.id}
              onOpenSession={handleOpenSession}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface RowProps {
  website: Website;
  onRating: (w: Website, r: number) => void;
  onToggleWorking: (w: Website) => void;
  onFlushCdns: (w: Website) => void;
  flushingCdns: boolean;
  onOpenSession: (w: Website) => void;
  onDelete: (w: Website) => void;
}

function WebsiteRow({
  website,
  onRating,
  onToggleWorking,
  onFlushCdns,
  flushingCdns,
  onOpenSession,
  onDelete,
}: RowProps) {
  return (
    <div class={`website-row${website.working ? '' : ' website-row--broken'}`}>
      <div class="website-row-top">
        <a
          class="website-name"
          href={website.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {website.name}
        </a>
        <span class={`website-source website-source--${website.source}`}>{website.source}</span>
        <span class="website-count" title="Times used">{website.use_count}×</span>
        <span class="website-date">{formatShortDateTime(website.last_used_at)}</span>
      </div>

      <div class="website-row-bottom">
        <StarRating rating={website.rating} onChange={(r) => onRating(website, r)} />

        <button
          class={`website-working-btn${website.working ? ' website-working-btn--ok' : ' website-working-btn--nok'}`}
          onClick={() => onToggleWorking(website)}
          title="Toggle working status"
        >
          {website.working ? '✓ Works' : '✗ Broken'}
        </button>

        {website.cdns.length > 0 && (
          <span class="website-cdn-info">
            <span class="website-cdn-count">{website.cdns.length} CDN{website.cdns.length !== 1 ? 's' : ''}</span>
            <button
              class="website-cdn-flush-btn"
              onClick={() => onFlushCdns(website)}
              disabled={flushingCdns}
              title="Remove all learned CDNs for this website"
            >
              {flushingCdns ? '…' : 'flush'}
            </button>
          </span>
        )}

        <button class="website-open-btn" onClick={() => onOpenSession(website)}>
          Captured mode →
        </button>

        <button class="website-del-btn" onClick={() => onDelete(website)} title="Remove">
          ✕
        </button>
      </div>
    </div>
  );
}

interface StarProps {
  rating: number;
  onChange: (r: number) => void;
}

function StarRating({ rating, onChange }: StarProps) {
  return (
    <div class="star-rating">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          class={`star-btn${n <= rating ? ' star-btn--on' : ''}`}
          onClick={() => onChange(n === rating ? 0 : n)}
          title={`${n} star${n !== 1 ? 's' : ''}`}
        >
          ★
        </button>
      ))}
    </div>
  );
}
