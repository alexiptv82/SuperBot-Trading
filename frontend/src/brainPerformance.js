/** Read-only Brain V3 PERFORMANCE adapter.
 * All accounting comes from the run-scoped /api/v3 endpoints; never mix with
 * classic portfolios, old Brain Free, or unrealized PnL.
 */
import { brainClosedTrades, finiteNumber } from './brainWallet';

const validTimestamp = ms => Number.isSafeInteger(ms) && ms > 0 && ms < 8640000000000000;
const round = n => Math.round(n * 100) / 100;

export function summarizeBrainPerformance(rawTrades, counts, wallet, fullyLoaded) {
  const records = brainClosedTrades(rawTrades).filter(t =>
    validTimestamp(t.close_ms) && Number.isFinite(t.pnl));
  const closed = Number.isSafeInteger(counts?.total_closed) && counts.total_closed >= 0
    ? counts.total_closed : null;
  const wins = Number.isSafeInteger(counts?.win_count) && counts.win_count >= 0
    ? counts.win_count : null;
  const losses = Number.isSafeInteger(counts?.loss_count) && counts.loss_count >= 0
    ? counts.loss_count : null;
  const full = fullyLoaded && closed != null && records.length === closed;
  const allNet = finiteNumber(wallet?.realized_pnl);
  const totalNet = allNet == null
    ? full ? records.reduce((s, t) => s + t.pnl, 0) : null : allNet;
  const days = new Map();
  const assets = new Map();
  const reasons = new Map();
  const sides = new Map();
  let totalFees = 0;
  let feesComplete = true;
  let gains = 0, grossLosses = 0;
  for (const t of records) {
    const day = new Date(t.close_ms).toISOString().slice(0, 10);
    const d = days.get(day) || { day, total_trades: 0, wins: 0, losses: 0, total_pnl: 0, trades: [] };
    d.total_trades += 1;
    d.wins += Number(t.pnl > 0);
    d.losses += Number(t.pnl < 0);
    d.total_pnl += t.pnl;
    d.trades.push(t);
    days.set(day, d);
    const groups = [
      [assets, t.symbol || 'N/D'],
      [reasons, t.close_reason || 'altro'],
      [sides, t.side === 1 ? 'long' : t.side === -1 ? 'short' : 'N/D'],
    ];
    for (const [map, label] of groups) {
      const val = map.get(label) || { trades: 0, wins: 0, losses: 0, net_pnl: 0 };
      val.trades++;
      val.wins += Number(t.pnl > 0);
      val.losses += Number(t.pnl < 0);
      val.net_pnl += t.pnl;
      map.set(label, val);
    }
    if (t.pnl > 0) gains += t.pnl;
    else if (t.pnl < 0) grossLosses += Math.abs(t.pnl);
    if (t.fees == null) feesComplete = false;
    else totalFees += t.fees;
  }
  return {
    records,
    fullyLoaded: full,
    loaded: records.length,
    totalClosed: closed,
    winningTrades: wins,
    losingTrades: losses,
    breakEvenTrades: Number.isSafeInteger(counts?.break_even_count) ? counts.break_even_count : null,
    winRate: closed && wins != null ? round(wins / closed * 100) : closed === 0 ? 0 : null,
    totalNet: totalNet == null ? null : round(totalNet),
    avgNet: totalNet != null && closed ? round(totalNet / closed) : null,
    profitFactor: full && grossLosses > 0 ? round(gains / grossLosses) : null,
    best: full && records.length ? Math.max(...records.map(t => t.pnl)) : null,
    worst: full && records.length ? Math.min(...records.map(t => t.pnl)) : null,
    totalFees: full && feesComplete ? round(totalFees) : null,
    days: [...days.values()].sort((a,b) => b.day.localeCompare(a.day)),
    assets: [...assets.entries()].sort((a,b) => b[1].net_pnl - a[1].net_pnl),
    reasons: [...reasons.entries()].sort((a,b) => b[1].trades - a[1].trades),
    sides: [...sides.entries()],
    // A drawdown from just realized closes is not the run's actual equity drawdown.
    drawdown: null,
  };
}
