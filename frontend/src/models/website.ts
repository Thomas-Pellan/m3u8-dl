export interface Website {
  id: number;
  url: string;
  name: string;
  rating: number;
  working: boolean;
  last_used_at: string;
  use_count: number;
  source: 'simple' | 'captured';
  cdns: string[];
}
