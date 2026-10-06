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
import type { LinkResult, Snapshot } from './types';
import { API_BASE_URL } from '../api/config';
import { haptic } from './haptics';
import {
  actionError,
  bridgeIssue,
  logFailure,
  readLink,
  readSnapshot,
} from './nativeContract';

type ContextValue = {
  snapshot: Snapshot | null;
  available: boolean;
  busy: boolean;
  error: string | null;
  feedback: string | null;
  refresh: () => Promise<void>;
  dismissError: () => void;
  dismissFeedback: () => void;
  start: (onlineDetection?: boolean) => Promise<unknown>;
  stop: () => Promise<unknown>;
  save: (
    input: string,
    action: 'block' | 'allow',
    subdomains: boolean,
  ) => Promise<string | undefined>;
  remove: (domain: string) => Promise<boolean | undefined>;
  check: (input: string) => Promise<LinkResult | undefined>;
  resolve: (input: string) => Promise<LinkResult | undefined>;
  clearHistory: () => Promise<unknown>;
};
const Context = createContext<ContextValue | null>(null);
export function BetGuardProvider({ children }: { children: React.ReactNode }) {
  const [compatibilityError] = useState(bridgeIssue);
  const available = compatibilityError === null;
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(compatibilityError);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const actionPending = useRef(false);
  const eventRevision = useRef(0);
  const refreshRequest = useRef(0);
  const lastEvent = useRef<number | null>(null);
  const lastPulse = useRef(0);
  useEffect(() => {
    const latest = snapshot?.history[0]?.id;
    if (latest === undefined) return;
    if (
      lastEvent.current !== null &&
      latest > lastEvent.current &&
      AppState.currentState === 'active'
    ) {
      const blocked = snapshot?.history.some(
        event =>
          event.id > lastEvent.current! &&
          ['dns_blocked', 'dns_detection_blocked'].includes(event.kind),
      );
      if (blocked && Date.now() - lastPulse.current > 5000) {
        haptic('blocked');
        lastPulse.current = Date.now();
      }
    }
    lastEvent.current = latest;
  }, [snapshot]);
  const refresh = useCallback(async () => {
    if (!available || !Native) {
      return;
    }
    const revision = eventRevision.current;
    const request = ++refreshRequest.current;
    try {
      const next = readSnapshot(await Native.getSnapshot());
      if (
        revision === eventRevision.current &&
        request === refreshRequest.current
      )
        setSnapshot(next);
    } catch (e) {
      if (
        revision !== eventRevision.current ||
        request !== refreshRequest.current
      )
        return;
      setSnapshot(null);
      logFailure('snapshot', e);
      setError(
        'BetGuard couldn’t read protection status. Try reopening the app.',
      );
    }
  }, [available]);
  useEffect(() => {
    let subscription: { remove: () => void } | undefined;
    try {
      subscription = available
        ? Native?.onSnapshot(value => {
            eventRevision.current++;
            try {
              setSnapshot(readSnapshot(value));
            } catch (e) {
              logFailure('snapshot event', e);
              setSnapshot(null);
              setError('Could not read a protection update. Reopen the app.');
            }
          })
        : undefined;
    } catch (e) {
      logFailure('subscribe snapshot', e);
      setSnapshot(null);
      setError('Protection updates couldn’t connect. Please reopen BetGuard.');
    }
    void refresh();
    const lifecycle = AppState.addEventListener('change', state => {
      if (state === 'active') {
        void refresh();
      }
    });
    return () => {
      subscription?.remove();
      lifecycle.remove();
    };
  }, [refresh, available]);
  async function perform<T>(work: () => Promise<T>): Promise<T | undefined> {
    if (actionPending.current) return;
    if (!available) {
      setError('Native protection is available only in the Android build.');
      return;
    }
    setBusy(true);
    actionPending.current = true;
    setError(null);
    setFeedback(null);
    try {
      return await work();
    } catch (e) {
      logFailure('action', e);
      setError(actionError(e));
      haptic('error');
      return;
    } finally {
      await refresh();
      setBusy(false);
      actionPending.current = false;
    }
  }
  const resolve = useCallback(
    async (input: string) => {
      if (!available || !Native) return;
      try {
        return readLink(await Native.resolveLink(input));
      } catch (e) {
        logFailure('resolve rule', e);
        setError(
          'BetGuard couldn’t read this website’s protection rule. Please try again.',
        );
      }
    },
    [available],
  );
  async function ruleFeedback(host: string, action: string) {
    const effective = await resolve(host);
    setFeedback(
      `${host}: ${action}. ${
        effective
          ? effective.matchedDomain
            ? effective.reason
            : 'No matching local rule. Online detection applies when enabled; manual mode allows unmatched hostnames.'
          : 'Current effective rule could not be read.'
      } Saving a rule is separate from observing a blocked DNS request.`,
    );
  }
  const value: ContextValue = {
    snapshot,
    available,
    busy,
    error,
    feedback,
    refresh,
    dismissError: () => setError(null),
    dismissFeedback: () => setFeedback(null),
    start: (onlineDetection = false) =>
      perform(async () => {
        if (onlineDetection && !API_BASE_URL) {
          throw new Error(
            'Configure the BetGuard API address before enabling online detection.',
          );
        }
        if (Platform.OS === 'android' && Number(Platform.Version) >= 33) {
          await PermissionsAndroid.request(
            PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS,
          );
        }
        await Native!.configureDetection(onlineDetection ? API_BASE_URL : '');
        await Native!.startProtection();
      }),
    stop: () => perform(() => Native!.stopProtection()),
    save: (input, action, subdomains) =>
      perform(async () => {
        const host = await Native!.saveRule(input, action, subdomains);
        await ruleFeedback(
          host,
          `${action === 'block' ? 'Block' : 'Allow'} rule saved`,
        );
        haptic('success');
        return host;
      }),
    remove: domain =>
      perform(async () => {
        await Native!.removeRule(domain);
        await ruleFeedback(domain, 'Override removed');
        return true;
      }),
    resolve,
    check: input =>
      perform(async () => readLink(await Native!.checkLink(input))),
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
