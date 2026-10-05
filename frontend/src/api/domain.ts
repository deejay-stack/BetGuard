import { ApiError, requestJson } from './client';

export type DomainDecision = {
  domain: string;
  enforcement_action: 'ALLOW' | 'BLOCK';
  intervention: 'NONE' | 'WARN' | 'BLOCK';
  risk_status: 'trusted' | 'user_blocked' | 'verified_gambling' | 'high' | 'suspicious' | 'low';
  decision_source: 'user_allowlist' | 'user_blocklist' | 'verified_gambling_blocklist' | 'ml_high_risk' | 'ml_warning' | 'ml_low_risk';
  matched_domain: string | null;
  ml_score: number | null;
  cache_hit: boolean;
};

function normalized(hostname: string): string {
  const labels = hostname.split('.');
  if (hostname.length > 253 || labels.length < 2 || /^\d+$/.test(labels[labels.length - 1]) ||
      !labels.every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))) {
    throw new ApiError('invalid');
  }
  return hostname.replace(/^www\./, '');
}

export function validDecision(value: unknown, expected: string): value is DomainDecision {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const d = value as Record<string, unknown>;
  const policy: Record<string, [string, string, string]> = {
    user_allowlist: ['ALLOW', 'NONE', 'trusted'],
    user_blocklist: ['BLOCK', 'BLOCK', 'user_blocked'],
    verified_gambling_blocklist: ['BLOCK', 'BLOCK', 'verified_gambling'],
    ml_high_risk: ['BLOCK', 'BLOCK', 'high'],
    ml_warning: ['ALLOW', 'WARN', 'suspicious'],
    ml_low_risk: ['ALLOW', 'NONE', 'low'],
  };
  const rule = typeof d.decision_source === 'string' && Object.hasOwn(policy, d.decision_source)
    ? policy[d.decision_source] : undefined;
  if (!rule || d.domain !== expected || d.enforcement_action !== rule[0] ||
      d.intervention !== rule[1] || d.risk_status !== rule[2] || typeof d.cache_hit !== 'boolean') return false;
  if (typeof d.decision_source === 'string' && d.decision_source.startsWith('ml_')) {
    if (typeof d.ml_score !== 'number' || !Number.isFinite(d.ml_score) || d.ml_score < 0 || d.ml_score > 1) return false;
    return d.matched_domain === null;
  }
  return d.ml_score === null && typeof d.matched_domain === 'string' && !!d.matched_domain;
}

export async function checkDomain(hostname: string, signal: AbortSignal): Promise<DomainDecision> {
  if (signal.aborted) throw new ApiError('cancelled');
  const expected = normalized(hostname);
  const data = await requestJson('/v1/domain/check', signal, { domain: hostname });
  if (!data || typeof data !== 'object' || !('ok' in data) || data.ok !== true ||
      !('result' in data) || !validDecision(data.result, expected)) throw new ApiError('unavailable');
  return data.result;
}

export async function checkDomains(hostnames: string[], signal: AbortSignal): Promise<DomainDecision[]> {
  if (signal.aborted) throw new ApiError('cancelled');
  if (!hostnames.length || hostnames.length > 100) throw new ApiError('invalid');
  const expected = hostnames.map(normalized);
  const data = await requestJson('/v1/domain/check-batch', signal, { domains: hostnames });
  if (!data || typeof data !== 'object' || !('ok' in data) || data.ok !== true ||
      !('count' in data) || data.count !== hostnames.length || !('results' in data) ||
      !Array.isArray(data.results) || data.results.length !== hostnames.length ||
      !data.results.every((result, i) => validDecision(result, expected[i]))) throw new ApiError('unavailable');
  return data.results;
}
