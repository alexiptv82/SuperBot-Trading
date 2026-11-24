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
  API.get.mockImplementation(url => (url === '/api/v3/compare' ? Promise.resolve({ data: compare })
    : url.startsWith('/api/v3/compare/') ? Promise.reject(new Error('non usato qui'))
    : url === '/api/v3/paper-archive' ? Promise.resolve({ data: { available: true, runs: [] } })
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

const tabs = el => Array.from(el.querySelectorAll('nav[aria-label="Navigazione principale"] button')).map(b => b.textContent);

test('the main bar has ONLY Brain, Trade, Performance, Archivio; settings and tools live in the separate menu', async () => {
  const s = await open('/brain-unico');
  try {
    expect(tabs(s.el)).toEqual(['🧠Brain', '💹Trade', '📈Performance', '🗄️Archivio']);
    const bar = s.el.querySelector('nav[aria-label="Navigazione principale"]').textContent;
    for (const t of ['Impostazioni', 'Storico', 'Classici', 'Agenti', 'Arena', 'Esci', 'LIVE']) expect(bar).not.toContain(t);
    const menu = s.el.querySelector('button[aria-label="Menu"]');
    expect(menu.getAttribute('aria-expanded')).toBe('false');
    await act(async () => { menu.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
    const dlg = s.el.querySelector('[role="dialog"]');
    for (const t of ['Impostazioni', 'Agenti e supervisione', 'Modalità LIVE', 'Esci']) expect(dlg.textContent).toContain(t);
    const go = Array.from(dlg.querySelectorAll('button')).find(b => b.textContent.includes('Impostazioni'));
    await act(async () => { go.dispatchEvent(new MouseEvent('click', { bubbles: true })); });
    expect(window.location.pathname).toBe('/settings');
    expect(s.el.querySelector('[role="dialog"]')).toBeNull();
  } finally { await s.close(); }
});

test('Trade, Performance and Archivio are the new pages on the current runs; old pages stay reachable from the Archive', async () => {
  const t = await open('/trades');
  try {
    expect(t.el.textContent).toContain('Solo le run attuali');
    expect(API.get.mock.calls.map(c => c[0])).toContain('/api/v3/compare/falco_evoluto/trades?limit=300');
    expect(API.get.mock.calls.map(c => c[0]).some(u => u.startsWith('/api/trades') || u.startsWith('/api/v3/brain/trades'))).toBe(false);
  } finally { await t.close(); }
  const p = await open('/performance');
  try {
    expect(p.el.textContent).toContain('Confronto diretto');
  } finally { await p.close(); }
  const a = await open('/archivio');
  try {
    expect(a.el.textContent).toContain('Sessioni PAPER archiviate');
    expect(a.el.querySelector('a[href="/brain-unico/rc1"]')).not.toBeNull();
    const lit = a.el.querySelector('nav[aria-label="Navigazione principale"] button[aria-current="page"]');
    expect(lit.textContent).toContain('Archivio');
  } finally { await a.close(); }
  const old = await open('/archivio/classici/trade');
  try {
    expect(window.location.pathname).toBe('/archivio/classici/trade');
    const lit = old.el.querySelector('nav[aria-label="Navigazione principale"] button[aria-current="page"]');
    expect(lit.textContent).toContain('Archivio');
  } finally { await old.close(); }
});
