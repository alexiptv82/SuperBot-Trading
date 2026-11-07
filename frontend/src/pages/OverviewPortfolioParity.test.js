/** The three portfolios use one visual grammar; Brain intelligence remains extra, not a different wallet UI. */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { OverviewContent } from './Overview';

const now = 1794050000000;
const position = {
  symbol:'BTCUSDT', side:1, leverage:25, entry:'100', price:'102', price_source:'live',
  margin:'200', quantity:'50', stop:'97', take_profit:'105', liquidation:'90',
  unrealized_pnl:'8', roi_pct:'4', trade_type:'scalp'
};
const closed = {
  symbol:'ETHUSDT', side:-1, leverage:30, entry:'100', exit:'98', margin:'250',
  realized_pnl:'11', closed_at_ms: now-12000, close_reason:'chiusura manuale',
  manual_learning:'profit_protection_example'
};
const fixture = {
  overview: { generated_at_ms: now, portfolios: [
    {id:'falco',kind:'classic',state:'running',open_positions:1,can_close_position:true,positions:[position],
      closed_trades:[closed],realized_pnl:'11',unrealized_pnl:'8',margin_in_use:'200',
      equity:'1019',day_pnl:'11',total_closed:1,win_rate:'100'},
    {id:'toro',kind:'classic',state:'paused',open_positions:1,can_close_position:true,positions:[{...position,symbol:'SOLUSDT'}],
      closed_trades:[{...closed,symbol:'ADAUSDT'}],realized_pnl:'11',unrealized_pnl:'8',margin_in_use:'200',
      equity:'1019',day_pnl:'11',total_closed:1,win_rate:'100'},
    {id:'brain',kind:'brain',state:'running',open_positions:1,realized_pnl:'11',
      margin_in_use:'200',total_closed:1,win_rate:'100'}
  ]},
  status:{state:'running',regime:'TREND_UP',spend:null},
  scoreboard:{regimes:[]},
  trades:{open_positions:[{...position,position_id:'brain-1',symbol:'XRPUSDT',strategy_id:'S1'}],
    closed_trades:[{...closed,position_id:'brain-2',symbol:'LINKUSDT',exit_reason:'manual',
      fees:'1.1',hold_ms:45000,net_bp:'45',regime:'TREND_UP'}],close_pending:false}
};

const render = data => {
  const parent = document.createElement('div');
  parent.innerHTML = renderToStaticMarkup(<OverviewContent {...data} nowMs={now} regime=""
    onRegime={() => {}} />);
  return parent;
};

test('Falco, Toro and Brain have the same visible wallet metrics, positions and trade history', () => {
  const root = render(fixture);
  const cards = ['falco','toro','brain'].map(id => root.querySelector(`[data-testid="portfolio-${id}"]`));
  cards.forEach(card => {
    expect(card).not.toBeNull();
    for (const label of ['Posizioni aperte','P&L realizzato','Margine in uso',
      'P&L aperto','Equity','Profitto di oggi','Trade chiusi','Win rate',
      'Trade aperti','Ultimi']) {
      expect(card.textContent).toContain(label);
    }
    expect(card.querySelector('button').textContent).toContain('Chiudi tutte');
    expect(card.querySelectorAll('details').length).toBe(1);
    expect(card.textContent).toContain('LONG');
    expect(card.textContent).toContain('25×');
    expect(card.textContent).toContain('Margine 200 USDT');
    expect(card.textContent).toContain('Stop 97');
    expect(card.textContent).toContain('ROI 4%');
    expect(card.textContent).toContain('Profitto protetto manualmente');
  });
  expect(cards[0].querySelector('[data-testid="portfolio-trade-classic"]')).not.toBeNull();
  expect(cards[1].querySelector('[data-testid="portfolio-trade-classic"]')).not.toBeNull();
  expect(cards[2].querySelector('[data-testid="portfolio-trade-brain"]')).not.toBeNull();
});

test('Brain AI insights are extra panels outside its wallet, not a separate trade list', () => {
  const root = render(fixture);
  const brainCard = root.querySelector('[data-testid="portfolio-brain"]');
  expect(brainCard.textContent).not.toContain('Risultati per strategia');
  expect(root.querySelector('section[aria-label="Stato Brain"]')).not.toBeNull();
  expect(root.querySelector('section[aria-label="Apprendimento Brain"]')).not.toBeNull();
  expect(root.querySelectorAll('[data-testid="portfolio-brain"]')).toHaveLength(1);
});

test('Brain equity and daily PnL are unknown rather than a fabricated wallet value', () => {
  const root = render(fixture);
  const brainCard = root.querySelector('[data-testid="portfolio-brain"]');
  expect(brainCard.textContent).toContain('Equity—');
  expect(brainCard.textContent).toContain('Profitto di oggi—');
  expect(brainCard.textContent).not.toContain('Equity0 USDT');
});

test('Brain displays settled capital and UTC realized profit without inventing open-position equity', () => {
  const updated = JSON.parse(JSON.stringify(fixture));
  Object.assign(updated.overview.portfolios[2], {
    start_equity:'2000', settled_equity:'2005.25', equity:null,
    equity_basis:'open_unmarked', day_pnl:'5.25', pnl_day_timezone:'UTC'
  });
  const root = render(updated);
  const brain = root.querySelector('[data-testid="portfolio-brain"]');
  expect(brain.textContent).toContain('Profitto di oggi (realizzato, UTC)');
  expect(brain.textContent).toContain('5.25');
  expect(brain.textContent).toContain('2005.25 USDT');
  expect(brain.textContent).toContain('escluso P&L aperto');
  expect(brain.textContent).toContain('Non calcolabile senza prezzi verificati');
});

test('Classics monitoring is read-only and never labelled active AI decision input', () => {
  const updated = JSON.parse(JSON.stringify(fixture));
  Object.assign(updated.overview.portfolios[2], {
    peer_observations_mode:'display_only_not_ai_input',
    peer_observations: [
      {portfolio_id:'falco',state:'paused',open_positions:2,day_pnl:'12.50'},
      {portfolio_id:'toro',state:'stale',open_positions:1,day_pnl:null}
    ]
  });
  const root = render(updated);
  const panel = root.querySelector('section[aria-label="Osservazioni Falco e Toro"]');
  expect(panel).not.toBeNull();
  expect(panel.textContent).toContain('Confronto informativo in sola lettura');
  expect(panel.textContent).toContain('non sono ancora collegati alle decisioni');
  expect(panel.textContent).toContain('Falco');
  expect(panel.textContent).toContain('Toro');
});
