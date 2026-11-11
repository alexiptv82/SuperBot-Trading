import { summarizeBrainPerformance } from './brainPerformance';

const trade = (id, pnl, day = 11) => ({
  position_id: id, symbol: 'BTCUSDT', side: 1,
  margin: '350', entry: '100', exit: '101', leverage: 20,
  realized_pnl: String(pnl), fees: '0.20',
  closed_at_ms: Date.UTC(2026, 10, day, 10, 20),
  exit_reason: 'take_profit',
});

test('Brain starts with zero trades and does not borrow Falco or Toro data', () => {
  const p = summarizeBrainPerformance([], {
    total_closed: 0, win_count: 0, loss_count: 0, break_even_count: 0,
  }, { id:'brain', realized_pnl:'0' }, true);
  expect(p.totalClosed).toBe(0);
  expect(p.totalNet).toBe(0);
  expect(p.days).toHaveLength(0);
  expect(p.profitFactor).toBeNull();
  expect(p.drawdown).toBeNull();
});

test('Brain computes only realized, net run-scoped outcomes and UTC diary', () => {
  const p = summarizeBrainPerformance([trade('a', 10), trade('b', -4, 12)], {
    total_closed: 2, win_count: 1, loss_count: 1,
  }, { id:'brain', realized_pnl:'6' }, true);
  expect(p.fullyLoaded).toBe(true);
  expect(p.totalNet).toBe(6);
  expect(p.winRate).toBe(50);
  expect(p.profitFactor).toBe(2.5);
  expect(p.totalFees).toBe(0.4);
  expect(p.days.map(d=>d.day)).toEqual(['2026-11-12','2026-11-11']);
  expect(p.assets).toHaveLength(1);
  expect(p.assets[0][1].trades).toBe(2);
});

test('Paginated Brain totals remain authoritative and partial breakdown is marked', () => {
  const p = summarizeBrainPerformance([trade('a', 10)], {
    total_closed: 2, win_count: 1, loss_count: 1,
  }, { realized_pnl:'6' }, false);
  expect(p.fullyLoaded).toBe(false);
  expect(p.totalClosed).toBe(2);
  expect(p.loaded).toBe(1);
  expect(p.totalNet).toBe(6);
  expect(p.profitFactor).toBeNull();
  expect(p.best).toBeNull();
  expect(p.drawdown).toBeNull();
});

test('Missing PnL is not silently converted to a profitable or break-even trade', () => {
  const t = trade('a', 10);
  t.realized_pnl = null;
  const p = summarizeBrainPerformance([t], { total_closed: 1, win_count: 0, loss_count: 0 }, {}, true);
  expect(p.records).toHaveLength(0);
  expect(p.fullyLoaded).toBe(false);
  expect(p.totalNet).toBeNull();
  expect(p.totalFees).toBeNull();
});

test('Missing starting data and invalid win counts never create fake win rate', () => {
  const p = summarizeBrainPerformance([trade('a', 10)], {
    total_closed: 1, win_count: null, loss_count: null,
  }, { realized_pnl:'10' }, true);
  expect(p.winRate).toBeNull();
  expect(p.winningTrades).toBeNull();
});
