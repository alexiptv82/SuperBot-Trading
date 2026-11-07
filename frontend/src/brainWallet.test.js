import { PAPER_PORTFOLIOS, finiteNumber, brainClosedTrades, brainOpenTrades, brainWalletSummary } from './brainWallet';

test('three independent wallets share one UI selector order', () => {
  expect(PAPER_PORTFOLIOS.map(p => p.id)).toEqual(['hawk','bull','brain']);
  expect(new Set(PAPER_PORTFOLIOS.map(p => p.id)).size).toBe(3);
});

test('Brain open position uses verified mark and does not fake missing P&L, cash or equity', () => {
  const p = { id:'brain',state:'paused',equity:null,settled_equity:'2003.5',start_equity:'2000',
    realized_pnl:'3.5',day_pnl:'3.5',total_closed:1,margin_in_use:'350',win_rate:'100',equity_basis:'open_unmarked' };
  const trades = {open_positions:[{position_id:'b1',symbol:'BTCUSDT',side:1,
      entry:'100',price:null,unrealized_pnl:null,roi_pct:null,
      margin:'350',leverage:25,stop:'94',opened_at_ms:123456}],win_count:1,loss_count:0};
  const w = brainWalletSummary(p,{last_decision:{kind:'NO_TRADE'}},trades);
  expect(w.cash).toBeNull();
  expect(w.equity).toBeNull();
  expect(w.settled_equity).toBe(2003.5);
  expect(w.unrealized_pnl).toBeNull();
  expect(w.positions[0]).toMatchObject({position_id:'b1',entry_price:100,live_price:null,pnl:null,pnl_pct:null});
  expect(w.win_count).toBe(1);
  expect(w.loss_count).toBe(0);
  expect(w.last_decision.kind).toBe('NO_TRADE');
});

test('Brain closed trades preserve independent ID, exact win/loss sign and manual learning', () => {
  const c = brainClosedTrades([{
    position_id:'b2',symbol:'ETHUSDT',side:-1,entry:'100',exit:'99',margin:'200',
    leverage:30,realized_pnl:'-12.30',fees:'1.25',exit_reason:'manual',hold_ms:60000,
    closed_at_ms:1234567,manual_learning:'loss_reduction_example'
  }])[0];
  expect(c).toMatchObject({position_id:'b2',side:-1,pnl:-12.3,fees:1.25,close_reason:'manual',
    manual_learning:'loss_reduction_example',entry_price:100,exit_price:99,open_ms:1174567});
});

test('invalid or absent values never silently turn into invented prices or winnings', () => {
  expect(finiteNumber(null)).toBeNull();
  expect(finiteNumber(undefined)).toBeNull();
  expect(finiteNumber('')).toBeNull();
  expect(finiteNumber('Infinity')).toBeNull();
  expect(finiteNumber('NaN')).toBeNull();
  expect(brainOpenTrades([{symbol:'SOLUSDT',side:-1,price:'not-a-price',unrealized_pnl:'bad'}])[0])
    .toMatchObject({live_price:null,pnl:null});
  expect(brainWalletSummary(null,{},{})).toBeNull();
});
