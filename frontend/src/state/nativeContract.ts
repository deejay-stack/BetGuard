import { Platform } from 'react-native';
import Native from '../../specs/NativeBetGuard';
import type { LinkResult, Snapshot } from './types';

export const BRIDGE_VERSION = 2;
export function bridgeIssue(): string | null {
  if (Platform.OS !== 'android' || !Native)
    return 'Native protection is available only in the Android app.';
  const bridge = Native;
  const methods = [
    'getBridgeVersion',
    'getSnapshot',
    'onSnapshot',
    'configureDetection',
    'startProtection',
    'stopProtection',
    'checkLink',
    'resolveLink',
    'saveRule',
    'removeRule',
    'clearHistory',
    'getThemePreference',
    'setThemePreference',
  ] as const;
  try {
    const missing = methods.filter(
      method => typeof bridge[method] !== 'function',
    );
    if (missing.length || bridge.getBridgeVersion() !== BRIDGE_VERSION) {
      console.error('[BetGuard] Android bridge mismatch', {
        missing,
        expected: BRIDGE_VERSION,
      });
      return 'This Android app needs an update to match BetGuard. Install the rebuilt APK; your saved rules will stay on this phone.';
    }
    return null;
  } catch (error) {
    logFailure('bridge', error);
    return 'Android protection could not connect. Close and reopen BetGuard, then try again.';
  }
}
// Log types/codes for diagnosis, never inputs, URLs or arbitrary exception messages.
export function logFailure(operation: string, error: unknown) {
  const code =
    error && typeof error === 'object' && 'code' in error
      ? String(error.code)
      : '';
  console.error(
    '[BetGuard]',
    operation,
    error instanceof Error ? error.name : 'NativeError',
    code,
  );
}
export function actionError(error: unknown): string {
  const message = error instanceof Error ? error.message : '';
  const safe =
    /^(Enter a |Remove spaces and backslashes|Only HTTP and HTTPS|A hostname is required|Links with credentials|Use a website hostname|Use a numeric port|IP addresses are not supported|VPN permission was not granted|Finish the open permission|Stop protection before|Configure the BetGuard API address)/;
  return safe.test(message)
    ? message
    : 'BetGuard couldn’t complete that action. Please try again. If protection needs attention, turn it off and enable it again.';
}
export function readSnapshot(raw: string): Snapshot {
  const value = JSON.parse(raw) as Snapshot;
  if (
    !value ||
    ![
      'off',
      'starting',
      'stopping',
      'active',
      'degraded',
      'failed',
      'interrupted',
    ].includes(value.state) ||
    typeof value.detail !== 'string' ||
    !Array.isArray(value.rules) ||
    !Array.isArray(value.history) ||
    (value.detectionEnabled !== undefined &&
      typeof value.detectionEnabled !== 'boolean') ||
    !value.rules.every(
      rule =>
        rule &&
        typeof rule.domain === 'string' &&
        ['allow', 'block'].includes(rule.action) &&
        typeof rule.includeSubdomains === 'boolean' &&
        Number.isFinite(rule.updatedAt),
    ) ||
    !value.history.every(
      item =>
        item &&
        Number.isFinite(item.id) &&
        typeof item.kind === 'string' &&
        typeof item.domain === 'string' &&
        typeof item.detail === 'string' &&
        Number.isFinite(item.createdAt) &&
        (item.clientIp === undefined ||
          item.clientIp === null ||
          typeof item.clientIp === 'string') &&
        (item.decisionSource === undefined ||
          item.decisionSource === null ||
          typeof item.decisionSource === 'string') &&
        (item.protection === undefined ||
          ['device', 'network'].includes(item.protection)),
    )
  )
    throw new Error('Invalid native snapshot');
  return value;
}
export function readLink(raw: string): LinkResult {
  const value = JSON.parse(raw) as LinkResult;
  if (
    !value ||
    typeof value.domain !== 'string' ||
    !['allow', 'block'].includes(value.action) ||
    value.classification !== 'unknown' ||
    typeof value.reason !== 'string' ||
    !Number.isFinite(value.checkedAt) ||
    !(value.matchedDomain === null || typeof value.matchedDomain === 'string')
  )
    throw new Error('Invalid native rule result');
  return value;
}
