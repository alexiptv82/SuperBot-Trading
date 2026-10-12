import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { deskAPI, bullAPI, errMsg } from '../api';
import { fmtDateTime, fmtDuration, signed, pnlColor } from '../deskUi';

const PAGE_SIZE = 100;
const MUTED = '#94a3b8';
const BORDER = '#334155';
const SURFACE = '#1e293b';
const ACCENT = '#38bdf8';

const apiFor = (portfolio) => (portfolio === 'bull' ? bullAPI : deskAPI);

// Motivo di chiusura in parole
const REASON = {
  'stop loss': 'STOP LOSS',
  'take profit': 'TAKE PROFIT',
  'liquidazione': 'LIQUIDAZIONE',
  'chiusura Claude': 'USCITA DEL BOT',
  'chiusura manuale': 'CHIUSURA MANUALE',
};
const reasonLabel = (r) => REASON[r] || (r ? String(r).toUpperCase().slice(0, 22) : 'CHIUSO');

const Chip = ({ active, onClick, children }) => (
  <button onClick={onClick} style={{
    padding: '6px 12px', borderRadius: '999px', fontSize: '12px', fontWeight: 'bold',
    border: `1px solid ${active ? ACCENT : BORDER}`,
    background: active ? 'rgba(56,189,248,0.15)' : 'transparent',
    color: active ? ACCENT : MUTED, cursor: 'pointer', whiteSpace: 'nowrap'
  }}>{children}</button>
);

const price = (v) => (v == null || isNaN(v)) ? '--' : Number(v).toFixed(Number(v) < 1 ? 5 : 2);

export default function Trades() {
  const [portfolio, setPortfolio] = useState('hawk');
  const [closed, setClosed] = useState([]);       // chiusi (storico)
  const [open, setOpen] = useState([]);           // aperti, con P&L live
  const [meta, setMeta] = useState(null);         // stato del bot
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [symbolFilter, setSymbolFilter] = useState('all');
  const [sideFilter, setSideFilter] = useState('all');
  const [outcomeFilter, setOutcomeFilter] = useState('all');

  const load = useCallback(async (pf, quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const api = apiFor(pf);
      const [histRes, statusRes] = await Promise.all([api.getTrades(PAGE_SIZE), api.getStatus()]);
      setClosed(Array.isArray(histRes.data) ? histRes.data : []);
      const st = statusRes.data || {};
      setMeta(st);
      setOpen(Array.isArray(st.positions) ? st.positions.map(p => ({
        symbol: p.symbol, side: p.side, entry_price: p.entry_price, exit_price: null,
        live_price: p.price, price_source: p.price_source,
        leverage: p.leverage, margin: p.margin, trade_type: p.trade_type, pnl: p.pnl, pnl_pct: p.pnl_pct,
        open_ms: p.open_ms, close_ms: null, dca_count: p.dca_count, sl: p.sl, tp: p.tp,
        entry_reason: p.reason, _isOpen: true,
      })) : []);
      setError('');
    } catch (e) {
      setError(`Impossibile leggere i trade: ${errMsg(e)}`);
    } finally {
      if (!quiet) setLoading(false);
    }
  }, []);

  useEffect(() => {
    setClosed([]); setOpen([]); setMeta(null);
    setSymbolFilter('all');
    load(portfolio);
    const t = setInterval(() => load(portfolio, true), 15000);   // il P&L dei trade aperti si aggiorna da solo
    return () => clearInterval(t);
  }, [portfolio, load]);

  const allTrades = useMemo(() => [...open, ...closed], [open, closed]);

  const symbols = useMemo(() => {
    const set = new Set(allTrades.map(t => t.symbol).filter(Boolean));
    return ['all', ...Array.from(set).sort()];
  }, [allTrades]);

  const sideStr = (s) => (s === 1 ? 'long' : s === -1 ? 'short' : '');

  const filtered = allTrades.filter(t => {
    if (symbolFilter !== 'all' && t.symbol !== symbolFilter) return false;
    if (sideFilter !== 'all' && sideStr(t.side) !== sideFilter) return false;
    if (outcomeFilter === 'open' && !t._isOpen) return false;
    if (outcomeFilter === 'win' && !(!t._isOpen && (t.pnl ?? 0) > 0)) return false;
    if (outcomeFilter === 'loss' && !(!t._isOpen && (t.pnl ?? 0) < 0)) return false;
    return true;
  });

  const openPnl = open.reduce((a, t) => a + (t.pnl || 0), 0);
  const closedNet = closed.reduce((a, t) => a + (t.pnl || 0), 0);

  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '14px' }}>💹 Trade</h1>

      {/* Portafoglio */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '12px', background: SURFACE, borderRadius: '12px', padding: '4px', border: `1px solid ${BORDER}` }}>
        {[['hawk', '🦅 Hawk', ACCENT], ['bull', '🐂 Bull', '#7c3aed']].map(([id, label, color]) => (
          <button key={id} onClick={() => setPortfolio(id)} style={{
            flex: 1, padding: '10px', border: 'none', borderRadius: '10px',
            background: portfolio === id ? color : 'transparent',
            color: portfolio === id ? '#fff' : MUTED, fontWeight: 'bold', cursor: 'pointer', fontSize: '13px',
          }}>{label}</button>
        ))}
      </div>

      {/* Riepilogo */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
        <div style={{ flex: 1, background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: '10px', padding: '8px 10px', textAlign: 'center' }}>
          <div style={{ fontSize: '10px', color: MUTED }}>Aperti ora</div>
          <div style={{ fontSize: '16px', fontWeight: 'bold' }}>{open.length}</div>
          <div style={{ fontSize: '11px', color: pnlColor(openPnl) }}>{signed(openPnl)}$ latente</div>
        </div>
        <div style={{ flex: 1, background: SURFACE, border: `1px solid ${BORDER}`, borderRadius: '10px', padding: '8px 10px', textAlign: 'center' }}>
          <div style={{ fontSize: '10px', color: MUTED }}>Chiusi{meta?.total_closed > closed.length ? ` (ultimi ${closed.length})` : ''}</div>
          <div style={{ fontSize: '16px', fontWeight: 'bold' }}>{meta?.total_closed ?? closed.length}</div>
          <div style={{ fontSize: '11px', color: pnlColor(closedNet) }}>{signed(closedNet)}$ netto</div>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: '12px', padding: '8px 10px', borderRadius: '8px', background: 'rgba(220,38,38,0.1)', color: '#fca5a5', fontSize: '12px' }}>
          {error}
        </div>
      )}

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

      {loading && allTrades.length === 0 ? (
        <div style={{ textAlign: 'center', color: MUTED, padding: '40px' }}>Caricamento...</div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', color: MUTED, padding: '40px' }}>
          {allTrades.length === 0
            ? 'Ancora nessun trade. Appena il bot apre una posizione la vedi qui, e quando la chiude passa nello storico.'
            : 'Nessun trade corrisponde ai filtri.'}
        </div>
      ) : filtered.map((t, i) => {
        const long = t.side === 1;
        const isOpen = !!t._isOpen;
        const pnl = t.pnl;
        return (
          <div key={`${isOpen ? 'o' : 'c'}-${t.symbol}-${t.id ?? ''}-${t.close_ms ?? t.open_ms ?? i}-${i}`} style={{
            background: SURFACE, borderRadius: '12px', padding: '14px', marginBottom: '10px',
            border: `1px solid ${isOpen ? 'rgba(56,189,248,0.4)' : BORDER}`
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span style={{
                  padding: '2px 8px', borderRadius: '6px', fontSize: '11px', fontWeight: 'bold',
                  background: long ? '#166534' : '#7f1d1d', color: 'white'
                }}>{long ? 'LONG' : 'SHORT'}</span>
                <span style={{ fontWeight: 'bold' }}>{t.symbol?.replace('USDT', '')}</span>
                <span style={{ color: MUTED, fontSize: '12px' }}>x{t.leverage ?? '--'}</span>
                <span style={{ color: '#64748b', fontSize: '10px' }}>[{t.trade_type || 'medio'}]</span>
                {t.partial && (
                  <span style={{ fontSize: '9px', color: ACCENT, border: `1px solid ${ACCENT}`, borderRadius: '4px', padding: '0 3px' }}>
                    PARZIALE
                  </span>
                )}
              </div>
              <span style={{
                padding: '2px 8px', borderRadius: '6px', fontSize: '11px',
                background: isOpen ? '#1e40af' : SURFACE, border: `1px solid ${BORDER}`, color: isOpen ? '#fff' : MUTED
              }}>{isOpen ? 'APERTO' : reasonLabel(t.close_reason)}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px', fontSize: '12px' }}>
              <div>
                <div style={{ color: MUTED, fontSize: '10px' }}>Entrata</div>
                <div>${price(t.entry_price)}</div>
              </div>
              <div>
                <div style={{ color: MUTED, fontSize: '10px' }}>{isOpen ? 'Prezzo ora' : 'Uscita'}</div>
                <div>{isOpen ? `$${price(t.live_price)}` : (t.exit_price != null ? `$${price(t.exit_price)}` : '--')}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: MUTED, fontSize: '10px' }}>{isOpen ? 'P&L latente' : 'P&L netto'}</div>
                <div style={{ fontWeight: 'bold', color: pnlColor(pnl) }}>
                  {pnl != null ? `${signed(pnl)}$` : '--'}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '12px', marginTop: '6px', fontSize: '11px', color: '#64748b', flexWrap: 'wrap' }}>
              <span>Margine: ${t.margin != null ? Number(t.margin).toFixed(0) : '--'}</span>
              {isOpen && t.sl && <span style={{ color: '#f87171' }}>SL ${price(t.sl)}</span>}
              {isOpen && t.tp && <span style={{ color: '#4ade80' }}>TP ${price(t.tp)}</span>}
              {!isOpen && t.gross_pnl != null && <span>Lordo: {signed(t.gross_pnl)}$</span>}
              {!isOpen && t.fees != null && <span>Fee: -{Number(t.fees).toFixed(2)}$</span>}
              {(t.dca_count ?? 0) > 0 && <span style={{ color: '#fbbf24' }}>DCA×{t.dca_count}</span>}
              {isOpen && t.pnl_pct != null && <span style={{ color: pnlColor(t.pnl_pct) }}>{signed(t.pnl_pct)}% sul margine</span>}
            </div>
            {t.entry_reason && (
              <div style={{ fontSize: '11px', color: '#64748b', marginTop: '6px', fontStyle: 'italic' }}>
                “{String(t.entry_reason).slice(0, 140)}”
              </div>
            )}
            {t.open_ms && (
              <div style={{ fontSize: '10px', color: '#475569', marginTop: '4px' }}>
                {fmtDateTime(t.open_ms)}
                {t.close_ms ? ` → ${fmtDateTime(t.close_ms)} (${fmtDuration(t.close_ms - t.open_ms)})` : ` · aperto da ${fmtDuration(Date.now() - t.open_ms)}`}
              </div>
            )}
          </div>
        );
      })}

      <button onClick={() => load(portfolio)} disabled={loading} style={{
        width: '100%', padding: '12px', borderRadius: '10px', border: `1px solid ${BORDER}`,
        background: 'none', color: MUTED, fontWeight: 'bold',
        cursor: loading ? 'not-allowed' : 'pointer', marginTop: '4px'
      }}>
        {loading ? 'Aggiornamento...' : '🔄 Aggiorna'}
      </button>
    </div>
  );
}
