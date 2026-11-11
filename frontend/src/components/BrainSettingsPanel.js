import React, { useCallback, useEffect, useRef, useState } from 'react';
import API, { errMsg } from '../api';

const MUTED = '#94a3b8', BORDER = '#334155', ACCENT = '#a78bfa';
const Card = ({ children }) => <div style={{
  background: '#1e293b', borderRadius: 16, padding: 16,
  border: `1px solid ${BORDER}`, marginBottom: 16,
}}>{children}</div>;
const Row = ({ label, value, color }) => <div style={{
  display: 'flex', justifyContent: 'space-between', gap: 12,
  padding: '7px 0', borderBottom: `1px solid ${BORDER}`, fontSize: 13,
}}><span style={{ color: MUTED }}>{label}</span>
  <strong style={{ color:color || '#f1f5f9', textAlign:'right' }}>{value ?? '—'}</strong></div>;
const amount = n => n == null || n === '' || !Number.isFinite(Number(n))
  ? '—' : `${Number(n).toFixed(2)} USDT`;
const percent = n => n == null || !Number.isFinite(Number(n))
  ? '—' : `${(Number(n)*100).toFixed(1)}%`;
const stateText = s => ({
  paused:'In pausa', halted:'Arrestato', stale:'Dati non recenti',
  running:'Operativo', not_started:'Non avviato',
})[s] || 'Non disponibile';

export default function BrainSettingsPanel() {
  const [view,setView] = useState(null);
  const [error,setError] = useState('');
  const serial = useRef(0);
  const refresh = useCallback(async () => {
    const id = ++serial.current;
    try {
      // These are authenticated GETs. No startup, no reset, no AI invocation.
      const [overview, status, config] = await Promise.all([
        API.get('/api/v3/overview'),
        API.get('/api/v3/brain/status'),
        API.get('/api/v3/brain/config').catch(() => ({data:{available:false}})),
      ]);
      const wallet = (overview.data?.portfolios || []).find(p=>p.id==='brain');
      if (!wallet) throw new Error('Brain V3 non presente nella risposta del server');
      if (id===serial.current) {setView({wallet,status:status.data||{},config:config.data||{}});setError('');}
    } catch(e) {
      if(id===serial.current)setError(`Dati Brain non disponibili: ${errMsg(e)}`);
    }
  },[]);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh,30000);
    return () => {serial.current++; clearInterval(timer);};
  },[refresh]);
  const p=view?.wallet, s=view?.status, cfg=view?.config, risk=cfg?.risk;
  const paused=s?.paused === true || ['paused','halted'].includes(p?.state);

  return <>
    <h2 style={{fontSize:15,fontWeight:'bold',marginBottom:8,color:'#cbd5e1'}}>
      🧠 Brain — Stato e comandi
    </h2>
    <Card>
      {error && <div style={{color:'#fca5a5',fontSize:12,marginBottom:10}}>{error}</div>}
      {!view ? <div style={{color:MUTED,fontSize:13}}>Caricamento Brain…</div> : <>
        <Row label="Stato" value={stateText(p?.state)} color={paused?'#fbbf24':ACCENT}/>
        <Row label="Run" value={s?.run_id || '—'}/>
        <Row label="Capitale iniziale PAPER" value={amount(p?.start_equity)}/>
        <Row label="Equity" value={p?.equity_basis==='unavailable'?'Non disponibile':amount(p?.equity)}/>
        <Row label="P&L realizzato" value={amount(p?.realized_pnl)}/>
        <Row label="Margine in uso" value={amount(p?.margin_in_use)}/>
        <Row label="Posizioni aperte" value={p?.open_positions ?? '—'}/>
        <Row label="Trade chiusi" value={p?.total_closed ?? '—'}/>
        <Row label="Spesa DeepSeek oggi" value={s?.spend?.day == null?'Non disponibile':`${s.spend.day} USD`}/>
        <Row label="Tetto giornaliero AI" value={s?.spend?.day_limit == null?'Non disponibile':`${s.spend.day_limit} USD`}/>
        <div style={{fontSize:12,color:MUTED,marginTop:12}}>
          Modalità solo consultazione: avvio, azzeramento e modifiche del Brain sono disabilitati
          finché non è predisposto un comando PAPER autorizzato e verificato.
          Le chiusure manuali restano disponibili soltanto tramite il servizio di uscita quando abilitato.
        </div>
      </>}
    </Card>
    <h2 style={{fontSize:15,fontWeight:'bold',marginBottom:8,color:'#cbd5e1'}}>
      📐 🧠 Brain — Parametri della run
    </h2>
    <Card>
      {!cfg?.available ? <div style={{fontSize:12,color:MUTED}}>
        Parametri Brain non disponibili dall'API attuale. Nessun valore viene inventato.
      </div> : <>
        <div style={{fontSize:11,color:MUTED,marginBottom:10}}>
          Valori letti dal profilo effettivo della run, non modificabili da questa schermata.
        </div>
        <Row label="Motore AI" value={cfg.model || '—'}/>
        <Row label="Leva minima" value={risk?.min_leverage == null?'—':`${risk.min_leverage}x`}/>
        <Row label="Leva massima" value={risk?.max_leverage == null?'—':`${risk.max_leverage}x`}/>
        <Row label="Margine massimo per trade" value={percent(risk?.max_position_margin_fraction)}/>
        <Row label="Margine totale massimo" value={percent(risk?.max_total_margin_fraction)}/>
        <Row label="Rischio aggregato massimo" value={percent(risk?.max_open_risk_fraction)}/>
        <Row label="Perdita stimata / margine" value={percent(risk?.max_loss_margin_fraction)}/>
        <Row label="Protezione equity minima" value={amount(risk?.minimum_equity)}/>
        <Row label="Ciclo AI" value={cfg.cycle_minutes == null?'—':`${cfg.cycle_minutes} min`}/>
        <Row label="Budget AI massimo/giorno" value={cfg.daily_cap_usd == null?'—':`${cfg.daily_cap_usd} USD`}/>
        <div style={{fontSize:11,color:MUTED,marginTop:12}}>
          I limiti di perdita sono stime PAPER, non garanzie di chiusura esatta in mercati veloci.
        </div>
      </>}
    </Card>
  </>;
}
