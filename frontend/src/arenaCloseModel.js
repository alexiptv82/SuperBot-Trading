/** Chiusura manuale PAPER dell'Arena: solo rotte dedicate per AI, mai /api/v3/brain/close. */
export const ARENA_CLOSE_PROVIDERS = Object.freeze(['deepseek', 'qwen', 'minimax']);

export const CLOSE_REASONS = Object.freeze([
  { id: 'profit_protection', label: 'Protezione del profitto' },
  { id: 'loss_reduction', label: 'Riduzione della perdita' },
  { id: 'trend_change', label: 'Cambio di tendenza' },
  { id: 'other', label: 'Altro' },
  { id: 'unspecified', label: 'Preferisco non indicarlo' },
]);
export const NOTE_MAX = 280;

const ERRORS = Object.freeze({
  exit_service_not_ready: 'Il servizio di uscita PAPER di questa AI non è pronto. Riprova tra un minuto.',
  request_in_progress: 'Una chiusura è già in corso per questa AI: attendi il risultato.',
  position_not_open: 'Questa posizione non è più aperta.',
  position_already_closed: 'Questa posizione è già stata chiusa.',
  request_id_reused: 'Richiesta non valida. Aggiorna la pagina.',
  close_not_confirmed: 'La chiusura non è confermata: la motivazione non può essere registrata.',
  already_annotated: 'La motivazione di questa chiusura è già registrata.',
  invalid_note: 'Nota non valida (massimo 280 caratteri, una riga).',
  invalid_reason: 'Motivazione non valida.',
  arena_run_not_available: 'Il portafoglio PAPER di questa AI non è disponibile.',
  arena_bridge_unavailable: 'Canale di chiusura PAPER non disponibile.',
  single_position_only: 'Puoi chiudere una sola posizione alla volta.',
});

export function arenaErrorText(err) {
  const code = err?.response?.data?.detail?.code;
  return ERRORS[code] || 'Chiusura PAPER non disponibile. Nessuna operazione presunta.';
}

const FAILED = Object.freeze({
  price_unavailable: 'Prezzo non disponibile: la posizione resta aperta.',
  expired: 'Richiesta scaduta: la posizione resta aperta.',
  position_not_open: 'La posizione non era più aperta.',
  exit_service_did_not_confirm: 'Il servizio di uscita non ha confermato: la posizione non risulta chiusa.',
});

/** Testo dello stato terminale: si basa solo su ciò che il journal ha confermato. */
export function statusText(s) {
  if (!s || typeof s !== 'object') return null;
  if (s.status === 'pending') return 'Richiesta inviata: in attesa della conferma del servizio di uscita…';
  if (s.status === 'closed') return 'Chiusura PAPER confermata dal journal.';
  if (s.status === 'closed_by_other_exit') {
    return 'La posizione è stata chiusa prima da stop o target (' + (s.exit_reason || 'uscita automatica') + ').';
  }
  if (s.status === 'failed' || s.status === 'unconfirmed') {
    return FAILED[s.code] || 'Chiusura non riuscita: la posizione non risulta chiusa.';
  }
  return null;
}

export function newRequestId(cryptoImpl = typeof window !== 'undefined' ? window.crypto : undefined) {
  const bytes = new Uint8Array(12);
  if (cryptoImpl && typeof cryptoImpl.getRandomValues === 'function') cryptoImpl.getRandomValues(bytes);
  else for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  return 'arena-' + Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}

export function validNote(note) {
  if (note === '' || note == null) return true;
  return typeof note === 'string' && note.trim().length > 0 && note.length <= NOTE_MAX &&
    !Array.from(note).some(c => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127);
}

export function arenaCloseUiEnabled(env = process.env) {
  return env.REACT_APP_ARENA_MANUAL_CLOSE === '1';
}
