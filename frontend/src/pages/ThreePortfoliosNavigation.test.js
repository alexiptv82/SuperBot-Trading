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
    expect(m.host.textContent).not.toContain('SOLUSDT');
    await act(async()=>chips.find(x=>x.textContent==='Perdenti').click());
    expect(m.host.textContent).toContain('SOL');
    expect(m.host.textContent).not.toContain('ETHUSDT');
    expect(API.get).toHaveBeenCalledWith('/api/v3/brain/trades?limit=100&offset=0');
  }finally{await m.done();}
});

test('Brain position close buttons remain disabled while cutover is readonly',()=>{
  const wallet=brainWalletSummary(paperOverview.portfolios[2],{state:'paused'},result);
  const html=renderToStaticMarkup(<BrainPortfolioSection wallet={wallet} rawTrades={result}
    readOnly onRefresh={()=>{}} />);
  expect(html).toContain('Chiusure');
  expect(html).toContain('disabled');
  expect(html).toContain('non disponibile').toBeUndefined();
});
