import React from 'react';
import {
  AccessibilityInfo,
  Alert,
  Linking,
  Platform,
  Modal,
  Text,
  TextInput,
} from 'react-native';
import Renderer, { act } from 'react-test-renderer';
import Native from '../specs/NativeBetGuard';
import { BetGuardProvider, useBetGuard } from '../src/state/BetGuardContext';
import { ThemeProvider } from '../src/state/ThemeContext';
import { HomeScreen } from '../src/screens/HomeScreen';
import { CheckScreen } from '../src/screens/CheckScreen';
import { SitesScreen } from '../src/screens/SitesScreen';
import { Button } from '../src/components/ui';
import type { Snapshot, LinkResult } from '../src/state/types';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { Tabs } from '../App';
import { checkCatalog, CatalogError } from '../src/api/catalog';
import { checkDomain } from '../src/api/domain';
import * as apiConfiguration from '../src/api/config';

jest.mock('../src/api/domain', () => ({ checkDomain: jest.fn() }));

jest.mock('../src/api/catalog', () => ({
  ...jest.requireActual('../src/api/catalog'),
  checkCatalog: jest.fn(),
}));

jest.mock('../specs/NativeBetGuard', () => ({
  __esModule: true,
  default: {
    getBridgeVersion: jest.fn(),
    getSnapshot: jest.fn(),
    onSnapshot: jest.fn(),
    startProtection: jest.fn(),
    configureDetection: jest.fn(),
    stopProtection: jest.fn(),
    saveRule: jest.fn(),
    removeRule: jest.fn(),
    checkLink: jest.fn(),
    resolveLink: jest.fn(),
    getThemePreference: jest.fn(),
    setThemePreference: jest.fn(),
    clearHistory: jest.fn(),
  },
}));
let current: ReturnType<typeof useBetGuard>;
let renderer: Renderer.ReactTestRenderer;
let emit: (value: string) => void;
let snapshot: Snapshot;
function Probe() {
  current = useBetGuard();
  return <Text>{current.snapshot?.state}</Text>;
}
const result: LinkResult = {
  domain: 'example.com',
  classification: 'unknown',
  action: 'allow',
  matchedDomain: null,
  reason:
    'No matching manual rule. Default: allow. Classification remains unknown.',
  checkedAt: 1,
};
async function mount(
  home = false,
  check = false,
  navigation?: React.ComponentProps<typeof CheckScreen>['navigation'],
  protection = false,
) {
  const props = {
    navigation: { navigate: jest.fn() },
    route: { key: 'home', name: 'Home' },
  } as unknown as BottomTabScreenProps<Tabs, 'Home'>;
  await act(async () => {
    renderer = Renderer.create(
      <ThemeProvider>
        <BetGuardProvider>
          <Probe />
          {home && <HomeScreen {...props} />}
          {check && <CheckScreen navigation={navigation} />}
          {protection && <SitesScreen />}
        </BetGuardProvider>
      </ThemeProvider>,
    );
  });
}
beforeEach(() => {
  (Native!.getBridgeVersion as jest.Mock).mockReturnValue(2);
  (checkDomain as jest.Mock).mockRejectedValue(new CatalogError('unavailable'));
  (checkCatalog as jest.Mock).mockRejectedValue(
    new CatalogError('unavailable'),
  );
  jest.replaceProperty(Platform, 'OS', 'android');
  jest
    .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
    .mockResolvedValue(true);
  snapshot = {
    state: 'off',
    detail: 'Protection is off.',
    rules: [],
    history: [],
  };
  (Native!.getSnapshot as jest.Mock).mockImplementation(async () =>
    JSON.stringify(snapshot),
  );
  (Native!.onSnapshot as jest.Mock).mockImplementation(callback => {
    emit = callback;
    return { remove: jest.fn() };
  });
  (Native!.getThemePreference as jest.Mock).mockReturnValue('light');
  (Native!.resolveLink as jest.Mock).mockResolvedValue(JSON.stringify(result));
  (Native!.saveRule as jest.Mock).mockResolvedValue('example.com');
  (Native!.removeRule as jest.Mock).mockResolvedValue(undefined);
  (Native!.stopProtection as jest.Mock).mockResolvedValue(undefined);
});
afterEach(async () => {
  if (renderer) await act(() => renderer.unmount());
  jest.restoreAllMocks();
  jest.clearAllMocks();
});
test.each(['failed', 'interrupted', 'off', 'stopping', 'starting'] as const)(
  'Home displays native %s without a success state',
  async state => {
    snapshot = { ...snapshot, state, detail: `Native ${state}` };
    await mount(true);
    const tree = JSON.stringify(renderer.toJSON());
    if (state !== 'off') expect(tree).toContain(`Native ${state}`);
    expect(tree).not.toContain('DNS FILTER RUNNING');
    expect(tree).not.toContain('DNS filter is running');
  },
);
test('late snapshot reads cannot overwrite a newer native stop event', async () => {
  await mount();
  let finish!: (value: string) => void;
  (Native!.getSnapshot as jest.Mock).mockImplementationOnce(
    () =>
      new Promise<string>(resolve => {
        finish = resolve;
      }),
  );
  let refreshing!: Promise<void>;
  await act(() => {
    refreshing = current.refresh();
  });
  await act(() => emit(JSON.stringify({ ...snapshot, state: 'off' })));
  await act(async () => {
    finish(JSON.stringify({ ...snapshot, state: 'active' }));
    await refreshing;
  });
  expect(current.snapshot?.state).toBe('off');
});
test('stopping waits for native off confirmation instead of inventing it', async () => {
  snapshot = { ...snapshot, state: 'active' };
  await mount();
  await act(async () => {
    await current.stop();
  });
  expect(current.snapshot?.state).toBe('active');
  await act(() => emit(JSON.stringify({ ...snapshot, state: 'stopping' })));
  expect(current.snapshot?.state).toBe('stopping');
  await act(() => emit(JSON.stringify({ ...snapshot, state: 'off' })));
  expect(current.snapshot?.state).toBe('off');
});
test('saving reports a setting change, preserves scope, and does not invent DNS history', async () => {
  await mount();
  await act(async () => {
    await current.save('HTTPS://Example.com/path', 'block', true);
  });
  expect(Native!.saveRule).toHaveBeenCalledWith(
    'HTTPS://Example.com/path',
    'block',
    true,
  );
  expect(current.feedback).toContain('Block rule saved');
  expect(current.feedback).toContain('separate from observing');
  expect(current.snapshot?.history).toEqual([]);
  expect(Native!.checkLink).not.toHaveBeenCalled();
});
test('removing an override reports remaining parent policy and never saves Allow', async () => {
  (Native!.resolveLink as jest.Mock).mockResolvedValue(
    JSON.stringify({
      ...result,
      domain: 'help.example.com',
      action: 'block',
      matchedDomain: 'example.com',
      reason: 'Parent rule: block example.com, including subdomains.',
    }),
  );
  await mount();
  await act(async () => {
    await current.remove('help.example.com');
  });
  expect(Native!.removeRule).toHaveBeenCalledWith('help.example.com');
  expect(Native!.saveRule).not.toHaveBeenCalled();
  expect(current.feedback).toContain('Override removed');
  expect(current.feedback).toContain('Parent rule: block');
});
test('native save rejection has no successful feedback', async () => {
  (Native!.saveRule as jest.Mock).mockRejectedValueOnce(
    new Error('Enter a complete hostname.'),
  );
  await mount();
  await act(async () => {
    await current.save('invalid', 'block', false);
  });
  expect(current.feedback).toBeNull();
  expect(current.error).toContain('complete hostname');
});
test('a denied native VPN request remains off and shows its error', async () => {
  (Native!.startProtection as jest.Mock).mockRejectedValueOnce(
    new Error('VPN permission was not granted.'),
  );
  await mount(true);
  await act(async () => {
    await current.start();
  });
  expect(current.snapshot?.state).toBe('off');
  expect(current.error).toContain('permission was not granted');
  expect(JSON.stringify(renderer.toJSON())).not.toContain('DNS FILTER RUNNING');
});

test('manual mode is explicit and online mode uses the existing API address', async () => {
  await mount();
  await act(async () => {
    await current.start();
  });
  expect(Native!.configureDetection).toHaveBeenLastCalledWith('');
  await act(async () => {
    await current.start(true);
  });
  expect(Native!.configureDetection).toHaveBeenLastCalledWith(
    'http://127.0.0.1:8000',
  );
});

test('stale Android bridge disables actions before calling incompatible methods', async () => {
  const log = jest.spyOn(console, 'error').mockImplementation(() => {});
  (Native!.getBridgeVersion as jest.Mock).mockReturnValue(1);
  await mount(true);
  expect(current.available).toBe(false);
  expect(current.error).toContain('match BetGuard');
  await act(async () => {
    await current.start(true);
    await current.check('stake.com');
  });
  expect(Native!.configureDetection).not.toHaveBeenCalled();
  expect(Native!.checkLink).not.toHaveBeenCalled();
  expect(log).toHaveBeenCalled();
});

test('invalid native events cannot display protection as on or crash the screen', async () => {
  jest.spyOn(console, 'error').mockImplementation(() => {});
  await mount(true);
  await act(() =>
    emit(
      JSON.stringify({
        state: 'active',
        detail: 'bad',
        rules: null,
        history: [],
      }),
    ),
  );
  expect(current.snapshot).toBeNull();
  expect(current.error).toContain('protection update');
  expect(JSON.stringify(renderer.toJSON())).not.toContain('DNS protection on');
});

test('technical native failures are logged and translated for users', async () => {
  const log = jest.spyOn(console, 'error').mockImplementation(() => {});
  (Native!.configureDetection as jest.Mock).mockRejectedValueOnce(
    new TypeError('undefined is not a function'),
  );
  await mount(true);
  await act(async () => {
    await current.start(true);
  });
  expect(current.error).toContain('complete that action');
  expect(current.error).not.toContain('undefined');
  expect(current.snapshot?.state).toBe('off');
  expect(log).toHaveBeenCalled();
});

test('warning Continue once opens the checked hostname and never persists a rule', async () => {
  const open = jest.spyOn(Linking, 'openURL').mockResolvedValue(undefined);
  (checkDomain as jest.Mock).mockResolvedValue({
    domain: 'example.com',
    enforcement_action: 'ALLOW',
    intervention: 'WARN',
    risk_status: 'suspicious',
    decision_source: 'ml_warning',
    ml_score: 0.58,
  });
  await checkExample();
  await press('Continue once');
  expect(open).toHaveBeenCalledWith('https://example.com');
  expect(Native!.saveRule).not.toHaveBeenCalled();
  expect(Native!.removeRule).not.toHaveBeenCalled();
});

test('warning Always allow uses the existing rule storage and preserves scope', async () => {
  (checkDomain as jest.Mock).mockResolvedValue({
    domain: 'example.com',
    enforcement_action: 'ALLOW',
    intervention: 'WARN',
    risk_status: 'suspicious',
    decision_source: 'ml_warning',
    ml_score: 0.58,
  });
  snapshot.rules = [
    {
      domain: 'example.com',
      action: 'block',
      includeSubdomains: true,
      updatedAt: 1,
    },
  ];
  await checkExample();
  await press('Always allow');
  expect(Native!.saveRule).toHaveBeenCalledWith('example.com', 'allow', true);
});

test('working ML decision stays visible when the independent catalog is offline', async () => {
  (checkDomain as jest.Mock).mockResolvedValue({
    domain: 'example.com',
    enforcement_action: 'BLOCK',
    intervention: 'BLOCK',
    risk_status: 'verified_gambling',
    decision_source: 'verified_gambling_blocklist',
    ml_score: null,
  });
  await checkExample();
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('DETECTION: BLOCK');
  expect(tree).not.toContain(
    'Online classification is temporarily unavailable',
  );
  expect(tree).not.toContain('verified_gambling_blocklist');
  expect(Native!.saveRule).not.toHaveBeenCalled();
});

test('ML warning uses the existing Notice and does not save a block rule', async () => {
  (checkDomain as jest.Mock).mockResolvedValue({
    domain: 'example.com',
    enforcement_action: 'ALLOW',
    intervention: 'WARN',
    risk_status: 'suspicious',
    decision_source: 'ml_warning',
    ml_score: 0.58,
    matched_domain: null,
    cache_hit: false,
  });
  await checkExample();
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('DETECTION: WARN');
  expect(tree).toContain('characteristics associated with gambling websites');
  expect(tree).toContain('network access remains allowed');
  expect(Native!.saveRule).not.toHaveBeenCalled();
});
test('checked links refresh after native rule changes without recording another link check', async () => {
  (Native!.checkLink as jest.Mock).mockResolvedValue(JSON.stringify(result));
  await mount(false, true);
  await act(() =>
    renderer.root.findByType(TextInput).props.onChangeText('example.com'),
  );
  const checkButton = renderer.root
    .findAllByType(Button)
    .find(button => button.props.title === 'Check link')!;
  await act(async () => {
    checkButton.props.onPress();
  });
  expect(JSON.stringify(renderer.toJSON())).toContain('NO SAVED RULE');
  (Native!.resolveLink as jest.Mock).mockResolvedValue(
    JSON.stringify({
      ...result,
      action: 'block',
      matchedDomain: 'example.com',
      reason: 'Exact hostname rule: block example.com.',
    }),
  );
  await act(async () => {
    emit(
      JSON.stringify({
        ...snapshot,
        rules: [
          {
            domain: 'example.com',
            action: 'block',
            includeSubdomains: false,
            updatedAt: 2,
          },
        ],
      }),
    );
  });
  expect(JSON.stringify(renderer.toJSON())).toContain('EFFECTIVE RULE: BLOCK');
  expect(Native!.checkLink).toHaveBeenCalledTimes(1);
});

async function checkExample() {
  (Native!.checkLink as jest.Mock).mockResolvedValue(JSON.stringify(result));
  await mount(false, true);
  await act(() =>
    renderer.root.findByType(TextInput).props.onChangeText('example.com'),
  );
  await press('Check link');
}
async function press(title: string) {
  await act(async () => {
    renderer.root
      .findAllByType(Button)
      .find(button => button.props.title === title)!
      .props.onPress();
  });
}
const reviewed = {
  hostname: 'example.com',
  classification: 'gambling',
  reason: 'reviewed_catalog',
  source: 'reviewed_catalog',
  explanation:
    'A reviewed catalog classification; this does not establish website safety.',
  label_provenance: 'test review',
  reviewed_at: '2026-01-01T00:00:00Z',
  model_version: null,
  calibrated_probability: null,
};

test('offline catalog preserves local Block and Allow controls and retries without a second local history event', async () => {
  await checkExample();
  await press('Show technical details');
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Online classification is temporarily unavailable',
  );
  await press('Block site');
  expect(Native!.saveRule).toHaveBeenCalledWith('example.com', 'block', false);
  (checkCatalog as jest.Mock).mockResolvedValue(reviewed);
  await press('Retry website check');
  expect(JSON.stringify(renderer.toJSON())).toContain('GAMBLING');
  expect(Native!.checkLink).toHaveBeenCalledTimes(1);
  expect(Native!.saveRule).toHaveBeenCalledTimes(1);
});

test('editing input aborts a lookup and ignores its late response', async () => {
  let finish!: (value: unknown) => void;
  (checkCatalog as jest.Mock).mockImplementation(
    () =>
      new Promise(resolve => {
        finish = resolve;
      }),
  );
  await checkExample();
  const signal = (checkCatalog as jest.Mock).mock.calls[0][1] as AbortSignal;
  await act(() =>
    renderer.root.findByType(TextInput).props.onChangeText('different.test'),
  );
  expect(signal.aborted).toBe(true);
  await act(async () => finish(reviewed));
  expect(JSON.stringify(renderer.toJSON())).not.toContain('GAMBLING');
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'WEBSITE CLASSIFICATION',
  );
  expect(renderer.root.findByType(TextInput).props.value).toBe(
    'different.test',
  );
});

test('cancel and retry suppress a superseded response', async () => {
  let finish!: (value: unknown) => void;
  (checkCatalog as jest.Mock).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        finish = resolve;
      }),
  );
  await checkExample();
  await press('Cancel lookup');
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Website check cancelled',
  );
  (checkCatalog as jest.Mock).mockResolvedValue({
    ...reviewed,
    classification: 'unknown',
    reason: 'not_reviewed',
    source: 'unavailable',
    explanation:
      'This entry has not been reviewed and no validated model is available.',
    reviewed_at: null,
    label_provenance: null,
  });
  await press('Retry website check');
  await act(async () => finish(reviewed));
  await press('Show technical details');
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('CLASSIFICATION UNKNOWN');
  expect(tree).toContain('has not been reviewed');
  expect(tree).not.toContain('test review');
  expect(Native!.saveRule).not.toHaveBeenCalled();
});

test('unmount aborts an outstanding catalog request', async () => {
  (checkCatalog as jest.Mock).mockImplementation(() => new Promise(() => {}));
  await checkExample();
  const signal = (checkCatalog as jest.Mock).mock.calls[0][1] as AbortSignal;
  await act(() => renderer.unmount());
  expect(signal.aborted).toBe(true);
});

test('model classification displays source and version without changing manual rules', async () => {
  (checkCatalog as jest.Mock).mockResolvedValue({
    hostname: 'example.com',
    source: 'model',
    classification: 'non_gambling',
    reason: 'model_prediction',
    explanation: 'A hostname model produced this label; it may be wrong.',
    model_version: 'software-test-v1',
  });
  await checkExample();
  await press('Show technical details');
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Catalog source: ');
  expect(tree).toContain('software-test-v1');
  expect(tree).toContain('NON-GAMBLING');
  expect(tree).toContain('NO SAVED RULE');
  expect(tree).not.toContain('confidence');
  expect(Native!.saveRule).not.toHaveBeenCalled();
  expect(Native!.removeRule).not.toHaveBeenCalled();
});

test('removing a checked override reveals the parent rule without creating an Allow', async () => {
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  snapshot.rules = [
    {
      domain: 'example.com',
      action: 'allow',
      includeSubdomains: false,
      updatedAt: 1,
    },
  ];
  await checkExample();
  (Native!.resolveLink as jest.Mock).mockResolvedValue(
    JSON.stringify({
      ...result,
      action: 'block',
      matchedDomain: 'parent.test',
      reason: 'Parent rule: block parent domain.',
    }),
  );
  await press('Remove override');
  expect(Native!.removeRule).not.toHaveBeenCalled();
  const confirmation = alert.mock.calls[0][2];
  await act(async () => {
    confirmation
      ?.find(button => button.text === 'Remove override')
      ?.onPress?.();
  });
  expect(Native!.removeRule).toHaveBeenCalledWith('example.com');
  expect(Native!.saveRule).not.toHaveBeenCalled();
  expect(JSON.stringify(renderer.toJSON())).toContain('EFFECTIVE RULE: BLOCK');
  expect(Native!.checkLink).toHaveBeenCalledTimes(1);
});

test('keyboard and button duplicate submissions record only one local check', async () => {
  (checkCatalog as jest.Mock).mockImplementation(() => new Promise(() => {}));
  await checkExample();
  await act(() => {
    renderer.root.findByType(TextInput).props.onSubmitEditing();
    renderer.root.findByType(TextInput).props.onSubmitEditing();
  });
  await press('Check link');
  expect(Native!.checkLink).toHaveBeenCalledTimes(1);
  expect(checkCatalog).toHaveBeenCalledTimes(1);
});

test('empty input makes no local check or remote request even via keyboard', async () => {
  await mount(false, true);
  await act(() => renderer.root.findByType(TextInput).props.onSubmitEditing());
  await press('Check link');
  expect(Native!.checkLink).not.toHaveBeenCalled();
  expect(checkCatalog).not.toHaveBeenCalled();
});

test('invalid native input shows validation and makes no remote request', async () => {
  (Native!.checkLink as jest.Mock).mockRejectedValueOnce(
    new Error('Enter a valid website link.'),
  );
  await mount(false, true);
  await act(() =>
    renderer.root
      .findByType(TextInput)
      .props.onChangeText('https://user:password@example.com'),
  );
  await press('Check link');
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Enter a valid website link.',
  );
  expect(checkCatalog).not.toHaveBeenCalled();
});

test('URL reaches native validation but only the returned hostname reaches the API', async () => {
  (Native!.checkLink as jest.Mock).mockResolvedValue(JSON.stringify(result));
  await mount(false, true);
  await act(() =>
    renderer.root
      .findByType(TextInput)
      .props.onChangeText('https://example.com/path?token=private#fragment'),
  );
  await press('Check link');
  expect(Native!.checkLink).toHaveBeenCalledWith(
    'https://example.com/path?token=private#fragment',
  );
  expect(checkCatalog).toHaveBeenCalledWith(
    'example.com',
    expect.any(AbortSignal),
  );
  expect(Native!.checkLink).toHaveBeenCalledTimes(1);
});

test('lookup B wins even when lookup A completes afterwards', async () => {
  let finishA!: (value: unknown) => void;
  (checkCatalog as jest.Mock).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        finishA = resolve;
      }),
  );
  await checkExample();
  await act(() =>
    renderer.root.findByType(TextInput).props.onChangeText('second.test'),
  );
  (Native!.checkLink as jest.Mock).mockResolvedValueOnce(
    JSON.stringify({ ...result, domain: 'second.test' }),
  );
  (Native!.resolveLink as jest.Mock).mockResolvedValue(
    JSON.stringify({ ...result, domain: 'second.test' }),
  );
  (checkCatalog as jest.Mock).mockResolvedValueOnce({
    ...reviewed,
    hostname: 'second.test',
    classification: 'non_gambling',
  });
  await press('Check link');
  await act(() => finishA(reviewed));
  await press('Show technical details');
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('second.test');
  expect(tree).toContain('NON-GAMBLING');
  expect(tree).not.toContain('"GAMBLING"');
  expect(Native!.checkLink).toHaveBeenCalledTimes(2);
});

test('navigation away aborts and suppresses late catalog results', async () => {
  let blur!: () => void;
  const unsubscribe = jest.fn();
  const navigation = {
    addListener: jest.fn((_event: string, listener: () => void) => {
      blur = listener;
      return unsubscribe;
    }),
  } as unknown as React.ComponentProps<typeof CheckScreen>['navigation'];
  let finish!: (value: unknown) => void;
  (checkCatalog as jest.Mock).mockImplementationOnce(
    () =>
      new Promise(resolve => {
        finish = resolve;
      }),
  );
  (Native!.checkLink as jest.Mock).mockResolvedValue(JSON.stringify(result));
  await mount(false, true, navigation);
  await act(() =>
    renderer.root.findByType(TextInput).props.onChangeText('example.com'),
  );
  await press('Check link');
  const signal = (checkCatalog as jest.Mock).mock.calls[0][1] as AbortSignal;
  await act(() => blur());
  await act(() => finish(reviewed));
  expect(signal.aborted).toBe(true);
  expect(JSON.stringify(renderer.toJSON())).toContain(
    'Website check cancelled',
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain('test review');
});

test('absent model is a completed unknown result with no error/retry or policy changes', async () => {
  (checkCatalog as jest.Mock).mockResolvedValue({
    hostname: 'example.com',
    classification: 'unknown',
    source: 'unavailable',
    reason: 'not_in_catalog',
    explanation:
      'No validated model is configured. Classification remains unknown.',
  });
  await checkExample();
  await press('Show technical details');
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('CLASSIFICATION UNKNOWN');
  expect(tree).toContain('No validated model is configured.');
  expect(tree).toContain('Retry website check'); // Independent detection is unavailable in this fixture.
  expect(Native!.saveRule).not.toHaveBeenCalled();
});

test('development readiness is explicit and does not add history', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ status: 'ready', model: 'absent' }),
  });
  try {
    await mount(false, true);
    expect(fetch).not.toHaveBeenCalled();
    await press('Check backend connection');
    expect(JSON.stringify(renderer.toJSON())).toContain('Connected');
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/health/ready',
      expect.objectContaining({ method: 'GET', body: undefined }),
    );
    expect(Native!.checkLink).not.toHaveBeenCalled();
    (fetch as jest.Mock).mockRejectedValueOnce(new TypeError('network'));
    await press('Check backend connection');
    expect(JSON.stringify(renderer.toJSON())).toContain('Unavailable');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('production Check Link does not render the development status control', async () => {
  const previous = __DEV__;
  Object.assign(globalThis, { __DEV__: false });
  try {
    await mount(false, true);
    expect(JSON.stringify(renderer.toJSON())).not.toContain(
      'Check backend connection',
    );
  } finally {
    Object.assign(globalThis, { __DEV__: previous });
  }
});

test('visible Home mode choices start local rules or the configured smart service', async () => {
  (Native!.startProtection as jest.Mock).mockResolvedValue(undefined);
  (Native!.configureDetection as jest.Mock).mockResolvedValue(undefined);
  await mount(true);
  await press('Enable protection');
  expect(Native!.startProtection).not.toHaveBeenCalled();
  await press('Continue to Android permission');
  expect(Native!.configureDetection).toHaveBeenLastCalledWith('');
  const smart = renderer.root
    .findAll(node => node.props.accessibilityRole === 'radio')
    .find(node => node.props.accessibilityLabel === 'Smart protection')!;
  await act(() => smart.props.onPress());
  await press('Enable protection');
  expect(Native!.configureDetection).toHaveBeenLastCalledWith(
    'http://127.0.0.1:8000',
  );
  expect(Native!.startProtection).toHaveBeenCalledTimes(2);
});

test('saved APK without a configured service disables smart mode and checks local rules without HTTP', async () => {
  jest.replaceProperty(apiConfiguration, 'API_BASE_URL', '');
  await mount(true);
  const smart = renderer.root
    .findAll(node => node.props.accessibilityRole === 'radio')
    .find(node => node.props.accessibilityLabel === 'Smart protection')!;
  expect(smart.props.disabled).toBe(true);
  await act(() => renderer.unmount());
  await checkExample();
  expect(checkDomain).not.toHaveBeenCalled();
  expect(checkCatalog).not.toHaveBeenCalled();
  expect(JSON.stringify(renderer.toJSON())).toContain('LOCAL RULE CHECK');
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Retry website check',
  );
});

test('website search, filters and expandable rule actions preserve stored scope', async () => {
  snapshot.rules = [
    {
      domain: 'example.com',
      action: 'block',
      includeSubdomains: true,
      updatedAt: 1,
    },
    {
      domain: 'wikipedia.org',
      action: 'allow',
      includeSubdomains: false,
      updatedAt: 1,
    },
  ];
  await mount(false, false, undefined, true);
  await press('Allowed');
  expect(JSON.stringify(renderer.toJSON())).not.toContain('example.com');
  expect(JSON.stringify(renderer.toJSON())).toContain('wikipedia.org');
  await press('All');
  await act(() =>
    renderer.root.findByType(TextInput).props.onChangeText('EXAMPLE'),
  );
  expect(JSON.stringify(renderer.toJSON())).not.toContain('wikipedia.org');
  const row = renderer.root
    .findAll(
      node => node.props.accessibilityLabel === 'Manage rule for example.com',
    )
    .find(
      node => node.props.accessibilityLabel === 'Manage rule for example.com',
    )!;
  await act(() => row.props.onPress());
  await press('Allow site');
  expect(Native!.saveRule).toHaveBeenCalledWith('example.com', 'allow', true);
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => {});
  await press('Remove rule');
  expect(Native!.removeRule).not.toHaveBeenCalled();
  await act(async () => {
    alert.mock.calls[0][2]
      ?.find(button => button.text === 'Remove override')
      ?.onPress?.();
  });
  expect(Native!.removeRule).toHaveBeenCalledWith('example.com');
});

test('add website sheet closes on successful save and supports Android back dismissal', async () => {
  await mount(false, false, undefined, true);
  await press('Add website');
  const input = renderer.root
    .findAllByType(TextInput)
    .find(
      node => node.props.accessibilityLabel === 'Website link or hostname',
    )!;
  await act(() => input.props.onChangeText('https://example.com/path'));
  await press('Block site');
  expect(Native!.saveRule).toHaveBeenCalledWith(
    'https://example.com/path',
    'block',
    false,
  );
  expect(renderer.root.findAllByType(TextInput)).toHaveLength(1);
  await press('Add website');
  await act(() => renderer.root.findByType(Modal).props.onRequestClose());
  expect(renderer.root.findAllByType(TextInput)).toHaveLength(1);
});

test.each([
  'active',
  'degraded',
  'off',
  'starting',
  'failed',
  'interrupted',
] as const)(
  'premium shield claims Protected only for native active, including %s',
  async state => {
    snapshot.state = state;
    await mount(true);
    const labels = renderer.root
      .findAllByType(Text)
      .map(node => node.props.children);
    expect(labels.includes('Protected')).toBe(state === 'active');
  },
);

test('Check another link clears warning details without changing rules', async () => {
  (checkDomain as jest.Mock).mockResolvedValue({
    domain: 'example.com',
    enforcement_action: 'ALLOW',
    intervention: 'WARN',
    decision_source: 'ml_warning',
    ml_score: 0.58,
  });
  await checkExample();
  await press('Show technical details');
  await press('Check another link');
  expect(JSON.stringify(renderer.toJSON())).not.toContain('Review recommended');
  expect(renderer.root.findByType(TextInput).props.value).toBe('');
  expect(Native!.saveRule).not.toHaveBeenCalled();
});

test('quick guide explains server-free rules and separate checks and closes again', async () => {
  await mount(true);
  await press('How BetGuard works');
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Checking is separate from protecting');
  expect(tree).toContain('not in this APK');
  expect(tree).toContain('browsing websites still needs internet');
  await press('Close quick guide');
  expect(JSON.stringify(renderer.toJSON())).not.toContain(
    'Checking is separate from protecting',
  );
});
