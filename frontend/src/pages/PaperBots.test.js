import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import { MemoryRouter } from 'react-router-dom';
import API from '../api';
import PaperBots, { PaperBotsContent } from './PaperBots';

jest.mock('../api', () => ({ get: jest.fn(), post: jest.fn() }));

const NOW = 1_800_000_000_000;
const MIN = 60_000;
const R = el => <MemoryRouter>{el}</MemoryRouter>;
const html = props => renderToStaticMarkup(R(<PaperBotsContent nowMs={NOW} {...props} />));
const run = (name, label, over = {}) => ({
  name, label, run_id: name, available: true, state: 'running', paused: false, initial_equity: '1000',
  settled_equity: '1010', net_pnl: '10', return_pct: '1.00', ai_cost_total: '0.2', net_after_ai: '9.8',
  return_after_ai_pct: '0.98', fees: '1.5',
  closed: 5, wins: 3, losses: 2, manual_closes: 1, protected_stops: 2, manual_close_allowed: true,
  guardian: { state: 'SELECTIVE', reasons: ['floor_armed'], equity: '1042.5', session_start_equity: '1000',
    peak_equity: '1100', giveback: '57.5', floor: '1075', budget: '40', risk_cap: '20', unrealized: '32.5',
    open_risk: '30', as_of_ms: NOW - 3 * MIN },
  open_positions: [{ position_id: 'p1', symbol: 'BTCUSDT', side: -1, entry: '100', stop: '101', margin: '150', leverage: 30 }],
  ai_spend: { day: '0.042', total: '0.3' },
  config: { initial_equity: '1000', analyst: 'falco_evoluto', cycle_minutes: 15, max_positions: 4, daily_cap_usd: '0.20',
    leverage: [15, 45], margin: ['100', '250'], risk_per_trade_pct: '4.00', open_risk_pct: '10.00', daily_stop_pct: '12.00' },
  decisions: [{ ts_ms: NOW - 3 * MIN, symbol: 'ETHUSDT', kind: 'NO_TRADE', rationale: 'falco_no_trade_regime' },
    { ts_ms: NOW - 18 * MIN, symbol: 'SOLUSDT', kind: 'NO_TRADE', rationale: 'risk_rejected', risk_reason: 'margin_loss_ratio_exceeded' },
    { ts_ms: NOW - 33 * MIN, symbol: 'XRPUSDT', kind: 'NO_TRADE', rationale: '<b>x</b>' }],
  ...over });
const both = () => ({ available: true, generated_at_ms: NOW - 20_000, runs: [
  run('falco_evoluto', 'Falco Evoluto'),
  run('brain_scalp', 'Brain Scalp', { paused: true, initial_equity: '2000', settled_equity: '1990', net_pnl: '-10',
    guardian: { state: 'LOCKED', reasons: ['below_floor'], equity: '1975', session_start_equity: '2000', as_of_ms: NOW - 9 * MIN },
    open_positions: [{ position_id: 's1', symbol: 'ETHUSDT', side: 1, entry: '10', stop: '9.9', margin: '300', leverage: 20 }],
    config: { initial_equity: '2000', analyst: 'deepseek', cycle_minutes: 30, max_positions: 4, daily_cap_usd: '0.75',
      leverage: [15, 45], margin: ['250', '450'], daily_stop_pct: '25.00' } })] });
const liveFalco = { name: 'falco_evoluto', open_positions: [{ position_id: 'p1', symbol: 'BTCUSDT', side: -1, entry: '100',
  stop: '101', margin: '150', leverage: 30, price: '99.5', unrealized_pnl: '4.5', take_profit: '97', opened_at_ms: NOW - 40 * MIN }] };

test('hierarchy: state and capital, equity, realized/open P&L, net after AI, positions, then Guardian and decisions', () => {
  const h = html({ data: both() });
  const order = ['Stato Falco Evoluto', 'Equity Falco Evoluto', 'Profitti e perdite Falco Evoluto', 'Posizioni aperte (1)',
    'Guardian Falco Evoluto', 'Decisioni Falco Evoluto'];
  const at = order.map(t => h.indexOf(t));
  expect(at.every(i => i > 0)).toBe(true);
  expect([...at].sort((a, b) => a - b)).toEqual(at);
  for (const t of ['Capitale iniziale', '$1.000', 'Giro ogni', '15 min', 'regole Falco Evoluto', 'stop giornaliero 12.00 %',
    'Equity a mercato', '$1.042,50', '+$42,50', '(+4,25%)', 'Realizzato (trade chiusi)', '+$10,00', 'commissioni incluse: $1,50',
    'Aperto (posizioni in corso)', '+$32,50', 'Costi AI (totale run)', '$0,200', 'Netto realizzato dopo AI', '+$9,80',
    'Risultato netto complessivo', '+$42,30', 'Chiudi BTCUSDT (PAPER)', 'SHORT', '30×'])
    expect(h).toContain(t);
  // Guardian e decisioni sono sezioni secondarie chiuse (details senza open)
  expect(h).toMatch(/<details aria-label="Guardian Falco Evoluto"/);
  expect(h).not.toMatch(/<details open=""[^>]*aria-label="Guardian/);
  expect(h).not.toContain('$NaN');
  expect(h).not.toContain('undefined');
  expect(h).not.toContain('<b>x</b>');
  expect(h).not.toContain('&lt;b&gt;');
});

test('fresh values and last-round values are labelled differently', () => {
  const h = html({ data: both() });
  expect(h).toContain('ultimo giro, 3 min fa');             // equity a mercato e aperto: valori del giro
  expect(h).toContain('● aggiornato');                       // realizzato: dal journal, aggiornato ora
  const l = html({ data: both(), live: liveFalco });
  expect(l).toContain('Prezzo e P&amp;L aggiornati dal ticker');
  expect(l).toContain('$99,50');
  expect(l).toContain('+$4,50');
  expect(l).toContain('$97,00');                             // take profit
});

test('without the live trade route the positions still show, and price/P&L say "—" instead of being invented', () => {
  const h = html({ data: both() });
  expect(h).toContain('Prezzo e P&amp;L per posizione non disponibili');
  expect(h).toContain('Chiudi BTCUSDT (PAPER)');
});

test('no microscopic text: no font below 12 px in the Brain screen', () => {
  const h = html({ data: both(), live: liveFalco });
  const sizes = [...h.matchAll(/font-size:(\d+(?:\.\d+)?)px/g)].map(m => Number(m[1]));
  expect(sizes.length).toBeGreaterThan(10);
  expect(Math.min(...sizes)).toBeGreaterThanOrEqual(12);
});

test('both summaries always visible; below only the selected bot (Falco Evoluto by default)', () => {
  const h = html({ data: both() });
  for (const t of ['Falco Evoluto', 'Brain Scalp', 'RUNNING', 'PAUSA', '$1.042,50', '$1.975,00']) expect(h).toContain(t);
  for (const t of ['Dettagli Brain Scalp', 'Chiudi ETHUSDT (PAPER)', 'Bloccato', 'DeepSeek']) expect(h).not.toContain(t);
});

test('selecting Brain Scalp shows only its details', () => {
  const h = html({ data: both(), initialSelected: 'brain_scalp' });
  for (const t of ['Dettagli Brain Scalp', 'PAUSA', 'Nessuna nuova apertura', '$1.975,00', '−$25,00', '$2.000',
    'Bloccato', 'LONG', 'Chiudi ETHUSDT (PAPER)', 'DeepSeek', '30 min', 'stop giornaliero 25.00 %']) expect(h).toContain(t);
  for (const t of ['Dettagli Falco Evoluto', 'Chiudi BTCUSDT (PAPER)', 'regole Falco Evoluto']) expect(h).not.toContain(t);
});

test('the main screen is not RC1: the history lives in the Archive', () => {
  const h = html({ data: both() });
  expect(h).not.toContain('Brain Unico');
  expect(h).not.toContain('href="/brain-unico/rc1"');
  expect(h).toContain('href="/archivio"');
});

test('no start/pause controls and no close-all: only single manual closes', () => {
  const h = html({ data: both() });
  expect(h).not.toMatch(/Avvia|Riprendi|Chiudi tutte/);
  expect(h).toContain('avvio, pausa e mandato');
});

test('a stale RUNNING is said out loud', () => {
  const old = both();
  old.runs[0].guardian.as_of_ms = NOW - 3 * 60 * MIN;
  old.runs[0].decisions = [{ ts_ms: NOW - 3 * 60 * MIN, symbol: 'ETHUSDT', kind: 'NO_TRADE' }];
  const h = html({ data: old });
  expect(h).toContain('Nessun giro recente');
  expect(h).toContain('3 h 00 min fa');
});

test('halted, not started and not prepared bots show their state and no money', () => {
  const data = { available: true, runs: [run('falco_evoluto', 'Falco Evoluto', { state: 'halted' }),
    { name: 'brain_scalp', label: 'Brain Scalp', available: false, reason: 'not_started' }] };
  expect(html({ data })).toContain('FERMO');
  expect(html({ data })).toContain('NON AVVIATO');
  const s = html({ data, initialSelected: 'brain_scalp' });
  expect(s).toContain('Nessun dato viene mostrato finché non esiste il suo journal');
});

test('without guardian samples, AI costs or positions nothing is invented', () => {
  const data = { available: true, runs: [run('falco_evoluto', 'Falco Evoluto',
    { guardian: null, open_positions: [], decisions: [], net_after_ai: null, ai_cost_total: null, ai_spend: {} })] };
  const h = html({ data });
  expect(h).toContain('Equity contabile');
  expect(h).toContain('Nessuna valutazione registrata finora');
  expect(h).toContain('Nessuna posizione aperta');
  expect(h).toContain('Nessuna decisione registrata');
  expect(h).toContain('non calcolabile: manca un dato registrato');
  expect(h).not.toContain('$NaN');
});

test('bots not active and a failed load say so', () => {
  expect(html({ data: { available: false, runs: [] } })).toContain('Bot non ancora attivi');
  expect(html({ data: null, error: true })).toContain('role="alert"');
  expect(html({ data: null })).toContain('Caricamento');
  expect(html({ data: both(), error: true })).toContain('Ultimo aggiornamento non');
});

test('reads compare, then the live trades of the shown bot only (GET only)', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  API.get.mockImplementation(url => Promise.resolve({ data: url === '/api/v3/compare' ? both() : liveFalco }));
  const el = document.createElement('div');
  const root = createRoot(el);
  try {
    await act(async () => { root.render(R(<PaperBots />)); });
    await act(async () => {});
    const urls = API.get.mock.calls.map(c => c[0]);
    expect(urls).toContain('/api/v3/compare');
    expect(urls).toContain('/api/v3/compare/falco_evoluto/trades?limit=1');
    expect(urls.some(u => u.includes('brain_scalp'))).toBe(false);
    expect(API.post).not.toHaveBeenCalled();
    expect(el.textContent).toContain('$99,50');
  } finally { await act(async () => { root.unmount(); }); API.get.mockReset(); }
});

test('a missing live route (old server) keeps the screen working on compare data', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  API.get.mockImplementation(url => (url === '/api/v3/compare' ? Promise.resolve({ data: both() }) : Promise.reject(new Error('404'))));
  const el = document.createElement('div');
  const root = createRoot(el);
  try {
    await act(async () => { root.render(R(<PaperBots />)); });
    await act(async () => {});
    expect(el.textContent).toContain('Chiudi BTCUSDT (PAPER)');
    expect(el.textContent).toContain('non disponibili in questo momento');
    expect(el.querySelector('[role="alert"]')).toBeNull();
  } finally { await act(async () => { root.unmount(); }); API.get.mockReset(); }
});

test('single manual close: asks first, one POST, to the bot that owns the position, never to the other', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  API.post.mockResolvedValue({ data: { ok: true, ts_ms: 5 } });
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  const click = async b => { await act(async () => { b.dispatchEvent(new MouseEvent('click', { bubbles: true })); }); };
  const find = label => Array.from(el.querySelectorAll('button')).find(b => b.textContent === label);
  try {
    await act(async () => { root.render(R(<PaperBotsContent data={both()} nowMs={NOW} />)); });
    await click(el.querySelector('button[data-bot="brain_scalp"]'));
    await click(find('Chiudi ETHUSDT (PAPER)'));
    expect(API.post).not.toHaveBeenCalled();
    expect(el.textContent).toContain('Chiudere ETHUSDT adesso a prezzo di mercato?');
    await click(find('Chiudi'));
    expect(API.post).toHaveBeenCalledTimes(1);
    expect(API.post).toHaveBeenCalledWith('/api/v3/compare/brain_scalp/close', { position_id: 's1' });
  } finally { await act(async () => { root.unmount(); }); el.remove(); API.post.mockReset(); }
});

test('manual close is disabled while the exit service of THAT bot is not healthy', () => {
  const data = both();
  data.runs[0].manual_close_allowed = false;
  const h = html({ data });
  expect(h).toMatch(/<button[^>]*disabled=""[^>]*>Chiudi BTCUSDT \(PAPER\)<\/button>/);
  expect(h).toContain('servizio\n      uscite di questo bot non è sano'.replace(/\n\s+/, ' '));
  const s = html({ data, initialSelected: 'brain_scalp' });
  expect(s).not.toMatch(/<button[^>]*disabled=""[^>]*>Chiudi ETHUSDT \(PAPER\)<\/button>/);
});

async function mount(data, props = {}) {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  const draw = (d, p) => root.render(R(<PaperBotsContent data={d} nowMs={NOW} {...props} {...p} />));
  await act(async () => { draw(data); });
  const tile = name => el.querySelector(`button[data-bot="${name}"]`);
  const region = () => el.querySelector('[role="region"]');
  const tap = async b => { await act(async () => { b.dispatchEvent(new MouseEvent('click', { bubbles: true })); }); };
  return { el, draw, tile, region, tap, close: async () => { await act(async () => { root.unmount(); }); el.remove(); } };
}

test('the two top tiles are real buttons with aria-pressed and aria-controls', async () => {
  const seen = [];
  const m = await mount(both(), { onSelectedChange: n => seen.push(n) });
  try {
    for (const name of ['falco_evoluto', 'brain_scalp']) {
      const b = m.tile(name);
      expect(b.tagName).toBe('BUTTON');
      expect(b.getAttribute('type')).toBe('button');
      expect(b.getAttribute('aria-controls')).toBe(`bot-dettagli-${name}`);
    }
    expect(m.tile('falco_evoluto').getAttribute('aria-pressed')).toBe('true');
    expect(m.tile('falco_evoluto').style.border).toContain('2px solid');
    expect(m.tile('brain_scalp').getAttribute('aria-label')).toContain('PAUSA');
    await m.tap(m.tile('brain_scalp'));
    expect(m.tile('brain_scalp').getAttribute('aria-pressed')).toBe('true');
    expect(m.region().id).toBe('bot-dettagli-brain_scalp');
    expect(m.region().textContent).toContain('Chiudi ETHUSDT (PAPER)');
    expect(m.el.querySelectorAll('section[aria-label^="Bot "]').length).toBe(1);
    expect(m.tile('falco_evoluto').textContent).toContain('$1.042,50');
    expect(seen).toEqual(['falco_evoluto', 'brain_scalp']);   // il genitore legge i prezzi del solo bot mostrato
  } finally { await m.close(); }
});

test('the choice survives the refresh; a bot that disappears falls back to the first one', async () => {
  const m = await mount(both());
  try {
    await m.tap(m.tile('brain_scalp'));
    await act(async () => { m.draw(both(), { nowMs: NOW + 30_000 }); });
    expect(m.region().id).toBe('bot-dettagli-brain_scalp');
    await act(async () => { m.draw({ ...both(), runs: [both().runs[0]] }); });
    expect(m.region().id).toBe('bot-dettagli-falco_evoluto');
  } finally { await m.close(); }
});

// Brain unico PAPER 2000 (24/11): una sola run, nessun selettore; modalità, slot, salvadanaio, quote, revisioni AI.
const unico = () => ({ available: true, generated_at_ms: NOW - 20_000, runs: [run('brain_scalp', 'Brain', {
  initial_equity: '2000', settled_equity: '2310', net_pnl: '310', open_trades: 1,
    ai_spend: { day: '0.5', total: '1.2', by_provider: { deepseek: { day: '0.4', total: '0.9' }, claude: { day: '0.1', total: '0.3' } } },
    collaboration: { entry: { consults: 3, agreed: 2, claude_adopted: 1, blocked: 1, unavailable: 0, deepseek_only: 5 },
      review: { consults: 2, agreed: 1, claude_adopted: 1, deepseek_kept: 0, unavailable: 0 },
      results: { deepseek: { trades: 4, net_pnl: '20' }, agreed: { trades: 2, net_pnl: '31.5' }, claude: { trades: 1, net_pnl: '-4' } } },
  guardian: { state: 'SELECTIVE', reasons: ['profit_selective'], equity: '2330', session_start_equity: '2000',
    realized_session: '310', ai_cost_session: '1.2', risk_cap: '51.6', as_of_ms: NOW - 2 * MIN },
  open_positions: [
    { position_id: 'a', symbol: 'XAUUSDT', side: 1, entry: '2650', stop: '2640', margin: '120', leverage: 22, leg: 'tp1', stop_brain: null },
    { position_id: 'b', symbol: 'XAUUSDT', side: 1, entry: '2650', stop: '2640', margin: '220', leverage: 22, leg: 'runner', stop_brain: '2652' }],
  piggy: { total: '120', operating_equity: '2190', reference_equity: '2000', next_sweep_ms: NOW + 3 * 60 * MIN,
    sweeps: [[NOW - 21 * 60 * MIN, '120']] },
  reviews: [{ ts_ms: NOW - 5 * MIN, symbol: 'XAUUSDT', proposed: 'MODIFY_STOP', executed: 'MODIFY_STOP', code: 'stop_tightened',
    claude: 'CONFIRM', source: 'agreed' },
    { ts_ms: NOW - 35 * MIN, symbol: 'XAUUSDT', proposed: 'MODIFY_STOP', executed: 'HOLD', code: 'stop_not_tighter' }],
  config: { initial_equity: '2000', analyst: 'deepseek', cycle_minutes: 30, max_positions: 10, symbols: 27,
    leverage: [15, 50], risk_per_trade_pct: '4.300', open_risk_pct: '12.00', daily_stop_pct: '25.00',
    unico: { leverage_fit: true, position_review: true, partial: { fraction: '0.35', at_r: '2' }, max_hold_hours: null,
      claude: { model: 'claude-opus-5-5', daily_cap_usd: '3' },
      exit: { take_profit_r: '3.5' }, tiers: { selective_usd: '300', protect_usd: '400' },
      piggy: { reference_equity: '2000', tz: 'Europe/Rome', hour: 0 } } } })] });

test('Brain unico: one Brain without bot switch, mode and slots, piggy bank, legs and AI reviews', () => {
  const h = html({ data: unico() });
  expect(h).not.toContain('Scegli il bot');
  expect(h).toContain('Brain unico PAPER');
  for (const t of ['SELETTIVO', 'Slot 1/10', 'scelta dal codice', '35 % a 2R, residuo verso 3.5R, nessun limite di tempo', '27 mercati',
    'Claude consulente nei casi importanti', 'DeepSeek + Claude', 'Aperture valutate da Claude', 'scelta di Claude 1',
    'DeepSeek + Claude d’accordo 2 trade +$31,50', 'Claude: conferma', 'DeepSeek $0,900 · Claude $0,300',
    'Salvadanaio', 'Accantonato', '$120,00', 'Capitale operativo', '$2.190,00', 'senza\n      reintegri'.replace(/\s+/g, ' '),
    '1ª quota · presa a 2R', 'Residuo · verso 3,5R', 'Stop (Brain)', 'Revisioni AI delle posizioni (2)', 'stringe lo stop',
    'stop non più stretto: ignorato', 'a mezzanotte (ora italiana)'])
    expect(h.replace(/\s+/g, ' ')).toContain(t);
  // la modalità sta nella card di stato, sopra equity e posizioni
  expect(h.indexOf('SELETTIVO')).toBeLessThan(h.indexOf('Equity Brain'));
  expect(h.indexOf('Salvadanaio Brain')).toBeLessThan(h.indexOf('Posizioni aperte (2)'));
});
