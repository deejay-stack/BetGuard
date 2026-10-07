import { checkApplication, visibleApplications } from '../src/api/applications';
import { ApiError } from '../src/api/client';

const metadata = {
  app_name: 'Test fixture',
  package_name: '',
  description: 'Public description',
  keywords: [],
  permissions: [],
  reviews: [],
};
const originalFetch = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = originalFetch;
});
test('app response cannot turn unavailable input into a definitive classification', async () => {
  globalThis.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      classification: 'gambling',
      source: 'unavailable',
      reason: 'absent',
      explanation: 'test',
      enforcement: 'dns_network_only',
    }),
  });
  await expect(
    checkApplication(metadata, new AbortController().signal),
  ).rejects.toBeInstanceOf(ApiError);
});
test('accepts reviewed model result with version and bounded inventory', async () => {
  const response = {
    classification: 'gambling',
    source: 'app_metadata_model',
    reason: 'model_prediction',
    explanation: 'test',
    enforcement: 'dns_network_only',
    model_version: 'test-only',
  };
  globalThis.fetch = jest
    .fn()
    .mockResolvedValue({ ok: true, json: async () => response });
  await expect(
    checkApplication(metadata, new AbortController().signal),
  ).resolves.toEqual(response);
  expect((globalThis.fetch as jest.Mock).mock.calls[0][0]).toContain(
    '/v1/apps/check',
  );
  expect(
    visibleApplications(
      '[{"app_name":"Test","package_name":"test.fixture","permissions":[]}]',
    ),
  ).toHaveLength(1);
  expect(() =>
    visibleApplications(
      '[{"app_name":"Test","package_name":"https://example.com","permissions":[]}]',
    ),
  ).toThrow();
});
test('aborted explicit app review sends no request', async () => {
  globalThis.fetch = jest.fn();
  const controller = new AbortController();
  controller.abort();
  await expect(
    checkApplication(metadata, controller.signal),
  ).rejects.toMatchObject({ code: 'cancelled' });
  expect(globalThis.fetch).not.toHaveBeenCalled();
});
