import React, { useEffect, useState } from 'react';
import API from '../api';
import { BrainCloseControls } from '../components/OverviewCloseControls';
import { ago, botStatus, equityView, guardianView, num } from '../paperBotsModel';
import { REASON, RISK } from './Compare';

// Schermata principale "Brain": i due bot PAPER in funzione (Falco Evoluto e Brain Scalp), uno sotto l'altro, con stato
// RUNNING/PAUSA, capitale, equity, profitti, posizioni, Guardian e chiusura manuale SINGOLA (con conferma).
// Dati: solo /api/v3/compare (sola lettura, ogni numero dal journal della SUA run). Nessun comando di avvio/pausa:
// l'app non ha API sicure per questo. Brain RC1, Falco classico e Toro restano consultabili nello Storico.
const usd = (v, d = 2) => (num(v) === null ? '—' : `${num(v) < 0 ? '-' : ''}$${Math.abs(num(v)).toFixed(d)}`);
const sgn = (v, d = 2) => (num(v) === null ? '—' : `${num(v) > 0 ? '+' : num(v) < 0 ? '-' : ''}$${Math.abs(num(v)).toFixed(d)}`);
const pct = v => (num(v) === null ? '—' : `${num(v) > 0 ? '+' : ''}${num(v).toFixed(2)}%`);
const tone = v => (num(v) === null ? '#94a3b8' : num(v) > 0 ? '#4ade80' : num(v) < 0 ? '#f87171' : '#94a3b8');
const MUTED = { color: '#94a3b8', fontSize: 12 };
const own = (t, k) => (typeof k === 'string' && Object.prototype.hasOwnProperty.call(t, k) ? t[k] : undefined);

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

const Kpi = ({ label, color, children, sub }) => (
  <Card style={{ flex: 1, textAlign: 'center', padding: '10px 6px', minWidth: 0 }}>
    <div style={{ fontSize: 10, color: '#64748b', marginBottom: 2 }}>{label}</div>
    <div style={{ fontSize: 22, fontWeight: 'bold', color }}>{children}</div>
    {sub && <div style={{ fontSize: 9, color: '#475569' }}>{sub}</div>}
  </Card>
);

const Badge = ({ status }) => (
  <span aria-label={`Stato ${status.label}`} style={{ padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 'bold',
    background: `${status.color}26`, color: status.color, border: `1px solid ${status.color}66`, flexShrink: 0,
    whiteSpace: 'nowrap' }}>{status.key === 'running' || status.key === 'running_wait' ? '● ' : status.key === 'paused' ? '⏸ ' : ''}{status.label}</span>
);

const ANALYST = { falco_evoluto: 'regole Falco Evoluto', deepseek: 'DeepSeek' };

function Summary({ runs, nowMs }) {
  return <div role="group" aria-label="Riepilogo dei due bot" style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
    {runs.map(r => {
      const st = botStatus(r, nowMs);
      const eq = equityView(r);
      return <Card key={r.name} style={{ flex: 1, minWidth: 0, padding: '10px 10px', borderColor: `${st.color}55` }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#cbd5e1', overflowWrap: 'anywhere' }}>{r.label}</div>
        <div style={{ margin: '4px 0' }}><Badge status={st} /></div>
        <div style={{ fontSize: 20, fontWeight: 'bold', color: '#e2e8f0' }}>{r.available ? usd(eq.value) : '—'}</div>
        <div style={{ fontSize: 11, color: tone(eq.totalPct) }}>{r.available ? pct(eq.totalPct) : '—'}</div>
      </Card>;
    })}
  </div>;
}

function Guardian({ run, nowMs }) {
  const g = guardianView(run);
  if (!g) {
    return <Card aria-label={`Guardian ${run.label}`} style={{ marginBottom: 12, fontSize: 13, padding: '12px 16px' }}>
      <div style={{ fontWeight: 'bold', color: '#cbd5e1' }}>🛡️ Smart Profit Guardian</div>
      <div style={{ ...MUTED, marginTop: 4 }}>Nessuna valutazione registrata finora: compare dopo il primo giro.</div>
    </Card>;
  }
  return <Card aria-label={`Guardian ${run.label}`} style={{ marginBottom: 12, borderColor: g.color, background: `${g.color}14`,
    fontSize: 13, padding: '12px 16px' }}>
    <div style={{ color: g.color, fontWeight: 'bold' }}>🛡️ Guardian · {g.label}</div>
    <div style={{ ...MUTED, marginTop: 4 }}>{g.detail}{g.reasons.length ? ` (${g.reasons.join(', ')})` : ''}</div>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 14px', marginTop: 6, fontSize: 11, color: '#94a3b8' }}>
      <span>Picco <strong style={{ color: '#e2e8f0' }}>{usd(g.peak)}</strong></span>
      <span>Giveback <strong style={{ color: '#e2e8f0' }}>{usd(g.giveback)}</strong></span>
      <span>Floor <strong style={{ color: '#e2e8f0' }}>{usd(g.floor)}</strong></span>
      <span>Rischio residuo <strong style={{ color: '#e2e8f0' }}>{usd(g.budget)}</strong></span>
      <span>Tetto apertura <strong style={{ color: '#e2e8f0' }}>{g.state === 'NORMAL' ? 'ordinario' : usd(g.riskCap)}</strong></span>
    </div>
    <div style={{ fontSize: 10, color: '#475569', marginTop: 4 }}>
      Valutato {ago(g.asOfMs, nowMs) || '—'}. Il floor limita le nuove aperture: non garantisce il profitto finale.</div>
  </Card>;
}

function Positions({ run, onRefresh }) {
  const open = run.open_positions || [];
  return <>
    <h3 style={{ fontSize: 14, fontWeight: 'bold', margin: '4px 0 8px', color: '#cbd5e1' }}>⚡ Posizioni aperte</h3>
    {open.length === 0 && <Card style={{ marginBottom: 12, textAlign: 'center', color: '#475569', fontSize: 13 }}>
      Nessuna posizione aperta al momento</Card>}
    <BrainCloseControls positions={open} allowCloseAll={false} readOnly={run.manual_close_allowed !== true}
      serverPending={run.close_pending === true} onRefresh={onRefresh}
      closeUrl={`/api/v3/compare/${run.name}/close`} resultUrl={`/api/v3/compare/${run.name}/close-result`}
      itemStyle={{ background: '#0f172a', borderRadius: 12, padding: 12, border: '1px solid #334155', marginBottom: 8 }}
      closeLabel={p => `Chiudi ${p.symbol} (PAPER)`}
      renderPosition={p => <div data-testid={`bot-position-${run.name}`}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          <span style={{ padding: '2px 7px', borderRadius: 5, fontSize: 10, fontWeight: 'bold', color: 'white',
            background: p.side === 1 ? '#166534' : p.side === -1 ? '#7f1d1d' : '#334155' }}>
            {p.side === 1 ? 'LONG' : p.side === -1 ? 'SHORT' : '—'}</span>
          <span style={{ fontWeight: 'bold', fontSize: 14 }}>{String(p.symbol || '?').replace('USDT', '')}</span>
          <span style={{ color: '#94a3b8', fontSize: 12 }}>x{p.leverage ?? '—'}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', marginTop: 6, fontSize: 11,
          color: '#94a3b8', gap: '2px 10px' }}>
          <span>Entrata <strong style={{ color: '#e2e8f0' }}>${p.entry ?? '—'}</strong></span>
          <span>Margine <strong style={{ color: '#e2e8f0' }}>{usd(p.margin, 0)}</strong></span>
          <span style={{ color: '#f87171' }}>Stop ${p.stop ?? '—'}</span>
        </div>
      </div>} />
    {open.length > 0 && <p style={{ ...MUTED, fontSize: 10, margin: '0 0 8px' }}>
      Prezzo e P&L per singola posizione non sono in questa vista: il P&L aperto complessivo è nella card dell’equity.
      {run.manual_close_allowed !== true && ' Chiusura manuale non disponibile finché il servizio uscite di questo portafoglio non è sano.'}</p>}
  </>;
}

export function BotCard({ run, nowMs, onRefresh }) {
  const st = botStatus(run, nowMs);
  if (run.available !== true) {
    return <Card aria-label={`Bot ${run.label}`} style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <strong style={{ fontSize: 16 }}>{run.label}</strong><Badge status={st} /></div>
      <p style={{ ...MUTED, margin: '8px 0 0' }}>{st.detail} Nessun dato viene mostrato finché non esiste il suo journal.</p>
    </Card>;
  }
  const eq = equityView(run);
  const cfg = run.config || {};
  const equityColor = eq.total === null || eq.total === 0 ? '#e2e8f0' : eq.total > 0 ? '#4ade80'
    : (eq.initial && eq.value !== null && eq.value < eq.initial * 0.8 ? '#f87171' : '#fbbf24');
  const open = run.open_positions || [];
  const spendLimit = num(cfg.daily_cap_usd);
  const spendDay = num(run.ai_spend?.day);
  const budgetHigh = spendDay !== null && spendLimit ? spendDay > spendLimit * 0.85 : false;
  const decisions = run.decisions || [];
  return <section aria-label={`Bot ${run.label}`} style={{ marginBottom: 18 }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 6 }}>
      <div style={{ minWidth: 0 }}>
        <h2 style={{ fontSize: 18, fontWeight: 'bold', margin: 0, color: '#f1f5f9' }}>{run.label}</h2>
        <div style={{ fontSize: 11, color: '#64748b' }}>
          analisi: {own(ANALYST, cfg.analyst) || '—'} · giro ogni {num(cfg.cycle_minutes) ?? '—'} min</div>
      </div>
      <Badge status={st} />
    </div>
    <div aria-label={`Stato ${run.label}`} style={{ padding: '6px 10px', borderRadius: 10, fontSize: 12, textAlign: 'center',
      marginBottom: 10, background: `${st.color}14`, border: `1px solid ${st.color}55`, color: st.color }}>
      {st.detail}{run.manual_close_allowed === true ? ' · uscite sane, chiusura manuale disponibile' : ' · chiusura manuale non disponibile'}</div>

    <Card aria-label={`Equity ${run.label}`} style={{ marginBottom: 10, textAlign: 'center', borderColor: `${equityColor}55` }}>
      <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4, letterSpacing: '0.05em', textTransform: 'uppercase' }}>
        Equity {eq.basis === 'market' ? 'a mercato' : 'contabile'} — PAPER</div>
      <div style={{ fontSize: 34, fontWeight: 'bold', color: equityColor }}>{usd(eq.value)}</div>
      <div style={{ fontSize: 13, fontWeight: 'bold', color: tone(eq.total), marginTop: 2 }}>
        {sgn(eq.total)} ({pct(eq.totalPct)}) su capitale {usd(eq.initial, 0)}</div>
      <div style={{ display: 'flex', justifyContent: 'center', gap: '4px 14px', marginTop: 8, fontSize: 12, flexWrap: 'wrap' }}>
        <span style={{ color: '#64748b' }}>Chiuso <strong style={{ color: tone(run.net_pnl) }}>{sgn(run.net_pnl)}</strong></span>
        <span style={{ color: '#64748b' }}>Aperto <strong style={{ color: tone(eq.unrealized) }}>{sgn(eq.unrealized)}</strong></span>
        <span style={{ color: '#64748b' }}>Sessione <strong style={{ color: tone(eq.session) }}>{sgn(eq.session)}</strong></span>
        <span style={{ color: '#64748b' }}>Dopo AI <strong style={{ color: tone(run.net_after_ai) }}>{sgn(run.net_after_ai)}</strong></span>
      </div>
      <div style={{ fontSize: 10, color: '#475569', marginTop: 6 }}>
        {eq.basis === 'market' ? `A mercato all’ultimo giro (${ago(eq.asOfMs, nowMs) || '—'}), commissioni di chiusura incluse. ` : 'Nessuna valutazione a mercato ancora registrata. '}
        Contabile (solo trade chiusi): {usd(eq.settled)}. “Chiuso” include le commissioni e non i costi AI; “Sessione” parte dalle 08:00.</div>
    </Card>

    <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
      <Kpi label="Aperte" color={open.length ? '#38bdf8' : '#94a3b8'} sub={`max ${cfg.max_positions ?? '—'}`}>{open.length}</Kpi>
      <Kpi label="Chiuse" color="#e2e8f0" sub={`${run.wins ?? 0} vinte · ${run.losses ?? 0} perse`}>{run.closed ?? '—'}</Kpi>
      <Kpi label="Budget AI" color={budgetHigh ? '#fbbf24' : '#4ade80'} sub={spendLimit !== null ? `/ $${spendLimit.toFixed(2)} oggi` : undefined}>
        <span style={{ fontSize: 16 }}>{spendDay === null ? '—' : `$${spendDay.toFixed(3)}`}</span></Kpi>
    </div>

    <Guardian run={run} nowMs={nowMs} />
    <Positions run={run} onRefresh={onRefresh} />

    <Fold title={`🧾 Ultime decisioni · ${run.label}`} label={`Decisioni ${run.label}`}>
      {decisions.length === 0 && <p style={MUTED}>Nessuna decisione registrata.</p>}
      {decisions.map((d, i) => <div key={`${d.ts_ms}-${i}`} style={{ ...MUTED, padding: '3px 0' }}>
        {ago(d.ts_ms, nowMs) || '—'} · {d.symbol || '—'} · {own(REASON, d.rationale) || d.kind || '—'}
        {d.risk_reason ? ` · ${own(RISK, d.risk_reason) || 'limite di rischio'}` : ''}</div>)}
    </Fold>
    <p style={{ ...MUTED, fontSize: 10, margin: '0 0 4px' }}>
      Capitale {usd(cfg.initial_equity, 0)} · leva {(cfg.leverage || []).join('–') || '—'}× · margine ${(cfg.margin || []).join('–') || '—'}
      {' · '}chiusure tue / protettive: {run.manual_closes ?? '—'} / {run.protected_stops ?? '—'}</p>
  </section>;
}

export function StoricoFold() {
  return <Fold title="🗄️ Storico" label="Storico">
    <p style={MUTED}>Brain RC1, Falco classico, Toro e i Brain precedenti restano consultabili con tutti i loro dati,
      separati da questi due bot. L’Arena è consultabile in sola lettura.</p>
    <nav aria-label="Storico portafogli" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <a href="/brain-unico/rc1" style={{ color: '#7dd3fc', fontSize: 14 }}>🧠 Brain RC1</a>
      <a href="/overview" style={{ color: '#7dd3fc', fontSize: 14 }}>Falco classico · Toro · Brain V3</a>
      <a href="/compare" style={{ color: '#7dd3fc', fontSize: 14 }}>⚖️ Confronto affiancato Falco Evoluto · Brain Scalp</a>
      <a href="/classic" style={{ color: '#7dd3fc', fontSize: 14 }}>Dashboard classica</a>
      <a href="/brain/archive" style={{ color: '#7dd3fc', fontSize: 14 }}>Brain precedenti</a>
      <a href="/arena" style={{ color: '#7dd3fc', fontSize: 14 }}>Arena</a>
    </nav>
  </Fold>;
}

export function PaperBotsContent({ data, error = false, nowMs = Date.now(), onRefresh = () => {} }) {
  const runs = data?.available ? (data.runs || []) : [];
  const now = new Date(nowMs);
  return <div style={{ padding: 16, maxWidth: 600, margin: '0 auto', boxSizing: 'border-box' }}>
    <header style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <div style={{ minWidth: 0 }}>
          <h1 style={{ fontSize: 22, fontWeight: 'bold', margin: 0, background: 'linear-gradient(90deg, #f1f5f9, #a78bfa)',
            WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>🧠 Brain</h1>
          <div style={{ fontSize: 10, color: '#a78bfa', fontWeight: 700, letterSpacing: '0.08em', marginTop: 3 }}>
            ○ PAPER MODE · FALCO EVOLUTO · BRAIN SCALP · soldi simulati</div>
        </div>
        <span style={{ padding: '3px 10px', borderRadius: 20, fontSize: 11, fontWeight: 'bold', background: '#a78bfa26',
          color: '#c4b5fd', border: '1px solid #a78bfa4d', flexShrink: 0 }}>PAPER</span>
      </div>
      <div style={{ fontSize: 12, color: '#64748b', marginTop: 8 }}>
        {now.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short' })} · <strong style={{ color: '#94a3b8' }}>
          {now.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}</strong>
        <span> · aggiornato {data?.generated_at_ms ? ago(data.generated_at_ms, nowMs) : '—'}</span>
      </div>
    </header>

    {error && <p role="alert" style={{ color: '#fda4af', fontSize: 13 }}>
      Dati dei bot non disponibili: verifica la connessione o la sessione. Lo Storico resta qui sotto.</p>}
    {!error && data === null && <p role="status" style={MUTED}>Caricamento dei bot…</p>}
    {!error && data && !data.available && <Card style={{ marginBottom: 12 }}><strong>Bot non ancora attivi</strong>
      <p style={MUTED}>Le due run PAPER (Falco Evoluto e Brain Scalp) non sono ancora state preparate e approvate.
        Nessun dato viene mostrato finché non esistono i loro journal.</p></Card>}
    {!error && runs.length > 0 && <>
      <Summary runs={runs} nowMs={nowMs} />
      {runs.map(r => <BotCard key={r.name} run={r} nowMs={nowMs} onRefresh={onRefresh} />)}
      <p style={{ ...MUTED, fontSize: 11 }}>Soldi simulati: nessun ordine reale. Ogni bot ha la sua run, il suo journal e il suo
        servizio uscite. Ciò che non è registrato resta “—”. Qui sono consentite solo chiusure manuali singole, con conferma;
        avvio, pausa e mandato restano un intervento del proprietario sul server.</p>
    </>}
    <StoricoFold />
  </div>;
}

export default function PaperBots() {
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
        if (alive) { setError(true); }
      }
    };
    load();
    const t = setInterval(load, 30000);
    return () => { alive = false; clearInterval(t); };
  }, [tick]);
  return <PaperBotsContent data={data} error={error} onRefresh={() => setTick(n => n + 1)} />;
}
