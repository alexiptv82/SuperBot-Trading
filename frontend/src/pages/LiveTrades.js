import React, { useState, useEffect, useCallback } from 'react';
import { deskAPI } from '../api';
import { signed, pnlColor } from '../deskUi';
import { MUTED, liveBotStatus, PositionCard, RecentTrades, CloseResultNote, closePositionRequest } from '../components/LiveParts';

const BOTS = [
  { key: 'hawk', label: '🦅 Hawk', color: '#0ea5e9' },
  { key: 'bull', label: '🐂 Bull', color: '#f59e0b' },
];

function BotSection({ bot, data, serverIsLive, onClosePosition }) {
  if (!data) return (
    <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '14px', padding: '16px 20px', marginBottom: '16px' }}>
      <div style={{ color: '#475569', fontSize: '13px' }}>{bot.label} — dati non disponibili</div>
    </div>
  );

  const { positions = [], recent_trades = [], positions_error, positions_source, bot_mode, last_action } = data;
  const status = liveBotStatus(data, serverIsLive);
  const closer = serverIsLive && bot_mode === 'live' && data.can_close_position && data.bot_online !== false
    ? { pending: data.close_pending || [], onClose: onClosePosition } : null;

  return (
    <div style={{ background: '#0f172a', border: `1px solid ${bot.color}33`, borderRadius: '14px', overflow: 'hidden', marginBottom: '16px' }}>
      <div style={{
        padding: '14px 16px', borderBottom: '1px solid #1e293b', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', gap: '8px', background: `linear-gradient(135deg, ${bot.color}12 0%, transparent 60%)`,
      }}>
        <div style={{ fontWeight: 800, fontSize: '15px', color: '#f1f5f9' }}>{bot.label}</div>
        <div style={{ fontSize: '12px', color: status.color, textAlign: 'right' }}>{status.text}</div>
      </div>

      <div style={{ padding: '12px 16px' }}>
        <div style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1', marginBottom: '8px' }}>⚡ Trade aperti ({positions.length})</div>
        {positions.length === 0 ? (
          <div style={{ fontSize: '12px', color: MUTED }}>
            {serverIsLive && bot_mode !== 'live' ? 'In attesa del bot live: nessuna posizione reale.' : 'Nessuna posizione aperta al momento.'}
          </div>
        ) : positions.map((p) => <PositionCard key={`${p.symbol}-${p.side}`} p={p} closer={closer} />)}
        <CloseResultNote action={last_action} />
        {positions_error && bot_mode === 'live' && (
          <div style={{ marginTop: '4px', fontSize: '10px', color: '#a16207' }}>
            {positions_source === 'bot' ? 'Posizioni dal bot: ' : ''}{positions_error}
          </div>
        )}
      </div>

      <div style={{ borderTop: '1px solid #1e293b', padding: '12px 8px 14px' }}>
        <div style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1', margin: '0 8px 6px' }}>🧾 Ultimi trade chiusi</div>
        <RecentTrades trades={recent_trades} />
      </div>
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

  const serverIsLive = overview?.mode === 'live';
  // P&L non incassato di tutte le posizioni aperte (calcolato dal server: BitGet se leggibile, altrimenti bot)
  const totalUnrealized = overview
    ? (parseFloat(overview.hawk?.unrealized_pnl) || 0) + (parseFloat(overview.bull?.unrealized_pnl) || 0)
    : 0;

  return (
    <div style={{ padding: '16px', maxWidth: '900px', margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '8px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '18px', fontWeight: 900, color: '#f1f5f9' }}>🔴 Trade Live</span>
            <span style={{
              fontSize: '10px', fontWeight: 700, letterSpacing: '0.1em', color: '#f87171', background: 'rgba(239,68,68,0.12)',
              border: '1px solid rgba(239,68,68,0.3)', borderRadius: '999px', padding: '3px 10px', textTransform: 'uppercase',
            }}>● LIVE · BitGet Futures</span>
          </div>
          <div style={{ fontSize: '12px', color: '#475569', marginTop: '4px' }}>Trade aperti e ultimi chiusi</div>
        </div>
        {overview && (
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '11px', color: '#475569' }}>Non ancora incassato</div>
            <div style={{ fontSize: '20px', fontWeight: 800, color: pnlColor(totalUnrealized), fontVariantNumeric: 'tabular-nums' }}>
              {signed(totalUnrealized)}$
            </div>
          </div>
        )}
      </div>

      {loading && <div style={{ padding: '40px', textAlign: 'center', color: '#475569' }}>Caricamento posizioni live…</div>}

      {error && (
        <div style={{ margin: '0 0 16px', padding: '14px 18px', background: '#1e293b', border: '1px solid #dc2626', borderRadius: '12px', color: '#fca5a5', fontSize: '13px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>⚠️ {error}</span>
          <button onClick={load} style={{ fontSize: '12px', color: '#94a3b8', background: 'none', border: '1px solid #334155', borderRadius: '6px', padding: '3px 10px', cursor: 'pointer' }}>Riprova</button>
        </div>
      )}

      {!loading && overview && (
        <>
          {BOTS.map((bot) => (
            <BotSection key={bot.key} bot={bot} data={overview[bot.key]} serverIsLive={serverIsLive}
              onClosePosition={async (symbol) => { const r = await closePositionRequest(bot.key, symbol); await load(); return r; }} />
          ))}
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
