import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { botAPI } from '../api';

const PAGE_SIZE = 50;
const MUTED = '#94a3b8';
const BORDER = '#334155';
const SURFACE = '#1e293b';

const Chip = ({ active, onClick, children }) => (
  <button onClick={onClick} style={{
    padding: '6px 12px', borderRadius: '999px', fontSize: '12px', fontWeight: 'bold',
    border: `1px solid ${active ? '#38bdf8' : BORDER}`,
    background: active ? 'rgba(56,189,248,0.15)' : 'transparent',
    color: active ? '#38bdf8' : MUTED, cursor: 'pointer', whiteSpace: 'nowrap'
  }}>{children}</button>
);

export default function Trades() {
  const [trades, setTrades] = useState([]);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [symbolFilter, setSymbolFilter] = useState('all');
  const [sideFilter, setSideFilter] = useState('all');
  const [outcomeFilter, setOutcomeFilter] = useState('all');

  const loadPage = useCallback(async (nextOffset) => {
    setLoading(true);
    try {
      const { data } = await botAPI.getTrades(PAGE_SIZE, nextOffset);
      setTrades(prev => nextOffset === 0 ? data : [...prev, ...data]);
      setHasMore(data.length === PAGE_SIZE);
      setOffset(nextOffset + data.length);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadPage(0); }, [loadPage]);

  const symbols = useMemo(() => {
    const set = new Set(trades.map(t => t.symbol).filter(Boolean));
    return ['all', ...Array.from(set).sort()];
  }, [trades]);

  const filtered = trades.filter(t => {
    if (symbolFilter !== 'all' && t.symbol !== symbolFilter) return false;
    if (sideFilter !== 'all' && t.side !== sideFilter) return false;
    if (outcomeFilter === 'open' && t.status !== 'open') return false;
    if (outcomeFilter === 'win' && !(t.status !== 'open' && t.pnl > 0)) return false;
    if (outcomeFilter === 'loss' && !(t.status !== 'open' && t.pnl < 0)) return false;
    return true;
  });

  const pnlColor = (v) => v > 0 ? '#4ade80' : v < 0 ? '#f87171' : MUTED;

  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '14px' }}>💹 Storico Trade</h1>

      <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', marginBottom: '8px', paddingBottom: '2px' }}>
        {symbols.map(s => (
          <Chip key={s} active={symbolFilter === s} onClick={() => setSymbolFilter(s)}>
            {s === 'all' ? 'Tutti' : s.replace('USDT', '')}
          </Chip>
        ))}
      </div>
      <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', marginBottom: '8px', paddingBottom: '2px' }}>
        {[['all', 'Lato'], ['long', 'Long'], ['short', 'Short']].map(([v, l]) => (
          <Chip key={v} active={sideFilter === v} onClick={() => setSideFilter(v)}>{l}</Chip>
        ))}
      </div>
      <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', marginBottom: '16px', paddingBottom: '2px' }}>
        {[['all', 'Tutti'], ['open', 'Aperti'], ['win', 'Vincenti'], ['loss', 'Perdenti']].map(([v, l]) => (
          <Chip key={v} active={outcomeFilter === v} onClick={() => setOutcomeFilter(v)}>{l}</Chip>
        ))}
      </div>

      {filtered.length === 0 ? (
        <div style={{ textAlign: 'center', color: MUTED, padding: '40px' }}>
          {trades.length === 0 ? 'Nessun trade ancora. Avvia il bot dalla Dashboard.' : 'Nessun trade corrisponde ai filtri.'}
        </div>
      ) : filtered.map(t => (
        <div key={t.id} style={{
          background: SURFACE, borderRadius: '12px', padding: '14px',
          marginBottom: '10px', border: `1px solid ${BORDER}`
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{
                padding: '2px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: 'bold',
                background: t.side === 'long' ? '#166534' : '#7f1d1d', color: 'white'
              }}>{t.side?.toUpperCase()}</span>
              <span style={{ fontWeight: 'bold' }}>{t.symbol}</span>
              <span style={{ color: MUTED, fontSize: '12px' }}>x{t.leverage}</span>
            </div>
            <span style={{
              padding: '2px 8px', borderRadius: '6px', fontSize: '11px',
              background: t.status === 'open' ? '#1e40af' : SURFACE,
              border: `1px solid ${BORDER}`, color: MUTED
            }}>{t.status}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
            <div>
              <div style={{ color: MUTED }}>Entrata</div>
              <div>${t.entry_price?.toFixed(2)}</div>
            </div>
            <div>
              <div style={{ color: MUTED }}>Uscita</div>
              <div>{t.exit_price ? `$${t.exit_price?.toFixed(2)}` : '--'}</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ color: MUTED }}>P&L</div>
              <div style={{ fontWeight: 'bold', color: pnlColor(t.pnl) }}>
                {t.pnl ? `${t.pnl > 0 ? '+' : ''}${t.pnl.toFixed(2)}$` : '--'}
              </div>
            </div>
          </div>
          {t.close_reason && (
            <div style={{ marginTop: '6px', fontSize: '11px', color: '#64748b' }}>
              Chiuso: {t.close_reason?.toUpperCase()} | {t.trade_type}
            </div>
          )}
        </div>
      ))}

      {hasMore && (
        <button onClick={() => loadPage(offset)} disabled={loading} style={{
          width: '100%', padding: '12px', borderRadius: '10px', border: `1px solid ${BORDER}`,
          background: 'none', color: MUTED, fontWeight: 'bold',
          cursor: loading ? 'not-allowed' : 'pointer', marginTop: '4px'
        }}>
          {loading ? 'Caricamento...' : 'Carica altri'}
        </button>
      )}
    </div>
  );
}
