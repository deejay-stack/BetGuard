import { API_BASE_URL } from './config';
import type { HistoryItem, Rule } from '../state/types';

export type RouterSnapshot = {
  state:
    | 'off'
    | 'preview'
    | 'applying'
    | 'active'
    | 'degraded'
    | 'offline'
    | 'recovery_required'
    | 'restoring';
  detail: string;
  router: string | null;
  routerUrl: string | null;
  routerType: string | null;
  version: string | null;
  filterHost: string;
  filterPort: number;
  dnsRunning: boolean;
  mlReady: boolean;
  blocklistLoaded: boolean;
  enforcementVerified: boolean;
  preview: string | null;
  changes: {
    config: string;
    section: string;
    option: string;
    before: unknown;
    after: unknown;
  }[];
  firewallRule: unknown;
  clients: {
    ip: string;
    firstSeen: number;
    lastActivity: number;
    requests: number;
    blocked: number;
    warnings: number;
  }[];
  history: HistoryItem[];
  requests: number;
  allowed: number;
  blocked: number;
  warnings: number;
  errors: number;
};

const states = [
  'off',
  'preview',
  'applying',
  'active',
  'degraded',
  'offline',
  'recovery_required',
  'restoring',
];
export function readRouterSnapshot(value: unknown): RouterSnapshot {
  if (!value || typeof value !== 'object')
    throw new Error('Invalid router status');
  const row = value as RouterSnapshot;
  if (
    !states.includes(row.state) ||
    typeof row.detail !== 'string' ||
    typeof row.filterHost !== 'string' ||
    !Number.isInteger(row.filterPort) ||
    row.filterPort < 1 ||
    row.filterPort > 65535 ||
    ![
      row.dnsRunning,
      row.mlReady,
      row.blocklistLoaded,
      row.enforcementVerified,
    ].every(v => typeof v === 'boolean') ||
    ![row.requests, row.allowed, row.blocked, row.warnings, row.errors].every(
      v => Number.isSafeInteger(v) && v >= 0,
    ) ||
    !Array.isArray(row.clients) ||
    !Array.isArray(row.history) ||
    !Array.isArray(row.changes) ||
    row.clients.length > 128 ||
    row.history.length > 200 ||
    (row.state === 'active' &&
      (!row.enforcementVerified ||
        !row.dnsRunning ||
        !row.mlReady ||
        !row.blocklistLoaded ||
        !row.router)) ||
    row.clients.some(
      c =>
        typeof c.ip !== 'string' ||
        ![c.firstSeen, c.lastActivity, c.requests, c.blocked, c.warnings].every(
          v => Number.isSafeInteger(v) && v >= 0,
        ),
    ) ||
    row.history.some(
      e =>
        e.protection !== 'router' ||
        ![
          'router_allowed',
          'router_warning',
          'router_blocked',
          'router_error',
        ].includes(e.kind) ||
        !Number.isSafeInteger(e.id) ||
        !Number.isSafeInteger(e.createdAt) ||
        typeof e.domain !== 'string' ||
        typeof e.detail !== 'string' ||
        typeof e.clientIp !== 'string',
    )
  ) {
    throw new Error('Invalid router status');
  }
  return row;
}

export async function routerRequest(
  token: string,
  action: 'status' | 'connect' | 'apply' | 'verify' | 'stop' | 'policy',
  body?: unknown,
): Promise<unknown> {
  if (!API_BASE_URL || token.length < 32)
    throw new Error(
      'Enter the dedicated service administrator token. Configure the Router Protection service first.',
    );
  const controller = new AbortController();
  const timer = setTimeout(
    () => controller.abort(),
    action === 'status' || action === 'policy' ? 8000 : 90000,
  );
  try {
    const response = await fetch(`${API_BASE_URL}/v1/router/${action}`, {
      method: action === 'status' ? 'GET' : 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok)
      throw new Error(
        typeof result?.detail === 'string' && result.detail.length <= 500
          ? result.detail
          : 'Router service request failed.',
      );
    return result;
  } catch (error) {
    if (error instanceof Error && error.name !== 'AbortError') throw error;
    throw new Error(
      'The router action timed out. Refresh status before retrying; changes may still require restoration.',
    );
  } finally {
    clearTimeout(timer);
  }
}

export async function syncPhoneRules(token: string, rules: Rule[]) {
  const value = (await routerRequest(token, 'policy', { rules })) as {
    synced?: boolean;
    rules?: number;
  };
  if (value.synced !== true || value.rules !== rules.length)
    throw new Error('Phone rules were not acknowledged by the router service.');
}
