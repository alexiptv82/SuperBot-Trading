import React, { useState, useEffect } from 'react';
import { botAPI } from '../api';
const eventColor = {
  bot_start: '#4ade80', bot_stop: '#f87171',
  trade_open: '#38bdf8', trade_close: '#a78bfa',
  risk_alert: '#fb923c', error: '#f87171',
};
export default function Logs() {
  const [logs, setLogs] = useState([]);
  useEffect(() => {
    const fetchLogs = () => botAPI.getLogs().then(r => setLogs(r.data)).catch(console.error);
    fetchLogs(); const t = setInterval(fetchLogs, 15000); return () => clearInterval(t);
  }, []);
  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '16px' }}>📋 Log di Sistema</h1>
      {logs.length === 0 ? (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: '40px' }}>Nessun log disponibile.</div>
      ) : logs.map(l => (
        <div key={l.id} style={{
          background: '#1e293b', borderRadius: '10px', padding: '12px',
          marginBottom: '8px', border: '1px solid #334155',
          borderLeft: `3px solid ${eventColor[l.event_type] || '#475569'}`
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={{
              fontSize: '11px', fontWeight: 'bold',
              color: eventColor[l.event_type] || '#94a3b8'
            }}>{l.event_type?.toUpperCase()}</span>
            <span style={{ fontSize: '11px', color: '#64748b' }}>
              {new Date(l.timestamp).toLocaleTimeString('it-IT')}
            </span>
          </div>
          <div style={{ fontSize: '13px', color: '#cbd5e1' }}>{l.message}</div>
          {l.symbol && <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>{l.symbol}</div>}
        </div>
      ))}
    </div>
  );
}
