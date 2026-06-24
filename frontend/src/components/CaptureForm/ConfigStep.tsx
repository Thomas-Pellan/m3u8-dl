import type { FieldErrors } from '../../schemas/capture';

interface Props {
  url: string;
  candidates: string[];
  outputName: string;
  onOutputNameChange: (name: string) => void;
  mode: string;
  onModeChange: (mode: string) => void;
  quality: string;
  onQualityChange: (quality: string) => void;
  parallel: number;
  onParallelChange: (n: number) => void;
  scheduledAt: string;
  onScheduledAtChange: (s: string) => void;
  onBack: () => void;
  onSubmit: (e: Event) => void;
  submitting: boolean;
  message: string;
  messageError: boolean;
  fieldErrors: FieldErrors;
}

export function ConfigStep({
  url,
  candidates,
  outputName,
  onOutputNameChange,
  mode,
  onModeChange,
  quality,
  onQualityChange,
  parallel,
  onParallelChange,
  scheduledAt,
  onScheduledAtChange,
  onBack,
  onSubmit,
  submitting,
  message,
  messageError,
  fieldErrors,
}: Props) {
  return (
    <form onSubmit={onSubmit}>
      <div class="url-confirm">
        <span>{url}</span>
        <button type="button" class="btn-link" onClick={onBack}>
          ↩ change URL
        </button>
      </div>

      <label>
        Output filename (without .mp4) <span class="req">*</span>
      </label>
      <input
        type="text"
        value={outputName}
        onInput={(e) => onOutputNameChange((e.target as HTMLInputElement).value)}
        placeholder="interstellar-2014"
        list="name-list"
        autocomplete="off"
        class={fieldErrors.output_name ? 'input-invalid' : ''}
      />
      {fieldErrors.output_name && <p class="field-error">{fieldErrors.output_name}</p>}
      <datalist id="name-list">
        {candidates.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>

      {candidates.length > 0 && (
        <div class="name-hints">
          {candidates.map((c) => (
            <button
              key={c}
              type="button"
              class={`hint-chip${c === outputName ? ' hint-active' : ''}`}
              onClick={() => onOutputNameChange(c)}
            >
              {c}
            </button>
          ))}
        </div>
      )}

      <div class="row">
        <div>
          <label>Capture mode</label>
          <select
            value={mode}
            onChange={(e) => onModeChange((e.target as HTMLSelectElement).value)}
          >
            <option value="auto">auto</option>
            <option value="direct">direct</option>
          </select>
        </div>
        <div>
          <label>Quality</label>
          <select
            value={quality}
            onChange={(e) => onQualityChange((e.target as HTMLSelectElement).value)}
          >
            <option value="best">best</option>
            <option value="worst">worst</option>
          </select>
        </div>
        <div>
          <label>
            Parallel downloads
            {fieldErrors.parallel && <span class="field-error-inline">{fieldErrors.parallel}</span>}
          </label>
          <input
            type="number"
            value={parallel}
            min={1}
            max={16}
            onInput={(e) => onParallelChange(Number((e.target as HTMLInputElement).value))}
            class={fieldErrors.parallel ? 'input-invalid' : ''}
          />
        </div>
      </div>

      <label>
        Schedule for <span class="opt-label">(optional — leave blank to run immediately)</span>
      </label>
      <input
        type="datetime-local"
        value={scheduledAt}
        onInput={(e) => onScheduledAtChange((e.target as HTMLInputElement).value)}
        class={fieldErrors.scheduled_at ? 'input-invalid' : ''}
      />
      {fieldErrors.scheduled_at && <p class="field-error">{fieldErrors.scheduled_at}</p>}

      <button class="btn" type="submit" disabled={submitting}>
        {submitting ? 'Submitting…' : 'Start capture'}
      </button>
      {message && <p class={messageError ? 'msg-error' : 'msg-ok'}>{message}</p>}
    </form>
  );
}
