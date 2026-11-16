import { ARENA_PROFILES, money, portfolioFromExisting, sanitizedShadow } from './brainArenaModel';

test('three independent initial PAPER capital references', () => {
  expect(ARENA_PROFILES.map(x => x.id)).toEqual(['deepseek','qwen','minimax']);
  expect(ARENA_PROFILES.every(x => x.capital === 2000)).toBe(true);
});

test('existing Brain is the only source of DeepSeek PAPER values', () => {
  const data = portfolioFromExisting(
    { generated_at_ms: 9000, portfolios: [{id:'falco',state:'running',realized_pnl:'99999'},
      {id:'brain',state:'running',realized_pnl:'12.45',equity:'2012.45',total_closed:1}] },
    {last_decision:{symbol:'BTCUSDT',status:'APPROVED'}},
    {open_positions:[],closed_trades:[{symbol:'LINKUSDT',realized_pnl:'12.45'}]},
  );
  expect(data.realized_pnl).toBe('12.45');
  expect(data.source).toBe('v3_existing_brain_paper');
  expect(data.open_positions).toEqual([]);
  expect(data.closed_trades).toHaveLength(1);
  expect(data.updated_ms).toBe(9000);
});

test('unknown states and numbers remain unknown, not zero', () => {
  expect(portfolioFromExisting({portfolios:[]},null,null)).toBeNull();
  expect(money(null)).toBe('—');
  expect(money('NaN')).toBe('—');
  expect(sanitizedShadow('qwen',null)).toBeNull();
});

test('shadow data requires independently verified run ID and source, never DeepSeek run', () => {
  const valid = {
    portfolio_id:'qwen', mode:'paper', state:'running',
    initial_capital:2000, source:'arena_independent_journal_v1',
    run_id:'brain-qwen-paper20261116', realized_pnl:'22.50',
    open_positions:[{symbol:'BTCUSDT',side:-1}],closed_trades:[],
  };
  expect(sanitizedShadow('qwen',valid).realized_pnl).toBe('22.50');
  expect(sanitizedShadow('minimax',valid)).toBeNull();
  expect(sanitizedShadow('qwen',{...valid,run_id:'brain-v3-paper20261111'})).toBeNull();
  expect(sanitizedShadow('qwen',{...valid,source:'v3_existing_brain_paper'})).toBeNull();
  expect(sanitizedShadow('qwen',{...valid,mode:'live'})).toBeNull();
  expect(sanitizedShadow('qwen',{...valid,initial_capital:1000})).toBeNull();
});

test('future shadow with partial data does not fabricate PnL or positions', () => {
  const partial = sanitizedShadow('minimax',{
    portfolio_id:'minimax',mode:'paper',state:'paused',
    initial_capital:2000, source:'arena_independent_journal_v1',
    run_id:'brain-minimax-paper20261116',
  });
  expect(partial).not.toBeNull();
  expect(partial.realized_pnl).toBeNull();
  expect(partial.equity).toBeNull();
  expect(partial.open_positions).toBeNull();
  expect(partial.closed_trades).toBeNull();
  expect(money(partial.equity)).toBe('—');
});
