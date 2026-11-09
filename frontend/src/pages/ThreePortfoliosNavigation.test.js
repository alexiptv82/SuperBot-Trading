import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import Dashboard from './Dashboard';
import Trades from './Trades';
import BrainPortfolioSection from '../components/BrainPortfolioSection';
import { brainWalletSummary } from '../brainWallet';
import API, { deskAPI, bullAPI } from '../api';

jest.mock('../api', () => {
  const get = jest.fn();
  return {
    __esModule:true,
    default: { get },
    deskAPI: { getStatus: jest.fn(), getPrices:jest.fn() },
    bullAPI: { getStatus: jest.fn() },
    errMsg: () => 'Errore di rete',
  };
});

const paperOverview = {
  generated_at_ms:Date.now(),cutover_readonly:true,
  portfolios:[{id:'falco',state:'paused',open_positions:6},{id:'toro',state:'paused',open_positions:2},
    {id:'brain',state:'not_started',start_equity:null,equity:null,day_pnl:null,
      settled_equity:null,realized_pnl:'0',margin_in_use:'0',total_closed:2,win_rate:'50'}]
};
const result = {
  total_closed:2,win_count:1,loss_count:1,offset:0,has_more:false,close_pending:false,
  open_positions:[{position_id:'p1',symbol:'BTCUSDT',side:1,entry:'100',price:null,margin:'200',leverage:25,
    unrealized_pnl:null,roi_pct:null,stop:'98'}],
  closed_trades:[
    {position_id:'p2',symbol:'ETHUSDT',side:1,entry:'100',exit:'105',margin:'200',
      leverage:20,realized_pnl:'9',exit_reason:'take_profit',closed_at_ms:1700000000000},
    {position_id:'p3',symbol:'SOLUSDT',side:-1,entry:'100',exit:'102',margin:'200',
      leverage:20,realized_pnl:'-7',exit_reason:'stop_loss',closed_at_ms:1700000001000}
  ]
};
function prepare() {
  deskAPI.getStatus.mockResolvedValue({ data:{available:false} });
  bullAPI.getStatus.mockResolvedValue({ data:{available:false} });
  deskAPI.getPrices.mockResolvedValue({ data:{} });
  API.get.mockImplementation(url => {
    if (url.includes('/api/v3/overview')) return Promise.resolve({data:paperOverview});
    if (url.includes('/api/v3/brain/status')) return Promise.resolve({data:{state:'not_started',paused:true}});
    if (url.includes('/api/v3/brain/trades')) return Promise.resolve({data:result});
    return Promise.reject(new Error('Unexpected URL '+url));
  });
}
async function mount(Component) {
  const host=document.createElement('div');
  document.body.appendChild(host);
  const root=createRoot(host);
  await act(async()=>root.render(<Component/>));
  return {host,done:async()=>{await act(async()=>root.unmount());host.remove()}};
}
beforeEach(()=>{prepare();window.history.replaceState(null,'','/classic');global.IS_REACT_ACT_ENVIRONMENT=true});
afterEach(()=>{jest.clearAllMocks()});

test('Classici offers Falco, Toro and Brain and Brain uses same wallet hero, read-only controls and AI details',async()=>{
  const m=await mount(Dashboard);
  try{
    const choices=Array.from(m.host.querySelectorAll('button[aria-pressed]'));
    expect(choices.map(x=>x.textContent)).toEqual(expect.arrayContaining(['🦅 Falco','🐂 Toro','🧠 Brain']));
    const b=choices.find(x=>x.textContent.includes('Brain'));
    await act(async()=>b.click());
    const card=m.host.querySelector('[data-testid="brain-classic-wallet"]');
    expect(card).not.toBeNull();
    expect(card.textContent).toContain('Equity');
    expect(card.textContent).toContain('Posizioni Aperte');
    expect(card.textContent).toContain('Chiuse');
    expect(card.textContent).toContain('AI');
    expect(card.textContent).toContain('sola lettura');
    expect(card.querySelector('button:disabled')).not.toBeNull();
    expect(card.textContent).not.toContain('$2000.00'); // capital absent from run ledger, not invented
  }finally{await m.done();}
});

test('Trade uses the same three selectors, exact closed outcomes and side/outcome filters for Brain',async()=>{
  const m=await mount(Trades);
  try{
    const brain=Array.from(m.host.querySelectorAll('button[aria-pressed]'))
      .find(x=>x.textContent.includes('Brain'));
    await act(async()=>brain.click());
    expect(m.host.textContent).toContain('Vincenti');
    expect(m.host.textContent).toContain('Perdenti');
    expect(m.host.textContent).toContain('ETH');
    expect(m.host.textContent).toContain('SOL');
    expect(m.host.textContent).toContain('BTC');
    expect(m.host.textContent).toContain('prezzo mancante');
    const chips=Array.from(m.host.querySelectorAll('button'));
    await act(async()=>chips.find(x=>x.textContent==='Vincenti').click());
    expect(m.host.textContent).toContain('ETH');
    expect(Array.from(m.host.querySelectorAll('[data-testid="trade-ticket"]')).map(x=>x.textContent)).toEqual([expect.stringContaining('ETH')]);
    await act(async()=>chips.find(x=>x.textContent==='Perdenti').click());
    expect(m.host.textContent).toContain('SOL');
    expect(Array.from(m.host.querySelectorAll('[data-testid="trade-ticket"]')).map(x=>x.textContent)).toEqual([expect.stringContaining('SOL')]);
    expect(API.get).toHaveBeenCalledWith('/api/v3/brain/trades?limit=100&offset=0');
  }finally{await m.done();}
});

test('Brain position close buttons remain disabled while cutover is readonly',()=>{
  const wallet=brainWalletSummary(paperOverview.portfolios[2],{state:'paused'},result);
  const html=renderToStaticMarkup(<BrainPortfolioSection wallet={wallet} rawTrades={result}
    readOnly onRefresh={()=>{}} />);
  expect(html).toContain('chiusure disabilitate');
  expect(html).toContain('disabled');
  expect(html).toContain('Equity');
});


test('RC84: Falco RUNNING alarms remain visible even when Brain API is unavailable',async()=>{
  deskAPI.getStatus.mockResolvedValue({data:{
    available:true, bot_mode:'running', positions:[{symbol:'BTC',side:1,entry:100,qty:1,
      margin:100,leverage:20,trade_type:'scalp'}], cash:900, margin_used:100, equity:1000,
    pnl_total:0, start_equity:1000, run_no:1, max_open:10, total_closed:0,
    close_worker_mode:'classic_runner', can_close_position:false, bot_online:true
  }});
  const stopped = {scope:'classic_runner_15m_ohlc',state:'degraded',alarm:true,
    stop_certified:false,quote_coverage:false,blocked_symbols:['ARB'],
    reason:'feed_alarm_or_unchecked_positions'};
  API.get.mockImplementation(url => {
    if (url === '/api/v3/overview') return Promise.resolve({data:{
      generated_at_ms:Date.now(),cutover_readonly:true,classic_single_close_allowed:false,
      portfolios:[{id:'falco',kind:'classic',open_positions:1,stop_health:stopped},
                  {id:'toro',kind:'classic',open_positions:0},
                  {id:'brain',kind:'brain',state:'paused',open_positions:0}]
    }});
    return Promise.reject(new Error('Brain temporarily unreachable'));
  });
  const m=await mount(Dashboard);
  try{
    const notice=m.host.querySelector('[data-testid="classic-running-stop-notice"]');
    expect(notice).not.toBeNull();
    expect(notice.getAttribute('role')).toBe('alert');
    expect(notice.textContent).toContain('ARB');
    expect(notice.textContent).toContain('non equivale a stop-loss certificato');
    expect(API.get).toHaveBeenCalledWith('/api/v3/brain/status');
  }finally{await m.done();}
});

const flatStatus = {data:{
  available:true, bot_mode:'running', positions:[], cash:1005.03, margin_used:0, equity:1005.03,
  pnl_total:5.03, start_equity:1000, run_no:1, max_open:10, total_closed:1,
  close_worker_mode:'classic_runner', can_close_position:false, bot_online:true
}};
const reconOverview = (falco) => ({data:{
  generated_at_ms:Date.now(),cutover_readonly:true,classic_single_close_allowed:false,
  portfolios:[{id:'falco',kind:'classic',state:'running',open_positions:0,...falco},
              {id:'toro',kind:'classic',state:'paused',open_positions:0},
              {id:'brain',kind:'brain',state:'paused',open_positions:0}]
}});

test('D1: Classici shows the reconciliation alert with zero open positions and Brain API down',async()=>{
  deskAPI.getStatus.mockResolvedValue(flatStatus);
  API.get.mockImplementation(url => url === '/api/v3/overview'
    ? Promise.resolve(reconOverview({close_reconciliation:{state:'pending',pending_count:1,conflict_count:0,
        affected_symbols:['BTC'],checkpointed_not_final:true}}))
    : Promise.reject(new Error('Brain temporarily unreachable')));
  const m=await mount(Dashboard);
  try{
    const notice=m.host.querySelector('[data-testid="claim-reconciliation-notice"]');
    expect(notice).not.toBeNull();
    expect(notice.getAttribute('role')).toBe('alert');
    expect(notice.textContent).toContain('BTC');
    expect(notice.textContent).toContain('possono includere chiusure non ancora definitive');
    expect(m.host.textContent).toContain('5.03');
  }finally{await m.done();}
});

test('D1: Classici shows a conflict, then no alert after the claim is reconciled',async()=>{
  deskAPI.getStatus.mockResolvedValue(flatStatus);
  let recon={state:'conflict',pending_count:0,conflict_count:1,affected_symbols:['ETH'],checkpointed_not_final:true};
  API.get.mockImplementation(url => url === '/api/v3/overview'
    ? Promise.resolve(reconOverview({close_reconciliation:recon}))
    : Promise.reject(new Error('x')));
  let m=await mount(Dashboard);
  try{
    expect(m.host.querySelector('[data-testid="claim-reconciliation-notice"]').textContent).toContain('intervento umano');
  }finally{await m.done();}
  recon={state:'ok',pending_count:0,conflict_count:0,affected_symbols:[],checkpointed_not_final:false};
  m=await mount(Dashboard);
  try{
    expect(m.host.querySelector('[data-testid="claim-reconciliation-notice"]')).toBeNull();
  }finally{await m.done();}
});

test('D1: when the overview itself is unavailable the Classici page says reconciliation is not verifiable',async()=>{
  deskAPI.getStatus.mockResolvedValue(flatStatus);
  API.get.mockImplementation(() => Promise.reject(new Error('overview down')));
  const m=await mount(Dashboard);
  try{
    const notice=m.host.querySelector('[data-testid="claim-reconciliation-notice"]');
    expect(notice).not.toBeNull();
    expect(notice.textContent).toContain('non verificabile');
  }finally{await m.done();}
});

test('D1: the notice adds no request other than the existing GETs',async()=>{
  deskAPI.getStatus.mockResolvedValue(flatStatus);
  API.get.mockImplementation(url => url === '/api/v3/overview'
    ? Promise.resolve(reconOverview({close_reconciliation:{state:'pending',pending_count:1,conflict_count:0,
        affected_symbols:['BTC'],checkpointed_not_final:true}}))
    : Promise.reject(new Error('x')));
  const m=await mount(Dashboard);
  try{
    expect(m.host.querySelectorAll('[data-testid="claim-reconciliation-notice"] button, [data-testid="claim-reconciliation-notice"] a')).toHaveLength(0);
    expect(API.post).toBeUndefined();
  }finally{await m.done();}
});
