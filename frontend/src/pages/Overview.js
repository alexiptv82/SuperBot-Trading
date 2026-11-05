/** Unified PAPER overview: read-only mobile-first view. No trading controls. */
import React, { useEffect, useState } from 'react';
import API from '../api';

const PALETTE = { running: '#34d399', paused: '#fbbf24', halted: '#fb7185', stale: '#fbbf24', not_started: '#94a3b8' };
const STATE_TEXT = { running: 'In funzione', paused: 'In pausa', halted: 'Fermo', stale: 'Segnale assente', not_started: 'Non avviato' };
const VERDICTS = { positive: ['Positivo', '#34d399'], negative: ['Negativo', '#fb7185'], inconclusive: ['Inconcludente', '#fbbf24'], insufficient: ['Dati insufficienti', '#94a3b8'] };
const BLOCK = { background: '#172338', border: '1px solid #2f425b', borderRadius: 16, padding: 16, marginBottom: 12 };
const MUTED = { color: '#a8bacd', fontSize: 12 };

const money = value => value === null || value === undefined ? '—' : `${value} USDT`;
const bp = value => value === null || value === undefined ? '—' : `${value} bp`;
const amountUsd = value => value === null || value === undefined ? '—' : `$${value}`;
const direction = side => side === 1 ? 'LONG' : side === -1 ? 'SHORT' : '—';
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

function StateLabel({ state }) {
  return <span style={{ color: PALETTE[state] || '#94a3b8', fontWeight: 700, fontSize: 13 }}>
    <span aria-hidden="true">● </span>{STATE_TEXT[state] || 'Non disponibile'}
  </span>;
}

export function OverviewContent({ overview, status, scoreboard, trades, nowMs = Date.now(), regime, onRegime }) {
  if (!overview) return <section role="status" style={BLOCK}>Nessun dato disponibile.</section>;
  const portfolios = overview.portfolios || [];
  const regimes = scoreboard?.regimes || [];
  const shownRegime = regimes.find(r => r.regime === regime) || regimes[0];
  const stoppedReason = status?.state === 'halted' ? reasonText(status?.heartbeat?.last_error) : null;
  const openPositions = trades?.open_positions || [];
  const closedTrades = (trades?.closed_trades || []).slice(0, 20);
  return <main style={{ background: '#0b1323', color: '#eef5ff', minHeight: '100vh', padding: '16px 12px 92px', maxWidth: 640, margin: '0 auto', boxSizing: 'border-box', fontFamily: 'system-ui, sans-serif' }}>
    <header style={{ marginBottom: 18 }}>
      <div style={{ color: '#7dd3fc', fontSize: 11, fontWeight: 800, letterSpacing: 2 }}>SUPERBOT V3 · PAPER</div>
      <h1 style={{ fontSize: 25, margin: '6px 0' }}>I tre portafogli</h1>
      <div style={MUTED}>Solo lettura · Ultimo aggiornamento {ageText(overview.generated_at_ms, nowMs)}</div>
    </header>
    <section aria-label="Portafogli">
      {portfolios.map(p => <article key={p.id} style={BLOCK}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
          <strong style={{ fontSize: 18 }}>{({ falco: '🦅 Falco', toro: '🐂 Toro', brain: '🧠 Brain V3' })[p.id] || p.id}</strong>
          <StateLabel state={p.state} />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 16 }}>
          <div><div style={MUTED}>Posizioni aperte</div><strong>{p.open_positions ?? '—'}</strong></div>
          <div><div style={MUTED}>P&L realizzato</div><strong>{p.state === 'not_started' ? '—' : money(p.realized_pnl)}</strong></div>
          <div><div style={MUTED}>Margine in uso</div><strong>{p.state === 'not_started' ? '—' : money(p.margin_in_use)}</strong></div>
          <div><div style={MUTED}>Ultimo evento</div><strong>{ageText(p.last_event_ms, nowMs)}</strong></div>
        </div>
        {p.id === 'brain' && stoppedReason && <p style={{ color: '#fda4af', fontSize: 13 }}>{stoppedReason}</p>}
      </article>)}
    </section>
    <section style={BLOCK} aria-label="Stato Brain">
      <h2 style={{ fontSize: 17, marginTop: 0 }}>🧠 Brain · come lavora</h2>
      {status?.state === 'not_started' ? <p style={MUTED}>Brain non ancora avviato: nessuna decisione disponibile.</p> : <>
        <div style={MUTED}>Regime · Ultima decisione</div>
        <div style={{ fontWeight: 700, margin: '5px 0 12px' }}>{status?.regime || 'Non disponibile'} · {status?.last_decision?.kind || 'Nessuna'}</div>
        {status?.last_decision && <div style={MUTED}>{status.last_decision.symbol || '—'} · {status.last_decision.strategy_id || 'Senza strategia dichiarata'} · {status.last_decision.status || '—'}</div>}
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
    <section style={BLOCK} aria-label="Posizioni Brain">
      <h2 style={{ fontSize: 17, margin: '0 0 12px' }}>Posizioni aperte · Brain</h2>
      {openPositions.length === 0 ? <p style={MUTED}>Nessuna posizione aperta.</p> : openPositions.map(p => <div key={p.position_id} style={{ borderTop: '1px solid #314357', padding: '12px 0' }}>
        <strong>{p.symbol} · {direction(p.side)} · {p.leverage}×</strong>
        <div style={MUTED}>Strategia: {p.strategy_id || 'Non dichiarata'}</div>
        <div style={MUTED}>Ingresso {p.entry} · Stop {p.stop}</div>
        <div style={MUTED}>P&L non realizzato: {money(p.unrealized_pnl)}</div>
      </div>)}
    </section>
    <section style={BLOCK} aria-label="Ultimi trade Brain">
      <h2 style={{ fontSize: 17, margin: '0 0 12px' }}>Ultimi 20 trade chiusi · Brain</h2>
      {closedTrades.length === 0 ? <p style={MUTED}>Nessun trade chiuso disponibile.</p> : closedTrades.map(t => <div key={t.position_id} style={{ borderTop: '1px solid #314357', padding: '12px 0' }}>
        <strong>{t.symbol} · {direction(t.side)} · {t.strategy_id || 'Senza etichetta'}</strong>
        <div style={MUTED}>{t.regime || 'Regime sconosciuto'} · {t.exit_reason} · {ageText(t.closed_at_ms, nowMs)}</div>
        <div style={MUTED}>Netto: {bp(t.net_bp)} · Durata: {t.hold_ms} ms</div>
      </div>)}
    </section>
  </main>;
}

export default function Overview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [regime, setRegime] = useState('');
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
  }, []);
  if (loading) return <div role="status" style={{ padding: 22 }}>Caricamento della dashboard PAPER…</div>;
  if (error) return <div role="alert" style={{ padding: 22 }}>Impossibile aggiornare la dashboard. Verifica la connessione o la sessione.</div>;
  return <OverviewContent {...data} regime={regime} onRegime={setRegime} />;
}
