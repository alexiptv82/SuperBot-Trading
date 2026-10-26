import React, { useEffect, useState } from 'react';
import { brainAPI } from '../api';

// Same card, typography and palette as Dashboard. Observation only.
const Card = ({ title, children }) => (
  <section style={{ background: '#1e293b', borderRadius: '16px', padding: '16px', border: '1px solid #334155' }}>
    <h2 style={{ fontSize: '16px', fontWeight: 'bold', margin: '0 0 12px' }}>
      <span style={{ color: '#38bdf8' }}>🧠 Brain</span> · {title}
    </h2>
    {children}
  </section>
);
const fmt = (value, digits = 2) => Number.isFinite(value) ? value.toFixed(digits) : '—';
const money = value => Number.isFinite(value) ? `$${fmt(value)}` : '—';
const date = ms => Number.isFinite(ms) ? new Date(ms).toLocaleString('it-IT') : 'Non disponibile';
const color = value => Number.isFinite(value) ? (value < 0 ? '#f87171' : '#4ade80') : '#94a3b8';
const noteStyle = { color: '#94a3b8', fontSize: '12px', lineHeight: 1.5 };
const Row = ({ label, children }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', padding: '5px 0', fontSize: '13px' }}>
    <span style={{ color: '#94a3b8' }}>{label}</span><span>{children}</span>
  </div>
);

// Exported for offline server-render tests; React escapes all model text.
export function BrainCards({ data }) {
  const portfolio = data?.portfolio || {};
  const stats = data?.stats || {};
  const daily = data?.daily_stop || {};
  const reasoning = data?.reasoning || {};
  const system = data?.system || {};
  const positions = data?.positions || [];
  const trades = data?.trades || [];
  const available = data?.status === 'ok';
  return (
    <div style={{ display: 'grid', gap: '12px' }}>
      <Card title="Portafoglio">
        <Row label="Equity attuale">{money(portfolio.equity)}</Row>
        <Row label="Cash disponibile">{money(portfolio.cash)}</Row>
        <Row label="P&L da $1000 PAPER"><span style={{ color: color(portfolio.pnl) }}>{money(portfolio.pnl)} · {fmt(portfolio.pnl_pct)}%</span></Row>
        <Row label="Cicli completati">{portfolio.cycles ?? '—'}</Row>
        <p style={noteStyle}>Valutazione alle {date(portfolio.valued_ms)}. {portfolio.stale ? 'Dati non aggiornati.' : 'Prezzi dell’ultimo ciclo, aggiornati ogni 15 minuti.'}</p>
      </Card>
      <Card title="Posizioni aperte">
        {positions.map(position => (
          <div key={position.symbol} style={{ borderBottom: '1px solid #334155', padding: '8px 0' }}>
            <Row label={position.symbol}><strong style={{ color: position.side === 'LONG' ? '#4ade80' : '#f87171' }}>{position.side}</strong></Row>
            <Row label="Entry">{fmt(position.entry, 6)}</Row>
            <Row label="P&L floating"><span style={{ color: color(position.floating_pnl) }}>{money(position.floating_pnl)}</span></Row>
          </div>
        ))}
        {!positions.length && <p style={noteStyle}>{available ? 'Nessuna posizione aperta' : 'Posizioni non disponibili'}</p>}
        <p style={noteStyle}>Floating lordo ai prezzi dell’ultimo ciclo; commissioni di uscita e funding futuri esclusi.</p>
      </Card>
      <Card title="Ultimi trade chiusi">
        {trades.map((trade, index) => (
          <div key={`${trade.symbol}-${trade.closed_ms}-${index}`} style={{ borderBottom: '1px solid #334155', padding: '8px 0' }}>
            <Row label={`${trade.symbol} · ${trade.side}`}><span style={{ color: color(trade.pnl) }}>{money(trade.pnl)}</span></Row>
            <div style={noteStyle}>{trade.reason || 'Motivo non disponibile'}{trade.partial ? ' · Chiusura parziale' : ''} · {date(trade.closed_ms)}</div>
          </div>
        ))}
        {!trades.length && <p style={noteStyle}>{available ? 'Nessun trade chiuso disponibile' : 'Storico non disponibile'}</p>}
        <p style={noteStyle}>Ultimi 20 realizzi esportati, incluse le chiusure parziali.</p>
      </Card>
      <Card title="Statistiche">
        <Row label="Trade interamente chiusi">{stats.closed_trades ?? '—'}</Row>
        <Row label="Win rate">{fmt(stats.win_rate_pct)}%</Row>
        <Row label="P&L medio per trade">{money(stats.average_pnl)}</Row>
        <Row label="Daily stop · limite 20%">{daily.stopped === true ? 'Raggiunto · protezioni attive' : daily.stopped === false ? 'Non raggiunto' : 'Non disponibile'}</Row>
        <Row label="Perdita equity oggi">{fmt(daily.drawdown_pct)}%</Row>
        <Row label="Quota del limite usata">{fmt(daily.used_limit_pct)}%</Row>
        <p style={noteStyle}>Giorno UTC: {daily.day || '—'}. {daily.state === 'awaiting_utc_rollover' ? 'In attesa del rollover del pilot.' : ''} Le statistiche aggregano i parziali per posizione e includono l’intero storico SQLite.</p>
      </Card>
      <Card title="Ultimo reasoning DeepSeek">
        <Row label="Ultima chiamata tentata">{date(reasoning.last_call_ms)}</Row>
        <Row label="Tesi conservata">{reasoning.symbol || '—'} · {date(reasoning.decision_ms)}</Row>
        {[
          ['Tesi bull', reasoning.bull_scenario], ['Tesi bear', reasoning.bear_scenario],
          ['Verdetto finale', reasoning.verdict], ['Vista mercato', reasoning.market_view],
        ].map(([label, value]) => (
          <div key={label} style={{ marginTop: '10px', overflowWrap: 'anywhere' }}>
            <strong style={{ fontSize: '13px' }}>{label}</strong>
            <p style={{ ...noteStyle, whiteSpace: 'pre-wrap', margin: '4px 0' }}>{value || 'Non disponibile'}</p>
          </div>
        ))}
        <p style={noteStyle}>{reasoning.note}</p>
      </Card>
      <Card title="Stato sistema">
        <Row label="Container">{system.container || 'superbot-brain-pilot'}</Row>
        <Row label="Salute Docker">{system.health || 'unknown'}</Row>
        <Row label="SHA in esecuzione">{system.sha || 'Non disponibile'}</Row>
        <Row label="Uptime">{system.uptime_seconds == null ? 'Non disponibile' : `${fmt(system.uptime_seconds / 3600, 1)} h`}</Row>
        <Row label="Heartbeat">{system.heartbeat || 'unknown'}</Row>
        <Row label="Ultimo heartbeat">{date(system.heartbeat_ms)}</Row>
        <p style={noteStyle}>{system.note}</p>
      </Card>
    </div>
  );
}

export default function BrainDashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    const poll = async () => {
      try {
        const response = await brainAPI.getStatus(controller.signal);
        if (!controller.signal.aborted) setData(response.data);
      } catch (_) {
        if (!controller.signal.aborted) setData({ status: 'unavailable' });
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
          timer = setTimeout(poll, 30000);
        }
      }
    };
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);
  return (
    <main style={{ padding: '16px', maxWidth: '600px', margin: '0 auto', color: '#f1f5f9' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '4px' }}>🧠 Brain · PAPER</h1>
      <p style={noteStyle}>Portafoglio virtuale · sola osservazione · aggiornamento automatico</p>
      <div role="status" aria-live="polite" style={{ ...noteStyle, marginBottom: '12px' }}>
        {loading ? 'Caricamento…' : data?.status !== 'ok' ? 'Brain non disponibile. Nuovo controllo automatico tra 30 secondi.' : 'Dati PAPER · nessun controllo operativo'}
      </div>
      <BrainCards data={data?.status === 'ok' ? data : null} />
    </main>
  );
}
