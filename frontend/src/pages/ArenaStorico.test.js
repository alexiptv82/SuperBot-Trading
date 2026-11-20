import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { ArenaStoricoContent } from './ArenaStorico';

const wallet = (id, extra = {}) => ({ portfolio_id: id, mode: 'paper', state: 'running', initial_capital: 2000,
  source: 'arena_independent_journal_v1', run_id: `brain-${id}-paper20261118`, equity: '2010.50', realized_pnl: '10.50',
  total_closed: 4, win_rate: 50, open_count: 1, decision_count: 30, no_trade_count: 20, manual_close_count: 1,
  learning_status: 'JOURNAL_EVIDENCE_ONLY_NOT_MODEL_TRAINING', ...extra });

test('read-only history of the three Arena wallets', () => {
  const h = renderToStaticMarkup(<ArenaStoricoContent data={{ portfolios: {
    deepseek: wallet('deepseek'), qwen: wallet('qwen'), minimax: { portfolio_id: 'minimax', state: 'not_started' } } }} />);
  for (const t of ['DeepSeek', 'Qwen', 'MiniMax', '2.010,50 USDT', 'nessun modello addestrato', 'Dati non disponibili'])
    expect(h).toContain(t);
  expect(h).not.toContain('<button');
});

test('unverified payloads never show numbers', () => {
  const h = renderToStaticMarkup(<ArenaStoricoContent data={{ portfolios: { deepseek: wallet('deepseek', { mode: 'live' }) } }} />);
  expect(h).not.toContain('USDT');
});
