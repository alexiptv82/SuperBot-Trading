import React from 'react';

/** Quote health is not a stop certificate and does not describe the running classic engine. */
export default function ClassicStopNotice({ health, openPositions = 0 }) {
  if (openPositions === 0) return null;
  const state = health?.state || 'unverified';
  const labels = {
    covered: 'Prezzi recenti disponibili (ultima candela 1m conclusa)',
    partial: 'Solo alcune posizioni hanno prezzi verificati',
    blind: 'Nessuna posizione ha un prezzo verificato',
    blocked: 'Monitor bloccato: verifica necessaria',
    stale: 'Il segnale del monitor è scaduto',
    off: 'Monitor automatico di manutenzione spento',
    idle: 'Monitor senza posizioni: dati non coerenti',
    telemetry_failed: 'Telemetria non disponibile',
    unverified: 'Protezione stop non verificata',
  };
  const hasQuoteCoverage = state === 'covered' && health?.quote_coverage === true;
  const message = labels[state] || labels.unverified;
  const reason = health?.reason === 'maintenance_worker_not_active'
    ? 'Il monitor RC80 è valido solo in manutenzione: gli stop del motore operativo vanno verificati separatamente.'
    : 'Il monitor RC80 riguarda soltanto la manutenzione PAPER.';
  return <div data-testid="classic-stop-notice" role={hasQuoteCoverage ? 'status' : 'alert'}
    style={{ padding: 10, marginTop: 11, border: '1px solid #fbbf24', borderRadius: 9,
      background: '#312a15', color: '#fde68a', fontSize: 12 }}>
    <strong>{hasQuoteCoverage ? 'Monitor prezzi PAPER' : '⚠️ Protezione stop da verificare'}</strong>
    <div>{message}</div>
    <div style={{ marginTop: 4 }}>{reason} Le chiusure automatiche usano soltanto la chiusura della candela da 1 minuto:
      un attraversamento intraminuto dello stop può non causare alcuna uscita.</div>
    <div>Copertura prezzi non equivale a stop-loss certificato.</div>
  </div>;
}

