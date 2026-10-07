import React from 'react';
import { AccessibilityInfo, Modal, Platform, TextInput } from 'react-native';
import Renderer, { act } from 'react-test-renderer';
import { ThemeProvider } from '../src/state/ThemeContext';
import { BetGuardProvider } from '../src/state/BetGuardContext';
import { ApplicationsScreen } from '../src/screens/ApplicationsScreen';
import { Button } from '../src/components/ui';
import Native from '../specs/NativeBetGuard';
import { checkApplication } from '../src/api/applications';
import { useIsFocused } from '@react-navigation/native';

jest.mock('@react-navigation/native', () => ({
  ...jest.requireActual('@react-navigation/native'),
  useIsFocused: jest.fn(() => true),
}));
jest.mock('../src/api/applications', () => ({
  ...jest.requireActual('../src/api/applications'),
  checkApplication: jest.fn(),
}));
jest.mock('../specs/NativeBetGuard', () => ({
  __esModule: true,
  default: {
    getBridgeVersion: jest.fn(() => 2),
    getSnapshot: jest.fn(),
    onSnapshot: jest.fn(() => ({ remove: jest.fn() })),
    configureDetection: jest.fn(),
    startProtection: jest.fn(),
    stopProtection: jest.fn(),
    checkLink: jest.fn(),
    resolveLink: jest.fn(),
    saveRule: jest.fn(),
    removeRule: jest.fn(),
    clearHistory: jest.fn(),
    getThemePreference: jest.fn(() => 'system'),
    setThemePreference: jest.fn(),
    getVisibleApplications: jest.fn(),
  },
}));

let renderer: Renderer.ReactTestRenderer;
const fixtureApp = {
  app_name: 'Test library',
  package_name: 'test.library',
  permissions: ['android.permission.INTERNET'],
};
const notEvaluated = {
  classification: 'unknown',
  source: 'unavailable',
  reason: 'app_model_unavailable',
  explanation: 'No reviewed app metadata model is available.',
  enforcement: 'dns_network_only',
};
function button(title: string) {
  return renderer.root
    .findAllByType(Button)
    .find(b => b.props.title === title)!;
}
async function press(title: string) {
  await act(async () => button(title).props.onPress());
}
async function change(label: string, value: string) {
  const input = renderer.root
    .findAllByType(TextInput)
    .find(node => node.props.accessibilityLabel === label)!;
  await act(() => input.props.onChangeText(value));
}
async function mount() {
  await act(async () => {
    renderer = Renderer.create(
      <ThemeProvider>
        <BetGuardProvider>
          <ApplicationsScreen />
        </BetGuardProvider>
      </ThemeProvider>,
    );
  });
}
beforeEach(() => {
  jest.clearAllMocks();
  jest.replaceProperty(Platform, 'OS', 'android');
  (useIsFocused as jest.Mock).mockReturnValue(true);
  jest
    .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
    .mockResolvedValue(true);
  (Native!.getVisibleApplications as jest.Mock).mockResolvedValue(
    JSON.stringify([fixtureApp]),
  );
  (Native!.getSnapshot as jest.Mock).mockResolvedValue(
    JSON.stringify({ state: 'off', detail: 'Off', rules: [], history: [] }),
  );
  (checkApplication as jest.Mock).mockResolvedValue(notEvaluated);
});
afterEach(async () => {
  if (renderer) await act(() => renderer.unmount());
  jest.restoreAllMocks();
});

test('inventory stays local until requested and only selected metadata is sent with consent', async () => {
  await mount();
  expect(Native!.getVisibleApplications).not.toHaveBeenCalled();
  await press('Choose an installed app');
  expect(renderer.root.findAllByType(Modal).some(m => m.props.visible)).toBe(
    true,
  );
  expect(Native!.getVisibleApplications).not.toHaveBeenCalled();
  await press('Continue with local app list');
  expect(Native!.getVisibleApplications).toHaveBeenCalledTimes(1);
  expect(checkApplication).not.toHaveBeenCalled();
  await press('Test library');
  await change(
    'Public app description',
    'Public educational library description for software testing only.',
  );
  expect(button('Review app information').props.disabled).toBe(true);
  await press('I agree to send this app information');
  await press('Review app information');
  expect(checkApplication).toHaveBeenCalledWith(
    expect.objectContaining({
      package_name: 'test.library',
      app_name: 'Test library',
      permissions: ['android.permission.INTERNET'],
    }),
    expect.any(AbortSignal),
  );
  expect(JSON.stringify(renderer.toJSON())).toContain('NOT EVALUATED');
  expect(Native!.saveRule).not.toHaveBeenCalled();
  expect(Native!.startProtection).not.toHaveBeenCalled();
});

test('editing discards previous result and revokes upload consent', async () => {
  await mount();
  await change('App name', 'Test app');
  await press('I agree to send this app information');
  await press('Review app information');
  expect(JSON.stringify(renderer.toJSON())).toContain('NOT EVALUATED');
  await change('App keywords', 'educational');
  expect(JSON.stringify(renderer.toJSON())).not.toContain('NOT EVALUATED');
  expect(button('Review app information').props.disabled).toBe(true);
});

test('cancelled or stale review cannot display a result', async () => {
  let finish!: (value: typeof notEvaluated) => void;
  (checkApplication as jest.Mock).mockImplementation(
    () =>
      new Promise(resolve => {
        finish = resolve;
      }),
  );
  await mount();
  await change('App name', 'Test app');
  await press('I agree to send this app information');
  await press('Review app information');
  const signal = (checkApplication as jest.Mock).mock
    .calls[0][1] as AbortSignal;
  await press('Cancel review');
  expect(signal.aborted).toBe(true);
  await act(() => finish(notEvaluated));
  expect(JSON.stringify(renderer.toJSON())).not.toContain('NOT EVALUATED');
});

test('leaving clears inventory and app metadata', async () => {
  await mount();
  await change('App name', 'Private session fixture');
  (useIsFocused as jest.Mock).mockReturnValue(false);
  await act(() =>
    renderer.update(
      <ThemeProvider>
        <BetGuardProvider>
          <ApplicationsScreen />
        </BetGuardProvider>
      </ThemeProvider>,
    ),
  );
  const name = renderer.root
    .findAllByType(TextInput)
    .find(node => node.props.accessibilityLabel === 'App name')!;
  expect(name.props.value).toBe('');
  expect(button('Review app information').props.disabled).toBe(true);
});
