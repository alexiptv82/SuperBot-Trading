import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ClaimReconciliationNotice from './ClaimReconciliationNotice';
import { OverviewContent } from '../pages/Overview';

const html = (props) => renderToStaticMarkup(<ClaimReconciliationNotice {...props} />);
const rec = (state, extra = {}) => ({ state, pending_count: 0, conflict_count: 0, affected_symbols: [],
  checkpointed_not_final: state !== 'ok', ...extra });

test('ok renders nothing', () => {
  expect(html({ recon: rec('ok') })).toBe('');
});

test('pending is an alert, names symbols and says P&L may include unconfirmed closes', () => {
  const out = html({ recon: rec('pending', { pending_count: 2, affected_symbols: ['BTC', 'ETH'] }) });
  expect(out).toContain('role="alert"');
  expect(out).toContain('Chiusure PAPER in riconciliazione');
  expect(out).toContain('BTC, ETH');
  expect(out).toContain('possono includere chiusure non ancora definitive');
  expect(out).toContain('non vengono azzerati né ricalcolati');
  expect(out).toContain('In attesa: 2');
});

test('conflict is distinct and says human intervention is needed', () => {
  const out = html({ recon: rec('conflict', { conflict_count: 1, affected_symbols: ['SOL'] }) });
  expect(out).toContain('Conflitto contabile');
  expect(out).toContain('intervento umano');
  expect(out).toContain('reset del portafoglio è rifiutato');
  expect(out).toContain('In conflitto: 1');
});

test('unknown, missing, null and malformed payloads are fail-visible', () => {
  for (const recon of [rec('unknown'), null, undefined, {}, 'x', { state: 'weird' }]) {
    const out = html({ recon });
    expect(out).toContain('role="alert"');
    expect(out).toContain('non verificabile');
  }
});

test('a portfolio that never started does not show the unknown alert, but a real conflict is always shown', () => {
  expect(html({ recon: null, notStarted: true })).toBe('');
  expect(html({ recon: rec('unknown'), notStarted: true })).toBe('');
  expect(html({ recon: rec('conflict'), notStarted: true })).toContain('Conflitto contabile');
});

test('only safe, validated text is rendered', () => {
  const out = html({ recon: rec('pending', { affected_symbols: ['<img src=x>', 'BTC', 'A'.repeat(40)],
    pending_count: '1; drop', secret: 'password', claim_id: 'abc' }) });
  expect(out).not.toContain('<img');
  expect(out).not.toContain('password');
  expect(out).not.toContain('abc');
  expect(out).toContain('BTC');
  expect(out).toContain('In attesa: —');
});

test('has no controls or forms: read-only', () => {
  const out = html({ recon: rec('pending', { pending_count: 1 }) });
  expect(out).not.toMatch(/<(button|form|input|a )/);
});

const now = 1700000100000;
const content = (falco) => renderToStaticMarkup(<OverviewContent
  overview={{ generated_at_ms: now, cutover_readonly: true, portfolios: [
    { id: 'falco', kind: 'classic', state: 'running', open_positions: 0, realized_pnl: '5.03', margin_in_use: '0',
      total_closed: 1, last_event_ms: now - 1000, ...falco },
    { id: 'toro', kind: 'classic', state: 'paused', open_positions: 0, realized_pnl: '0', margin_in_use: '0',
      close_reconciliation: rec('ok') },
    { id: 'brain', kind: 'brain', state: 'not_started', open_positions: 0, realized_pnl: '0', margin_in_use: '0' },
  ] }}
  status={null} scoreboard={null} trades={null} nowMs={now} regime="" onRegime={() => {}} />);

test('Overview shows the alert for Falco with zero open positions and keeps the amounts untouched', () => {
  const out = content({ close_reconciliation: rec('pending', { pending_count: 1, affected_symbols: ['BTC'] }) });
  expect(out).toContain('Chiusure PAPER in riconciliazione');
  expect(out).toContain('5.03');
  expect(out).toContain('Posizioni aperte');
});

test('Overview: recovery completed removes the alert, Toro ok never shows it, Brain is never given one', () => {
  const out = content({ close_reconciliation: rec('ok') });
  expect(out).not.toContain('riconciliazione');
  expect(out).not.toContain('Conflitto contabile');
});

test('Overview: Falco without the field (old backend) is flagged as not verifiable', () => {
  expect(content({})).toContain('Stato di riconciliazione non verificabile');
});

test('Overview works with Brain data absent and still shows the Falco conflict', () => {
  const out = content({ close_reconciliation: rec('conflict', { conflict_count: 1, affected_symbols: ['ETH'] }) });
  expect(out).toContain('Conflitto contabile');
  expect(out).toContain('ETH');
});
