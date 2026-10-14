import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { AppState } from 'react-native';
import Native from '../../specs/NativeBetGuard';
import { readSnapshot } from './nativeContract';
import { useBetGuard } from './BetGuardContext';
import {
  readRouterSnapshot,
  routerRequest,
  syncPhoneRules,
  type RouterSnapshot,
} from '../api/router';

type Value = {
  snapshot: RouterSnapshot | null;
  busy: boolean;
  error: string | null;
  connected: boolean;
  rulesSynced: boolean;
  unlock: (token: string) => Promise<void>;
  refresh: () => Promise<void>;
  sync: () => Promise<void>;
  connect: (
    url: string,
    username: string,
    password: string,
    authorized: boolean,
  ) => Promise<void>;
  apply: () => Promise<void>;
  verify: () => Promise<void>;
  stop: () => Promise<void>;
};
const Context = createContext<Value | null>(null);

export function RouterProtectionProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { snapshot: phone } = useBetGuard();
  const [token, setToken] = useState(''); // Session memory only; never AsyncStorage or logs.
  const tokenRef = useRef('');
  const [snapshot, setSnapshot] = useState<RouterSnapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rulesSynced, setRulesSynced] = useState(false);
  const pending = useRef(false);
  const syncQueue = useRef<Promise<void>>(Promise.resolve());
  const revision = useRef(0);
  const refreshSequence = useRef(0);
  const signature = JSON.stringify(phone?.rules);
  const phoneAvailable = !!phone;
  const latestRules = useRef(signature);
  latestRules.current = signature;
  const refresh = useCallback(async () => {
    const key = tokenRef.current;
    if (!key || pending.current) return;
    const version = revision.current;
    const request = ++refreshSequence.current;
    try {
      const next = readRouterSnapshot(await routerRequest(key, 'status'));
      if (
        key === tokenRef.current &&
        version === revision.current &&
        request === refreshSequence.current
      ) {
        setSnapshot(next);
        setError(null);
      }
    } catch (e) {
      if (
        key === tokenRef.current &&
        version === revision.current &&
        request === refreshSequence.current
      ) {
        setSnapshot(null);
        setError(e instanceof Error ? e.message : 'Router status unavailable.');
      }
    }
  }, []);
  const sync = useCallback(async () => {
    const key = tokenRef.current;
    setRulesSynced(false);
    if (!key || !Native)
      throw new Error(
        'The Android shared rule storage and administrator session are required.',
      );
    const next = syncQueue.current
      .catch(() => {})
      .then(async () => {
        if (key !== tokenRef.current) return;
        const version = latestRules.current;
        const rules = readSnapshot(await Native!.getSnapshot()).rules;
        await syncPhoneRules(key, rules);
        if (key === tokenRef.current && version === latestRules.current)
          setRulesSynced(true);
      });
    syncQueue.current = next;
    try {
      await next;
    } catch (e) {
      setError(
        e instanceof Error ? e.message : 'Shared rule synchronization failed.',
      );
      throw e;
    }
  }, []);
  useEffect(() => {
    if (!token || !phoneAvailable) return;
    let mounted = true;
    setRulesSynced(false);
    void sync().catch(e => {
      if (mounted)
        setError(
          e instanceof Error
            ? e.message
            : 'Shared rule synchronization failed.',
        );
    });
    return () => {
      mounted = false;
    };
    // Rule changes come from Room, including edits outside the Router screen.
  }, [token, signature, sync, phoneAvailable]);
  useEffect(() => {
    if (!token) return;
    const timer = setInterval(() => {
      if (AppState.currentState === 'active') void refresh();
    }, 15000);
    const listener = AppState.addEventListener('change', state => {
      if (state === 'active') void refresh();
    });
    return () => {
      clearInterval(timer);
      listener.remove();
    };
  }, [token, refresh]);
  async function action(work: () => Promise<unknown>) {
    if (pending.current) return;
    pending.current = true;
    revision.current++;
    setBusy(true);
    setError(null);
    let failure: string | null = null;
    try {
      setSnapshot(readRouterSnapshot(await work()));
    } catch (e) {
      failure = e instanceof Error ? e.message : 'Router action failed.';
    } finally {
      pending.current = false;
      setBusy(false);
      await refresh();
      if (failure) setError(failure);
    }
  }
  const value: Value = {
    snapshot,
    busy,
    error,
    connected: !!token,
    rulesSynced,
    refresh,
    sync,
    unlock: async key => {
      tokenRef.current = key.trim();
      setToken(key.trim());
      setSnapshot(null);
      try {
        await sync();
        await refresh();
      } catch (e) {
        setError(
          e instanceof Error ? e.message : 'Could not connect to the service.',
        );
      }
    },
    connect: (url, username, password, authorized) =>
      action(() =>
        routerRequest(tokenRef.current, 'connect', {
          routerUrl: url.trim(),
          username: username.trim(),
          password,
          authorized,
        }),
      ),
    apply: () =>
      action(async () => {
        await sync();
        return routerRequest(tokenRef.current, 'apply', {
          preview: snapshot?.preview,
          authorized: true,
        });
      }),
    verify: () => action(() => routerRequest(tokenRef.current, 'verify')),
    stop: () => action(() => routerRequest(tokenRef.current, 'stop')),
  };
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useRouterProtection() {
  return useContext(Context);
}
