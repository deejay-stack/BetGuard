import {
  CatalogError,
  checkCatalog,
  REQUEST_TIMEOUT_MS,
} from '../src/api/catalog';

const unknown = {
  hostname: 'example.test',
  classification: 'unknown',
  reason: 'not_in_catalog',
  source: 'unavailable',
  explanation: 'No reviewed entry and no validated model are available.',
  label_provenance: null,
  reviewed_at: null,
  model_version: null,
  calibrated_probability: null,
};
beforeEach(() => {
  globalThis.fetch = jest.fn();
});
afterEach(() => {
  jest.useRealTimers();
  jest.restoreAllMocks();
});

test('sends a hostname to FastAPI and accepts an honest unknown result', async () => {
  (fetch as jest.Mock).mockResolvedValue({
    ok: true,
    json: async () => unknown,
  });
  expect(
    await checkCatalog('example.test', new AbortController().signal),
  ).toEqual(unknown);
  expect(fetch).toHaveBeenCalledWith(
    'http://127.0.0.1:8000/v1/check',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ hostname: 'example.test' }),
    }),
  );
});

test.each([503, 500, 429, 422])(
  'HTTP %s remains an error, never an unknown classification',
  async status => {
    (fetch as jest.Mock).mockResolvedValue({ ok: false, status });
    await expect(
      checkCatalog('example.test', new AbortController().signal),
    ).rejects.toMatchObject({
      code: status === 422 ? 'invalid' : 'unavailable',
    });
  },
);

test.each([
  { ...unknown, hostname: 'another.test' },
  { ...unknown, classification: 'gambling' },
  { ...unknown, classification: 'safe' },
  {
    ...unknown,
    classification: 'gambling',
    reason: 'reviewed_catalog',
    source: 'reviewed_catalog',
    reviewed_at: 'invalid',
  },
  null,
])('rejects malformed or unreviewed definitive responses', async data => {
  (fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => data });
  await expect(
    checkCatalog('example.test', new AbortController().signal),
  ).rejects.toEqual(new CatalogError('unavailable'));
});

test('accepts a reviewed classification without confidence scores', async () => {
  const data = {
    ...unknown,
    classification: 'gambling',
    reason: 'reviewed_catalog',
    source: 'reviewed_catalog',
    reviewed_at: '2026-01-01T00:00:00Z',
    label_provenance: 'test review',
  };
  (fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => data });
  expect(
    await checkCatalog('example.test', new AbortController().signal),
  ).toEqual(data);
});

test('times out even when the transport ignores abort', async () => {
  jest.useFakeTimers();
  (fetch as jest.Mock).mockReturnValue(new Promise(() => {}));
  const pending = checkCatalog('example.test', new AbortController().signal);
  const outcome = pending.catch(error => error);
  await jest.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);
  expect(await outcome).toMatchObject({ code: 'timeout' });
  expect((fetch as jest.Mock).mock.calls[0][1].signal.aborted).toBe(true);
  expect(jest.getTimerCount()).toBe(0);
});

test('cancels in flight and never starts a pre-cancelled request', async () => {
  (fetch as jest.Mock).mockReturnValue(new Promise(() => {}));
  const controller = new AbortController();
  const pending = checkCatalog('example.test', controller.signal);
  controller.abort();
  await expect(pending).rejects.toMatchObject({ code: 'cancelled' });
  await expect(
    checkCatalog('example.test', controller.signal),
  ).rejects.toMatchObject({ code: 'cancelled' });
  expect(fetch).toHaveBeenCalledTimes(1);
});

test.each([
  {
    hostname: 'example.test',
    classification: 'non_gambling',
    source: 'model',
    reason: 'model_prediction',
    explanation: 'Hostname model classification.',
    model_version: 'fixture-v1',
  },
  {
    hostname: 'example.test',
    classification: 'unknown',
    source: 'model',
    reason: 'model_abstained',
    explanation: 'Insufficient evidence.',
    model_version: 'fixture-v1',
  },
  {
    hostname: 'example.test',
    classification: 'unknown',
    source: 'unavailable',
    reason: 'not_in_catalog',
    explanation: 'No validated model is configured.',
  },
])(
  'accepts source-specific responses with inapplicable metadata omitted',
  async data => {
    (fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => data,
    });
    expect(
      await checkCatalog('example.test', new AbortController().signal),
    ).toEqual(data);
  },
);

test.each([
  {
    ...unknown,
    source: 'model',
    reason: 'model_prediction',
    classification: 'gambling',
  },
  {
    ...unknown,
    source: 'model',
    reason: 'model_abstained',
    classification: 'gambling',
    model_version: 'v1',
  },
  { ...unknown, calibrated_probability: 0.99 },
  {
    ...unknown,
    source: 'reviewed_catalog',
    reason: 'model_prediction',
    model_version: 'v1',
  },
])(
  'rejects invalid model/source contracts and uncalibrated confidence',
  async data => {
    (fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => data,
    });
    await expect(
      checkCatalog('example.test', new AbortController().signal),
    ).rejects.toMatchObject({ code: 'unavailable' });
  },
);

test.each([
  '',
  'https://example.test/private?token=secret',
  'example.test/path',
  'user:password@example.test',
  '127.0.0.1',
  '[::1]',
  'EXAMPLE.test',
  'bad..test',
  'ftp://example.test',
  'example.test#fragment',
])(
  'service boundary rejects non-normalized input without sending it: %s',
  async hostname => {
    await expect(
      checkCatalog(hostname, new AbortController().signal),
    ).rejects.toMatchObject({ code: 'invalid' });
    expect(fetch).not.toHaveBeenCalled();
  },
);

test.each([
  new TypeError('connection refused'),
  new SyntaxError('private server error'),
])('network and JSON failures are sanitized', async error => {
  (fetch as jest.Mock).mockImplementation(async () => {
    if (error instanceof TypeError) throw error;
    return {
      ok: true,
      json: async () => {
        throw error;
      },
    };
  });
  await expect(
    checkCatalog('example.test', new AbortController().signal),
  ).rejects.toEqual(new CatalogError('unavailable'));
});

test('timeout covers a response whose JSON body never arrives', async () => {
  jest.useFakeTimers();
  (fetch as jest.Mock).mockResolvedValue({
    ok: true,
    json: () => new Promise(() => {}),
  });
  const outcome = checkCatalog(
    'example.test',
    new AbortController().signal,
  ).catch(error => error);
  await jest.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);
  expect(await outcome).toMatchObject({ code: 'timeout' });
  expect(jest.getTimerCount()).toBe(0);
});

test.each([
  'not JSON',
  17,
  [],
  {},
  { ...unknown, explanation: 12 },
  { ...unknown, source: 'mystery' },
])(
  'untrusted response values fail closed without escaping exceptions',
  async data => {
    (fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => data,
    });
    await expect(
      checkCatalog('example.test', new AbortController().signal),
    ).rejects.toMatchObject({ code: 'unavailable' });
  },
);

test('future model probability follows backend type without creating UI confidence claims', async () => {
  const data = {
    ...unknown,
    source: 'model',
    classification: 'gambling',
    reason: 'model_prediction',
    model_version: 'test-contract',
    calibrated_probability: 0.9,
  };
  (fetch as jest.Mock).mockResolvedValue({ ok: true, json: async () => data });
  expect(
    await checkCatalog('example.test', new AbortController().signal),
  ).toEqual(data);
});
