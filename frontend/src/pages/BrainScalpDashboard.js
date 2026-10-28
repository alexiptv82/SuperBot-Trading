import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {brainAPI} from '../api';

const money = n => Number.isFinite(n) ? '$' + n.toFixed(2) : '—';
const card = {border:'1px solid #334155',background:'#1e293b',borderRadius:14,padding:14,marginBottom:14};
const label = {color:'#94a3b8',fontSize:12};
const fmtTime = n => Number.isFinite(n) ? new Date(n).toLocaleString('it-IT') : '—';

function Wallet({name,data}) {
  const d=data || {}, ready=d.status==='ok';
  return <section style={card}>
    <h2 style={{margin:'0 0 6px',fontSize:19}}>🧠 Brain {name==='hawk'?'Hawk':'Bull'}</h2>
    <p style={label}>Conto PAPER separato · base di prova 1.000 $ · {name==='hawk'?10:3} slot</p>
    {!ready ? <p role="status" style={{color:'#fbbf24'}}>Portafoglio non ancora avviato o dati non leggibili. Nessun saldo ricostruito.</p> : <>
      <p>{d.online ? '🟢 Online' : '🟠 Dati non aggiornati'} · {d.paused?'Aperture in pausa':'H24 previsto'}</p>
      <p>Equity <strong>{money(d.equity)}</strong> · P&amp;L {money(d.net_pnl_vs_initial)}</p>
      <p>Disponibile {money(d.cash)} · Margine {money(d.margin)} / {money(d.margin_limit)}</p>
      <p>Slot occupati {d.positions?.length ?? 0}/{d.max_slots ?? '—'} · Piani in attesa {d.pending?.length ?? 0}</p>
      {d.equity===null && <p style={label}>Prezzi non aggiornati: equity e P&amp;L non vengono inventati.</p>}
      <h3>Posizioni aperte</h3>
      {!d.positions?.length && <p style={label}>Nessuna posizione.</p>}
      {d.positions?.map(p=><article key={p.symbol} style={{borderTop:'1px solid #334155',padding:'9px 0'}}>
        <strong>{p.symbol} · {p.side}</strong>
        <p>Margine {money(p.margin)} · Leva {p.leverage?.toFixed(1)}× · Nozionale {money(p.notional)}</p>
        <p>Netto chiudendo ora {money(p.net_close_estimate)} · Durata {p.age_minutes?.toFixed(1)} min</p>
        <p style={label}>Stop {p.stop} · Target {p.target} · {p.reason}</p>
      </article>)}
      <h3>Piani condizionali</h3>
      {!d.pending?.length && <p style={label}>Nessun ordine simulato in attesa.</p>}
      {d.pending?.map(p=><p key={p.symbol}>{p.symbol} {p.side} · {p.trigger} {p.price} · scade {fmtTime(p.expires_ms)}</p>)}
      <h3>Ultime chiusure</h3>
      {!d.trades?.length && <p style={label}>Nessuna chiusura registrata.</p>}
      {d.trades?.map((t,i)=><p key={t.position_id+'-'+i}>
        {t.symbol} · {t.side===1?'LONG':'SHORT'} · netto {money(t.net)} · {t.reason}
      </p>)}
      <details><summary>Ultimi eventi e rifiuti</summary>
        {d.rejections?.map((r,i)=><p key={i} style={label}>{r.symbol}: {r.why}</p>)}
        {d.latest_events?.map((e,i)=><p key={i} style={label}>{fmtTime(e.ts)} · {e.kind} · {e.body?.symbol || 'wallet'}</p>)}
      </details>
    </>}
  </section>;
}

export default function BrainScalpDashboard() {
  const [data,setData]=useState(null);
  const [error,setError]=useState(false);
  useEffect(()=>{
    const controller=new AbortController();let timer;
    const poll=async()=>{
      try{
        const r=await brainAPI.getScalpStatus(controller.signal);
        if(!controller.signal.aborted){setData(r.data);setError(false);}
      }catch(_){if(!controller.signal.aborted)setError(true);}
      if(!controller.signal.aborted)timer=setTimeout(poll,15000);
    };
    poll();
    return ()=>{controller.abort();clearTimeout(timer);};
  },[]);
  return <main style={{maxWidth:650,margin:'auto',padding:16,color:'#f1f5f9'}}>
    <h1>🧠 Brain Scalp · PAPER</h1>
    <p style={label}>Due portafogli indipendenti, stesso scanner 1m/5m. Sola osservazione, nessun comando di trading.</p>
    <p><Link style={{color:'#38bdf8'}} to="/brain">Consulta archivio Brain precedente</Link></p>
    {error && <p role="status" style={{color:'#fbbf24'}}>Connessione non disponibile; non mostrare dati inventati.</p>}
    <Wallet name="hawk" data={data?.profiles?.hawk}/>
    <Wallet name="bull" data={data?.profiles?.bull}/>
    <p style={label}>Saldo e risultati PAPER; costi AI non disponibili finché il nuovo provider non sarà collegato e misurato.</p>
  </main>;
}
