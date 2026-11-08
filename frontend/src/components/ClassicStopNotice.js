import React from 'react';

/** Quote health is not a stop certificate and does not describe the running classic engine. */
export default function ClassicStopNotice({ health, openPositions = 0 }) {
  if (health?.scope === 'classic_runner_15m_ohlc') {
    const blocked = Array.isArray(health.blocked_symbols) ? health.blocked_symbols.slice(0, 8) : [];
    if (openPositions === 0 && blocked.length === 0) return null;
    // 'observed' is a periodic diagnostic, never a certified stop or exchange execution.
    const observed = health.state === 'observed' && health.alarm === false &&
      health.stop_certified === false && openPositions > 0;
    const stateMessages = {
      observed: 'Ultimo ciclo di controllo OHLC 15m completato',
      degraded: 'Dati di mercato o controlli stop non completi',
      stale: 'Controllo stop o heartbeat troppo vecchio',
      unverified: 'Protezione stop del bot operativo non verificabile',
    };
    const message = observed ? stateMessages.observed
      : (health.state === 'observed'
          ? stateMessages.unverified
          : (stateMessages[health.state] || stateMessages.unverified));
    return <div data-testid="classic-running-stop-notice" role={observed ? 'status' : 'alert'}
      style={{ padding: 10, marginTop: 11, border: '1px solid #fbbf24', borderRadius: 9,
        background: '#312a15', color: '#fde68a', fontSize: 12 }}>
      <strong>{observed ? 'Controllo OHLC PAPER — ultimo ciclo' : '⚠️ Allarme controllo stop PAPER'}</strong>
      <div>{message}</div>
      {blocked.length > 0 && <div>Nuovi ingressi/DCA senza prezzo idoneo: {blocked.join(', ')}</div>}
      <div style={{ marginTop: 4 }}>
        Falco e Toro controllano gli estremi delle candele 15m a intervalli di circa 15 minuti
        (scalp) o 30 minuti (altro), più la durata del ciclo. Non è monitoraggio continuo,
        non è un ordine stop su exchange e il wick della candela di ingresso non viene rigiocato.
      </div>
      <div>Controllo del feed non equivale a stop-loss certificato.</div>
    </div>;
  }
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
  // A partial/inconsistent UI payload must never describe missing price coverage as available.
  const message = state === 'covered' && !hasQuoteCoverage
    ? 'Copertura prezzi non dimostrata: dati incoerenti o incompleti'
    : (labels[state] || labels.unverified);
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

