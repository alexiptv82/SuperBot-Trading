import React, { useState, useEffect, useCallback, useRef } from 'react';
import { botAPI, deskAPI } from '../api';
import ChartModal from '../components/ChartModal';
import ProfileBadge, { profileColor } from '../components/ProfileBadge';

// Formatta un numero in modo sicuro: converte stringhe, gestisce null/undefined.
const fmt = (v, dec = 2) => {
  const n = parseFloat(v);
  return isNaN(n) ? '--' : n.toFixed(dec);
};

// Tutti i 27 simboli del bot V2, nello stesso ordine della lista in cli.py.
// I primi 4 (BTC, ETH, XAU, XAG) sono sempre visibili nel carousel;
// gli altri 23 sono scorrevoli/espandibili.
const V2_SYMBOLS = [
  'BTC','ETH','BNB','XRP','SOL','ADA','DOGE','AVAX',
  'DOT','LINK','MATIC','UNI','ATOM','LTC','BCH',
  'APT','ARB','OP','NEAR','FIL','INJ','SUI','TIA',
  'RUNE','STX','XAU','XAG',
];

// Emoji/icone per i simboli principali
const SYMBOL_EMOJI = {
  BTC: '₿', ETH: 'Ξ', XAU: '🥇', XAG: '🥈',
  BNB: '🔶', SOL: '◎', ADA: '🔵', DOGE: '🐶',
  XRP: '💧', AVAX: '🔺', DOT: '⚫', LINK: '🔗',
  MATIC: '🟣', UNI: '🦄', ATOM: '⚛️', LTC: 'Ł',
  BCH: '💚', APT: '🅰️', ARB: '🔵', OP: '🔴',
  NEAR: '🟢', FIL: '🗂️', INJ: '💉', SUI: '💧',
  TIA: '☀️', RUNE: '🪄', STX: '📚',
};

// Error boundary: cattura crash di render nella sezione V2 evitando schermata nera.
class DeskErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { hasError: false, msg: '' }; }
  static getDerivedStateFromError(e) { return { hasError: true, msg: e?.message || '' }; }
  componentDidCatch(e, info) { console.error('[DeskSection crash]', e, info); }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          background: '#1e293b', borderRadius: '12px', padding: '14px',
          border: '1px solid #dc2626', color: '#fca5a5', fontSize: '13px',
          marginBottom: '16px'
        }}>
          ⚠️ Errore nel caricamento dei dati V2. Ricarica l'app.
          {this.state.msg ? <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>{this.state.msg}</div> : null}
        </div>
      );
    }
    return this.props.children;
  }
}

const Card = ({ children, style, onClick }) => (
  <div onClick={onClick} style={{
    background: '#1e293b', borderRadius: '16px', padding: '16px',
    border: '1px solid #334155', ...style
  }}>{children}</div>
);

const StatusChip = ({ label, ok, okText, badText }) => (
  <div style={{
    display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px',
    color: '#cbd5e1', background: '#0f172a', border: '1px solid #334155',
    borderRadius: '999px', padding: '4px 10px', whiteSpace: 'nowrap'
  }}>
    <span style={{
      width: '6px', height: '6px', borderRadius: '50%',
      background: ok ? '#4ade80' : '#f87171', flexShrink: 0
    }} />
    <span style={{ color: '#94a3b8' }}>{label}</span>
    <span style={{ fontWeight: 'bold' }}>{ok ? okText : badText}</span>
  </div>
);

// Carousel orizzontale scorrevole per le card mercato.
// showCount = quante card sono visibili per default (le prime); le altre si
// vedono scorrendo o premendo "Mostra tutti".
function MarketCarousel({ symbols, prices, onSymbolClick }) {
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef(null);

  // Mostriamo sempre tutti i simboli nella barra scorrevole, ma
  // quando non è espanso la barra ha un overflow-x: auto che ne mostra
  // solo alcuni contemporaneamente (su mobile ~2-3 carte per volta).
  const visibleSymbols = expanded ? symbols : symbols;

  return (
    <div style={{ marginBottom: '16px' }}>
      {/* Barra scorrevole */}
      <div
        ref={scrollRef}
        style={{
          display: 'flex',
          gap: '8px',
          overflowX: 'auto',
          paddingBottom: '8px',
          scrollbarWidth: 'none',  /* Firefox */
          msOverflowStyle: 'none', /* IE */
          WebkitOverflowScrolling: 'touch',
        }}
      >
        {visibleSymbols.map((sym) => {
          const key = sym + 'USDT';
          const data = prices[key] || prices[sym] || null;
          const up = (data?.change_24h ?? 0) > 0;
          const emoji = SYMBOL_EMOJI[sym] || '💱';
          const isActive = (data?.price) != null;
          return (
            <div
              key={sym}
              onClick={() => onSymbolClick(key)}
              style={{
                background: '#1e293b',
                borderRadius: '14px',
                padding: '12px 14px',
                border: '1px solid #334155',
                cursor: 'pointer',
                flexShrink: 0,
                minWidth: '100px',
                textAlign: 'center',
                opacity: isActive ? 1 : 0.55,
              }}
            >
              <div style={{ fontSize: '18px', marginBottom: '4px' }}>{emoji}</div>
              <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '4px', fontWeight: 'bold' }}>{sym}</div>
              <div style={{ fontSize: '13px', fontWeight: 'bold' }}>
                {isActive ? (data.price >= 1 ? '$' + data.price.toLocaleString('it-IT', { maximumFractionDigits: 2 }) : '$' + fmt(data.price, 4)) : '--'}
              </div>
              <div style={{ fontSize: '11px', color: up ? '#4ade80' : '#f87171', marginTop: '2px' }}>
                {isActive ? ((up ? '▲ +' : '▼ ') + Math.abs(data.change_24h || 0).toFixed(2) + '%') : ''}
              </div>
            </div>
          );
        })}
      </div>
      {/* Indicatore "scorri per vedere altri N simboli" */}
      <div style={{ fontSize: '10px', color: '#475569', textAlign: 'center', marginTop: '-4px' }}>
        ← scorri per vedere tutti i {symbols.length} simboli →
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [status, setStatus] = useState(null);
  const [prices, setPrices] = useState({});
  const [openTrades, setOpenTrades] = useState([]);
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState(false);
  const [now, setNow] = useState(new Date());

  // Stato modal grafico: { symbol, tradeInfo? }
  const [chartState, setChartState] = useState(null);

  // V2 desk bot state
  const [deskStatus, setDeskStatus] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [s, p, o] = await Promise.all([
        botAPI.getStatus(), botAPI.getPrices(), botAPI.getOpenTrades()
      ]);
      setStatus(s.data); setPrices(p.data); setOpenTrades(o.data);
      setApiError(false);
    } catch (e) { console.error(e); setApiError(true); }
  }, []);

  const fetchDeskData = useCallback(async () => {
    try {
      const r = await deskAPI.getStatus();
      setDeskStatus(r.data);
    } catch (e) { /* desk offline è normale */ }
  }, []);

  // Poll dati V1 ogni 10s, V2 ogni 5s (per sincronizzarsi con Telegram quasi in tempo reale)
  useEffect(() => { fetchData(); const t = setInterval(fetchData, 10000); return () => clearInterval(t); }, [fetchData]);
  useEffect(() => { fetchDeskData(); const t = setInterval(fetchDeskData, 5000); return () => clearInterval(t); }, [fetchDeskData]);
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 15000); return () => clearInterval(t); }, []);

  const marketLive = !apiError && Object.keys(prices).length > 0;
  const dateLabel = now.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short' });
  const timeLabel = now.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });

  const toggleBot = async () => {
    setLoading(true);
    try {
      if (status?.is_running) await botAPI.stop(); else await botAPI.start();
      await fetchData();
    } finally { setLoading(false); }
  };

  const pnlColor = (v) => v > 0 ? '#4ade80' : v < 0 ? '#f87171' : '#94a3b8';

  // Apre il grafico per un simbolo (con o senza info trade V2)
  const openChart = (symbol, tradeInfo = null) => setChartState({ symbol, tradeInfo });
  const closeChart = () => setChartState(null);

  // Computa quante posizioni V2 sono effettivamente aperte dall'array
  const v2OpenCount = Array.isArray(deskStatus?.positions) ? deskStatus.positions.length : (deskStatus?.open_positions ?? 0);

  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <h1 style={{
          fontSize: '22px', fontWeight: 'bold',
          background: 'linear-gradient(90deg, #f1f5f9, #38bdf8)',
          WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent'
        }}>🤖 SuperBot</h1>
        <span style={{
          padding: '4px 12px', borderRadius: '20px', fontSize: '12px',
          background: status?.mode === 'paper' ? '#1e40af' : '#166534',
          color: 'white'
        }}>
          {status?.mode === 'paper' ? '📝 PAPER' : '💰 LIVE'}
        </span>
      </div>

      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        gap: '8px', marginBottom: '16px', flexWrap: 'wrap'
      }}>
        <div style={{ fontSize: '13px', color: '#cbd5e1', display: 'flex', alignItems: 'baseline', gap: '6px' }}>
          <span style={{ textTransform: 'capitalize' }}>{dateLabel}</span>
          <span style={{ fontWeight: 'bold', fontVariantNumeric: 'tabular-nums' }}>{timeLabel}</span>
        </div>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          <StatusChip label="Mercato" ok={marketLive} okText="Live" badText="Offline" />
          <StatusChip label="Trading" ok={status?.mode === 'paper'} okText="Paper" badText="Live" />
        </div>
      </div>

      {/* V1 DISATTIVATA — codice preservato, non renderizzato. Riattivare togliendo {false &&} */}
      {false && (<>
        {/* Bot V1 status */}
        <Card style={{
          marginBottom: '16px', textAlign: 'center',
          boxShadow: status?.is_running ? '0 0 0 1px rgba(74,222,128,0.2)' : 'none'
        }}>
          <div style={{ fontSize: '48px', marginBottom: '8px' }}>
            {status?.is_running ? '🟢' : '🔴'}
          </div>
          <div style={{ fontSize: '18px', fontWeight: 'bold', marginBottom: '4px' }}>
            {status?.is_running ? 'Bot V1 Attivo' : 'Bot V1 Fermo'}
          </div>
          <div style={{ color: '#94a3b8', fontSize: '13px', marginBottom: '16px' }}>
            Posizioni aperte: {status?.open_positions || 0} | Win rate: {status?.win_rate || 0}%
          </div>
          <button onClick={toggleBot} disabled={loading} style={{
            padding: '12px 32px', borderRadius: '12px', border: 'none',
            background: status?.is_running ? '#dc2626' : '#16a34a',
            color: 'white', fontSize: '16px', fontWeight: 'bold',
            cursor: loading ? 'not-allowed' : 'pointer', width: '100%'
          }}>
            {loading ? '...' : status?.is_running ? '⏹ Ferma Bot' : '▶ Avvia Bot'}
          </button>
        </Card>

        {/* KPI V1 */}
        <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
          <Card style={{ flex: 1, textAlign: 'center' }}>
            <div style={{ color: '#94a3b8', fontSize: '12px', marginBottom: '4px' }}>
              {(status?.portfolios?.length || 0) > 1 ? 'Capitale totale' : 'Capitale'}
            </div>
            <div style={{ fontSize: '20px', fontWeight: 'bold' }}>
              ${status?.capital?.toFixed(2) || '0.00'}
            </div>
          </Card>
          <Card style={{ flex: 1, textAlign: 'center' }}>
            <div style={{ color: '#94a3b8', fontSize: '12px', marginBottom: '4px' }}>P&L Oggi</div>
            <div style={{ fontSize: '20px', fontWeight: 'bold', color: pnlColor(status?.daily_pnl) }}>
              {status?.daily_pnl > 0 ? '+' : ''}{status?.daily_pnl?.toFixed(2) || '0.00'}$
            </div>
          </Card>
          <Card style={{ flex: 1, textAlign: 'center' }}>
            <div style={{ color: '#94a3b8', fontSize: '12px', marginBottom: '4px' }}>Trade Tot.</div>
            <div style={{ fontSize: '20px', fontWeight: 'bold' }}>{status?.total_trades || 0}</div>
          </Card>
        </div>

        {/* Portafogli V1 — mostrati solo se il bot V1 ha dati */}
        {(status?.portfolios?.length || 0) > 0 && (
          <>
            <h2 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '4px' }}>💼 Portafogli V1</h2>
            <p style={{ fontSize: '11px', color: '#475569', marginBottom: '10px' }}>
              Portafogli del Bot V1 (Conservativo / Aggressivo) — separati dal Bot V2 qui sotto
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
              {status.portfolios.map(pf => (
                <Card key={pf.name} style={{
                  flex: '1 1 calc(50% - 8px)', minWidth: '240px',
                  borderColor: pf.active ? profileColor(pf.name) : '#334155', opacity: pf.active ? 1 : 0.7
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                    <ProfileBadge profile={pf.name} label={pf.label} />
                    <span style={{ fontSize: '11px', color: pf.paused ? '#fbbf24' : '#94a3b8' }}>
                      {pf.paused ? '⏸ In pausa (limite giornaliero)' : pf.active ? 'Attivo' : 'Solo chiusura'}
                    </span>
                  </div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold' }}>${pf.capital?.toFixed(2)}</div>
                  <div style={{ fontSize: '12px', color: pnlColor(pf.daily_pnl), marginBottom: '8px' }}>
                    Oggi {pf.daily_pnl > 0 ? '+' : ''}{pf.daily_pnl?.toFixed(2)}$
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#94a3b8' }}>
                    <span>Aperte {pf.open_positions}</span>
                    <span>Chiusi {pf.closed_trades} · Win {pf.win_rate}%</span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
                    <span style={{ color: pnlColor(pf.net_pnl) }}>Netto {pf.net_pnl > 0 ? '+' : ''}{pf.net_pnl?.toFixed(2)}$</span>
                    <span>Commissioni {pf.fees_paid?.toFixed(2)}$</span>
                  </div>
                </Card>
              ))}
            </div>
          </>
        )}

        {/* Posizioni aperte V1 */}
        {openTrades.length > 0 && (
          <>
            <h2 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '10px' }}>⚡ Posizioni V1 Aperte</h2>
            {openTrades.map((t, i) => (
              <Card key={i} onClick={() => openChart(t.symbol)} style={{ marginBottom: '8px', cursor: 'pointer' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <span style={{
                      padding: '2px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: 'bold',
                      background: t.side === 'long' ? '#166534' : '#7f1d1d',
                      color: 'white', marginRight: '8px'
                    }}>
                      {t.side?.toUpperCase()}
                    </span>
                    <span style={{ fontWeight: 'bold' }}>{t.symbol}</span>
                    <span style={{ color: '#94a3b8', fontSize: '12px', marginLeft: '6px', marginRight: '6px' }}>x{t.leverage}</span>
                    <ProfileBadge profile={t.profile} label={t.profile_label} />
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '13px' }}>@ ${t.entry_price?.toFixed(2)}</div>
                    <div style={{ fontSize: '11px', color: '#94a3b8' }}>{t.trade_type}</div>
                  </div>
                </div>
              </Card>
            ))}
          </>
        )}
      </>)}

      {/* ── Mercato Live (27 simboli V2 carousel) ── */}
      <h2 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '4px' }}>📊 Mercato Live</h2>
      <p style={{ fontSize: '11px', color: '#475569', marginBottom: '10px' }}>
        Tutti i 27 simboli del Bot V2 — tocca un simbolo per aprire il grafico
      </p>
      <MarketCarousel
        symbols={V2_SYMBOLS}
        prices={prices}
        onSymbolClick={(sym) => openChart(sym)}
      />

      {/* ── Sezione V2 Bot Desk (paper trading con Claude) ── */}
      {deskStatus && (
        <DeskErrorBoundary>
          <h2 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '4px', marginTop: '8px' }}>
            🧠 Bot V2 Paper (Claude AI)
          </h2>
          <p style={{ fontSize: '11px', color: '#475569', marginBottom: '10px' }}>
            Sistema separato dal V1 — paper trading gestito da Claude AI su {V2_SYMBOLS.length} simboli
          </p>

          {!deskStatus.available ? (
            <Card style={{ marginBottom: '16px', color: '#94a3b8', fontSize: '13px', textAlign: 'center' }}>
              {deskStatus.message || 'Bot V2 non ancora attivo'}
            </Card>
          ) : (
            <>
              {/* KPI V2 — riga 1: equity, cassa, margine in uso */}
              <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
                <Card style={{ flex: 1, textAlign: 'center', minWidth: '100px' }}>
                  <div style={{ color: '#94a3b8', fontSize: '10px', marginBottom: '2px' }}>Equity totale</div>
                  <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#f1f5f9' }}>${fmt(deskStatus.equity)}</div>
                  <div style={{ fontSize: '10px', color: '#475569', marginTop: '2px' }}>
                    cassa ${fmt(deskStatus.cash)} · margine ${fmt(deskStatus.margin_used, 0)}
                  </div>
                </Card>
                <Card style={{ flex: '0 0 auto', textAlign: 'center', minWidth: '80px' }}>
                  <div style={{ color: '#94a3b8', fontSize: '10px', marginBottom: '2px' }}>Aperte</div>
                  <div style={{ fontSize: '18px', fontWeight: 'bold' }}>{v2OpenCount}</div>
                </Card>
                <Card style={{ flex: '0 0 auto', textAlign: 'center', minWidth: '80px' }}>
                  <div style={{ color: '#94a3b8', fontSize: '10px', marginBottom: '2px' }}>Chiuse</div>
                  <div style={{ fontSize: '18px', fontWeight: 'bold' }}>
                    {deskStatus.total_closed ?? '--'}
                  </div>
                </Card>
                <Card style={{ flex: '0 0 auto', textAlign: 'center', minWidth: '80px' }}>
                  <div style={{ color: '#94a3b8', fontSize: '10px', marginBottom: '2px' }}>Claude $</div>
                  <div style={{
                    fontSize: '15px', fontWeight: 'bold',
                    color: (deskStatus.budget_spent_usd ?? 0) > (deskStatus.budget_daily_cap_usd ?? 0.7) * 0.9 ? '#fbbf24' : '#4ade80'
                  }}>
                    ${fmt(deskStatus.budget_spent_usd, 3)}
                  </div>
                </Card>
              </div>

              {deskStatus.halt && (
                <Card style={{ marginBottom: '8px', borderColor: '#dc2626', color: '#fca5a5', fontSize: '12px' }}>
                  ⚠️ HALT: {deskStatus.halt}
                </Card>
              )}

              {/* Posizioni V2 — cliccabili per aprire il grafico con dettagli */}
              {Array.isArray(deskStatus.positions) && deskStatus.positions.length > 0 && (
                <>
                  <div style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '6px' }}>
                    ⚡ Posizioni V2 aperte — tocca per vedere il grafico e i dettagli
                  </div>
                  {deskStatus.positions.map((p, i) => {
                    const sym = p.symbol || '?';
                    const cleanSym = sym.replace('USDT', '');
                    const isLong = p.side === 1 || p.side === 'long';
                    const sideLabel = p.side === 1 ? 'LONG' : p.side === -1 ? 'SHORT'
                      : typeof p.side === 'string' ? p.side.toUpperCase() : '?';
                    return (
                      <Card
                        key={i}
                        onClick={() => openChart(sym.endsWith('USDT') ? sym : sym + 'USDT', p)}
                        style={{ marginBottom: '6px', cursor: 'pointer', borderColor: '#1e3a4c' }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                            <span style={{ fontSize: '16px' }}>{SYMBOL_EMOJI[cleanSym] || '💱'}</span>
                            <span style={{
                              padding: '2px 6px', borderRadius: '5px', fontSize: '10px', fontWeight: 'bold',
                              background: isLong ? '#166534' : '#7f1d1d', color: 'white'
                            }}>{sideLabel}</span>
                            <span style={{ fontWeight: 'bold', fontSize: '13px' }}>{cleanSym}</span>
                            <span style={{ color: '#94a3b8', fontSize: '11px' }}>x{p.leverage ?? '--'}</span>
                            <span style={{ color: '#64748b', fontSize: '10px' }}>[{p.trade_type || 'medio'}]</span>
                            {(p.dca_count ?? 0) > 0 && (
                              <span style={{ color: '#fbbf24', fontSize: '10px' }}>DCA×{p.dca_count}</span>
                            )}
                          </div>
                          <div style={{ textAlign: 'right', fontSize: '12px', color: '#94a3b8' }}>
                            <div style={{ color: '#f1f5f9', fontWeight: 'bold' }}>@ ${fmt(p.entry_price)}</div>
                            <div>${fmt(p.margin, 0)} margin</div>
                            {p.tp && <div style={{ color: '#4ade80', fontSize: '10px' }}>TP ${fmt(p.tp)}</div>}
                            {p.sl && <div style={{ color: '#f87171', fontSize: '10px' }}>SL ${fmt(p.sl)}</div>}
                          </div>
                        </div>
                        <div style={{ fontSize: '10px', color: '#475569', marginTop: '4px', textAlign: 'right' }}>
                          📈 Tocca per grafico TradingView
                        </div>
                      </Card>
                    );
                  })}
                </>
              )}

              <div style={{ fontSize: '11px', color: '#475569', marginTop: '6px' }}>
                Ciclo #{deskStatus.cycle ?? 0} · Giorno {deskStatus.day || '--'} · Budget giornaliero ${fmt(deskStatus.budget_daily_cap_usd ?? 0.70)}
              </div>
            </>
          )}
        </DeskErrorBoundary>
      )}

      {/* Modal grafico (V1 o V2) */}
      <ChartModal
        symbol={chartState?.symbol || null}
        tradeInfo={chartState?.tradeInfo || null}
        onClose={closeChart}
      />
    </div>
  );
}
