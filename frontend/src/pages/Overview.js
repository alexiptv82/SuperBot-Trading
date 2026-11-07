/** Unified PAPER overview: read-only metrics plus authenticated close requests. */
import React, { useCallback, useEffect, useState } from 'react';

import API from '../api';
import { BrainCloseControls, ClassicCloseControls, PortfolioTradeFields } from '../components/OverviewCloseControls';

const PALETTE = { running: '#34d399', paused: '#fbbf24', halted: '#fb7185', stale: '#fbbf24', not_started: '#94a3b8' };
const STATE_TEXT = { running: 'In funzione', paused: 'In pausa', halted: 'Fermo', stale: 'Segnale assente', not_started: 'Non avviato' };
const VERDICTS = { positive: ['Positivo', '#34d399'], negative: ['Negativo', '#fb7185'], inconclusive: ['Inconcludente', '#fbbf24'], insufficient: ['Dati insufficienti', '#94a3b8'] };
const BLOCK = { background: '#172338', border: '1px solid #2f425b', borderRadius: 16, padding: 16, marginBottom: 12 };
const MUTED = { color: '#a8bacd', fontSize: 12 };

const money = value => value === null || value === undefined ? '—' : `${value} USDT`;
const bp = value => value === null || value === undefined ? '—' : `${value} bp`;
const field = value => value === null || value === undefined || value === '' ? '—' : value;
const pnlColor = value => value === null || value === undefined ? '#a8bacd' : String(value).startsWith('-') ? '#fda4af' : '#4ade80';
const detailBox = { padding: '10px 11px', background: '#0e1a2d', borderRadius: 10, border: '1px solid #30465e' };
const amountUsd = value => value === null || value === undefined ? '—' : `$${value}`;
const direction = side => side === 1 ? 'LONG' : side === -1 ? 'SHORT' : '—';
// Only Brain trade exit reasons are translated; unknown codes never reach the UI.
const EXIT_REASONS = Object.freeze({
  stop: 'stop', take_profit: 'obiettivo raggiunto',
  timeout: 'tempo scaduto', manual: 'chiusa da te',
  brain_close: 'chiusa dal Brain', liquidation: 'liquidata',
});
export const brainExitReason = reason => (
  typeof reason === 'string' && Object.prototype.hasOwnProperty.call(EXIT_REASONS, reason)
    ? EXIT_REASONS[reason] : 'altro'
);
const ageText = (ts, nowMs) => {
  if (!Number.isInteger(ts) || ts <= 0) return 'Mai';
  const seconds = Math.max(0, Math.floor((nowMs - ts) / 1000));
  return seconds < 60 ? `${seconds} s fa` : `${Math.floor(seconds / 60)} min fa`;
};
const reasonText = code => {
  if (!code || typeof code !== 'string') return null;
  if (/(?:^|;)(?:halted:)?(?:no_mandate|mandate_not_approved|mandate_invalid|mandate_mismatch)(?:;|$)/.test(code)) {
    return 'In attesa del mandato dell’utente';
  }
  if (/(?:^|;)(?:halted:)?(?:budget|ledger_error)(?:;|$)/.test(code)) {
    return 'Tetto di spesa raggiunto';
  }
  return 'Verificare lo stato del Brain';
};

/** Identical closed-trade presentation across Falco, Toro and Brain; AI metadata is additive. */
function ClosedTradeDetails({ t, brain = false, nowMs }) {
  const reason = brain ? brainExitReason(t.exit_reason) : field(t.close_reason);
  return <div style={{ padding:'10px 0', borderBottom:'1px solid #314357' }}>
    <strong>{t.symbol} · {direction(t.side)} · {field(t.leverage)}×
      {brain && t.strategy_id ? ` · ${t.strategy_id}` : null}</strong>
    <div style={{ ...MUTED, color:pnlColor(t.realized_pnl) }}>
      P&L netto {money(t.realized_pnl)}{brain && t.net_bp != null ? ` · ${bp(t.net_bp)}` : ''}
    </div>
    <div style={MUTED}>Entrata {field(t.entry)} · Uscita {field(t.exit)} · Margine {money(t.margin)}</div>
    <div style={MUTED}>{t.partial ? 'Chiusura parziale · ' : ''}{reason} · {ageText(t.closed_at_ms, nowMs)}</div>
    {brain && <div style={MUTED}>
      {t.regime || 'Regime sconosciuto'} · Commissioni {money(t.fees)} · Durata {t.hold_ms == null ? '—' : `${Math.round(t.hold_ms / 60000)} min`}
    </div>}
    {t.manual_learning === 'profit_protection_example' &&
      <div style={{ ...MUTED, color:'#4ade80' }}>Profitto protetto manualmente · esempio per AI, non strategia convalidata</div>}
    {t.manual_learning === 'loss_reduction_example' && <div style={MUTED}>Uscita manuale in perdita · esempio per AI</div>}
  </div>;
}

function StateLabel({ state }) {
  return <span style={{ color: PALETTE[state] || '#94a3b8', fontWeight: 700, fontSize: 13 }}>
    <span aria-hidden="true">● </span>{STATE_TEXT[state] || 'Non disponibile'}
  </span>;
}

export function OverviewContent({ overview, status, scoreboard, trades, nowMs = Date.now(), regime, onRegime, onRefresh = () => {} }) {
  if (!overview) return <section role="status" style={BLOCK}>Nessun dato disponibile.</section>;
  const portfolios = overview.portfolios || [];
  const regimes = scoreboard?.regimes || [];
  const shownRegime = regimes.find(r => r.regime === regime) || regimes[0];
  const stoppedReason = status?.state === 'halted' ? reasonText(status?.heartbeat?.last_error) : null;
  const openPositions = trades?.open_positions || [];
  const closedTrades = (trades?.closed_trades || []).slice(0, 20);
  const brainUnrealized = !openPositions.length ? '0' :
    openPositions.every(p => p.unrealized_pnl !== null && p.unrealized_pnl !== undefined)
      ? openPositions.reduce((sum, p) => sum + Number(p.unrealized_pnl), 0).toFixed(2) : null;
  const portfolioNames = { falco: '🦅 Falco', toro: '🐂 Toro', brain: '🧠 Brain V3' };
  const actualPeerSources = Array.isArray(status?.last_decision?.peer_observations_used)
    ? status.last_decision.peer_observations_used.filter(x => x === 'falco' || x === 'toro')
    : [];
  return <main style={{ background: '#0b1323', color: '#eef5ff', minHeight: '100vh', padding: '16px 12px 92px', maxWidth: 1200, margin: '0 auto', boxSizing: 'border-box', fontFamily: 'system-ui, sans-serif' }}>
    <header style={{ marginBottom: 18 }}>
      <div style={{ color: '#7dd3fc', fontSize: 11, fontWeight: 800, letterSpacing: 2 }}>SUPERBOT V3 · PAPER</div>
      <h1 style={{ fontSize: 25, margin: '6px 0' }}>I tre portafogli</h1>
      <div style={MUTED}>Monitoraggio · Ultimo aggiornamento {ageText(overview.generated_at_ms, nowMs)}</div>
    </header>
    <section aria-label="Portafogli" style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(min(100%, 280px), 1fr))', gap:12, alignItems:'start', marginBottom:14 }}>
      {portfolios.map(p => <article key={p.id} data-testid={`portfolio-${p.id}`} aria-label={`Portafoglio ${p.id}`} style={{ ...BLOCK, marginBottom:0, borderTop: `3px solid ${p.id === 'falco' ? '#38bdf8' : p.id === 'toro' ? '#fbbf24' : '#a78bfa'}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
          <strong style={{ fontSize: 18 }}>{portfolioNames[p.id] || p.id}</strong>
          <StateLabel state={p.state} />
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:9, marginTop:14 }}>
          <div style={detailBox}><div style={MUTED}>Posizioni aperte</div><strong>{p.open_positions ?? '—'}</strong></div>
          <div style={detailBox}><div style={MUTED}>P&L realizzato</div><strong style={{ color:pnlColor(p.realized_pnl) }}>{p.state === 'not_started' ? '—' : money(p.realized_pnl)}</strong></div>
          <div style={detailBox}><div style={MUTED}>Margine in uso</div><strong>{p.state === 'not_started' ? '—' : money(p.margin_in_use)}</strong></div>
          <div style={detailBox}><div style={MUTED}>P&L aperto</div><strong style={{ color:pnlColor(p.id === 'brain' ? brainUnrealized : p.unrealized_pnl) }}>{p.state === 'not_started' ? '—' : money(p.id === 'brain' ? brainUnrealized : p.unrealized_pnl)}</strong></div>
          <div style={detailBox}><div style={MUTED}>Equity</div><strong>{p.state === 'not_started' ? '—' : money(p.equity)}</strong>
            {p.id === 'brain' && p.equity_basis === 'open_unmarked' && <div style={MUTED}>Non calcolabile senza prezzi verificati delle posizioni aperte.</div>}
          </div>
          <div style={detailBox}><div style={MUTED}>Profitto di oggi{p.id === 'brain' ? ' (realizzato, UTC)' : ''}</div>
            <strong style={{ color:pnlColor(p.day_pnl) }}>{p.state === 'not_started' ? '—' : money(p.day_pnl)}</strong>
          </div>
          <div style={detailBox}><div style={MUTED}>Trade chiusi</div><strong>{p.total_closed ?? 0}</strong></div>
          <div style={detailBox}><div style={MUTED}>Win rate</div><strong>{p.win_rate == null ? '—' : `${p.win_rate}%`}</strong></div>
          <div style={{ gridColumn:'1 / -1', ...MUTED }}>Ultimo evento: {ageText(p.last_event_ms, nowMs)}</div>
        </div>
        {p.id === 'brain' && p.settled_equity != null && <p style={{ ...MUTED, marginTop:9 }}>
          Saldo PAPER contabile (capitale iniziale + trade chiusi): <strong>{money(p.settled_equity)}</strong>
          {p.equity_basis === 'open_unmarked' ? ' · escluso P&L aperto' : ''}
        </p>}
        {p.id === 'brain' && stoppedReason && <p style={{ color: '#fda4af', fontSize: 13 }}>{stoppedReason}</p>}
        {p.kind === 'classic' && <>
          <h3 style={{ fontSize:14, margin:'17px 0 8px' }}>Trade aperti · {p.id === 'falco' ? 'Falco' : 'Toro'}</h3>
          {p.close_worker_mode === 'exit_only' && <div style={{ ...MUTED, color: '#7dd3fc', marginBottom: 8 }}>
            Modalità solo chiusure PAPER · nessun nuovo ingresso</div>}
          <ClassicCloseControls portfolio={p.id} positions={p.positions || []}
            canClose={p.can_close_position === true && (overview.cutover_readonly !== true || overview.classic_single_close_allowed === true)}
            allowCloseAll={overview.cutover_readonly !== true} pending={p.close_pending || []}
            allPending={p.close_all_pending === true} lastAction={p.last_action}
            onRefresh={onRefresh} />
          <details style={{ marginTop:14 }}>
            <summary style={{ color:'#7dd3fc', cursor:'pointer', fontWeight:700, fontSize:13 }}>Ultimi trade chiusi ({(p.closed_trades || []).length})</summary>
            {(p.closed_trades || []).length === 0 && <p style={MUTED}>Ancora nessun trade chiuso nella nuova run.</p>}
            {(p.closed_trades || []).map((t, i) => <ClosedTradeDetails key={`${t.symbol}-${t.closed_at_ms}-${i}`} t={t} nowMs={nowMs} />)}
          </details>
          <a href="/classic" style={{ display:'inline-block', color:'#7dd3fc', fontSize:12, marginTop:13 }}>Apri la dashboard classica completa</a>
        </>}
        {p.id === 'brain' && <>
          <h3 style={{ fontSize:14, margin:'17px 0 8px' }}>Trade aperti · Brain</h3>
          {openPositions.length === 0 && <p style={MUTED}>Nessuna posizione aperta.</p>}
          <BrainCloseControls positions={openPositions} readOnly={overview.cutover_readonly === true} serverPending={trades?.close_pending === true}
            onRefresh={onRefresh} renderPosition={pos => <PortfolioTradeFields p={pos} brain />} />
          <details style={{ marginTop:14 }}>
            <summary style={{ color:'#7dd3fc', cursor:'pointer', fontWeight:700, fontSize:13 }}>
              Ultimi 20 trade chiusi · Brain ({closedTrades.length})
            </summary>
            {closedTrades.length === 0 && <p style={MUTED}>Nessun trade chiuso disponibile.</p>}
            {closedTrades.map((t,i) => <ClosedTradeDetails key={`${t.position_id || t.symbol}-${i}`} t={t} brain nowMs={nowMs} />)}
          </details>
        </>}
      </article>)}
    </section>
    <section style={BLOCK} aria-label="Osservazioni Falco e Toro">
      <h2 style={{ fontSize:17, marginTop:0 }}>Brain · osservazioni Falco e Toro</h2>
      <p style={MUTED}>Confronto informativo in sola lettura. Questi dati non sono ancora collegati alle decisioni automatiche del Brain.</p>
      {(portfolios.find(p => p.id === 'brain')?.peer_observations || []).map(peer =>
        <div key={peer.portfolio_id} style={{ padding:'9px 0', borderTop:'1px solid #314357', ...MUTED }}>
          <strong>{peer.portfolio_id === 'falco' ? '🦅 Falco' : '🐂 Toro'}</strong>
          {' · '}Stato {STATE_TEXT[peer.state] || 'Non disponibile'} · Aperte {peer.open_positions ?? '—'}
          {' · '}P&L oggi {peer.day_pnl == null ? '—' : money(peer.day_pnl)}
        </div>)}
      {!(portfolios.find(p => p.id === 'brain')?.peer_observations || []).length &&
        <p style={MUTED}>Dati di osservazione non ancora disponibili.</p>}
    </section>
    <section style={BLOCK} aria-label="Stato Brain">
      <h2 style={{ fontSize: 17, marginTop: 0 }}>🧠 Brain · come lavora</h2>
      {status?.state === 'not_started' ? <p style={MUTED}>Brain non ancora avviato: nessuna decisione disponibile.</p> : <>
        <div style={MUTED}>Regime · Ultima decisione</div>
        <div style={{ fontWeight: 700, margin: '5px 0 12px' }}>{status?.regime || 'Non disponibile'} · {status?.last_decision?.kind || 'Nessuna'}</div>
        {status?.last_decision && <div style={MUTED}>{status.last_decision.symbol || '—'} · {status.last_decision.strategy_id || 'Senza strategia dichiarata'} · {status.last_decision.status || '—'}</div>}
        {status?.last_decision && <div style={{ ...MUTED, marginTop:7 }}>
          Osservazioni classici usate nell'ultima decisione: {
            actualPeerSources.length
              ? actualPeerSources.map(x => x === 'falco' ? 'Falco' : 'Toro').join(', ')
              : 'nessuna o non disponibile'}
        </div>}
      </>}
      <div style={{ borderTop: '1px solid #314357', marginTop: 12, paddingTop: 12 }}>
        <div style={MUTED}>Spesa DeepSeek oggi / tetto giornaliero</div>
        <strong>{amountUsd(status?.spend?.day)} / {amountUsd(status?.spend?.day_limit)}</strong>
        <div style={{ ...MUTED, marginTop: 5 }}>Mese: {amountUsd(status?.spend?.month)}</div>
      </div>
    </section>
    <section style={BLOCK} aria-label="Apprendimento Brain">
      <h2 style={{ fontSize: 17, margin: '0 0 10px' }}>📈 Risultati per strategia</h2>
      {regimes.length === 0 ? <p style={MUTED}>Non ci sono ancora risultati attribuibili alle strategie.</p> : <>
        <label htmlFor="regime-select" style={MUTED}>Regime analizzato</label>
        <select id="regime-select" value={shownRegime.regime} onChange={e => onRegime(e.target.value)}
          style={{ display: 'block', width: '100%', margin: '6px 0 14px', padding: '10px', borderRadius: 9, color: '#e0f2fe', background: '#263750', border: '1px solid #4b617b' }}>
          {regimes.map(r => <option key={r.regime} value={r.regime}>{r.regime}</option>)}
        </select>
        <div style={{ ...MUTED, marginBottom: 10 }}>Esiti collegati: {shownRegime.n_closed_linked} · Etichettati: {shownRegime.n_labelled}</div>
        {shownRegime.cells?.length === 0 && <p style={MUTED}>Nessuna strategia ancora misurata in questo regime.</p>}
        {shownRegime.cells?.map((c, i) => <div key={`${c.strategy_id}-${c.origin}-${c.side}-${i}`} style={{ padding: '12px 0', borderTop: '1px solid #314357' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <strong>{c.strategy_id} · {direction(c.side)}</strong>
            <span style={{ color: VERDICTS[c.status]?.[1] || '#94a3b8', fontSize: 12 }}>{VERDICTS[c.status]?.[0] || c.status}</span>
          </div>
          <div style={{ ...MUTED, marginTop: 6 }}>N. {c.n} · Media netta {bp(c.mean_net_bp)}</div>
          <div style={MUTED}>Intervallo: {bp(c.ci_low)} / {bp(c.ci_high)}</div>
        </div>)}
        {shownRegime.truncated && <p style={MUTED}>La tabella mostra solo le prime celle disponibili.</p>}
      </>}
      <div style={{ fontSize: 12, color: '#cbd5e1', borderTop: '1px solid #314357', paddingTop: 10 }}>
        Insufficiente ≠ cattivo: significa non ancora misurato.
      </div>
    </section>
  </main>;
}

export default function Overview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [regime, setRegime] = useState('');
  const [refreshToken, setRefreshToken] = useState(0);
  const requestRefresh = useCallback(() => setRefreshToken(n => n + 1), []);
  useEffect(() => {
    let alive = true;
    let active = null;
    const refresh = async () => {
      if (active) return; // no overlapping requests
      const controller = new AbortController();
      active = controller;
      try {
        const [a, b, c, d] = await Promise.all([
          API.get('/api/v3/overview', { signal: controller.signal }),
          API.get('/api/v3/brain/status', { signal: controller.signal }),
          API.get('/api/v3/brain/scoreboard', { signal: controller.signal }),
          API.get('/api/v3/brain/trades?limit=20', { signal: controller.signal }),
        ]);
        if (alive) { setData({ overview: a.data, status: b.data, scoreboard: c.data, trades: d.data }); setError(false); }
      } catch (e) {
        if (alive && !controller.signal.aborted) { setError(true); setData(null); }
      } finally {
        if (active === controller) active = null;
        if (alive) setLoading(false);
      }
    };
    refresh();
    const timer = setInterval(refresh, 30000);
    return () => { alive = false; clearInterval(timer); if (active) active.abort(); };
  }, [refreshToken]);
  if (loading) return <div role="status" style={{ padding: 22 }}>Caricamento della dashboard PAPER…</div>;
  if (error) return <div role="alert" style={{ padding: 22 }}>Impossibile aggiornare la dashboard. Verifica la connessione o la sessione.</div>;
  return <OverviewContent {...data} regime={regime} onRegime={setRegime} onRefresh={requestRefresh} />;
}
