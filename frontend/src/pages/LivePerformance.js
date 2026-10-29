import React, { useState, useEffect, useCallback } from 'react';
import { deskAPI } from '../api';

const fmt = (v, d = 2) => { const n = parseFloat(v); return isNaN(n) ? '--' : n.toFixed(d); };
const pnlColor = (v) => { const n = parseFloat(v); if (isNaN(n) || n === 0) return '#94a3b8'; return n > 0 ? '#4ade80' : '#f87171'; };
const sign = (v) => { const n = parseFloat(v); if (isNaN(n)) return ''; return n >= 0 ? '+' : ''; };

function StatCard({ label, value, color, sub }) {
  return (
    <div style={{
      background: '#0f172a', border: '1px solid #1e293b',
      borderRadius: '12px', padding: '14px 18px',
      flex: '1 1 140px', minWidth: 0,
    }}>
      <div style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>{label}</div>
      <div style={{ fontSize: '22px', fontWeight: 800, color: color || '#f1f5f9', fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      {sub && <div style={{ fontSize: '11px', color: '#475569', marginTop: '3px' }}>{sub}</div>}
    </div>
  );
}

function BotPerfCard({ bot, data }) {
  if (!data) return null;
  const { capital_usdt, daily_pnl, total_pnl, open_positions, total_closed, daily_loss_limit_usdt } = data;
  const color = bot.key === 'hawk' ? '#0ea5e9' : '#f59e0b';

  const limitPct = daily_loss_limit_usdt > 0
    ? Math.min(100, Math.abs(Math.min(0, parseFloat(daily_pnl) || 0)) / daily_loss_limit_usdt * 100)
    : 0;

  return (
    <div style={{
      background: '#0f172a',
      border: `1px solid ${color}33`,
      borderRadius: '14px',
      overflow: 'hidden',
      flex: '1 1 280px', minWidth: 0,
    }}>
      <div style={{
        padding: '14px 18px',
        borderBottom: '1px solid #1e293b',
        background: `linear-gradient(135deg, ${color}12 0%, transparent 60%)`,
        display: 'flex', alignItems: 'center', gap: '8px',
      }}>
        <span style={{ fontSize: '18px' }}>{bot.emoji}</span>
        <span style={{ fontWeight: 800, fontSize: '15px', color: '#f1f5f9' }}>{bot.label}</span>
        <span style={{ fontSize: '11px', color: '#475569', marginLeft: 'auto' }}>sub-account BitGet</span>
      </div>

      <div style={{ padding: '16px 18px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        <div>
          <div style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>Capitale</div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#94a3b8', fontVariantNumeric: 'tabular-nums' }}>${fmt(capital_usdt, 0)}</div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>P&L Oggi</div>
          <div style={{ fontSize: '18px', fontWeight: 800, color: pnlColor(daily_pnl), fontVariantNumeric: 'tabular-nums' }}>
            {sign(daily_pnl)}${fmt(daily_pnl, 2)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>P&L Totale</div>
          <div style={{ fontSize: '18px', fontWeight: 800, color: pnlColor(total_pnl), fontVariantNumeric: 'tabular-nums' }}>
            {sign(total_pnl)}${fmt(total_pnl, 2)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px' }}>Trade chiusi</div>
          <div style={{ fontSize: '18px', fontWeight: 700, color: '#94a3b8' }}>{total_closed ?? '--'}</div>
        </div>
      </div>

      {/* Barra limite perdita */}
      <div style={{ padding: '0 18px 16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px', fontSize: '10px', color: '#475569' }}>
          <span>Limite perdita giornaliera</span>
          <span style={{ color: limitPct > 80 ? '#ef4444' : '#64748b' }}>
            {fmt(limitPct, 0)}% / ${fmt(daily_loss_limit_usdt, 0)}
          </span>
        </div>
        <div style={{ height: '4px', background: '#1e293b', borderRadius: '999px', overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${limitPct}%`,
            background: limitPct > 80 ? '#ef4444' : limitPct > 50 ? '#f59e0b' : '#4ade80',
            borderRadius: '999px', transition: 'width 0.4s',
          }} />
        </div>
      </div>
    </div>
  );
}

const BOTS = [
  { key: 'hawk', label: 'Falco', emoji: '🦅' },
  { key: 'bull', label: 'Toro', emoji: '🐂' },
];

export default function LivePerformance() {
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
      setError(e?.message || 'Errore caricamento performance live');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  // Totali combinati
  const hawk = overview?.hawk;
  const bull = overview?.bull;
  const totalCapital = (parseFloat(hawk?.capital_usdt) || 0) + (parseFloat(bull?.capital_usdt) || 0);
  const totalDayPnl  = (parseFloat(hawk?.daily_pnl)    || 0) + (parseFloat(bull?.daily_pnl)    || 0);
  const totalPnl     = (parseFloat(hawk?.total_pnl)     || 0) + (parseFloat(bull?.total_pnl)     || 0);
  const totalClosed  = (hawk?.total_closed ?? 0) + (bull?.total_closed ?? 0);
  const totalOpen    = (hawk?.open_positions ?? 0) + (bull?.open_positions ?? 0);

  const wallet = overview?.wallet;

  return (
    <div style={{ padding: '16px', maxWidth: '900px', margin: '0 auto' }}>

      {/* Intestazione */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '18px', fontWeight: 900, color: '#f1f5f9' }}>🔴 Performance Live</span>
        <span style={{
          fontSize: '10px', fontWeight: 700, letterSpacing: '0.1em',
          color: '#f87171', background: 'rgba(239,68,68,0.12)',
          border: '1px solid rgba(239,68,68,0.3)',
          borderRadius: '999px', padding: '3px 10px', textTransform: 'uppercase',
        }}>● LIVE · BitGet Futures</span>
      </div>

      {loading && <div style={{ padding: '40px', textAlign: 'center', color: '#475569' }}>Caricamento performance live…</div>}

      {error && (
        <div style={{ margin: '0 0 16px', padding: '14px 18px', background: '#1e293b', border: '1px solid #dc2626', borderRadius: '12px', color: '#fca5a5', fontSize: '13px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>⚠️ {error}</span>
          <button onClick={load} style={{ fontSize: '12px', color: '#94a3b8', background: 'none', border: '1px solid #334155', borderRadius: '6px', padding: '3px 10px', cursor: 'pointer' }}>Riprova</button>
        </div>
      )}

      {!loading && overview && (
        <>
          {/* Riepilogo wallet reale */}
          {wallet?.available && (
            <div style={{
              background: 'linear-gradient(135deg, #0f2027 0%, #12303d 60%, #0f2027 100%)',
              border: '1px solid #1e3a4a',
              borderRadius: '14px', padding: '16px 20px', marginBottom: '20px',
              position: 'relative', overflow: 'hidden',
            }}>
              <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '2px', background: 'linear-gradient(90deg, transparent, #0ea5e9, transparent)' }} />
              <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Saldo reale BitGet — Falco + Toro</div>
              <div style={{ display: 'flex', gap: '28px', flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '3px' }}>TOTALE</div>
                  <div style={{ fontSize: '26px', fontWeight: 800, color: '#f1f5f9', fontVariantNumeric: 'tabular-nums' }}>${fmt(wallet.total_usdt, 2)} <span style={{ fontSize: '12px', color: '#475569' }}>USDT</span></div>
                </div>
                <div>
                  <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '3px' }}>DISPONIBILE</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#4ade80', fontVariantNumeric: 'tabular-nums' }}>${fmt(wallet.available_usdt, 2)}</div>
                </div>
                <div>
                  <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '3px' }}>IN MARGINE</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#fb923c', fontVariantNumeric: 'tabular-nums' }}>${fmt(wallet.used_usdt, 2)}</div>
                </div>
              </div>
            </div>
          )}

          {/* Statistiche globali */}
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '20px' }}>
            <StatCard label="Capitale totale" value={`$${fmt(totalCapital, 0)}`} color="#94a3b8" />
            <StatCard label="P&L oggi" value={`${sign(totalDayPnl)}$${fmt(totalDayPnl, 2)}`} color={pnlColor(totalDayPnl)} />
            <StatCard label="P&L totale" value={`${sign(totalPnl)}$${fmt(totalPnl, 2)}`} color={pnlColor(totalPnl)} />
            <StatCard label="Trade chiusi" value={totalClosed} />
            <StatCard label="Pos. aperte" value={totalOpen} />
          </div>

          {/* Dettaglio per bot */}
          <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
            {BOTS.map(bot => (
              <BotPerfCard key={bot.key} bot={bot} data={overview[bot.key]} />
            ))}
          </div>

          {/* Footer */}
          <div style={{ textAlign: 'center', fontSize: '11px', color: '#334155', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginTop: '20px' }}>
            {lastUpdate && <span>Aggiornato: {lastUpdate.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>}
            <span>·</span>
            <button onClick={load} style={{ background: 'none', border: 'none', color: '#475569', cursor: 'pointer', fontSize: '11px', padding: '2px 6px' }}>↻ Aggiorna</button>
            <span>· Auto 30s</span>
          </div>
        </>
      )}
    </div>
  );
}
