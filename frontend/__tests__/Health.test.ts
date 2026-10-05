import { checkReadiness } from '../src/api/health';
const originalFetch = globalThis.fetch;
beforeEach(() => {
  globalThis.fetch = jest.fn();
});
afterEach(() => {
  globalThis.fetch = originalFetch;
});
test('ready with absent model is connected', async () => {
  (fetch as jest.Mock).mockResolvedValue({
    ok: true,
    json: async () => ({ status: 'ready', model: 'absent' }),
  });
  await expect(
    checkReadiness(new AbortController().signal),
  ).resolves.toBeUndefined();
});
test.each([null, {}, { status: 'ok' }, { status: 'unavailable' }, []])(
  'invalid readiness remains unavailable',
  async data => {
    (fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => data,
    });
    await expect(
      checkReadiness(new AbortController().signal),
    ).rejects.toMatchObject({ code: 'unavailable' });
  },
);
test('503 readiness does not read or expose the error body', async () => {
  const json = jest.fn();
  (fetch as jest.Mock).mockResolvedValue({ ok: false, status: 503, json });
  await expect(
    checkReadiness(new AbortController().signal),
  ).rejects.toMatchObject({ code: 'unavailable' });
  expect(json).not.toHaveBeenCalled();
});
