import React, { useState } from 'react';
import {
  BotSwitch, BOTS, C, Card, Fold, Grid, LineChart, LoadState, Note, Page, PageHeader, Pill, Section, Stat,
  botMeta, day, duration, num, pct, reasonText, riskText, sgn, tone, usd, usePoll, when,
} from '../paperApp/kit';

// Performance: valutazione del test PAPER dalla nuova ripartenza. Solo run attive (mai le archiviate).
// Fonti: /api/v3/compare (metriche per run) e /api/v3/compare/<bot>/performance (giorni, curve, statistiche, motivi).
const NAMES = Object.keys(BOTS);
const DAY_MS = 86_400_000;

const rate = r => (num(r?.win_rate) === null ? '—' : `${String(r.win_rate).replace('.', ',')}%`);
const ddPct = p => (num(p) === null ? '—' : num(p) === 0 ? '0,00%' : `−${Math.abs(num(p)).toFixed(2).replace('.', ',')}%`);
const dd = (p, v) => (num(p) === null ? '—' : `${ddPct(p)} (${usd(v)})`);

export const ROWS = [
  ['Capitale iniziale', r => usd(r.initial_equity, 0)],
  ['Equity contabile', r => usd(r.settled_equity)],
  ['P&L netto trading', r => <span style={{ color: tone(r.net_pnl) }}>{sgn(r.net_pnl)}</span>],
  ['Rendimento', r => <strong style={{ color: tone(r.return_pct) }}>{pct(r.return_pct)}</strong>],
  ['Commissioni', r => usd(r.fees)],
  ['Costi AI', r => usd(r.ai_cost_total, 3)],
  ['Netto dopo AI', r => <strong style={{ color: tone(r.net_after_ai) }}>{sgn(r.net_after_ai)}</strong>],
  ['Rendimento dopo AI', r => <span style={{ color: tone(r.return_after_ai_pct) }}>{pct(r.return_after_ai_pct)}</span>],
  ['Trade chiusi', r => r.closed ?? '—'],
  ['Vinti / persi', r => `${r.wins ?? 0} / ${r.losses ?? 0}`],
  ['Win rate', r => rate(r)],
  ['Profit factor', r => (r.profit_factor ?? '—').toString().replace('.', ',')],
  ['Drawdown max (chiusi)', r => dd(r.max_drawdown_pct, r.max_drawdown)],
  ['Drawdown max (a mercato)', r => (num(r.mtm_drawdown_pct) === null ? 'non disponibile' : dd(r.mtm_drawdown_pct, r.mtm_drawdown))],
  ['LONG', r => side(r.by_side?.long)],
  ['SHORT', r => side(r.by_side?.short)],
];

function side(b) {
  if (!b) return '—';
  return <span>{b.trades} trade · <span style={{ color: tone(b.net_pnl), whiteSpace: 'nowrap' }}>{sgn(b.net_pnl)}</span>
    <span style={{ color: C.muted }}> · {b.wins}V/{b.losses}P</span></span>;
}

function period(perf, nowMs) {
  const s = perf?.started_at_ms;
  if (!Number.isSafeInteger(s)) return '—';
  const days = Math.max(0, (nowMs - s) / DAY_MS);
  return `dal ${when(s)} · ${days < 1 ? `${Math.round(days * 24)} ore` : `${days.toFixed(1).replace('.', ',')} giorni`}`;
}

// curva contabile: l'equity resta quella dell'ultima chiusura fino ad adesso (la linea arriva a "ora")
const extend = (pts, nowMs) => (pts.length && nowMs > pts[pts.length - 1].t ? [...pts, { t: nowMs, v: pts[pts.length - 1].v }] : pts);
// curva in % sul capitale: confrontabile fra 1.000 e 2.000
const pctCurve = (points, initial) => (points || []).map(p => ({ t: p.t, v: (num(p.equity) / initial - 1) * 100 }))
  .filter(p => Number.isFinite(p.v) && Number.isSafeInteger(p.t));

function CompareView({ runs, perfs, nowMs }) {
  const [basis, setBasis] = useState('settled');
  const series = runs.map(r => ({ name: r.label, color: botMeta(r.name).color,
    points: basis === 'settled' ? extend(pctCurve(perfs[r.name]?.curve_settled, num(r.initial_equity)), nowMs)
      : pctCurve(perfs[r.name]?.curve_market, num(r.initial_equity)) }));
  return <>
    <Card>
      <div style={{ fontSize: 13, color: C.muted, marginBottom: 8 }}>Periodo di test (dalla nuova ripartenza)</div>
      {runs.map(r => <div key={r.name} style={{ fontSize: 14, margin: '4px 0' }}>
        <strong style={{ color: botMeta(r.name).color }}>{r.label}</strong> <span style={{ color: C.soft }}>{period(perfs[r.name], nowMs)}</span></div>)}
    </Card>
    <Section title="Confronto diretto">
      <Card style={{ padding: 0, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14, tableLayout: 'fixed' }}>
          <thead><tr style={{ background: C.card2 }}>
            <th scope="col" style={{ textAlign: 'left', padding: '10px 10px', color: C.muted, fontWeight: 600, width: '36%' }}>Metrica</th>
            {runs.map(r => <th key={r.name} scope="col" style={{ textAlign: 'right', padding: '10px 10px', color: botMeta(r.name).color }}>
              {botMeta(r.name).short}</th>)}
          </tr></thead>
          <tbody>{ROWS.map(([label, f]) => <tr key={label} style={{ borderTop: `1px solid ${C.line}` }}>
            <th scope="row" style={{ textAlign: 'left', padding: '9px 10px', color: C.soft, fontWeight: 500 }}>{label}</th>
            {runs.map(r => <td key={r.name} style={{ textAlign: 'right', padding: '9px 10px', fontVariantNumeric: 'tabular-nums',
              overflowWrap: 'anywhere' }}>{r.available ? f(r) : '—'}</td>)}
          </tr>)}</tbody>
        </table>
      </Card>
      <Note>Drawdown “chiusi” sulla curva contabile (a ogni chiusura); “a mercato” dai campioni del Guardian a ogni giro.</Note>
    </Section>
    <Section title="Rendimento nel tempo" hint="In percentuale sul capitale, per confrontare 1.000 e 2.000 USDT.">
      <div role="group" aria-label="Base della curva" style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        {[['settled', 'Contabile (trade chiusi)'], ['market', 'A mercato (ultimo giro)']].map(([k, l]) =>
          <button key={k} type="button" aria-pressed={basis === k} onClick={() => setBasis(k)} style={{ minHeight: 40, padding: '6px 12px',
            borderRadius: 999, border: `1px solid ${basis === k ? C.accent : C.line}`, background: basis === k ? `${C.accent}26` : C.card,
            color: C.text, fontSize: 13, fontWeight: 700, cursor: 'pointer', font: 'inherit' }}>{l}</button>)}
      </div>
      <Card><LineChart label="Rendimento percentuale dei due bot" series={series} baseline={0} format={v => pct(v)} /></Card>
    </Section>
  </>;
}

function Bars({ title, counts, labeler, total }) {
  const items = Object.entries(counts || {}).sort((a, b) => b[1] - a[1]);
  if (!items.length) return null;
  return <div style={{ marginBottom: 14 }}>
    <div style={{ fontSize: 14, fontWeight: 700, color: C.soft, marginBottom: 6 }}>{title}</div>
    {items.map(([k, n]) => <div key={k} style={{ margin: '6px 0' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 14 }}>
        <span style={{ color: C.text }}>{labeler(k)}</span>
        <span style={{ color: C.muted, whiteSpace: 'nowrap' }}>{n} · {total ? Math.round(n / total * 100) : 0}%</span>
      </div>
      <div style={{ height: 6, background: C.card2, borderRadius: 3, marginTop: 3 }}>
        <div style={{ height: 6, width: `${total ? Math.max(2, n / total * 100) : 0}%`, background: C.accent, borderRadius: 3 }} />
      </div>
    </div>)}
  </div>;
}

function SingleView({ run, perf, nowMs }) {
  const m = botMeta(run.name);
  const initial = num(run.initial_equity);
  const st = perf?.stats || {};
  const series = [
    { name: 'Contabile (chiusi)', color: m.color, points: extend((perf?.curve_settled || []).map(p => ({ t: p.t, v: num(p.equity) })).filter(p => p.v !== null), nowMs) },
    { name: 'A mercato (ultimo giro)', color: '#94a3b8', points: (perf?.curve_market || []).map(p => ({ t: p.t, v: num(p.equity) })).filter(p => p.v !== null) },
  ];
  const daily = [...(perf?.daily || [])].reverse();
  const dec = perf?.decisions;
  return <>
    <Card accent={m.color}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
        <strong style={{ fontSize: 17 }}>{m.icon} {run.label}</strong><Pill color={m.color}>{period(perf, nowMs)}</Pill></div>
      <div style={{ marginTop: 12 }}><Grid cols={2}>
        <Stat label="Capitale iniziale" value={usd(run.initial_equity, 0)} />
        <Stat label="Equity contabile" value={usd(run.settled_equity)} />
        <Stat label="P&L netto trading" value={sgn(run.net_pnl)} color={tone(run.net_pnl)} sub={pct(run.return_pct)} />
        <Stat label="Netto dopo costi AI" value={sgn(run.net_after_ai)} color={tone(run.net_after_ai)} sub={pct(run.return_after_ai_pct)} />
        <Stat label="Commissioni" value={usd(run.fees)} color={C.soft} />
        <Stat label="Costi AI" value={usd(run.ai_cost_total, 3)} color={C.soft} />
      </Grid></div>
    </Card>
    <Card>
      <Grid cols={3} gap={10}>
        <Stat label="Trade" value={run.closed ?? '—'} />
        <Stat label="Vinti" value={run.wins ?? 0} color={C.up} />
        <Stat label="Persi" value={run.losses ?? 0} color={C.down} />
        <Stat label="Win rate" value={rate(run)} />
        <Stat label="Profit factor" value={(run.profit_factor ?? '—').toString().replace('.', ',')} />
        <Stat label="Payoff" value={(st.payoff ?? '—').toString().replace('.', ',')} sub="media vinti / media persi" />
        <Stat label="DD max chiusi" value={ddPct(run.max_drawdown_pct)} color={C.warn} />
        <Stat label="DD a mercato" value={ddPct(run.mtm_drawdown_pct)} color={C.warn} />
        <Stat label="Durata media" value={duration(st.avg_hold_ms)} />
      </Grid>
    </Card>
    <Section title="Curva dell’equity" hint="Contabile a ogni chiusura; a mercato dai campioni del Guardian a ogni giro.">
      <Card><LineChart label={`Equity ${run.label}`} series={series} baseline={initial} /></Card>
    </Section>
    <Section title="LONG e SHORT">
      <Grid cols={2} gap={10}>{['long', 'short'].map(k => { const b = run.by_side?.[k] || {}; return <Card key={k} style={{ marginBottom: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 800, color: k === 'long' ? C.up : C.down, marginBottom: 6 }}>{k.toUpperCase()}</div>
        <Stat label="Netto" value={sgn(b.net_pnl)} color={tone(b.net_pnl)} />
        <Note style={{ margin: '6px 0 0' }}>{b.trades ?? 0} trade · {b.wins ?? 0} vinti · {b.losses ?? 0} persi
          {b.trades ? ` · win rate ${Math.round((b.wins || 0) / Math.max(1, (b.wins || 0) + (b.losses || 0)) * 100)}%` : ''}</Note>
      </Card>; })}</Grid>
      <Card style={{ marginTop: 12 }}><Grid cols={2}>
        <Stat label="Vincita media" value={sgn(st.avg_win)} color={C.up} />
        <Stat label="Perdita media" value={sgn(st.avg_loss)} color={C.down} />
        <Stat label="Trade migliore" value={sgn(st.best)} color={tone(st.best)} />
        <Stat label="Trade peggiore" value={sgn(st.worst)} color={tone(st.worst)} />
      </Grid></Card>
    </Section>
    <Section title="Risultati giornalieri" hint={`Giorni di calendario (${perf?.day_tz === 'UTC' ? 'UTC' : 'ora italiana'}), dal più recente.`}>
      {daily.length === 0 && <Card style={{ color: C.muted, fontSize: 14 }}>Nessun giorno registrato.</Card>}
      {daily.map(d => <Card key={d.date} style={{ padding: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
          <strong style={{ fontSize: 15 }}>{day(d.date)}</strong>
          <span style={{ fontSize: 17, fontWeight: 800, color: tone(d.net) }}>{sgn(d.net)}</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '2px 14px', fontSize: 13, color: C.muted, marginTop: 4 }}>
          <span>{d.trades} trade ({d.wins}V/{d.losses}P)</span>
          <span>commissioni {usd(d.fees)}</span>
          <span>AI {usd(d.ai_cost, 3)}</span>
          <span>dopo AI <strong style={{ color: tone(d.net_after_ai) }}>{sgn(d.net_after_ai)}</strong></span>
          <span>equity a fine giorno {usd(d.equity_end)}</span>
        </div>
      </Card>)}
    </Section>
    <Section title="Perché apre o non apre" hint="Tutte le decisioni della run, dal journal: filtri della strategia (regime, punteggio, AI) e limiti di rischio.">
      <Card>
        {!dec || !dec.total ? <Note>Nessuna decisione registrata.</Note> : <>
          <div style={{ fontSize: 14, color: C.soft, marginBottom: 10 }}>{dec.total} decisioni · prima {when(perf.first_decision_ms)}</div>
          <Bars title="Motivo della decisione" counts={dec.by_reason} total={dec.total} labeler={k => (k === '—' ? 'motivo non registrato' : reasonText(k))} />
          <Bars title="Limite di rischio che ha fermato l’apertura" counts={dec.by_risk_reason}
            total={Object.values(dec.by_risk_reason || {}).reduce((a, b) => a + b, 0)} labeler={riskText} />
          <Bars title="Regime di mercato al momento della decisione" counts={dec.by_regime} total={dec.total} labeler={k => k} />
        </>}
      </Card>
      {dec && dec.last && dec.last.length > 0 && <Fold title={`Ultime ${dec.last.length} decisioni`}>
        {dec.last.map((d, i) => <div key={`${d.ts_ms}-${i}`} style={{ padding: '7px 0', borderBottom: `1px solid ${C.line}`, fontSize: 14 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <strong>{String(d.symbol || '—').replace('USDT', '')} <span style={{ color: C.muted, fontWeight: 500 }}>{d.regime || ''}</span></strong>
            <span style={{ color: C.muted, fontSize: 13 }}>{when(d.ts_ms)}</span></div>
          <div style={{ color: d.kind === 'OPEN' && d.status !== 'RISK_REJECTED' ? C.up : C.soft }}>{reasonText(d.rationale)}
            {d.risk_reason ? <span style={{ color: C.warn }}> · {riskText(d.risk_reason)}</span> : null}</div>
        </div>)}
      </Fold>}
    </Section>
  </>;
}

export function PerformanceContent({ cmp, perfs, error, nowMs = Date.now(), selected, onSelect }) {
  const runs = cmp?.available ? cmp.runs || [] : [];
  // un solo Brain (dal 24/11): nessun confronto, la sua vista direttamente
  const current = runs.length === 1 ? runs[0] : runs.find(r => r.name === selected);
  return <Page>
    <PageHeader title="Performance" subtitle="Valutazione del test PAPER dalla nuova ripartenza · run archiviate escluse" />
    {runs.length !== 1 && <BotSwitch both runs={runs.length ? runs : NAMES.map(n => ({ name: n, label: BOTS[n].label }))}
      selected={current ? current.name : '__both'} onSelect={onSelect} />}
    <LoadState error={error} loading={!error && !cmp} what="Dati di performance" />
    {cmp && !cmp.available && <Card><Note>Le run PAPER non sono disponibili.</Note></Card>}
    {runs.length > 0 && (current ? <SingleView run={current} perf={perfs[current.name]} nowMs={nowMs} />
      : <CompareView runs={runs} perfs={perfs} nowMs={nowMs} />)}
  </Page>;
}

export default function PaperPerformance() {
  const [selected, setSelected] = useState('__both');
  const c = usePoll(['/api/v3/compare'], 60000);
  const cmp = c.data ? c.data[0] : null;
  const names = cmp?.available ? (cmp.runs || []).map(r => r.name) : [];      // le run attive, non un elenco fisso
  const q = usePoll(names.map(n => `/api/v3/compare/${n}/performance`), 60000);
  const perfs = {};
  names.forEach((n, i) => { if (q.data && q.data[i]?.available) perfs[n] = q.data[i]; });
  return <PerformanceContent cmp={cmp} perfs={perfs} error={c.error && !cmp} selected={selected} onSelect={setSelected} />;
}
