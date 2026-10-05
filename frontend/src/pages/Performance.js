import React, { useState, useEffect } from 'react';
import { botAPI } from '../api';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
export default function Performance() {
  const [perf, setPerf] = useState(null);
  useEffect(() => { botAPI.getPerformance().then(r => setPerf(r.data)).catch(console.error); }, []);
  const data = perf ? [
    { name: 'Vincenti', value: perf.winning_trades, color: '#4ade80' },
    { name: 'Perdenti', value: perf.losing_trades, color: '#f87171' },
  ] : [];
  const StatCard = ({ label, value, color }) => (
    <div style={{
      background: '#1e293b', borderRadius: '12px', padding: '16px',
      border: '1px solid #334155', textAlign: 'center', flex: '1 1 calc(50% - 8px)'
    }}>
      <div style={{ color: '#94a3b8', fontSize: '12px', marginBottom: '6px' }}>{label}</div>
      <div style={{ fontSize: '22px', fontWeight: 'bold', color: color || '#f1f5f9' }}>{value}</div>
    </div>
  );
  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '16px' }}>🏆 Performance</h1>
      {!perf || perf.total_trades === 0 ? (
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: '40px' }}>
          Nessun dato ancora. Avvia il bot per vedere le statistiche.
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '16px' }}>
            <StatCard label="Trade Totali" value={perf.total_trades} />
            <StatCard label="Win Rate" value={`${perf.win_rate}%`} color={perf.win_rate >= 50 ? '#4ade80' : '#f87171'} />
            <StatCard label="P&L Totale" value={`${perf.total_pnl > 0 ? '+' : ''}${perf.total_pnl?.toFixed(2)}$`}
              color={perf.total_pnl > 0 ? '#4ade80' : '#f87171'} />
            <StatCard label="Media/Trade" value={`${perf.avg_pnl_per_trade > 0 ? '+' : ''}${perf.avg_pnl_per_trade?.toFixed(2)}$`}
              color={perf.avg_pnl_per_trade > 0 ? '#4ade80' : '#f87171'} />
          </div>
          <div style={{ background: '#1e293b', borderRadius: '12px', padding: '16px', border: '1px solid #334155' }}>
            <div style={{ fontSize: '14px', fontWeight: 'bold', marginBottom: '12px' }}>Vincenti vs Perdenti</div>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={data}>
                <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} />
                <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155' }} />
                <Bar dataKey="value" radius={[6,6,0,0]}>
                  {data.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
