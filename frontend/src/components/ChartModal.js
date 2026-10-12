import React, { useEffect, useRef } from 'react';

// Mappa ogni simbolo del bot al ticker TradingView.
// - Crypto: usiamo BITGET (il nostro exchange reale).
// - Oro/Argento: BITGET li ha come futures sintetici ma TV usa il codice
//   spot OANDA per il feed di prezzo continuo.
const TV_SYMBOL = {
  BTCUSDT:  'BITGET:BTCUSDT',
  ETHUSDT:  'BITGET:ETHUSDT',
  BNBUSDT:  'BITGET:BNBUSDT',
  XRPUSDT:  'BITGET:XRPUSDT',
  SOLUSDT:  'BITGET:SOLUSDT',
  ADAUSDT:  'BITGET:ADAUSDT',
  DOGEUSDT: 'BITGET:DOGEUSDT',
  AVAXUSDT: 'BITGET:AVAXUSDT',
  DOTUSDT:  'BITGET:DOTUSDT',
  LINKUSDT: 'BITGET:LINKUSDT',
  MATICUSDT:'BITGET:MATICUSDT',
  UNIUSDT:  'BITGET:UNIUSDT',
  ATOMUSDT: 'BITGET:ATOMUSDT',
  LTCUSDT:  'BITGET:LTCUSDT',
  BCHUSDT:  'BITGET:BCHUSDT',
  APTUSDT:  'BITGET:APTUSDT',
  ARBUSDT:  'BITGET:ARBUSDT',
  OPUSDT:   'BITGET:OPUSDT',
  NEARUSDT: 'BITGET:NEARUSDT',
  FILUSDT:  'BITGET:FILUSDT',
  INJUSDT:  'BITGET:INJUSDT',
  SUIUSDT:  'BITGET:SUIUSDT',
  TIAUSDT:  'BITGET:TIAUSDT',
  RUNEUSDT: 'BITGET:RUNEUSDT',
  STXUSDT:  'BITGET:STXUSDT',
  XAUUSDT:  'OANDA:XAUUSD',
  XAGUSDT:  'OANDA:XAGUSD',
};

let tvScriptPromise = null;
function loadTradingViewScript() {
  if (window.TradingView) return Promise.resolve();
  if (!tvScriptPromise) {
    tvScriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://s3.tradingview.com/tv.js';
      script.async = true;
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }
  return tvScriptPromise;
}

// Genera un id container univoco per evitare conflitti se il modal viene
// rimontato rapidamente con simboli diversi.
let chartSeq = 0;

export default function ChartModal({ symbol, onClose, tradeInfo }) {
  const containerRef = useRef(null);
  const containerId = useRef('tv_chart_' + (++chartSeq));

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    loadTradingViewScript().then(() => {
      if (cancelled || !containerRef.current || !window.TradingView) return;
      containerRef.current.innerHTML = '';
      // Crea un div interno con l'id univoco richiesto da TradingView
      const inner = document.createElement('div');
      inner.id = containerId.current;
      inner.style.width = '100%';
      inner.style.height = '100%';
      containerRef.current.appendChild(inner);

      // eslint-disable-next-line no-new
      new window.TradingView.widget({
        autosize: true,
        symbol: TV_SYMBOL[symbol] || ('BITGET:' + symbol),
        interval: '15',
        timezone: 'Etc/UTC',
        theme: 'dark',
        style: '1',
        locale: 'it',
        toolbar_bg: '#0f172a',
        enable_publishing: false,
        hide_top_toolbar: false,
        hide_legend: false,
        save_image: false,
        container_id: containerId.current,
      });
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [symbol]);

  if (!symbol) return null;

  const cleanSym = symbol.replace('USDT', '');
  const fmt = (v, d = 2) => { const n = parseFloat(v); return isNaN(n) ? '--' : n.toFixed(d); };
  const sideLabel = tradeInfo
    ? (tradeInfo.side === 1 ? 'LONG' : tradeInfo.side === -1 ? 'SHORT'
        : typeof tradeInfo.side === 'string' ? tradeInfo.side.toUpperCase() : '?')
    : null;
  const sideColor = (tradeInfo?.side === 1 || tradeInfo?.side === 'long') ? '#4ade80' : '#f87171';

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: '#0a0d12', zIndex: 1000,
      display: 'flex', flexDirection: 'column'
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '12px 16px', borderBottom: '1px solid #334155',
        paddingTop: 'calc(12px + env(safe-area-inset-top))',
        flexShrink: 0,
      }}>
        <div style={{ fontWeight: 'bold', fontSize: '15px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          📈 {cleanSym}
          {sideLabel && (
            <span style={{
              fontSize: '11px', fontWeight: 'bold', padding: '2px 8px', borderRadius: '6px',
              background: (tradeInfo?.side === 1 || tradeInfo?.side === 'long') ? '#166534' : '#7f1d1d',
              color: 'white'
            }}>{sideLabel}</span>
          )}
        </div>
        <button onClick={onClose} style={{
          background: '#1e293b', border: '1px solid #334155', color: '#f1f5f9',
          borderRadius: '8px', width: '32px', height: '32px', fontSize: '16px', cursor: 'pointer'
        }}>✕</button>
      </div>

      {/* Dettagli trade V2 (solo se abbiamo tradeInfo) */}
      {tradeInfo && (
        <div style={{
          display: 'flex', gap: '6px', padding: '10px 16px',
          borderBottom: '1px solid #1e293b', flexShrink: 0,
          overflowX: 'auto', flexWrap: 'nowrap',
        }}>
          {[
            { label: 'Entrata', value: '$' + fmt(tradeInfo.entry_price) },
            { label: 'Leva', value: 'x' + (tradeInfo.leverage ?? '--') },
            { label: 'Margin', value: '$' + fmt(tradeInfo.margin, 0) },
            { label: 'TP', value: tradeInfo.tp ? '$' + fmt(tradeInfo.tp) : '--' },
            { label: 'SL', value: tradeInfo.sl ? '$' + fmt(tradeInfo.sl) : '--' },
            ...(tradeInfo.dca_count > 0 ? [{ label: 'DCA', value: '×' + tradeInfo.dca_count }] : []),
            { label: 'Tipo', value: tradeInfo.trade_type || 'medio' },
          ].map(({ label, value }) => (
            <div key={label} style={{
              background: '#1e293b', border: '1px solid #334155', borderRadius: '8px',
              padding: '6px 10px', textAlign: 'center', flexShrink: 0,
            }}>
              <div style={{ fontSize: '9px', color: '#64748b', marginBottom: '2px' }}>{label}</div>
              <div style={{
                fontSize: '12px', fontWeight: 'bold',
                color: label === 'TP' ? '#4ade80' : label === 'SL' ? '#f87171' : label === 'Entrata' ? sideColor : '#f1f5f9'
              }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Grafico TradingView */}
      <div ref={containerRef} style={{ flex: 1, minHeight: 0 }} />
    </div>
  );
}
