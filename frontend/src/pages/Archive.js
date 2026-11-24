import React from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  C, Card, EXIT_REASON, Grid, LineChart, LoadState, Note, Page, PageHeader, Pill, Section, SideTag, Stat,
  botMeta, duration, num, own, pct, price, sgn, tone, usd, usePoll, when,
} from '../paperApp/kit';

// Archivio: tutto cio' che NON e' la coppia PAPER attiva, in un solo posto e in sola lettura.
//  * Sessioni PAPER archiviate dal reset (/api/v3/paper-archive): run complete con journal intatto, mai mescolate.
//  * Brain RC1, Falco/Toro classici, Arena, Brain precedenti: le pagine esistenti, invariate.
//  * Niente link a /compare: legge le run ATTUALI (V3_COMPARE_RUNS), non le sessioni precedenti.
const LINKS = [
  ['🧠', 'Brain RC1', 'Run Brain Unico RC1 (in pausa): portafoglio, decisioni e trade.', '/brain-unico/rc1'],
  ['🦅', 'Falco e Toro classici', 'Portafogli classici: panoramica, posizioni e storico.', '/overview'],
  ['📊', 'Dashboard classica', 'La vecchia schermata dei portafogli classici.', '/classic'],
  ['💹', 'Trade classici', 'Storico dei trade di Falco, Toro e Brain classici.', '/archivio/classici/trade'],
  ['🏆', 'Performance classiche', 'Statistiche dei portafogli classici.', '/archivio/classici/performance'],
  ['🏟️', 'Arena', 'Gara fra modelli, sola lettura.', '/arena'],
  ['🗃️', 'Brain precedenti', 'Sessioni Brain V3 precedenti a RC1.', '/brain/archive'],
];

function ArchivedRun({ r }) {
  const m = botMeta(r.label === 'Falco Evoluto' ? 'falco_evoluto' : r.label === 'Brain Scalp' ? 'brain_scalp' : '');
  return <Link to={`/archivio/run/${encodeURIComponent(r.name)}`} style={{ textDecoration: 'none', color: 'inherit' }}>
    <Card accent={m.color} style={{ padding: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
        <strong style={{ fontSize: 16 }}>{m.icon} {r.label}</strong>
        <span style={{ fontSize: 17, fontWeight: 800, color: tone(r.net_pnl) }}>{sgn(r.net_pnl)}</span>
      </div>
      <div style={{ fontSize: 13, color: C.muted, margin: '4px 0 8px' }}>
        {when(r.started_at_ms)} → {when(r.archived_at_ms)} · run {r.run_id}</div>
      {r.available ? <Grid cols={3} gap={8}>
        <Stat compact label="Capitale" value={usd(r.initial_equity, 0)} />
        <Stat compact label="Equity finale" value={usd(r.settled_equity)} />
        <Stat compact label="Rendimento" value={pct(r.return_pct)} color={tone(r.return_pct)} />
        <Stat compact label="Trade" value={r.closed ?? '—'} />
        <Stat compact label="Vinti / persi" value={`${r.wins ?? 0} / ${r.losses ?? 0}`} />
        <Stat compact label="Costi AI" value={usd(r.ai_cost_total, 3)} />
      </Grid> : <Note>Journal non leggibile da qui.</Note>}
      <div style={{ fontSize: 13, color: '#c4b5fd', marginTop: 8 }}>Apri i trade e i risultati →</div>
    </Card>
  </Link>;
}

export function ArchiveContent({ data, error }) {
  const runs = data?.available ? data.runs || [] : [];
  return <Page>
    <PageHeader title="Archivio" subtitle="Run concluse e portafogli storici · sola lettura, separati dai bot attivi" />
    <Section title="Sessioni PAPER archiviate" hint="Run di Falco Evoluto e Brain Scalp chiuse e archiviate dal reset, con il loro journal integro.">
      <LoadState error={error} loading={!error && !data} what="Sessioni archiviate" />
      {data && !data.available && <Card><Note style={{ margin: 0 }}>L’archivio delle sessioni PAPER non è collegato a questa
        versione del server.</Note></Card>}
      {data?.available && runs.length === 0 && <Card><Note style={{ margin: 0 }}>Nessuna sessione archiviata.</Note></Card>}
      {data?.cumulative && data.cumulative.sessions > 0 && <Card style={{ padding: 14 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
          <strong style={{ fontSize: 16 }}>Σ Totale esperimenti archiviati</strong>
          <span style={{ fontSize: 17, fontWeight: 800, color: tone(data.cumulative.net_pnl) }}>{sgn(data.cumulative.net_pnl)}</span>
        </div>
        <Grid cols={3} gap={8}>
          <Stat compact label="Sessioni" value={data.cumulative.sessions} />
          <Stat compact label="Trade" value={data.cumulative.trades} />
          <Stat compact label="Vinti / persi" value={`${data.cumulative.wins} / ${data.cumulative.losses}`} />
          <Stat compact label="Commissioni" value={usd(data.cumulative.fees)} />
          <Stat compact label="Costi AI" value={usd(data.cumulative.ai_cost_total, 3)} />
        </Grid>
      </Card>}
      {runs.map(r => <ArchivedRun key={r.name} r={r} />)}
    </Section>
    <Section title="Portafogli e pagine storiche">
      <nav aria-label="Pagine storiche">
        {LINKS.map(([icon, title, desc, to]) => <Link key={to} to={to} style={{ textDecoration: 'none', color: 'inherit' }}>
          <Card style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 14, minHeight: 56 }}>
            <span aria-hidden="true" style={{ fontSize: 22 }}>{icon}</span>
            <span style={{ minWidth: 0 }}>
              <strong style={{ display: 'block', fontSize: 15 }}>{title}</strong>
              <span style={{ fontSize: 13, color: C.muted }}>{desc}</span>
            </span>
            <span aria-hidden="true" style={{ marginLeft: 'auto', color: C.muted, fontSize: 18 }}>›</span>
          </Card>
        </Link>)}
      </nav>
    </Section>
  </Page>;
}

export default function Archive() {
  const q = usePoll(['/api/v3/paper-archive'], 120000);
  return <ArchiveContent data={q.data ? q.data[0] : null} error={q.error && !q.data} />;
}

export function ArchivedRunContent({ data, error }) {
  const perf = data?.performance;
  const trades = data?.closed_trades || [];
  const curve = (perf?.curve_settled || []).map(p => ({ t: p.t, v: num(p.equity) })).filter(p => p.v !== null);
  const net = trades.reduce((s, t) => s + (num(t.realized_pnl) || 0), 0);
  return <Page>
    <PageHeader title={data ? `${data.label} · archiviata` : 'Sessione archiviata'}
      subtitle={data ? `Run ${data.run_id} · ${data.archive}` : null}>
      <div style={{ marginTop: 8 }}><Link to="/archivio" style={{ color: '#c4b5fd', fontSize: 14 }}>← Archivio</Link></div>
    </PageHeader>
    <LoadState error={error} loading={!error && !data} what="Sessione archiviata" />
    {data && <>
      <Card><Grid cols={3} gap={8}>
        <Stat compact label="Trade" value={trades.length} />
        <Stat label="Netto trading" value={sgn(net)} color={tone(net)} />
        <Stat label="Periodo" value={perf?.started_at_ms ? when(perf.started_at_ms) : '—'} />
      </Grid></Card>
      <Section title="Curva contabile"><Card><LineChart label="Equity contabile della sessione archiviata" series={[{ name: 'Equity', color: C.accent, points: curve }]}
        baseline={curve[0]?.v ?? null} /></Card></Section>
      <Section title={`Trade chiusi (${trades.length})`}>
        {trades.length === 0 && <Card><Note style={{ margin: 0 }}>Nessun trade chiuso in questa sessione.</Note></Card>}
        {trades.map(t => <Card key={t.position_id} style={{ padding: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <SideTag side={t.side} /><strong style={{ fontSize: 16 }}>{String(t.symbol || '?').replace('USDT', '')}</strong>
            <span style={{ color: C.soft, fontSize: 14 }}>{t.leverage ?? '—'}×</span>
            <span style={{ marginLeft: 'auto', fontSize: 17, fontWeight: 800, color: tone(t.realized_pnl) }}>{sgn(t.realized_pnl)}</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 14px', fontSize: 13, color: C.muted, marginTop: 6 }}>
            <span>{price(t.entry)} → {price(t.exit)}</span><span>commissioni {usd(t.fees)}</span>
            <span>{duration(t.hold_ms)}</span><span>{when(t.closed_at_ms)}</span>
          </div>
          <div style={{ marginTop: 6 }}><Pill color={C.soft}>{own(EXIT_REASON, t.exit_reason) || t.exit_reason || '—'}</Pill></div>
        </Card>)}
      </Section>
    </>}
  </Page>;
}

export function ArchivedRunPage() {
  const { key } = useParams();
  const q = usePoll([`/api/v3/paper-archive/${encodeURIComponent(key || '')}`], 300000);
  return <ArchivedRunContent data={q.data ? q.data[0] : null} error={q.error && !q.data} />;
}
