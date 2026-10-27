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
