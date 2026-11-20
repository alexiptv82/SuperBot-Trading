import React, { useCallback, useEffect, useState } from 'react';
import API from '../api';
import BrainMemorySection from '../components/BrainMemorySection';
import { BrainCloseControls, PortfolioTradeFields } from '../components/OverviewCloseControls';
import { ClosedTradeDetails, StateLabel, ageText, amountUsd, detailBox, pnlColor, reasonText } from './Overview';

// Schermata principale del Brain Unico (PAPER). Riusa i componenti gia' collaudati della Overview: stessi controlli di
// chiusura singola con conferma, stessa presentazione dei trade. Falco, Toro e i Brain precedenti restano nello Storico.
const BLOCK = { background: '#172338', border: '1px solid #2f425b', borderRadius: 16, padding: 16, marginBottom: 12 };
const MUTED = { color: '#a8bacd', fontSize: 12 };
const money = value => (value === null || value === undefined ? '—' : `${value} USDT`);
const sum = values => values.reduce((a, v) => a + v, 0);
const num = v => (v === null || v === undefined || v === '' || !Number.isFinite(Number(v)) ? null : Number(v));

function Box({ label, children, color }) {
  return <div style={detailBox}><div style={MUTED}>{label}</div><strong style={color ? { color } : undefined}>{children}</strong></div>;
}

export function BrainUnicoContent({ overview, status, trades, memory, nowMs = Date.now(), onRefresh = () => {} }) {
  const p = (overview?.portfolios || []).find(x => x.id === 'brain');
  const notStarted = !p || p.state === 'not_started';
  const open = trades?.open_positions || [];
  const closed = (trades?.closed_trades || []).slice(0, 20);
  const unrealized = !trades ? null : !open.length ? '0' :
    open.every(x => num(x.unrealized_pnl) !== null) ? sum(open.map(x => Number(x.unrealized_pnl))).toFixed(2) : null;
  const shownPnl = closed.map(t => num(t.realized_pnl)).filter(v => v !== null);
  const gains = sum(shownPnl.filter(v => v > 0));
  const losses = sum(shownPnl.filter(v => v < 0));
  const stoppedReason = status?.state === 'halted' ? reasonText(status?.heartbeat?.last_error) : null;
  const m = memory?.memory || {};
  return <main style={{ background: '#0b1323', color: '#eef5ff', minHeight: '100vh', padding: '16px 12px 92px', maxWidth: 1200, margin: '0 auto', boxSizing: 'border-box', fontFamily: 'system-ui, sans-serif' }}>
    <header style={{ marginBottom: 16 }}>
      <div style={{ color: '#c4b5fd', fontSize: 11, fontWeight: 800, letterSpacing: 2 }}>SUPERBOT · BRAIN UNICO · PAPER</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
        <h1 style={{ fontSize: 25, margin: '6px 0' }}>🧠 Brain</h1>
        {p && <StateLabel state={p.state} />}
      </div>
      <div style={MUTED}>Ultimo aggiornamento {overview ? ageText(overview.generated_at_ms, nowMs) : '—'} · conto virtuale, nessun ordine reale</div>
      {stoppedReason && <p role="status" style={{ color: '#fda4af', fontSize: 13 }}>{stoppedReason}</p>}
    </header>

    <section style={BLOCK} aria-label="Profitti e perdite">
      <h2 style={{ fontSize: 17, marginTop: 0 }}>💰 Profitti e perdite</h2>
      {notStarted ? <p style={MUTED}>Brain non ancora avviato: nessun risultato.</p> :
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 9 }}>
          <Box label="Equity">{money(p.equity)}</Box>
          <Box label="P&L realizzato" color={pnlColor(p.realized_pnl)}>{money(p.realized_pnl)}</Box>
          <Box label="P&L aperto" color={pnlColor(unrealized)}>{money(unrealized)}</Box>
          <Box label="Profitto di oggi (realizzato, UTC)" color={pnlColor(p.day_pnl)}>{money(p.day_pnl)}</Box>
          <Box label="Margine in uso">{money(p.margin_in_use)}</Box>
          <Box label="Saldo contabile">{money(p.settled_equity)}</Box>
        </div>}
      {p?.equity_basis === 'open_unmarked' && <p style={MUTED}>Equity non calcolabile senza prezzi verificati delle posizioni aperte.</p>}
    </section>

    <section style={BLOCK} aria-label="Statistiche">
      <h2 style={{ fontSize: 17, marginTop: 0 }}>📊 Statistiche</h2>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 9 }}>
        <Box label="Trade chiusi">{trades?.total_closed ?? p?.total_closed ?? '—'}</Box>
        <Box label="Win rate">{p?.win_rate == null ? '—' : `${p.win_rate}%`}</Box>
        <Box label="Vinti / persi / pari">{trades ? `${trades.win_count ?? 0} / ${trades.loss_count ?? 0} / ${trades.break_even_count ?? 0}` : '—'}</Box>
        <Box label="Chiusure: tue / automatiche">{memory?.state === 'ok' ? `${m.manual_closes ?? 0} / ${m.automatic_closes ?? 0}` : '—'}</Box>
        <Box label="Guadagni (ultimi 20)" color="#4ade80">{shownPnl.length ? money(gains.toFixed(2)) : '—'}</Box>
        <Box label="Perdite (ultimi 20)" color="#fda4af">{shownPnl.length ? money(losses.toFixed(2)) : '—'}</Box>
      </div>
      <p style={MUTED}>Le tue chiusure manuali restano nello storico come interventi dell’operatore: non vengono trattate come strategie del Brain.</p>
    </section>

    <section style={BLOCK} aria-label="Posizioni aperte">
      <h2 style={{ fontSize: 17, marginTop: 0 }}>📂 Posizioni aperte</h2>
      {!trades && <p role="alert" style={{ color: '#fda4af', fontSize: 13 }}>
        Dettaglio posizioni non disponibile: nessuna chiusura consentita da questa schermata.</p>}
      {trades && open.length === 0 && <p style={MUTED}>Nessuna posizione aperta.</p>}
      {trades && <BrainCloseControls positions={open}
        readOnly={overview?.cutover_readonly === true && overview?.brain_single_close_allowed !== true}
        allowCloseAll={overview?.cutover_readonly !== true}
        serverPending={trades?.close_pending === true}
        onRefresh={onRefresh} renderPosition={pos => <PortfolioTradeFields p={pos} brain />} />}
    </section>

    <section style={BLOCK} aria-label="Trade chiusi">
      <h2 style={{ fontSize: 17, marginTop: 0 }}>🧾 Ultimi trade chiusi</h2>
      {trades && closed.length === 0 && <p style={MUTED}>Nessun trade chiuso disponibile.</p>}
      {!trades && <p style={MUTED}>Storico dei trade non disponibile.</p>}
      {closed.map((t, i) => <ClosedTradeDetails key={`${t.position_id || t.symbol}-${i}`} t={t} brain nowMs={nowMs} />)}
    </section>

    <section style={BLOCK} aria-label="Come lavora">
      <h2 style={{ fontSize: 17, marginTop: 0 }}>⚙️ Stato del sistema</h2>
      {status?.state === 'not_started' || !status ? <p style={MUTED}>Stato non disponibile.</p> : <>
        <div style={MUTED}>Regime · Ultima decisione</div>
        <div style={{ fontWeight: 700, margin: '5px 0 8px' }}>{status.regime || 'Non disponibile'} · {status.last_decision?.kind || 'Nessuna'}</div>
        {status.last_decision && <div style={MUTED}>{status.last_decision.symbol || '—'} · {status.last_decision.status || '—'} · {ageText(status.last_decision.ts_ms, nowMs)}</div>}
        <div style={{ ...MUTED, marginTop: 8 }}>Battito: {status.heartbeat ? ageText(status.heartbeat.ts_ms, nowMs) : '—'}{status.paused ? ' · in pausa' : ''}</div>
      </>}
      <div style={{ borderTop: '1px solid #314357', marginTop: 12, paddingTop: 12 }}>
        <div style={MUTED}>Spesa AI oggi / tetto giornaliero</div>
        <strong>{amountUsd(status?.spend?.day)} / {amountUsd(status?.spend?.day_limit)}</strong>
      </div>
    </section>

    <BrainMemorySection memory={memory} />

    <section style={BLOCK} aria-label="Storico">
      <h2 style={{ fontSize: 17, marginTop: 0 }}>🗄️ Storico</h2>
      <p style={MUTED}>Falco, Toro e i Brain precedenti restano consultabili, separati dal Brain Unico. La vista storica dell’Arena non è ancora integrata in questa versione dell’app.</p>
      <nav aria-label="Storico portafogli" style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <a href="/overview" style={{ color: '#7dd3fc', fontSize: 13 }}>Falco · Toro · Brain V3</a>
        <a href="/classic" style={{ color: '#7dd3fc', fontSize: 13 }}>Dashboard classica</a>
        <a href="/brain/archive" style={{ color: '#7dd3fc', fontSize: 13 }}>Brain precedenti</a>
      </nav>
    </section>
  </main>;
}

export default function BrainUnico() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const requestRefresh = useCallback(() => setRefreshToken(n => n + 1), []);
  useEffect(() => {
    let alive = true;
    let active = null;
    const refresh = async () => {
      if (active) return;
      const controller = new AbortController();
      active = controller;
      try {
        const [a, b, c, d] = await Promise.allSettled([
          API.get('/api/v3/overview', { signal: controller.signal }),
          API.get('/api/v3/brain/status', { signal: controller.signal }),
          API.get('/api/v3/brain/trades?limit=20', { signal: controller.signal }),
          API.get('/api/v3/brain/memory', { signal: controller.signal }),
        ]);
        if (a.status !== 'fulfilled' || !Array.isArray(a.value?.data?.portfolios)) throw new Error('overview_unavailable');
        if (alive && !controller.signal.aborted) {
          setData({
            overview: a.value.data,
            status: b.status === 'fulfilled' ? b.value.data : null,
            trades: c.status === 'fulfilled' ? c.value.data : null,
            memory: d.status === 'fulfilled' ? d.value.data : null,
          });
          setError(false);
        }
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
  if (loading) return <div role="status" style={{ padding: 22 }}>Caricamento del Brain…</div>;
  if (error) return <div role="alert" style={{ padding: 22 }}>Impossibile aggiornare il Brain. Verifica la connessione o la sessione.</div>;
  return <BrainUnicoContent {...data} onRefresh={requestRefresh} />;
}
