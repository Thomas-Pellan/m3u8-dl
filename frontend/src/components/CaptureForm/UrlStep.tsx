import type { FieldErrors } from '../../schemas/capture';

interface Props {
  url: string;
  onUrlChange: (url: string) => void;
  onFetch: () => void;
  onSkip: () => void;
  onClear: () => void;
  fetching: boolean;
  message: string;
  messageError: boolean;
  fieldErrors: FieldErrors;
}

export function UrlStep({
  url,
  onUrlChange,
  onFetch,
  onSkip,
  onClear,
  fetching,
  message,
  messageError,
  fieldErrors,
}: Props) {
  return (
    <>
      <label>
        Stream page URL <span class="req">*</span>
      </label>
      <div class="url-row">
        <input
          type="url"
          value={url}
          onInput={(e) => onUrlChange((e.target as HTMLInputElement).value)}
          placeholder="https://example.com/watch/movie"
          class={fieldErrors.url ? 'input-invalid' : ''}
        />
        <button type="button" class="btn-clear-url" onClick={onClear} title="Clear">
          ×
        </button>
        <button
          type="button"
          class="btn-fetch"
          onClick={onFetch}
          disabled={fetching || !url.trim()}
        >
          {fetching ? 'Fetching…' : 'Fetch names →'}
        </button>
      </div>
      {fieldErrors.url && <p class="field-error">{fieldErrors.url}</p>}
      {message && <p class={messageError ? 'msg-error' : 'msg-info'}>{message}</p>}
      <button type="button" class="btn-link" onClick={onSkip}>
        skip →
      </button>
    </>
  );
}
