import React, { useEffect, useState } from 'react';
import API from '../api';
import { ARENA_PROFILES, money, preparedAwaitingT0, sanitizedTrial } from '../brainArenaModel';

// Storico dell'Arena (DeepSeek, Qwen, MiniMax) in SOLA LETTURA: nessuna chiusura, nessun comando.
// Dati da GET /api/v3/arena (codice di lettura del ramo Arena); il modello scarta tutto cio' che non e' verificato.
const BLOCK = { background: '#172338', border: '1px solid #2f425b', borderRadius: 16, padding: 16, marginBottom: 12 };
const MUTED = { color: '#a8bacd', fontSize: 12 };
const ROW = { display: 'flex', justifyContent: 'space-between', gap: 12, padding: '4px 0', fontSize: 13 };
const STATE = { running: 'In funzione', paused: 'In pausa', halted: 'Fermo', stale: 'Segnale assente' };
const Row = ({ label, children }) => <div style={ROW}><span style={MUTED}>{label}</span><span>{children}</span></div>;
const pct = v => (v === null || v === undefined ? '—' : `${v}%`);

export function ArenaStoricoContent({ data }) {
  const portfolios = data?.portfolios || {};
  return <main style={{ background: '#0b1323', color: '#eef5ff', minHeight: '100vh', padding: '16px 12px 92px', maxWidth: 900, margin: '0 auto', boxSizing: 'border-box', fontFamily: 'system-ui, sans-serif' }}>
    <div style={{ color: '#7dd3fc', fontSize: 11, fontWeight: 800, letterSpacing: 2 }}>STORICO · ARENA · PAPER</div>
    <h1 style={{ fontSize: 23, margin: '6px 0 4px' }}>Arena AI</h1>
    <p style={MUTED}>Consultazione in sola lettura dei tre conti dell’Arena. Nessuna chiusura né comando da questa schermata.</p>
    {ARENA_PROFILES.map(p => {
      const raw = portfolios[p.id];
      const t = sanitizedTrial(p.id, raw);
      return <section key={p.id} style={BLOCK} aria-label={`Arena ${p.title}`}>
        <h2 style={{ fontSize: 17, margin: '0 0 6px' }}>{p.title} <span style={MUTED}>· {p.kind}</span></h2>
        {!t ? <p style={MUTED}>{preparedAwaitingT0(p.id, raw) ? 'Run preparata, in attesa dell’avvio.' : 'Dati non disponibili o non verificati.'}</p> : <>
          <Row label="Stato">{STATE[t.state] || '—'}</Row>
          <Row label="Equity">{money(t.equity)}</Row>
          <Row label="P&L realizzato">{money(t.realized_pnl)}</Row>
          <Row label="Trade chiusi · win rate">{t.total_closed ?? '—'} · {pct(t.win_rate)}</Row>
          <Row label="Posizioni aperte">{t.open_count ?? '—'}</Row>
          <Row label="Decisioni · nessun trade">{t.decision_count ?? '—'} · {t.no_trade_count ?? '—'}</Row>
          <Row label="Chiusure manuali">{t.manual_close_count ?? '—'}</Row>
          <p style={MUTED}>Apprendimento: {t.learning_status === 'JOURNAL_EVIDENCE_ONLY_NOT_MODEL_TRAINING' ? 'solo evidenze nel registro, nessun modello addestrato' : 'non verificato'}.</p>
        </>}
      </section>;
    })}
    <a href="/brain-unico" style={{ color: '#7dd3fc', fontSize: 13 }}>Torna al Brain</a>
  </main>;
}

export default function ArenaStorico() {
  const [data, setData] = useState(undefined);
  useEffect(() => {
    const controller = new AbortController();
    API.get('/api/v3/arena', { signal: controller.signal })
      .then(r => setData(r.data)).catch(() => { if (!controller.signal.aborted) setData(null); });
    return () => controller.abort();
  }, []);
  if (data === undefined) return <div role="status" style={{ padding: 22 }}>Caricamento dello storico Arena…</div>;
  if (data === null) return <div role="status" style={{ padding: 22 }}>Storico Arena non disponibile su questo server.</div>;
  return <ArenaStoricoContent data={data} />;
}
