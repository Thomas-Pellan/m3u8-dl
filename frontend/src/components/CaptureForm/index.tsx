import { useState } from 'preact/hooks';
import type { ZodIssue } from 'zod';
import { api } from '../../services/api';
import { type FieldErrors, configSchema, urlSchema } from '../../schemas/capture';
import { ConfigStep } from './ConfigStep';
import { UrlStep } from './UrlStep';

type Step = 'url' | 'config';

export function CaptureForm() {
  const [step, setStep] = useState<Step>('url');
  const [url, setUrl] = useState('');
  const [candidates, setCandidates] = useState<string[]>([]);
  const [outputName, setOutputName] = useState('');
  const [mode, setMode] = useState('auto');
  const [quality, setQuality] = useState('best');
  const [parallel, setParallel] = useState(4);
  const [scheduledAt, setScheduledAt] = useState('');
  const [fetchMsg, setFetchMsg] = useState('');
  const [fetchError, setFetchError] = useState(false);
  const [fetching, setFetching] = useState(false);
  const [submitMsg, setSubmitMsg] = useState('');
  const [submitError, setSubmitError] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [urlErrors, setUrlErrors] = useState<FieldErrors>({});
  const [configErrors, setConfigErrors] = useState<FieldErrors>({});

  function reset() {
    setStep('url');
    setOutputName('');
    setCandidates([]);
    setScheduledAt('');
    setSubmitMsg('');
    setFetchMsg('');
    setFetchError(false);
    setUrlErrors({});
    setConfigErrors({});
  }

  function goToConfig(names: string[]) {
    setCandidates(names);
    setOutputName(names[0] ?? '');
    setStep('config');
  }

  function parseIssues(issues: ZodIssue[]): FieldErrors {
    const errs: FieldErrors = {};
    for (const issue of issues) {
      const key = String(issue.path[0] ?? '_');
      if (!errs[key]) errs[key] = issue.message;
    }
    return errs;
  }

  async function fetchNames() {
    const result = urlSchema.safeParse({ url: url.trim() });
    if (!result.success) {
      setUrlErrors(parseIssues(result.error.issues));
      return;
    }
    setUrlErrors({});
    setFetching(true);
    setFetchError(false);
    setFetchMsg('Loading page and scraping title…');
    try {
      const { candidates: names } = await api.suggestNames(url.trim());
      goToConfig(names);
    } catch (err) {
      setFetchError(true);
      setFetchMsg(`Error: ${(err as Error).message}`);
    } finally {
      setFetching(false);
    }
  }

  function skipToConfig() {
    const result = urlSchema.safeParse({ url: url.trim() });
    if (!result.success) {
      setUrlErrors(parseIssues(result.error.issues));
      return;
    }
    setUrlErrors({});
    goToConfig([]);
  }

  async function submit(e: Event) {
    e.preventDefault();
    const result = configSchema.safeParse({
      output_name: outputName,
      mode,
      quality,
      parallel,
      scheduled_at: scheduledAt || undefined,
    });
    if (!result.success) {
      setConfigErrors(parseIssues(result.error.issues));
      return;
    }
    setConfigErrors({});
    setSubmitting(true);
    setSubmitError(false);
    setSubmitMsg('Submitting…');
    try {
      const fd = new FormData();
      fd.append('url', url);
      fd.append('output_name', outputName);
      fd.append('mode', mode);
      fd.append('quality', quality);
      fd.append('parallel', String(parallel));
      if (scheduledAt) fd.append('scheduled_at', new Date(scheduledAt).toISOString());
      const { job_id } = await api.startCapture(fd);
      setSubmitMsg(scheduledAt ? `Job ${job_id} scheduled.` : `Job ${job_id} queued.`);
      setTimeout(reset, 1200);
    } catch (err) {
      setSubmitError(true);
      setSubmitMsg(`Error: ${(err as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div class="card">
      <div class="card-title">New capture</div>
      {step === 'url' ? (
        <UrlStep
          url={url}
          onUrlChange={(v) => {
            setUrl(v);
            if (urlErrors.url) setUrlErrors({});
          }}
          onFetch={fetchNames}
          onSkip={skipToConfig}
          onClear={reset}
          fetching={fetching}
          message={fetchMsg}
          messageError={fetchError}
          fieldErrors={urlErrors}
        />
      ) : (
        <ConfigStep
          url={url}
          candidates={candidates}
          outputName={outputName}
          onOutputNameChange={(v) => {
            setOutputName(v);
            if (configErrors.output_name)
              setConfigErrors((p) => ({ ...p, output_name: undefined }));
          }}
          mode={mode}
          onModeChange={setMode}
          quality={quality}
          onQualityChange={setQuality}
          parallel={parallel}
          onParallelChange={(n) => {
            setParallel(n);
            if (configErrors.parallel) setConfigErrors((p) => ({ ...p, parallel: undefined }));
          }}
          scheduledAt={scheduledAt}
          onScheduledAtChange={(v) => {
            setScheduledAt(v);
            if (configErrors.scheduled_at)
              setConfigErrors((p) => ({ ...p, scheduled_at: undefined }));
          }}
          onBack={reset}
          onSubmit={submit}
          submitting={submitting}
          message={submitMsg}
          messageError={submitError}
          fieldErrors={configErrors}
        />
      )}
    </div>
  );
}
