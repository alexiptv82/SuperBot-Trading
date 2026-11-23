import React from 'react';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import API from './api';
import App from './App';

// Routing REALE dell'app (BrowserRouter, stesse rotte): quale schermata compare a quale indirizzo.
jest.mock('./api', () => {
  const get = jest.fn();
  const post = jest.fn();
  return { __esModule: true, default: { get, post }, botAPI: { passwordStatus: () => Promise.resolve({ data: {} }) },
    deskAPI: { getStatus: jest.fn(), getPrices: jest.fn() }, bullAPI: { getStatus: jest.fn() }, brainAPI: {},
    errMsg: () => 'errore' };
});

const compare = { available: true, generated_at_ms: Date.now(), runs: [
  { name: 'falco_evoluto', label: 'Falco Evoluto', available: true, state: 'running', paused: false, initial_equity: '1000',
    settled_equity: '1000', open_positions: [], decisions: [], config: { cycle_minutes: 15 } },
  { name: 'brain_scalp', label: 'Brain Scalp', available: true, state: 'running', paused: true, initial_equity: '2000',
    settled_equity: '2000', open_positions: [], decisions: [], config: { cycle_minutes: 30 } }] };

async function open(path) {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  window.history.pushState({}, '', path);
  sessionStorage.setItem('sb_token', 'test-token');
  API.get.mockImplementation(url => (url.startsWith('/api/v3/compare') ? Promise.resolve({ data: compare })
    : Promise.resolve({ data: { portfolios: [], state: 'not_started' } })));
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(<App />); });
  return { el, close: async () => { await act(async () => { root.unmount(); }); el.remove(); sessionStorage.clear(); API.get.mockReset(); } };
}

test('the main Brain screen (/brain-unico and /) shows Falco Evoluto and Brain Scalp, not RC1', async () => {
  for (const path of ['/brain-unico', '/']) {
    const s = await open(path);
    try {
      expect(window.location.pathname).toBe('/brain-unico');
      expect(s.el.textContent).toContain('Falco Evoluto');
      expect(s.el.textContent).toContain('Brain Scalp');
      expect(s.el.textContent).toContain('RUNNING');
      expect(s.el.textContent).toContain('PAUSA');
      expect(s.el.textContent).not.toContain('Brain Unico');
      expect(API.get.mock.calls.map(c => c[0])).toContain('/api/v3/compare');
      expect(API.get.mock.calls.map(c => c[0])).not.toContain('/api/v3/brain/status');   // niente dati di RC1 qui
    } finally { await s.close(); }
  }
});

test('Brain RC1 stays available at /brain-unico/rc1 with its own data, and the compare page is untouched', async () => {
  const rc1 = await open('/brain-unico/rc1');
  try {
    expect(rc1.el.textContent).toContain('Brain Unico');
    expect(API.get.mock.calls.map(c => c[0])).toContain('/api/v3/brain/status');
  } finally { await rc1.close(); }
  const cmp = await open('/compare');
  try {
    expect(cmp.el.textContent).toContain('Confronto');
  } finally { await cmp.close(); }
});
