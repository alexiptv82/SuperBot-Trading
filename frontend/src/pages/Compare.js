import React, { useEffect, useState } from 'react';
import API from '../api';
import { BrainCloseControls } from '../components/OverviewCloseControls';

// Confronto PAPER Falco Evoluto / Brain Scalp (sola lettura, /api/v3/compare). Stessa grafica dei Classici.
// Ogni numero arriva dal journal della SUA run; quello che manca resta "—" (mai valori inventati).
const num = v => (v === null || v === undefined || v === '' || !Number.isFinite(Number(v)) ? null : Number(v));
const usd = (v, d = 2) => (num(v) === null ? '—' : `${num(v) < 0 ? '-' : ''}$${Math.abs(num(v)).toFixed(d)}`);
const pct = v => (num(v) === null ? '—' : `${num(v) > 0 ? '+' : ''}${num(v).toFixed(2)}%`);
const tone = v => (num(v) === null ? '#94a3b8' : num(v) > 0 ? '#4ade80' : num(v) < 0 ? '#f87171' : '#94a3b8');
const MUTED = { color: '#94a3b8', fontSize: 12 };
const own = (t, k) => (typeof k === 'string' && Object.prototype.hasOwnProperty.call(t, k) ? t[k] : undefined);

const GUARDIAN = {
  NORMAL: ['Normale', '#4ade80'], SELECTIVE: ['Selettivo', '#38bdf8'],
  PROTECTED: ['Protetto', '#fbbf24'], LOCKED: ['Bloccato', '#f87171'],
};
const REASON = {
  falco_no_trade_regime: 'nessun trade: mercato laterale, incerto o shock',
  falco_no_trade_score: 'nessun trade: segnale insufficiente',
  falco_no_trade_conflict: 'nessun trade: segnali contrastanti',
  falco_no_trade_data: 'nessun trade: dati insufficienti',
  falco_ai_no_trade: 'nessun trade: l’AI consultata non conferma',
  falco_ai_unavailable: 'nessun trade: AI non disponibile',
  falco_short_signal: 'SHORT dalle regole', falco_long_signal: 'LONG dalle regole',
  'deepseek:analysis': 'decisione DeepSeek', risk_rejected: 'rifiutata dal rischio', risk_quote_ok: 'approvata',
  policy_not_authorized: 'mandato non approvato', market_gate: 'mercato non idoneo',
};
const RISK = {
  below_min_margin: 'margine sotto il minimo', margin_loss_ratio_exceeded: 'stop troppo largo per la leva minima',
  stop_near_liquidation: 'stop troppo vicino alla liquidazione', max_positions_reached: 'posizioni al massimo',
  guardian_budget_exhausted: 'budget del Guardian esaurito', risk_budget_exhausted: 'rischio disponibile esaurito',
  margin_budget_exhausted: 'margine disponibile esaurito', equity_floor_reached: 'equity al minimo',
};

function Card({ children, style, ...rest }) {
  return <div {...rest} style={{ background: '#1e293b', borderRadius: 16, padding: 14, border: '1px solid #334155',
    marginBottom: 12, ...style }}>{children}</div>;
}

function rows(runs) {
  const g = r => r.guardian || {};
  const sessionPnl = r => (num(g(r).equity) !== null && num(g(r).session_start_equity) !== null
    ? num(g(r).equity) - num(g(r).session_start_equity) : null);
  return [
    ['Capitale', r => usd(r.initial_equity, 0)],
    ['Equity contabile', r => usd(r.settled_equity)],
    ['P&L trading (netto commissioni)', r => <span style={{ color: tone(r.net_pnl) }}>{usd(r.net_pnl)}</span>],
    ['Rendimento trading', r => <strong style={{ color: tone(r.return_pct) }}>{pct(r.return_pct)}</strong>],
    ['Spesa AI totale', r => usd(r.ai_cost_total, 3)],
    ['Risultato dopo AI', r => <strong style={{ color: tone(r.net_after_ai) }}>
      {usd(r.net_after_ai)}{num(r.return_after_ai_pct) === null ? '' : ` (${pct(r.return_after_ai_pct)})`}</strong>],
    ['Drawdown trade chiusi', r => `${num(r.max_drawdown_pct) === null ? '—' : `-${num(r.max_drawdown_pct).toFixed(2)}%`} (${usd(r.max_drawdown)})`],
    ['Drawdown a mercato', r => (num(r.mtm_drawdown_pct) === null ? 'non disponibile'
      : `-${num(r.mtm_drawdown_pct).toFixed(2)}% (${usd(r.mtm_drawdown)})${r.mtm_incomplete ? ' · feed incompleto' : ''}`)],
    ['Profit factor', r => r.profit_factor ?? '—'],
    ['Win rate', r => (r.win_rate == null ? '—' : `${r.win_rate}% (${r.wins}/${r.losses})`)],
    ['LONG', r => `${r.by_side?.long?.trades ?? 0} · ${usd(r.by_side?.long?.net_pnl)}`],
    ['SHORT', r => `${r.by_side?.short?.trades ?? 0} · ${usd(r.by_side?.short?.net_pnl)}`],
    ['Guardian', r => { const s = own(GUARDIAN, g(r).state); return s ? <strong style={{ color: s[1] }}>{s[0]}</strong> : '—'; }],
    ['Sessione', r => <span style={{ color: tone(sessionPnl(r)) }}>{usd(sessionPnl(r))}</span>],
    ['Picco / giveback', r => `${usd(g(r).peak_equity)} / ${usd(g(r).giveback)}`],
    ['Rischio residuo', r => usd(g(r).budget)],
    ['Tetto nuova apertura', r => (g(r).state === 'NORMAL' ? 'limiti ordinari' : usd(g(r).risk_cap))],
    ['Posizioni aperte', r => `${(r.open_positions || []).length} / ${r.config?.max_positions ?? '—'}`],
    ['Chiusure manuali', r => r.manual_closes ?? '—'],
    ['Stop protettivi', r => r.protected_stops ?? '—'],
    ['Spesa AI oggi', r => `${usd(r.ai_spend?.day, 3)} / ${usd(r.config?.daily_cap_usd)}`],
    ['Leva · margine', r => `${(r.config?.leverage || []).join('–')}× · $${(r.config?.margin || []).join('–')}`],
  ];
}

export function CompareContent({ data, onRefresh = () => {} }) {
  if (!data?.available) {
    return <Card><strong>Confronto non ancora attivo</strong>
      <p style={MUTED}>Le due run PAPER (Falco Evoluto e Brain Scalp) non sono ancora state preparate e approvate.
        Nessun dato viene mostrato finché non esistono i loro journal.</p></Card>;
  }
  const runs = data.runs || [];
  const live = runs.filter(r => r.available);
  return <>
    <Card style={{ padding: 0, overflow: 'hidden' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, tableLayout: 'fixed' }}>
        <thead><tr style={{ background: '#0f172a' }}>
          <th style={{ textAlign: 'left', padding: '10px 8px', color: '#64748b', width: '34%' }}>PAPER</th>
          {runs.map(r => <th key={r.name} style={{ textAlign: 'right', padding: '10px 8px', color: '#cbd5e1' }}>{r.label}</th>)}
        </tr></thead>
        <tbody>
          {rows(runs).map(([label, cell]) => <tr key={label} style={{ borderTop: '1px solid #273449' }}>
            <td style={{ padding: '7px 8px', color: '#94a3b8' }}>{label}</td>
            {runs.map(r => <td key={r.name} style={{ padding: '7px 8px', textAlign: 'right', overflowWrap: 'anywhere' }}>
              {r.available ? cell(r) : <span style={MUTED}>{r.reason === 'not_started' ? 'non avviato' : 'non preparato'}</span>}
            </td>)}
          </tr>)}
        </tbody>
      </table>
    </Card>
    <p style={{ ...MUTED, fontSize: 11 }}>Il P&L di trading include commissioni e slippage, non i costi AI: il risultato
      dopo AI li sottrae una sola volta. Il drawdown a mercato usa solo le equity registrate dal Guardian a ogni giro
      con prezzi verificati (campioni, non ogni minuto); senza campioni resta non disponibile. Il Guardian mostra
      l’equity a mercato della sessione (dalle 08:00). Il floor del Guardian limita le nuove aperture: non garantisce il
      profitto finale né protegge le posizioni già aperte.</p>
    {live.map(r => <Card key={r.name} aria-label={`Dettaglio ${r.label}`}>
      <strong>{r.label}</strong>
      <div style={{ ...MUTED, marginTop: 4 }}>{(own(GUARDIAN, r.guardian?.state) || ['Guardian non disponibile'])[0]}
        {(r.guardian?.reasons || []).length ? ` · ${r.guardian.reasons.join(', ')}` : ''}</div>
      <div style={{ marginTop: 8, fontSize: 13, fontWeight: 700, color: '#cbd5e1' }}>Posizioni aperte</div>
      {(r.open_positions || []).length === 0 && <div style={MUTED}>Nessuna posizione aperta.</div>}
      <BrainCloseControls positions={r.open_positions || []} allowCloseAll={false}
        readOnly={r.manual_close_allowed !== true} serverPending={r.close_pending === true} onRefresh={onRefresh}
        closeUrl={`/api/v3/compare/${r.name}/close`} resultUrl={`/api/v3/compare/${r.name}/close-result`}
        itemStyle={{ padding: '6px 0', borderTop: '1px solid #273449' }}
        closeLabel={p => `Chiudi ${p.symbol} (PAPER)`}
        renderPosition={p => <div style={{ ...MUTED }}>
          <strong style={{ color: p.side === 1 ? '#4ade80' : '#f87171' }}>{p.side === 1 ? 'LONG' : 'SHORT'}</strong>{' '}
          {String(p.symbol).replace('USDT', '')} x{p.leverage} · ingresso ${p.entry} · stop ${p.stop} · margine {usd(p.margin, 0)}
        </div>} />
      {(r.open_positions || []).length > 0 && r.manual_close_allowed !== true && <div style={{ ...MUTED, fontSize: 11 }}>
        Chiusura manuale non disponibile finché il servizio uscite di questo portafoglio non è sano.</div>}
      <div style={{ marginTop: 8, fontSize: 13, fontWeight: 700, color: '#cbd5e1' }}>Ultime decisioni</div>
      {(r.decisions || []).length === 0 && <div style={MUTED}>Nessuna decisione registrata.</div>}
      {(r.decisions || []).map((d, i) => <div key={`${d.ts_ms}-${i}`} style={{ ...MUTED, padding: '3px 0' }}>
        {d.symbol || '—'} · {own(REASON, d.rationale) || d.kind || '—'}{d.risk_reason ? ` · ${own(RISK, d.risk_reason) || 'limite di rischio'}` : ''}
      </div>)}
    </Card>)}
  </>;
}

export default function Compare() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const { data: d } = await API.get('/api/v3/compare');
        if (alive) { setData(d); setError(false); }
      } catch (e) {
        if (alive) setError(true);
      }
    };
    load();
    const t = setInterval(load, 30000);
    return () => { alive = false; clearInterval(t); };
  }, [tick]);
  return <div style={{ padding: 16, maxWidth: 600, margin: '0 auto', boxSizing: 'border-box' }}>
    <h1 style={{ fontSize: 22, fontWeight: 'bold', margin: 0, background: 'linear-gradient(90deg, #f1f5f9, #38bdf8)',
      WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>⚖️ Confronto</h1>
    <div style={{ fontSize: 10, color: '#a78bfa', fontWeight: 700, letterSpacing: '0.08em', margin: '3px 0 12px' }}>
      ○ PAPER MODE · Falco Evoluto vs Brain Scalp · soldi simulati</div>
    {error && <p role="alert" style={{ color: '#fda4af', fontSize: 13 }}>Confronto non disponibile: verifica la connessione o la sessione.</p>}
    {!error && data === null && <p role="status" style={MUTED}>Caricamento…</p>}
    {!error && data !== null && <CompareContent data={data} onRefresh={() => setTick(n => n + 1)} />}
  </div>;
}
