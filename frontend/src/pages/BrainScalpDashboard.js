import React, {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {brainAPI} from '../api';
import BrainOperatorReviews from '../components/BrainOperatorReviews';

// A deliberately compact, mobile-first PAPER portfolio view in the style of
// the classical trading desk. Financial values are never reconstructed from
// stale or missing quotes. The service publishes read-only settled history.
const BG='#0f172a',SURFACE='#1e293b',BORDER='#334155',MUTED='#94a3b8';
const GREEN='#4ade80',RED='#fb7185',BLUE='#38bdf8',AMBER='#fbbf24';
const number=n=>typeof n==='number' && Number.isFinite(n);
const money=n=>number(n)?'$'+Math.abs(n).toFixed(2):'—';
const signed=n=>number(n)?(n<0?'−':'+')+money(n):'—';
const num=(n,d=2)=>number(n)?n.toLocaleString('it-IT',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
const price=n=>number(n)?'$'+num(n,n<1?6:n<10?4:2):'—';
const date=n=>number(n)?new Date(n).toLocaleString('it-IT',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'—';
const pnlColor=n=>!number(n)?MUTED:n>=0?GREEN:RED;
const panel={border:'1px solid '+BORDER,background:SURFACE,borderRadius:14,padding:14};
const small={color:MUTED,fontSize:12};
const tabs=[['open','Aperte'],['history','Storico'],['stats','Statistiche'],['plans','In attesa']];
function Kpi({label,value,sub,color}) {
  return <div style={{...panel,minWidth:0,padding:12}}>
    <div style={{...small,marginBottom:5}}>{label}</div>
    <div style={{fontSize:21,fontWeight:800,color:color||'#f1f5f9',overflowWrap:'anywhere'}}>{value}</div>
    {sub&&<div style={{...small,marginTop:5}}>{sub}</div>}
  </div>;
}
function Status({active,stale,paused}) {
  return <div style={{display:'flex',gap:7,alignItems:'center',flexWrap:'wrap'}}>
    <span style={{fontSize:12,color:active&&!stale?GREEN:AMBER,fontWeight:700}}>
      {active&&!stale?'🟢 Online':'🟠 Dati non aggiornati'}
    </span>
    <span style={{fontSize:11,color:MUTED}}>· {paused?'Aperture in pausa':'H24 previsto'}</span>
    <span style={{fontSize:10,border:'1px solid #64748b',padding:'3px 6px',borderRadius:5,color:'#cbd5e1',fontWeight:700}}>PAPER</span>
  </div>;
}
function Position({item,stale}) {
  const p=item||{};
  const known=!stale&&p.price_status==='fresh'&&number(p.net_close_estimate);
  const net=known?p.net_close_estimate:null;
  const roi=known&&number(p.pnl_pct_margin)?p.pnl_pct_margin:null;
  const long=p.side==='LONG';
  return <article style={{...panel,marginBottom:9,borderLeft:'3px solid '+(long?GREEN:RED)}} data-testid="brain-position">
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',gap:8}}>
      <div>
        <strong style={{fontSize:17}}>{p.symbol}{p.symbol&&!p.symbol.endsWith('USDT')?'USDT':''}</strong>
        <span style={{fontSize:11,marginLeft:7,color:long?GREEN:RED,fontWeight:800}}>{p.side||'—'}</span>
      </div>
      <div style={{textAlign:'right'}}>
        <div style={{fontSize:18,fontWeight:800,color:pnlColor(net)}}>{signed(net)}</div>
        <div style={{fontSize:11,color:pnlColor(roi)}}>{number(roi)?(roi>=0?'+':'')+num(roi,2)+'% margine':'P&L non disponibile'}</div>
      </div>
    </div>
    <div style={{display:'grid',gridTemplateColumns:'repeat(2,minmax(0,1fr))',gap:12,marginTop:13}}>
      <div><div style={small}>Prezzo entrata</div><strong>{price(p.entry)}</strong></div>
      <div><div style={small}>Prezzo attuale</div><strong>{!stale&&p.price_status==='fresh'?price(p.mark_price):'—'}</strong></div>
      <div><div style={small}>Margine</div><strong>{money(p.margin)}</strong></div>
      <div><div style={small}>Leva</div><strong>{number(p.leverage)?num(p.leverage,1)+'×':'—'}</strong></div>
      <div><div style={small}>Stop loss</div><strong>{price(p.stop)}</strong></div>
      <div><div style={small}>Take profit</div><strong>{price(p.target)}</strong></div>
    </div>
    <div style={{...small,borderTop:'1px solid '+BORDER,marginTop:12,paddingTop:10,display:'flex',justifyContent:'space-between',gap:8}}>
      <span>Nozionale {money(p.notional)}</span><span>Durata {number(p.age_minutes)?num(p.age_minutes,0)+' min':'—'}</span>
    </div>
    {!known&&<div style={{fontSize:11,color:AMBER,marginTop:7}}>Quotazione non verificata: il profitto non viene inventato.</div>}
  </article>;
}
function History({wallet}) {
  const rows=wallet.trades||[];
  return <>
    <p style={small}>Ultime {rows.length} chiusure PAPER registrate nel portafoglio. {number(wallet.closed_total)?'Totale '+wallet.closed_total+'.':''}</p>
    {!rows.length&&<div style={panel}>Nessuna chiusura ancora disponibile nello storico. {wallet.trades_summary_only?'Lo storico dettagliato non è ancora pubblicato.':''}</div>}
    {rows.map((t,i)=><article key={String(t.position_id)+'-'+i} style={{...panel,marginBottom:8}}>
      <div style={{display:'flex',justifyContent:'space-between',gap:12}}>
        <strong>{t.symbol}{t.symbol&&!t.symbol.endsWith('USDT')?'USDT':''} <span style={{fontSize:11,color:t.side==='LONG'?GREEN:RED}}>{t.side===1?'LONG':t.side===-1?'SHORT':t.side}</span></strong>
        <strong style={{color:pnlColor(t.net)}}>{signed(t.net)}</strong>
      </div>
      <div style={{...small,display:'grid',gridTemplateColumns:'1fr 1fr',gap:6,marginTop:9}}>
        <span>Entrata: {price(t.entry)}</span><span>Uscita: {price(t.exit)}</span>
        <span>Leva: {number(t.leverage)?num(t.leverage,1)+'×':'—'}</span><span>Chiuso: {date(t.close_ms)}</span>
      </div>
      {t.reason&&<div style={{...small,marginTop:9}}>Motivo: {t.reason}</div>}
    </article>)}
  </>;
}
function Stats({wallet}) {
  const m=wallet.metrics||{};
  const n=wallet.trades_shown;
  const win=wallet.recent_closed_wins;
  return <>
    <p style={small}>Statistiche del conto PAPER. Le vittorie recenti riguardano soltanto le ultime {number(n)?n:0} chiusure disponibili, non necessariamente tutta la storia.</p>
    <div style={{display:'grid',gridTemplateColumns:'repeat(2,minmax(0,1fr))',gap:9}}>
      <Kpi label="Trade aperti oggi" value={number(m.trades_today)?m.trades_today:'—'}/>
      <Kpi label="Trade chiusi totali" value={number(wallet.closed_total)?wallet.closed_total:number(m.trades_closed)?m.trades_closed:'—'}/>
      <Kpi label="Profitti/perdite realizzati" value={signed(m.pnl_realized_usd)} color={pnlColor(m.pnl_realized_usd)}/>
      <Kpi label="Commissioni contabilizzate" value={money(m.fee_paid_usd)}/>
      <Kpi label="Vittorie nelle ultime chiusure" value={number(win)&&number(n)&&n>0?num(win/n*100,1)+'%':'—'} sub={number(win)?win+' vinte su '+n:''}/>
      <Kpi label="Durata media trade" value={number(m.avg_duration_min)?num(m.avg_duration_min,0)+' min':'—'}/>
    </div>
    <p style={{...small,marginTop:12}}>Il P&L realizzato e l'equity non sono la stessa misura; i costi AI non sono compresi finché non saranno rendicontati.</p>
  </>;
}
function Wallet({name,data,historical}) {
  const [tab,setTab]=useState('open');
  const d=data||{};
  const ready=d.status==='ok';
  const single=name==='brain';
  return <section aria-label="Portafoglio Brain" style={{padding:0}}>
    <header style={{...panel,marginBottom:13}}>
      <h2 style={{margin:'0 0 7px',fontSize:21}}>{single?'🧠 Brain · Conto unico':'🧠 Brain '+(name==='hawk'?'Hawk':'Bull')}</h2>
      <Status active={d.online} stale={historical} paused={d.paused}/>
      <div style={{...small,marginTop:8}}>Capitale iniziale {money(d.initial_cash)} · {d.max_slots ?? '—'} slot · {single?'portafoglio unico':'conto separato'}</div>
    </header>
    {!ready?<div role="status" style={{...panel,color:AMBER}}>Portafoglio non ancora avviato o dati non leggibili. Nessun saldo ricostruito.</div>:<>
      {historical&&<div role="status" style={{...panel,marginBottom:12,color:AMBER}}>Aggiornamento non disponibile: i valori mostrati sono storici, non quotazioni correnti.</div>}
      <div style={{display:'grid',gridTemplateColumns:'repeat(2,minmax(0,1fr))',gap:9,marginBottom:12}}>
        <Kpi label="Patrimonio (equity)" value={money(d.equity)} sub={!number(d.equity)?'Prezzi incompleti':undefined}/>
        <Kpi label="P&L complessivo" value={signed(d.net_pnl_vs_initial)} color={pnlColor(d.net_pnl_vs_initial)}/>
        <Kpi label="Saldo disponibile" value={money(d.cash)}/>
        <Kpi label="Margine utilizzato" value={money(d.margin)} sub={'Limite '+money(d.margin_limit)}/>
      </div>
      <div style={{...panel,marginBottom:13,display:'flex',justifyContent:'space-between',gap:8,alignItems:'center'}}>
        <div><strong>{d.positions?.length??0}/{d.max_slots??'—'}</strong><div style={small}>Slot occupati</div></div>
        <div style={{textAlign:'right'}}><strong>{d.pending?.length??0}</strong><div style={small}>Piani in attesa</div></div>
      </div>
      {single&&<BrainOperatorReviews/>}
      <div role="tablist" aria-label="Sezioni conto Brain" style={{display:'flex',gap:5,overflowX:'auto',marginBottom:12}}>
        {tabs.map(([id,text])=><button key={id} role="tab" aria-selected={tab===id}
           onClick={()=>setTab(id)} style={{border:'1px solid '+(tab===id?BLUE:BORDER),
             background:tab===id?'#12394d':SURFACE,color:tab===id?'#f1f5f9':MUTED,
             padding:'9px 12px',borderRadius:9,fontWeight:700,fontSize:12,whiteSpace:'nowrap',cursor:'pointer'}}>
          {text}
        </button>)}
      </div>
      {tab==='open'&&<div role="tabpanel">
        <h3 style={{fontSize:16,margin:'8px 0 12px'}}>Posizioni aperte</h3>
        {!d.positions?.length&&<div style={panel}>Nessuna posizione aperta. Uno slot libero non è un errore.</div>}
        {d.positions?.map((p,i)=><Position key={p.position_id||p.symbol||i} item={p} stale={historical}/>)}
      </div>}
      {tab==='history'&&<div role="tabpanel"><h3 style={{fontSize:16}}>Storico chiusure</h3><History wallet={d}/></div>}
      {tab==='stats'&&<div role="tabpanel"><h3 style={{fontSize:16}}>Statistiche</h3><Stats wallet={d}/></div>}
      {tab==='plans'&&<div role="tabpanel">
        <h3 style={{fontSize:16}}>Piani in attesa</h3>
        {!d.pending?.length&&<div style={panel}>Nessun piano condizionale in attesa.</div>}
        {d.pending?.map((p,i)=><div key={p.symbol||i} style={{...panel,marginBottom:8}}>
          <strong>{p.symbol} · {p.side}</strong>
          <div style={{...small,marginTop:5}}>Ingresso condizionale {p.trigger} a {price(p.price)}</div>
          <div style={small}>Margine riservato {money(p.margin_reserved)} · Scade {date(p.expires_ms)}</div>
        </div>)}
      </div>}
    </>}
  </section>;
}

export default function BrainScalpDashboard() {
  const [received,setReceived]=useState(null);
  const [clock,setClock]=useState(()=>performance.now());
  const [error,setError]=useState(false);
  useEffect(()=>{
    const controller=new AbortController();let timer;
    const ageTimer=setInterval(()=>setClock(performance.now()),1000);
    const poll=async()=>{
      try{
        const r=await brainAPI.getScalpStatus(controller.signal);
        if(!controller.signal.aborted){
          const at=performance.now();
          setReceived({data:r.data,at,wall:Date.now()});setClock(at);setError(false);
        }
      }catch(_){if(!controller.signal.aborted)setError(true);}
      if(!controller.signal.aborted)timer=setTimeout(poll,15000);
    };
    poll();
    return ()=>{controller.abort();clearTimeout(timer);clearInterval(ageTimer);};
  },[]);
  const data=received?.data;
  const single=data?.layout==='single';
  const names=single?['brain']:['hawk','bull'];
  const elapsed=received?Math.max(0,clock-received.at):0;
  const snapshotAge=number(data?.snapshot_age_ms)?data.snapshot_age_ms:0;
  const historical=error||elapsed>=60000||Boolean(data?.snapshot_stale)||
    (data?.source==='snapshot'&&snapshotAge+elapsed>60000);
  const walletHistorical=name=>{
    const d=data?.profiles?.[name];
    if(historical||!number(d?.heartbeat_ms))return true;
    const observedNow=data?.source==='snapshot'&&number(data?.snapshot_ts_ms)
      ?data.snapshot_ts_ms+snapshotAge:received.wall;
    const heartbeatAge=observedNow-d.heartbeat_ms+elapsed;
    return heartbeatAge<0||heartbeatAge>=60000;
  };
  return <main style={{maxWidth:700,margin:'auto',padding:'18px 12px 100px',background:BG,color:'#f1f5f9',minHeight:'100vh'}}>
    <div style={{display:'flex',alignItems:'flex-start',justifyContent:'space-between',gap:12,marginBottom:14}}>
      <div><h1 style={{fontSize:24,margin:'0 0 6px'}}>Brain Trading</h1>
        <p style={{...small,margin:0}}>Dashboard PAPER · Sola lettura, nessun comando operativo.</p>
      </div>
      <Link to="/brain" style={{color:BLUE,fontSize:12,textDecoration:'none'}}>Archivio Brain</Link>
    </div>
    {error&&<div role="status" style={{...panel,color:AMBER,marginBottom:12}}>Connessione non disponibile; gli ultimi valori ricevuti restano solo come storico.</div>}
    {data?.source==='snapshot'&&<p style={{...small,margin:'0 0 12px'}}>Fonte: snapshot PAPER {historical?'(non aggiornato)':'(ultimo aggiornamento verificato)'} · {date(data.snapshot_ts_ms)}</p>}
    {data?.status==='unavailable'&&<p role="status" style={{color:AMBER}}>Snapshot non leggibile o non valido: saldi non disponibili.</p>}
    {names.map(name=><Wallet key={name} name={name} data={data?.profiles?.[name]} historical={walletHistorical(name)}/>)}
    <p style={{...small,marginTop:18}}>Tutti gli importi sono simulati. Il netto di posizione è una stima di chiusura basata solo su quotazioni recenti, inclusi i costi stimati. Se il dato manca compare —.</p>
  </main>;
}
