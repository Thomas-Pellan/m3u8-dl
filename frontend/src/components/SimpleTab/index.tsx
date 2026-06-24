import type { Job } from '../../models/job';
import { CaptureForm } from '../CaptureForm';
import { JobsPanel } from '../JobsPanel';
import { ScheduledPanel } from '../ScheduledPanel';

interface Props {
  jobs: Job[];
  scheduled: Job[];
}

export function SimpleTab({ jobs, scheduled }: Props) {
  return (
    <>
      <CaptureForm />
      {scheduled.length > 0 && <ScheduledPanel jobs={scheduled} />}
      <JobsPanel jobs={jobs} />
    </>
  );
}
