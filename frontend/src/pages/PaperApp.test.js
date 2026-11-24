import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import { MemoryRouter } from 'react-router-dom';
import API from '../api';
import PaperTrades, { TradesContent } from './PaperTrades';
import PaperPerformance, { PerformanceContent } from './PaperPerformance';
import Archive, { ArchiveContent, ArchivedRunContent } from './Archive';

// Trade, Performance e Archivio della nuova app PAPER: solo run attuali, nessun dato inventato, testi leggibili.
jest.mock('../api', () => ({ get: jest.fn(), post: jest.fn() }));

const NOW = 1_800_000_000_000;
const H = 3_600_000;
const R = el => <MemoryRouter>{el}</MemoryRouter>;
const minFont = h => Math.min(...[...h.matchAll(/font-size:(\d+(?:\.\d+)?)px/g)].map(m => Number(m[1])));

const trades = (over = {}) => ({
  name: 'falco_evoluto', run_id: 'falco-evoluto-paper-p1', generated_at_ms: NOW - 5_000, take_profit_r: '3', fee_bps: '6',
  total_closed: 3, win_count: 2, loss_count: 1, has_more: false, close_pending: false,
  open_positions: [{ position_id: 'o1', symbol: 'BTCUSDT', side: -1, entry: '60000', stop: '61200', take_profit: '56400',
    price: '59500', unrealized_pnl: '8.25', roi_pct: '5.5', margin: '150', leverage: 20, notional: '3000', opened_at_ms: NOW - 2 * H }],
  closed_trades: [
    { position_id: 'c3', symbol: 'ETHUSDT', side: 1, entry: '3000', exit: '3001.5', stop: '2950', take_profit: '3150',
      realized_pnl: '0.1', gross_pnl: '0.9', fees: '0.8', exit_reason: 'stop', stop_kind: 'break_even', hold_ms: 3 * H,
      leverage: 25, margin: '120', closed_at_ms: NOW - H },
    { position_id: 'c2', symbol: 'SOLUSDT', side: -1, entry: '150', exit: '151', stop: '153', take_profit: '141',
      realized_pnl: '-4.2', gross_pnl: '-3.5', fees: '0.7', exit_reason: 'manual', manual_learning: 'loss_reduction_example',
      hold_ms: H, leverage: 15, margin: '100', closed_at_ms: NOW - 5 * H },
    { position_id: 'c1', symbol: 'XRPUSDT', side: 1, entry: '0.5', exit: '0.53', stop: '0.49', take_profit: '0.53',
      realized_pnl: '29', gross_pnl: '30', fees: '1', exit_reason: 'take_profit', hold_ms: 7 * H, leverage: 30, margin: '200',
      closed_at_ms: NOW - 9 * H }],
  ...over });

test('Trade: open positions with side, leverage, margin, entry, price, stop, TP and per-position P&L', () => {
  const h = renderToStaticMarkup(R(<TradesContent name="falco_evoluto" data={trades()} nowMs={NOW} onSelect={() => {}}
    compareRun={{ manual_close_allowed: true }} />));
  for (const t of ['SHORT', 'BTC', '20×', '$150,00', '$60.000,0', '$59.500,0', '$61.200,0', '$56.400,0', '+$8,25',
    '+5,50% sul margine', 'Chiudi BTCUSDT (PAPER)', 'Take profit a 3 R', '6 bp', 'Aperti (1)', 'Chiusi (3)', '2 / 1'])
    expect(h).toContain(t);
  expect(h).not.toContain('Chiudi tutte');
  expect(minFont(h)).toBeGreaterThanOrEqual(12);
});

test('Trade: closed trades with exit reason, stop kind, fees, gross/net and the learning of manual closes', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  const click = async b => { await act(async () => { b.dispatchEvent(new MouseEvent('click', { bubbles: true })); }); };
  const btn = t => Array.from(el.querySelectorAll('button')).find(b => b.textContent.startsWith(t));
  try {
    await act(async () => { root.render(R(<TradesContent name="falco_evoluto" data={trades()} nowMs={NOW} onSelect={() => {}} />)); });
    await click(btn('Chiusi'));
    const cards = el.querySelectorAll('[data-testid="trade-closed"]');
    expect(cards.length).toBe(3);
    expect(cards[0].textContent).toContain('Stop · stop a pareggio');
    expect(cards[1].textContent).toContain('Chiusura manuale');
    expect(cards[1].textContent).toContain('apprendimento: esempio di perdita ridotta');
    expect(cards[2].textContent).toContain('Take profit');
    expect(cards[2].textContent).toContain('+$30,00');                   // lordo
    expect(cards[2].textContent).toContain('$1,00');                     // commissioni
    expect(cards[2].textContent).toContain('+$29,00');                   // netto
    await click(btn('SHORT'));
    expect(el.querySelectorAll('[data-testid="trade-closed"]').length).toBe(1);
    await click(btn('LONG'));
    expect(el.querySelectorAll('[data-testid="trade-closed"]').length).toBe(2);
  } finally { await act(async () => { root.unmount(); }); el.remove(); }
});

test('Trade: a position without a verifiable price shows "—", never the entry as price', () => {
  const d = trades({ open_positions: [{ ...trades().open_positions[0], price: null, unrealized_pnl: null, roi_pct: null }] });
  const h = renderToStaticMarkup(R(<TradesContent name="falco_evoluto" data={d} nowMs={NOW} onSelect={() => {}} />));
  expect(h).toContain('P&amp;L non verificabile');
  expect(h.match(/\$60\.000,0/g).length).toBe(1);                       // solo come entrata
});

test('Trade page reads only the current runs (GET), the shown bot first, and switches bot', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  API.get.mockImplementation(url => Promise.resolve({ data: url.includes('/trades')
    ? trades({ name: url.includes('brain_scalp') ? 'brain_scalp' : 'falco_evoluto' }) : { available: true, runs: [] } }));
  const el = document.createElement('div');
  const root = createRoot(el);
  try {
    await act(async () => { root.render(R(<PaperTrades />)); });
    await act(async () => {});
    let urls = API.get.mock.calls.map(c => c[0]);
    expect(urls).toContain('/api/v3/compare/falco_evoluto/trades?limit=300');
    expect(urls.every(u => u.startsWith('/api/v3/compare'))).toBe(true);   // mai /api/trades dei classici o di RC1
    await act(async () => { el.querySelector('button[data-bot="brain_scalp"]').dispatchEvent(new MouseEvent('click', { bubbles: true })); });
    await act(async () => {});
    urls = API.get.mock.calls.map(c => c[0]);
    expect(urls).toContain('/api/v3/compare/brain_scalp/trades?limit=300');
    expect(API.post).not.toHaveBeenCalled();
  } finally { await act(async () => { root.unmount(); }); API.get.mockReset(); }
});

const cmpRun = (name, label, over = {}) => ({ name, label, available: true, run_id: name, initial_equity: name === 'brain_scalp' ? '2000' : '1000',
  settled_equity: '1030', net_pnl: '30', return_pct: '3.00', fees: '4.2', ai_cost_total: '0.4', net_after_ai: '29.6',
  return_after_ai_pct: '2.96', closed: 4, wins: 3, losses: 1, win_rate: '75.0', profit_factor: '2.50', max_drawdown: '10',
  max_drawdown_pct: '0.97', mtm_drawdown: null, mtm_drawdown_pct: null,
  by_side: { long: { trades: 3, wins: 2, losses: 1, net_pnl: '20' }, short: { trades: 1, wins: 1, losses: 0, net_pnl: '10' } }, ...over });
const perf = name => ({ available: true, name, run_id: name, day_tz: 'Europe/Rome', started_at_ms: NOW - 2.5 * 24 * H,
  first_decision_ms: NOW - 2 * 24 * H,
  daily: [{ date: '2027-01-13', trades: 0, wins: 0, losses: 0, gross: '0', fees: '0', net: '0', ai_cost: '0.1', net_after_ai: '-0.1', equity_end: '1000' },
    { date: '2027-01-14', trades: 4, wins: 3, losses: 1, gross: '34.2', fees: '4.2', net: '30', ai_cost: '0.3', net_after_ai: '29.7', equity_end: '1030' }],
  curve_settled: [{ t: NOW - 2 * 24 * H, equity: '1000' }, { t: NOW - 24 * H, equity: '1040' }, { t: NOW - H, equity: '1030' }],
  curve_market: [{ t: NOW - H, equity: '1031' }],
  stats: { avg_win: '13.3', avg_loss: '-10', best: '20', worst: '-10', avg_hold_ms: 2 * H, payoff: '1.33' },
  decisions: { total: 10, by_reason: { falco_no_trade_score: 6, falco_no_trade_regime: 3, falco_short_signal: 1 },
    by_risk_reason: { margin_loss_ratio_exceeded: 1 }, by_regime: { RANGE: 5, EXPANSION: 5 }, by_kind: {},
    last: [{ ts_ms: NOW - 60_000, symbol: 'BTCUSDT', kind: 'OPEN', status: 'RISK_REJECTED', rationale: 'falco_short_signal',
      risk_reason: 'margin_loss_ratio_exceeded', regime: 'EXPANSION' }] } });
const cmp = () => ({ available: true, runs: [cmpRun('falco_evoluto', 'Falco Evoluto'), cmpRun('brain_scalp', 'Brain Scalp', { net_pnl: '-12', return_pct: '-0.60' })] });

test('Performance: direct comparison of the two bots with every metric asked for', () => {
  const h = renderToStaticMarkup(R(<PerformanceContent cmp={cmp()} perfs={{ falco_evoluto: perf('f'), brain_scalp: perf('b') }}
    nowMs={NOW} selected="__both" onSelect={() => {}} />));
  for (const t of ['Confronto diretto', 'Capitale iniziale', '$1.000', '$2.000', 'P&amp;L netto trading', '+$30,00', '−$12,00',
    'Rendimento', '+3,00%', '−0,60%', 'Commissioni', '$4,20', 'Costi AI', '$0,400', 'Netto dopo AI', 'Win rate', '75,0%',
    'Profit factor', '2,50', 'Drawdown max (chiusi)', '−0,97%', 'non disponibile', 'LONG', 'SHORT', '3 trade',
    'Periodo di test', '2,5 giorni', 'Rendimento nel tempo', 'Rendimento percentuale dei due bot'])
    expect(h).toContain(t);
  expect(h).not.toContain('NaN');
  expect(minFont(h)).toBeGreaterThanOrEqual(12);
});

test('Performance: single bot with daily results, equity curve, LONG/SHORT and why it does or does not open', () => {
  const h = renderToStaticMarkup(R(<PerformanceContent cmp={cmp()} perfs={{ falco_evoluto: perf('f') }} nowMs={NOW}
    selected="falco_evoluto" onSelect={() => {}} />));
  for (const t of ['Curva dell’equity', 'Equity Falco Evoluto', 'Risultati giornalieri', 'ora italiana', '4 trade (3V/1P)',
    'AI $0,300', 'dopo AI', '+$29,70', 'equity a fine giorno $1.030,00', 'Vincita media', 'Perdita media', 'Payoff', '1,33',
    'Durata media', '2 h 00', 'Perché apre o non apre', 'Punteggio sotto la soglia', '6 · 60%',
    'Regime non adatto', 'Limite di rischio che ha fermato l’apertura', 'stop troppo largo per la leva minima', 'EXPANSION'])
    expect(h).toContain(t);
  expect(h.indexOf('mer 14 gen') < h.indexOf('mar 13 gen') || h.indexOf('14 gen') < h.indexOf('13 gen')).toBe(true);
});

test('Performance page: compare + both performance routes, all GET; a missing performance route does not break it', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  API.get.mockImplementation(url => (url === '/api/v3/compare' ? Promise.resolve({ data: cmp() })
    : url.includes('falco_evoluto') ? Promise.resolve({ data: perf('f') }) : Promise.reject(new Error('404'))));
  const el = document.createElement('div');
  const root = createRoot(el);
  try {
    await act(async () => { root.render(R(<PaperPerformance />)); });
    await act(async () => {});
    expect(API.get.mock.calls.map(c => c[0])).toEqual(['/api/v3/compare', '/api/v3/compare/falco_evoluto/performance',
      '/api/v3/compare/brain_scalp/performance']);
    expect(el.textContent).toContain('Confronto diretto');
    expect(el.querySelector('[role="alert"]')).toBeNull();
  } finally { await act(async () => { root.unmount(); }); API.get.mockReset(); }
});

const archive = { available: true, runs: [{ name: 'reset-20261123T203000Z~brain-v3-brain-scalp-p1', label: 'Brain Scalp',
  run_id: 'brain-scalp-paper-p1', available: true, initial_equity: '2000', settled_equity: '1835.5', net_pnl: '-164.5',
  return_pct: '-8.23', closed: 7, wins: 2, losses: 5, ai_cost_total: '0.81', started_at_ms: NOW - 30 * H, archived_at_ms: NOW - 10 * H,
  archive: 'reset-20261123T203000Z' }] };

test('Archivio: archived PAPER sessions and every historical page, read-only, out of the operating dashboard', () => {
  const h = renderToStaticMarkup(R(<ArchiveContent data={archive} />));
  for (const t of ['Sessioni PAPER archiviate', 'Brain Scalp', '−$164,50', '−8,23%', '$2.000', '2 / 5', '$0,810',
    'href="/archivio/run/reset-20261123T203000Z~brain-v3-brain-scalp-p1"'])
    expect(h).toContain(t);
  for (const href of ['/brain-unico/rc1', '/overview', '/classic', '/archivio/classici/trade', '/archivio/classici/performance',
    '/arena', '/brain/archive', '/compare']) expect(h).toContain(`href="${href}"`);
  expect(h).not.toMatch(/<button[^>]*>Chiudi/);
  expect(renderToStaticMarkup(R(<ArchiveContent data={{ available: false, runs: [] }} />))).toContain('non è collegato');
  expect(minFont(h)).toBeGreaterThanOrEqual(12);
});

test('Archivio: an archived session shows its own closed trades and curve, no close buttons', () => {
  const det = { key: 'k', label: 'Brain Scalp', run_id: 'brain-scalp-paper-p1', archive: 'reset-20261123T203000Z',
    closed_trades: [{ position_id: 'x', symbol: 'ETHUSDT', side: 1, leverage: 20, entry: '3000', exit: '2950', fees: '1.2',
      realized_pnl: '-21.2', exit_reason: 'stop', hold_ms: H, closed_at_ms: NOW - 20 * H }],
    performance: { available: true, started_at_ms: NOW - 30 * H, curve_settled: [{ t: NOW - 30 * H, equity: '2000' }, { t: NOW - 20 * H, equity: '1978.8' }] } };
  const h = renderToStaticMarkup(R(<ArchivedRunContent data={det} />));
  for (const t of ['Brain Scalp · archiviata', 'brain-scalp-paper-p1', '−$21,20', 'Stop', 'Trade chiusi (1)', '← Archivio'])
    expect(h).toContain(t);
  expect(h).not.toMatch(/<button[^>]*>Chiudi/);
});

test('Archivio page reads only the archive route', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  API.get.mockResolvedValue({ data: archive });
  const el = document.createElement('div');
  const root = createRoot(el);
  try {
    await act(async () => { root.render(R(<Archive />)); });
    expect(API.get.mock.calls.map(c => c[0])).toEqual(['/api/v3/paper-archive']);
    expect(el.textContent).toContain('Brain Scalp');
  } finally { await act(async () => { root.unmount(); }); API.get.mockReset(); }
});
