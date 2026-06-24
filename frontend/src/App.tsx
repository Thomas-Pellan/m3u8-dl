import { useState } from 'preact/hooks';
import { CapturedTab } from './components/CapturedTab';
import { SessionsTab } from './components/SessionsTab';
import { SimpleTab } from './components/SimpleTab';
import { Tabs } from './components/Tabs';
import { WebsitesTab } from './components/WebsitesTab';
import { useJobs } from './hooks/useJobs';

export function App() {
  const [activeTab, setActiveTab] = useState('simple');
  const jobs = [...useJobs()].reverse();
  const scheduled = jobs.filter((j) => j.scheduled_at !== null);
  const regular = jobs.filter((j) => j.scheduled_at === null);

  return (
    <div class="wrap">
      <h1>m3u8-dl</h1>
      <p class="sub">HLS stream downloader — headless browser mode</p>
      <Tabs
        activeTab={activeTab}
        onTabChange={setActiveTab}
        tabs={[
          {
            id: 'simple',
            label: 'Simple',
            content: <SimpleTab jobs={regular} scheduled={scheduled} />,
          },
          { id: 'captured', label: 'Captured', content: <CapturedTab /> },
          { id: 'sessions', label: 'Sessions', content: <SessionsTab /> },
          {
            id: 'websites',
            label: 'Websites',
            content: <WebsitesTab onNavigateToCaptured={() => setActiveTab('captured')} />,
          },
        ]}
      />
    </div>
  );
}
