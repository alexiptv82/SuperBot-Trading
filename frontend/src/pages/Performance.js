import React, { useState, useEffect } from 'react';
import { botAPI } from '../api';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  Cell, CartesianGrid,
} from 'recharts';

const ACCENT = '#38bdf8';
const GOOD = '#4ade80';
const BAD = '#f87171';
const MUTED = '#94a3b8';
const SURFACE = '#1e293b';
const BORDER = '#334155';

const Card = ({ children, style }) => (
  <div style={{
    background: SURFACE, borderRadius: '16px', padding: '16px',
    border: `1px solid ${BORDER}`, ...style
  }}>{children}</div>
);

const ChartTooltip = ({ active, payload, label, formatter }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: '#0f172a', border: `1px solid ${BORDER}`, borderRadius: '8px',
      padding: '8px 10px', fontSize: '12px'
    }}>
      <div style={{ color: MUTED, marginBottom: '2px' }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color || '#f1f5f9', fontWeight: 'bold' }}>
          {formatter ? formatter(p.value) : p.value}
        </div>
      ))}
    </div>
  );
};

const fmtTime = (iso) => {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }) +
      ' ' + d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  } catch { return iso; }
};

export default function Performance() {
  const [perf, setPerf] = useState(null);

  useEffect(() => { botAPI.getPerformance().then(r => setPerf(r.data)).catch(console.error); }, []);

  const StatCard = ({ label, value, color }) => (
    <Card style={{ flex: '1 1 calc(50% - 8px)', textAlign: 'center', padding: '14px' }}>
      <div style={{ color: MUTED, fontSize: '12px', marginBottom: '6px' }}>{label}</div>
      <div style={{ fontSize: '22px', fontWeight: 'bold', color: color || '#f1f5f9' }}>{value}</div>
    </Card>
  );

  if (!perf || perf.total_trades === 0) {
    return (
      <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
        <h1 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '16px' }}>🏆 Performance</h1>
        <div style={{ textAlign: 'center', color: MUTED, padding: '40px' }}>
          Nessun dato ancora. Avvia il bot per vedere le statistiche.
        </div>
      </div>
    );
  }

  const winLossData = [
    { name: 'Vincenti', value: perf.winning_trades, color: GOOD },
    { name: 'Perdenti', value: perf.losing_trades, color: BAD },
  ];

  const equityData = (perf.equity_curve || []).map(p => ({
    time: fmtTime(p.time), equity: p.equity,
  }));

  const pnlBySymbol = Object.entries(perf.pnl_by_symbol || {})
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([symbol, pnl]) => ({ symbol: symbol.replace('USDT', ''), pnl }));

  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '16px' }}>🏆 Performance</h1>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
        <StatCard label="Trade Totali" value={perf.total_trades} />
        <StatCard label="Win Rate" value={`${perf.win_rate}%`} color={perf.win_rate >= 50 ? GOOD : BAD} />
        <StatCard label="P&L Totale" value={`${perf.total_pnl > 0 ? '+' : ''}${perf.total_pnl?.toFixed(2)}$`}
          color={perf.total_pnl > 0 ? GOOD : BAD} />
        <StatCard label="Media/Trade" value={`${perf.avg_pnl_per_trade > 0 ? '+' : ''}${perf.avg_pnl_per_trade?.toFixed(2)}$`}
          color={perf.avg_pnl_per_trade > 0 ? GOOD : BAD} />
        <StatCard label="Profit Factor" value={perf.profit_factor != null ? perf.profit_factor : 'N/A'}
          color={perf.profit_factor != null ? (perf.profit_factor >= 1 ? GOOD : BAD) : MUTED} />
      </div>

      {equityData.length > 1 && (
        <Card style={{ marginBottom: '16px' }}>
          <div style={{ fontSize: '14px', fontWeight: 'bold', marginBottom: '12px', color: '#f1f5f9' }}>
            📈 Curva del Capitale
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <AreaChart data={equityData} margin={{ top: 4, right: 8, bottom: 0, left: -24 }}>
              <defs>
                <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={ACCENT} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={BORDER} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="time" stroke={MUTED} fontSize={10} minTickGap={30} />
              <YAxis stroke={MUTED} fontSize={10} width={54} />
              <Tooltip content={<ChartTooltip formatter={(v) => `$${v?.toFixed(2)}`} />} />
              <Area type="monotone" dataKey="equity" stroke={ACCENT} strokeWidth={2}
                fill="url(#equityFill)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </Card>
      )}

      {pnlBySymbol.length > 0 && (
        <Card style={{ marginBottom: '16px' }}>
          <div style={{ fontSize: '14px', fontWeight: 'bold', marginBottom: '12px', color: '#f1f5f9' }}>
            💱 P&L per Asset
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={pnlBySymbol} margin={{ top: 4, right: 8, bottom: 0, left: -24 }}>
              <CartesianGrid stroke={BORDER} strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="symbol" stroke={MUTED} fontSize={11} />
              <YAxis stroke={MUTED} fontSize={10} width={54} />
              <Tooltip content={<ChartTooltip formatter={(v) => `${v > 0 ? '+' : ''}${v?.toFixed(2)}$`} />} />
              <Bar dataKey="pnl" radius={[6, 6, 6, 6]}>
                {pnlBySymbol.map((entry, i) => (
                  <Cell key={i} fill={entry.pnl >= 0 ? GOOD : BAD} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </Card>
      )}

      <Card>
        <div style={{ fontSize: '14px', fontWeight: 'bold', marginBottom: '12px', color: '#f1f5f9' }}>
          Vincenti vs Perdenti
        </div>
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={winLossData} margin={{ top: 4, right: 8, bottom: 0, left: -24 }}>
            <CartesianGrid stroke={BORDER} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" stroke={MUTED} fontSize={12} />
            <YAxis stroke={MUTED} fontSize={10} width={54} />
            <Tooltip content={<ChartTooltip />} />
            <Bar dataKey="value" radius={[6, 6, 6, 6]}>
              {winLossData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}
