import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { OverviewContent } from './Overview';
import ClassicStopNotice from '../components/ClassicStopNotice';

const status = (state, quote_coverage = false, reason = 'coverage_' + state) => ({
  scope: 'maintenance_exit_only', state, quote_coverage, alarm: !quote_coverage,
  reason, stop_certified: false, execution: 'closed_1m_close_only',
  intrabar_wick: 'not_a_fill'
});
const view = health => renderToStaticMarkup(
  <ClassicStopNotice health={health} openPositions={1} />
);

test('fresh quotes are never described as a certified stop', () => {
  const html = view(status('covered', true, 'one_minute_close_only'));
  expect(html).toContain('Monitor prezzi PAPER');
  expect(html).toContain('1 minuto');
  expect(html).toContain('non equivale a stop-loss certificato');
  expect(html).toContain('role="status"');
  expect(html).not.toContain('stop garantito');
});

test.each(['blind', 'partial', 'stale', 'off', 'blocked', 'telemetry_failed', 'unverified'])(
  'state %s shows an explicit warning when a trade is open', state => {
    const html = view(status(state));
    expect(html).toContain('role="alert"');
    expect(html).toContain('Protezione stop da verificare');
  }
);

test('running classic engine does not inherit maintenance RC80 coverage', () => {
  const html = view(status('unverified', false, 'maintenance_worker_not_active'));
  expect(html).toContain('motore operativo');
  expect(html).toContain('role="alert"');
});

test('no open positions need no extra warning', () => {
  const html = renderToStaticMarkup(
    <ClassicStopNotice health={status('off')} openPositions={0} />);
  expect(html).toBe('');
});

test('overview binds a classic portfolio health object without issuing commands', () => {
  const html = renderToStaticMarkup(
    <OverviewContent
      overview={{ generated_at_ms:1700000100000, cutover_readonly:true,
        portfolios:[{ id:'falco', kind:'classic', state:'paused', open_positions:1,
          positions:[], stop_health:status('blind'), realized_pnl:'0',
          margin_in_use:'100', close_worker_mode:'exit_only', can_close_position:false
        }] }}
      status={{state:'not_started'}} scoreboard={{regimes:[]}}
      trades={{open_positions:[],closed_trades:[]}}
      nowMs={1700000100000} regime="" onRegime={() => {}} />
  );
  expect(html).toContain('Portafoglio falco');
  expect(html).toContain('classic-stop-notice');
  expect(html).toContain('Nessuna posizione ha un prezzo verificato');
});

test('inconsistent covered flag never claims that quote data is available', () => {
  const html = view(status('covered', false));
  expect(html).toContain('role="alert"');
  expect(html).toContain('Copertura prezzi non dimostrata');
  expect(html).not.toContain('Prezzi recenti disponibili');
  expect(html).toContain('non equivale a stop-loss certificato');
});


const runnerStatus = (state, alarm = true, blocked_symbols = []) => ({
  scope: 'classic_runner_15m_ohlc', state, alarm,
  blocked_symbols, stop_certified: false, quote_coverage: false,
  execution: 'periodic_15m_ohlc',
});

test('running OHLC good state is never called certified or continuous', () => {
  const html = view(runnerStatus('observed', false));
  expect(html).toContain('role="status"');
  expect(html).toContain('ultimo ciclo');
  expect(html).toContain('15 minuti');
  expect(html).toContain('30 minuti');
  expect(html.toLowerCase()).toContain('non è monitoraggio continuo');
  expect(html).toContain('non equivale a stop-loss certificato');
  expect(html).not.toContain('ultima candela 1m');
});

test.each(['stale', 'unverified', 'degraded'])(
  'running status %s creates an explicit warning', state => {
    const html = view(runnerStatus(state));
    expect(html).toContain('role="alert"');
    expect(html).toContain('Allarme controllo stop PAPER');
    expect(html).not.toContain('Prezzi recenti disponibili');
  }
);

test('running alarm with no positions still displays blocked exposure symbols', () => {
  const html = renderToStaticMarkup(
    <ClassicStopNotice health={runnerStatus('degraded', true, ['ARB'])} openPositions={0} />);
  expect(html).toContain('role="alert"');
  expect(html).toContain('ARB');
  expect(html).toContain('Nuovi ingressi/DCA');
});

test('running observed state with alarm true never gives a green status', () => {
  const html = view(runnerStatus('observed', true));
  expect(html).toContain('role="alert"');
  expect(html).toContain('non verificabile');
});

test('runner and maintenance monitors never display each other\'s model', () => {
  const running = view(runnerStatus('observed', false));
  const maintenance = view(status('covered', true, 'one_minute_close_only'));
  expect(running).toContain('OHLC');
  expect(running).not.toContain('monitor RC80');
  expect(maintenance).toContain('Il monitor RC80');
  expect(maintenance).not.toContain('intervalli di circa 15 minuti');
});


test('missing stop health shows neutral warning without pretending 1m or 15m protection', () => {
  for (const payload of [null, undefined, {scope:'unknown'}]) {
    const html = view(payload);
    expect(html).toContain('role="alert"');
    expect(html).toContain('Dati di protezione non disponibili');
    expect(html).not.toContain('chiusura della candela da 1 minuto');
    expect(html).not.toContain('controllano gli estremi delle candele 15m');
    expect(html).not.toContain('stop-loss certificato');
  }
  const empty = renderToStaticMarkup(
    <ClassicStopNotice health={null} openPositions={0} />);
  expect(empty).toBe('');
});
