import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import API from '../api';
import Compare, { CompareContent } from './Compare';

jest.mock('../api', () => ({ get: jest.fn() }));

const run = (name, label, over = {}) => ({
  name, label, run_id: name, available: true, initial_equity: '1000', settled_equity: '1050', net_pnl: '50',
  return_pct: '5.00', max_drawdown: '25', max_drawdown_pct: '2.43', profit_factor: '1.80', wins: 3, losses: 2,
  win_rate: '60.0', by_side: { long: { trades: 2, net_pnl: '-10' }, short: { trades: 3, net_pnl: '60' } },
  guardian: { state: 'SELECTIVE', reasons: ['floor_armed'], equity: '1080', session_start_equity: '1000',
    peak_equity: '1100', giveback: '20', budget: '40', risk_cap: '20' },
  open_positions: [{ position_id: 'p1', symbol: 'BTCUSDT', side: -1, entry: '100', stop: '101', margin: '150', leverage: 30 }],
  manual_closes: 1, protected_stops: 2, ai_spend: { day: '0.042', total: '0.3' },
  config: { max_positions: 4, daily_cap_usd: '0.20', leverage: [15, 45], margin: ['100', '250'] },
  decisions: [{ ts_ms: 1, symbol: 'ETHUSDT', kind: 'NO_TRADE', rationale: 'falco_no_trade_regime' },
    { ts_ms: 2, symbol: 'SOLUSDT', kind: 'NO_TRADE', rationale: 'risk_rejected', risk_reason: 'below_min_margin' },
    { ts_ms: 3, symbol: 'XRPUSDT', kind: 'NO_TRADE', rationale: '<b>x</b>' }],
  ...over });

test('both bots side by side with return, drawdown, guardian and reasons', () => {
  const data = { available: true, runs: [run('falco_evoluto', 'Falco Evoluto'),
    run('brain_scalp', 'Brain Scalp', { initial_equity: '2000', return_pct: '-1.50', guardian: { state: 'LOCKED', reasons: ['below_floor'] } })] };
  const h = renderToStaticMarkup(<CompareContent data={data} />);
  for (const t of ['Falco Evoluto', 'Brain Scalp', '+5.00%', '-1.50%', '-2.43% ($25.00)', '1.80', '60.0% (3/2)',
    'Selettivo', 'Bloccato', '$1100.00 / $20.00', '$40.00', 'SHORT', 'x30', 'Stop protettivi',
    'nessun trade: mercato laterale, incerto o shock', 'margine sotto il minimo', '15–45× · $100–250',
    'non garantisce il profitto finale']) expect(h).toContain(t);
  expect(h).not.toContain('<b>x</b>');
  expect(h).not.toContain('&lt;b&gt;');                       // un codice sconosciuto non diventa mai testo
});

test('not yet prepared runs show no numbers', () => {
  const h = renderToStaticMarkup(<CompareContent data={{ available: false, runs: [] }} />);
  expect(h).toContain('Confronto non ancora attivo');
  expect(h).not.toMatch(/\$\d/);
  const part = renderToStaticMarkup(<CompareContent data={{ available: true, runs: [
    { name: 'brain_scalp', label: 'Brain Scalp', available: false, reason: 'not_started' }] }} />);
  expect(part).toContain('non avviato');
});

test('loads the compare endpoint', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  API.get.mockResolvedValue({ data: { available: false, runs: [] } });
  const el = document.createElement('div');
  const root = createRoot(el);
  try {
    await act(async () => { root.render(<Compare />); });
    expect(API.get).toHaveBeenCalledWith('/api/v3/compare');
    expect(el.textContent).toContain('Confronto non ancora attivo');
  } finally { await act(async () => { root.unmount(); }); API.get.mockReset(); }
});
