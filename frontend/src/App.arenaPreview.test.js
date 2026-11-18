import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import App, { isArenaReadOnlyPreview } from './App';

// Do not mount real pages or talk to any backend in a routing-only unit test.
jest.mock('./pages/BrainArena', () => () => 'ARENA_PREVIEW_TEST_VIEW');
jest.mock('./pages/Dashboard', () => () => 'LEGACY_CLASSIC_CONTROL_PAGE');
jest.mock('./pages/Settings', () => () => 'LEGACY_MUTABLE_SETTINGS_PAGE');
jest.mock('./pages/LiveDashboard', () => () => 'LEGACY_LIVE_PAGE');
jest.mock('./components/NavBar', () => () => 'LEGACY_MODE_TOGGLE');

let container;
let root;
let previous;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  previous = process.env.REACT_APP_PREVIEW_READONLY;
  process.env.REACT_APP_PREVIEW_READONLY = '1';
  sessionStorage.setItem('sb_token', 'test_only_not_real');
  container = document.createElement('div');
  document.body.appendChild(container);
});
afterEach(async () => {
  if (root) {
    await act(async () => root.unmount());
    root = null;
  }
  container.remove();
  sessionStorage.clear();
  if (previous === undefined) delete process.env.REACT_APP_PREVIEW_READONLY;
  else process.env.REACT_APP_PREVIEW_READONLY = previous;
});

async function openAt(path) {
  window.history.pushState({}, '', path);
  root = createRoot(container);
  await act(async () => root.render(<App />));
}

test('read-only flag is an explicit opt-in', () => {
  expect(isArenaReadOnlyPreview({})).toBe(false);
  expect(isArenaReadOnlyPreview({ REACT_APP_PREVIEW_READONLY: '0' })).toBe(false);
  expect(isArenaReadOnlyPreview({ REACT_APP_PREVIEW_READONLY: '1' })).toBe(true);
});

test.each(['/settings', '/classic', '/trades', '/live', '/supervisor'])(
  'isolated Arena preview refuses legacy route %s and LIVE toggle', async path => {
    await openAt(path);
    expect(window.location.pathname).toBe('/arena');
    expect(container.textContent).toContain('ARENA_PREVIEW_TEST_VIEW');
    expect(container.textContent).toContain('nuovi portafogli non avviati');
    expect(container.textContent).toContain('il Brain storico può essere operativo');
    expect(container.textContent).toContain("Esci dall'anteprima");
    expect(container.textContent).not.toContain('LEGACY_CLASSIC_CONTROL_PAGE');
    expect(container.textContent).not.toContain('LEGACY_MUTABLE_SETTINGS_PAGE');
    expect(container.textContent).not.toContain('LEGACY_LIVE_PAGE');
    expect(container.textContent).not.toContain('LEGACY_MODE_TOGGLE');
  },
);

test('read-only preview allows only Arena after existing login', async () => {
  await openAt('/arena');
  expect(container.textContent).toContain('ARENA_PREVIEW_TEST_VIEW');
  expect(container.textContent).not.toContain('LEGACY_MODE_TOGGLE');
});
