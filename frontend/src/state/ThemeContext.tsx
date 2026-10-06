import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { AccessibilityInfo, Appearance, useColorScheme } from 'react-native';
import Native from '../../specs/NativeBetGuard';
import { createStyles, darkColors, lightColors } from '../theme';
import { logFailure } from './nativeContract';

export type ThemeMode = 'light' | 'dark';
export type ThemePreference = ThemeMode | 'system';
function readPreference(): {
  preference: ThemePreference;
  error: string | null;
} {
  try {
    const saved =
      typeof Native?.getThemePreference === 'function'
        ? Native.getThemePreference()
        : 'system';
    return {
      preference: saved === 'light' || saved === 'dark' ? saved : 'system',
      error: null,
    };
  } catch (error) {
    logFailure('read appearance', error);
    return {
      preference: 'system',
      error:
        'Your appearance preference couldn’t be read. Device appearance is being used.',
    };
  }
}
type ThemeValue = {
  mode: ThemeMode;
  preference: ThemePreference;
  colors: typeof lightColors;
  styles: ReturnType<typeof createStyles>;
  reducedMotion: boolean;
  saving: boolean;
  error: string | null;
  setMode: (mode: ThemePreference) => Promise<void>;
};
const Context = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [initial] = useState(readPreference);
  const [preference, setPreference] = useState(initial.preference);
  const system = useColorScheme();
  const mode =
    preference === 'system'
      ? system === 'dark'
        ? 'dark'
        : 'light'
      : preference;
  const [error, setError] = useState(initial.error);
  const [saving, setSaving] = useState(false);
  const pending = useRef(false);
  // Start conservatively until Android reports the accessibility setting.
  const [reducedMotion, setReducedMotion] = useState(true);
  useEffect(() => {
    let live = true;
    let changed = false;
    const subscription = AccessibilityInfo.addEventListener(
      'reduceMotionChanged',
      value => {
        changed = true;
        setReducedMotion(value);
      },
    );
    void AccessibilityInfo.isReduceMotionEnabled()
      .then(value => {
        if (live && !changed) {
          setReducedMotion(value);
        }
      })
      .catch(() => {});
    return () => {
      live = false;
      subscription.remove();
    };
  }, []);
  useEffect(() => {
    Appearance.setColorScheme(preference === 'system' ? 'auto' : preference);
  }, [preference]);
  const colors = mode === 'dark' ? darkColors : lightColors;
  const styles = useMemo(() => createStyles(colors), [colors]);
  async function setMode(next: ThemePreference) {
    if (pending.current) {
      return;
    }
    pending.current = true;
    setSaving(true);
    setError(null);
    setPreference(next);
    Appearance.setColorScheme(next === 'system' ? 'auto' : next);
    try {
      if (!Native) {
        throw new Error('Appearance persistence requires the Android build.');
      }
      await Native.setThemePreference(next);
    } catch (failure) {
      logFailure('save appearance', failure);
      setError(
        'Theme changed for this session, but could not be saved. Please try again.',
      );
    } finally {
      pending.current = false;
      setSaving(false);
    }
  }
  return (
    <Context.Provider
      value={{
        mode,
        preference,
        colors,
        styles,
        reducedMotion,
        saving,
        error,
        setMode,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useTheme() {
  const value = useContext(Context);
  if (!value) {
    throw new Error('ThemeProvider is required.');
  }
  return value;
}
