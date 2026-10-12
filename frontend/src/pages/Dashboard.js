import React, { useState, useCallback, useEffect } from 'react';
import { deskAPI } from '../api';
import ChartModal from '../components/ChartModal';

const V2_SYMBOLS = [
  'BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT',
  'AVAXUSDT','DOTUSDT','MATICUSDT','LINKUSDT','UNIUSDT','LTCUSDT','ATOMUSDT',
  'NEARUSDT','APTUSDT','ARBUSDT','OPUSDT','INJUSDT','SEIUSDT','SUIUSDT',
  'TIAUSDT','WLDUSDT','FETUSDT','RENDERUSDT','XAUUSDT','XAGUSDT',
];

const SYMBOL_EMOJI = {
  BTC:'₿', ETH:'🔷', SOL:'☀️', XRP:'💧', BNB:'🟡', DOGE:'🐕', ADA:'🔵',
  AVAX:'🔺', DOT:'⚪', MATIC:'🟣', LINK:'🔗', UNI:'🦄', LTC:'Ł', ATOM:'⚛️',
  NEAR:'🟩', APT:'🅰️', ARB:'🔵', OP:'🔴', INJ:'💉', SEI:'🌊', SUI:'🌀',
  TIA:'🌌', WLD:'🌍', FET:'🤖', RENDER:'🖥️', XAU:'🥇', XAG:'🥈',
};

const fmt = (v, d = 2) => (v == null || isNaN(v)) ? '--' : Number(v).toFixed(d);

class DeskErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { err: null }; }
  static getDerivedStateFromError(e) { return { err: e }; }
  render() {
    if (this.state.err) return (
      <div style={{ color: '#f87171', fontSize: '12px', padding: '8px' }}>
        Errore nel rendering V2: {this.state.err.message}
      </div>
    );
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
  <span style={{
    padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 'bold',
    background: ok ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)',
    color: ok ? '#4ade80' : '#f87171',
    border: `1px solid ${ok ? 'rgba(74,222,128,0.3)' : 'rgba(248,113,113,0.3)'}`,
  }}>
    {label}: {ok ? okText : badText}
  </span>
);

function MarketCarousel({ symbols, prices, onSymbolClick }) {
  return (
    <div style={{ marginBottom: '16px' }}>
      <div style={{
        display: 'flex', overflowX: 'auto', gap: '8px', paddingBottom: '8px',
        scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch',
      }}>
        {symbols.map(sym => {
          const base = sym.replace('USDT', '').replace('PERP', '');
          const emoji = SYMBOL_EMOJI[base] || '💱';
          const data = prices[sym] || prices[base] || {};
          const isActive = data.price > 0;
          const up = (data.change_24h || 0) >= 0;
          return (
            <div
              key={sym}
              onClick={() => onSymbolClick(sym)}
              style={{
                background: '#1e293b', borderRadius: '12px', padding: '10px 8px',
                border: '1px solid #334155', cursor: 'pointer', flexShrink: 0,
                minWidth: '100px', textAlign: 'center', opacity: isActive ? 1 : 0.55,
              }}
            >
              <div style={{ fontSize: '18px', marginBottom: '4px' }}>{emoji}</div>
              <div style={{ fontSize: '10px', color: '#94a3b8', marginBottom: '4px', fontWeight: 'bold' }}>{base}</div>
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
      <div style={{ fontSize: '10px', color: '#475569', textAlign: 'center', marginTop: '-4px' }}>
        ← scorri per vedere tutti i {symbols.length} simboli →
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [prices, setPrices] = useState({});
  const [deskStatus, setDeskStatus] = useState(null);
  const [now, setNow] = useState(new Date());
  const [chartState, setChartState] = useState(null);
  const [closeAllBusy, setCloseAllBusy] = useState(false);

  const fetchDeskStatus = useCallback(async () => {
    try {
      const r = await deskAPI.getStatus();
      setDeskStatus(r.data);
    } catch (e) { /* desk offline è normale */ }
  }, []);

  const fetchDeskPrices = useCallback(async () => {
    try {
      const p = await deskAPI.getPrices();
      setPrices(p.data);
    } catch (e) { /* prezzi non disponibili */ }
  }, []);

  useEffect(() => { fetchDeskStatus(); const t = setInterval(fetchDeskStatus, 8000); return () => clearInterval(t); }, [fetchDeskStatus]);
  useEffect(() => { fetchDeskPrices(); const t = setInterval(fetchDeskPrices, 60000); return () => clearInterval(t); }, [fetchDeskPrices]);
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 15000); return () => clearInterval(t); }, []);

  const marketLive = Object.keys(prices).length > 0;
  const dateLabel = now.toLocaleDateString('it-IT', { weekday: 'short', day: 'numeric', month: 'short' });
  const timeLabel = now.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });

  const openChart = (symbol, tradeInfo = null) => setChartState({ symbol, tradeInfo });
  const closeChart = () => setChartState(null);

  const v2OpenCount = Array.isArray(deskStatus?.positions) ? deskStatus.positions.length : (deskStatus?.open_positions ?? 0);
  const botOnline = deskStatus?.available === true;

  // equity color: verde se > 1000, giallo se tra 800 e 1000, rosso se < 800
  const equityColor = (eq) => {
    if (eq == null) return '#94a3b8';
    if (eq >= 1000) return '#4ade80';
    if (eq >= 800) return '#fbbf24';
    return '#f87171';
  };

  const pnlColor = (v) => v > 0 ? '#4ade80' : v < 0 ? '#f87171' : '#94a3b8';

  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <h1 style={{
          fontSize: '22px', fontWeight: 'bold',
          background: 'linear-gradient(90deg, #f1f5f9, #38bdf8)',
          WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent',
          margin: 0,
        }}>🤖 SuperBot V2</h1>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          <StatusChip label="Mercato" ok={marketLive} okText="Live" badText="Offline" />
          <StatusChip label="Bot" ok={botOnline} okText="Attivo" badText="Offline" />
        </div>
      </div>

      <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '16px' }}>
        {dateLabel} · <strong style={{ color: '#94a3b8' }}>{timeLabel}</strong>
        {deskStatus?.day && <span> · Giorno {deskStatus.day}</span>}
        {deskStatus?.cycle != null && <span> · Ciclo #{deskStatus.cycle}</span>}
      </div>

      {/* ── KPI principali V2 ── */}
      <DeskErrorBoundary>
        {!deskStatus ? (
          <Card style={{ marginBottom: '16px', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
            ⏳ Connessione al Bot V2...
          </Card>
        ) : !botOnline ? (
          <Card style={{ marginBottom: '16px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
            🔴 Bot V2 non raggiungibile — {deskStatus.message || 'riprovo ogni 8 secondi'}
          </Card>
        ) : (
          <>
            {/* Equity hero */}
            <Card style={{ marginBottom: '12px', textAlign: 'center', borderColor: equityColor(deskStatus.equity) + '40' }}>
              <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px', letterSpacing: '0.05em', textTransform: 'uppercase' }}>Equity</div>
              <div style={{ fontSize: '36px', fontWeight: 'bold', color: equityColor(deskStatus.equity) }}>
                ${fmt(deskStatus.equity)}
              </div>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '16px', marginTop: '8px', fontSize: '12px' }}>
                <span style={{ color: '#64748b' }}>Cassa <strong style={{ color: '#cbd5e1' }}>${fmt(deskStatus.cash)}</strong></span>
                <span style={{ color: '#64748b' }}>Margine <strong style={{ color: '#cbd5e1' }}>${fmt(deskStatus.margin_used, 0)}</strong></span>
              </div>
            </Card>

            {/* KPI secondari */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
              <Card style={{ flex: 1, textAlign: 'center', padding: '12px 8px' }}>
                <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '2px' }}>Aperte</div>
                <div style={{ fontSize: '24px', fontWeight: 'bold', color: v2OpenCount > 0 ? '#38bdf8' : '#94a3b8' }}>{v2OpenCount}</div>
              </Card>
              <Card style={{ flex: 1, textAlign: 'center', padding: '12px 8px' }}>
                <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '2px' }}>Chiuse</div>
                <div style={{ fontSize: '24px', fontWeight: 'bold' }}>{deskStatus.total_closed ?? '--'}</div>
              </Card>
              <Card style={{ flex: 1, textAlign: 'center', padding: '12px 8px' }}>
                <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '2px' }}>Budget AI</div>
                <div style={{
                  fontSize: '18px', fontWeight: 'bold',
                  color: (deskStatus.budget_spent_usd ?? 0) > (deskStatus.budget_daily_cap_usd ?? 0.7) * 0.85 ? '#fbbf24' : '#4ade80'
                }}>
                  ${fmt(deskStatus.budget_spent_usd, 3)}
                </div>
                <div style={{ fontSize: '9px', color: '#475569' }}>/ ${fmt(deskStatus.budget_daily_cap_usd ?? 0.70)} cap</div>
              </Card>
            </div>

            {/* HALT warning */}
            {deskStatus.halt && (
              <Card style={{ marginBottom: '12px', borderColor: '#dc2626', color: '#fca5a5', fontSize: '13px', textAlign: 'center' }}>
                ⚠️ <strong>HALT:</strong> {deskStatus.halt}
              </Card>
            )}

            {/* Pulsante chiusura forzata */}
            {Array.isArray(deskStatus.positions) && deskStatus.positions.length > 0 && (
              <button
                disabled={closeAllBusy}
                onClick={async () => {
                  if (!window.confirm(`Chiudere forzatamente tutte le ${deskStatus.positions.length} posizioni V2?`)) return;
                  setCloseAllBusy(true);
                  try {
                    await deskAPI.closeAll();
                    setTimeout(fetchDeskStatus, 1000);
                  } catch (e) { alert('Errore: ' + (e?.message || e)); }
                  finally { setCloseAllBusy(false); }
                }}
                style={{
                  width: '100%', padding: '10px', borderRadius: '10px', marginBottom: '12px',
                  border: '1px solid #dc2626', background: 'rgba(220,38,38,0.1)',
                  color: '#fca5a5', fontWeight: 'bold', fontSize: '13px',
                  cursor: closeAllBusy ? 'not-allowed' : 'pointer', opacity: closeAllBusy ? 0.6 : 1,
                }}
              >
                {closeAllBusy ? '⏳ Chiusura...' : `🔒 Chiudi tutte le posizioni (${deskStatus.positions.length})`}
              </button>
            )}

            {/* Posizioni V2 aperte */}
            {Array.isArray(deskStatus.positions) && deskStatus.positions.length > 0 && (
              <>
                <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
                  ⚡ Posizioni Aperte
                </h2>
                {deskStatus.positions.map((p, i) => {
                  const sym = p.symbol || '?';
                  const base = sym.replace('USDT', '').replace('PERP', '');
                  const emoji = SYMBOL_EMOJI[base] || '💱';
                  const isLong = p.side === 1 || p.side === 'long';
                  const sideLabel = p.side === 1 ? 'LONG' : p.side === -1 ? 'SHORT'
                    : typeof p.side === 'string' ? p.side.toUpperCase() : '?';
                  const currentPrice = prices[sym]?.price || prices[base]?.price;
                  const pnlEst = currentPrice && p.entry_price && p.qty
                    ? (p.side === 1 ? 1 : -1) * (currentPrice - p.entry_price) * p.qty
                    : null;
                  return (
                    <Card
                      key={i}
                      onClick={() => openChart(sym.endsWith('USDT') ? sym : sym + 'USDT', p)}
                      style={{ marginBottom: '8px', cursor: 'pointer', borderColor: isLong ? '#164e63' : '#4c0519' }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                          <span style={{ fontSize: '20px' }}>{emoji}</span>
                          <span style={{
                            padding: '2px 7px', borderRadius: '5px', fontSize: '10px', fontWeight: 'bold',
                            background: isLong ? '#166534' : '#7f1d1d', color: 'white'
                          }}>{sideLabel}</span>
                          <span style={{ fontWeight: 'bold', fontSize: '14px' }}>{base}</span>
                          <span style={{ color: '#94a3b8', fontSize: '12px' }}>x{p.leverage ?? '--'}</span>
                          <span style={{
                            fontSize: '10px', color: '#475569',
                            background: '#0f172a', padding: '1px 5px', borderRadius: '4px'
                          }}>{p.trade_type || 'medio'}</span>
                          {(p.dca_count ?? 0) > 0 && (
                            <span style={{ color: '#fbbf24', fontSize: '10px' }}>DCA×{p.dca_count}</span>
                          )}
                        </div>
                        <div style={{ textAlign: 'right', fontSize: '12px' }}>
                          <div style={{ color: '#f1f5f9', fontWeight: 'bold' }}>@ ${fmt(p.entry_price)}</div>
                          <div style={{ color: '#64748b' }}>${fmt(p.margin, 0)} margin</div>
                          {pnlEst != null && (
                            <div style={{ color: pnlColor(pnlEst), fontWeight: 'bold', marginTop: '2px' }}>
                              {pnlEst >= 0 ? '+' : ''}{fmt(pnlEst)}$
                            </div>
                          )}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '12px', marginTop: '6px', fontSize: '10px' }}>
                        {p.sl && <span style={{ color: '#f87171' }}>SL ${fmt(p.sl)}</span>}
                        {p.tp && <span style={{ color: '#4ade80' }}>TP ${fmt(p.tp)}</span>}
                        {currentPrice && <span style={{ color: '#94a3b8' }}>Live ${fmt(currentPrice)}</span>}
                      </div>
                      <div style={{ fontSize: '10px', color: '#334155', marginTop: '4px', textAlign: 'right' }}>
                        📈 tocca per grafico
                      </div>
                    </Card>
                  );
                })}
              </>
            )}

            {v2OpenCount === 0 && (
              <Card style={{ marginBottom: '12px', textAlign: 'center', color: '#475569', fontSize: '13px' }}>
                Nessuna posizione aperta al momento
              </Card>
            )}
          </>
        )}
      </DeskErrorBoundary>

      {/* ── Mercato Live ── */}
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '4px', marginTop: '8px', color: '#cbd5e1' }}>
        📊 Mercato Live
      </h2>
      <p style={{ fontSize: '11px', color: '#475569', marginBottom: '8px' }}>
        {V2_SYMBOLS.length} simboli monitorati dal Bot V2 — tocca per aprire il grafico
      </p>
      <MarketCarousel
        symbols={V2_SYMBOLS}
        prices={prices}
        onSymbolClick={(sym) => openChart(sym)}
      />

      {/* Modal grafico */}
      <ChartModal
        symbol={chartState?.symbol || null}
        tradeInfo={chartState?.tradeInfo || null}
        onClose={closeChart}
      />
    </div>
  );
}
