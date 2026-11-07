import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { PortfolioSection } from './Dashboard';
import { ClassicCloseControls } from '../components/OverviewCloseControls';

const now=Date.now();
const one={
  symbol:'BTC',side:-1,entry:100,price:98,price_source:'bot',
  leverage:20,margin:100,sl:110,tp:95,pnl:35,pnl_pct:35,open_ms:now-10000
};
const stopped={
  available:true, portfolio:'hawk', bot_online:false, bot_mode:'draining', paused:true,
  can_close_position:true, close_worker_mode:'exit_only', positions:[one],
  open_positions:1, total_closed:9, start_equity:1000, equity:1035,
  cash:950, margin_used:100, day_pnl:20, unrealized_pnl:35,
  pnl_total:35,pnl_total_pct:3.5,
};

function render(allowSingle){
  const host=document.createElement('div');
  host.innerHTML=renderToStaticMarkup(<PortfolioSection status={stopped} portfolio="hawk"
    readOnly singleCloseAllowed={allowSingle} busy={null} actionMsg={null}
    onCloseAll={()=>{}} onChartOpen={()=>{}} onPause={()=>{}} onResume={()=>{}}
    onClosePosition={()=>async()=>({ok:true})}/>);
  return host;
}

test('exit-only allows only the individually confirmed close when server explicitly enables it',()=>{
  const root=render(true);
  expect(root.textContent).toContain('Solo chiusure PAPER');
  expect(root.textContent).toContain('Chiudi ora');
  const all=Array.from(root.querySelectorAll('button')).find(b=>b.textContent.includes('Chiudi subito tutte'));
  expect(all.disabled).toBe(true);
  const start=Array.from(root.querySelectorAll('button')).find(b=>b.textContent.includes('Riprendi'));
  expect(start.disabled).toBe(true);
  expect(root.textContent).toContain('nessuna nuova apertura');
});

test('without server permission even healthy exit-only reports no clickable individual close',()=>{
  const root=render(false);
  expect(root.textContent).not.toContain('Chiudi ora');
  expect(root.textContent).toContain('chiusure manuali temporaneamente bloccati');
});

test('unified Overview close controls can show individual trades while hiding close-all',()=>{
  const html=renderToStaticMarkup(<ClassicCloseControls portfolio="falco" positions={[{
    symbol:'BTC',side:-1,entry:100,price:98,margin:100,leverage:20,
    unrealized_pnl:35,price_source:'bot'
  }]} canClose allowCloseAll={false}/>);
  expect(html).toContain('Chiudi BTC');
  expect(html).not.toContain('Chiudi tutte');
});
