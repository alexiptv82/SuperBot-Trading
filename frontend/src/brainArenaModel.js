/** AI Arena read-only model. Unknown data is never replaced by invented PnL. */
export const ARENA_PROFILES = Object.freeze([
  { id: 'deepseek', title: 'DeepSeek', kind: 'Brain PAPER', capital: 2000, model: 'deepseek-flash' },
  { id: 'qwen', title: 'Qwen', kind: 'Shadow PAPER', capital: 2000, model: 'qwen/qwen3.7-plus' },
  { id: 'minimax', title: 'MiniMax', kind: 'Shadow PAPER', capital: 2000, model: 'minimax/minimax-m3.1-flash' },
]);

const CODES = new Set(['running', 'paused', 'halted', 'stale', 'not_started']);
const RUN_IDS = {
  deepseek: /^brain-deepseek-paper\d{8}$/,
  qwen: /^brain-qwen-paper\d{8}$/,
  minimax: /^brain-minimax-paper\d{8}$/,
};

function finite(value) {
  if (value === null || value === undefined || value === '' || typeof value === 'boolean') return null;
  const valueNumber = Number(value);
  return Number.isFinite(valueNumber) ? valueNumber : null;
}

export function money(value) {
  const number = finite(value);
  return number === null ? '—' :
    number.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' USDT';
}

/** Marked PnL is displayed ONLY when every open position has a valid ticker mark. */
export function markedOpenPnl(trades) {
  if (!trades || !Array.isArray(trades.open_positions)) return null;
  if (trades.open_positions.length === 0) return 0;
  let total = 0;
  for (const position of trades.open_positions) {
    if (!position || position.price_source !== 'ticker') return null;
    const mark = finite(position.price);
    const pnl = finite(position.unrealized_pnl);
    if (mark === null || mark <= 0 || pnl === null) return null;
    total += pnl;
    if (!Number.isFinite(total)) return null;
  }
  return total;
}

export function portfolioFromExisting(overview, status, trades) {
  // The old DeepSeek run is an archive/baseline, not a newly reset trial wallet.
  const entry = overview && Array.isArray(overview.portfolios)
    ? overview.portfolios.find(x => x && x.id === 'brain') : null;
  if (!entry || !CODES.has(entry.state)) return null;
  const marked = markedOpenPnl(trades);
  // Overview and trades are distinct GETs: refuse a mixed-timestamp
  // aggregate if an open/close happened between the two snapshots.
  const comparableOpenCount = Number.isSafeInteger(entry.open_positions)
    ? entry.open_positions : null;
  const openCountMatches = comparableOpenCount === null ||
    (Array.isArray(trades?.open_positions) &&
     trades.open_positions.length === comparableOpenCount);
  return {
    state: entry.state,
    initial_capital: 2000,
    equity: entry.equity ?? null,
    settled_equity: entry.settled_equity ?? null,
    equity_basis: entry.equity_basis ?? null,
    realized_pnl: entry.realized_pnl ?? null,
    unrealized_pnl: trades
      ? (openCountMatches ? marked : null)
      : (entry.unrealized_pnl ?? null),
    day_pnl: entry.day_pnl ?? null,
    total_closed: entry.total_closed ?? null,
    win_rate: entry.win_rate ?? null,
    margin_in_use: entry.margin_in_use ?? null,
    open_count: entry.open_positions ?? null,
    open_positions: Array.isArray(trades?.open_positions) ? trades.open_positions : null,
    closed_trades: Array.isArray(trades?.closed_trades) ? trades.closed_trades : null,
    last_decision: status?.last_decision ?? null,
    updated_ms: overview.generated_at_ms ?? null,
    source: 'v3_existing_brain_paper',
    run_id: null,
    trial_start_ms: null,
    trial_comparable: false,
    // Only the existing Brain's certified single-close bridge may be used.
    manual_close_allowed: entry.manual_close_allowed === true,
    close_pending: trades?.close_pending === true,
    // The historical dashboard does not expose full-journal learning counts.
    decision_count: null, no_trade_count: null, manual_close_count: null,
    verified_outcome_count: null, learning_status: 'NOT_VERIFIED_FOR_OLD_RUN',
  };
}

export function sanitizedTrial(profileId, payload) {
  if (!Object.prototype.hasOwnProperty.call(RUN_IDS, profileId) ||
      !payload || typeof payload !== 'object' || Array.isArray(payload) ||
      payload.portfolio_id !== profileId || payload.mode !== 'paper' ||
      !CODES.has(payload.state) || payload.initial_capital !== 2000 ||
      payload.source !== 'arena_independent_journal_v1' ||
      typeof payload.run_id !== 'string' ||
      !RUN_IDS[profileId].test(payload.run_id)) return null;

  // A missing journal is not a 0-PnL wallet.
  if (payload.state === 'not_started') return null;
  const val = (key) => finite(payload[key]);
  return {
    state: payload.state, initial_capital: 2000,
    equity: val('equity'), settled_equity: val('settled_equity'),
    realized_pnl: val('realized_pnl'), unrealized_pnl: val('unrealized_pnl'),
    day_pnl: val('day_pnl'), margin_in_use: val('margin_in_use'),
    total_closed: val('total_closed'), win_rate: val('win_rate'),
    open_count: val('open_count'),
    open_positions: Array.isArray(payload.open_positions) ? payload.open_positions : null,
    closed_trades: Array.isArray(payload.closed_trades) ? payload.closed_trades : null,
    last_decision: payload.last_decision ?? null,
    updated_ms: Number.isInteger(payload.updated_ms) ? payload.updated_ms : null,
    source: 'arena_independent_journal_v1', run_id: payload.run_id,
    equity_basis: payload.equity_basis ?? null,
    trial_start_ms: Number.isSafeInteger(payload.trial_start_ms) &&
      payload.trial_start_ms > 0 ? payload.trial_start_ms : null,
    trial_comparable: payload.trial_comparable === true,
    // A trial wallet cannot be closed via /api/v3/brain/close.
    // Dedicated provider-scoped commands must be audited first.
    manual_close_allowed: false,
    close_pending: false,
    decision_count: val('decision_count'),
    no_trade_count: val('no_trade_count'),
    manual_close_count: val('manual_close_count'),
    verified_outcome_count: val('verified_outcome_count'),
    learning_status: payload.learning_status === 'JOURNAL_EVIDENCE_ONLY_NOT_MODEL_TRAINING'
      ? payload.learning_status : 'NOT_VERIFIED',
  };
}

export function sanitizedShadow(profileId, payload) {
  if (profileId !== 'qwen' && profileId !== 'minimax') return null;
  return sanitizedTrial(profileId, payload);
}

export function trialTotalPnl(portfolios) {
  // Historical DeepSeek PnL cannot be added to fresh Qwen/MiniMax trials.
  const items = ARENA_PROFILES.map(p => portfolios[p.id]);
  if (!items.every(p => p && p.trial_comparable === true &&
       Number.isSafeInteger(p.trial_start_ms) && p.trial_start_ms > 0 &&
       finite(p.realized_pnl) !== null)) return null;
  const sharedStart = items[0].trial_start_ms;
  if (!items.every(p => p.trial_start_ms === sharedStart)) return null;
  return items.reduce((total, item) => total + finite(item.realized_pnl), 0);
}
