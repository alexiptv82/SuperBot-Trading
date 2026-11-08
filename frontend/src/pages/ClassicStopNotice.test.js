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
