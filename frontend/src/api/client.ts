import { API_BASE_URL } from './config';
import type { AppMetadata } from './applications';
export const REQUEST_TIMEOUT_MS = 8000;

export class ApiError extends Error {
  constructor(
    public code:
      | 'unavailable'
      | 'invalid'
      | 'cancelled'
      | 'timeout'
      | 'configuration',
  ) {
    super(code);
  }
}

export async function requestJson(
  path:
    | '/v1/check'
    | '/health/ready'
    | '/v1/domain/check'
    | '/v1/domain/check-batch'
    | '/v1/apps/check'
    | '/health/apps',
  signal: AbortSignal,
  body?:
    | { hostname: string }
    | { domain: string }
    | { domains: string[] }
    | AppMetadata,
): Promise<unknown> {
  if (signal.aborted) throw new ApiError('cancelled');
  const base = API_BASE_URL.replace(/\/+$/, '');
  if (
    !/^https:\/\/[^/?#@\s]+(?:\/[^?#]*)?$/.test(base) &&
    !(
      __DEV__ &&
      /^http:\/\/(?:127\.0\.0\.1|localhost|10\.0\.2\.2)(?::\d+)?$/.test(base)
    )
  ) {
    throw new ApiError('configuration');
  }
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let cancel = () => {};
  const interrupted = new Promise<never>((_resolve, reject) => {
    cancel = () => {
      controller.abort();
      reject(new ApiError('cancelled'));
    };
    signal.addEventListener('abort', cancel);
    timer = setTimeout(() => {
      controller.abort();
      reject(new ApiError('timeout'));
    }, REQUEST_TIMEOUT_MS);
  });
  try {
    return await Promise.race([
      interrupted,
      (async () => {
        const response = await fetch(`${base}${path}`, {
          method: body ? 'POST' : 'GET',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
          },
          body: body ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        });
        if (!response.ok)
          throw new ApiError(
            response.status === 422 ? 'invalid' : 'unavailable',
          );
        return response.json();
      })(),
    ]);
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError('unavailable');
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', cancel);
  }
}
