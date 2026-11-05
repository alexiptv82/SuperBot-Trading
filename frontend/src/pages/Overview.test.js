import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import API from '../api';
import Overview, { OverviewContent } from './Overview';

jest.mock('../api', () => ({ get: jest.fn() }));

const now = 1700000100000;
const sample = {
  overview: { generated_at_ms: now, portfolios: [
    { id: 'falco', kind: 'classic', state: 'running', open_positions: 2, realized_pnl: '13.50', margin_in_use: '70', last_event_ms: now - 50000 },
    { id: 'toro', kind: 'classic', state: 'paused', open_positions: 0, realized_pnl: '-2.50', margin_in_use: '0', last_event_ms: now - 30000 },
    { id: 'brain', kind: 'brain', state: 'halted', open_positions: 1, realized_pnl: '8.33', margin_in_use: '40', last_event_ms: now - 20000 },
  ] },
  status: { state: 'halted', regime: 'TREND_UP', heartbeat: { last_error: 'halted:no_mandate' },
    last_decision: { kind: 'OPEN', symbol: 'BTCUSDT', strategy_id: 'S07', status: 'APPROVED' },
    spend: { day: '0.11', day_limit: '1.25', month: '0.88' } },
  scoreboard: { regimes: [{ regime: 'TREND_UP', n_closed_linked: 3, n_labelled: 3,
    cells: [{ strategy_id: 'S07', origin: 'library', side: 1, n: 3, mean_net_bp: '19.2000',
      ci_low: '5.0000', ci_high: '25.0000', status: 'positive' }] }] },
  trades: { open_positions: [{ position_id: 'p1', symbol: 'BTCUSDT', side: 1,
    leverage: 5, entry: '100', stop: '95', unrealized_pnl: null, strategy_id: 'S07' }],
  closed_trades: [{ position_id: 'p2', symbol: 'ETHUSDT', side: -1, strategy_id: 'AI_X',
    regime: 'RANGE', exit_reason: 'take_profit', net_bp: '23.0000', hold_ms: 20000, closed_at_ms: now - 20000 }] } };

test('phone-first unified cards and learning metrics, only safe text', () => {
  const html = renderToStaticMarkup(<OverviewContent {...sample} regime="TREND_UP" onRegime={() => {}} nowMs={now} />);
  expect(html).toContain('Falco');
  expect(html).toContain('Toro');
  expect(html).toContain('Brain V3');
  expect(html).toContain('In attesa del mandato dell’utente');
  expect(html).toContain('0.11');
  expect(html).toContain('1.25');
  expect(html).toContain('S07');
  expect(html).toContain('19.2000 bp');
  expect(html).toContain('Insufficiente ≠ cattivo');
  expect(html).toContain('AI_X');
  expect(html).toContain('P&amp;L non realizzato:');
  expect(html).toContain('Chiudi BTCUSDT');
  expect(html).toContain('Chiudi tutte (1)');
  expect(html).not.toContain('<form');
  expect(html).toContain('max-width:640px');
});

test('not started means unavailable, not fictional wallet', () => {
  const empty = { overview: { generated_at_ms: now, portfolios: [
    { id: 'brain', kind: 'brain', state: 'not_started', open_positions: 0,
      realized_pnl: '0', margin_in_use: '0', last_event_ms: null },
  ] }, status: { state: 'not_started', spend: null }, scoreboard: { regimes: [] },
    trades: { open_positions: [], closed_trades: [] } };
  const html = renderToStaticMarkup(<OverviewContent {...empty} nowMs={now} regime="" onRegime={() => {}} />);
  expect(html).toContain('Non avviato');
  expect(html).toContain('Brain non ancora avviato');
  expect(html).not.toContain('0 USDT');
  expect(html).toContain('Nessun trade chiuso disponibile');
});

test('safe status when network rejects, no stale content', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  API.get.mockRejectedValue(new Error('offline'));
  const rootEl = document.createElement('div');
  const root = createRoot(rootEl);
  try {
    await act(async () => { root.render(<Overview />); });
    expect(rootEl.textContent).toContain('Impossibile aggiornare la dashboard');
    expect(rootEl.textContent).not.toContain('Falco');
  } finally { await act(async () => { root.unmount(); }); API.get.mockReset(); }
});

test('poll GET only every 30 sec, aborts pending on unmount', async () => {
  jest.useFakeTimers();
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const paths = ['/api/v3/overview', '/api/v3/brain/status', '/api/v3/brain/scoreboard', '/api/v3/brain/trades?limit=20'];
  const bodies = [sample.overview, sample.status, sample.scoreboard, sample.trades];
  API.get.mockImplementation(path => Promise.resolve({ data: bodies[paths.indexOf(path)] }));
  const rootEl = document.createElement('div');
  const root = createRoot(rootEl);
  try {
    await act(async () => { root.render(<Overview />); });
    expect(API.get.mock.calls.map(call => call[0])).toEqual(paths);
    expect(rootEl.textContent).toContain('Falco');
    await act(async () => { jest.advanceTimersByTime(30000); });
    expect(API.get).toHaveBeenCalledTimes(8);
    expect(API.get.mock.calls.every(([path]) => path.startsWith('/api/v3/'))).toBe(true);
    const signal = API.get.mock.calls[0][1].signal;
    expect(signal).toBeDefined();
  } finally { await act(async () => { root.unmount(); }); jest.useRealTimers(); API.get.mockReset(); }
});

test('model text is escaped by React', () => {
  const altered = { ...sample, trades: { ...sample.trades,
    closed_trades: [{ ...sample.trades.closed_trades[0], symbol: '<script>alert(1)</script>' }] } };
  const html = renderToStaticMarkup(<OverviewContent {...altered} nowMs={now} regime="" onRegime={() => {}} />);
  expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
  expect(html).not.toContain('<script>');
});
