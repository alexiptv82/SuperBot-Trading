import React from 'react';

const SYMBOL = /^[A-Za-z0-9]{1,16}$/;

/** Read-only: chiusure PAPER nel conto ma non ancora provate in storico e learning. Nessun importo inventato. */
export default function ClaimReconciliationNotice({ recon, notStarted = false }) {
  const valid = recon && typeof recon === 'object' && ['ok', 'pending', 'conflict', 'unknown'].includes(recon.state);
  const state = valid ? recon.state : 'unknown';
  if (state === 'ok') return null;
  if (state === 'unknown' && notStarted) return null;
  const symbols = valid && Array.isArray(recon.affected_symbols)
    ? recon.affected_symbols.filter(s => typeof s === 'string' && SYMBOL.test(s)).slice(0, 8) : [];
  const count = (v) => (Number.isInteger(v) && v >= 0 ? v : null);
  const pending = valid ? count(recon.pending_count) : null;
  const conflict = valid ? count(recon.conflict_count) : null;
  const title = {
    pending: '⚠️ Chiusure PAPER in riconciliazione',
    conflict: '⛔ Conflitto contabile: serve intervento umano',
    unknown: '⚠️ Stato di riconciliazione non verificabile',
  }[state];
  const detail = {
    pending: 'Il conto ha registrato la chiusura, ma storico e learning non la confermano ancora. Il bot riprova da solo; nel frattempo nuove aperture e DCA restano bloccate.',
    conflict: 'Nei registri esiste già una chiusura diversa per la stessa posizione. Il bot non scrive nulla e non risolve da solo: nuove aperture e DCA restano bloccate e il reset del portafoglio è rifiutato.',
    unknown: 'Non è possibile verificare se ci siano chiusure ancora da riconciliare. Considera conto e P&L come non confermati.',
  }[state];
  return <div data-testid="claim-reconciliation-notice" role="alert"
    style={{ padding: 10, marginTop: 11, border: `1px solid ${state === 'conflict' ? '#f87171' : '#fbbf24'}`,
      borderRadius: 9, background: state === 'conflict' ? '#3b1a1a' : '#312a15',
      color: state === 'conflict' ? '#fecaca' : '#fde68a', fontSize: 12 }}>
    <strong>{title}</strong>
    <div>{detail}</div>
    <div style={{ marginTop: 4 }}>
      Equity, P&amp;L e trade chiusi mostrati qui possono includere chiusure non ancora definitive.
      I valori non vengono azzerati né ricalcolati.
    </div>
    {(pending != null || conflict != null) && <div>
      In attesa: {pending ?? '—'} · In conflitto: {conflict ?? '—'}
    </div>}
    {symbols.length > 0 && <div>Simboli coinvolti: {symbols.join(', ')}</div>}
  </div>;
}
