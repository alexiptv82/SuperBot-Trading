/** Brain V3 data adapter for the same PAPER tabs used by Falco and Toro.
 *
 * Reads only the Brain run-scoped journal/API; never substitutes legacy
 * Brain-free data or positions from Falco/Toro. Missing marks stay unknown.
 */
export const PAPER_PORTFOLIOS = Object.freeze([
  Object.freeze({ id: 'hawk', label: '🦅 Falco', color: '#38bdf8' }),
  Object.freeze({ id: 'bull', label: '🐂 Toro', color: '#7c3aed' }),
  Object.freeze({ id: 'brain', label: '🧠 Brain', color: '#a78bfa' }),
]);

export const finiteNumber = value => {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

const safeInt = x => Number.isSafeInteger(x) && x >= 0 ? x : null;
const side = s => s === 1 || s === -1 ? s : null;

/** Map Brain's V3 positions into the already familiar classic Trade cards. */
export const brainOpenTrades = list => (Array.isArray(list) ? list : []).map(p => ({
  id: p.position_id,
  position_id: p.position_id,
  symbol: p.symbol,
  side: side(p.side),
  entry_price: finiteNumber(p.entry),
  live_price: finiteNumber(p.price),
  price_source: p.price_source || null,
  leverage: finiteNumber(p.leverage),
  margin: finiteNumber(p.margin),
  trade_type: p.strategy_id || 'Brain AI',
  pnl: finiteNumber(p.unrealized_pnl),
  pnl_pct: finiteNumber(p.roi_pct),
  open_ms: safeInt(p.opened_at_ms),
  sl: finiteNumber(p.stop),
  tp: finiteNumber(p.take_profit),
  entry_reason: p.strategy_id ? `Strategia Brain ${p.strategy_id}` : null,
  _isOpen: true,
}));

export const brainClosedTrades = list => (Array.isArray(list) ? list : []).map(t => ({
  id: t.position_id,
  position_id: t.position_id,
  symbol: t.symbol,
  side: side(t.side),
  entry_price: finiteNumber(t.entry),
  exit_price: finiteNumber(t.exit),
  leverage: finiteNumber(t.leverage),
  margin: finiteNumber(t.margin),
  trade_type: t.strategy_id || 'Brain AI',
  pnl: finiteNumber(t.realized_pnl),
  fees: finiteNumber(t.fees),
  close_reason: t.exit_reason || 'chiusura Brain',
  close_ms: safeInt(t.closed_at_ms),
  open_ms: Number.isSafeInteger(t.closed_at_ms) && Number.isSafeInteger(t.hold_ms) &&
    t.hold_ms >= 0 ? Math.max(0,t.closed_at_ms-t.hold_ms) : null,
  partial: t.partial === true,
  manual_learning: t.manual_learning || null,
  _isOpen: false,
}));

export function brainWalletSummary(portfolio, status, tradeData) {
  if (!portfolio || portfolio.id !== 'brain') return null;
  const positionList = Array.isArray(tradeData?.open_positions) ? tradeData.open_positions : [];
  const open = brainOpenTrades(positionList);
  const pnlNumbers = open.map(t => t.pnl);
  const unrealized = !open.length ? 0
    : pnlNumbers.every(x => x != null) ? pnlNumbers.reduce((a,b) => a+b,0) : null;
  const cash = finiteNumber(portfolio.cash);
  // Settled equity is deliberately NOT the total equity when open prices are unknown.
  const equity = finiteNumber(portfolio.equity);
  const settled = finiteNumber(portfolio.settled_equity);
  const realized = finiteNumber(portfolio.realized_pnl);
  const start = finiteNumber(portfolio.start_equity);
  return {
    id: 'brain',
    state: portfolio.state,
    available: true,
    bot_mode: portfolio.state === 'running' ? 'running' : 'paused',
    start_equity: start,
    equity,
    settled_equity: settled,
    equity_basis: portfolio.equity_basis || 'unavailable',
    cash, // no inferred cash from starting capital
    margin_used: finiteNumber(portfolio.margin_in_use),
    unrealized_pnl: unrealized,
    pnl_total: realized,
    pnl_total_pct: start && realized != null ? realized / start * 100 : null,
    day_pnl: finiteNumber(portfolio.day_pnl),
    total_closed: safeInt(portfolio.total_closed),
    win_rate: finiteNumber(portfolio.win_rate),
    win_count: safeInt(tradeData?.win_count),
    loss_count: safeInt(tradeData?.loss_count),
    max_open: null, // only display a limit when the live run config provides it
    positions: open,
    close_pending: tradeData?.close_pending === true,
    manual_close_allowed: portfolio.manual_close_allowed === true,
    last_decision: status?.last_decision || null,
    peer_observations: Array.isArray(portfolio.peer_observations) ? portfolio.peer_observations : [],
    spend: status?.spend || null,
  };
}
