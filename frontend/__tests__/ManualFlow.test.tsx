import React from 'react';
import { AccessibilityInfo, Platform, Text, TextInput } from 'react-native';
import Renderer, { act } from 'react-test-renderer';
import Native from '../specs/NativeBetGuard';
import { BetGuardProvider, useBetGuard } from '../src/state/BetGuardContext';
import { ThemeProvider } from '../src/state/ThemeContext';
import { HomeScreen } from '../src/screens/HomeScreen';
import { CheckScreen } from '../src/screens/CheckScreen';
import { Button } from '../src/components/ui';
import type { Snapshot, LinkResult } from '../src/state/types';
import type { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import type { Tabs } from '../App';
import { checkCatalog, CatalogError } from '../src/api/catalog';
import { checkDomain } from '../src/api/domain';

jest.mock('../src/api/domain', () => ({ checkDomain: jest.fn() }));

jest.mock('../src/api/catalog', () => ({
  ...jest.requireActual('../src/api/catalog'),
  checkCatalog: jest.fn(),
}));

jest.mock('../specs/NativeBetGuard', () => ({
  __esModule: true,
  default: {
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
        </BetGuardProvider>
      </ThemeProvider>,
    );
  });
}
beforeEach(() => {
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
    expect(tree).toContain(`Native ${state}`);
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
  await act(async () => { await current.start(); });
  expect(Native!.configureDetection).toHaveBeenLastCalledWith('');
  await act(async () => { await current.start(true); });
  expect(Native!.configureDetection).toHaveBeenLastCalledWith('http://127.0.0.1:8000');
});

test('ML warning uses the existing Notice and does not save a block rule', async () => {
  (checkDomain as jest.Mock).mockResolvedValue({
    domain: 'example.com', enforcement_action: 'ALLOW', intervention: 'WARN',
    risk_status: 'suspicious', decision_source: 'ml_warning', ml_score: 0.58,
    matched_domain: null, cache_hit: false,
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
  expect(JSON.stringify(renderer.toJSON())).toContain('EFFECTIVE RULE: ALLOW');
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
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('Source: model');
  expect(tree).toContain('software-test-v1');
  expect(tree).toContain('Classified as non-gambling.');
  expect(tree).toContain('EFFECTIVE RULE: ALLOW');
  expect(tree).not.toContain('confidence');
  expect(Native!.saveRule).not.toHaveBeenCalled();
  expect(Native!.removeRule).not.toHaveBeenCalled();
});

test('removing a checked override reveals the parent rule without creating an Allow', async () => {
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
      reason: 'Parent rule: block parent domain.',
    }),
  );
  await press('Remove override');
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
  const tree = JSON.stringify(renderer.toJSON());
  expect(tree).toContain('CLASSIFICATION UNKNOWN');
  expect(tree).toContain('No validated model is configured.');
  expect(tree).not.toContain('Retry website check');
  expect(Native!.saveRule).not.toHaveBeenCalled();
});

test('development readiness is explicit and does not add history', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = jest
    .fn()
    .mockResolvedValue({
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
