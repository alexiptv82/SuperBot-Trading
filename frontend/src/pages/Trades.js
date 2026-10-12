import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { deskAPI } from '../api';

const PAGE_SIZE = 100;
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
  const [trades, setTrades] = useState([]);       // chiusi dal JSONL
  const [openPos, setOpenPos] = useState([]);     // aperti dallo stato live
  const [loading, setLoading] = useState(false);
  const [symbolFilter, setSymbolFilter] = useState('all');
  const [sideFilter, setSideFilter] = useState('all');
  const [outcomeFilter, setOutcomeFilter] = useState('all');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [histRes, statusRes] = await Promise.all([
        deskAPI.getTrades(PAGE_SIZE),
        deskAPI.getStatus(),
      ]);
      setTrades(Array.isArray(histRes.data) ? histRes.data : []);
      // posizioni aperte da status — le trasformiamo nel formato card
      const pos = statusRes.data?.positions;
      if (Array.isArray(pos)) {
        setOpenPos(pos.map(p => ({
          symbol: p.symbol,
          side: p.side,
          entry_price: p.entry,
          exit_price: null,        // aperta
          leverage: p.leverage,
          margin: p.margin,
          trade_type: p.trade_type,
          pnl: null,
          open_ms: null,
          close_ms: null,
          close_reason: null,
          _isOpen: true,
        })));
      } else {
        setOpenPos([]);
      }
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // unione: aperti in testa, poi chiusi
  const allTrades = useMemo(() => [...openPos, ...trades], [openPos, trades]);

  const symbols = useMemo(() => {
    const set = new Set(allTrades.map(t => t.symbol).filter(Boolean));
    return ['all', ...Array.from(set).sort()];
  }, [allTrades]);

  // side V2 è int (1=LONG, -1=SHORT) — normalizza a stringa per i filtri
  const sideStr = (s) => s === 1 ? 'long' : s === -1 ? 'short' : (s || '').toLowerCase();

  const filtered = allTrades.filter(t => {
    if (symbolFilter !== 'all' && t.symbol !== symbolFilter) return false;
    if (sideFilter !== 'all' && sideStr(t.side) !== sideFilter) return false;
    const isOpen = t._isOpen || t.exit_price == null;
    if (outcomeFilter === 'open' && !isOpen) return false;
    if (outcomeFilter === 'win' && !(t.exit_price != null && (t.pnl ?? 0) > 0)) return false;
    if (outcomeFilter === 'loss' && !(t.exit_price != null && (t.pnl ?? 0) < 0)) return false;
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

      {loading && trades.length === 0 ? (
        <div style={{ textAlign: 'center', color: MUTED, padding: '40px' }}>Caricamento...</div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', color: MUTED, padding: '40px' }}>
          {trades.length === 0
            ? 'Nessun trade chiuso ancora. Il bot scrive qui ogni volta che chiude una posizione.'
            : 'Nessun trade corrisponde ai filtri.'}
        </div>
      ) : filtered.map((t, i) => {
        const sd = sideStr(t.side);
        const closed = t.exit_price != null;
        const pnl = t.pnl ?? t.net;
        const fmt2 = (v, d = 4) => v != null ? Number(v).toFixed(d) : '--';
        return (
          <div key={i} style={{
            background: SURFACE, borderRadius: '12px', padding: '14px',
            marginBottom: '10px', border: `1px solid ${BORDER}`
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{
                  padding: '2px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: 'bold',
                  background: sd === 'long' ? '#166534' : '#7f1d1d', color: 'white'
                }}>{sd.toUpperCase()}</span>
                <span style={{ fontWeight: 'bold' }}>{t.symbol?.replace('USDT', '')}</span>
                <span style={{ color: MUTED, fontSize: '12px' }}>x{t.leverage ?? '--'}</span>
                <span style={{ color: '#64748b', fontSize: '10px' }}>[{t.trade_type || 'medio'}]</span>
              </div>
              <span style={{
                padding: '2px 8px', borderRadius: '6px', fontSize: '11px',
                background: !closed ? '#1e40af' : SURFACE,
                border: `1px solid ${BORDER}`, color: MUTED
              }}>{closed ? (t.close_reason?.toUpperCase() || 'CHIUSO') : 'APERTO'}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', fontSize: '12px' }}>
              <div>
                <div style={{ color: MUTED, fontSize: '10px' }}>Entrata</div>
                <div>${fmt2(t.entry_price, 4)}</div>
              </div>
              <div>
                <div style={{ color: MUTED, fontSize: '10px' }}>Uscita</div>
                <div>{t.exit_price != null ? `$${fmt2(t.exit_price, 4)}` : '--'}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: MUTED, fontSize: '10px' }}>P&L netto</div>
                <div style={{ fontWeight: 'bold', color: pnlColor(pnl) }}>
                  {pnl != null ? `${pnl > 0 ? '+' : ''}${Number(pnl).toFixed(2)}$` : '--'}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '12px', marginTop: '6px', fontSize: '11px', color: '#64748b' }}>
              <span>Margin: ${fmt2(t.margin, 0)}</span>
              {t.gross_pnl != null && <span>Lordo: {Number(t.gross_pnl) > 0 ? '+' : ''}{Number(t.gross_pnl).toFixed(2)}$</span>}
              {t.fees != null && <span>Fee: -{Number(t.fees).toFixed(2)}$</span>}
              {(t.dca_count ?? 0) > 0 && <span style={{ color: '#fbbf24' }}>DCA×{t.dca_count}</span>}
            </div>
            {t.open_ms && (
              <div style={{ fontSize: '10px', color: '#334155', marginTop: '4px' }}>
                {new Date(t.open_ms).toLocaleString('it-IT')}
                {t.close_ms && ` → ${new Date(t.close_ms).toLocaleString('it-IT')}`}
              </div>
            )}
          </div>
        );
      })}

      <button onClick={load} disabled={loading} style={{
        width: '100%', padding: '12px', borderRadius: '10px', border: `1px solid ${BORDER}`,
        background: 'none', color: MUTED, fontWeight: 'bold',
        cursor: loading ? 'not-allowed' : 'pointer', marginTop: '4px'
      }}>
        {loading ? 'Aggiornamento...' : '🔄 Aggiorna'}
      </button>
    </div>
  );
}
