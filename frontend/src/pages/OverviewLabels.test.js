import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { OverviewContent, exitReasonText } from './Overview';
import { closeResultMessages } from '../components/OverviewCloseControls';

jest.mock('../api', () => ({ get: jest.fn() }));

const now = 1700000100000;

test.each([
  ['stop', 'stop'],
  ['take_profit', 'obiettivo raggiunto'],
  ['timeout', 'tempo scaduto'],
  ['manual', 'chiusa da te'],
  ['brain_close', 'chiusa dal Brain'],
  ['liquidation', 'liquidata'],
  ['qualcosa_di_nuovo', 'altro'],
  ['constructor', 'altro'],
  ['__proto__', 'altro'],
  [undefined, 'altro'],
  [null, 'altro'],
  [42, 'altro'],
])('motivo di chiusura %j -> %s', (code, text) => {
  expect(exitReasonText(code)).toBe(text);
});

test('la lista dei trade chiusi mostra il motivo in parole, mai il codice grezzo', () => {
  const trade = (id, reason) => ({ position_id: id, symbol: 'ETHUSDT', side: 1, strategy_id: 'S07', regime: 'RANGE',
    exit_reason: reason, net_bp: '10.0000', hold_ms: 1000, closed_at_ms: now - 1000 });
  const data = { overview: { generated_at_ms: now, portfolios: [] }, status: { state: 'not_started', spend: null }, scoreboard: { regimes: [] },
    trades: { open_positions: [], closed_trades: [trade('a', 'take_profit'), trade('b', 'manual'), trade('c', 'xyz_nuovo')] } };
  const html = renderToStaticMarkup(<OverviewContent {...data} nowMs={now} regime="" onRegime={() => {}} />);
  expect(html).toContain('obiettivo raggiunto');
  expect(html).toContain('chiusa da te');
  expect(html).toContain('· altro ·');
  expect(html).not.toContain('take_profit');
  expect(html).not.toContain('xyz_nuovo');
});

test('esiti di chiusura: il simbolo al posto dell’identificativo tecnico', () => {
  const names = { 'aaa111': 'BTCUSDT', 'bbb222': 'ETHUSDT' };
  const nameOf = id => names[id] || 'Posizione';
  const msg = closeResultMessages({ status: 'done', closed: ['aaa111'],
    failed: [['bbb222', 'price_unavailable'], ['ccc333', 'position_already_closed']] }, nameOf).join(' | ');
  expect(msg).toContain('BTCUSDT: posizione chiusa.');
  expect(msg).toContain('ETHUSDT: prezzo non disponibile, riprova.');
  expect(msg).toContain('Posizione: posizione già chiusa.');
  expect(msg).not.toContain('aaa111');
  expect(msg).not.toContain('bbb222');
  expect(msg).not.toContain('ccc333');
});

test('senza funzione di traduzione il comportamento resta quello consegnato', () => {
  expect(closeResultMessages({ status: 'done', closed: ['p-001'], failed: [] })).toEqual(['p-001: posizione chiusa.']);
});
