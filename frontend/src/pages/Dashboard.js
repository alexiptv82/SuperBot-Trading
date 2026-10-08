import React, { useState, useEffect, useCallback } from 'react';
import { botAPI } from '../api';
import ChartModal from '../components/ChartModal';
const Card = ({ children, style, onClick }) => (
  <div onClick={onClick} style={{
    background: '#1e293b', borderRadius: '16px', padding: '16px',
    border: '1px solid #334155', ...style
  }}>{children}</div>
);
const PriceCard = ({ symbol, data, onClick }) => {
  const emoji = { BTCUSDT:'₿', ETHUSDT:'Ξ', XAUUSDT:'🥇', XAGUSDT:'🥈' };
  const up = data?.change_24h > 0;
  return (
    <Card onClick={onClick} style={{
      flex: '1 1 calc(50% - 8px)', minWidth: '140px', cursor: 'pointer'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ fontSize: '20px', marginBottom: '4px' }}>{emoji[symbol] || '💱'}</div>
        <div style={{ fontSize: '14px', color: '#475569' }}>📈</div>
      </div>
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

export default function Dashboard() {
  const [status, setStatus] = useState(null);
  const [prices, setPrices] = useState({});
  const [openTrades, setOpenTrades] = useState([]);
  const [loading, setLoading] = useState(false);
  const [apiError, setApiError] = useState(false);
  const [now, setNow] = useState(new Date());
  const [chartSymbol, setChartSymbol] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const [s, p, o] = await Promise.all([
        botAPI.getStatus(), botAPI.getPrices(), botAPI.getOpenTrades()
      ]);
      setStatus(s.data); setPrices(p.data); setOpenTrades(o.data);
      setApiError(false);
    } catch (e) { console.error(e); setApiError(true); }
  }, []);
  useEffect(() => { fetchData(); const t = setInterval(fetchData, 10000); return () => clearInterval(t); }, [fetchData]);
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

      <Card style={{
        marginBottom: '16px', textAlign: 'center',
        boxShadow: status?.is_running ? '0 0 0 1px rgba(74,222,128,0.2)' : 'none'
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
          <PriceCard key={sym} symbol={sym} data={data} onClick={() => setChartSymbol(sym)} />
        ))}
      </div>
      {openTrades.length > 0 && (
        <>
          <h2 style={{ fontSize: '16px', fontWeight: 'bold', marginBottom: '10px' }}>⚡ Posizioni Aperte</h2>
          {openTrades.map((t, i) => (
            <Card key={i} onClick={() => setChartSymbol(t.symbol)} style={{ marginBottom: '8px', cursor: 'pointer' }}>
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
      <ChartModal symbol={chartSymbol} onClose={() => setChartSymbol(null)} />
    </div>
  );
}
