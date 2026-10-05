import { resolveApiBaseUrl } from '../src/api/config';

const settings = { developmentTarget: 'device', remoteBaseUrl: '' };

test.each([
  ['device', 'http://127.0.0.1:8000'],
  ['emulator', 'http://10.0.2.2:8000'],
  ['remote', ''],
  ['invalid', ''],
])(
  'development target %s resolves without a fabricated remote',
  (target, expected) => {
    expect(
      resolveApiBaseUrl({ ...settings, developmentTarget: target }, true),
    ).toBe(expected);
  },
);

test.each(['device', 'emulator', 'remote'])(
  'release ignores local target %s',
  target => {
    expect(
      resolveApiBaseUrl({ ...settings, developmentTarget: target }, false),
    ).toBe('');
    expect(
      resolveApiBaseUrl(
        {
          developmentTarget: target,
          remoteBaseUrl: 'https://api.example.test/',
        },
        false,
      ),
    ).toBe('https://api.example.test');
  },
);

test.each([
  'http://127.0.0.1:8000',
  'http://10.0.2.2:8000',
  'https://user:password@example.test',
  'https://example.test?secret=1',
])('release rejects unsuitable address %s', remoteBaseUrl => {
  expect(resolveApiBaseUrl({ ...settings, remoteBaseUrl }, false)).toBe('');
});

test('unconfigured service makes no HTTP request', async () => {
  jest.resetModules();
  jest.doMock('../api.config.json', () => ({
    developmentTarget: 'remote',
    remoteBaseUrl: '',
  }));
  const { checkCatalog } = require('../src/api/catalog');
  const originalFetch = globalThis.fetch;
  globalThis.fetch = jest.fn();
  try {
    await expect(
      checkCatalog('example.test', new AbortController().signal),
    ).rejects.toMatchObject({ code: 'configuration' });
    expect(fetch).not.toHaveBeenCalled();
  } finally {
    globalThis.fetch = originalFetch;
    jest.dontMock('../api.config.json');
    jest.resetModules();
  }
});
