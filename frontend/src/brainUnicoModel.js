/** Modello di presentazione della schermata Brain Unico (solo lettura: nessuna chiamata, nessuna scrittura).
 *
 * Riceve le risposte gia' lette da /api/v3/overview, /brain/status, /brain/trades e le traduce in testo e colori.
 * Non inventa nulla: un dato assente resta null e la schermata lo mostra come "—".
 */
export const num = v => (v === null || v === undefined || v === '' || typeof v === 'boolean' || !Number.isFinite(Number(v))
  ? null : Number(v));

const MANDATE_RE = /(?:^|;)(?:halted:)?(?:no_mandate|mandate_not_approved|mandate_invalid|mandate_mismatch)(?:;|$)/;
const BUDGET_RE = /(?:^|;)(?:halted:)?(?:budget|ledger_error)(?:;|$)/;

const TONES = { ok: '#4ade80', wait: '#fbbf24', stop: '#f87171', idle: '#94a3b8' };

/** Stato leggibile del Brain: operativo, in pausa, bloccato dal rischio, in attesa del mandato, ... */
export function brainStateCard(portfolio, status) {
  const code = typeof status?.heartbeat?.last_error === 'string' ? status.heartbeat.last_error : '';
  const state = status?.state || portfolio?.state || null;
  const pct = status?.daily_loss?.pct;
  const card = (key, title, detail) => ({ key, title, detail, color: TONES[{ operational: 'ok', paused: 'wait', mandate: 'wait',
    risk: 'stop', budget: 'wait', halted: 'stop', stale: 'wait', not_started: 'idle', unknown: 'idle' }[key]] });
  if (!portfolio || !state) return card('unknown', 'Stato non disponibile', 'Il Brain non ha ancora dato segnali leggibili.');
  if (state === 'not_started') return card('not_started', 'Non avviato', 'Nessuna decisione registrata in questa run.');
  if (MANDATE_RE.test(code)) {
    return card('mandate', 'In attesa del mandato', 'Il Brain non apre operazioni finché il proprietario non approva il mandato.');
  }
  if (BUDGET_RE.test(code)) return card('budget', 'Tetto di spesa AI raggiunto', 'Nessuna nuova decisione fino al prossimo giorno.');
  if (status?.daily_loss?.level === 'halt') {
    return card('risk', 'Bloccato dal rischio',
      `Perdita giornaliera oltre il limite${pct != null ? ` (${pct}%)` : ''}: nuove aperture sospese.`);
  }
  if (state === 'halted') return card('halted', 'Fermo', 'Il Brain si è fermato: verificare lo stato del servizio.');
  if (state === 'paused' || status?.paused === true) {
    return card('paused', 'In pausa', 'Nessuna nuova apertura. Le posizioni aperte restano gestite da stop e obiettivo.');
  }
  if (state === 'stale') return card('stale', 'Segnale assente', 'Nessun battito recente dal Brain.');
  if (state === 'running') return card('operational', 'DeepSeek operativo', 'Analizza il mercato a ogni ciclo; NO TRADE resta una decisione valida.');
  return card('unknown', 'Stato non disponibile', 'Stato non riconosciuto.');
}

/** Cassa libera = saldo contabile (capitale + risultati chiusi) meno il margine in uso. Mai dedotta dal capitale iniziale. */
export function freeCash(portfolio) {
  const settled = num(portfolio?.settled_equity);
  const margin = num(portfolio?.margin_in_use);
  return settled === null || margin === null ? null : settled - margin;
}

/** P&L aperto: somma solo se TUTTE le posizioni hanno un valore; altrimenti sconosciuto (mai 0 per default). */
export function openPnl(trades) {
  if (!trades) return null;
  const open = trades.open_positions || [];
  if (!open.length) return 0;
  const values = open.map(x => num(x.unrealized_pnl));
  return values.every(v => v !== null) ? values.reduce((a, v) => a + v, 0) : null;
}

/** Statistiche dei soli trade chiusi mostrati (ultimi 20): somma di guadagni e perdite. */
export function shownResults(trades) {
  const values = ((trades?.closed_trades) || []).map(t => num(t.realized_pnl)).filter(v => v !== null);
  return { count: values.length, gains: values.filter(v => v > 0).reduce((a, v) => a + v, 0),
    losses: values.filter(v => v < 0).reduce((a, v) => a + v, 0) };
}
