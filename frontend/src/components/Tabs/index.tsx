import { useState } from 'preact/hooks';
import type { ComponentChildren } from 'preact';

export interface TabDef {
  id: string;
  label: string;
  content: ComponentChildren;
}

interface Props {
  tabs: TabDef[];
  defaultTab?: string;
  activeTab?: string;
  onTabChange?: (id: string) => void;
}

export function Tabs({ tabs, defaultTab, activeTab: controlledTab, onTabChange }: Props) {
  const [internalActive, setInternalActive] = useState(defaultTab ?? tabs[0]?.id ?? '');
  const active = controlledTab ?? internalActive;

  function setActive(id: string) {
    if (controlledTab === undefined) setInternalActive(id);
    onTabChange?.(id);
  }

  const current = tabs.find((t) => t.id === active);

  return (
    <>
      <nav class="tab-bar" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            class={`tab-btn${active === t.id ? ' tab-active' : ''}`}
            aria-selected={active === t.id}
            onClick={() => setActive(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <div class="tab-content">{current?.content}</div>
    </>
  );
}
