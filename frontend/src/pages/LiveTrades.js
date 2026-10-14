import React, { useState, useEffect, useCallback } from 'react';
import { deskAPI } from '../api';

const fmt = (v, d = 2) => { const n = parseFloat(v); return isNaN(n) ? '--' : n.toFixed(d); };
const fmtMs = (ms) => {
  if (!ms) return '--';
  return new Date(ms).toLocaleString('it-IT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};
const pnlColor = (v) => { const n = parseFloat(v); if (isNaN(n) || n === 0) return '#94a3b8'; return n > 0 ? '#4ade80' : '#f87171'; };
const sign = (v) => { const n = parseFloat(v); if (isNaN(n)) return ''; return n >= 0 ? '+' : ''; };

const BOTS = [
  { key: 'hawk', label: '🦅 Hawk', color: '#0ea5e9' },
  { key: 'bull', label: '🐂 Bull', color: '#f59e0b' },
];

function BotSection({ bot, data }) {
  const [showOpen, setShowOpen] = useState(true);

  if (!data) return (
    <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '14px', padding: '16px 20px', marginBottom: '16px' }}>
      <div style={{ color: '#475569', fontSize: '13px' }}>{bot.label} — dati non disponibili</div>
    </div>
  );

  const { positions = [], available } = data;

  return (
    <div style={{
      background: '#0f172a',
      border: `1px solid ${bot.color}33`,
      borderRadius: '14px',
      overflow: 'hidden',
      marginBottom: '16px',
    }}>
      {/* Header bot */}
      <div style={{
        padding: '14px 20px',
        borderBottom: '1px solid #1e293b',
        background: `linear-gradient(135deg, ${bot.color}12 0%, transparent 60%)`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ fontWeight: 800, fontSize: '15px', color: '#f1f5f9' }}>{bot.label}</div>
        <div style={{ fontSize: '12px', color: '#64748b' }}>
          {positions.length} posizioni aperte
        </div>
      </div>

      {/* Posizioni aperte */}
      {positions.length === 0 ? (
        <div style={{ padding: '20px', textAlign: 'center', color: '#475569', fontSize: '13px' }}>
          Nessuna posizione aperta al momento
        </div>
      ) : (
        <div>
          <button
            onClick={() => setShowOpen(s => !s)}
            style={{
              width: '100%', padding: '10px 20px', background: 'none',
              border: 'none', borderBottom: '1px solid #1e293b',
              cursor: 'pointer', display: 'flex', justifyContent: 'space-between',
              alignItems: 'center', color: '#94a3b8', fontSize: '12px',
            }}>
            <span>Posizioni aperte ({positions.length})</span>
            <span>{showOpen ? '▲' : '▼'}</span>
          </button>
          {showOpen && (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr style={{ color: '#475569', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    {['Simbolo', 'Lato', 'Leva', 'Margine', 'P&L non real.', 'Aperto'].map(h => (
                      <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #1e293b' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p, i) => (
                    <tr key={i} style={{ background: i % 2 === 0 ? 'transparent' : '#0f1829' }}>
                      <td style={{ padding: '9px 12px', color: '#e2e8f0', fontWeight: 700 }}>{p.symbol}</td>
                      <td style={{ padding: '9px 12px' }}>
                        <span style={{
                          fontSize: '10px', fontWeight: 700,
                          color: p.side === 1 ? '#4ade80' : '#f87171',
                          background: p.side === 1 ? 'rgba(74,222,128,0.12)' : 'rgba(248,113,113,0.12)',
                          borderRadius: '4px', padding: '2px 6px',
                        }}>{p.side === 1 ? 'LONG' : 'SHORT'}</span>
                      </td>
                      <td style={{ padding: '9px 12px', color: '#94a3b8' }}>{p.leverage}x</td>
                      <td style={{ padding: '9px 12px', color: '#94a3b8', fontVariantNumeric: 'tabular-nums' }}>${fmt(p.margin, 0)}</td>
                      <td style={{ padding: '9px 12px', color: pnlColor(p.unrealized_pnl), fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                        {sign(p.unrealized_pnl)}${fmt(p.unrealized_pnl, 2)}
                      </td>
                      <td style={{ padding: '9px 12px', color: '#475569', fontSize: '11px' }}>{fmtMs(p.open_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function LiveTrades() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await deskAPI.getLiveOverview();
      setOverview(data);
      setLastUpdate(new Date());
      setError(null);
    } catch (e) {
      setError(e?.message || 'Errore caricamento dati live');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000); // aggiorna ogni 15s
    return () => clearInterval(t);
  }, [load]);

  // P&L totale delle posizioni aperte
  const totalUnrealized = overview
    ? (overview.hawk?.positions || []).concat(overview.bull?.positions || [])
        .reduce((s, p) => s + (parseFloat(p.unrealized_pnl) || 0), 0)
    : 0;

  return (
    <div style={{ padding: '16px', maxWidth: '900px', margin: '0 auto' }}>

      {/* Intestazione */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '8px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '18px', fontWeight: 900, color: '#f1f5f9' }}>🔴 Trade Live</span>
            <span style={{
              fontSize: '10px', fontWeight: 700, letterSpacing: '0.1em',
              color: '#f87171', background: 'rgba(239,68,68,0.12)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: '999px', padding: '3px 10px', textTransform: 'uppercase',
            }}>● LIVE · BitGet Futures</span>
          </div>
          <div style={{ fontSize: '12px', color: '#475569', marginTop: '4px' }}>Posizioni aperte in tempo reale</div>
        </div>
        {overview && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '11px', color: '#475569' }}>P&L non realizzato totale</div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: pnlColor(totalUnrealized), fontVariantNumeric: 'tabular-nums' }}>
              {sign(totalUnrealized)}${fmt(totalUnrealized, 2)}
            </div>
          </div>
        )}
      </div>

      {loading && (
        <div style={{ padding: '40px', textAlign: 'center', color: '#475569' }}>Caricamento posizioni live…</div>
      )}

      {error && (
        <div style={{ margin: '0 0 16px', padding: '14px 18px', background: '#1e293b', border: '1px solid #dc2626', borderRadius: '12px', color: '#fca5a5', fontSize: '13px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>⚠️ {error}</span>
          <button onClick={load} style={{ fontSize: '12px', color: '#94a3b8', background: 'none', border: '1px solid #334155', borderRadius: '6px', padding: '3px 10px', cursor: 'pointer' }}>Riprova</button>
        </div>
      )}

      {!loading && overview && (
        <>
          {BOTS.map(bot => (
            <BotSection key={bot.key} bot={bot} data={overview[bot.key]} />
          ))}

          {/* Footer aggiornamento */}
          <div style={{ textAlign: 'center', fontSize: '11px', color: '#334155', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginTop: '8px' }}>
            {lastUpdate && <span>Aggiornato: {lastUpdate.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>}
            <span>·</span>
            <button onClick={load} style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: '11px', padding: '2px 6px' }}>↻ Aggiorna</button>
            <span>· Auto 15s</span>
          </div>
        </>
      )}
    </div>
  );
}
