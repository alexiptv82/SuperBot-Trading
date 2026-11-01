import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { longShadowAPI } from '../api';

const consumerLabels = { hawk: '🦅 Falco', bull: '🐂 Toro', brain: '🧠 Brain' };
const roles = { hawk: 'Regole classiche · osservazione', bull: 'Regole classiche · osservazione', brain: 'Consulente AI non vincolante' };
const boxStyle = { background: '#1e293b', padding: 16, borderRadius: 14, border: '1px solid #334155', marginBottom: 12 };
const muted = { fontSize: 12, color: '#94a3b8', lineHeight: 1.5 };

export function LongShadowStatus({ data, error }) {
  if (error || !data) {
    return <section role="status" style={boxStyle}>
      <strong>LONG Shadow · non disponibile</strong>
      <p style={muted}>La pagina è in sola osservazione. Nessuna decisione del LONG può controllare gli ordini.</p>
    </section>;
  }
  const consumers = data.consumers || {};
  const disabled = data.engine_running !== true || data.enabled !== true || data.can_execute_orders !== true;
  return <section aria-label="Stato del modulo LONG Shadow">
    <div style={{ ...boxStyle, borderColor: '#64748b' }}>
      <strong>LONG Shadow — {data.engine_running === true ? 'motore segnalato attivo' : 'motore non avviato'}</strong>
      <p style={muted}>
        Solo osservazione · {disabled ? 'ordini LONG da questo modulo disabilitati' : 'verificare autorizzazioni'}
        {' · '}PAPER non autorizzato.
      </p>
      <p style={{ ...muted, color: '#fbbf24' }}>
        I consigli non attivano trade, non bloccano gli SHORT e non modificano il capitale.
      </p>
    </div>
    {['hawk', 'bull', 'brain'].map(id => {
      const consumer = consumers[id];
      const walletOk = consumer?.wallet_status === 'ok';
      const advice = consumer?.advice;
      const decision = consumer?.advisory_status === 'unverified_external_record' && advice
        ? advice.decision : null;
      return <div key={id} style={boxStyle}>
        <h2 style={{ fontSize: 17, margin: '0 0 4px' }}>{consumerLabels[id]}</h2>
        <p style={{ ...muted, marginTop: 0 }}>{roles[id]}</p>
        <div style={{ ...muted, color: walletOk ? '#86efac' : '#fbbf24' }}>
          Wallet: {walletOk ? 'letto in sola lettura' : 'non disponibile o non verificato'}
        </div>
        {walletOk && Object.entries(consumer.positions || {}).map(([symbol, flags]) =>
          <div key={symbol} style={{ ...muted, marginTop: 3 }}>
            {symbol}: {flags.short_open ? 'SHORT aperto' : flags.long_open ? 'LONG aperto' : 'nessuna posizione sul simbolo'}
          </div>)}
        <div style={{ marginTop: 10, ...muted, color: decision === 'CANDIDATE' ? '#fbbf24' : '#cbd5e1' }}>
          Consiglio LONG: {decision === 'CANDIDATE' ? 'CANDIDATE · NON eseguibile' :
            decision === 'NO_TRADE' ? 'NO_TRADE · nessuna apertura' : 'non disponibile'}
        </div>
        {decision && <p style={muted}>
          {advice.symbol} · {advice.setup} · {(advice.reasons || []).join(', ') || 'nessun dettaglio'}
          <span style={{ display: 'block', color: '#64748b' }}>Record esterno, non certificato come segnale live.</span>
        </p>}
        {!walletOk && <p style={{ ...muted, color: '#fbbf24' }}>
          Il wallet assente non viene interpretato come vuoto.
        </p>}
      </div>;
    })}
  </section>;
}

export default function LongShadowDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    const poll = async () => {
      try {
        const response = await longShadowAPI.getStatus(controller.signal);
        if (!controller.signal.aborted) { setData(response.data); setError(false); }
      } catch (_) {
        if (!controller.signal.aborted) { setError(true); setData(null); }
      }
      if (!controller.signal.aborted) timer = setTimeout(poll, 30000);
    };
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);
  return <main style={{ padding: 16, maxWidth: 600, margin: '0 auto', color: '#f1f5f9' }}>
    <h1 style={{ fontSize: 22, marginBottom: 4 }}>🔎 Motore LONG · Shadow</h1>
    <p style={muted}>Diagnostica separata da Brain, Falco e Toro. Nessun controllo operativo.</p>
    <LongShadowStatus data={data} error={error} />
    <Link to="/" style={{ color: '#38bdf8', fontSize: 13 }}>Torna alla dashboard PAPER</Link>
  </main>;
}
