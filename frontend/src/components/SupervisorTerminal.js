/** S2 Brain PAPER terminal: a read-only view of recorded decisions and preflight skips.
 * Not a live execution control. Data may be incomplete until S0/S1 are integrated.
 */
import React, { useEffect, useState } from 'react';
import API from '../api';

const PANEL = { background: '#172338', border: '1px solid #32465f', borderRadius: 14,
  padding: 14, margin: '10px 0' };
const NOTE = { color: '#b9c9dc', fontSize: 12 };
const LABELS = Object.freeze({
  brain_wait: 'Il Brain ha scelto di aspettare',
  ai_unavailable: 'AI non disponibile',
  risk_blocked: 'Operazione bloccata dal rischio',
  market_or_execution_gate: 'Condizione di mercato o esecuzione non superata',
  mandate_blocked: 'Mandato non autorizzato',
  approved_open: 'Apertura approvata',
  other_recorded_decision: 'Decisione registrata, motivazione non completa',
  preflight_skipped: 'Candidato scartato prima dell’analisi AI',
});
const SKIP = Object.freeze({
  already_open: 'Posizione già aperta', no_market_rules: 'Regole mercato mancanti',
  feed_error: 'Dati mercato non accessibili', view_error: 'Indicatori non disponibili',
  data_unavailable: 'Dati insufficienti', price_error: 'Prezzo non disponibile',
  cycle_error: 'Errore del ciclo',
});
const REASONS = Object.keys(LABELS);

export function decisionReason(reason) {
  return typeof reason === 'string' && Object.prototype.hasOwnProperty.call(LABELS, reason)
    ? LABELS[reason] : 'Motivazione non disponibile';
}
export function skipReason(reason) {
  return typeof reason === 'string' && Object.prototype.hasOwnProperty.call(SKIP, reason)
    ? SKIP[reason] : 'Scarto non classificato';
}
export function timestampUTC(ms) {
  return Number.isInteger(ms) && ms > 0 && ms <= 8640000000000000
    ? new Date(ms).toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC')
    : 'Orario non disponibile';
}
const amount = (num, unit) => num === null || num === undefined ? 'Non registrato' : `${num} ${unit}`;
const kind = k => ({OPEN:'Apertura',NO_TRADE:'Nessuna operazione',HOLD:'Mantieni',
  CLOSE:'Chiusura',MODIFY_STOP:'Modifica stop',SKIPPED:'Scartato'})[k] || 'Altro';

export function SupervisorResult({ data }) {
  if (!data) return <p role="status">Nessun dato disponibile.</p>;
  if (data.state === 'not_started') return <p role="status">Il registro Brain non è ancora stato avviato.</p>;
  const cards = Array.isArray(data.decisions) ? data.decisions : [];
  return <section aria-label="Registro delle decisioni" style={{ marginTop: 14 }}>
    {data.source_window_limited && <p role="note" style={NOTE}>Risultati parziali: il registro mostra solo una finestra recente degli eventi.</p>}
    {data.has_more && <p style={NOTE}>Sono presenti altre decisioni in questa finestra.</p>}
    {cards.length === 0 ? <p role="status">Nessuna decisione corrispondente ai filtri.</p> : cards.map(c =>
      <article key={c.id} style={PANEL}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'baseline', gap:10 }}>
          <strong style={{ color:'#e6f3ff', fontSize:15 }}>{c.symbol || 'Simbolo non registrato'} · {kind(c.kind)}</strong>
          <span style={{ color: c.reason_class === 'risk_blocked' ? '#fda4af' : '#a5d8ff', fontSize:12 }}>{c.status || '—'}</span>
        </div>
        <div style={NOTE}>{timestampUTC(c.at_ms)}</div>
        <p style={{ color:'#d9e5f5', fontSize:13 }}>{decisionReason(c.reason_class)}</p>
        {c.reason_class === 'preflight_skipped' && <p style={NOTE}>{skipReason(c.reason_code)}</p>}
        <div style={NOTE}>Strategia: {c.strategy_id || 'Non attribuita'} · Regime: {c.regime || 'Non noto'}</div>
        <details style={{ marginTop:10 }}>
          <summary style={{ cursor:'pointer', fontWeight:700, color:'#7dd3fc' }}>Dettagli verificabili</summary>
          <div style={{ ...NOTE, paddingTop:10 }}>
            <p>Esito netto: {amount(c.net_bp,'bp')} · PnL realizzato: {amount(c.realized_pnl,'USDT')}</p>
            <p>Stato evidenze: {c.evidence_status === 'recorded' || c.evidence_status === 'preflight_recorded'
              ? 'Fotografia registrata' : c.evidence_status === 'ambiguous' ? 'Collegamento ambiguo'
                : c.evidence_status === 'inconsistent' ? 'Collegamento incoerente: dati non attribuiti'
                : 'Non registrate'}</p>
            {c.evidence && <>
              <p>Equity al momento: {amount(c.evidence.equity,'USDT')} · Rischio stimato allo stop: {amount(c.evidence.risk_at_stop,'USDT')}</p>
              <p>Budget di rischio: {amount(c.evidence.risk_budget,'USDT')}</p>
              <p>Digest mercato: {c.evidence.market_sha256 || 'Non registrato'}</p>
              {(c.evidence.timeframes || []).map(tf =>
                <div key={tf.tf} style={{ margin:'8px 0', borderTop:'1px solid #374960', paddingTop:6 }}>
                  {tf.tf} · {tf.status} · {tf.regime || 'Regime non noto'} · RSI {tf.rsi || '—'} · ADX {tf.adx || '—'}
                </div>)}
            </>}
            <p>Memoria richiamata e regola d’invalidazione: non ancora registrate in modo verificabile.</p>
            <p style={{ overflowWrap:'anywhere' }}>ID evento: {c.id}</p>
          </div>
        </details>
      </article>)}
  </section>;
}

export default function SupervisorTerminal() {
  const [symbol, setSymbol] = useState('');
  const [reason, setReason] = useState('');
  const [request, setRequest] = useState({ symbol:'', reason:'' });
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');
  const [updated, setUpdated] = useState(null);
  const validSymbol = !symbol || /^[A-Z0-9][A-Z0-9/_:.-]{0,31}$/.test(symbol);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const params = {limit: 50};
        if (request.symbol) params.symbol = request.symbol;
        if (request.reason) params.reason = request.reason;
        const response = await API.get('/api/v3/brain/decision-timeline', {params});
        if (active) { setResult(response.data); setError(''); setUpdated(Date.now()); }
      } catch (e) {
        if (active) {
          setResult(null);
          setError(e?.response?.status === 503
            ? 'Supervisore non ancora integrato o dati temporaneamente non disponibili.'
            : 'Impossibile leggere il registro. Verifica la connessione.');
        }
      } finally { if (active) setBusy(false); }
    };
    setBusy(true);
    load();
    const timer = setInterval(load, 30000);
    return () => { active = false; clearInterval(timer); };
  }, [request.symbol, request.reason]);

  return <main aria-label="Terminale Supervisore Brain" style={{ minHeight:'100vh', background:'#0b1323',
    color:'#e6f3ff', padding:'16px 12px 100px', boxSizing:'border-box', maxWidth:650,
    margin:'auto', fontFamily:'system-ui,sans-serif' }}>
    <header>
      <p style={{ color:'#7dd3fc',fontSize:11,fontWeight:800,letterSpacing:1.8 }}>SUPERBOT V3 · PAPER · SOLA LETTURA</p>
      <h1 style={{fontSize:24,margin:'6px 0'}}>Registro decisioni Brain</h1>
      <p style={NOTE}>Mostra decisioni ed evidenze registrate, non spiegazioni ricostruite dopo il risultato.</p>
    </header>
    <form onSubmit={e=>{e.preventDefault(); if(validSymbol) setRequest({symbol,reason}); }}
      style={{...PANEL,display:'grid',gap:10}}>
      <label htmlFor="supervisor-symbol">Simbolo</label>
      <input id="supervisor-symbol" value={symbol} onChange={e=>setSymbol(e.target.value.toUpperCase())}
        placeholder="BTCUSDT (vuoto = tutti)" maxLength={32} aria-invalid={!validSymbol}
        style={{fontSize:16,padding:10,borderRadius:8,background:'#eaf3fa',color:'#13243b'}} />
      <label htmlFor="supervisor-reason">Motivo</label>
      <select id="supervisor-reason" value={reason} onChange={e=>setReason(e.target.value)}
        style={{fontSize:16,padding:10,borderRadius:8}}>
        <option value="">Tutte le decisioni</option>
        {REASONS.map(r=><option key={r} value={r}>{decisionReason(r)}</option>)}
      </select>
      <button type="submit" disabled={!validSymbol} style={{border:0,borderRadius:9,padding:12,
        color:'#081525',background:'#7dd3fc',fontWeight:700}}>Applica filtri</button>
      {!validSymbol && <p role="alert" style={NOTE}>Simbolo non valido.</p>}
    </form>
    {updated && <p style={NOTE}>Ultima lettura: {timestampUTC(updated)} · Aggiornamento ogni 30 secondi</p>}
    {busy && <p role="status">Caricamento delle decisioni…</p>}
    {error && <p role="alert">{error}</p>}
    {!busy && !error && <SupervisorResult data={result} />}
  </main>;
}
