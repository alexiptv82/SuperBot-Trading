import React,{useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {brainAPI} from '../api';

const money = n => Number.isFinite(n) ? '$' + n.toFixed(2) : '—';
const card = {border:'1px solid #334155',background:'#1e293b',borderRadius:14,padding:14,marginBottom:14};
const label = {color:'#94a3b8',fontSize:12};
const fmtTime = n => Number.isFinite(n) ? new Date(n).toLocaleString('it-IT') : '—';

function Wallet({name,data,historical}) {
  const d=data || {}, ready=d.status==='ok';
  return <section style={card}>
    <h2 style={{margin:'0 0 6px',fontSize:19}}>🧠 Brain {name==='brain'?'· Conto unico':name==='hawk'?'Hawk':'Bull'}</h2>
    <p style={label}>{name==='brain'?'Conto PAPER unico':'Conto PAPER separato'} · Capitale iniziale {money(d.initial_cash)} · {d.max_slots ?? '—'} slot</p>
    {!ready ? <p role="status" style={{color:'#fbbf24'}}>Portafoglio non ancora avviato o dati non leggibili. Nessun saldo ricostruito.</p> : <>
      <p>{d.online && !historical ? '🟢 Online' : '🟠 Dati non aggiornati'} · {d.paused?'Aperture in pausa':'H24 previsto'}</p>
      {(d.snapshot_stale || historical) && <p role="status" style={{color:'#fbbf24'}}>Aggiornamento non disponibile: i valori mostrati sono storici, non quotazioni correnti.</p>}
      <p>Equity <strong>{money(d.equity)}</strong> · P&amp;L {money(d.net_pnl_vs_initial)}</p>
      {d.metrics && <p style={label}>Trade oggi: {d.metrics.trades_today ?? '—'} · Chiusi: {d.metrics.trades_closed ?? '—'} · Fee cumulative: {money(d.metrics.fee_paid_usd)} · Motivo blocco: {d.metrics.block_reason || 'nessuno'}</p>}
      <p>Disponibile {money(d.cash)} · Margine {money(d.margin)} / {money(d.margin_limit)}</p>
      <p>Slot occupati {d.positions?.length ?? 0}/{d.max_slots ?? '—'} · Piani in attesa {d.pending?.length ?? 0}</p>
      {d.equity===null && <p style={label}>Prezzi non aggiornati: equity e P&amp;L non vengono inventati.</p>}
      <h3>Posizioni aperte</h3>
      {!d.positions?.length && <p style={label}>Nessuna posizione.</p>}
      {d.positions?.map(p=><article key={p.symbol} style={{borderTop:'1px solid #334155',padding:'9px 0'}}>
        <strong>{p.symbol} · {p.side}</strong>
        <p>Margine {money(p.margin)} · Leva {p.leverage?.toFixed(1)}× · Nozionale {money(p.notional)}</p>
        <p>{historical?'Ultima stima netta disponibile':'Netto stimato di chiusura'} {money(p.net_close_estimate)} · Durata {p.age_minutes?.toFixed(1)} min</p>
        <p style={label}>Stop {p.stop} · Target {p.target} · {p.reason}</p>
      </article>)}
      <h3>Piani condizionali</h3>
      {!d.pending?.length && <p style={label}>Nessun ordine simulato in attesa.</p>}
      {d.pending?.map(p=><p key={p.symbol}>{p.symbol} {p.side} · {p.trigger} {p.price} · scade {fmtTime(p.expires_ms)}</p>)}
      <h3>Ultime chiusure</h3>
      {!d.trades?.length && <p style={label}>{d.trades_summary_only ? 'Snapshot di riepilogo: le singole chiusure restano nello storico SQLite.' : 'Nessuna chiusura registrata.'}</p>}
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
  const [received,setReceived]=useState(null);
  const [clock,setClock]=useState(()=>performance.now());
  const [error,setError]=useState(false);
  useEffect(()=>{
    const controller=new AbortController();let timer;
    // Age the last response even if the next GET hangs or the phone goes offline.
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
  const elapsed=received ? Math.max(0,clock-received.at) : 0;
  const snapshotAge=Number.isFinite(data?.snapshot_age_ms) ? data.snapshot_age_ms : 0;
  const historical=error || elapsed>=60000 || Boolean(data?.snapshot_stale) ||
    (data?.source==='snapshot' && snapshotAge+elapsed>60000);
  const walletHistorical=name=>{
    const d=data?.profiles?.[name];
    if(historical || !Number.isFinite(d?.heartbeat_ms)) return true;
    // Snapshot time + server-reported age avoids depending on phone clock skew.
    const observedNow=data.source==='snapshot' && Number.isFinite(data.snapshot_ts_ms)
      ? data.snapshot_ts_ms+snapshotAge : received.wall;
    const heartbeatAge=observedNow-d.heartbeat_ms+elapsed;
    return heartbeatAge<0 || heartbeatAge>=60000;
  };
  return <main style={{maxWidth:650,margin:'auto',padding:16,color:'#f1f5f9'}}>
    <h1>🧠 Brain Scalp · PAPER</h1>
    <p style={label}>{single?'Un solo portafoglio Brain PAPER.':'Portafogli Brain PAPER separati.'} Sola osservazione, nessun comando di trading.</p>
    <p><Link style={{color:'#38bdf8'}} to="/brain">Consulta archivio Brain precedente</Link></p>
    {error && <p role="status" style={{color:'#fbbf24'}}>Connessione non disponibile; gli ultimi valori ricevuti restano solo come storico.</p>}
    {data?.source==='snapshot' && <p style={label}>Fonte: snapshot PAPER {historical ? '(non aggiornato)' : '(ultimo aggiornamento verificato)'} · {fmtTime(data.snapshot_ts_ms)}</p>}
    {data?.status==='unavailable' && <p role="status" style={{color:'#fbbf24'}}>Snapshot non leggibile o non valido: saldi non disponibili.</p>}
    {names.map(name=><Wallet key={name} name={name} data={data?.profiles?.[name]} historical={walletHistorical(name)}/>)}
    <p style={label}>Saldo e risultati PAPER; costi AI non disponibili finché il nuovo provider non sarà collegato e misurato.</p>
  </main>;
}

