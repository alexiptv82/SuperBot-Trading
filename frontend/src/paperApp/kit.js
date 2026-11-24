import React, { useEffect, useRef, useState } from 'react';
import API from '../api';

// Kit dell'app PAPER (Brain, Trade, Performance, Archivio): formattazione, colori, componenti di base e lettura dati.
// Regole di presentazione: nessun numero inventato (assente = "—"), testi mai sotto 12 px, contrasto alto sul fondo
// scuro, ogni valore dice se e' AGGIORNATO (ora) o riferito all'ULTIMO GIRO del bot.

export const num = v => (v === null || v === undefined || v === '' || typeof v === 'boolean' || !Number.isFinite(Number(v))
  ? null : Number(v));
export const usd = (v, d = 2) => (num(v) === null ? '—' : `${num(v) < 0 ? '−' : ''}$${Math.abs(num(v)).toLocaleString('it-IT', { minimumFractionDigits: d, maximumFractionDigits: d })}`);
export const sgn = (v, d = 2) => (num(v) === null ? '—' : `${num(v) > 0 ? '+' : num(v) < 0 ? '−' : ''}$${Math.abs(num(v)).toLocaleString('it-IT', { minimumFractionDigits: d, maximumFractionDigits: d })}`);
export const pct = (v, d = 2) => (num(v) === null ? '—' : `${num(v) > 0 ? '+' : num(v) < 0 ? '−' : ''}${Math.abs(num(v)).toFixed(d).replace('.', ',')}%`);
export const price = v => {
  const n = num(v);
  if (n === null) return '—';
  const d = n >= 1000 ? 1 : n >= 10 ? 2 : n >= 1 ? 4 : 5;
  return `$${n.toLocaleString('it-IT', { minimumFractionDigits: d, maximumFractionDigits: d })}`;
};
export const own = (t, k) => (typeof k === 'string' && Object.prototype.hasOwnProperty.call(t, k) ? t[k] : undefined);

export const C = {
  bg: '#0b1018', card: '#141b26', card2: '#0f1520', line: '#263244', text: '#f1f5f9', soft: '#cbd5e1',
  muted: '#9aa8bc', up: '#4ade80', down: '#f87171', warn: '#fbbf24', info: '#38bdf8', accent: '#a78bfa',
};
export const tone = v => (num(v) === null ? C.muted : num(v) > 0 ? C.up : num(v) < 0 ? C.down : C.soft);

// Colore fisso per bot: lo stesso in tutte le pagine e nei grafici di confronto
export const BOTS = {
  falco_evoluto: { label: 'Falco Evoluto', color: '#f59e0b', icon: '🦅', short: 'Falco' },
  // dal 24/11 lo slot brain_scalp ospita il Brain unico PAPER 2000 (le sessioni Scalp precedenti sono in Archivio)
  brain_scalp: { label: 'Brain', color: '#38bdf8', icon: '🧠', short: 'Brain' },
};
export const botMeta = name => own(BOTS, name) || { label: name, color: C.accent, icon: '•', short: name };

export function when(ms) {
  if (!Number.isSafeInteger(ms) || ms <= 0) return '—';
  return new Date(ms).toLocaleString('it-IT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}
export function day(iso) {
  const d = typeof iso === 'string' ? new Date(`${iso}T12:00:00`) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short' }) : '—';
}
export function ago(ms, nowMs) {
  if (!Number.isSafeInteger(ms) || ms <= 0 || !Number.isSafeInteger(nowMs)) return null;
  const s = Math.floor((nowMs - ms) / 1000);
  if (s < 60) return 'ora';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min fa`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h ${String(m % 60).padStart(2, '0')} min fa`;
  return `${Math.floor(h / 24)} giorni fa`;
}
export function duration(ms) {
  if (!Number.isSafeInteger(ms) || ms < 0) return '—';
  const m = Math.round(ms / 60000);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return h < 48 ? `${h} h ${String(m % 60).padStart(2, '0')}` : `${Math.floor(h / 24)} g ${h % 24} h`;
}

export const SIDE = { 1: ['LONG', '#166534', '#bbf7d0'], '-1': ['SHORT', '#7f1d1d', '#fecaca'] };
export const EXIT_REASON = {
  stop: 'Stop', take_profit: 'Take profit', timeout: 'Tempo massimo', manual: 'Chiusura manuale',
  brain_close: 'Chiusura del Brain',
};
export const STOP_KIND = { initial: 'stop iniziale', break_even: 'stop a pareggio', trailing: 'trailing stop', protect: 'protezione profitti',
  brain: 'stop stretto dal Brain' };
// quote di un'apertura divisa del Brain unico
export const LEG = { tp1: '1ª quota · presa a 2R', runner: 'Residuo · verso 3,5R' };
export const REVIEW_ACTION = { HOLD: 'mantiene', CLOSE: 'chiude tutto', PARTIAL_CLOSE: 'incassa la 1ª quota',
  MODIFY_STOP: 'stringe lo stop', ADD: 'secondo ingresso', NONE: 'nessuna risposta AI' };
export const REVIEW_CODE = { hold: '', close_all_legs: '', close_tp1_leg: '', stop_tightened: '',
  partial_not_available: 'presa parziale non disponibile', stop_not_tighter: 'stop non più stretto: ignorato',
  stop_too_close_to_price: 'stop troppo vicino al prezzo: ignorato', stop_invalid: 'stop non valido: ignorato',
  action_invalid: 'risposta non valida', budget_denied: 'budget AI esaurito', invalid_model_output: 'risposta AI non valida',
  ai_unavailable: 'AI non disponibile', review_failed: 'revisione non riuscita',
  close_request_pending: 'chiusura in attesa del servizio uscite',
  claude_unavailable_critical: 'Claude non disponibile: azione non eseguita', claude_unavailable_hold: '',
  claude_unavailable_risk_reducing: 'Claude non disponibile: riduzione del rischio eseguita',
  add_requested: '', paper_add_committed: '', reduce_position: '', add_not_available: 'secondo ingresso non previsto',
  add_price_not_better: 'prezzo non abbastanza conveniente', add_no_risk_room: 'nessun rischio disponibile',
  claude_rejected_add: 'Claude contrario al secondo ingresso', add_needs_both: 'serve l’accordo delle due AI',
  add_needs_consult: 'serve il consulto di Claude',
  claude_adopted: 'scelta di Claude', deepseek_kept: 'scelta di DeepSeek', claude_confirmed: '',
  both_tighten_stop: 'stop più stretto fra i due', no_consult_needed: '' };
export const SOURCE = { deepseek: 'DeepSeek', claude: 'Claude', agreed: 'DeepSeek + Claude d’accordo', none: '—' };
export const LEARNING = {
  profit_protection_example: 'esempio di profitto protetto', loss_reduction_example: 'esempio di perdita ridotta',
  break_even_example: 'esempio a pareggio',
};
export const REASON = {
  falco_no_trade_regime: 'Regime non adatto (laterale, incerto o shock)',
  falco_no_trade_score: 'Punteggio sotto la soglia',
  falco_no_trade_conflict: 'Segnali LONG e SHORT in conflitto',
  falco_no_trade_data: 'Dati di mercato insufficienti',
  falco_ai_no_trade: 'L’AI consultata non conferma',
  falco_ai_unavailable: 'AI non disponibile',
  falco_short_signal: 'Segnale SHORT dalle regole', falco_long_signal: 'Segnale LONG dalle regole',
  'deepseek:analysis': 'Analisi DeepSeek', risk_rejected: 'Rifiutata dai limiti di rischio', risk_quote_ok: 'Approvata',
  policy_not_authorized: 'Mandato non approvato', market_gate: 'Mercato non idoneo', price_divergence: 'Prezzo cambiato',
  malformed_output: 'Risposta AI non valida', invalid_input: 'Dati non validi',
};
export const RISK = {
  below_min_margin: 'margine sotto il minimo', below_minimum_size: 'quantità sotto il minimo del contratto',
  margin_loss_ratio_exceeded: 'stop troppo largo per la leva minima', stop_near_liquidation: 'stop troppo vicino alla liquidazione',
  max_positions_reached: 'posizioni al massimo', guardian_budget_exhausted: 'budget del Guardian esaurito',
  risk_budget_exhausted: 'rischio disponibile esaurito', margin_budget_exhausted: 'margine disponibile esaurito',
  equity_floor_reached: 'equity al minimo (floor)', leverage_outside_profile: 'leva fuori dal profilo 15–45×',
  stale_market_data: 'dati di mercato vecchi', portfolio_locked: 'portafoglio bloccato', stop_wrong_side: 'stop dal lato sbagliato',
};
// un codice sconosciuto si mostra solo se e' un codice (mai testo libero arrivato dal server)
const CODE = /^[a-z][a-z0-9_:]{0,63}$/;
export const reasonText = code => own(REASON, code) || (CODE.test(code || '') ? `codice ${code}` : 'motivo non registrato');
export const riskText = code => (!code ? null : own(RISK, code) || (CODE.test(code) ? `limite ${code}` : 'limite non registrato'));

// ---------------------------------------------------------------- componenti
export function Card({ children, style, accent, ...rest }) {
  return <div {...rest} style={{ background: C.card, borderRadius: 18, padding: 16, border: `1px solid ${accent ? `${accent}66` : C.line}`,
    marginBottom: 12, boxShadow: '0 1px 0 rgba(255,255,255,0.03) inset', ...style }}>{children}</div>;
}

export function Section({ title, hint, children, right }) {
  return <section style={{ marginTop: 18 }} aria-label={title}>
    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8, margin: '0 2px 8px' }}>
      <h2 style={{ fontSize: 16, fontWeight: 700, color: C.text, margin: 0 }}>{title}</h2>
      {right}
    </div>
    {hint && <p style={{ fontSize: 13, color: C.muted, margin: '-4px 2px 10px', lineHeight: 1.4 }}>{hint}</p>}
    {children}
  </section>;
}

export function Stat({ label, value, color = C.text, sub, big = false, compact = false }) {
  return <div style={{ minWidth: 0 }}>
    <div style={{ fontSize: 12, color: C.muted, marginBottom: 2 }}>{label}</div>
    <div style={{ fontSize: big ? 24 : compact ? 15 : 18, fontWeight: 700, color, fontVariantNumeric: 'tabular-nums',
      ...(compact ? { whiteSpace: 'nowrap', letterSpacing: '-0.01em' } : { overflowWrap: 'anywhere' }) }}>{value}</div>
    {sub && <div style={{ fontSize: 12, color: C.muted, marginTop: 1 }}>{sub}</div>}
  </div>;
}

export const Grid = ({ children, cols = 2, gap = 14 }) => (
  <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap }}>{children}</div>
);

// Etichetta della freschezza di un valore: "aggiornato ora" (verde) o "ultimo giro, 12 min fa" (grigio)
export function Fresh({ live, atMs, nowMs }) {
  const a = ago(atMs, nowMs);
  return <span style={{ fontSize: 12, fontWeight: 600, padding: '2px 8px', borderRadius: 999, whiteSpace: 'nowrap',
    background: live ? '#14532d' : '#1f2937', color: live ? '#bbf7d0' : C.soft, border: `1px solid ${live ? '#166534' : C.line}` }}>
    {live ? `● aggiornato${a ? ` ${a}` : ''}` : `ultimo giro${a ? `, ${a}` : ''}`}</span>;
}

export function Pill({ children, color = C.soft, bg }) {
  return <span style={{ display: 'inline-block', fontSize: 12, fontWeight: 700, padding: '2px 9px', borderRadius: 999,
    color, background: bg || `${color}22`, border: `1px solid ${color}55`, whiteSpace: 'nowrap' }}>{children}</span>;
}

export function SideTag({ side }) {
  const s = own(SIDE, String(side));
  return s ? <span style={{ fontSize: 12, fontWeight: 800, padding: '2px 8px', borderRadius: 6, background: s[1], color: s[2] }}>{s[0]}</span>
    : <span style={{ fontSize: 12, color: C.muted }}>—</span>;
}

export function Fold({ title, children, label, open = false }) {
  return <details open={open} aria-label={label || title} style={{ background: C.card, borderRadius: 18, padding: '14px 16px',
    border: `1px solid ${C.line}`, marginBottom: 12 }}>
    <summary style={{ fontSize: 15, fontWeight: 700, cursor: 'pointer', color: C.soft, minHeight: 24 }}>{title}</summary>
    <div style={{ marginTop: 12 }}>{children}</div>
  </details>;
}

export const Note = ({ children, style }) => <p style={{ fontSize: 13, color: C.muted, lineHeight: 1.45, margin: '6px 2px', ...style }}>{children}</p>;

export function Empty({ children }) {
  return <Card style={{ textAlign: 'center', color: C.muted, fontSize: 14, padding: 20 }}>{children}</Card>;
}

// Selettore dei due bot: <button> nativi con aria-pressed (tocco Android, tastiera, lettori di schermo)
export function BotSwitch({ runs, selected, onSelect, both = false, render, controls, label }) {
  const items = both ? [{ name: '__both', label: 'Confronto' }, ...runs] : runs;
  return <div role="group" aria-label="Scegli il bot" style={{ display: 'flex', gap: 8, margin: '4px 0 12px' }}>
    {items.map(r => {
      const m = r.name === '__both' ? { color: C.accent, icon: '⚖️' } : botMeta(r.name);
      const on = r.name === selected;
      return <button key={r.name} type="button" aria-pressed={on} data-bot={r.name} onClick={() => onSelect(r.name)}
        aria-controls={controls ? controls(r) : undefined} aria-label={label ? label(r, on) : undefined}
        style={{ flex: 1, minWidth: 0, minHeight: 48, padding: '9px 10px', borderRadius: 14, cursor: 'pointer', textAlign: 'left',
          font: 'inherit', color: C.text, WebkitTapHighlightColor: 'transparent', touchAction: 'manipulation',
          background: on ? `${m.color}26` : C.card, border: on ? `2px solid ${m.color}` : `1px solid ${C.line}`,
          boxShadow: on ? `0 0 0 3px ${m.color}22` : 'none' }}>
        {render ? render(r, on) : <span style={{ fontSize: 14, fontWeight: 700 }}>{m.icon} {r.label}</span>}
      </button>;
    })}
  </div>;
}

export function PageHeader({ title, subtitle, children }) {
  return <header style={{ margin: '4px 2px 12px' }}>
    <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0, color: C.text, letterSpacing: '-0.01em' }}>{title}</h1>
    {subtitle && <div style={{ fontSize: 13, color: C.muted, marginTop: 4 }}>{subtitle}</div>}
    {children}
  </header>;
}

export const Page = ({ children }) => (
  <main style={{ padding: '12px 16px 24px', maxWidth: 680, margin: '0 auto', boxSizing: 'border-box', color: C.text }}>{children}</main>
);

// Grafico a linee in SVG puro (niente dipendenze): una o piu' serie {name, color, points:[{t, v}]} sullo stesso asse.
export function LineChart({ series, height = 180, baseline = null, label, format = v => usd(v, 0) }) {
  const pts = series.flatMap(s => s.points);
  if (pts.length < 2) return <div role="img" aria-label={`${label}: dati insufficienti`} style={{ fontSize: 13, color: C.muted, padding: '24px 0', textAlign: 'center' }}>
    Il grafico compare dopo almeno due punti registrati.</div>;
  const W = 600;
  const pad = { l: 8, r: 8, t: 12, b: 22 };
  const ts = pts.map(p => p.t);
  const vs = pts.map(p => p.v).concat(baseline === null ? [] : [baseline]);
  let lo = Math.min(...vs);
  let hi = Math.max(...vs);
  if (hi === lo) { hi += 1; lo -= 1; }
  const m = (hi - lo) * 0.08;
  lo -= m; hi += m;
  const t0 = Math.min(...ts);
  const t1 = Math.max(...ts) === t0 ? t0 + 1 : Math.max(...ts);
  const x = t => pad.l + (t - t0) / (t1 - t0) * (W - pad.l - pad.r);
  const y = v => pad.t + (hi - v) / (hi - lo) * (height - pad.t - pad.b);
  return <figure style={{ margin: 0 }}>
    <svg role="img" aria-label={label} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" style={{ width: '100%', height, display: 'block' }}>
      {baseline !== null && <line x1={pad.l} x2={W - pad.r} y1={y(baseline)} y2={y(baseline)} stroke="#475569" strokeDasharray="4 4" strokeWidth="1" vectorEffect="non-scaling-stroke" />}
      {series.filter(s => s.points.length).map(s => <polyline key={s.name} fill="none" stroke={s.color} strokeWidth="2.2" vectorEffect="non-scaling-stroke"
        strokeLinejoin="round" points={s.points.map(p => `${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ')} />)}
    </svg>
    <figcaption style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: C.muted, marginTop: 4, gap: 8, flexWrap: 'wrap' }}>
      <span>min {format(Math.min(...pts.map(p => p.v)))} · max {format(Math.max(...pts.map(p => p.v)))}</span>
      <span>{when(t0)} → {when(Math.max(...ts))}</span>
    </figcaption>
    {series.length > 1 && <div style={{ display: 'flex', gap: 14, fontSize: 13, color: C.soft, marginTop: 6, flexWrap: 'wrap' }}>
      {series.map(s => <span key={s.name}><span aria-hidden="true" style={{ display: 'inline-block', width: 12, height: 3, background: s.color, verticalAlign: 'middle', marginRight: 6 }} />{s.name}</span>)}
    </div>}
  </figure>;
}

// Lettura periodica in sola lettura (GET). ``paths`` = elenco di URL; risultato nello stesso ordine.
// Il PRIMO URL e' quello principale: se fallisce -> errore (si tengono i dati gia' letti). Gli altri sono accessori:
// se falliscono il loro posto vale null e la pagina resta utilizzabile.
export function usePoll(paths, everyMs = 30000) {
  const [state, setState] = useState({ data: null, error: false, at: null });
  const [tick, setTick] = useState(0);
  const key = paths.join('|');
  const keyRef = useRef(key);
  keyRef.current = key;
  useEffect(() => {
    let alive = true;
    const load = async () => {
      if (!key) { setState({ data: [], error: false, at: Date.now() }); return; }
      const FAIL = {};
      const res = await Promise.all(key.split('|').map(p => API.get(p).then(r => r.data, () => FAIL)));
      if (!alive || keyRef.current !== key) return;
      if (res[0] === FAIL) setState(s => ({ ...s, error: true }));
      else setState({ data: res.map(r => (r === FAIL ? null : r)), error: false, at: Date.now() });
    };
    load();
    const t = setInterval(load, everyMs);
    return () => { alive = false; clearInterval(t); };
  }, [key, everyMs, tick]);
  return { ...state, refresh: () => setTick(n => n + 1) };
}

export function LoadState({ error, loading, what }) {
  if (error) return <p role="alert" style={{ color: '#fda4af', fontSize: 14, margin: '8px 2px' }}>
    {what} non disponibili: verifica la connessione o la sessione.</p>;
  if (loading) return <p role="status" style={{ color: C.muted, fontSize: 14, margin: '8px 2px' }}>Caricamento…</p>;
  return null;
}
