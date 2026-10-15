import React, { useState, useEffect, useCallback, useRef } from 'react';
import { deskAPI } from '../api';
import { fmtClock, signed, pnlColor } from '../deskUi';
import { MUTED, money, relTime, liveBotStatus, PositionCard, RecentTrades, CloseResultNote, closePositionRequest } from '../components/LiveParts';

const BOTS = [
  { key: 'hawk', name: 'Hawk', emoji: '🦅', color: '#0ea5e9' },
  { key: 'bull', name: 'Bull', emoji: '🐂', color: '#f59e0b' },
];

const LABEL = { fontSize: '10px', color: '#475569', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '4px' };

function Tile({ label, value, color = '#e2e8f0', sub }) {
  return (
    <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '12px 14px', minWidth: 0 }}>
      <div style={LABEL}>{label}</div>
      <div style={{ fontSize: '19px', fontWeight: 800, color, fontVariantNumeric: 'tabular-nums' }}>{value}</div>
      {sub ? <div style={{ fontSize: '11px', color: MUTED, marginTop: '2px' }}>{sub}</div> : null}
    </div>
  );
}

// ── Saldo reale dei due sub-account BitGet ─────────────────────────────────────
function WalletSection({ wallet, mode }) {
  const isLive = mode === 'live';
  if (!isLive) {
    return (
      <div style={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '14px', padding: '14px 16px', marginBottom: '16px', color: MUTED, fontSize: '13px' }}>
        Il server è in modalità paper: nessun saldo reale da mostrare.
      </div>
    );
  }
  const per = wallet?.per_bot || {};
  const WalletTile = ({ title, w }) => (
    <div style={{ background: 'linear-gradient(135deg, #0f2027 0%, #12303d 100%)', border: '1px solid #0e4a63', borderRadius: '14px', padding: '14px 16px', minWidth: 0 }}>
      <div style={LABEL}>{title}</div>
      {w?.available ? (
        <>
          <div style={{ fontSize: '24px', fontWeight: 800, color: '#f1f5f9', fontVariantNumeric: 'tabular-nums' }}>
            ${money(w.total_usdt)} <span style={{ fontSize: '12px', color: MUTED, fontWeight: 400 }}>USDT</span>
          </div>
          <div style={{ fontSize: '11px', color: MUTED, marginTop: '4px' }}>
            <span style={{ color: '#4ade80' }}>${money(w.available_usdt)}</span> disponibili ·{' '}
            <span style={{ color: '#fb923c' }}>${money(w.used_usdt)}</span> in margine
          </div>
        </>
      ) : (
        <div style={{ fontSize: '12px', color: '#f87171' }}>{w?.error || 'Saldo non disponibile'}</div>
      )}
    </div>
  );
  return (
    <div style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
        <span style={{ fontSize: '10px', fontWeight: 700, letterSpacing: '0.08em', color: '#0ea5e9', background: 'rgba(14,165,233,0.12)', border: '1px solid rgba(14,165,233,0.3)', borderRadius: '999px', padding: '3px 10px', textTransform: 'uppercase' }}>
          ● Saldo reale BitGet
        </span>
        <span style={{ fontSize: '11px', color: '#475569' }}>un sub-account per bot</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '10px' }}>
        <WalletTile title="🦅 Hawk" w={per.hawk} />
        <WalletTile title="🐂 Bull" w={per.bull} />
        {wallet?.available && <WalletTile title="Totale" w={wallet} />}
      </div>
    </div>
  );
}

// ── Una scheda per bot ─────────────────────────────────────────────────────────
function BotCard({ bot, data, mode, walletOf, onToggleTrading, onClosePosition }) {
  const [toggling, setToggling] = useState(false);
  if (!data) return null;

  const { capital_usdt, daily_pnl, total_pnl, daily_loss_limit_usdt, daily_limit_hit, positions = [],
    recent_trades = [], trading_enabled, bot_mode, live_interlock, live_pending_close = [],
    unrealized_pnl, cycle_info = {}, positions_source, positions_error, halt, last_action } = data;

  const serverIsLive = mode === 'live';
  const botIsLive = bot_mode === 'live';
  const status = liveBotStatus(data, serverIsLive);
  // ▶ bloccato finché il bot non gira davvero in live: l'interruttore resterebbe acceso e il bot, alla prima
  // partenza in live, aprirebbe subito posizioni vere senza che tu l'abbia deciso in quel momento.
  const switchBlocked = serverIsLive && !botIsLive && !trading_enabled;
  // Tasto "Chiudi ora" sulle posizioni: solo con il bot live, acceso e della versione che lo sa fare
  const closer = serverIsLive && botIsLive && data.can_close_position && data.bot_online !== false && onClosePosition
    ? { pending: data.close_pending || [], onClose: onClosePosition } : null;

  const handleToggle = async () => {
    if (toggling || switchBlocked) return;
    const enabling = !trading_enabled;
    if (enabling) {
      const ok = window.confirm(
        `Vuoi AVVIARE il trading live per ${bot.name}?\n\n` +
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

  // Il saldo del sub-account è molto sotto il capitale su cui ragiona il bot: gli ordini verrebbero rifiutati.
  const w = walletOf;
  const underfunded = serverIsLive && w?.available && capital_usdt > 0 && w.total_usdt < capital_usdt * 0.9;

  const lastCheck = relTime(cycle_info.last_end_ms);
  const nextCheck = cycle_info.next_cycle_ms && trading_enabled ? relTime(cycle_info.next_cycle_ms) : null;
  const alertBox = (bg, border, color, children) => (
    <div style={{ margin: '0 16px 12px', padding: '8px 12px', borderRadius: '8px', background: bg, border: `1px solid ${border}`, color, fontSize: '12px', lineHeight: 1.45 }}>
      {children}
    </div>
  );

  return (
    <div style={{
      background: '#0f172a',
      border: `1px solid ${daily_limit_hit ? '#ef4444' : halt ? '#f59e0b' : '#1e3a5f'}`,
      borderRadius: '16px', overflow: 'hidden', flex: '1 1 340px', minWidth: 0,
    }}>
      {/* Intestazione: chi è, cosa sta facendo, interruttore */}
      <div style={{
        padding: '14px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px',
        background: `linear-gradient(135deg, ${bot.color}18 0%, transparent 60%)`, borderBottom: '1px solid #1e293b',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', minWidth: 0 }}>
          <span style={{ fontSize: '24px' }}>{bot.emoji}</span>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 800, fontSize: '16px', color: '#f1f5f9' }}>{bot.name}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: status.color }}>
              <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: status.color, flexShrink: 0,
                boxShadow: status.key === 'on' ? `0 0 6px ${status.color}` : 'none' }} />
              <span>{status.text}</span>
            </div>
          </div>
        </div>
        {serverIsLive && (
          <button
            onClick={handleToggle}
            disabled={toggling || switchBlocked}
            title={switchBlocked
              ? 'Il bot gira ancora in paper: ridistribuisci i bot prima di avviare il live'
              : trading_enabled ? 'Stop trading (nessuna nuova apertura)' : 'Avvia trading live'}
            style={{
              flexShrink: 0, display: 'flex', alignItems: 'center', gap: '5px', padding: '8px 14px', borderRadius: '999px',
              border: `1px solid ${trading_enabled ? 'rgba(239,68,68,0.4)' : 'rgba(74,222,128,0.4)'}`,
              background: trading_enabled ? 'rgba(239,68,68,0.12)' : 'rgba(74,222,128,0.12)',
              color: trading_enabled ? '#f87171' : '#4ade80', fontSize: '12px', fontWeight: 700,
              cursor: switchBlocked ? 'not-allowed' : toggling ? 'wait' : 'pointer',
              opacity: switchBlocked ? 0.35 : toggling ? 0.6 : 1, letterSpacing: '0.04em', textTransform: 'uppercase',
            }}>
            {toggling ? '…' : trading_enabled ? '⏹ Stop' : '▶ Avvia'}
          </button>
        )}
      </div>

      <div style={{ paddingTop: '12px' }}>
        {/* Avvisi: solo quando c'è qualcosa da sapere */}
        {serverIsLive && !botIsLive && alertBox('rgba(245,158,11,0.12)', 'rgba(245,158,11,0.3)', '#fbbf24', (
          <>⏸ Nessun ordine reale e numeri a zero finché il bot non gira in live.{' '}
            {bot_mode === 'paper' ? 'Questo bot gira in PAPER.' : 'Gira ancora la versione precedente, oppure è fermo.'}{' '}
            Il pulsante ▶ si sblocca dopo la ridistribuzione dei bot in live.</>
        ))}
        {serverIsLive && botIsLive && live_interlock && alertBox('rgba(239,68,68,0.12)', 'rgba(239,68,68,0.35)', '#f87171', (
          <>⛔ Nuove aperture BLOCCATE: {live_interlock}. Le posizioni già aperte restano gestite; il blocco si toglie da solo
            quando BitGet e bot coincidono di nuovo.
            {live_pending_close.length > 0 && ` Chiusura da completare su: ${live_pending_close.join(', ')}.`}</>
        ))}
        {underfunded && alertBox('rgba(245,158,11,0.12)', 'rgba(245,158,11,0.3)', '#fbbf24', (
          <>💰 Su BitGet ci sono ${money(w.total_usdt, 0)} ma il bot ragiona su ${money(capital_usdt, 0)}: prima di avviare
            servono i fondi sul sub-account, altrimenti gli ordini verrebbero rifiutati per margine insufficiente.</>
        ))}

        {/* Numeri */}
        <div style={{ padding: '0 16px 12px', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
          <div>
            <div style={LABEL}>Capitale</div>
            <div style={{ fontSize: '16px', fontWeight: 700, color: '#94a3b8', fontVariantNumeric: 'tabular-nums' }}>${money(capital_usdt, 0)}</div>
          </div>
          <div>
            <div style={LABEL}>Oggi</div>
            <div style={{ fontSize: '16px', fontWeight: 800, color: pnlColor(daily_pnl), fontVariantNumeric: 'tabular-nums' }}>{signed(daily_pnl)}$</div>
          </div>
          <div>
            <div style={LABEL}>Totale</div>
            <div style={{ fontSize: '16px', fontWeight: 800, color: pnlColor(total_pnl), fontVariantNumeric: 'tabular-nums' }}>{signed(total_pnl)}$</div>
          </div>
        </div>

        {/* Limite di perdita giornaliera */}
        <div style={{ padding: '0 16px 12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
            <span style={{ ...LABEL, marginBottom: 0 }}>Perdita di oggi / limite</span>
            <span style={{ fontSize: '10px', color: limitPct > 80 ? '#ef4444' : MUTED, fontVariantNumeric: 'tabular-nums' }}>
              ${money(Math.abs(Math.min(0, daily_pnl)), 2)} / ${money(daily_loss_limit_usdt, 0)}
            </span>
          </div>
          <div style={{ height: '4px', background: '#1e293b', borderRadius: '999px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${limitPct}%`, borderRadius: '999px', transition: 'width 0.4s ease',
              background: limitPct > 80 ? '#ef4444' : limitPct > 50 ? '#f59e0b' : '#4ade80' }} />
          </div>
        </div>

        {/* Cosa sta facendo il bot */}
        {serverIsLive && botIsLive && (
          <div style={{ padding: '0 16px 12px', fontSize: '11px', color: MUTED }}>
            {lastCheck ? `Ultimo controllo del mercato: ${lastCheck}` : 'Nessun controllo ancora eseguito'}
            {nextCheck ? ` · prossimo ${nextCheck} (${fmtClock(cycle_info.next_cycle_ms)})` : ''}
            {cycle_info.last_ok === false && cycle_info.last_error
              ? <div style={{ color: '#f87171', marginTop: '2px' }}>Ultimo ciclo con errore: {cycle_info.last_error}</div> : null}
          </div>
        )}

        {/* Trade aperti: sempre visibili */}
        <div style={{ borderTop: '1px solid #1e293b', padding: '12px 16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '8px' }}>
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1' }}>⚡ Trade aperti ({positions.length})</span>
            {positions.length > 0 && (
              <span style={{ fontSize: '11px', color: pnlColor(unrealized_pnl) }}>
                {signed(unrealized_pnl)}$ non ancora incassati
              </span>
            )}
          </div>
          {positions.length === 0 ? (
            <div style={{ fontSize: '12px', color: MUTED }}>
              Nessuna posizione aperta{status.key === 'on' ? ': il bot sta aspettando l’occasione giusta.' : '.'}
            </div>
          ) : positions.map((p) => <PositionCard key={`${p.symbol}-${p.side}`} p={p} closer={closer} />)}
          <CloseResultNote action={last_action} />
          {positions_error && botIsLive && (
            <div style={{ marginTop: '4px', fontSize: '10px', color: '#a16207' }}>
              {positions_source === 'bot' ? 'Posizioni dal bot: ' : ''}{positions_error}
            </div>
          )}
        </div>

        {/* Ultimi trade chiusi */}
        <div style={{ borderTop: '1px solid #1e293b', padding: '12px 8px 14px' }}>
          <div style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1', margin: '0 8px 6px' }}>🧾 Ultimi trade chiusi</div>
          <RecentTrades trades={recent_trades} />
        </div>
      </div>
    </div>
  );
}

// ── Pagina Live ────────────────────────────────────────────────────────────────
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

  const toggler = (bot) => async (enable) => {
    const api = bot.key === 'hawk'
      ? (enable ? deskAPI.enableHawkTrading : deskAPI.disableHawkTrading)
      : (enable ? deskAPI.enableBullTrading : deskAPI.disableBullTrading);
    try {
      await api();
      showMsg(`${bot.name}: trading ${enable ? 'AVVIATO ▶' : 'FERMATO ⏹'}`);
      await load();   // rilegge subito lo stato aggiornato
    } catch (e) {
      showMsg(`Errore: ${e?.response?.data?.detail || e.message}`, true);
    }
  };

  // Chiudi una posizione a mano: invia la richiesta e rilegge subito lo stato (la richiesta appare "in corso")
  const closer = (bot) => async (symbol) => {
    const r = await closePositionRequest(bot.key, symbol);
    await load();
    return r;
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  useEffect(() => () => clearTimeout(tradingMsgTimer.current), []);

  if (loading) return (
    <div style={{ padding: '32px', textAlign: 'center', color: '#475569' }}>Caricamento dati live…</div>
  );

  if (error && !overview) return (
    <div style={{ margin: '24px', padding: '16px', background: '#1e293b', border: '1px solid #dc2626', borderRadius: '12px', color: '#fca5a5', fontSize: '13px' }}>
      ⚠️ {error}
      <button onClick={load} style={{ marginLeft: '12px', fontSize: '12px', color: '#94a3b8', background: 'none', border: '1px solid #334155', borderRadius: '6px', padding: '3px 10px', cursor: 'pointer' }}>Riprova</button>
    </div>
  );

  const mode = overview?.mode || 'paper';
  const isLive = mode === 'live';
  const wallet = overview?.wallet;
  const hawk = overview?.hawk;
  const bull = overview?.bull;

  const num = (v) => parseFloat(v) || 0;
  const dayPnl = num(hawk?.daily_pnl) + num(bull?.daily_pnl);
  const totalPnl = num(hawk?.total_pnl) + num(bull?.total_pnl);
  const totalCapital = num(hawk?.capital_usdt) + num(bull?.capital_usdt);
  const totalOpen = (hawk?.open_positions || 0) + (bull?.open_positions || 0);
  const totalUnreal = num(hawk?.unrealized_pnl) + num(bull?.unrealized_pnl);

  return (
    <div style={{ padding: '16px', maxWidth: '980px', margin: '0 auto' }}>
      {/* Titolo */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '18px', fontWeight: 900, color: '#f1f5f9', letterSpacing: '-0.01em' }}>🔴 Trade Live</span>
          <span style={{
            fontSize: '10px', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', borderRadius: '999px', padding: '3px 10px',
            color: isLive ? '#4ade80' : '#64748b', background: isLive ? 'rgba(74,222,128,0.12)' : '#1e293b',
            border: `1px solid ${isLive ? 'rgba(74,222,128,0.3)' : '#334155'}`,
          }}>{isLive ? '● LIVE' : '○ PAPER'}</span>
        </div>
        <div style={{ fontSize: '11px', color: '#475569', display: 'flex', alignItems: 'center', gap: '8px' }}>
          {error ? <span style={{ color: '#f87171' }}>aggiornamento fallito</span>
            : lastUpdate ? <span>Aggiornato {lastUpdate.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span> : null}
          <button onClick={load} style={{ background: 'none', border: '1px solid #1e293b', color: '#94a3b8', cursor: 'pointer', fontSize: '11px', padding: '3px 8px', borderRadius: '6px' }}>↻</button>
        </div>
      </div>

      <WalletSection wallet={wallet} mode={mode} />

      {isLive && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '10px', marginBottom: '16px' }}>
          <Tile label="Capitale totale" value={`$${money(totalCapital, 0)}`} color="#94a3b8" />
          <Tile label="Profitto oggi" value={`${signed(dayPnl)}$`} color={pnlColor(dayPnl)} />
          <Tile label="Profitto totale" value={`${signed(totalPnl)}$`} color={pnlColor(totalPnl)} />
          <Tile label="Trade aperti" value={totalOpen} sub={totalOpen > 0 ? `${signed(totalUnreal)}$ non incassati` : undefined} />
        </div>
      )}

      {tradingMsg && (
        <div style={{
          position: 'fixed', top: '16px', left: '50%', transform: 'translateX(-50%)', zIndex: 200,
          background: tradingMsg.error ? '#7f1d1d' : '#052e16', border: `1px solid ${tradingMsg.error ? '#ef4444' : '#4ade80'}`,
          color: tradingMsg.error ? '#fca5a5' : '#86efac', borderRadius: '10px', padding: '10px 20px',
          fontSize: '13px', fontWeight: 600, boxShadow: '0 4px 16px rgba(0,0,0,0.5)', whiteSpace: 'nowrap',
        }}>{tradingMsg.text}</div>
      )}

      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
        {BOTS.map((bot) => (
          <BotCard
            key={bot.key}
            bot={bot}
            data={overview?.[bot.key]}
            mode={mode}
            walletOf={wallet?.per_bot?.[bot.key]}
            onToggleTrading={toggler(bot)}
            onClosePosition={closer(bot)}
          />
        ))}
      </div>

      <div style={{ marginTop: '16px', textAlign: 'center', fontSize: '10px', color: '#334155' }}>
        Aggiornamento automatico ogni 15 secondi · saldo e posizioni sono quelli veri di BitGet, i profitti chiusi sono calcolati dal bot
      </div>
    </div>
  );
}

// Esportati solo per la prova di rendering (non cambia nulla per l app)
export { BotCard, WalletSection };
