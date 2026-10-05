import { ApiError, requestJson } from './client';

export async function checkReadiness(signal: AbortSignal): Promise<void> {
  const data = await requestJson('/health/ready', signal);
  if (
    !data ||
    typeof data !== 'object' ||
    !('status' in data) ||
    data.status !== 'ready'
  ) {
    throw new ApiError('unavailable');
  }
}
