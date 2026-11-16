/** AI Arena read-only display contract. Never infer results for absent providers. */
export const ARENA_PROFILES = Object.freeze([
  { id: 'deepseek', title: 'DeepSeek', kind: 'Brain PAPER', capital: 2000, model: 'deepseek-flash' },
  { id: 'qwen', title: 'Qwen', kind: 'Shadow PAPER', capital: 2000, model: 'qwen3.7-plus' },
  { id: 'minimax', title: 'MiniMax', kind: 'Shadow PAPER', capital: 2000, model: 'Da verificare con API' },
]);

const CODES = new Set(['running', 'paused', 'halted', 'stale', 'not_started']);

export function money(value) {
  if (value === null || value === undefined || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' USDT' : '—';
}

export function portfolioFromExisting(overview, status, trades) {
  // Real PAPER DeepSeek from existing authenticated v3 read-only endpoints.
  const entry = (overview && Array.isArray(overview.portfolios)
    ? overview.portfolios.find(x => x?.id === 'brain') : null);
  if (!entry || !CODES.has(entry.state)) return null;
  const open = Array.isArray(trades?.open_positions) ? trades.open_positions : null;
  const closed = Array.isArray(trades?.closed_trades) ? trades.closed_trades : null;
  return {
    state: entry.state,
    initial_capital: 2000,
    equity: entry.equity ?? null,
    settled_equity: entry.settled_equity ?? null,
    equity_basis: entry.equity_basis ?? null,
    realized_pnl: entry.realized_pnl ?? null,
    unrealized_pnl: entry.unrealized_pnl ?? null,
    day_pnl: entry.day_pnl ?? null,
    total_closed: entry.total_closed ?? null,
    win_rate: entry.win_rate ?? null,
    margin_in_use: entry.margin_in_use ?? null,
    open_count: entry.open_positions ?? null,
    open_positions: open,
    closed_trades: closed,
    last_decision: status?.last_decision ?? null,
    updated_ms: overview.generated_at_ms ?? null,
    source: 'v3_existing_brain_paper',
  };
}

export function sanitizedShadow(profileId, payload) {
  if (!['qwen', 'minimax'].includes(profileId) || !payload || typeof payload !== 'object'
      || payload.portfolio_id !== profileId || payload.mode !== 'paper'
      || !CODES.has(payload.state) || payload.initial_capital !== 2000
      || payload.source !== 'arena_independent_journal_v1'
      || typeof payload.run_id !== 'string' || payload.run_id.length < 4) return null;
  // No fallback from DeepSeek's record: absent or malformed shadow data stays unknown.
  const value = key => {
    const v = payload[key];
    return v === null || v === undefined || !Number.isFinite(Number(v)) ? null : v;
  };
  return {
    state: payload.state, initial_capital: 2000,
    equity: value('equity'), settled_equity: value('settled_equity'),
    realized_pnl: value('realized_pnl'), unrealized_pnl: value('unrealized_pnl'),
    day_pnl: value('day_pnl'), margin_in_use: value('margin_in_use'),
    total_closed: value('total_closed'), win_rate: value('win_rate'),
    open_count: value('open_count'),
    open_positions: Array.isArray(payload.open_positions) ? payload.open_positions : null,
    closed_trades: Array.isArray(payload.closed_trades) ? payload.closed_trades : null,
    last_decision: payload.last_decision ?? null,
    updated_ms: Number.isInteger(payload.updated_ms) ? payload.updated_ms : null,
    source: 'arena_independent_journal_v1', run_id: payload.run_id,
    equity_basis: payload.equity_basis ?? null,
  };
}
