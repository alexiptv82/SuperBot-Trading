import React, { useState, useEffect, useCallback, useRef } from 'react';
import { deskAPI } from '../api';

const fmt = (v, dec = 2) => {
  const n = parseFloat(v);
  return isNaN(n) ? '--' : n.toFixed(dec);
};

const fmtMs = (ms) => {
  if (!ms) return '--';
  const d = new Date(ms);
  return d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }) +
    ' ' + d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
};

const pnlColor = (v) => {
  const n = parseFloat(v);
  if (isNaN(n) || n === 0) return '#94a3b8';
  return n > 0 ? '#4ade80' : '#f87171';
};

const pnlSign = (v) => {
  const n = parseFloat(v);
  if (isNaN(n)) return '';
  return n >= 0 ? '+' : '';
};

// ── Wallet banner ──────────────────────────────────────────────────────────────
function WalletBanner({ wallet, mode }) {
  const isLive = mode === 'live';
  return (
    <div style={{
      background: isLive ? 'linear-gradient(135deg, #0f2027 0%, #12303d 60%, #0f2027 100%)' : '#0f172a',
      border: `1px solid ${isLive ? '#0ea5e9' : '#334155'}`,
      borderRadius: '16px',
      padding: '20px 24px',
      marginBottom: '20px',
      position: 'relative',
      overflow: 'hidden',
    }}>
      {isLive && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: '2px',
          background: 'linear-gradient(90deg, transparent, #0ea5e9, transparent)',
        }} />
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: '6px',
          fontSize: '11px', fontWeight: 700, letterSpacing: '0.08em',
          color: isLive ? '#0ea5e9' : '#64748b',
          textTransform: 'uppercase',
          background: isLive ? 'rgba(14,165,233,0.12)' : '#1e293b',
          border: `1px solid ${isLive ? 'rgba(14,165,233,0.3)' : '#334155'}`,
          borderRadius: '999px', padding: '3px 10px',
        }}>
          <span style={{
            width: '6px', height: '6px', borderRadius: '50%',
            background: isLive ? '#0ea5e9' : '#475569',
            boxShadow: isLive ? '0 0 6px #0ea5e9' : 'none',
            animation: isLive ? 'pulse 2s infinite' : 'none',
          }} />
          {isLive ? 'LIVE' : 'PAPER MODE'}
        </span>
        <span style={{ color: '#475569', fontSize: '12px' }}>Portafoglio BitGet Futures</span>
      </div>

      {!isLive ? (
        <p style={{ color: '#64748b', fontSize: '13px', margin: 0 }}>
          Il bot è in modalità paper. Imposta <code style={{ color: '#94a3b8', fontSize: '12px' }}>DESK_MODE=live</code> nei GitHub Secrets per attivare il live.
        </p>
      ) : wallet?.available ? (
        <div style={{ display: 'flex', gap: '32px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Saldo totale</div>
            <div style={{ fontSize: '28px', fontWeight: 800, color: '#f1f5f9', fontVariantNumeric: 'tabular-nums' }}>
              ${fmt(wallet.total_usdt, 2)} <span style={{ fontSize: '13px', color: '#64748b', fontWeight: 400 }}>USDT</span>
            </div>
          </div>
          <div>
            <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Disponibile</div>
            <div style={{ fontSize: '22px', fontWeight: 700, color: '#4ade80', fontVariantNumeric: 'tabular-nums' }}>
              ${fmt(wallet.available_usdt, 2)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>In margine</div>
            <div style={{ fontSize: '22px', fontWeight: 700, color: '#fb923c', fontVariantNumeric: 'tabular-nums' }}>
              ${fmt(wallet.used_usdt, 2)}
            </div>
          </div>
        </div>
      ) : (
        <p style={{ color: '#f87171', fontSize: '13px', margin: 0 }}>
          {wallet?.error || 'Saldo non disponibile — verifica le chiavi API nei GitHub Secrets.'}
        </p>
      )}
    </div>
  );
}

// ── Portfolio card ─────────────────────────────────────────────────────────────
function PortfolioCard({ name, emoji, data, color, onToggleTrading, mode }) {
  const [expanded, setExpanded] = useState(false);
  const [toggling, setToggling] = useState(false);
  if (!data) return null;

  const { capital_usdt, daily_pnl, total_pnl, daily_loss_limit_usdt,
    daily_limit_hit, open_positions, positions = [], total_closed,
    cycle, halt, available, trading_enabled, bot_mode } = data;

  const isLive = mode === 'live';
  // I Secret dicono "live", ma conta come gira DAVVERO il bot (dal suo battito cardiaco).
  // Se il container non e' stato ridistribuito gira ancora in paper: niente ordini reali.
  const botIsLive = bot_mode === 'live';
  const switchBlocked = isLive && !botIsLive && !trading_enabled;

  const handleToggle = async () => {
    if (toggling || switchBlocked) return;
    const enabling = !trading_enabled;
    if (enabling) {
      // Conferma prima di abilitare il live
      const ok = window.confirm(
        `Vuoi AVVIARE il trading live per ${name}?\n\n` +
        `Il bot inizierà ad aprire posizioni reali su BitGet.\n` +
        `Assicurati che le chiavi API siano configurate correttamente.`
      );
      if (!ok) return;
    }
    setToggling(true);
    try {
      await onToggleTrading(enabling);
    } finally {
      setToggling(false);
    }
  };

  const limitPct = daily_loss_limit_usdt > 0
    ? Math.min(100, Math.abs(Math.min(0, daily_pnl)) / daily_loss_limit_usdt * 100)
    : 0;

  return (
    <div style={{
      background: '#0f172a',
      border: `1px solid ${daily_limit_hit ? '#ef4444' : halt ? '#f59e0b' : '#1e3a5f'}`,
      borderRadius: '16px',
      overflow: 'hidden',
      flex: '1 1 300px',
      minWidth: 0,
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px',
        borderBottom: '1px solid #1e293b',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        background: `linear-gradient(135deg, ${color}18 0%, transparent 60%)`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '20px' }}>{emoji}</span>
          <div>
            <div style={{ fontWeight: 800, fontSize: '15px', color: '#f1f5f9' }}>{name}</div>
            <div style={{ fontSize: '11px', color: '#475569' }}>
              {available ? `Ciclo ${cycle} · ${open_positions} pos. aperte` : 'Non disponibile'}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
          {daily_limit_hit && (
            <span style={{
              fontSize: '10px', fontWeight: 700, color: '#ef4444',
              background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: '999px', padding: '3px 8px', textTransform: 'uppercase', letterSpacing: '0.06em',
            }}>⛔ Limite</span>
          )}
          {halt && !daily_limit_hit && (
            <span style={{
              fontSize: '10px', fontWeight: 700, color: '#f59e0b',
              background: 'rgba(245,158,11,0.15)', border: '1px solid rgba(245,158,11,0.3)',
              borderRadius: '999px', padding: '3px 8px', textTransform: 'uppercase', letterSpacing: '0.06em',
            }}>⚠️ Halt</span>
          )}
          {/* Bottone ▶/⏹ — visibile solo in live mode */}
          {isLive && (
            <button
              onClick={handleToggle}
              disabled={toggling || switchBlocked}
              title={switchBlocked
                ? 'Il bot gira ancora in paper: ridistribuisci i bot prima di avviare il live'
                : trading_enabled ? 'Stop trading (nessuna nuova apertura)' : 'Avvia trading live'}
              style={{
                display: 'flex', alignItems: 'center', gap: '5px',
                padding: '5px 12px',
                borderRadius: '999px',
                border: `1px solid ${trading_enabled ? 'rgba(239,68,68,0.4)' : 'rgba(74,222,128,0.4)'}`,
                background: trading_enabled
                  ? 'rgba(239,68,68,0.12)'
                  : 'rgba(74,222,128,0.12)',
                color: trading_enabled ? '#f87171' : '#4ade80',
                fontSize: '11px', fontWeight: 700,
                cursor: switchBlocked ? 'not-allowed' : toggling ? 'wait' : 'pointer',
                opacity: switchBlocked ? 0.35 : toggling ? 0.6 : 1,
                transition: 'all 0.2s',
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
              }}>
              {toggling
                ? '…'
                : trading_enabled
                  ? <>⏹ <span>Stop</span></>
                  : <>▶ <span>Avvia</span></>
              }
            </button>
          )}
        </div>
      </div>

      {isLive && !botIsLive && (
        <div style={{
          margin: '12px 20px 0', padding: '8px 12px', borderRadius: '8px',
          background: 'rgba(245,158,11,0.12)', border: '1px solid rgba(245,158,11,0.3)',
          color: '#fbbf24', fontSize: '12px', lineHeight: 1.4,
        }}>
          ⚠️ {bot_mode === 'paper'
            ? 'Questo bot gira in PAPER: nessun ordine reale. Il live parte solo dopo aver ridistribuito i bot.'
            : 'Stato del bot non disponibile: gira ancora con una versione senza live, oppure è fermo. Nessun ordine reale.'}
        </div>
      )}

      {/* P&L stats */}
      <div style={{ padding: '16px 20px', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
        <div>
          <div style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '4px' }}>Capitale</div>
          <div style={{ fontSize: '16px', fontWeight: 700, color: '#94a3b8', fontVariantNumeric: 'tabular-nums' }}>${fmt(capital_usdt, 0)}</div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '4px' }}>Oggi</div>
          <div style={{ fontSize: '16px', fontWeight: 800, color: pnlColor(daily_pnl), fontVariantNumeric: 'tabular-nums' }}>
            {pnlSign(daily_pnl)}${fmt(daily_pnl, 2)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '4px' }}>Totale</div>
          <div style={{ fontSize: '16px', fontWeight: 800, color: pnlColor(total_pnl), fontVariantNumeric: 'tabular-nums' }}>
            {pnlSign(total_pnl)}${fmt(total_pnl, 2)}
          </div>
        </div>
      </div>

      {/* Barra limite perdita giornaliera */}
      <div style={{ padding: '0 20px 14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>
          <span style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Perdita giornaliera
          </span>
          <span style={{ fontSize: '10px', color: limitPct > 80 ? '#ef4444' : '#64748b', fontVariantNumeric: 'tabular-nums' }}>
            ${fmt(Math.abs(Math.min(0, daily_pnl)), 2)} / ${fmt(daily_loss_limit_usdt, 0)} ({fmt(limitPct, 0)}%)
          </span>
        </div>
        <div style={{ height: '4px', background: '#1e293b', borderRadius: '999px', overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${limitPct}%`,
            background: limitPct > 80 ? '#ef4444' : limitPct > 50 ? '#f59e0b' : '#4ade80',
            borderRadius: '999px',
            transition: 'width 0.4s ease',
          }} />
        </div>
      </div>

      {/* Posizioni aperte */}
      {positions.length > 0 && (
        <div style={{ borderTop: '1px solid #1e293b' }}>
          <button
            onClick={() => setExpanded(e => !e)}
            style={{
              width: '100%', padding: '10px 20px', background: 'none',
              border: 'none', cursor: 'pointer', display: 'flex',
              justifyContent: 'space-between', alignItems: 'center',
              color: '#94a3b8', fontSize: '12px',
            }}>
            <span>{open_positions} posizioni aperte</span>
            <span style={{ fontSize: '10px' }}>{expanded ? '▲' : '▼'}</span>
          </button>
          {expanded && (
            <div style={{ padding: '0 12px 12px' }}>
              {positions.map((pos, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '7px 8px', borderRadius: '8px',
                  background: i % 2 === 0 ? '#0f1829' : 'transparent',
                  fontSize: '12px', gap: '8px',
                }}>
                  <span style={{ color: '#e2e8f0', fontWeight: 600, minWidth: '44px' }}>{pos.symbol}</span>
                  <span style={{
                    color: pos.side === 1 ? '#4ade80' : '#f87171',
                    fontSize: '10px', fontWeight: 700,
                    background: pos.side === 1 ? 'rgba(74,222,128,0.12)' : 'rgba(248,113,113,0.12)',
                    borderRadius: '4px', padding: '1px 5px',
                  }}>{pos.side === 1 ? 'LONG' : 'SHORT'}</span>
                  <span style={{ color: '#64748b', fontSize: '10px' }}>{pos.leverage}x</span>
                  <span style={{ color: '#94a3b8', fontVariantNumeric: 'tabular-nums' }}>${fmt(pos.margin, 0)}</span>
                  <span style={{ color: '#475569', fontSize: '10px' }}>{fmtMs(pos.open_ms)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div style={{
        padding: '8px 20px', borderTop: '1px solid #1e293b',
        fontSize: '10px', color: '#334155',
        display: 'flex', justifyContent: 'space-between',
      }}>
        <span>Trade chiusi: {total_closed}</span>
        {halt && <span style={{ color: '#f59e0b' }}>Halt: {halt}</span>}
      </div>
    </div>
  );
}

// ── Pagina principale LiveDashboard ───────────────────────────────────────────
export default function LiveDashboard() {
  const [overview, setOverview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [tradingMsg, setTradingMsg] = useState(null);
  const tradingMsgTimer = useRef(null);

  const showMsg = useCallback((msg, isError = false) => {
    setTradingMsg({ text: msg, error: isError });
    clearTimeout(tradingMsgTimer.current);
    tradingMsgTimer.current = setTimeout(() => setTradingMsg(null), 4000);
  }, []);

  const load = useCallback(async () => {
    try {
      const { data } = await deskAPI.getLiveOverview();   // axios: il corpo sta in .data
      setOverview(data);
      setLastUpdate(new Date());
      setError(null);
    } catch (e) {
      setError(e?.message || 'Errore caricamento dati live');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleHawkTrading = useCallback(async (enable) => {
    try {
      if (enable) await deskAPI.enableHawkTrading();
      else await deskAPI.disableHawkTrading();
      showMsg(`Hawk: trading ${enable ? 'AVVIATO ▶' : 'FERMATO ⏹'}`);
      await load(); // rilegge subito lo stato aggiornato
    } catch (e) {
      showMsg(`Errore: ${e?.response?.data?.detail || e.message}`, true);
    }
  }, [load, showMsg]);

  const handleBullTrading = useCallback(async (enable) => {
    try {
      if (enable) await deskAPI.enableBullTrading();
      else await deskAPI.disableBullTrading();
      showMsg(`Bull: trading ${enable ? 'AVVIATO ▶' : 'FERMATO ⏹'}`);
      await load();
    } catch (e) {
      showMsg(`Errore: ${e?.response?.data?.detail || e.message}`, true);
    }
  }, [load, showMsg]);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000); // aggiorna ogni 30s
    return () => clearInterval(t);
  }, [load]);

  if (loading) return (
    <div style={{ padding: '32px', textAlign: 'center', color: '#475569' }}>
      Caricamento dati live…
    </div>
  );

  if (error) return (
    <div style={{
      margin: '24px', padding: '16px', background: '#1e293b',
      border: '1px solid #dc2626', borderRadius: '12px', color: '#fca5a5', fontSize: '13px',
    }}>
      ⚠️ {error}
      <button onClick={load} style={{
        marginLeft: '12px', fontSize: '12px', color: '#94a3b8', background: 'none',
        border: '1px solid #334155', borderRadius: '6px', padding: '3px 10px', cursor: 'pointer',
      }}>Riprova</button>
    </div>
  );

  const mode = overview?.mode || 'paper';
  const wallet = overview?.wallet;
  const hawk = overview?.hawk;
  const bull = overview?.bull;

  // P&L combinato
  const combinedDayPnl = (parseFloat(hawk?.daily_pnl) || 0) + (parseFloat(bull?.daily_pnl) || 0);
  const combinedTotalPnl = (parseFloat(hawk?.total_pnl) || 0) + (parseFloat(bull?.total_pnl) || 0);
  const totalCapital = (parseFloat(hawk?.capital_usdt) || 0) + (parseFloat(bull?.capital_usdt) || 0);
  const totalOpen = (hawk?.open_positions || 0) + (bull?.open_positions || 0);

  return (
    <div style={{ padding: '16px 0', maxWidth: '900px', margin: '0 auto' }}>

      {/* Wallet BitGet */}
      <WalletBanner wallet={wallet} mode={mode} />

      {/* Riepilogo combinato */}
      {mode === 'live' && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: '12px', marginBottom: '20px',
        }}>
          {[
            { label: 'Capitale totale', value: `$${fmt(totalCapital, 0)}`, color: '#94a3b8' },
            { label: 'P&L oggi', value: `${pnlSign(combinedDayPnl)}$${fmt(combinedDayPnl, 2)}`, color: pnlColor(combinedDayPnl) },
            { label: 'P&L totale', value: `${pnlSign(combinedTotalPnl)}$${fmt(combinedTotalPnl, 2)}`, color: pnlColor(combinedTotalPnl) },
            { label: 'Posizioni aperte', value: totalOpen, color: '#e2e8f0' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{
              background: '#0f172a', border: '1px solid #1e293b',
              borderRadius: '12px', padding: '12px 16px',
            }}>
              <div style={{ fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '6px' }}>{label}</div>
              <div style={{ fontSize: '18px', fontWeight: 800, color, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Toast feedback interruttore trading */}
      {tradingMsg && (
        <div style={{
          position: 'fixed', top: '16px', left: '50%', transform: 'translateX(-50%)',
          background: tradingMsg.error ? '#7f1d1d' : '#052e16',
          border: `1px solid ${tradingMsg.error ? '#ef4444' : '#4ade80'}`,
          color: tradingMsg.error ? '#fca5a5' : '#86efac',
          borderRadius: '10px', padding: '10px 20px',
          fontSize: '13px', fontWeight: 600, zIndex: 200,
          boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
          whiteSpace: 'nowrap',
        }}>
          {tradingMsg.text}
        </div>
      )}

      {/* Card portafogli */}
      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
        <PortfolioCard
          name="Hawk"
          emoji="🦅"
          data={hawk}
          color="#0ea5e9"
          mode={mode}
          onToggleTrading={handleHawkTrading}
        />
        <PortfolioCard
          name="Bull"
          emoji="🐂"
          data={bull}
          color="#f59e0b"
          mode={mode}
          onToggleTrading={handleBullTrading}
        />
      </div>

      {/* Footer aggiornamento */}
      <div style={{
        marginTop: '20px', textAlign: 'center',
        fontSize: '11px', color: '#334155',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px',
      }}>
        {lastUpdate && <span>Aggiornato: {lastUpdate.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>}
        <span>·</span>
        <button onClick={load} style={{
          background: 'none', border: 'none', color: '#475569', cursor: 'pointer',
          fontSize: '11px', padding: '2px 6px', borderRadius: '4px',
        }}>↻ Aggiorna</button>
        <span>· Auto 30s</span>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}
