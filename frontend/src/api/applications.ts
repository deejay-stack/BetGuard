import { ApiError, requestJson } from './client';

export type AppMetadata = {
  app_name: string;
  package_name: string;
  description: string;
  keywords: string[];
  permissions: string[];
  reviews: string[];
};
export type VisibleApplication = Pick<
  AppMetadata,
  'app_name' | 'package_name' | 'permissions'
>;
export type AppCheck = {
  classification: 'gambling' | 'non_gambling' | 'unknown';
  source: 'app_metadata_model' | 'unavailable';
  reason: string;
  explanation: string;
  model_version?: string;
  enforcement: 'dns_network_only';
};

export function visibleApplications(raw: string): VisibleApplication[] {
  const rows: unknown = JSON.parse(raw);
  if (
    !Array.isArray(rows) ||
    rows.length > 500 ||
    !rows.every(
      row =>
        row &&
        typeof row.app_name === 'string' &&
        row.app_name.length > 0 &&
        row.app_name.length <= 200 &&
        typeof row.package_name === 'string' &&
        /^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$/.test(row.package_name) &&
        Array.isArray(row.permissions) &&
        row.permissions.length <= 150 &&
        row.permissions.every(
          (p: unknown) =>
            typeof p === 'string' && p.length > 0 && p.length <= 160,
        ),
    )
  ) {
    throw new ApiError('unavailable');
  }
  return rows;
}

export async function checkApplication(
  metadata: AppMetadata,
  signal: AbortSignal,
): Promise<AppCheck> {
  const response = await requestJson('/v1/apps/check', signal, metadata);
  if (!response || typeof response !== 'object')
    throw new ApiError('unavailable');
  const value = response as AppCheck;
  if (
    !['gambling', 'non_gambling', 'unknown'].includes(value.classification) ||
    !['app_metadata_model', 'unavailable'].includes(value.source) ||
    typeof value.reason !== 'string' ||
    typeof value.explanation !== 'string' ||
    value.enforcement !== 'dns_network_only' ||
    (value.classification !== 'unknown' &&
      value.source !== 'app_metadata_model') ||
    (value.source === 'app_metadata_model' &&
      (typeof value.model_version !== 'string' || !value.model_version))
  ) {
    throw new ApiError('unavailable');
  }
  return value;
}
