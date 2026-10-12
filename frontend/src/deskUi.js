// Piccoli helper condivisi dalle schermate dei portafogli (Dashboard, Trade, Performance, Impostazioni).

export const fmtClock = (ms) =>
  ms ? new Date(ms).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' }) : '--';

export const fmtDateTime = (ms) =>
  ms ? new Date(ms).toLocaleString('it-IT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '--';

export const fmtDuration = (ms) => {
  if (!ms || ms < 0) return '--';
  const m = Math.round(ms / 60000);
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return h < 24 ? `${h}h ${m % 60}m` : `${Math.floor(h / 24)}g ${h % 24}h`;
};

export const signed = (v, d = 2) =>
  (v == null || isNaN(v)) ? '--' : `${v > 0 ? '+' : ''}${Number(v).toFixed(d)}`;

export const pnlColor = (v) => (v > 0 ? '#4ade80' : v < 0 ? '#f87171' : '#94a3b8');

// Stato del bot in parole, calcolato dallo status del server.
export function botState(status) {
  if (!status || status.available !== true) return { key: 'unavailable', text: 'senza dati', color: '#94a3b8' };
  if (status.bot_online === false) return { key: 'offline', text: 'non risponde', color: '#f87171' };
  switch (status.bot_mode) {
    case 'draining': return { key: 'draining', text: 'pausa in corso', color: '#fbbf24' };
    case 'paused':   return { key: 'paused', text: 'in pausa', color: '#94a3b8' };
    default:         return { key: 'running', text: 'in funzione', color: '#4ade80' };
  }
}

// Parametri confrontabili tra una run e l'altra / mostrati in Impostazioni: [etichetta, lettura, formato]
export const PARAM_ROWS = [
  ['Margine max / trade', (p) => p?.limits?.max_margin_trade, (v) => `$${v}`],
  ['Posizioni max', (p) => p?.limits?.max_open, (v) => v],
  ['Budget totale margine', (p) => p?.limits?.max_margin_total, (v) => `$${v}`],
  ['Soglia ingresso BTC/ETH/XAU/XAG', (p) => p?.entry_score_tier_ab, (v) => v],
  ['Soglia ingresso altcoin', (p) => p?.entry_score_tier_c, (v) => v],
  ['Stop giornaliero', (p) => p?.limits?.daily_stop, (v) => `${Math.round(v * 100)}%`],
  ['Soglia minima capitale', (p) => p?.limits?.kill_equity, (v) => `$${v}`],
  ['Leva minima', (p) => p?.guardrail?.min_lev, (v) => `${v}x`],
  ['Margine minimo', (p) => p?.guardrail?.min_margin, (v) => `$${v}`],
  ['Tetto spesa Claude / giorno', (p) => p?.daily_cap_usd, (v) => `$${v}`],
  ['Versione del codice', (p) => p?.code_version, (v) => v],
];
