import config from '../../api.config.json';

export type ApiSettings = {
  developmentTarget: string;
  remoteBaseUrl: string;
};

export function resolveApiBaseUrl(
  settings: ApiSettings,
  development: boolean,
): string {
  if (development) {
    if (settings.developmentTarget === 'device') return 'http://127.0.0.1:8000';
    if (settings.developmentTarget === 'emulator')
      return 'http://10.0.2.2:8000';
    if (settings.developmentTarget !== 'remote') return '';
  }
  // Preview/production never fall back to the PC or emulator, even if a
  // development target was selected when the release APK was built.
  const remote = settings.remoteBaseUrl.trim().replace(/\/+$/, '');
  return /^https:\/\/[^/?#@\s]+(?:\/[^?#]*)?$/.test(remote) ? remote : '';
}

// These settings are public API addresses only, never database credentials.
export const API_BASE_URL = resolveApiBaseUrl(config, __DEV__);
