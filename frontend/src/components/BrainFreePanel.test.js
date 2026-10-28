import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import BrainFreePanel from './BrainFreePanel';
test('independent 2000 account shows cost and never a fixed 1000 baseline', () => {
  const html = renderToStaticMarkup(<BrainFreePanel data={{online:true,equity:2020,cash:1500,margin:500,pnl:20,positions:[],spend:{today_usd:1.5,total_usd:5,uncertain_requests:1},trades:[]}} />);
  expect(html).toContain('2.000$'); expect(html).toContain('$2020.00');
  expect(html).toContain('$1.5000'); expect(html).toContain('Nessun tetto software');
});
test('explicit thesis is escaped; margin and leverage are visible', () => {
  const data={online:true,spend:{},positions:[{symbol:'BTC',side:'LONG',margin:200,leverage:15,notional:3000,qty:1,age_minutes:2,stop:95,liquidation_estimate:90,reason:'<script>unsafe</script>',invalidation:'support fails'}]};
  const html=renderToStaticMarkup(<BrainFreePanel data={data} />);
  expect(html).toContain('$200.00');expect(html).toContain('15.00');
  expect(html).toContain('&lt;script&gt;unsafe&lt;/script&gt;');expect(html).not.toContain('<script>');
});
test('stale or missing equity never becomes a made-up zero', () => {
  const html=renderToStaticMarkup(<BrainFreePanel data={{online:false,positions:[]}} />);
  expect(html).toContain('Non disponibile');expect(html).not.toContain('$0.00');
});

test('Brain V2 shows new five-slot capacity, margin ceiling and separate run PnL', () => {
  const html=renderToStaticMarkup(<BrainFreePanel data={{
    available:true,online:true,equity:1910,cash:1910,margin:0,
    pnl:20,pnl_since_original_start:-90,run_start_equity:1890,
    margin_limit:1750,max_slots:5,paused:true,
    positions:[],spend:{today_usd:.1,total_usd:3,current_run_usd:.2}
  }} />);
  expect(html).toContain('5 slot');
  expect(html).toContain('$1750.00');
  expect(html).toContain('P&amp;L run attuale');
  expect(html).toContain('P&amp;L cumulato dalla V1');
  expect(html).toContain('Spesa AI run attuale');
  expect(html).toContain('Nuove esposizioni in pausa');
});
