import React from 'react';
import { AccessibilityInfo, TextInput, useColorScheme } from 'react-native';
import Renderer, { act } from 'react-test-renderer';
import { ThemeProvider } from '../src/state/ThemeContext';
import { BetGuardProvider } from '../src/state/BetGuardContext';
import { SettingsScreen } from '../src/screens/SettingsScreen';
import { CheckScreen } from '../src/screens/CheckScreen';
import { SitesScreen } from '../src/screens/SitesScreen';
import { HistoryScreen } from '../src/screens/HistoryScreen';
import { Button } from '../src/components/ui';
import { BrandLogo } from '../src/components/BrandLogo';

jest.mock('../specs/NativeBetGuard', () => ({
  __esModule: true,
  default: null,
}));
test.each(['light', 'dark'] as const)(
  '%s screens render theme controls, inputs and truthful unavailable states',
  async mode => {
    (useColorScheme as jest.Mock).mockReturnValue(mode);
    const motion = jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockResolvedValue(true);
    let renderer!: Renderer.ReactTestRenderer;
    await act(async () => {
      renderer = Renderer.create(
        <ThemeProvider>
          <BetGuardProvider>
            <SettingsScreen />
            <CheckScreen />
            <SitesScreen />
            <HistoryScreen />
          </BetGuardProvider>
        </ThemeProvider>,
      );
    });
    const tree = JSON.stringify(renderer.toJSON());
    expect(tree).toContain(
      `Switch to ${mode === 'dark' ? 'light' : 'dark'} mode`,
    );
    expect(tree).toContain('Reviewed catalog labels');
    expect(tree).toContain('DEVELOPMENT BUILD');
    expect(tree).not.toContain('PROTOTYPE');
    expect(tree).toContain('Native protection is unavailable');
    expect(
      renderer.root.findAllByType(BrandLogo).length,
    ).toBeGreaterThanOrEqual(5);
    for (const input of renderer.root.findAllByType(TextInput)) {
      expect(input.props.keyboardAppearance).toBe(mode);
      expect(input.props.accessibilityLabel).toBeTruthy();
    }
    const toggle = renderer.root
      .findAllByType(Button)
      .find(button => button.props.title.startsWith('Switch to'))!;
    await act(() => toggle.props.onPress());
    expect(JSON.stringify(renderer.toJSON())).toContain(
      `Switch to ${mode} mode`,
    );
    expect(JSON.stringify(renderer.toJSON())).toContain('could not be saved');
    await act(() => renderer.unmount());
    motion.mockRestore();
  },
);
