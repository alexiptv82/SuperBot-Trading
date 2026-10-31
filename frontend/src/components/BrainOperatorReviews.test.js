import React from 'react';
import {createRoot} from 'react-dom/client';
import {act} from 'react-dom/test-utils';
import BrainOperatorReviews from './BrainOperatorReviews';

const groups={status:'available',groups:[{group_id:'b'.repeat(16),symbols:['BTC'],count:1,net_usd:12}]};
const reply=data=>Promise.resolve({ok:true,json:async()=>data});
let host,root,originalFetch,originalCrypto;
beforeEach(()=>{
  jest.useFakeTimers();global.IS_REACT_ACT_ENVIRONMENT=true;
  originalFetch=global.fetch;global.fetch=jest.fn();
  originalCrypto=Object.getOwnPropertyDescriptor(global,'crypto');
  Object.defineProperty(global,'crypto',{configurable:true,value:{randomUUID:()=> 'a'.repeat(32)}});
  host=document.createElement('div');root=createRoot(host);
});
afterEach(async()=>{
  await act(async()=>root.unmount());
  expect(jest.getTimerCount()).toBe(0);
  global.fetch=originalFetch;jest.useRealTimers();
  if(originalCrypto)Object.defineProperty(global,'crypto',originalCrypto);
  else delete global.crypto;
});
const mount=async()=>act(async()=>root.render(<BrainOperatorReviews/>));
const advance=async(ms)=>act(async()=>jest.advanceTimersByTime(ms));
const click=async()=>act(async()=>host.querySelector('button').click());

test('confirmation is sent once and pending is distinct from owner confirmation',async()=>{
  global.fetch.mockImplementation(url=>reply(url.includes('/result/')?{status:'confirmed'}:url.endsWith('/confirm')?{status:'pending'}:groups));
  await mount();await click();await click();
  expect(global.fetch.mock.calls.filter(([url])=>url.endsWith('/confirm'))).toHaveLength(1);
  expect(host.textContent).toContain('Richiesta accodata');
  expect(host.textContent).not.toContain('Conferma registrata');
  await advance(5000);
  expect(host.textContent).toContain('Conferma registrata dal Brain');
  expect(host.querySelector('button').disabled).toBe(true);
});

test('hanging polls abort after deadline without overlapping polls and recover',async()=>{
  let signal;
  global.fetch.mockImplementationOnce((url,options)=>new Promise((resolve,reject)=>{
    signal=options.signal;signal.addEventListener('abort',()=>reject(new Error('aborted')));
  })).mockImplementation(()=>reply(groups));
  await mount();await advance(5000);
  expect(global.fetch).toHaveBeenCalledTimes(1);
  await advance(5000);expect(signal.aborted).toBe(true);
  expect(host.textContent).toContain('temporaneamente non disponibili');
  await advance(5000);expect(host.textContent).toContain('BTC');
});

test('uncertain POST remains disabled and receipt is checked without resending',async()=>{
  global.fetch.mockImplementation(url=>url.endsWith('/confirm')?Promise.reject(new Error('lost reply')):reply(url.includes('/result/')?{status:'needs_reconciliation'}:groups));
  await mount();await click();
  expect(host.textContent).toContain('Esito invio incerto');
  await advance(5000);
  expect(host.textContent).toContain('needs_reconciliation');
  expect(host.querySelector('button').disabled).toBe(true);
  expect(global.fetch.mock.calls.filter(([url])=>url.endsWith('/confirm'))).toHaveLength(1);
});

test('unmount aborts pending requests and cancels timers',async()=>{
  let signal;
  global.fetch.mockImplementation((url,options)=>new Promise((resolve,reject)=>{
    signal=options.signal;signal.addEventListener('abort',()=>reject(new Error('aborted')));
  }));
  await mount();await act(async()=>root.unmount());
  expect(signal.aborted).toBe(true);expect(jest.getTimerCount()).toBe(0);
  root=createRoot(host);
});

test('classical confirmation uses its portfolio endpoint and exact account scope',async()=>{
  const classic={...groups,account_id:'desk-hawk-paper-run-8'};
  global.fetch.mockImplementation(url=>reply(url.includes('/result/')?{status:'confirmed'}:url.endsWith('/confirm')?{status:'pending'}:classic));
  await act(async()=>root.render(<BrainOperatorReviews basePath="/api/desk/operator/hawk" owner="Falco" accountScoped/>));
  await click();await click();
  const posts=global.fetch.mock.calls.filter(([url])=>url.endsWith('/confirm'));
  expect(posts).toHaveLength(1);
  expect(posts[0][0]).toBe('/api/desk/operator/hawk/confirm');
  expect(JSON.parse(posts[0][1].body).account_id).toBe('desk-hawk-paper-run-8');
  await advance(5000);
  expect(host.textContent).toContain('Conferma registrata da Falco');
});
