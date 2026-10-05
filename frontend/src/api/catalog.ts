import { ApiError, requestJson } from './client';
import type { CatalogResult } from './types';
export { API_BASE_URL } from './config';
export { ApiError as CatalogError, REQUEST_TIMEOUT_MS } from './client';
export type { CatalogResult } from './types';

function validResult(value: unknown, hostname: string): value is CatalogResult {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const data = value as Record<string, unknown>;
  if (
    !data ||
    data.hostname !== hostname ||
    typeof data.classification !== 'string' ||
    !['gambling', 'non_gambling', 'unknown'].includes(data.classification) ||
    typeof data.explanation !== 'string' ||
    !data.explanation.trim() ||
    data.explanation.length > 2000
  )
    return false;
  const probability = data.calibrated_probability;
  if (
    probability != null &&
    (data.source !== 'model' ||
      typeof probability !== 'number' ||
      !Number.isFinite(probability) ||
      probability < 0 ||
      probability > 1)
  )
    return false;
  if (data.source === 'reviewed_catalog') {
    return (
      data.reason === 'reviewed_catalog' &&
      (data.model_version ?? null) === null &&
      typeof data.label_provenance === 'string' &&
      data.label_provenance.length <= 500 &&
      !!data.label_provenance.trim() &&
      typeof data.reviewed_at === 'string' &&
      Number.isFinite(Date.parse(data.reviewed_at))
    );
  }
  if (
    (data.label_provenance ?? null) !== null ||
    (data.reviewed_at ?? null) !== null
  )
    return false;
  if (data.source === 'model') {
    return (
      typeof data.model_version === 'string' &&
      !!data.model_version.trim() &&
      data.model_version.length <= 200 &&
      (data.reason === 'model_prediction'
        ? data.classification !== 'unknown'
        : typeof data.reason === 'string' &&
          ['model_abstained', 'model_ineligible'].includes(data.reason) &&
          data.classification === 'unknown')
    );
  }
  return (
    data.source === 'unavailable' &&
    (data.model_version ?? null) === null &&
    data.classification === 'unknown' &&
    typeof data.reason === 'string' &&
    ['not_in_catalog', 'not_reviewed'].includes(data.reason)
  );
}

// Native DomainPolicy owns URL parsing/IDN normalization. This boundary accepts
// only its normalized ASCII hostname, preventing future callers leaking a URL.
function isNormalizedHostname(hostname: string): boolean {
  if (hostname.length > 253) return false;
  const labels = hostname.split('.');
  return (
    labels.length >= 2 &&
    !/^\d+$/.test(labels[labels.length - 1]) &&
    labels.every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))
  );
}

export async function checkCatalog(
  hostname: string,
  signal: AbortSignal,
): Promise<CatalogResult> {
  if (signal.aborted) throw new ApiError('cancelled');
  if (!isNormalizedHostname(hostname)) throw new ApiError('invalid');
  const data = await requestJson('/v1/check', signal, { hostname });
  if (!validResult(data, hostname)) throw new ApiError('unavailable');
  return data;
}
