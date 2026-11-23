/** Modello di presentazione della schermata Brain (Falco Evoluto e Brain Scalp, PAPER). Solo funzioni pure.
 *
 * Riceve una riga di /api/v3/compare e la traduce in stato, equity e Guardian. Non inventa nulla: un dato assente
 * resta null e la schermata lo mostra come "—". Lo stato RUNNING non basta il battito del runner: se nessun giro
 * del Brain e' stato registrato da troppo tempo, la schermata lo dice invece di mostrare un RUNNING rassicurante.
 */
export const num = v => (v === null || v === undefined || v === '' || typeof v === 'boolean' || !Number.isFinite(Number(v))
  ? null : Number(v));

const TONES = { ok: '#4ade80', wait: '#fbbf24', stop: '#f87171', idle: '#94a3b8' };

/** "3 min fa", "1 h 05 min fa". Ora nel futuro (orologi sfasati) -> "ora". */
export function ago(ms, nowMs) {
  if (!Number.isSafeInteger(ms) || ms <= 0 || !Number.isSafeInteger(nowMs)) return null;
  const s = Math.floor((nowMs - ms) / 1000);
  if (s < 60) return 'ora';
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min fa`;
  const h = Math.floor(m / 60);
  return `${h} h ${String(m % 60).padStart(2, '0')} min fa`;
}

/** Ultimo giro decisionale registrato nel journal: il piu' recente tra valutazione del Guardian e decisioni. */
export function lastRoundMs(run) {
  const values = [run?.guardian?.as_of_ms, ...(run?.decisions || []).map(d => d?.ts_ms)]
    .filter(v => Number.isSafeInteger(v) && v > 0);
  return values.length ? Math.max(...values) : null;
}

/** Oltre questo ritardo un runner "running" e' sospetto: due giri completi piu' 5 minuti (le chiamate AI durano minuti). */
export function staleLimitMs(run) {
  const cycle = num(run?.config?.cycle_minutes);
  return ((cycle && cycle > 0 ? cycle : 30) * 2 + 5) * 60 * 1000;
}

/** Stato leggibile del bot: { key, label, color, detail }. label e' sempre una parola maiuscola da badge. */
export function botStatus(run, nowMs) {
  const card = (key, label, tone, detail) => ({ key, label, color: TONES[tone], detail });
  if (!run || run.available !== true) {
    return run?.reason === 'not_started'
      ? card('not_started', 'NON AVVIATO', 'idle', 'Nessun giro registrato in questa run.')
      : card('not_prepared', 'NON PREPARATO', 'idle', 'La run PAPER non e’ ancora stata preparata.');
  }
  if (run.paused === true) {
    return card('paused', 'PAUSA', 'wait',
      'Nessuna nuova apertura. Le posizioni aperte restano gestite da stop e obiettivo.');
  }
  if (run.state === 'halted') {
    return card('halted', 'FERMO', 'stop',
      'Il runner si e’ fermato (mandato, tetto di spesa o limite di perdita): nessuna nuova apertura.');
  }
  if (run.state === 'running') {
    const last = lastRoundMs(run);
    if (last === null) return card('running_wait', 'RUNNING', 'ok', 'In attesa del primo giro decisionale.');
    const when = ago(last, nowMs);
    if (nowMs - last > staleLimitMs(run)) {
      return card('stale', 'RUNNING', 'wait',
        `Nessun giro recente: ultimo giro ${when}. Verifica il servizio se non riparte.`);
    }
    return card('running', 'RUNNING', 'ok', `Ultimo giro ${when}.`);
  }
  return card('unknown', 'STATO N/D', 'idle', 'Stato del runner non disponibile.');
}

/** Equity da mostrare: a mercato (Guardian, ultimo giro) se disponibile, altrimenti contabile. Mai dedotta. */
export function equityView(run) {
  const g = run?.guardian || {};
  const market = num(g.equity);
  const settled = num(run?.settled_equity);
  const initial = num(run?.initial_equity);
  const value = market !== null ? market : settled;
  return {
    value, basis: market !== null ? 'market' : settled !== null ? 'settled' : null, settled, initial,
    asOfMs: market !== null && Number.isSafeInteger(g.as_of_ms) ? g.as_of_ms : null,
    total: value !== null && initial ? value - initial : null,
    totalPct: value !== null && initial ? (value - initial) / initial * 100 : null,
    unrealized: num(g.unrealized),
    session: market !== null && num(g.session_start_equity) !== null ? market - num(g.session_start_equity) : null,
  };
}

export const GUARDIAN_STATES = {
  NORMAL: ['Normale', '#4ade80', 'Limiti ordinari: nessuna restrizione aggiuntiva.'],
  SELECTIVE: ['Selettivo', '#38bdf8', 'Profitto di sessione da difendere: nuove aperture con rischio ridotto.'],
  PROTECTED: ['Protetto', '#fbbf24', 'Poco margine sopra il floor: solo setup ad alta confidenza, nessun rientro.'],
  LOCKED: ['Bloccato', '#f87171', 'Nuove aperture bloccate per il resto della sessione. Le posizioni aperte restano gestite.'],
};

export const GUARDIAN_REASONS = {
  floor_armed: 'floor armato', floor_budget_low: 'margine sul floor ridotto', floor_budget: 'margine sul floor esaurito',
  below_floor: 'equity sotto il floor', session_loss: 'perdita di sessione', global_drawdown: 'drawdown globale',
  drawdown_half: 'drawdown: rischio dimezzato', data_fault: 'dati di mercato mancanti', guardian_error: 'errore del Guardian',
};

const own = (t, k) => (typeof k === 'string' && Object.prototype.hasOwnProperty.call(t, k) ? t[k] : undefined);

/** Guardian leggibile; un codice sconosciuto non diventa mai testo libero. */
export function guardianView(run) {
  const g = run?.guardian;
  const s = g ? own(GUARDIAN_STATES, g.state) : undefined;
  if (!s) return null;
  return {
    state: g.state, label: s[0], color: s[1], detail: s[2],
    reasons: (Array.isArray(g.reasons) ? g.reasons : []).map(r => own(GUARDIAN_REASONS, r)).filter(Boolean),
    floor: num(g.floor), peak: num(g.peak_equity), giveback: num(g.giveback), budget: num(g.budget),
    riskCap: g.state === 'NORMAL' ? null : num(g.risk_cap), openRisk: num(g.open_risk), asOfMs: g.as_of_ms ?? null,
  };
}
