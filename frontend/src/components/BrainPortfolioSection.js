import React from 'react';
import { BrainCloseControls, PortfolioTradeFields } from './OverviewCloseControls';
import { signed, pnlColor } from '../deskUi';

const card = { background:'#1e293b', borderRadius:16, padding:16, border:'1px solid #334155' };
const value = (v, decimals=2) => v == null || !Number.isFinite(Number(v))
  ? '—' : '$' + Number(v).toFixed(decimals);
const total = v => v == null ? '—' : signed(v) + '$';

export default function BrainPortfolioSection({ wallet, rawTrades, readOnly, onRefresh }) {
  if (!wallet) return <div style={{ ...card, marginBottom:16, color:'#94a3b8' }}>
    Brain V3: dati del portafoglio non disponibili.
  </div>;
  const nOpen = wallet.positions.length;
  const tone = wallet.pnl_total == null ? '#e2e8f0' : pnlColor(wallet.pnl_total);
  const stateLabel = {
    running:'In funzione', paused:'In pausa', halted:'Fermo',
    stale:'Segnale assente', not_started:'Non avviato'
  }[wallet.state] || 'Stato non disponibile';

  return <div data-testid="brain-classic-wallet">
    <div style={{ ...card, textAlign:'center', marginBottom:12, borderColor:tone+'55' }}>
      <div style={{ color:'#64748b', textTransform:'uppercase', fontSize:11, letterSpacing:'.05em' }}>
        Equity — 🧠 Brain · PAPER
      </div>
      <div style={{ fontSize:36, fontWeight:'bold', color:tone }}>{value(wallet.equity)}</div>
      <div style={{ color:tone, fontWeight:'bold', fontSize:13 }}>
        P&L realizzato {total(wallet.pnl_total)}
        {wallet.pnl_total_pct != null && ' (' + signed(wallet.pnl_total_pct) + '%)'}
        {wallet.start_equity != null && ' da ' + value(wallet.start_equity,0)}
      </div>
      <div style={{ display:'flex', flexWrap:'wrap', justifyContent:'center', gap:14,
        marginTop:8, fontSize:12, color:'#94a3b8' }}>
        <span>Cassa <strong style={{color:'#cbd5e1'}}>{value(wallet.cash)}</strong></span>
        <span>Margine <strong style={{color:'#cbd5e1'}}>{value(wallet.margin_used,0)}</strong></span>
        <span>Aperto <strong style={{color:pnlColor(wallet.unrealized_pnl)}}>{total(wallet.unrealized_pnl)}</strong></span>
        <span>Oggi <strong style={{color:pnlColor(wallet.day_pnl)}}>{total(wallet.day_pnl)}</strong></span>
      </div>
      {wallet.settled_equity != null && <p style={{ color:'#94a3b8', fontSize:11 }}>
        Saldo PAPER contabile: {value(wallet.settled_equity)}
        {wallet.equity_basis === 'open_unmarked' && ' (escluso P&L aperto)'}
      </p>}
      {wallet.equity == null && <div style={{ color:'#fbbf24', marginTop:6, fontSize:11 }}>
        Equity non verificabile finché mancano prezzi attendibili o dati della run.
      </div>}
    </div>

    <div style={{display:'flex',gap:8,marginBottom:12}}>
      {[
        ['Aperte', nOpen, '#38bdf8'],
        ['Chiuse', wallet.total_closed, '#e2e8f0'],
        ['Budget AI', wallet.spend?.today_usd == null ? '—' : value(wallet.spend.today_usd,3), '#4ade80']
      ].map(([label,metric,color]) => <div key={label} style={{...card,flex:1,
        padding:'12px 7px',textAlign:'center'}}>
        <div style={{color:'#64748b',fontSize:10}}>{label}</div>
        <div style={{fontWeight:'bold',fontSize:label==='Budget AI'?17:24,color}}>
          {metric == null ? '—' : metric}{label === 'Aperte' && <span style={{fontSize:12,color:'#475569'}}>
            /{wallet.max_open ?? '—'}</span>}
        </div>
      </div>)}
    </div>

    <div style={{...card,borderColor:'#a78bfa',background:'#a78bfa14',marginBottom:12}}>
      <strong style={{color:'#c4b5fd'}}>🧠 Brain · {stateLabel}</strong>
      <div style={{fontSize:12,color:'#94a3b8',marginTop:5}}>
        Portafoglio autonomo e separato da Falco e Toro.
      </div>
      {readOnly && <div style={{fontSize:12,color:'#fbbf24',marginTop:6}}>
        {wallet.manual_close_allowed
          ? 'Solo chiusura manuale singola PAPER consentita; nuove aperture e pausa/ripresa restano bloccate.'
          : 'Collaudo PAPER in sola lettura: apertura, pausa e chiusure disabilitate.'}
      </div>}
    </div>

    <div style={{display:'flex',gap:8,marginBottom:12}}>
      {['▶ Avvia / Riprendi','⏸ Pausa'].map(label => <button key={label}
        type="button" disabled style={{flex:1,padding:12,borderRadius:10,
          border:'1px solid #334155',background:'#0f172a',color:'#64748b',
          fontWeight:'bold'}}>{label}</button>)}
    </div>
    <h2 style={{color:'#cbd5e1',fontSize:15,marginBottom:8}}>⚡ Posizioni Aperte</h2>
    {nOpen === 0 && <div style={{...card,marginBottom:12,color:'#94a3b8'}}>
      Nessuna posizione aperta nella run Brain V3.
    </div>}
    {nOpen > 0 && <BrainCloseControls positions={rawTrades?.open_positions || []}
      readOnly={readOnly && !wallet.manual_close_allowed} allowCloseAll={!readOnly}
      serverPending={rawTrades?.close_pending === true}
      onRefresh={onRefresh} renderPosition={pos => <PortfolioTradeFields p={pos} brain />} />}

    <details style={{ marginTop:14, marginBottom:14 }}>
      <summary style={{ color:'#7dd3fc', cursor:'pointer',fontSize:13,fontWeight:'bold' }}>
        🧠 Analisi, osservazioni e memoria AI
      </summary>
      <div style={{...card,marginTop:8,fontSize:12,color:'#cbd5e1'}}>
        <div>Ultima decisione: {wallet.last_decision?.kind || 'Nessuna decisione disponibile'}</div>
        <div>Strategia: {wallet.last_decision?.strategy_id || '—'}</div>
        <div>Osservazioni classici consultate: {
          (wallet.last_decision?.peer_observations_used || []).join(', ') || 'nessuna'
        }</div>
        <div style={{marginTop:7,color:'#94a3b8'}}>
          Il Brain non copia automaticamente le operazioni degli altri portafogli.
        </div>
        <div style={{marginTop:9}}><a href="/overview" style={{color:'#7dd3fc'}}>
          Dettagli AI e apprendimento nella panoramica V3</a></div>
        <div style={{marginTop:7}}><a href="/brain/archive" style={{color:'#94a3b8'}}>
          Archivio Brain precedenti</a></div>
      </div>
    </details>
  </div>;
}
