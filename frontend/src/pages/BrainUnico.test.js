import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import API from '../api';
import BrainUnico, { BrainUnicoContent } from './BrainUnico';

jest.mock('../api', () => ({ get: jest.fn(), post: jest.fn() }));

const now = 1700000100000;
const overview = { generated_at_ms: now, portfolios: [
  { id: 'falco', kind: 'classic', state: 'running', open_positions: 2, realized_pnl: '13.50' },
  { id: 'brain', kind: 'brain', state: 'running', open_positions: 1, realized_pnl: '8.33', margin_in_use: '40',
    equity: '2008.33', settled_equity: '2008.33', day_pnl: '-1.20', total_closed: 3, win_rate: 66.7 },
] };
const status = { state: 'running', regime: 'TREND_UP', heartbeat: { ts_ms: now - 5000 },
  last_decision: { kind: 'NO_TRADE', symbol: 'ETHUSDT', status: 'REJECTED', ts_ms: now - 60000 },
  spend: { day: '0.11', day_limit: '0.75' } };
const trades = {
  open_positions: [{ position_id: 'p1', symbol: 'BTCUSDT', side: 1, leverage: 20, entry: '100', stop: '99',
    unrealized_pnl: '2.50', margin: '40', strategy_id: 'S07' }],
  closed_trades: [
    { position_id: 'p2', symbol: 'ETHUSDT', side: -1, exit_reason: 'manual', realized_pnl: '4.00', net_bp: '20',
      manual_learning: 'profit_protection_example', closed_at_ms: now - 20000 },
    { position_id: 'p3', symbol: 'SOLUSDT', side: 1, exit_reason: 'stop', realized_pnl: '-3.00', net_bp: '-15', closed_at_ms: now - 40000 },
    { position_id: 'p4', symbol: '<script>x</script>', side: 1, exit_reason: 'take_profit', realized_pnl: '7.33', closed_at_ms: now - 60000 },
  ],
  total_closed: 3, win_count: 2, loss_count: 1, break_even_count: 0, close_pending: false };
const memory = { state: 'ok', memory: { decisions: 5, valid_links: 5, coverage_pct: '100.0', chain_ok: true, missing: 0,
  invalid: 0, untraced_opens: 0, no_trade: 2, manual_closes: 1, automatic_closes: 2 },
  theses: { mode: 'observe', opens_with_thesis: 3, distinct_theses: 2, reentries: 1, would_block: 0, rules: {} },
  learning: { valid_examples_collected: 5, distinct_days: 1, shadow_threshold: { examples: 300, days: 20 },
    promotion_review_threshold: { examples: 1000, days: 45 }, training_authorized: false, model_active: false },
  recent: [] };
const html = props => renderToStaticMarkup(<BrainUnicoContent overview={overview} status={status} trades={trades}
  memory={memory} nowMs={now} {...props} />);

test('classic-style screen: equity, KPI, state, commands, positions, statistics and learning on one screen', () => {
  const h = html();
  for (const text of ['Brain Unico', 'PAPER MODE', 'Equity', '$2008.33', '+8.33$', '+2.50$', '-1.20$', '$1968.33', '66.7%',
    '2 / 1 / 0', '1 / 2', '$11.33', '-$3.00', 'BTC', 'LONG', 'x20', 'S07', 'SL $99.00', 'Chiudi BTCUSDT (PAPER)', 'chiusa da te',
    'Memoria decisionale', 'Apprendimento', 'Addestramento autorizzato', 'Storico', 'Budget AI', 'Aperte', 'Chiuse',
    'Avvia / Riprendi', 'Pausa']) expect(h).toContain(text);
  expect(h).not.toContain('Falco · 13.50');                         // i classici non occupano la schermata
  expect(h).not.toMatch(/Falco (●|⏸|○)|Toro (●|⏸|○)/);
  expect(h).toContain('href="/overview"');
  expect(h).toContain('href="/classic"');
});

const livePosition = { position_id: 'p1', symbol: 'BTCUSDT', side: 1, leverage: 20, entry: '100', price: '101.25', stop: '99',
  take_profit: '104', liquidation: '95.5', unrealized_pnl: '2.50', roi_pct: '6.25', margin: '40', strategy_id: 'S07',
  opened_at_ms: now - 3600000 };

test('the open position card shows every field of the classic card, with ROI and P&L', () => {
  const h = html({ trades: { ...trades, open_positions: [livePosition] } });
  for (const text of ['LONG', 'BTC', 'x20', 'S07', 'Entrata <strong style="color:#e2e8f0">$100.00',
    'Ora <strong style="color:#e2e8f0">$101.25', 'Margine <strong style="color:#e2e8f0">$40', 'SL $99.00', 'TP $104.00',
    'Liq $95.50', 'aperta da 1h 0m', '+2.50$', '+6.25% sul margine']) expect(h).toContain(text);
  expect(h).not.toContain('P&amp;L e ROI non calcolabili');
});

test('without a verified price the position shows unknown P&L and ROI, never invented values', () => {
  const h = html({ trades: { ...trades, open_positions: [{ ...livePosition, price: null }] } });
  expect(h).toContain('P&amp;L e ROI non calcolabili');
  expect(h).toContain('ROI —');
  expect(h).not.toContain('+6.25%');
});

test('commands are disabled and explain why; close-all never exists, single close does', () => {
  const h = html({ overview: { ...overview, cutover_readonly: true, brain_single_close_allowed: true } });
  expect(h).toMatch(/<button[^>]*disabled=""[^>]*>▶ Avvia \/ Riprendi<\/button>/);
  expect(h).toMatch(/<button[^>]*disabled=""[^>]*>⏸ Pausa<\/button>/);
  expect(h).toContain('non ha un’API sicura');
  expect(h).not.toContain('Chiudi tutte');
  expect(h).toMatch(/<button(?![^>]*disabled)[^>]*>Chiudi BTCUSDT \(PAPER\)<\/button>/);
  expect(html({ overview: { ...overview, cutover_readonly: false } })).not.toContain('Chiudi tutte');
});

test('the PAPER label is always visible, also before the start', () => {
  expect(html()).toContain('PAPER MODE');
  expect(html()).toContain('BRAIN UNICO');          // marcatore richiesto da 70-interfaccia.sh nel bundle
  const h = html({ overview: { generated_at_ms: now, portfolios: [{ id: 'brain', state: 'not_started' }] },
    status: null, trades: null, memory: null });
  expect(h).toContain('PAPER MODE');
  expect(h).toContain('>PAPER</span>');
  expect(h).toContain('Brain Unico ⏸ Non avviato');
});

test('the Brain state card distinguishes running, paused, risk stop and mandate pending', () => {
  expect(html()).toContain('DeepSeek operativo');
  expect(html({ status: { ...status, state: 'paused', paused: true } })).toContain('In pausa');
  expect(html({ status: { ...status, daily_loss: { level: 'halt', pct: '51.0' } } })).toContain('Bloccato dal rischio');
  const waiting = html({ status: { ...status, state: 'halted', heartbeat: { ts_ms: now - 5000, last_error: 'halted:mandate_not_approved' } } });
  expect(waiting).toContain('In attesa del mandato');
  expect(waiting).not.toContain('DeepSeek operativo');
});

test('memory sections are collapsible and closed by default, below the operational part', () => {
  const h = html();
  expect(h).toMatch(/<details[^>]*aria-label="Memoria Brain"/);
  expect(h).not.toMatch(/<details[^>]*\sopen[\s=>]/);
  expect(h.indexOf('Posizioni Aperte')).toBeLessThan(h.indexOf('Memoria decisionale'));
  expect(h.indexOf('Statistiche')).toBeLessThan(h.indexOf('Memoria decisionale'));
});

test('the page does not claim that the memory learned from manual closes', () => {
  const h = html();
  expect(h).not.toMatch(/ha imparato|appreso dalle chiusure|strategia appresa/i);
  expect(h).toContain('Modello appreso attivo');
});

test('manual closes are shown as operator interventions, not strategies', () => {
  const h = html();
  expect(h).toContain('interventi dell’operatore');
  expect(h).toContain('esempio per AI, non strategia convalidata');
});

test('model and symbol text is escaped', () => {
  const h = html();
  expect(h).toContain('&lt;script&gt;x&lt;/script&gt;');
  expect(h).not.toContain('<script>x');
});

test('the Arena history is linked read-only', () => {
  expect(html()).toContain('href="/arena"');
  expect(html()).toContain('sola lettura');
});

test('not started and missing details fail safe', () => {
  const h = html({ overview: { generated_at_ms: now, portfolios: [{ id: 'brain', state: 'not_started' }] }, trades: null, memory: null });
  expect(h).toContain('Brain non ancora avviato');
  expect(h).toContain('nessuna chiusura consentita');
  expect(h).toContain('Memoria non disponibile');
});

test('read-only cutover disables the close buttons', () => {
  const h = html({ overview: { ...overview, cutover_readonly: true, brain_single_close_allowed: false } });
  expect(h).toMatch(/disabled/);
});

test('polls the four Brain endpoints and survives a memory outage', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const bodies = { '/api/v3/overview': overview, '/api/v3/brain/status': status, '/api/v3/brain/trades?limit=20': trades };
  API.get.mockImplementation(path => (path in bodies ? Promise.resolve({ data: bodies[path] }) : Promise.reject(new Error('down'))));
  const el = document.createElement('div');
  const root = createRoot(el);
  try {
    await act(async () => { root.render(<BrainUnico />); });
    expect(API.get.mock.calls.map(c => c[0])).toEqual(['/api/v3/overview', '/api/v3/brain/status',
      '/api/v3/brain/trades?limit=20', '/api/v3/brain/memory']);
    expect(el.textContent).toContain('Posizioni Aperte');
    expect(el.textContent).toContain('Memoria non disponibile');
  } finally { await act(async () => { root.unmount(); }); API.get.mockReset(); }
});

test('an unavailable overview is an explicit alert', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  API.get.mockImplementation(() => Promise.reject(new Error('down')));
  const el = document.createElement('div');
  const root = createRoot(el);
  try {
    await act(async () => { root.render(<BrainUnico />); });
    expect(el.textContent).toContain('Impossibile aggiornare il Brain');
  } finally { await act(async () => { root.unmount(); }); API.get.mockReset(); }
});

test('daily loss state is shown from the runner heartbeat', () => {
  const h = html({ status: { ...status, daily_loss: { level: 'warn', pct: '36.2' } } });
  expect(h).toContain('Perdita giornaliera');
  expect(h).toContain('avviso');
  expect(h).toContain('36.2%');
  expect(html({ status: { ...status, daily_loss: { level: 'toString', pct: null } } })).toContain('non disponibile');
});
