import React from 'react';
import Renderer, { act } from 'react-test-renderer';
import { AccessibilityInfo, Platform, Text } from 'react-native';
import Native from '../specs/NativeBetGuard';
import { BetGuardProvider } from '../src/state/BetGuardContext';
import { ThemeProvider } from '../src/state/ThemeContext';
import {
  NetworkProtectionProvider,
  readNetworkSnapshot,
  type NetworkSnapshot,
} from '../src/state/NetworkProtectionContext';
import { NetworkProtectionScreen } from '../src/screens/NetworkProtectionScreen';
import { Button } from '../src/components/ui';
import { HoldButton } from '../src/components/HoldButton';
import { ActivityRow, activityKind } from '../src/components/ActivityRow';
import type { Snapshot } from '../src/state/types';

jest.mock('../specs/NativeBetGuard', () => ({
  __esModule: true,
  default: {
    getBridgeVersion: jest.fn(() => 2),
    getSnapshot: jest.fn(),
    onSnapshot: jest.fn(),
    configureDetection: jest.fn(),
    startProtection: jest.fn(),
    stopProtection: jest.fn(),
    saveRule: jest.fn(),
    removeRule: jest.fn(),
    checkLink: jest.fn(),
    resolveLink: jest.fn(),
    clearHistory: jest.fn(),
    getThemePreference: jest.fn(() => 'system'),
    setThemePreference: jest.fn(),
    getNetworkSnapshot: jest.fn(),
    startNetworkProtection: jest.fn(),
    stopNetworkProtection: jest.fn(),
    onNetworkSnapshot: jest.fn(),
  },
}));
let renderer: Renderer.ReactTestRenderer;
let emit: (raw: string) => void;
let device: Snapshot;
const network: NetworkSnapshot = {
  state: 'active',
  detail: 'Gateway listening',
  address: '192.168.43.1',
  port: 8080,
  interfaceName: 'ap0',
  interfaces: [
    { address: '192.168.43.1', prefixLength: 24, interfaceName: 'ap0' },
  ],
  runtime: 'ready',
  startedAt: 1,
  requests: 3,
  allowed: 2,
  blocked: 1,
  warnings: 1,
  errors: 0,
  rejected: 0,
  clients: [
    {
      ip: '192.168.43.25',
      firstSeen: 1,
      lastActivity: 2,
      requests: 3,
      blocked: 1,
      warnings: 1,
      connections: 1,
    },
  ],
};
beforeEach(() => {
  jest.clearAllMocks();
  jest.replaceProperty(Platform, 'OS', 'android');
  jest.spyOn(AccessibilityInfo, 'isReduceMotionEnabled').mockResolvedValue(true);
  device = {
    state: 'off',
    detail: 'Off',
    rules: [],
    history: [
      {
        id: 1,
        kind: 'network_warning',
        domain: 'microsoft.com',
        clientIp: '192.168.43.25',
        decisionSource: 'ml_warning',
        protection: 'network',
        detail: 'Uncertain model warning; access allowed.',
        createdAt: Date.now(),
      },
    ],
  };
  (Native!.getSnapshot as jest.Mock).mockImplementation(async () =>
    JSON.stringify(device),
  );
  (Native!.getNetworkSnapshot as jest.Mock).mockResolvedValue(
    JSON.stringify(network),
  );
  (Native!.onSnapshot as jest.Mock).mockReturnValue({ remove: jest.fn() });
  (Native!.onNetworkSnapshot as jest.Mock).mockImplementation(callback => {
    emit = callback;
    return { remove: jest.fn() };
  });
  (Native!.resolveLink as jest.Mock).mockImplementation(
    async (domain: string) =>
      JSON.stringify({
        domain,
        classification: 'unknown',
        action: 'block',
        matchedDomain: domain,
        reason: 'Saved block rule',
        checkedAt: 1,
      }),
  );
  (Native!.saveRule as jest.Mock).mockImplementation(
    async (
      domain: string,
      action: 'block' | 'allow',
      includeSubdomains: boolean,
    ) => {
      device.rules = [{ domain, action, includeSubdomains, updatedAt: 1 }];
      return domain;
    },
  );
});
async function mount() {
  await act(async () => {
    renderer = Renderer.create(
      <ThemeProvider>
        <BetGuardProvider>
          <NetworkProtectionProvider>
            <NetworkProtectionScreen />
          </NetworkProtectionProvider>
        </BetGuardProvider>
      </ThemeProvider>,
    );
  });
}
afterEach(async () => {
  if (renderer) await act(async () => renderer.unmount());
  jest.restoreAllMocks();
});
test('network snapshot refuses fake active endpoints and invalid client counts', () => {
  expect(readNetworkSnapshot(JSON.stringify(network))).toEqual(network);
  expect(() =>
    readNetworkSnapshot(JSON.stringify({ ...network, address: null })),
  ).toThrow();
  expect(() =>
    readNetworkSnapshot(JSON.stringify({ ...network, requests: -1 })),
  ).toThrow();
  expect(() =>
    readNetworkSnapshot(
      JSON.stringify({
        ...network,
        clients: [{ ...network.clients[0], ip: '999.0.0.1' }],
      }),
    ),
  ).toThrow();
});
test('network WARN review saves through existing device rules and does not automatically block', async () => {
  await mount();
  expect(Native!.saveRule).not.toHaveBeenCalled();
  expect(JSON.stringify(renderer.toJSON())).toContain('REVIEW · ALLOWED');
  expect(JSON.stringify(renderer.toJSON())).toContain('192.168.43.25');
  await act(async () =>
    renderer.root
      .findAllByType(Button)
      .find(row => row.props.title === 'Block Site')!
      .props.onPress(),
  );
  expect(Native!.saveRule).toHaveBeenCalledWith(
    'microsoft.com',
    'block',
    false,
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain('REVIEW · ALLOWED');
});
test('gateway stop uses the separate service and real-time failures clear the listening address', async () => {
  await mount();
  const hold = renderer.root.findByType(HoldButton);
  expect(hold.props.title).toBe('Hold to stop Network Protection');
  await act(async () => hold.props.onComplete());
  expect(Native!.stopNetworkProtection).toHaveBeenCalledTimes(1);
  expect(Native!.stopProtection).not.toHaveBeenCalled();
  await act(async () =>
    emit(
      JSON.stringify({
        ...network,
        state: 'interrupted',
        address: null,
        port: 0,
        clients: [],
        detail: 'Address changed',
      }),
    ),
  );
  expect(JSON.stringify(renderer.toJSON())).toContain('Gateway interrupted');
});
test('network activity distinguishes client identity and proxy outcomes from device DNS', async () => {
  expect(activityKind('network_blocked')).toBe('Blocked');
  expect(activityKind('network_warning')).toBe('Warnings');
  expect(activityKind('network_allowed')).toBe('Allowed');
  expect(activityKind('network_error')).toBe('Other');
  await act(async () => {
    renderer = Renderer.create(
      <ThemeProvider>
        <ActivityRow item={device.history[0]} />
      </ThemeProvider>,
    );
  });
  const labels = renderer.root
    .findAllByType(Text)
    .map(row => row.props.children);
  expect(JSON.stringify(labels)).toContain('NETWORK');
  expect(JSON.stringify(labels)).toContain('192.168.43.25');
});
