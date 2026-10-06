import React from 'react';
import {
  AccessibilityInfo,
  Appearance,
  Text,
  useColorScheme,
} from 'react-native';
import Renderer, { act } from 'react-test-renderer';
import Native from '../specs/NativeBetGuard';
import { ThemeProvider, useTheme } from '../src/state/ThemeContext';
import { lightColors, darkColors } from '../src/theme';

jest.mock('../specs/NativeBetGuard', () => ({
  __esModule: true,
  default: {
    getThemePreference: jest.fn(),
    setThemePreference: jest.fn(),
  },
}));
let saved = 'system';
let current: ReturnType<typeof useTheme>;
let renderer: Renderer.ReactTestRenderer;
function Probe() {
  current = useTheme();
  return <Text>{current.mode}</Text>;
}
async function mount() {
  await act(() => {
    renderer = Renderer.create(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
  });
}
beforeEach(() => {
  saved = 'system';
  (useColorScheme as jest.Mock).mockReturnValue('light');
  jest.spyOn(Appearance, 'getColorScheme').mockReturnValue('light');
  jest.spyOn(Appearance, 'setColorScheme').mockImplementation(() => {});
  jest
    .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
    .mockResolvedValue(true);
  (Native!.getThemePreference as jest.Mock).mockImplementation(() => saved);
  (Native!.setThemePreference as jest.Mock).mockImplementation(
    async (mode: string) => {
      saved = mode;
    },
  );
});
afterEach(async () => {
  if (renderer) {
    await act(() => renderer.unmount());
  }
  jest.restoreAllMocks();
  jest.clearAllMocks();
});
test('uses device appearance without saving an implicit preference', async () => {
  (useColorScheme as jest.Mock).mockReturnValue('dark');
  await mount();
  expect(current.mode).toBe('dark');
  expect(Native!.setThemePreference).not.toHaveBeenCalled();
});
test('restores saved dark appearance on the first render even on a light device', async () => {
  saved = 'dark';
  const observed: string[] = [];
  function FirstFrame() {
    observed.push(useTheme().mode);
    return null;
  }
  await act(() => {
    renderer = Renderer.create(
      <ThemeProvider>
        <FirstFrame />
      </ThemeProvider>,
    );
  });
  expect(observed.length).toBeGreaterThan(0);
  expect(observed.every(mode => mode === 'dark')).toBe(true);
});
test('switches immediately, saves, and restores after provider remount', async () => {
  await mount();
  await act(() => current.setMode('dark'));
  expect(current.mode).toBe('dark');
  expect(current.colors).toEqual(darkColors);
  expect(saved).toBe('dark');
  expect(Appearance.setColorScheme).toHaveBeenCalledWith('dark');
  await act(() => renderer.unmount());
  await mount();
  expect(current.mode).toBe('dark');
  await act(() => current.setMode('light'));
  expect(saved).toBe('light');
});
test('failed writes are visible and a later selection can retry', async () => {
  (Native!.setThemePreference as jest.Mock).mockRejectedValueOnce(
    new Error('disk'),
  );
  await mount();
  await act(() => current.setMode('dark'));
  expect(current.mode).toBe('dark');
  expect(current.error).toContain('could not be saved');
  expect(saved).toBe('system');
  await act(() => current.setMode('light'));
  expect(current.error).toBeNull();
  expect(saved).toBe('light');
});

test('System restores automatic appearance and persists across remount', async () => {
  saved = 'dark';
  await mount();
  await act(() => current.setMode('system'));
  expect(saved).toBe('system');
  expect(current.preference).toBe('system');
  expect(Appearance.setColorScheme).toHaveBeenCalledWith('auto');
  expect(current.mode).toBe('light');
  await act(() => renderer.unmount());
  (useColorScheme as jest.Mock).mockReturnValue('dark');
  await mount();
  expect(current.mode).toBe('dark');
  expect(current.preference).toBe('system');
});
test('serializes pending writes and respects reduced motion', async () => {
  let resolve!: () => void;
  (Native!.setThemePreference as jest.Mock).mockImplementationOnce(
    () =>
      new Promise<void>(done => {
        resolve = done;
      }),
  );
  await mount();
  await act(() => {
    void current.setMode('dark');
    void current.setMode('light');
  });
  expect(current.mode).toBe('dark');
  expect(current.saving).toBe(true);
  expect(current.reducedMotion).toBe(true);
  expect(Native!.setThemePreference).toHaveBeenCalledTimes(1);
  await act(async () => {
    resolve();
  });
  expect(current.saving).toBe(false);
});
function luminance(hex: string) {
  const c = hex
    .slice(1)
    .match(/../g)!
    .map(v => parseInt(v, 16) / 255)
    .map(v => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722;
}
test.each([
  ['light', lightColors],
  ['dark', darkColors],
] as const)('%s semantic text pairs have at least 4.5:1 contrast', (_, c) => {
  const pairs = [
    [c.text, c.background],
    [c.text, c.surface],
    [c.textMuted, c.background],
    [c.textMuted, c.surface],
    [c.primary, c.primarySoft],
    [c.primary, c.surface],
    [c.onPrimary, c.primary],
    [c.success, c.successSoft],
    [c.warning, c.warningSoft],
    [c.error, c.errorSoft],
    [c.onDisabled, c.disabled],
    [c.onHero, c.hero],
    [c.heroMuted, c.hero],
  ];
  for (const [fg, bg] of pairs) {
    const a = luminance(fg),
      b = luminance(bg);
    expect(
      (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05),
    ).toBeGreaterThanOrEqual(4.5);
  }
});
