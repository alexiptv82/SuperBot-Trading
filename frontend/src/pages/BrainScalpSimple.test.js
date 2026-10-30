import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {MemoryRouter} from 'react-router-dom';
import BrainScalpDashboard from './BrainScalpDashboard';
import {brainAPI} from '../api';

jest.mock('../api',()=>({brainAPI:{getScalpStatus:jest.fn()}}));
const NOW=1800000000000;
const sample=(stale=false,mark=102)=>({data:{
  layout:'single',source:'snapshot',status:stale?'stale':'ok',
  snapshot_ts_ms:NOW,snapshot_age_ms:stale?70000:0,snapshot_stale:stale,
  profiles:{brain:{
    status:'ok',online:!stale,heartbeat_ms:NOW,initial_cash:1000,equity:1050,
    net_pnl_vs_initial:50,cash:850,margin:150,margin_limit:900,max_slots:10,
    metrics:{trades_today:2,trades_closed:1,pnl_realized_usd:30,fee_paid_usd:3},
    positions:[{symbol:'BTC',side:'SHORT',entry:100,mark_price:mark,
      price_status:mark===null?'unavailable':'fresh',net_close_estimate:mark===null?null:12,
      pnl_pct_margin:mark===null?null:8,margin:150,leverage:20,
      notional:3000,stop:104,target:96,age_minutes:14}],
    pending:[],trades:[{symbol:'ETH',side:'LONG',entry:120,exit:124,
      leverage:10,net:30,position_id:'abc',reason:'take profit',close_ms:NOW}],
    closed_total:1,trades_shown:1,recent_closed_wins:1,trades_summary_only:false
  }}
}});
let host,root;
const mount=async()=>await act(async()=>root.render(<MemoryRouter><BrainScalpDashboard/></MemoryRouter>));
beforeEach(()=>{
  jest.useFakeTimers('modern');jest.setSystemTime(NOW);
  global.IS_REACT_ACT_ENVIRONMENT=true;
  host=document.createElement('div');root=createRoot(host);
  brainAPI.getScalpStatus.mockReset();
});
afterEach(async()=>{
  await act(async()=>root.unmount());
  expect(jest.getTimerCount()).toBe(0);
  jest.useRealTimers();
});

test('mobile-first single wallet shows meaningful price margin leverage and net',async()=>{
  brainAPI.getScalpStatus.mockResolvedValue(sample());
  await mount();
  expect(host.querySelectorAll('section')).toHaveLength(1);
  expect(host.textContent).toContain('Conto unico');
  expect(host.textContent).toContain('Prezzo entrata');
  expect(host.textContent).toContain('Prezzo attuale');
  expect(host.textContent).toContain('Leva');
  expect(host.textContent).toContain('20,0×');
  expect(host.textContent).toContain('+$12.00');
  expect(host.textContent).toContain('8,00% margine');
  expect(host.textContent).toContain('SHORT');
});

test('only real persisted recent closures appear on the history tab',async()=>{
  brainAPI.getScalpStatus.mockResolvedValue(sample());
  await mount();
  const history=[...host.querySelectorAll('[role=tab]')].find(b=>b.textContent==='Storico');
  await act(async()=>history.click());
  expect(host.textContent).toContain('ETHUSDT');
  expect(host.textContent).toContain('take profit');
  expect(host.textContent).toContain('+$30.00');
  expect(host.textContent).not.toContain('BTCUSDT');
  const stats=[...host.querySelectorAll('[role=tab]')].find(b=>b.textContent==='Statistiche');
  await act(async()=>stats.click());
  expect(host.textContent).toContain('Vittorie nelle ultime chiusure');
  expect(host.textContent).toContain('100,0%');
});

test('stale data can never masquerade as current position P&L',async()=>{
  brainAPI.getScalpStatus.mockResolvedValue(sample(true));
  await mount();
  expect(host.textContent).toContain('Dati non aggiornati');
  expect(host.textContent).toContain('valori mostrati sono storici');
  expect(host.textContent).toContain('P&L non disponibile');
  expect(host.textContent).not.toContain('+$12.00');
});

test('no invented live mark if source supplies null',async()=>{
  brainAPI.getScalpStatus.mockResolvedValue(sample(false,null));
  await mount();
  expect(host.textContent).toContain('P&L non disponibile');
  expect(host.textContent).toContain('Quotazione non verificata');
  expect(host.textContent).not.toContain('+$12.00');
});
