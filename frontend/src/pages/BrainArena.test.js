import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import API from '../api';
import BrainArena from './BrainArena';

jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn() } }));

const BRAIN = {
  generated_at_ms: 1794916800000,
  portfolios: [
    { id: 'falco', state: 'running', realized_pnl: '500' },
    { id: 'brain', state: 'running', realized_pnl: '12.45',
      settled_equity: '2012.45', equity: null, equity_basis: 'open_unmarked',
      total_closed: 4, win_rate: '50', open_positions: 1 },
  ],
};
const TRADES = {
  open_positions: [
    { position_id: 'p1', symbol: 'DOGEUSDT', side: 1,
      entry: '0.15', stop: '0.14', leverage: 20, margin: '200',
      price: '0.16', price_source: 'ticker',
      unrealized_pnl: '9.40', roi_pct: '4.7' },
  ],
  closed_trades: [
    { position_id: 'p0', symbol: 'SOLUSDT', side: -1,
      entry: '150', exit: '149', leverage: 20, margin: '200',
      realized_pnl: '12.45' },
  ],
};
function inputs(ok = true) {
  API.get.mockImplementation((url) => {
    if (!ok) return Promise.reject(new Error('offline'));
    if (url === '/api/v3/overview') return Promise.resolve({ data: BRAIN });
    if (url === '/api/v3/brain/status') return Promise.resolve({ data: { state: 'running' } });
    if (url === '/api/v3/brain/trades?limit=100') return Promise.resolve({ data: TRADES });
    throw new Error('UNEXPECTED_ENDPOINT_' + url);
  });
}
async function mount() {
  const node = document.createElement('div');
  document.body.appendChild(node);
  const root = createRoot(node);
  await act(async () => { root.render(<BrainArena />); });
  return { node, dispose: async () => {
    await act(async () => { root.unmount(); });
    node.remove();
  } };
}
// The deployed UI fetches /api/v3/arena when its build flag is enabled.
// Legacy-only tests below explicitly run with that optional route disabled;
// trial-specific tests opt in via withFlags() and verify the extra GET.
const originalShadowApiFlag = process.env.REACT_APP_BRAIN_ARENA_SHADOW_API;
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  process.env.REACT_APP_BRAIN_ARENA_SHADOW_API = '0';
  inputs();
});
afterEach(() => {
  API.get.mockReset();
  if (originalShadowApiFlag === undefined) delete process.env.REACT_APP_BRAIN_ARENA_SHADOW_API;
  else process.env.REACT_APP_BRAIN_ARENA_SHADOW_API = originalShadowApiFlag;
});

test('standalone SSR dashboard has exactly three choices and no invented trial result', () => {
  const html = renderToStaticMarkup(<BrainArena />);
  expect(html).toContain('DeepSeek');
  expect(html).toContain('Qwen');
  expect(html).toContain('MiniMax');
  expect(html).toContain('in attesa di attivazione comune');
  expect(html).toContain('Non avviato');
  expect(html).toContain('PnL del test comune');
  expect(html).not.toContain('P&L totale 0');
});

test('DeepSeek old-paper data and marked open PnL appear without mixing with Qwen or MiniMax', async () => {
  const { node, dispose } = await mount();
  try {
    expect(node.textContent).toContain('Storico precedente');
    expect(node.textContent).toContain('12,45 USDT');
    expect(node.textContent).toContain('9,40 USDT');
    expect(node.textContent).toContain('Saldo contabile');
    // CLDR/ICU versions can differ on grouping for 4-digit Italian numbers.
    // Both 2012,45 and 2.012,45 represent the same exact displayed amount.
    expect(node.textContent).toMatch(/2[.\u00a0\u202f]?012,45 USDT/);
    expect(node.textContent).toContain('Non calcolabile');
    expect(node.textContent).toContain('PnL del test comune: —');
    expect(API.get.mock.calls.map(([url]) => url)).toEqual([
      '/api/v3/overview',
      '/api/v3/brain/status',
      '/api/v3/brain/trades?limit=100',
    ]);
    expect(API.post).toBeUndefined();
    const buttons = Array.from(node.querySelectorAll('button[aria-pressed]'));
    expect(buttons).toHaveLength(3);
    const qwen = buttons.find(b => b.textContent.includes('Qwen'));
    await act(async () => { qwen.click(); });
    expect(node.textContent).toContain('Portafoglio non ancora disponibile');
    expect(node.textContent).not.toContain('9,40 USDT');
    expect(node.textContent).not.toContain('Prezzo disponibile:');
  } finally { await dispose(); }
});

test('GET failure never shows fake historic profit or opens trade API', async () => {
  inputs(false);
  const { node, dispose } = await mount();
  try {
    expect(node.textContent).toContain('Il Brain PAPER attuale non risponde');
    expect(node.textContent).not.toContain('12,45 USDT');
    expect(API.get).toHaveBeenCalledTimes(3);
  } finally { await dispose(); }
});

// Manual closing is explicit opt-in for the legacy DeepSeek only.  The test
// does not send a POST; the provider-specific trial services are not installed.
test('Arena never exposes an active close button without both flags', async () => {
  const original = BRAIN.portfolios[1].manual_close_allowed;
  BRAIN.portfolios[1].manual_close_allowed = true;
  const { node, dispose } = await mount();
  try {
    const posTab = Array.from(node.querySelectorAll('button')).find(x => x.textContent === 'Posizioni aperte');
    await act(async () => { posTab.click(); });
    const close = Array.from(node.querySelectorAll('button')).find(x => x.textContent === 'Chiudi DOGEUSDT');
    expect(close).toBeDefined();
    expect(close.disabled).toBe(true);
    expect(node.textContent).not.toContain('Chiudi tutte');
  } finally {
    await dispose();
    BRAIN.portfolios[1].manual_close_allowed = original;
  }
});

test('legacy DeepSeek close requires separately certified backend and explicit UI opt-in', async () => {
  const prior = process.env.REACT_APP_ARENA_EXISTING_CLOSE;
  const original = BRAIN.portfolios[1].manual_close_allowed;
  process.env.REACT_APP_ARENA_EXISTING_CLOSE = '1';
  BRAIN.portfolios[1].manual_close_allowed = true;
  const { node, dispose } = await mount();
  try {
    const posTab = Array.from(node.querySelectorAll('button')).find(x => x.textContent === 'Posizioni aperte');
    await act(async () => { posTab.click(); });
    const close = Array.from(node.querySelectorAll('button')).find(x => x.textContent === 'Chiudi DOGEUSDT');
    expect(close).toBeDefined();
    expect(close.disabled).toBe(false);
    expect(API.get).toHaveBeenCalledTimes(3);
  } finally {
    await dispose();
    BRAIN.portfolios[1].manual_close_allowed = original;
    if (prior === undefined) delete process.env.REACT_APP_ARENA_EXISTING_CLOSE;
    else process.env.REACT_APP_ARENA_EXISTING_CLOSE = prior;
  }
});

test('Memory view does not invent historical learning statistics', async () => {
  const { node, dispose } = await mount();
  try {
    const tab = Array.from(node.querySelectorAll('button')).find(x => x.textContent === 'Memoria');
    expect(tab).toBeDefined();
    await act(async () => { tab.click(); });
    expect(node.textContent).toContain('Registro delle esperienze');
    expect(node.textContent).toContain('NO_TRADE registrati');
    expect(node.textContent).toContain('Memoria operativa non ancora certificata');
    expect(node.textContent).toContain('Nessuna strategia viene modificata automaticamente');
    expect(node.textContent).not.toContain('42');
  } finally { await dispose(); }
});

// Esperimento: i controlli per AI compaiono solo con entrambi i flag UI e i dati delle rotte dedicate.
const QWEN = { portfolio_id: 'qwen', mode: 'paper', state: 'running', initial_capital: 2000,
  source: 'arena_independent_journal_v1', run_id: 'brain-qwen-paper20261118', realized_pnl: '0',
  open_count: 1, open_positions: [{ position_id: 'q1', symbol: 'ETHUSDT', side: -1, leverage: 20 }],
  closed_trades: [], decision_count: 3, no_trade_count: 2 };
function trialInputs(annotationsOk = true) {
  API.get.mockImplementation((url) => {
    if (url === '/api/v3/overview') return Promise.resolve({ data: BRAIN });
    if (url === '/api/v3/brain/status') return Promise.resolve({ data: { state: 'running' } });
    if (url === '/api/v3/brain/trades?limit=100') return Promise.resolve({ data: TRADES });
    if (url === '/api/v3/arena') return Promise.resolve({ data: { portfolios: { qwen: QWEN } } });
    if (url === '/api/v3/arena/qwen/annotations') {
      return annotationsOk
        ? Promise.resolve({ data: { ok: true, provider: 'qwen', manual_close_ready: true,
            annotations: [{ position_id: 'q0', reason: 'trend_change' }] } })
        : Promise.reject(new Error('404'));
    }
    throw new Error('UNEXPECTED_ENDPOINT_' + url);
  });
}
async function withFlags(flags, fn) {
  const prior = {};
  for (const [k, v] of Object.entries(flags)) { prior[k] = process.env[k]; process.env[k] = v; }
  try { await fn(); } finally {
    for (const k of Object.keys(flags)) {
      if (prior[k] === undefined) delete process.env[k]; else process.env[k] = prior[k];
    }
  }
}
const click = async (node, text) => {
  const b = Array.from(node.querySelectorAll('button')).find(x => x.textContent.includes(text));
  await act(async () => { b.click(); });
};

test('Qwen trial wallet gets its own close controls and reason count only with both flags', async () => {
  await withFlags({ REACT_APP_BRAIN_ARENA_SHADOW_API: '1', REACT_APP_ARENA_MANUAL_CLOSE: '1' }, async () => {
    trialInputs();
    const { node, dispose } = await mount();
    try {
      await click(node, 'Qwen');
      await click(node, 'Posizioni aperte');
      const close = Array.from(node.querySelectorAll('button')).find(x => x.textContent.trim() === 'Chiudi ETHUSDT');
      expect(close).toBeDefined();
      expect(close.disabled).toBe(false);
      expect(API.get.mock.calls.map(([u]) => u)).toContain('/api/v3/arena/qwen/annotations');
      await click(node, 'Memoria');
      expect(node.textContent).toContain('Motivazioni umane registrate');
      expect(node.textContent).toContain('mai dedotto dal risultato');
    } finally { await dispose(); }
  });
});

test('without the close flag, or if the dedicated route is missing, Qwen stays read-only', async () => {
  for (const [flags, ok] of [[{ REACT_APP_BRAIN_ARENA_SHADOW_API: '1' }, true],
    [{ REACT_APP_BRAIN_ARENA_SHADOW_API: '1', REACT_APP_ARENA_MANUAL_CLOSE: '1' }, false]]) {
    await withFlags(flags, async () => {
      trialInputs(ok);
      const { node, dispose } = await mount();
      try {
        await click(node, 'Qwen');
        await click(node, 'Posizioni aperte');
        expect(Array.from(node.querySelectorAll('button')).some(x => x.textContent.trim() === 'Chiudi ETHUSDT')).toBe(false);
        expect(node.textContent).toContain('non abilitata su questa dashboard');
      } finally { await dispose(); API.get.mockReset(); }
    });
  }
});

test('header says the trial is running only when all three wallets share a verified T0', async () => {
  const t0 = 1794900000000;
  const w = id => ({ ...QWEN, portfolio_id: id, run_id: `brain-${id}-paper20261118`, trial_start_ms: t0,
    trial_comparable: true, realized_pnl: '1' });
  for (const [portfolios, live] of [[{ deepseek: w('deepseek'), qwen: w('qwen'), minimax: w('minimax') }, true],
    [{ deepseek: w('deepseek'), qwen: w('qwen'), minimax: { ...w('minimax'), trial_start_ms: t0 + 1 } }, false]]) {
    await withFlags({ REACT_APP_BRAIN_ARENA_SHADOW_API: '1' }, async () => {
      API.get.mockImplementation((url) => {
        if (url === '/api/v3/arena') return Promise.resolve({ data: { portfolios } });
        if (url === '/api/v3/overview') return Promise.resolve({ data: BRAIN });
        if (url === '/api/v3/brain/status') return Promise.resolve({ data: { state: 'running' } });
        return Promise.resolve({ data: TRADES });
      });
      const { node, dispose } = await mount();
      try {
        expect(node.textContent.includes('Prova PAPER in corso')).toBe(live);
        expect(node.textContent.includes('in attesa di attivazione comune')).toBe(!live);
        expect(node.textContent.includes('Finché Qwen e MiniMax non sono avviati')).toBe(!live);
      } finally { await dispose(); API.get.mockReset(); }
    });
  }
});

test('readonly preview blocks historical Brain close even with explicit close opt-in', async () => {
  const previousAllowed = BRAIN.portfolios[1].manual_close_allowed;
  await withFlags({ REACT_APP_PREVIEW_READONLY: '1', REACT_APP_ARENA_EXISTING_CLOSE: '1' }, async () => {
    BRAIN.portfolios[1].manual_close_allowed = true;
    const { node, dispose } = await mount();
    try {
      await click(node, 'Posizioni aperte');
      const closeButton = Array.from(node.querySelectorAll('button')).find(
        x => x.textContent.trim() === 'Chiudi DOGEUSDT',
      );
      expect(closeButton).toBeDefined();
      expect(closeButton.disabled).toBe(true);
    } finally {
      BRAIN.portfolios[1].manual_close_allowed = previousAllowed;
      await dispose();
    }
  });
});

test('readonly preview blocks trial-AI close even with provider close opt-in', async () => {
  await withFlags({
    REACT_APP_PREVIEW_READONLY: '1',
    REACT_APP_BRAIN_ARENA_SHADOW_API: '1',
    REACT_APP_ARENA_MANUAL_CLOSE: '1',
  }, async () => {
    trialInputs();
    const { node, dispose } = await mount();
    try {
      await click(node, 'Qwen');
      await click(node, 'Posizioni aperte');
      expect(Array.from(node.querySelectorAll('button')).some(
        x => x.textContent.trim() === 'Chiudi ETHUSDT',
      )).toBe(false);
    } finally {
      await dispose();
    }
  });
});

test('prepared paused runs without T0 show a label only, never numbers', async () => {
  const prep = id => ({ portfolio_id: id, mode: 'paper', state: 'not_started', initial_capital: 2000,
    source: 'arena_independent_journal_v1', run_id: `brain-${id}-paper20261118`, trial_start_ms: null,
    trial_comparable: false, data_status: 'PREPARED_AWAITING_T0', realized_pnl: null });
  await withFlags({ REACT_APP_BRAIN_ARENA_SHADOW_API: '1' }, async () => {
    API.get.mockImplementation((url) => {
      if (url === '/api/v3/arena') {
        return Promise.resolve({ data: { portfolios: { deepseek: prep('deepseek'), qwen: prep('qwen'),
          minimax: { ...prep('minimax'), data_status: 'NOT_CONFIGURED' } } } });
      }
      if (url === '/api/v3/overview') return Promise.resolve({ data: BRAIN });
      if (url === '/api/v3/brain/status') return Promise.resolve({ data: { state: 'running' } });
      return Promise.resolve({ data: TRADES });
    });
    const { node, dispose } = await mount();
    try {
      const cards = Array.from(node.querySelectorAll('button[aria-pressed]')).map(b => b.textContent);
      expect(cards.find(c => c.includes('Qwen'))).toContain('Preparato · in pausa');
      expect(cards.find(c => c.includes('MiniMax'))).toContain('Non avviato');
      expect(cards.find(c => c.includes('Qwen'))).toContain('PnL —');
      expect(node.textContent).toContain('in attesa di attivazione comune');
    } finally { await dispose(); API.get.mockReset(); }
  });
});
