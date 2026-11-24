import React, { useState } from 'react';
import { BrainCloseControls } from '../components/OverviewCloseControls';
import {
  BotSwitch, BOTS, C, Card, EXIT_REASON, Fresh, Grid, LEARNING, LoadState, Note, Page, PageHeader, Pill, Section,
  SideTag, STOP_KIND, Stat, ago, botMeta, duration, num, own, pct, price, sgn, tone, usd, usePoll, when,
} from '../paperApp/kit';

// Trade: SOLO le run attuali di Falco Evoluto e Brain Scalp (/api/v3/compare/<bot>/trades, journal della run).
// Aperti: lato, leva, margine, entrata, prezzo corrente (ticker), stop, take profit, P&L per posizione, chiusura
// manuale singola. Chiusi: entrata/uscita, P&L netto e lordo, commissioni, motivo di chiusura, durata, apprendimento
// associato alle chiusure manuali (esempio, mai regola di trading).
const NAMES = Object.keys(BOTS);
const SIDES = [['all', 'Tutti'], ['1', 'LONG'], ['-1', 'SHORT']];

function Chip({ on, children, onClick }) {
  return <button type="button" aria-pressed={on} onClick={onClick} style={{ minHeight: 40, padding: '6px 14px', borderRadius: 999,
    border: `1px solid ${on ? C.accent : C.line}`, background: on ? `${C.accent}26` : C.card, color: on ? C.text : C.soft,
    fontSize: 14, fontWeight: 700, cursor: 'pointer', font: 'inherit' }}>{children}</button>;
}

function OpenCard({ p, nowMs }) {
  const roi = num(p.roi_pct);
  return <div data-testid="trade-open">
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <SideTag side={p.side} />
      <strong style={{ fontSize: 17 }}>{String(p.symbol || '?').replace('USDT', '')}</strong>
      <span style={{ color: C.soft, fontSize: 14 }}>{p.leverage ?? '—'}×</span>
      <span style={{ marginLeft: 'auto', textAlign: 'right' }}>
        <span style={{ display: 'block', fontSize: 18, fontWeight: 800, color: tone(p.unrealized_pnl) }}>{sgn(p.unrealized_pnl)}</span>
        <span style={{ fontSize: 13, color: tone(roi) }}>{roi === null ? 'P&L non verificabile' : `${pct(roi)} sul margine`}</span>
      </span>
    </div>
    <Grid cols={3} gap={10}>
      <div style={{ marginTop: 10 }}><Stat compact label="Entrata" value={price(p.entry)} /></div>
      <div style={{ marginTop: 10 }}><Stat compact label="Prezzo ora" value={price(p.price)} /></div>
      <div style={{ marginTop: 10 }}><Stat compact label="Margine" value={usd(p.margin)} /></div>
      <Stat compact label="Stop iniziale" value={price(p.stop)} color={C.down} />
      <Stat compact label="Take profit" value={price(p.take_profit)} color={C.up} />
      <Stat compact label="Nozionale" value={usd(p.notional, 0)} />
    </Grid>
    <Note>Aperta {when(p.opened_at_ms)} ({ago(p.opened_at_ms, nowMs) || '—'}). P&L lordo al prezzo del ticker, commissioni escluse.</Note>
  </div>;
}

function ClosedCard({ t }) {
  const reason = own(EXIT_REASON, t.exit_reason) || t.exit_reason || '—';
  const kind = t.exit_reason === 'stop' && t.stop_kind && t.stop_kind !== 'initial' ? own(STOP_KIND, t.stop_kind) : null;
  const learning = own(LEARNING, t.manual_learning);
  return <Card data-testid="trade-closed" style={{ padding: 14 }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <SideTag side={t.side} />
      <strong style={{ fontSize: 17 }}>{String(t.symbol || '?').replace('USDT', '')}</strong>
      <span style={{ color: C.soft, fontSize: 14 }}>{t.leverage ?? '—'}×</span>
      <span style={{ marginLeft: 'auto', fontSize: 18, fontWeight: 800, color: tone(t.realized_pnl) }}>{sgn(t.realized_pnl)}</span>
    </div>
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', margin: '8px 0' }}>
      <Pill color={t.exit_reason === 'take_profit' ? C.up : t.exit_reason === 'manual' ? C.accent : t.exit_reason === 'stop' ? C.down : C.soft}>
        {reason}{kind ? ` · ${kind}` : ''}</Pill>
      {learning && <Pill color={C.info}>apprendimento: {learning}</Pill>}
    </div>
    <Grid cols={3} gap={10}>
      <Stat compact label="Entrata" value={price(t.entry)} />
      <Stat compact label="Uscita" value={price(t.exit)} />
      <Stat compact label="Margine" value={usd(t.margin)} />
      <Stat compact label="Stop" value={price(t.stop)} color={C.down} />
      <Stat compact label="Take profit" value={price(t.take_profit)} color={C.up} />
      <Stat compact label="Durata" value={duration(t.hold_ms)} />
      <Stat compact label="P&L lordo" value={sgn(t.gross_pnl)} color={tone(t.gross_pnl)} />
      <Stat compact label="Commissioni" value={usd(t.fees)} color={C.soft} />
      <Stat compact label="Chiusa" value={when(t.closed_at_ms)} />
    </Grid>
  </Card>;
}

export function TradesContent({ name, data, error, nowMs = Date.now(), onSelect, onRefresh = () => {}, compareRun = null }) {
  const [view, setView] = useState('open');
  const [side, setSide] = useState('all');
  const m = botMeta(name);
  const open = (data?.open_positions || []).filter(p => side === 'all' || String(p.side) === side);
  const closed = (data?.closed_trades || []).filter(t => side === 'all' || String(t.side) === side);
  const fees = (data?.closed_trades || []).reduce((s, t) => s + (num(t.fees) || 0), 0);
  return <Page>
    <PageHeader title="Trade" subtitle="Solo le run attuali, dalla nuova ripartenza" />
    <BotSwitch runs={NAMES.map(n => ({ name: n, label: BOTS[n].label }))} selected={name} onSelect={onSelect} />
    <LoadState error={error} loading={!error && !data} what={`Trade di ${m.label}`} />
    {data && <>
      <Card accent={m.color}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center', marginBottom: 10 }}>
          <strong style={{ fontSize: 16 }}>{m.icon} {m.label}</strong><Fresh live atMs={data.generated_at_ms} nowMs={nowMs} />
        </div>
        <Grid cols={2} gap={10}>
          <Stat label="Aperti" value={(data.open_positions || []).length} color={C.info} />
          <Stat label="Chiusi" value={data.total_closed ?? '—'} />
          <Stat label="Vinti / persi" value={`${data.win_count ?? 0} / ${data.loss_count ?? 0}`} />
          <Stat compact label="Commissioni" value={usd(fees)} color={C.soft} />
        </Grid>
        <Note>Take profit a {data.take_profit_r ?? '—'} R dalla politica d’uscita della run; commissioni {data.fee_bps ?? '—'} bp per lato.</Note>
      </Card>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '6px 0 4px' }}>
        <Chip on={view === 'open'} onClick={() => setView('open')}>Aperti ({(data.open_positions || []).length})</Chip>
        <Chip on={view === 'closed'} onClick={() => setView('closed')}>Chiusi ({data.total_closed ?? 0})</Chip>
      </div>
      <div role="group" aria-label="Filtro lato" style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '6px 0 8px' }}>
        {SIDES.map(([k, l]) => <Chip key={k} on={side === k} onClick={() => setSide(k)}>{l}</Chip>)}
      </div>
      {view === 'open' ? <Section title="Posizioni aperte" hint="Prezzo e P&L aggiornati dal ticker a ogni lettura (ogni 30 secondi).">
        {open.length === 0 && <Card style={{ textAlign: 'center', color: C.muted, fontSize: 14 }}>Nessuna posizione aperta</Card>}
        <BrainCloseControls positions={open} allowCloseAll={false} readOnly={compareRun?.manual_close_allowed !== true}
          serverPending={data.close_pending === true || compareRun?.close_pending === true} onRefresh={onRefresh}
          closeUrl={`/api/v3/compare/${name}/close`} resultUrl={`/api/v3/compare/${name}/close-result`}
          itemStyle={{ background: C.card, borderRadius: 18, padding: 14, border: `1px solid ${C.line}`, marginBottom: 10 }}
          closeLabel={p => `Chiudi ${p.symbol} (PAPER)`} renderPosition={p => <OpenCard p={p} nowMs={nowMs} />} />
        {compareRun && compareRun.manual_close_allowed !== true && open.length > 0 && <Note>Chiusura manuale non
          disponibile finché il servizio uscite di questo bot non è sano.</Note>}
      </Section> : <Section title="Trade chiusi" hint="Dal più recente. P&L netto = lordo − commissioni; i costi AI sono in Performance.">
        {closed.length === 0 && <Card style={{ textAlign: 'center', color: C.muted, fontSize: 14 }}>Nessun trade chiuso</Card>}
        {closed.map(t => <ClosedCard key={t.position_id} t={t} />)}
        {data.has_more && <Note>Sono mostrati i {(data.closed_trades || []).length} trade più recenti.</Note>}
      </Section>}
      <Note>Le chiusure manuali restano esempi per l’apprendimento (profitto protetto o perdita ridotta), mai una regola di
        trading. I trade delle run precedenti sono nell’Archivio.</Note>
    </>}
  </Page>;
}

export default function PaperTrades() {
  const [name, setName] = useState(NAMES[0]);
  const tr = usePoll([`/api/v3/compare/${name}/trades?limit=300`]);
  const cmp = usePoll(['/api/v3/compare']);
  const data = tr.data && tr.data[0] && tr.data[0].name === name ? tr.data[0] : null;
  const run = (cmp.data?.[0]?.runs || []).find(r => r.name === name) || null;
  return <TradesContent name={name} data={data} error={tr.error && !data} onSelect={setName}
    onRefresh={() => { tr.refresh(); cmp.refresh(); }} compareRun={run} />;
}
