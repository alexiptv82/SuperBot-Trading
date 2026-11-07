import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRoot } from 'react-dom/client';
import { act } from 'react-dom/test-utils';
import API from '../api';
import SupervisorTerminal, { SupervisorResult, decisionReason, skipReason } from './SupervisorTerminal';

jest.mock('../api', () => ({ get: jest.fn() }));

const c = { id:'brain.dec.1', kind:'OPEN', status:'APPROVED', reason_class:'approved_open',
  reason_code:'risk_quote_ok', at_ms:1700000000000, symbol:'BTCUSDT', regime:'TREND_UP',
  strategy_id:'S07', execution:'closed_verified', net_bp:'25.0', realized_pnl:'2.5',
  evidence_status:'recorded', evidence:{ equity:'1000', risk_at_stop:'18', risk_budget:'20',
  market_sha256:'a'.repeat(64), timeframes:[{tf:'15m',status:'ok',regime:'TREND_UP',rsi:'46',adx:'28'}] } };

beforeEach(()=> { API.get.mockReset(); global.IS_REACT_ACT_ENVIRONMENT = true; });

test('static cards expose recorded data with explicit missing memory', () => {
 const html = renderToStaticMarkup(<SupervisorResult data={{state:'ready',decisions:[c]}} />);
 expect(html).toContain('BTCUSDT');
 expect(html).toContain('Apertura approvata');
 expect(html).toContain('Dettagli verificabili');
 expect(html).toContain('Rischio stimato allo stop');
 expect(html).toContain('non ancora registrate');
});

test('preflight candidate not counted as Brain NO_TRADE', () => {
 const html = renderToStaticMarkup(<SupervisorResult data={{state:'ready',decisions:[{
  ...c,id:'supervisor.2',kind:'SKIPPED',reason_class:'preflight_skipped',reason_code:'feed_error',
  status:'NOT_ANALYZED',evidence:null,net_bp:null
 }]}} />);
 expect(html).toContain('Scartato'); expect(html).toContain('Dati mercato non accessibili');
 expect(html).toContain('Non registrato');
});

test('missing data and truncated source are disclosed', () => {
 const html = renderToStaticMarkup(<SupervisorResult data={{state:'ready',decisions:[],source_window_limited:true}}/>);
 expect(html).toContain('Risultati parziali'); expect(html).toContain('Nessuna decisione corrispondente');
 expect(renderToStaticMarkup(<SupervisorResult data={{state:'not_started'}}/>)).toContain('non è ancora stato avviato');
});

test('safe reason labels handle prototype keys', () => {
 expect(decisionReason('__proto__')).toBe('Motivazione non disponibile');
 expect(decisionReason('brain_wait')).toContain('aspettare');
 expect(skipReason('feed_error')).toContain('Dati mercato');
 expect(skipReason('<script>')).toBe('Scarto non classificato');
});

function mount() {
 const host=document.createElement('div'); document.body.appendChild(host);
 const root=createRoot(host);
 return {host, draw: async() => {await act(async()=>root.render(<SupervisorTerminal/>));},
   close: async()=> {await act(async()=>root.unmount());host.remove();}};
}

test('fetches authenticated GET endpoint and shows cards', async() => {
 API.get.mockResolvedValue({data:{state:'ready',decisions:[c]}});
 const a=mount();
 try {
  await a.draw();
  expect(API.get).toHaveBeenCalledWith('/api/v3/brain/decision-timeline',{params:{limit:50}});
  expect(a.host.textContent).toContain('BTCUSDT');
 } finally { await a.close(); }
});

test('503 shows explicit missing integration not imaginary trading results',async()=>{
 API.get.mockRejectedValue({response:{status:503}});
 const a=mount();
 try{await a.draw();expect(a.host.textContent).toContain('non ancora integrato');}
 finally{await a.close();}
});
