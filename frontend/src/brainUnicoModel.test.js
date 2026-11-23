import { brainStateCard, freeCash, num, openPnl, shownResults } from './brainUnicoModel';

const p = { id: 'brain', state: 'running' };

test('num never turns blanks, booleans or garbage into numbers', () => {
  expect([null, undefined, '', true, 'abc', NaN].map(num)).toEqual([null, null, null, null, null, null]);
  expect(num('8.33')).toBe(8.33);
});

test('state card: mandate, budget, risk, halted, paused, stale, running', () => {
  const st = extra => ({ state: 'running', heartbeat: { last_error: null }, ...extra });
  expect(brainStateCard(p, st()).key).toBe('operational');
  expect(brainStateCard(p, st({ state: 'stale' })).key).toBe('stale');
  expect(brainStateCard(p, st({ paused: true })).key).toBe('paused');
  expect(brainStateCard(p, st({ state: 'halted' })).key).toBe('halted');
  expect(brainStateCard(p, st({ daily_loss: { level: 'halt', pct: '50.0' } })).key).toBe('risk');
  expect(brainStateCard(p, st({ state: 'halted', heartbeat: { last_error: 'ledger_error' } })).key).toBe('budget');
  expect(brainStateCard(p, st({ state: 'paused', heartbeat: { last_error: 'halted:mandate_not_approved' } })).key).toBe('mandate');
  expect(brainStateCard({ id: 'brain', state: 'not_started' }, null).key).toBe('not_started');
  expect(brainStateCard(null, null).key).toBe('unknown');
  expect(brainStateCard(p, st({ state: 'toString' })).key).toBe('unknown');
});

test('free cash is settled equity minus margin, otherwise unknown (never from the starting capital)', () => {
  expect(freeCash({ settled_equity: '2008.33', margin_in_use: '40' })).toBeCloseTo(1968.33);
  expect(freeCash({ settled_equity: null, margin_in_use: '40', start_equity: '2000' })).toBeNull();
  expect(freeCash({ settled_equity: '2000' })).toBeNull();
});

test('open P&L is zero without positions, unknown when any mark is missing', () => {
  expect(openPnl(null)).toBeNull();
  expect(openPnl({ open_positions: [] })).toBe(0);
  expect(openPnl({ open_positions: [{ unrealized_pnl: '2.5' }, { unrealized_pnl: '-1' }] })).toBeCloseTo(1.5);
  expect(openPnl({ open_positions: [{ unrealized_pnl: '2.5' }, { unrealized_pnl: null }] })).toBeNull();
});

test('shown results sum only the displayed closed trades', () => {
  expect(shownResults({ closed_trades: [{ realized_pnl: '4' }, { realized_pnl: '-3' }, { realized_pnl: null }] }))
    .toEqual({ count: 2, gains: 4, losses: -3 });
  expect(shownResults(null)).toEqual({ count: 0, gains: 0, losses: 0 });
});
