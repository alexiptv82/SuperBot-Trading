import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import Login from './Login';
import { botAPI } from '../api';
import { isPlatformAuthenticatorAvailable } from '../webauthnClient';

jest.mock('../api', () => ({
  botAPI: {
    webauthnStatus: jest.fn(),
    login: jest.fn(),
    webauthnLoginOptions: jest.fn(),
    webauthnLoginVerify: jest.fn(),
    webauthnRegisterOptions: jest.fn(),
    webauthnRegisterVerify: jest.fn(),
  },
}));
jest.mock('../webauthnClient', () => ({
  isPlatformAuthenticatorAvailable: jest.fn(),
  createCredential: jest.fn(),
  getCredential: jest.fn(),
  deviceLabel: jest.fn(),
  describeWebAuthnError: jest.fn(),
}));

let host;
let root;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement('div');
  document.body.appendChild(host);
  botAPI.webauthnStatus.mockResolvedValue({
    data: { available: true, has_credentials: true },
  });
  isPlatformAuthenticatorAvailable.mockResolvedValue(true);
});
afterEach(async () => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
  }
  host.remove();
  jest.clearAllMocks();
});

async function renderLogin() {
  root = createRoot(host);
  await act(async () => root.render(<Login onLogin={jest.fn()} />));
}

test('biometric entry appears when same-origin API and Android authenticator are available', async () => {
  await renderLogin();
  expect(botAPI.webauthnStatus).toHaveBeenCalledTimes(1);
  expect(isPlatformAuthenticatorAvailable).toHaveBeenCalledTimes(1);
  expect(host.textContent).toContain('Sblocca con impronta digitale');
  expect(host.textContent).toContain('Accedi');
});

test('failure contacting biometric status endpoint hides biometric entry', async () => {
  botAPI.webauthnStatus.mockRejectedValue(new Error('network blocked'));
  await renderLogin();
  expect(host.textContent).not.toContain('Sblocca con impronta digitale');
  expect(host.textContent).toContain('Accedi');
});

test('fingerprint entry hidden when platform authenticator actually absent', async () => {
  isPlatformAuthenticatorAvailable.mockResolvedValue(false);
  await renderLogin();
  expect(host.textContent).not.toContain('Sblocca con impronta digitale');
  expect(host.textContent).toContain('Accedi');
});
