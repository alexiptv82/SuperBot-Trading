import API, { botAPI, resolveBackendBaseURL } from './api';

afterEach(() => jest.restoreAllMocks());

test('production PWA uses same-origin /api when React build variables are missing', () => {
  expect(resolveBackendBaseURL({})).toBe('');
  expect(resolveBackendBaseURL({ REACT_APP_BACKEND_URL: undefined })).toBe('');
  expect(resolveBackendBaseURL({ REACT_APP_API_URL: undefined })).toBe('');
});

test('explicit empty backend URL wins over old secondary override', () => {
  expect(resolveBackendBaseURL({
    REACT_APP_BACKEND_URL: '',
    REACT_APP_API_URL: 'http://unwanted.example',
  })).toBe('');
});

test('dedicated preview may explicitly set a backend URL', () => {
  expect(resolveBackendBaseURL({ REACT_APP_BACKEND_URL: 'http://127.0.0.1:18004' }))
    .toBe('http://127.0.0.1:18004');
  expect(resolveBackendBaseURL({ REACT_APP_API_URL: '/preview' })).toBe('/preview');
});

test('both password and WebAuthn auth methods use Nginx same-origin API routes', async () => {
  const post = jest.spyOn(API, 'post').mockResolvedValue({ data: {} });
  const get = jest.spyOn(API, 'get').mockResolvedValue({ data: {} });
  await botAPI.login('test-password-not-a-real-secret');
  await botAPI.webauthnStatus();
  await botAPI.webauthnLoginOptions();
  expect(post).toHaveBeenNthCalledWith(
    1, '/api/auth/login', { password: 'test-password-not-a-real-secret' },
  );
  expect(get).toHaveBeenCalledWith('/api/auth/webauthn/status');
  expect(post).toHaveBeenNthCalledWith(2, '/api/auth/webauthn/login/options');
});
