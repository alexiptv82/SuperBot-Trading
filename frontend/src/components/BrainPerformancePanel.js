import React, { useCallback, useEffect, useRef, useState } from 'react';
import API, { errMsg } from '../api';
import { summarizeBrainPerformance } from '../brainPerformance';

const GOOD = '#4ade80', BAD = '#f87171', MUTED = '#94a3b8';
const BORDER = '#334155', SURF = '#1e293b', ACCENT = '#a78bfa';
const MAX_PAGES = 10, PAGE_SIZE = 200;
const Card = ({children, style}) => <div style={{
  background: SURF, borderRadius: 14, padding: 14, border: `1px solid ${BORDER}`, marginBottom: 12, ...style,
}}>{children}</div>;
const money = v => v == null || !Number.isFinite(Number(v))
  ? '—' : `${Number(v) > 0 ? '+' : ''}${Number(v).toFixed(2)} USDT`;
const moneyColor = v => v == null ? MUTED : Number(v) >= 0 ? GOOD : BAD;
const dt = ms => Number.isSafeInteger(ms)
  ? new Date(ms).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' }) : '—';
const stateLabel = s => ({
  paused: 'In pausa', halted: 'Arrestato', running: 'Operativo',
  stale: 'Non aggiornato', not_started: 'Non avviato',
})[s] || 'Non disponibile';
const Row = ({label,value,color}) => <div style={{
  display: 'flex', justifyContent: 'space-between', gap: 10, fontSize: 13,
  padding: '8px 0', borderBottom: `1px solid ${BORDER}`,
}}><span style={{color:MUTED}}>{label}</span><strong style={{color:color || '#f1f5f9',textAlign:'right'}}>{value}</strong></div>;

export default function BrainPerformancePanel() {
  const [tab, setTab] = useState('diary');
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const seq = useRef(0);
  const load = useCallback(async () => {
    const request = ++seq.current;
    setBusy(true);
    try {
      // Paging uses the genuine Brain V3 run journal; never the legacy wallet.
      const [first, ov, status] = await Promise.all([
        API.get(`/api/v3/brain/trades?limit=${PAGE_SIZE}&offset=0`),
        API.get('/api/v3/overview'),
        API.get('/api/v3/brain/status'),
      ]);
      const base = first.data || {};
      if (!Array.isArray(base.closed_trades)) throw new Error('Storico Brain non disponibile');
      const wallet = (ov.data?.portfolios || []).find(p => p.id === 'brain');
      if (!wallet) throw new Error('Portafoglio Brain V3 non disponibile');
      let trades = [...base.closed_trades];
      let more = base.has_more === true;
      for (let page = 1; more && page < MAX_PAGES; page++) {
        const result = await API.get(`/api/v3/brain/trades?limit=${PAGE_SIZE}&offset=${trades.length}`);
        const chunk = result.data?.closed_trades;
        if (!Array.isArray(chunk) || chunk.length === 0) throw new Error('Paginazione storico Brain incompleta');
        trades = trades.concat(chunk);
        more = result.data.has_more === true;
      }
      const stats = summarizeBrainPerformance(trades, base, wallet, !more);
      if (seq.current !== request) return;
      setData({stats, wallet, status:status.data || {}, partial:more || !stats.fullyLoaded});
      setError('');
    } catch (e) {
      if (seq.current === request) setError(`Impossibile caricare Brain: ${errMsg(e)}`);
    } finally {
      if (seq.current === request) setBusy(false);
    }
  }, []);
  useEffect(() => {
    load();
    const timer = setInterval(load, 120000);
    return () => {seq.current++; clearInterval(timer);};
  }, [load]);

  const s = data?.stats;
  const meta = data?.wallet;
  const status = data?.status;
  return <>
    <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:12}}>
      <div style={{fontSize:13,color:ACCENT,fontWeight:'bold'}}>🧠 Brain V3 · performance PAPER</div>
      <button onClick={load} disabled={busy} style={{
        background:'none',color:busy?MUTED:ACCENT,cursor:busy?'not-allowed':'pointer',
        border:`1px solid ${BORDER}`,borderRadius:8,padding:'6px 12px',
      }}>{busy?'...':'↻ Aggiorna'}</button>
    </div>
    {error && <Card style={{color:BAD,fontSize:13}}>{error} {data && '· Ultimi dati mantenuti a schermo.'}</Card>}
    {busy && !data && <Card style={{color:MUTED}}>Caricamento dello storico Brain…</Card>}
    {s && <>
      <div style={{fontSize:12,color:MUTED,marginBottom:12}}>
        Run {status?.run_id || 'non disponibile'} · {stateLabel(meta?.state)}.
        {data.partial ? ` Analisi dettagliata parziale: ${s.loaded} di ${s.totalClosed ?? '?'} trade caricati.` : ' Risultati della run Brain corrente, separati da Falco e Toro.'}
      </div>
      <div style={{display:'flex',flexWrap:'wrap',gap:6,marginBottom:12}}>
        {[
          ['Trade chiusi',s.totalClosed ?? '—'],
          ['Vincenti',s.winningTrades ?? '—'],
          ['Perdenti',s.losingTrades ?? '—'],
          ['Win%',s.winRate == null?'—':`${s.winRate}%`],
          ['P&L netto',money(s.totalNet)],
          ['Media/trade',money(s.avgNet)],
        ].map(([label,val])=><div key={label} style={{
          flex:'1 1 calc(33% - 6px)',minWidth:95,padding:10,background:SURF,
          border:`1px solid ${BORDER}`,borderRadius:10,textAlign:'center',
        }}><div style={{fontSize:10,color:MUTED}}>{label}</div>
          <strong style={{fontSize:14,color:label.includes('P&L')?moneyColor(s.totalNet):'#f1f5f9'}}>{val}</strong>
        </div>)}
      </div>
      <div style={{display:'flex',gap:6,marginBottom:16,background:SURF,padding:4,borderRadius:12,border:`1px solid ${BORDER}`}}>
        { [['diary','📖 Diario'],['stats','📊 Statistiche'],['runs','🧪 Run']].map(([id,label])=>
          <button key={id} onClick={()=>setTab(id)} style={{
            flex:1,padding:'10px 4px',border:0,borderRadius:10,cursor:'pointer',
            background:tab===id?ACCENT:'transparent',color:tab===id?'#0f172a':MUTED,
            fontWeight:'bold',fontSize:12,
          }}>{label}</button>)}
      </div>
      {tab==='diary' && (s.days.length===0 ?
        <Card style={{textAlign:'center',color:MUTED,padding:28}}>📭 Nessun trade Brain chiuso in questa run. Il diario apparirà alle prime chiusure PAPER.</Card>
        : s.days.map(d=><Card key={d.day}>
          <details><summary style={{cursor:'pointer',fontWeight:'bold',fontSize:14}}>
            {d.day} · {d.total_trades} trade · <span style={{color:moneyColor(d.total_pnl)}}>{money(d.total_pnl)}</span>
          </summary>
          <div style={{fontSize:12,color:MUTED,margin:'10px 0'}}>✅ {d.wins} · ❌ {d.losses}</div>
          {d.trades.map((t,i)=><Row key={t.position_id || i}
            label={`${dt(t.close_ms)} · ${t.side===1?'LONG':t.side===-1?'SHORT':'N/D'} · ${t.symbol} · ${t.close_reason||'chiusura'}`}
            value={money(t.pnl)} color={moneyColor(t.pnl)} />)}
          </details>
        </Card>))}
      {tab==='stats' && <>
        {s.totalClosed===0 && <Card style={{color:MUTED}}>Le statistiche saranno disponibili dopo i primi trade Brain chiusi.</Card>}
        {data.partial && <Card style={{color:'#fbbf24',fontSize:12}}>
          Dettagli riferiti agli ultimi {s.loaded} trade disponibili, non all'intero storico. Il totale P&L proviene dal conto Brain.
        </Card>}
        <Card>
          <div style={{fontWeight:'bold',marginBottom:8}}>📐 Qualità dei trade</div>
          <Row label="Profit factor" value={s.profitFactor ?? '—'} />
          <Row label="Miglior trade" value={money(s.best)} color={GOOD}/>
          <Row label="Peggior trade" value={money(s.worst)} color={BAD}/>
          <Row label="Commissioni registrate" value={s.totalFees == null?'—':`${s.totalFees.toFixed(2)} USDT`}/>
          <Row label="Max drawdown" value="Non disponibile per questa run" />
        </Card>
        {[
          ['💱 Per asset',s.assets],
          ['↕️ Long / Short',s.sides],
          ['🎯 Motivo di chiusura',s.reasons],
        ].map(([title,items]) => items.length > 0 && <Card key={title}>
          <div style={{fontWeight:'bold',marginBottom:8}}>{title}</div>
          {items.map(([label,group])=><Row key={label}
            label={`${label} · ${group.trades} trade · ${group.wins} win`}
            value={money(group.net_pnl)} color={moneyColor(group.net_pnl)}/>)}
        </Card>)}
        <div style={{fontSize:11,color:MUTED,textAlign:'center'}}>
          P&L realizzato dal journal Brain, senza sommare utili/perdite latenti.
        </div>
      </>}
      {tab==='runs' && <Card>
        <div style={{fontWeight:'bold',marginBottom:10}}>🧠 Run Brain corrente</div>
        <Row label="Identificativo" value={status?.run_id || '—'} />
        <Row label="Stato" value={stateLabel(meta?.state)} />
        <Row label="Capitale iniziale" value={meta?.start_equity==null?'—':`${Number(meta.start_equity).toFixed(2)} USDT`}/>
        <Row label="Equity" value={meta?.equity_basis==='unavailable'?'Non disponibile':meta?.equity==null?'—':`${Number(meta.equity).toFixed(2)} USDT`} />
        <Row label="Posizioni aperte" value={meta?.open_positions ?? '—'} />
        <Row label="Ultima decisione" value={status?.last_decision?.kind || 'Nessuna'} />
        <Row label="Spesa AI oggi" value={status?.spend?.day == null?'—':`${status.spend.day} USD`} />
        <Row label="Limite AI giornaliero" value={status?.spend?.day_limit == null?'—':`${status.spend.day_limit} USD`} />
        <div style={{fontSize:12,color:MUTED,marginTop:12}}>
          Le run precedenti di Brain non sono esposte dall'API corrente: non vengono mescolate con le run storiche di Falco e Toro.
          Le impostazioni della run attuale sono nella sezione Impostazioni.
        </div>
      </Card>}
    </>}
  </>;
}
