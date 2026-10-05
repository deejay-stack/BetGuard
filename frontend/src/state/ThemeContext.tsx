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

export type ThemeMode = 'light' | 'dark';
function readPreference(): {
  preference: ThemeMode | null;
  error: string | null;
} {
  try {
    const saved = Native?.getThemePreference();
    return {
      preference: saved === 'light' || saved === 'dark' ? saved : null,
      error: null,
    };
  } catch {
    return {
      preference: null,
      error:
        'Could not read appearance. Install the updated Android build and try again.',
    };
  }
}
type ThemeValue = {
  mode: ThemeMode;
  colors: typeof lightColors;
  styles: ReturnType<typeof createStyles>;
  reducedMotion: boolean;
  saving: boolean;
  error: string | null;
  setMode: (mode: ThemeMode) => Promise<void>;
};
const Context = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [initial] = useState(readPreference);
  const [preference, setPreference] = useState(initial.preference);
  const system = useColorScheme();
  const mode = preference ?? (system === 'dark' ? 'dark' : 'light');
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
    Appearance.setColorScheme(preference ?? 'auto');
  }, [preference]);
  const colors = mode === 'dark' ? darkColors : lightColors;
  const styles = useMemo(() => createStyles(colors), [colors]);
  async function setMode(next: ThemeMode) {
    if (pending.current) {
      return;
    }
    pending.current = true;
    setSaving(true);
    setError(null);
    setPreference(next);
    Appearance.setColorScheme(next);
    try {
      if (!Native) {
        throw new Error('Appearance persistence requires the Android build.');
      }
      await Native.setThemePreference(next);
    } catch {
      setError(
        'Theme changed for this session, but could not be saved. Try again with the updated Android build.',
      );
    } finally {
      pending.current = false;
      setSaving(false);
    }
  }
  return (
    <Context.Provider
      value={{ mode, colors, styles, reducedMotion, saving, error, setMode }}
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
