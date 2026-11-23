import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import API from '../api';
import PaperBots, { PaperBotsContent } from './PaperBots';

jest.mock('../api', () => ({ get: jest.fn(), post: jest.fn() }));

const NOW = 1_800_000_000_000;
const MIN = 60_000;
const run = (name, label, over = {}) => ({
  name, label, run_id: name, available: true, state: 'running', paused: false, initial_equity: '1000',
  settled_equity: '1010', net_pnl: '10', return_pct: '1.00', ai_cost_total: '0.2', net_after_ai: '9.8',
  closed: 5, wins: 3, losses: 2, manual_closes: 1, protected_stops: 2, manual_close_allowed: true,
  guardian: { state: 'SELECTIVE', reasons: ['floor_armed'], equity: '1042.5', session_start_equity: '1000',
    peak_equity: '1100', giveback: '57.5', floor: '1075', budget: '40', risk_cap: '20', unrealized: '32.5',
    open_risk: '30', as_of_ms: NOW - 3 * MIN },
  open_positions: [{ position_id: 'p1', symbol: 'BTCUSDT', side: -1, entry: '100', stop: '101', margin: '150', leverage: 30 }],
  ai_spend: { day: '0.042', total: '0.3' },
  config: { initial_equity: '1000', analyst: 'falco_evoluto', cycle_minutes: 15, max_positions: 4, daily_cap_usd: '0.20',
    leverage: [15, 45], margin: ['100', '250'] },
  decisions: [{ ts_ms: NOW - 3 * MIN, symbol: 'ETHUSDT', kind: 'NO_TRADE', rationale: 'falco_no_trade_regime' },
    { ts_ms: NOW - 18 * MIN, symbol: 'SOLUSDT', kind: 'NO_TRADE', rationale: 'risk_rejected', risk_reason: 'below_min_margin' },
    { ts_ms: NOW - 33 * MIN, symbol: 'XRPUSDT', kind: 'NO_TRADE', rationale: '<b>x</b>' }],
  ...over });
const both = () => ({ available: true, generated_at_ms: NOW - 20_000, runs: [
  run('falco_evoluto', 'Falco Evoluto'),
  run('brain_scalp', 'Brain Scalp', { paused: true, initial_equity: '2000', settled_equity: '1990', net_pnl: '-10',
    guardian: { state: 'LOCKED', reasons: ['below_floor'], equity: '1975', session_start_equity: '2000', as_of_ms: NOW - 9 * MIN },
    open_positions: [{ position_id: 's1', symbol: 'ETHUSDT', side: 1, entry: '10', stop: '9.9', margin: '300', leverage: 20 }],
    config: { initial_equity: '2000', analyst: 'deepseek', cycle_minutes: 30, max_positions: 4, daily_cap_usd: '0.75',
      leverage: [15, 45], margin: ['250', '450'] } })] });

test('both summaries always visible; below only the selected bot (Falco Evoluto by default)', () => {
  const h = renderToStaticMarkup(<PaperBotsContent data={both()} nowMs={NOW} />);
  // riepilogo di ENTRAMBI, sempre
  for (const t of ['Falco Evoluto', 'Brain Scalp', 'RUNNING', 'PAUSA', '$1042.50', '(+4.25%)', '$1975.00', 'Storico'])
    expect(h).toContain(t);
  // dettagli del solo Falco Evoluto
  for (const t of ['Dettagli Falco Evoluto', 'Ultimo giro 3 min fa', 'Equity a mercato', '+$42.50', 'su capitale $1000',
    'Selettivo', 'floor armato', 'Posizioni aperte', 'SHORT', 'x30', 'Chiudi BTCUSDT (PAPER)', 'Dopo AI', '+$9.80',
    'Budget AI', 'regole Falco Evoluto', 'giro ogni 15 min', 'nessun trade: mercato laterale, incerto o shock',
    'margine sotto il minimo', '3 min fa']) expect(h).toContain(t);
  for (const t of ['Dettagli Brain Scalp', 'Chiudi ETHUSDT (PAPER)', 'Bloccato', 'DeepSeek', 'giro ogni 30 min', 'Capitale $2000'])
    expect(h).not.toContain(t);
  expect(h.indexOf('Falco Evoluto')).toBeLessThan(h.indexOf('Brain Scalp'));
  expect(h).not.toContain('$NaN');
  expect(h).not.toContain('undefined');
  expect(h).not.toContain('<b>x</b>');
  expect(h).not.toContain('&lt;b&gt;');                       // un codice sconosciuto non diventa mai testo
});

test('selecting Brain Scalp shows only its details, with all the information', () => {
  const h = renderToStaticMarkup(<PaperBotsContent data={both()} nowMs={NOW} initialSelected="brain_scalp" />);
  for (const t of ['Dettagli Brain Scalp', 'PAUSA', 'Nessuna nuova apertura', '$1975.00', '-$25.00', 'Capitale $2000',
    'Bloccato', 'equity sotto il floor', 'LONG', 'x20', 'Chiudi ETHUSDT (PAPER)', 'DeepSeek', 'giro ogni 30 min',
    'Posizioni aperte', 'Ultime decisioni · Brain Scalp']) expect(h).toContain(t);
  for (const t of ['Dettagli Falco Evoluto', 'Chiudi BTCUSDT (PAPER)', 'regole Falco Evoluto', 'Selettivo'])
    expect(h).not.toContain(t);
  expect(h).toContain('$1042.50');                            // il riepilogo di Falco Evoluto resta in vista
});

test('the main screen is not RC1 any more, and RC1, Falco classico and Toro stay reachable from the Storico', () => {
  const h = renderToStaticMarkup(<PaperBotsContent data={both()} nowMs={NOW} />);
  expect(h).not.toContain('Brain Unico');
  for (const href of ['/brain-unico/rc1', '/overview', '/compare', '/classic', '/brain/archive', '/arena'])
    expect(h).toContain(`href="${href}"`);
  expect(h).toContain('Brain RC1');
  expect(h).toContain('Falco classico');
  expect(h).toContain('Toro');
});

test('no start/pause controls and no close-all: only single manual closes', () => {
  const h = renderToStaticMarkup(<PaperBotsContent data={both()} nowMs={NOW} />);
  expect(h).not.toMatch(/Avvia|Riprendi|Chiudi tutte/);
  expect(h).not.toMatch(/<button[^>]*>\s*⏸/);
  expect(h).toContain('avvio, pausa e mandato restano un intervento del proprietario');
});

test('a stale RUNNING is said out loud instead of a reassuring badge', () => {
  const old = both();
  old.runs[0].guardian.as_of_ms = NOW - 3 * 60 * MIN;
  old.runs[0].decisions = [{ ts_ms: NOW - 3 * 60 * MIN, symbol: 'ETHUSDT', kind: 'NO_TRADE' }];
  const h = renderToStaticMarkup(<PaperBotsContent data={old} nowMs={NOW} />);
  expect(h).toContain('Nessun giro recente');
  expect(h).toContain('3 h 00 min fa');
});

test('halted, not started and not prepared bots show their state and no money', () => {
  const data = { available: true, runs: [run('falco_evoluto', 'Falco Evoluto', { state: 'halted' }),
    { name: 'brain_scalp', label: 'Brain Scalp', available: false, reason: 'not_started' }] };
  const h = renderToStaticMarkup(<PaperBotsContent data={data} nowMs={NOW} />);
  expect(h).toContain('FERMO');
  expect(h).toContain('NON AVVIATO');
  const s = renderToStaticMarkup(<PaperBotsContent data={data} nowMs={NOW} initialSelected="brain_scalp" />);
  expect(s).toContain('Nessun dato viene mostrato finché non esiste il suo journal');
});

test('without guardian samples and without positions nothing is invented', () => {
  const data = { available: true, runs: [run('falco_evoluto', 'Falco Evoluto',
    { guardian: null, open_positions: [], decisions: [], net_after_ai: null, ai_spend: {} })] };
  const h = renderToStaticMarkup(<PaperBotsContent data={data} nowMs={NOW} />);
  expect(h).toContain('Equity contabile');
  expect(h).toContain('Nessuna valutazione registrata finora');
  expect(h).toContain('Nessuna posizione aperta al momento');
  expect(h).toContain('Nessuna decisione registrata');
  expect(h).not.toContain('$NaN');
});

test('bots not yet active and a failed load still leave the Storico reachable', () => {
  const off = renderToStaticMarkup(<PaperBotsContent data={{ available: false, runs: [] }} nowMs={NOW} />);
  expect(off).toContain('Bot non ancora attivi');
  expect(off).not.toMatch(/\$\d/);
  expect(off).toContain('href="/brain-unico/rc1"');
  const err = renderToStaticMarkup(<PaperBotsContent data={null} error nowMs={NOW} />);
  expect(err).toContain('role="alert"');
  expect(err).toContain('href="/brain-unico/rc1"');
  expect(err).toContain('href="/overview"');
  expect(renderToStaticMarkup(<PaperBotsContent data={null} nowMs={NOW} />)).toContain('Caricamento dei bot');
});

test('loads only the read-only compare endpoint', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  API.get.mockResolvedValue({ data: both() });
  const el = document.createElement('div');
  const root = createRoot(el);
  try {
    await act(async () => { root.render(<PaperBots />); });
    expect(API.get).toHaveBeenCalledTimes(1);
    expect(API.get).toHaveBeenCalledWith('/api/v3/compare');
    expect(el.textContent).toContain('Falco Evoluto');
    expect(el.textContent).toContain('Brain Scalp');
  } finally { await act(async () => { root.unmount(); }); API.get.mockReset(); }
});

test('a failed request shows the alert and keeps the Storico', async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  API.get.mockRejectedValue(new Error('x'));
  const el = document.createElement('div');
  const root = createRoot(el);
  try {
    await act(async () => { root.render(<PaperBots />); });
    expect(el.querySelector('[role="alert"]')).not.toBeNull();
    expect(el.querySelector('a[href="/brain-unico/rc1"]')).not.toBeNull();
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
    await act(async () => { root.render(<PaperBotsContent data={both()} nowMs={NOW} />); });
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
  const h = renderToStaticMarkup(<PaperBotsContent data={data} nowMs={NOW} />);
  expect(h).toMatch(/<button[^>]*disabled=""[^>]*>Chiudi BTCUSDT \(PAPER\)<\/button>/);
  expect(h).toContain('servizio uscite di questo portafoglio non è sano');
  const s = renderToStaticMarkup(<PaperBotsContent data={data} nowMs={NOW} initialSelected="brain_scalp" />);
  expect(s).toMatch(/<button[^>]*>Chiudi ETHUSDT \(PAPER\)<\/button>/);
  expect(s).not.toMatch(/<button[^>]*disabled=""[^>]*>Chiudi ETHUSDT \(PAPER\)<\/button>/);
});

// ---- selettori (schede superiori)
async function mount(data, props = {}) {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  const el = document.createElement('div');
  document.body.appendChild(el);
  const root = createRoot(el);
  await act(async () => { root.render(<PaperBotsContent data={data} nowMs={NOW} {...props} />); });
  const tile = name => el.querySelector(`button[data-bot="${name}"]`);
  const region = () => el.querySelector('[role="region"]');
  const tap = async b => { await act(async () => { b.dispatchEvent(new MouseEvent('click', { bubbles: true })); }); };
  return { el, root, tile, region, tap, close: async () => { await act(async () => { root.unmount(); }); el.remove(); } };
}

test('the two top tiles are real buttons: tap or keyboard selects, the selected one is highlighted', async () => {
  const m = await mount(both());
  try {
    for (const name of ['falco_evoluto', 'brain_scalp']) {
      const b = m.tile(name);
      expect(b.tagName).toBe('BUTTON');                          // nativo: tocco Android/PWA, Tab, Invio e Spazio
      expect(b.getAttribute('type')).toBe('button');
      expect(b.disabled).toBe(false);
      expect(b.getAttribute('tabindex')).toBeNull();             // raggiungibile con Tab
      expect(b.getAttribute('aria-controls')).toBe(`bot-dettagli-${name}`);
    }
    expect(m.tile('falco_evoluto').getAttribute('aria-pressed')).toBe('true');
    expect(m.tile('brain_scalp').getAttribute('aria-pressed')).toBe('false');
    expect(m.tile('falco_evoluto').style.border).toContain('2px solid');
    expect(m.tile('falco_evoluto').textContent).toContain('dettagli sotto');
    expect(m.region().id).toBe('bot-dettagli-falco_evoluto');

    m.tile('brain_scalp').focus();
    expect(document.activeElement).toBe(m.tile('brain_scalp'));
    await m.tap(m.tile('brain_scalp'));                        // Invio/Spazio su un <button> generano questo click
    expect(m.tile('brain_scalp').getAttribute('aria-pressed')).toBe('true');
    expect(m.tile('falco_evoluto').getAttribute('aria-pressed')).toBe('false');
    expect(m.tile('brain_scalp').style.border).toContain('2px solid');
    expect(m.tile('falco_evoluto').style.border).not.toContain('2px solid');
    expect(m.region().id).toBe('bot-dettagli-brain_scalp');
    expect(m.region().getAttribute('aria-label')).toBe('Dettagli Brain Scalp');
    expect(m.region().textContent).toContain('Chiudi ETHUSDT (PAPER)');
    expect(m.region().textContent).not.toContain('Chiudi BTCUSDT (PAPER)');
    expect(m.el.querySelectorAll('section[aria-label^="Bot "]').length).toBe(1);
    // il riepilogo di entrambi resta
    expect(m.tile('falco_evoluto').textContent).toContain('$1042.50');
    expect(m.tile('brain_scalp').textContent).toContain('$1975.00');

    await m.tap(m.tile('falco_evoluto'));
    expect(m.region().id).toBe('bot-dettagli-falco_evoluto');
    expect(m.region().textContent).toContain('Chiudi BTCUSDT (PAPER)');
  } finally { await m.close(); }
});

test('a FERMO bot stays visible in its tile while the other one is selected', async () => {
  const data = both();
  data.runs[1] = { ...data.runs[1], paused: false, state: 'halted' };
  const m = await mount(data);
  try {
    expect(m.region().id).toBe('bot-dettagli-falco_evoluto');
    expect(m.tile('brain_scalp').textContent).toContain('FERMO');
    expect(m.tile('brain_scalp').getAttribute('aria-label')).toContain('FERMO');
    await m.tap(m.tile('brain_scalp'));
    expect(m.region().textContent).toContain('FERMO');
    expect(m.region().textContent).toContain('nessuna nuova apertura');
  } finally { await m.close(); }
});

test('the choice survives the 30 s refresh; a bot that disappears falls back to the first one', async () => {
  const m = await mount(both());
  try {
    await m.tap(m.tile('brain_scalp'));
    const fresh = both();
    fresh.runs[1].settled_equity = '1980';
    await act(async () => { m.root.render(<PaperBotsContent data={fresh} nowMs={NOW + 30_000} />); });
    expect(m.region().id).toBe('bot-dettagli-brain_scalp');
    const onlyFalco = { ...both(), runs: [both().runs[0]] };
    await act(async () => { m.root.render(<PaperBotsContent data={onlyFalco} nowMs={NOW + 60_000} />); });
    expect(m.region().id).toBe('bot-dettagli-falco_evoluto');
  } finally { await m.close(); }
});

test('a bot not yet started can be selected and shows its state, no money', async () => {
  const data = { available: true, runs: [run('falco_evoluto', 'Falco Evoluto'),
    { name: 'brain_scalp', label: 'Brain Scalp', available: false, reason: 'not_started' }] };
  const m = await mount(data);
  try {
    expect(m.tile('brain_scalp').textContent).toContain('NON AVVIATO');
    await m.tap(m.tile('brain_scalp'));
    expect(m.region().textContent).toContain('NON AVVIATO');
    expect(m.region().textContent).not.toMatch(/\$\d/);
  } finally { await m.close(); }
});
