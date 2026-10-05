export type Rule = {
  domain: string;
  action: 'block' | 'allow';
  includeSubdomains: boolean;
  updatedAt: number;
};
export type HistoryItem = {
  id: number;
  kind: string;
  domain: string;
  detail: string;
  createdAt: number;
};
export type Snapshot = {
  state:
    | 'off'
    | 'starting'
    | 'stopping'
    | 'active'
    | 'degraded'
    | 'failed'
    | 'interrupted';
  detail: string;
  rules: Rule[];
  history: HistoryItem[];
};
export type LinkResult = {
  domain: string;
  classification: 'unknown';
  action: 'block' | 'allow';
  matchedDomain: string | null;
  reason: string;
  checkedAt: number;
};
export const stateLabels: Record<Snapshot['state'], string> = {
  off: 'Protection is off',
  starting: 'Starting protection',
  stopping: 'Stopping protection',
  active: 'DNS filter is running',
  degraded: 'Connection needs attention',
  failed: 'Protection could not start',
  interrupted: 'Protection was interrupted',
};
