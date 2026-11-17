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
beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  inputs();
});
afterEach(() => API.get.mockReset());

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
