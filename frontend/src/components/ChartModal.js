import React, { useEffect, useRef } from 'react';

// Mappa i simboli usati dal bot al simbolo TradingView corrispondente.
// BitGet è il nostro exchange reale; se un simbolo non è listato lì su
// TradingView, si può cambiare qui senza toccare il resto dell'app.
const TV_SYMBOL = {
  BTCUSDT: 'BITGET:BTCUSDT',
  ETHUSDT: 'BITGET:ETHUSDT',
  XAUUSDT: 'BITGET:XAUUSDT',
  XAGUSDT: 'BITGET:XAGUSDT',
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

export default function ChartModal({ symbol, onClose }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!symbol) return;
    let cancelled = false;
    loadTradingViewScript().then(() => {
      if (cancelled || !containerRef.current || !window.TradingView) return;
      containerRef.current.innerHTML = '';
      // eslint-disable-next-line no-new
      new window.TradingView.widget({
        autosize: true,
        symbol: TV_SYMBOL[symbol] || symbol,
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
        container_id: 'tv_chart_container',
      });
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [symbol]);

  if (!symbol) return null;

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: '#0a0d12', zIndex: 1000,
      display: 'flex', flexDirection: 'column'
    }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '12px 16px', borderBottom: '1px solid #334155',
        paddingTop: 'calc(12px + env(safe-area-inset-top))'
      }}>
        <div style={{ fontWeight: 'bold', fontSize: '15px' }}>
          📈 {symbol.replace('USDT', '')}
        </div>
        <button onClick={onClose} style={{
          background: '#1e293b', border: '1px solid #334155', color: '#f1f5f9',
          borderRadius: '8px', width: '32px', height: '32px', fontSize: '16px', cursor: 'pointer'
        }}>✕</button>
      </div>
      <div id="tv_chart_container" ref={containerRef} style={{ flex: 1 }} />
    </div>
  );
}
