import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { OverviewContent } from './Overview';

const NOW = 1794000000000;
const base = {
  overview: { generated_at_ms: NOW, portfolios: [
    { id: 'falco', kind:'classic', state:'running', open_positions:1, realized_pnl:'10.25',
      margin_in_use:'100', unrealized_pnl:'5.50', equity:'1015.75', day_pnl:'4.00',
      total_closed:1, win_rate:'100', last_event_ms: NOW-15000, can_close_position:false,
      positions:[{symbol:'BTCUSDT',side:-1,leverage:25,entry:'100',price:'99',price_source:'bot',
        margin:'100',stop:'102',take_profit:'95',liquidation:'105',
        unrealized_pnl:'5.5',roi_pct:'5.5',trade_type:'scalp'}],
      closed_trades:[{symbol:'ETHUSDT',side:1,leverage:20,entry:'100',exit:'102',
        margin:'150',realized_pnl:'4.50',close_reason:'obiettivo',closed_at_ms:NOW-20000}] },
    { id:'toro',kind:'classic',state:'paused',open_positions:0,realized_pnl:'0',
      margin_in_use:'0',positions:[],closed_trades:[],last_event_ms:NOW-10000 },
    { id:'brain',kind:'brain',state:'running',open_positions:1,realized_pnl:'7.10',
      margin_in_use:'350',last_event_ms:NOW-2000 },
  ] },
  status: { state:'running',regime:'TREND_UP',last_decision:null,spend:null },
  scoreboard: { regimes:[] },
  trades: { open_positions:[{position_id:'id-1',symbol:'SOLUSDT',side:1,leverage:30,
       entry:'200',price:'201.5',stop:'195',margin:'350',quantity:'3',
       opened_at_ms:NOW-60000,unrealized_pnl:'4.5',roi_pct:'1.2857',strategy_id:'S07'}],
    closed_trades:[{position_id:'id-2',symbol:'ADAUSDT',side:-1,leverage:40,margin:'200',
       entry:'100',exit:'98',realized_pnl:'7.10',net_bp:'27.1',fees:'1.2',
       closed_at_ms:NOW-5000,hold_ms:60000,exit_reason:'take_profit',regime:'TREND_DOWN'}] },
};
const render = data => renderToStaticMarkup(<OverviewContent {...data} nowMs={NOW} regime="" onRegime={() => {}} />);

test('three portfolios are immediately visible with separate capital and results', () => {
  const h=render(base);
  for(const name of ['Falco','Toro','Brain V3','Posizioni aperte','Equity','Win rate','Profitto di oggi'])
    expect(h).toContain(name);
  expect(h).toContain('1015.75 USDT');
  expect(h).toContain('7.10 USDT');
});

test('classic open trade remains visible when manual close is not available', () => {
  const h=render(base);
  expect(h).toContain('BTCUSDT');
  expect(h).toContain('SHORT');
  expect(h).toContain('25×');
  expect(h).toContain('Margine 100 USDT');
  expect(h).toContain('Prezzo attuale 99');
  expect(h).toContain('Chiusura manuale non ancora disponibile');
  expect(h).not.toContain('Chiudi BTCUSDT');
  expect(h).toContain('Apri la dashboard classica completa');
});

test('both classic and brain closed trades display financial details', () => {
  const h=render(base);
  expect(h).toContain('ETHUSDT');
  expect(h).toContain('4.50 USDT');
  expect(h).toContain('ADAUSDT');
  expect(h).toContain('7.10 USDT');
  expect(h).toContain('40×');
  expect(h).toContain('Commissioni 1.2 USDT');
});

test('Brain open trade shows margin, leverage, current price, stop and PnL', () => {
  const h=render(base);
  expect(h).toContain('SOLUSDT');
  expect(h).toContain('30×');
  expect(h).toContain('Prezzo attuale 201.5');
  expect(h).toContain('Margine 350 USDT');
  expect(h).toContain('Stop 195');
  expect(h).toContain('P&L non realizzato: 4.5 USDT');
});

test('unknown price and PnL must not appear as fabricated zero', () => {
  const clone=JSON.parse(JSON.stringify(base));
  clone.overview.portfolios[0].positions[0].price=null;
  clone.overview.portfolios[0].positions[0].unrealized_pnl=null;
  clone.trades.open_positions[0].price=null;
  clone.trades.open_positions[0].unrealized_pnl=null;
  const h=render(clone);
  expect(h).toContain('Prezzo aggiornato non disponibile');
  expect(h).not.toContain('P&L non realizzato: 0 USDT');
});
