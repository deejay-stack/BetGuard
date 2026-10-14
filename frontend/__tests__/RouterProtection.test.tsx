import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { TextInput } from 'react-native';
import { RouterProtectionScreen } from '../src/screens/RouterProtectionScreen';
import { ThemeProvider } from '../src/state/ThemeContext';
import { Button } from '../src/components/ui';
import { HoldButton } from '../src/components/HoldButton';
import {
  readRouterSnapshot,
  routerRequest,
  type RouterSnapshot,
} from '../src/api/router';
import { useRouterProtection } from '../src/state/RouterProtectionContext';
import { useBetGuard } from '../src/state/BetGuardContext';
import { activityKind } from '../src/components/ActivityRow';

jest.mock('../src/state/RouterProtectionContext', () => ({
  useRouterProtection: jest.fn(),
}));
jest.mock('../src/state/BetGuardContext', () => ({ useBetGuard: jest.fn() }));
jest.mock('../specs/NativeBetGuard', () => ({
  __esModule: true,
  default: null,
}));
const base: RouterSnapshot = {
  state: 'off',
  detail: 'Not configured',
  router: null,
  routerUrl: null,
  routerType: null,
  version: null,
  filterHost: '192.168.10.20',
  filterPort: 5353,
  dnsRunning: true,
  mlReady: true,
  blocklistLoaded: true,
  enforcementVerified: false,
  preview: null,
  changes: [],
  firewallRule: null,
  clients: [],
  history: [],
  requests: 0,
  allowed: 0,
  blocked: 0,
  warnings: 0,
  errors: 0,
};
let renderer: Renderer.ReactTestRenderer;
let current: ReturnType<typeof useRouterProtection>;
const save = jest.fn();
beforeEach(() => {
  jest.clearAllMocks();
  current = {
    snapshot: base,
    busy: false,
    error: null,
    connected: true,
    rulesSynced: true,
    unlock: jest.fn(),
    refresh: jest.fn().mockResolvedValue(undefined),
    sync: jest.fn().mockResolvedValue(undefined),
    connect: jest.fn(),
    apply: jest.fn(),
    verify: jest.fn(),
    stop: jest.fn(),
  };
  (useRouterProtection as jest.Mock).mockImplementation(() => current);
  (useBetGuard as jest.Mock).mockReturnValue({
    save,
    busy: false,
    snapshot: { rules: [] },
  });
});
async function mount() {
  await act(async () => {
    renderer = Renderer.create(
      <ThemeProvider>
        <RouterProtectionScreen />
      </ThemeProvider>,
    );
  });
}
async function press(title: string) {
  const button = renderer.root
    .findAllByType(Button)
    .find(b => b.props.title === title)!;
  await act(async () => {
    button.props.onPress();
  });
}
afterEach(async () => {
  if (renderer) await act(async () => renderer.unmount());
});
test('active requires healthy enforcement and bounded actual counters', () => {
  expect(readRouterSnapshot(base)).toEqual(base);
  expect(() => readRouterSnapshot({ ...base, state: 'active' })).toThrow();
  expect(() => readRouterSnapshot({ ...base, requests: -1 })).toThrow();
  expect(activityKind('router_warning')).toBe('Warnings');
  expect(activityKind('router_blocked')).toBe('Blocked');
  expect(activityKind('router_allowed')).toBe('Allowed');
});
test('router authentication needs ownership action and clears entered password', async () => {
  await mount();
  const input = (label: string) =>
    renderer.root
      .findAllByType(TextInput)
      .find(i => i.props.accessibilityLabel === label)!;
  await act(() => {
    input('OpenWrt router HTTPS address').props.onChangeText(
      'https://192.168.10.1',
    );
    input('OpenWrt administrator password').props.onChangeText(
      'never-log-secret',
    );
  });
  expect(
    renderer.root
      .findAllByType(Button)
      .find(b => b.props.title === 'Connect securely and preview')!.props
      .disabled,
  ).toBe(true);
  await press('I own or administer this network');
  await press('Connect securely and preview');
  expect(current!.connect).toHaveBeenCalledWith(
    'https://192.168.10.1',
    'root',
    'never-log-secret',
    true,
  );
  expect(input('OpenWrt administrator password').props.value).toBe('');
});
test('preview requires separate configuration approval and shared rule readiness', async () => {
  current!.snapshot = {
    ...base,
    state: 'preview',
    preview: 'test-preview',
    changes: [
      {
        config: 'dhcp',
        section: 'dns',
        option: 'noresolv',
        before: null,
        after: '1',
      },
    ],
  };
  await mount();
  expect(
    renderer.root
      .findAllByType(Button)
      .find(b => b.props.title === 'Apply Router Protection')!.props.disabled,
  ).toBe(true);
  await press('I own or administer this network');
  await press('I approve these DNS configuration changes');
  expect(
    renderer.root
      .findAllByType(Button)
      .find(b => b.props.title === 'Apply Router Protection')!.props.disabled,
  ).toBe(false);
  await press('Apply Router Protection');
  expect(current!.apply).toHaveBeenCalledTimes(1);
});
test('router warning actions use existing phone rules and stop restores independently', async () => {
  current!.snapshot = {
    ...base,
    state: 'active',
    router: '192.168.10.1',
    enforcementVerified: true,
    history: [
      {
        id: 1,
        kind: 'router_warning',
        domain: 'microsoft.com',
        detail: 'ML warning',
        clientIp: '192.168.10.42',
        decisionSource: 'ml_warning',
        createdAt: Date.now(),
        protection: 'router',
      },
    ],
  };
  save.mockResolvedValue('microsoft.com');
  await mount();
  expect(JSON.stringify(renderer.toJSON())).toContain('NETWORK ACTIVE');
  await press('Block Site');
  expect(save).toHaveBeenCalledWith('microsoft.com', 'block', false);
  expect(current!.sync).toHaveBeenCalledTimes(1);
  await act(async () =>
    renderer.root.findByType(HoldButton).props.onComplete(),
  );
  expect(current!.stop).toHaveBeenCalledTimes(1);
});
test('router API sends credentials in authenticated body without URL or console disclosure', async () => {
  const originalFetch = globalThis.fetch;
  const mock = jest
    .fn()
    .mockResolvedValue({ ok: true, json: async () => base });
  globalThis.fetch = mock;
  try {
    await routerRequest('t'.repeat(40), 'connect', {
      password: 'private-secret',
      routerUrl: 'https://192.168.10.1',
      authorized: true,
    });
    expect(mock.mock.calls[0][0]).not.toContain('private-secret');
    expect(mock.mock.calls[0][1].headers.Authorization).toBe(
      'Bearer ' + 't'.repeat(40),
    );
    expect(mock.mock.calls[0][1].body).toContain('private-secret');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
