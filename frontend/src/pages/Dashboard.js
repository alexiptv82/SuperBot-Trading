import React, { useState, useEffect, useCallback } from 'react';
import { botAPI } from '../api';
const Card = ({ children, style }) => (
  <div style={{
    background: '#1e293b', borderRadius: '16px', padding: '16px',
    border: '1px solid #334155', ...style
  }}>{children}</div>
);
const PriceCard = ({ symbol, data }) => {
  const emoji = { BTCUSDT:'₿', ETHUSDT:'Ξ', XAUUSDT:'🥇', XAGUSDT:'🥈' };
  const up = data?.change_24h > 0;
  return (
    <Card style={{ flex: '1 1 calc(50% - 8px)', minWidth: '140px' }}>
      <div style={{ fontSize: '20px', marginBottom: '4px' }}>{emoji[symbol] || '💱'}</div>
      <div style={{ fontSize: '11px', color: '#94a3b8', marginBottom: '4px' }}>
        {symbol.replace('USDT','')}
      </div>
      <div style={{ fontSize: '16px', fontWeight: 'bold' }}>
        ${data?.price?.toLocaleString() || '--'}
      </div>
      <div style={{ fontSize: '12px', color: up ? '#4ade80' : '#f87171', marginTop: '2px' }}>
        {up ? '▲' : '▼'} {Math.abs(data?.change_24h || 0).toFixed(2)}%
      </div>
    </Card>
  );
};
export default function Dashboard() {
  const [status, setStatus] = useState(null);
  const [prices, setPrices] = useState({});
  const [openTrades, setOpenTrades] = useState([]);
  const [loading, setLoading] = useState(false);
  const fetchData = useCallback(async () => {
    try {
      const [s, p, o] = await Promise.all([
        botAPI.getStatus(), botAPI.getPrices(), botAPI.getOpenTrades()
      ]);
      setStatus(s.data); setPrices(p.data); setOpenTrades(o.data);
    } catch (e) { console.error(e); }
  }, []);
  useEffect(() => { fetchData(); const t = setInterval(fetchData, 10000); return () => clearInterval(t); }, [fetchData]);
  const toggleBot = async () => {
    setLoading(true);
    try {
      if (status?.is_running) await botAPI.stop(); else await botAPI.start();
      await fetchData();
    } finally { setLoading(false); }
  };
  const pnlColor = (v) => v > 0 ? '#4ade80' : v < 0 ? '#f87171' : '#94a3b8';
  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
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
      <Card style={{
        marginBottom: '16px', textAlign: 'center',
        boxShadow: status?.is_running ? '0 0 0 1px rgba(74,222,128,0.25), 0 0 24px rgba(74,222,128,0.12)' : 'none'
      }}>
        <div style={{ fontSize: '48px', marginBottom: '8px' }}>
          {status?.is_running ? '🟢' : '🔴'}
        </div>
        <div style={{ fontSize: '18px', fontWeight: 'bold', marginBottom: '4px' }}>
          {status?.is_running ? 'Bot Attivo' : 'Bot Fermo'}
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
      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
        <Card style={{ flex: 1, textAlign: 'center' }}>
          <div style={{ color: '#94a3b8', fontSize: '12px', marginBottom: '4px' }}>Capitale</div>
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
      <h2 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '10px' }}>📈 Mercato Live</h2>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
        {Object.entries(prices).map(([sym, data]) => (
          <PriceCard key={sym} symbol={sym} data={data} />
        ))}
      </div>
      {openTrades.length > 0 && (
        <>
          <h2 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '10px' }}>⚡ Posizioni Aperte</h2>
          {openTrades.map((t, i) => (
            <Card key={i} style={{ marginBottom: '8px' }}>
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
                  <span style={{ color: '#94a3b8', fontSize: '12px', marginLeft: '6px' }}>x{t.leverage}</span>
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
    </div>
  );
}
