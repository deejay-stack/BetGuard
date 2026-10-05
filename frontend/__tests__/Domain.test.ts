import { checkDomain, checkDomains, validDecision } from '../src/api/domain';
import { ApiError } from '../src/api/client';

const warning = {
  domain: 'microsoft.com', enforcement_action: 'ALLOW', intervention: 'WARN',
  decision_source: 'ml_warning', risk_status: 'suspicious',
  ml_score: 0.58, matched_domain: null, cache_hit: false,
};
const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

test('warning keeps ALLOW and uses the existing API client', async () => {
  globalThis.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, result: warning }) });
  expect(await checkDomain('microsoft.com', new AbortController().signal)).toEqual(warning);
  expect(fetch).toHaveBeenCalledWith('http://127.0.0.1:8000/v1/domain/check', expect.objectContaining({ body: JSON.stringify({ domain: 'microsoft.com' }) }));
});

test('www normalization validates the response without sending URL paths', async () => {
  const block = { domain: 'stake.com', enforcement_action: 'BLOCK', intervention: 'BLOCK', risk_status: 'verified_gambling', decision_source: 'verified_gambling_blocklist', matched_domain: 'stake.com', ml_score: null, cache_hit: true };
  globalThis.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, result: block }) });
  expect(await checkDomain('www.stake.com', new AbortController().signal)).toEqual(block);
  await expect(checkDomain('https://stake.com/private?secret=x', new AbortController().signal)).rejects.toEqual(new ApiError('invalid'));
  expect(fetch).toHaveBeenCalledTimes(1);
});

test.each([
  { ...warning, enforcement_action: 'BLOCK' },
  { ...warning, intervention: 'BLOCK' },
  { ...warning, ml_score: NaN },
  { ...warning, ml_score: null },
  { ...warning, decision_source: 'toString' },
  { ...warning, domain: 'another.com' },
])('malformed decisions are rejected', value => {
  expect(validDecision(value, 'microsoft.com')).toBe(false);
});

test('503 never produces an ALLOW or BLOCK', async () => {
  globalThis.fetch = jest.fn().mockResolvedValue({ ok: false, status: 503 });
  await expect(checkDomain('microsoft.com', new AbortController().signal)).rejects.toEqual(new ApiError('unavailable'));
});

test('batch is bounded and preserves order', async () => {
  globalThis.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true, count: 1, results: [warning] }) });
  expect(await checkDomains(['microsoft.com'], new AbortController().signal)).toEqual([warning]);
  await expect(checkDomains(Array(101).fill('microsoft.com'), new AbortController().signal)).rejects.toEqual(new ApiError('invalid'));
  expect(fetch).toHaveBeenCalledTimes(1);
});
