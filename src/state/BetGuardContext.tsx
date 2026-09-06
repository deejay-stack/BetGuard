import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from 'react';
import { AppState, PermissionsAndroid, Platform } from 'react-native';
import Native from '../../specs/NativeBetGuard';
import type { LinkResult, Snapshot } from './types';

type ContextValue = {
  snapshot: Snapshot | null;
  available: boolean;
  busy: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  dismissError: () => void;
  start: () => Promise<unknown>;
  stop: () => Promise<unknown>;
  save: (
    input: string,
    action: 'block' | 'allow',
    subdomains: boolean,
  ) => Promise<string | undefined>;
  remove: (domain: string) => Promise<unknown>;
  check: (input: string) => Promise<LinkResult | undefined>;
  clearHistory: () => Promise<unknown>;
};
const Context = createContext<ContextValue | null>(null);
const available = Platform.OS === 'android' && Native !== null;
export function BetGuardProvider({ children }: { children: React.ReactNode }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => {
    if (!available || !Native) {
      return;
    }
    try {
      setSnapshot(JSON.parse(await Native.getSnapshot()) as Snapshot);
    } catch (e) {
      setSnapshot(null);
      setError(
        e instanceof Error ? e.message : 'Could not read protection status.',
      );
    }
  }, []);
  useEffect(() => {
    void refresh();
    const subscription = available
      ? Native?.onSnapshot(value => {
          try {
            setSnapshot(JSON.parse(value) as Snapshot);
          } catch {
            setSnapshot(null);
            setError('Could not read a protection update. Reopen the app.');
          }
        })
      : undefined;
    const lifecycle = AppState.addEventListener('change', state => {
      if (state === 'active') {
        void refresh();
      }
    });
    return () => {
      subscription?.remove();
      lifecycle.remove();
    };
  }, [refresh]);
  async function perform<T>(work: () => Promise<T>): Promise<T | undefined> {
    if (!available) {
      setError('Native protection is available only in the Android build.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      return await work();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'The action could not be completed.',
      );
      return;
    } finally {
      await refresh();
      setBusy(false);
    }
  }
  const value: ContextValue = {
    snapshot,
    available,
    busy,
    error,
    refresh,
    dismissError: () => setError(null),
    start: () =>
      perform(async () => {
        if (Platform.OS === 'android' && Number(Platform.Version) >= 33) {
          await PermissionsAndroid.request(
            PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS,
          );
        }
        await Native!.startProtection();
      }),
    stop: () => perform(() => Native!.stopProtection()),
    save: (input, action, subdomains) =>
      perform(() => Native!.saveRule(input, action, subdomains)),
    remove: domain => perform(() => Native!.removeRule(domain)),
    check: input =>
      perform(
        async () => JSON.parse(await Native!.checkLink(input)) as LinkResult,
      ),
    clearHistory: () => perform(() => Native!.clearHistory()),
  };
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
export function useBetGuard() {
  const value = useContext(Context);
  if (!value) {
    throw new Error('BetGuardProvider is required.');
  }
  return value;
}
