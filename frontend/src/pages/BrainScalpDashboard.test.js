import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import {MemoryRouter} from 'react-router-dom';
import BrainScalpDashboard from './BrainScalpDashboard';
import {brainAPI} from '../api';

jest.mock('../api',()=>({brainAPI:{getScalpStatus:jest.fn()}}));

const NOW=1800000000000;
const response=(extra={})=>({data:{
  source:'snapshot',status:'ok',snapshot_ts_ms:NOW,snapshot_age_ms:0,
  snapshot_stale:false,profiles:Object.fromEntries(['hawk','bull'].map(name=>[name,{
    status:'ok',online:true,heartbeat_ms:NOW,equity:name==='hawk'?1010:990,
    cash:800,margin:200,margin_limit:950,max_slots:name==='hawk'?10:3,
    positions:[],pending:[],trades_summary_only:true,
  }])),...extra,
}});
let host,root,originalFetch;
const mount=async()=>{await act(async()=>{
  root.render(<MemoryRouter><BrainScalpDashboard/></MemoryRouter>);
});};
const advance=async ms=>{await act(async()=>{jest.advanceTimersByTime(ms);});};
const online=()=>host.textContent.includes('🟢 Online');

beforeEach(()=>{
  jest.useFakeTimers('modern');jest.setSystemTime(NOW);
  global.IS_REACT_ACT_ENVIRONMENT=true;
  host=document.createElement('div');root=createRoot(host);
  brainAPI.getScalpStatus.mockReset();
  originalFetch=global.fetch;
  global.fetch=jest.fn().mockResolvedValue({ok:true,json:async()=>({status:'available',groups:[]})});
});
afterEach(async()=>{
  await act(async()=>{root.unmount();});
  expect(jest.getTimerCount()).toBe(0);
  jest.useRealTimers();
  global.fetch=originalFetch;
});

test('network failure removes online immediately, keeps labelled history and recovers',async()=>{
  brainAPI.getScalpStatus.mockResolvedValue(response())
    .mockResolvedValueOnce(response()).mockRejectedValueOnce(new Error('offline'));
  await mount();expect(online()).toBe(true);
  await advance(15000);
  expect(online()).toBe(false);
  expect(host.textContent).toContain('Connessione non disponibile');
  expect(host.textContent).toContain('valori mostrati sono storici');
  expect(host.textContent).toContain('$1010.00');
  expect(host.textContent).toContain('(non aggiornato)');
  await advance(15000);
  expect(online()).toBe(true);
  expect(host.textContent).not.toContain('Connessione non disponibile');
  expect(host.textContent).not.toContain('valori mostrati sono storici');
});

test('last response expires while the next GET hangs, with no overlapping polls',async()=>{
  brainAPI.getScalpStatus.mockResolvedValueOnce(response())
    .mockReturnValue(new Promise(()=>{}));
  await mount();await advance(15000);
  expect(brainAPI.getScalpStatus).toHaveBeenCalledTimes(2);
  await advance(45000);
  expect(online()).toBe(false);
  expect(host.textContent).toContain('valori mostrati sono storici');
  expect(host.textContent).toContain('$1010.00');
  expect(brainAPI.getScalpStatus).toHaveBeenCalledTimes(2);
});

test('server snapshot age continues locally even with a skewed phone clock',async()=>{
  jest.setSystemTime(NOW+86400000);
  brainAPI.getScalpStatus.mockResolvedValue(response({snapshot_age_ms:59000}));
  await mount();expect(online()).toBe(true);
  await advance(2000);
  expect(online()).toBe(false);
  expect(host.textContent).toContain('(non aggiornato)');
});

test('wallet heartbeat can expire before the response itself',async()=>{
  const r=response({source:'sqlite_legacy'});
  r.data.profiles.hawk.heartbeat_ms=NOW-59000;
  r.data.profiles.bull.heartbeat_ms=NOW-59000;
  brainAPI.getScalpStatus.mockResolvedValue(r);
  await mount();expect(online()).toBe(true);
  await advance(1000);expect(online()).toBe(false);
  expect(host.textContent).toContain('valori mostrati sono storici');
});

test('server stale snapshots remain historical on receipt',async()=>{
  brainAPI.getScalpStatus.mockResolvedValue(response({
    snapshot_stale:true,snapshot_age_ms:90000,status:'stale',
  }));
  await mount();
  expect(online()).toBe(false);
  expect(host.textContent).toContain('$1010.00');
  expect(host.textContent).toContain('(non aggiornato)');
});

test('unmount aborts a pending request and clears polling and age timers',async()=>{
  let resolve;
  brainAPI.getScalpStatus.mockReturnValue(new Promise(done=>{resolve=done;}));
  await mount();
  const signal=brainAPI.getScalpStatus.mock.calls[0][0];
  await advance(90000);
  expect(brainAPI.getScalpStatus).toHaveBeenCalledTimes(1);
  await act(async()=>{root.unmount();});
  expect(signal.aborted).toBe(true);
  expect(jest.getTimerCount()).toBe(0);
  await act(async()=>{resolve(response());});
  // Supply a fresh empty root so the shared cleanup can run normally.
  root=createRoot(host);
});

const singleResponse=()=>{
  const r=response({layout:'single'});
  r.data.profiles={brain:{...r.data.profiles.hawk,initial_cash:2000,equity:2015,
    net_pnl_vs_initial:15,max_slots:7,margin_limit:1600}};
  return r;
};

test('single account renders once with its actual mandate and no dual wallets',async()=>{
  brainAPI.getScalpStatus.mockResolvedValue(singleResponse());await mount();
  expect(host.querySelectorAll('section[aria-label="Portafoglio Brain"]')).toHaveLength(1);
  expect(host.textContent).toContain('Conto unico');
  expect(host.textContent).toContain('$2000.00');
  expect(host.textContent).toContain('7 slot');
  expect(host.textContent).not.toContain('Brain Hawk');
  expect(host.textContent).not.toContain('Brain Bull');
  expect(online()).toBe(true);
});

test('single account network failure labels history and recovers without duplication',async()=>{
  brainAPI.getScalpStatus.mockResolvedValue(singleResponse())
    .mockResolvedValueOnce(singleResponse()).mockRejectedValueOnce(new Error('offline'));
  await mount();await advance(15000);
  expect(online()).toBe(false);expect(host.textContent).toContain('$2015.00');
  expect(host.textContent).toContain('valori mostrati sono storici');
  await advance(15000);expect(online()).toBe(true);
  expect(host.querySelectorAll('section[aria-label="Portafoglio Brain"]')).toHaveLength(1);
});

test('unstarted single account never shows invented starting balance',async()=>{
  brainAPI.getScalpStatus.mockResolvedValue({data:{layout:'single',source:'snapshot',
    status:'not_started',profiles:{brain:{status:'not_started',available:false}}}});
  await mount();expect(host.querySelectorAll('section[aria-label="Portafoglio Brain"]')).toHaveLength(1);
  expect(host.textContent).not.toContain('$2000.00');
  expect(host.textContent).toContain('Nessun saldo ricostruito');
  expect(online()).toBe(false);
});
