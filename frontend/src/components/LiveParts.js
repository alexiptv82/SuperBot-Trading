import React from 'react';
import { fmtClock, fmtDuration, signed, pnlColor } from '../deskUi';

// Pezzi condivisi dalle schermate Live (Dashboard Live e scheda Trade Live): stato del bot in parole,
// scheda di una posizione aperta, elenco degli ultimi trade chiusi.

export const MUTED = '#64748b';
const LONG = { fg: '#4ade80', bg: 'rgba(74,222,128,0.12)' };
const SHORT = { fg: '#f87171', bg: 'rgba(248,113,113,0.12)' };

export const money = (v, d = 2) => {
  const n = parseFloat(v);
  return isNaN(n) ? '--' : n.toFixed(d);
};

// Prezzi di coin molto diversi (BTC 60000, XRP 0.52, PEPE 0.0000012): decimali in base alla grandezza.
export const price = (v) => {
  const n = parseFloat(v);
  if (isNaN(n)) return '--';
  return n.toFixed(n < 0.01 ? 7 : n < 1 ? 5 : n < 100 ? 3 : 2);
};

// "2 min fa" / "tra 3 min" / "adesso"
export const relTime = (ms, now = Date.now()) => {
  if (!ms) return null;
  const diff = ms - now;
  const abs = Math.abs(diff);
  if (abs < 60000) return diff < 0 ? 'adesso' : 'tra pochi secondi';
  const m = diff < 0 ? Math.floor(abs / 60000) : Math.ceil(abs / 60000);
  const txt = m < 60 ? `${m} min` : `${Math.floor(m / 60)}h ${m % 60}m`;
  return diff < 0 ? `${txt} fa` : `tra ${txt}`;
};

// Stato del bot in una frase, dai dati che il server manda per ogni portafoglio.
export function liveBotStatus(d, serverIsLive) {
  if (!d) return { key: 'none', text: 'Nessun dato', color: MUTED };
  if (!serverIsLive) return { key: 'paper', text: 'Modalità paper', color: MUTED };
  if (d.bot_mode !== 'live') return { key: 'waiting', text: 'In attesa del bot live', color: '#fbbf24' };
  if (d.bot_online === false) return { key: 'offline', text: 'Il bot non risponde', color: '#f87171' };
  const n = d.open_positions || 0;
  if (d.live_interlock) return { key: 'blocked', text: 'Nuove aperture bloccate', color: '#f87171' };
  if (d.daily_limit_hit) return { key: 'limit', text: 'Limite di perdita di oggi raggiunto', color: '#f87171' };
  if (d.halt) return { key: 'halt', text: `Fermo di sicurezza: ${d.halt}`, color: '#fbbf24' };
  if (!d.trading_enabled) {
    return { key: 'off', color: MUTED,
      text: n > 0 ? `Fermo: non apre nuove posizioni (${n} ancora aperte)` : 'Fermo: premi Avvia per iniziare' };
  }
  return { key: 'on', color: '#4ade80', text: n > 0 ? `Lavora · ${n} ${n === 1 ? 'posizione aperta' : 'posizioni aperte'}` : 'Lavora · cerca opportunità' };
}

// ── Una posizione aperta ───────────────────────────────────────────────────────
export function PositionCard({ p }) {
  const isLong = p.side === 1;
  const c = isLong ? LONG : SHORT;
  const hasPnl = p.pnl !== null && p.pnl !== undefined && !isNaN(p.pnl);
  const notes = [];
  if (p.source === 'bot') notes.push(p.confirmed === false
    ? 'Il bot la registra aperta ma BitGet non la mostra ancora: non confermata.'
    : 'Numeri del bot (BitGet non è leggibile in questo momento).');
  if (p.in_bot === false) notes.push('È su BitGet ma il bot non la conosce: non è un suo trade.');
  return (
    <div style={{
      background: '#0f1829', border: `1px solid ${isLong ? '#164e63' : '#4c0519'}`,
      borderRadius: '12px', padding: '12px 14px', marginBottom: '8px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap', minWidth: 0 }}>
          <span style={{ fontWeight: 800, fontSize: '15px', color: '#f1f5f9' }}>{p.symbol}</span>
          <span style={{ fontSize: '10px', fontWeight: 700, color: c.fg, background: c.bg, borderRadius: '4px', padding: '2px 6px' }}>
            {isLong ? 'LONG' : 'SHORT'}
          </span>
          {p.leverage ? <span style={{ fontSize: '12px', color: '#94a3b8' }}>x{p.leverage}</span> : null}
          {p.trade_type ? (
            <span style={{ fontSize: '10px', color: MUTED, background: '#0b1220', borderRadius: '4px', padding: '1px 5px' }}>{p.trade_type}</span>
          ) : null}
          {(p.dca_count || 0) > 0 && <span style={{ fontSize: '10px', color: '#fbbf24' }}>DCA×{p.dca_count}</span>}
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: '17px', fontWeight: 800, color: hasPnl ? pnlColor(p.pnl) : MUTED, fontVariantNumeric: 'tabular-nums' }}>
            {hasPnl ? `${signed(p.pnl)}$` : '--'}
          </div>
          <div style={{ fontSize: '11px', color: hasPnl ? pnlColor(p.pnl) : MUTED }}>
            {p.pnl_pct != null ? `${signed(p.pnl_pct)}% sul margine` : 'prezzo non disponibile'}
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px', flexWrap: 'wrap', marginTop: '10px', fontSize: '12px', color: '#94a3b8' }}>
        <span>Entrata <strong style={{ color: '#e2e8f0' }}>${price(p.entry)}</strong></span>
        <span>Ora <strong style={{ color: '#e2e8f0' }}>${price(p.price)}</strong></span>
        <span>Margine <strong style={{ color: '#e2e8f0' }}>${money(p.margin, 0)}</strong></span>
      </div>

      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '6px', fontSize: '11px' }}>
        {p.sl ? <span style={{ color: '#f87171' }}>Stop ${price(p.sl)}</span> : null}
        {p.tp ? <span style={{ color: '#4ade80' }}>Obiettivo ${price(p.tp)}</span> : null}
        {p.liq ? <span style={{ color: MUTED }}>Liquidazione ${price(p.liq)}</span> : null}
        {p.open_ms ? <span style={{ color: MUTED }}>aperta da {fmtDuration(Date.now() - p.open_ms)}</span> : null}
      </div>

      {notes.map((t) => (
        <div key={t} style={{ marginTop: '6px', fontSize: '10px', color: '#a16207' }}>{t}</div>
      ))}
    </div>
  );
}

// ── Ultimi trade chiusi ────────────────────────────────────────────────────────
export function RecentTrades({ trades = [] }) {
  if (!trades.length) {
    return <div style={{ padding: '4px 0', fontSize: '12px', color: MUTED }}>Ancora nessun trade chiuso in live.</div>;
  }
  return (
    <div>
      {trades.map((t, i) => {
        const c = t.side === 1 ? LONG : SHORT;
        return (
          <div key={`${t.close_ms}-${i}`} style={{
            display: 'flex', alignItems: 'center', gap: '8px', padding: '7px 8px', borderRadius: '8px',
            background: i % 2 === 0 ? '#0f1829' : 'transparent', fontSize: '12px',
          }}>
            <span style={{ color: '#e2e8f0', fontWeight: 700, minWidth: '44px' }}>{t.symbol}</span>
            <span style={{ fontSize: '10px', fontWeight: 700, color: c.fg, background: c.bg, borderRadius: '4px', padding: '1px 5px' }}>
              {t.side === 1 ? 'LONG' : 'SHORT'}
            </span>
            <span style={{ color: MUTED, fontSize: '11px', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {t.close_reason}{t.partial ? ' (parziale)' : ''}
            </span>
            <span style={{ color: MUTED, fontSize: '10px' }}>{fmtClock(t.close_ms)}</span>
            <span style={{ fontWeight: 700, color: pnlColor(t.pnl), fontVariantNumeric: 'tabular-nums', minWidth: '60px', textAlign: 'right' }}>
              {t.pnl != null ? `${signed(t.pnl)}$` : '--'}
            </span>
          </div>
        );
      })}
    </div>
  );
}
