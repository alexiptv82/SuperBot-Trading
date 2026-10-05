import React, { useState, useEffect } from 'react';
import { botAPI } from '../api';
export default function Trades() {
  const [trades, setTrades] = useState([]);
  useEffect(() => { botAPI.getTrades().then(r => setTrades(r.data)).catch(console.error); }, []);
  const pnlColor = (v) => v > 0 ? '#4ade80' : v < 0 ? '#f87171' : '#94a3b8';
  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '16px' }}>💹 Storico Trade</h1>
      {trades.length === 0 ? (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: '40px' }}>
          Nessun trade ancora. Avvia il bot dalla Dashboard.
        </div>
      ) : trades.map(t => (
        <div key={t.id} style={{
          background: '#1e293b', borderRadius: '12px', padding: '14px',
          marginBottom: '10px', border: '1px solid #334155'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{
                padding: '2px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: 'bold',
                background: t.side === 'long' ? '#166534' : '#7f1d1d', color: 'white'
              }}>{t.side?.toUpperCase()}</span>
              <span style={{ fontWeight: 'bold' }}>{t.symbol}</span>
              <span style={{ color: '#94a3b8', fontSize: '12px' }}>x{t.leverage}</span>
            </div>
            <span style={{
              padding: '2px 8px', borderRadius: '6px', fontSize: '11px',
              background: t.status === 'open' ? '#1e40af' : '#1e293b',
              border: '1px solid #334155', color: '#94a3b8'
            }}>{t.status}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
            <div>
              <div style={{ color: '#94a3b8' }}>Entrata</div>
              <div>${t.entry_price?.toFixed(2)}</div>
            </div>
            <div>
              <div style={{ color: '#94a3b8' }}>Uscita</div>
              <div>{t.exit_price ? `$${t.exit_price?.toFixed(2)}` : '--'}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ color: '#94a3b8' }}>P&L</div>
              <div style={{ fontWeight: 'bold', color: pnlColor(t.pnl) }}>
                {t.pnl ? `${t.pnl > 0 ? '+' : ''}${t.pnl.toFixed(2)}$` : '--'}
              </div>
            </div>
          </div>
          {t.close_reason && (
            <div style={{ marginTop: '6px', fontSize: '11px', color: '#64748b' }}>
              Chiuso: {t.close_reason?.toUpperCase()} | {t.trade_type}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
