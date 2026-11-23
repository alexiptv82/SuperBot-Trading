import React, { useCallback, useEffect, useState } from 'react';
import API from '../api';
import BrainMemorySection from '../components/BrainMemorySection';
import { BrainCloseControls } from '../components/OverviewCloseControls';
import { brainStateCard, freeCash, num, openPnl, shownResults } from '../brainUnicoModel';
import { fmtDuration, pnlColor, signed } from '../deskUi';
import { ClosedTradeDetails, ageText } from './Overview';

// Schermata principale del Brain Unico (PAPER). Stessa grafica e stessa disposizione della dashboard Classici
// (equity al centro, tre KPI, stato, comandi, posizioni), ma solo per il Brain: Falco e Toro restano nello Storico.
// Sola lettura + chiusura manuale SINGOLA con conferma (BrainCloseControls). Nessun comando di avvio/pausa.
const fmt = (v, d = 2) => (num(v) === null ? '--' : num(v).toFixed(d));
const px = v => (num(v) === null ? '--' : fmt(v, num(v) < 1 ? 5 : 2));
const usd = (v, d = 2) => (num(v) === null ? '—' : `${num(v) < 0 ? '-' : ''}$${Math.abs(num(v)).toFixed(d)}`);
const sgn = v => (num(v) === null ? '—' : `${signed(num(v))}$`);
const tone = v => (num(v) === null ? '#94a3b8' : pnlColor(num(v)));
const MUTED = { color: '#94a3b8', fontSize: 12 };

const Card = ({ children, style, ...rest }) => (
  <div {...rest} style={{ background: '#1e293b', borderRadius: 16, padding: 16, border: '1px solid #334155', ...style }}>{children}</div>
);

const Fold = ({ title, children, label }) => (
  <details aria-label={label || title} style={{ background: '#1e293b', borderRadius: 16, padding: '12px 16px',
    border: '1px solid #334155', marginBottom: 12 }}>
    <summary style={{ fontSize: 15, fontWeight: 700, cursor: 'pointer', color: '#cbd5e1' }}>{title}</summary>
    <div style={{ marginTop: 10 }}>{children}</div>
  </details>
);

function Kpi({ label, color, children, sub }) {
  return <Card style={{ flex: 1, textAlign: 'center', padding: '12px 8px', minWidth: 0 }}>
    <div style={{ fontSize: 10, color: '#64748b', marginBottom: 2 }}>{label}</div>
    <div style={{ fontSize: 24, fontWeight: 'bold', color }}>{children}</div>
    {sub && <div style={{ fontSize: 9, color: '#475569' }}>{sub}</div>}
  </Card>;
}

function Position({ p, nowMs }) {
  const base = String(p.symbol || '?').replace('USDT', '').replace('PERP', '');
  const isLong = p.side === 1;
  const priceOk = num(p.price) !== null && num(p.unrealized_pnl) !== null;
  const pnl = priceOk ? num(p.unrealized_pnl) : null;
  const roi = priceOk ? num(p.roi_pct) : null;
  const age = Number.isSafeInteger(p.opened_at_ms) && p.opened_at_ms > 0 ? fmtDuration(nowMs - p.opened_at_ms) : null;
  return <div data-testid="portfolio-trade-brain">
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', minWidth: 0 }}>
        <span style={{ padding: '2px 7px', borderRadius: 5, fontSize: 10, fontWeight: 'bold', color: 'white',
          background: p.side === 1 ? '#166534' : p.side === -1 ? '#7f1d1d' : '#334155' }}>
          {p.side === 1 ? 'LONG' : p.side === -1 ? 'SHORT' : '—'}</span>
        <span style={{ fontWeight: 'bold', fontSize: 14 }}>{base}</span>
        <span style={{ color: '#94a3b8', fontSize: 12 }}>x{p.leverage ?? '--'}</span>
        <span style={{ fontSize: 10, color: '#475569', background: '#0f172a', padding: '1px 5px', borderRadius: 4 }}>
          {p.strategy_id || 'Brain AI'}</span>
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        <div style={{ color: tone(pnl), fontWeight: 'bold', fontSize: 16 }}>{pnl === null ? '—' : sgn(pnl)}</div>
        <div style={{ color: tone(roi), fontSize: 11 }}>{roi === null ? 'ROI —' : `${signed(roi)}% sul margine`}</div>
      </div>
    </div>
    <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', marginTop: 8, fontSize: 11, color: '#94a3b8', gap: '2px 10px' }}>
      <span>Entrata <strong style={{ color: '#e2e8f0' }}>${px(p.entry)}</strong></span>
      <span>Ora <strong style={{ color: '#e2e8f0' }}>${px(p.price)}</strong></span>
      <span>Margine <strong style={{ color: '#e2e8f0' }}>${fmt(p.margin, 0)}</strong></span>
    </div>
    <div style={{ display: 'flex', gap: 12, marginTop: 6, fontSize: 10, flexWrap: 'wrap' }}>
      <span style={{ color: '#f87171' }}>SL ${px(p.stop)}</span>
      <span style={{ color: '#4ade80' }}>TP ${px(p.take_profit)}</span>
      {num(p.liquidation) !== null && <span style={{ color: '#64748b' }}>Liq ${px(p.liquidation)}</span>}
      {age && <span style={{ color: '#64748b' }}>aperta da {age}</span>}
    </div>
    {!priceOk && <div style={{ fontSize: 10, color: '#a16207', marginTop: 4 }}>
      Prezzo aggiornato non disponibile: P&L e ROI non calcolabili.</div>}
  </div>;
}

const POSITION_CARD = { background: '#1e293b', borderRadius: 16, padding: 16, border: '1px solid #334155', marginBottom: 8, minWidth: 0 };

export function BrainUnicoContent({ overview, status, trades, memory, nowMs = Date.now(), onRefresh = () => {} }) {
  const p = (overview?.portfolios || []).find(x => x.id === 'brain');
  const notStarted = !p || p.state === 'not_started';
  const open = trades?.open_positions || [];
  const closed = (trades?.closed_trades || []).slice(0, 20);
  const unrealized = openPnl(trades);
  const results = shownResults(trades);
  const m = memory?.memory || {};
  const card = brainStateCard(p, status);
  const realized = num(p?.realized_pnl);
  const start = num(p?.start_equity);
  const equity = num(p?.equity);
  const pct = start && realized !== null ? realized / start * 100 : null;
  const equityColor = realized === null || realized === 0 ? '#e2e8f0'
    : realized > 0 ? '#4ade80' : (start && equity !== null && equity < start * 0.8 ? '#f87171' : '#fbbf24');
  const spendDay = num(status?.spend?.day);
  const spendLimit = num(status?.spend?.day_limit);
  const budgetHigh = spendDay !== null && spendLimit ? spendDay > spendLimit * 0.85 : false;
  const now = new Date(nowMs);
  const cycle = status?.heartbeat?.cycle;
  const wins = trades?.win_count ?? null;
  const losses = trades?.loss_count ?? null;
  const readOnly = overview?.cutover_readonly === true && overview?.brain_single_close_allowed !== true;

  return <div style={{ padding: 16, maxWidth: 600, margin: '0 auto', boxSizing: 'border-box' }}>
    <header style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontSize: 22, fontWeight: 'bold', margin: 0, background: 'linear-gradient(90deg, #f1f5f9, #a78bfa)',
            WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>🧠 Brain Unico</h1>
          <div style={{ fontSize: 10, color: '#a78bfa', fontWeight: 700, letterSpacing: '0.08em', marginTop: 3 }}>
            ○ PAPER MODE · BRAIN UNICO · soldi simulati</div>
        </div>
        <span style={{ padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 'bold', background: '#a78bfa26',
          color: '#c4b5fd', border: '1px solid #a78bfa4d', flexShrink: 0 }}>PAPER</span>
      </div>
      <div style={{ fontSize: 12, color: '#64748b', marginTop: 8, marginBottom: 10 }}>
        {now.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short' })} · <strong style={{ color: '#94a3b8' }}>
          {now.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}</strong>
        {Number.isInteger(cycle) && <span> · Ciclo #{cycle}</span>}
        <span> · aggiornato {overview ? ageText(overview.generated_at_ms, nowMs) : '—'}</span>
      </div>
      <div aria-label="Stato del Brain" style={{ padding: '6px 10px', borderRadius: 10, fontSize: 12, textAlign: 'center',
        background: `${card.color}14`, border: `1px solid ${card.color}55`, color: card.color }}>
        🧠 Brain Unico {card.key === 'operational' ? '● ' : '⏸ '}{card.title}</div>
    </header>

    {/* Equity */}
    <Card aria-label="Equity" style={{ marginBottom: 12, textAlign: 'center', borderColor: `${equityColor}55` }}>
      <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
        Equity — 🧠 Brain Unico · PAPER</div>
      {notStarted ? <p style={{ ...MUTED, margin: '8px 0' }}>Brain non ancora avviato: nessun risultato.</p> : <>
        <div style={{ fontSize: 36, fontWeight: 'bold', color: equityColor }}>{usd(equity)}</div>
        <div style={{ fontSize: 13, fontWeight: 'bold', color: tone(realized), marginTop: 2 }}>
          P&L realizzato {sgn(realized)}{pct !== null && ` (${signed(pct)}%)`}{start !== null && ` da ${usd(start, 0)}`}
        </div>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 14, marginTop: 8, fontSize: 12, flexWrap: 'wrap' }}>
          <span style={{ color: '#64748b' }}>Cassa <strong style={{ color: '#cbd5e1' }}>{usd(freeCash(p))}</strong></span>
          <span style={{ color: '#64748b' }}>Margine <strong style={{ color: '#cbd5e1' }}>{usd(p.margin_in_use, 0)}</strong></span>
          <span style={{ color: '#64748b' }}>Aperto <strong style={{ color: tone(unrealized) }}>{sgn(unrealized)}</strong></span>
          <span style={{ color: '#64748b' }}>Oggi <strong style={{ color: tone(p.day_pnl) }}>{sgn(p.day_pnl)}</strong></span>
        </div>
        <div style={{ fontSize: 10, color: '#475569', marginTop: 6 }}>Oggi = risultato realizzato del giorno (UTC)</div>
        {num(p.settled_equity) !== null && <p style={{ ...MUTED, fontSize: 11, margin: '6px 0 0' }}>
          Saldo PAPER contabile: {usd(p.settled_equity)}{p.equity_basis === 'open_unmarked' && ' (escluso P&L aperto)'}</p>}
        {equity === null && <div style={{ color: '#fbbf24', marginTop: 6, fontSize: 11 }}>
          Equity non calcolabile senza prezzi verificati delle posizioni aperte.</div>}
      </>}
    </Card>

    {/* KPI */}
    <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
      <Kpi label="Aperte" color={open.length ? '#38bdf8' : '#94a3b8'}>{trades ? open.length : '—'}</Kpi>
      <Kpi label="Chiuse" color="#e2e8f0">{trades?.total_closed ?? p?.total_closed ?? '—'}</Kpi>
      <Kpi label="Budget AI" color={budgetHigh ? '#fbbf24' : '#4ade80'}
        sub={spendLimit !== null ? `/ $${fmt(spendLimit)} oggi` : undefined}>
        <span style={{ fontSize: 18 }}>{spendDay === null ? '—' : `$${fmt(spendDay, 3)}`}</span></Kpi>
    </div>

    {/* Stato Brain */}
    <Card aria-label="Stato Brain" style={{ marginBottom: 12, borderColor: card.color, background: `${card.color}14`, fontSize: 13, padding: '12px 16px' }}>
      <div style={{ color: card.color, fontWeight: 'bold' }}>🧠 Brain · {card.title}</div>
      <div style={{ ...MUTED, marginTop: 4 }}>{card.detail}</div>
      <div style={{ ...MUTED, fontSize: 11, marginTop: 4 }}>
        Battito: {status?.heartbeat ? ageText(status.heartbeat.ts_ms, nowMs) : '—'}
        {status?.last_decision && ` · ultima decisione ${status.last_decision.kind || '—'}${status.last_decision.symbol ? ` ${status.last_decision.symbol}` : ''} (${ageText(status.last_decision.ts_ms, nowMs)})`}
      </div>
    </Card>

    {/* Comandi: nessuna API sicura -> disabilitati */}
    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
      {['▶ Avvia / Riprendi', '⏸ Pausa'].map(label => <button key={label} type="button" disabled
        aria-describedby="brain-commands-why" style={{ flex: 1, padding: 12, borderRadius: 10, fontWeight: 'bold', fontSize: 14,
          border: '1px solid #334155', background: 'rgba(51,65,85,0.2)', color: '#475569', cursor: 'not-allowed' }}>{label}</button>)}
    </div>
    <p id="brain-commands-why" style={{ fontSize: 11, color: '#64748b', textAlign: 'center', margin: '0 0 12px' }}>
      Comandi disabilitati: l’app non ha un’API sicura per avviare o mettere in pausa il Brain. L’attivazione dipende dal
      mandato del proprietario sul server; da qui è consentita solo la chiusura manuale singola PAPER.</p>

    {/* Posizioni aperte */}
    <h2 style={{ fontSize: 15, fontWeight: 'bold', marginBottom: 8, color: '#cbd5e1' }}>⚡ Posizioni Aperte</h2>
    {!trades && <p role="alert" style={{ color: '#fda4af', fontSize: 13 }}>
      Dettaglio posizioni non disponibile: nessuna chiusura consentita da questa schermata.</p>}
    {trades && open.length === 0 && <Card style={{ marginBottom: 12, textAlign: 'center', color: '#475569', fontSize: 13 }}>
      Nessuna posizione aperta al momento</Card>}
    {trades && <BrainCloseControls positions={open} readOnly={readOnly} allowCloseAll={false}
      serverPending={trades?.close_pending === true} onRefresh={onRefresh} itemStyle={POSITION_CARD}
      closeLabel={pos => `Chiudi ${pos.symbol} (PAPER)`}
      renderPosition={pos => <Position p={pos} nowMs={nowMs} />} />}

    {/* Statistiche */}
    <h2 style={{ fontSize: 15, fontWeight: 'bold', margin: '16px 0 8px', color: '#cbd5e1' }}>📊 Statistiche</h2>
    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
      <Kpi label="Vinti" color="#4ade80">{wins ?? '—'}</Kpi>
      <Kpi label="Persi" color="#f87171">{losses ?? '—'}</Kpi>
      <Kpi label="Win rate" color="#e2e8f0">{p?.win_rate == null ? '—' : <span style={{ fontSize: 20 }}>{p.win_rate}%</span>}</Kpi>
    </div>
    <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
      <Kpi label="Guadagni (ultimi 20)" color="#4ade80"><span style={{ fontSize: 17 }}>{results.count ? usd(results.gains) : '—'}</span></Kpi>
      <Kpi label="Perdite (ultimi 20)" color="#fda4af"><span style={{ fontSize: 17 }}>{results.count ? usd(results.losses) : '—'}</span></Kpi>
    </div>
    <p style={{ ...MUTED, fontSize: 11, margin: '0 0 4px' }}>
      Vinti / persi / pari: {trades ? `${wins ?? 0} / ${losses ?? 0} / ${trades.break_even_count ?? 0}` : '—'}
      {' · '}Chiusure tue / automatiche: {memory?.state === 'ok' ? `${m.manual_closes ?? 0} / ${m.automatic_closes ?? 0}` : '—'}
    </p>
    <p style={{ ...MUTED, fontSize: 11, margin: '0 0 16px' }}>
      Sono risultati della simulazione PAPER. Le tue chiusure manuali restano nello storico come interventi dell’operatore:
      non vengono trattate come strategie del Brain. Ciò che non è registrato resta “—”.</p>

    {/* Sezioni espandibili */}
    <Fold title="🧾 Ultimi trade chiusi" label="Trade chiusi">
      {trades && closed.length === 0 && <p style={MUTED}>Nessun trade chiuso disponibile.</p>}
      {!trades && <p style={MUTED}>Storico dei trade non disponibile.</p>}
      {closed.map((t, i) => <ClosedTradeDetails key={`${t.position_id || t.symbol}-${i}`} t={t} brain nowMs={nowMs} />)}
    </Fold>

    <Fold title="⚙️ Come lavora" label="Come lavora">
      {status?.state === 'not_started' || !status ? <p style={MUTED}>Stato non disponibile.</p> : <>
        <div style={MUTED}>Regime · Ultima decisione</div>
        <div style={{ fontWeight: 700, margin: '5px 0 8px' }}>{status.regime || 'Non disponibile'} · {status.last_decision?.kind || 'Nessuna'}</div>
        {status.last_decision && <div style={MUTED}>{status.last_decision.symbol || '—'} · {status.last_decision.status || '—'} · {ageText(status.last_decision.ts_ms, nowMs)}</div>}
        <div style={{ ...MUTED, marginTop: 8 }}>Battito: {status.heartbeat ? ageText(status.heartbeat.ts_ms, nowMs) : '—'}{status.paused ? ' · in pausa' : ''}</div>
        <div style={{ ...MUTED, marginTop: 6 }}>Perdita giornaliera: <strong style={{ color: { ok: '#34d399', warn: '#fbbf24', halt: '#fb7185' }[status.daily_loss?.level] || '#a8bacd' }}>
          {{ ok: 'nei limiti', warn: 'avviso', halt: 'blocco nuove aperture', unknown: 'non verificabile' }[status.daily_loss?.level] || 'non disponibile'}</strong>
          {status.daily_loss?.pct != null ? ` · ${status.daily_loss.pct}%` : ''}</div>
      </>}
      <div style={{ ...MUTED, marginTop: 10 }}>Spesa AI oggi / tetto giornaliero:{' '}
        <strong style={{ color: '#e2e8f0' }}>{usd(status?.spend?.day, 3)} / {usd(status?.spend?.day_limit)}</strong></div>
    </Fold>

    <BrainMemorySection memory={memory} collapsible />

    <Fold title="🗄️ Storico" label="Storico">
      <p style={MUTED}>Falco, Toro e i Brain precedenti restano consultabili, separati dal Brain Unico. L’Arena è consultabile in sola lettura.</p>
      <nav aria-label="Storico portafogli" style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <a href="/brain-unico" style={{ color: '#7dd3fc', fontSize: 13 }}>Brain: Falco Evoluto · Brain Scalp</a>
        <a href="/overview" style={{ color: '#7dd3fc', fontSize: 13 }}>Falco · Toro · Brain V3</a>
        <a href="/classic" style={{ color: '#7dd3fc', fontSize: 13 }}>Dashboard classica</a>
        <a href="/brain/archive" style={{ color: '#7dd3fc', fontSize: 13 }}>Brain precedenti</a>
        <a href="/arena" style={{ color: '#7dd3fc', fontSize: 13 }}>Arena</a>
        <a href="/compare" style={{ color: '#7dd3fc', fontSize: 13 }}>Confronto Falco Evoluto · Brain Scalp</a>
      </nav>
    </Fold>
  </div>;
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
