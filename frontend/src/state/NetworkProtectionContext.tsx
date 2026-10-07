import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { AppState, PermissionsAndroid, Platform } from 'react-native';
import Native from '../../specs/NativeBetGuard';
import { API_BASE_URL } from '../api/config';
import { logFailure } from './nativeContract';

export type NetworkClient = {
  ip: string;
  firstSeen: number;
  lastActivity: number;
  requests: number;
  blocked: number;
  warnings: number;
  connections: number;
};
export type NetworkSnapshot = {
  state:
    | 'off'
    | 'starting'
    | 'active'
    | 'degraded'
    | 'stopping'
    | 'failed'
    | 'interrupted';
  detail: string;
  address: string | null;
  port: number;
  interfaceName: string | null;
  interfaces: {
    address: string;
    prefixLength: number;
    interfaceName: string;
  }[];
  runtime: 'not_checked' | 'ready' | 'unavailable';
  startedAt: number;
  requests: number;
  allowed: number;
  blocked: number;
  warnings: number;
  errors: number;
  rejected: number;
  clients: NetworkClient[];
};
function ip(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    /^\d{1,3}(?:\.\d{1,3}){3}$/.test(value) &&
    value.split('.').every(part => Number(part) <= 255)
  );
}
function count(value: unknown): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
export function readNetworkSnapshot(raw: string): NetworkSnapshot {
  const value = JSON.parse(raw) as NetworkSnapshot;
  if (
    !value ||
    ![
      'off',
      'starting',
      'active',
      'degraded',
      'stopping',
      'failed',
      'interrupted',
    ].includes(value.state) ||
    typeof value.detail !== 'string' ||
    !(value.address === null || ip(value.address)) ||
    !(
      value.interfaceName === null || typeof value.interfaceName === 'string'
    ) ||
    !count(value.port) ||
    value.port > 65535 ||
    !count(value.startedAt) ||
    !['not_checked', 'ready', 'unavailable'].includes(value.runtime) ||
    !['requests', 'allowed', 'blocked', 'warnings', 'errors', 'rejected'].every(
      key => count(value[key as keyof NetworkSnapshot]),
    ) ||
    !Array.isArray(value.interfaces) ||
    !value.interfaces.every(
      row =>
        row &&
        ip(row.address) &&
        Number.isInteger(row.prefixLength) &&
        row.prefixLength >= 8 &&
        row.prefixLength <= 30 &&
        typeof row.interfaceName === 'string',
    ) ||
    !Array.isArray(value.clients) ||
    value.clients.length > 64 ||
    !value.clients.every(
      row =>
        row &&
        ip(row.ip) &&
        [
          'firstSeen',
          'lastActivity',
          'requests',
          'blocked',
          'warnings',
          'connections',
        ].every(key => count(row[key as keyof NetworkClient])),
    ) ||
    (['active', 'degraded'].includes(value.state) &&
      (!value.address || value.port < 1024))
  ) {
    throw new Error('Invalid network protection snapshot');
  }
  return value;
}
type NetworkContextValue = {
  snapshot: NetworkSnapshot | null;
  available: boolean;
  busy: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  start: (address: string, port: number) => Promise<void>;
  stop: () => Promise<void>;
};
const Context = createContext<NetworkContextValue>({
  snapshot: null,
  available: false,
  busy: false,
  error: null,
  refresh: async () => {},
  start: async () => {},
  stop: async () => {},
});

export function NetworkProtectionProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const bridge = Native;
  const available =
    Platform.OS === 'android' &&
    !!bridge &&
    [
      'getNetworkSnapshot',
      'startNetworkProtection',
      'stopNetworkProtection',
      'onNetworkSnapshot',
    ].every(name => typeof bridge[name as keyof typeof bridge] === 'function');
  const [snapshot, setSnapshot] = useState<NetworkSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const revision = useRef(0);
  const live = useRef(true);
  const refresh = useCallback(async () => {
    if (!available || !Native) return;
    const current = ++revision.current;
    try {
      const next = readNetworkSnapshot(await Native.getNetworkSnapshot());
      if (live.current && current === revision.current) setSnapshot(next);
    } catch (failure) {
      if (live.current && current === revision.current) {
        setSnapshot(null);
        setError(
          'Could not read gateway status. Reopen BetGuard and try again.',
        );
      }
      logFailure('network snapshot', failure);
    }
  }, [available]);
  useEffect(() => {
    live.current = true;
    if (!available || !Native) return;
    const subscription = Native.onNetworkSnapshot(raw => {
      revision.current++;
      try {
        setSnapshot(readNetworkSnapshot(raw));
      } catch (failure) {
        setSnapshot(null);
        setError('Gateway status could not be read. Reopen BetGuard.');
        logFailure('network update', failure);
      }
    });
    void refresh();
    const lifecycle = AppState.addEventListener('change', next => {
      if (next === 'active') void refresh();
    });
    return () => {
      live.current = false;
      subscription.remove();
      lifecycle.remove();
    };
  }, [available, refresh]);
  async function action(work: () => Promise<void>) {
    if (!available || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (failure) {
      logFailure('network action', failure);
      const message = failure instanceof Error ? failure.message : '';
      if (live.current)
        setError(
          /^(Turn on your hotspot|Use a proxy port|Configure the BetGuard API address|Stop Network Protection)/.test(
            message,
          )
            ? message
            : 'Could not complete the gateway action. Check your hotspot or Wi-Fi and try again.',
        );
    } finally {
      await refresh();
      pending.current = false;
      if (live.current) setBusy(false);
    }
  }
  return (
    <Context.Provider
      value={{
        snapshot,
        available,
        busy,
        error,
        refresh,
        start: (address, port) =>
          action(async () => {
            if (!API_BASE_URL)
              throw new Error(
                'Configure the BetGuard API address before starting Network Protection.',
              );
            if (Platform.OS === 'android' && Number(Platform.Version) >= 33) {
              await PermissionsAndroid.request(
                PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS,
              );
            }
            await Native!.startNetworkProtection(address, port, API_BASE_URL);
          }),
        stop: () => action(() => Native!.stopNetworkProtection()),
      }}
    >
      {children}
    </Context.Provider>
  );
}
export const useNetworkProtection = () => useContext(Context);
