import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { BrainCloseControls } from '../components/OverviewCloseControls';
import { botStatus, equityView, guardianView } from '../paperBotsModel';
import {
  BotSwitch, C, Card, Fold, Fresh, Grid, LoadState, Note, Page, PageHeader, Pill, Section, SideTag, Stat,
  ago, botMeta, duration, LEG, num, own, pct, price, reasonText, REVIEW_ACTION, REVIEW_CODE, riskText, sgn, SOURCE, tone,
  usd, usePoll, when,
} from '../paperApp/kit';

// Schermata "Brain": i due bot PAPER attuali (Falco Evoluto, Brain Scalp). Gerarchia:
//   1. stato e capitale  2. equity  3. P&L realizzato / aperto  4. risultato netto dopo i costi AI
//   5. posizioni aperte con chiusura manuale SINGOLA  6. Guardian e decisioni (sezioni secondarie espandibili).
// Ogni valore dichiara se e' AGGIORNATO ora (trade chiusi, prezzo del ticker) o riferito all'ULTIMO GIRO del bot
// (equity a mercato e Guardian, registrati dal runner). Dati: /api/v3/compare e /api/v3/compare/<bot>/trades, sola
// lettura. Avvio, pausa e mandato restano interventi del proprietario sul server.
const ANALYST = { falco_evoluto: 'regole Falco Evoluto + AI consulente', deepseek: 'DeepSeek' };
export const panelId = name => `bot-dettagli-${String(name).replace(/[^a-z0-9_-]/gi, '_')}`;

function Badge({ status }) {
  return <Pill color={status.color}>{status.key === 'running' || status.key === 'running_wait' ? '● ' : status.key === 'paused' ? '⏸ ' : ''}{status.label}</Pill>;
}

function SummaryTile(r, on, nowMs) {
  const st = botStatus(r, nowMs);
  const eq = equityView(r);
  const m = botMeta(r.name);
  return <>
    <span style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
      <span style={{ fontSize: 14, fontWeight: 800, color: on ? C.text : C.soft, overflowWrap: 'anywhere' }}>{m.icon} {r.label}</span>
    </span>
    <span style={{ display: 'block', margin: '6px 0 4px' }}><Badge status={st} /></span>
    <span style={{ display: 'block', fontSize: 20, fontWeight: 800, color: C.text, fontVariantNumeric: 'tabular-nums' }}>
      {r.available ? usd(eq.value) : '—'}</span>
    <span style={{ display: 'block', fontSize: 13, fontWeight: 700, color: tone(eq.totalPct) }}>{r.available ? pct(eq.totalPct) : '—'}</span>
  </>;
}

function StatusCard({ run, nowMs }) {
  const st = botStatus(run, nowMs);
  const cfg = run.config || {};
  return <Card aria-label={`Stato ${run.label}`} accent={st.color}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
      <h2 style={{ fontSize: 20, fontWeight: 800, margin: 0 }}>{botMeta(run.name).icon} {run.label}</h2>
      <Badge status={st} />
    </div>
    <p style={{ fontSize: 14, color: st.color, margin: '8px 0 12px', lineHeight: 1.4 }}>{st.detail}</p>
    <Grid cols={3} gap={10}>
      <Stat label="Capitale iniziale" value={usd(run.initial_equity, 0)} />
      <Stat label="Giro ogni" value={`${num(cfg.cycle_minutes) ?? '—'} min`} />
      <Stat label="Chiusura manuale" value={run.manual_close_allowed === true ? 'attiva' : 'non attiva'}
        color={run.manual_close_allowed === true ? C.up : C.warn} />
    </Grid>
    {cfg.unico && <ModeRow run={run} nowMs={nowMs} />}
    <Note style={{ marginTop: 10 }}>Analisi: {own(ANALYST, cfg.analyst) || '—'}{cfg.unico?.claude ? ' + Claude consulente nei casi importanti' : ''} · rischio {cfg.risk_per_trade_pct ?? '—'} % per
      trade, {cfg.open_risk_pct ?? '—'} % aperto · leva {(cfg.leverage || []).join('–') || '—'}×{cfg.unico?.leverage_fit ? ' scelta dal codice' : ''} ·
      stop giornaliero {cfg.daily_stop_pct ?? '—'} %{cfg.unico?.partial ? ` · ${Math.round(num(cfg.unico.partial.fraction) * 100)} % a ${cfg.unico.partial.at_r}R, residuo verso ${cfg.unico.exit?.take_profit_r ?? '—'}R, ${cfg.unico.max_hold_hours ? `al massimo ${cfg.unico.max_hold_hours} h` : 'nessun limite di tempo'}` : ''}{cfg.symbols ? ` · ${cfg.symbols} mercati` : ''}</Note>
  </Card>;
}

// Brain unico: modalità (ATTIVO / SELETTIVO / PROTEZIONE) e slot occupati, in evidenza sotto lo stato.
function ModeRow({ run, nowMs }) {
  const g = guardianView(run);
  const tiers = run.config?.unico?.tiers;
  const net = g && g.realizedSession !== null ? g.realizedSession - (g.aiSession || 0) : null;
  return <div style={{ marginTop: 12, padding: '10px 12px', borderRadius: 14, background: C.card2, border: `1px solid ${C.line}` }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 13, color: C.muted }}>Modalità</span>
      {g ? <Pill color={g.color}>{g.label}</Pill> : <Pill color={C.muted}>dal primo giro</Pill>}
      <span style={{ fontSize: 13, color: C.muted }}>Slot {run.open_trades ?? 0}/{run.config?.max_positions ?? '—'}</span>
    </div>
    {g && <p style={{ fontSize: 13, color: C.soft, margin: '6px 0 0', lineHeight: 1.4 }}>{g.detail}</p>}
    <div style={{ fontSize: 13, color: C.soft, marginTop: 6 }}>Netto realizzato di sessione: <strong style={{ color: tone(net) }}>{sgn(net)}</strong>
      {tiers ? ` · selettivo da ${usd(tiers.selective_usd, 0)}, protezione da ${usd(tiers.protect_usd, 0)}` : ''}
      {g ? <span> · <Fresh live={false} atMs={g.asOfMs} nowMs={nowMs} /></span> : null}</div>
  </div>;
}

// Brain unico: salvadanaio separato dal capitale operativo.
function PiggyCard({ run, nowMs }) {
  const pg = run.piggy;
  if (!pg) return null;
  const sweeps = pg.sweeps || [];
  return <Card aria-label={`Salvadanaio ${run.label}`}>
    <span style={{ fontSize: 13, fontWeight: 700, color: C.muted, textTransform: 'uppercase', letterSpacing: '0.05em' }}>🐷 Salvadanaio</span>
    <Grid cols={2}>
      <div style={{ marginTop: 6 }}><Stat big label="Accantonato" value={usd(pg.total)} color={num(pg.total) > 0 ? C.up : C.text} /></div>
      <div style={{ marginTop: 6 }}><Stat label="Capitale operativo" value={usd(pg.operating_equity)}
        color={num(pg.operating_equity) < num(pg.reference_equity) ? C.down : C.text}
        sub={`riferimento ${usd(pg.reference_equity, 0)}`} /></div>
    </Grid>
    <Note>A mezzanotte (ora italiana) passa nel salvadanaio solo il profitto realizzato sopra {usd(pg.reference_equity, 0)}; non
      viene reinvestito. Posizioni aperte e P&amp;L non realizzato restano fuori; una perdita resta nel capitale operativo, senza
      reintegri. Prossimo accantonamento: {when(pg.next_sweep_ms)}{nowMs < pg.next_sweep_ms ? ` (tra ${duration(pg.next_sweep_ms - nowMs)})` : ''}.</Note>
    {sweeps.length > 0 && <div style={{ marginTop: 8, fontSize: 13, color: C.soft }}>Ultimi accantonamenti: {sweeps.slice(-5).reverse()
      .map(([t, v]) => `${when(t)} ${usd(v)}`).join(' · ')}</div>}
  </Card>;
}

function EquityCard({ run, nowMs }) {
  const eq = equityView(run);
  return <Card aria-label={`Equity ${run.label}`}>
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 13, fontWeight: 700, color: C.muted, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        Equity {eq.basis === 'market' ? 'a mercato' : 'contabile'}</span>
      {eq.basis === 'market' ? <Fresh live={false} atMs={eq.asOfMs} nowMs={nowMs} /> : <Fresh live atMs={null} nowMs={nowMs} />}
    </div>
    <div style={{ fontSize: 38, fontWeight: 800, margin: '6px 0 2px', fontVariantNumeric: 'tabular-nums', color: C.text }}>{usd(eq.value)}</div>
    <div style={{ fontSize: 16, fontWeight: 700, color: tone(eq.total) }}>{sgn(eq.total)} ({pct(eq.totalPct)}) sul capitale</div>
    <Note>{eq.basis === 'market'
      ? `Valore a mercato calcolato dal bot all’ultimo giro, posizioni aperte e commissioni di chiusura incluse. Contabile (solo trade chiusi): ${usd(eq.settled)}.`
      : 'Nessuna valutazione a mercato registrata: è l’equity contabile dei soli trade chiusi.'}</Note>
  </Card>;
}

function PnlCard({ run, nowMs }) {
  const eq = equityView(run);
  const ai = num(run.ai_cost_total);
  const fees = num(run.fees);
  const overall = eq.value !== null && eq.initial !== null && ai !== null ? eq.value - eq.initial - ai : null;
  return <Card aria-label={`Profitti e perdite ${run.label}`}>
    <Grid cols={2}>
      <div>
        <Stat label="Realizzato (trade chiusi)" value={sgn(run.net_pnl)} color={tone(run.net_pnl)}
          sub={`commissioni incluse: ${usd(fees)}`} />
        <div style={{ marginTop: 6 }}><Fresh live atMs={null} nowMs={nowMs} /></div>
      </div>
      <div>
        <Stat label="Aperto (posizioni in corso)" value={sgn(eq.unrealized)} color={tone(eq.unrealized)}
          sub={eq.unrealized === null ? 'nessuna valutazione' : 'a mercato'} />
        <div style={{ marginTop: 6 }}><Fresh live={false} atMs={eq.asOfMs} nowMs={nowMs} /></div>
      </div>
    </Grid>
    <div style={{ borderTop: `1px solid ${C.line}`, margin: '14px 0 12px' }} />
    <Grid cols={2}>
      <Stat label="Costi AI (totale run)" value={usd(ai, 3)} color={C.soft}
        sub={run.ai_spend?.by_provider?.claude ? `DeepSeek ${usd(run.ai_spend.by_provider.deepseek?.total, 3)} · Claude ${usd(run.ai_spend.by_provider.claude.total, 3)}` : null} />
      <Stat label="Netto realizzato dopo AI" value={sgn(run.net_after_ai)} color={tone(run.net_after_ai)}
        sub={num(run.return_after_ai_pct) === null ? null : pct(run.return_after_ai_pct)} />
    </Grid>
    <div style={{ marginTop: 14, padding: '12px 14px', borderRadius: 14, background: C.card2, border: `1px solid ${C.line}` }}>
      <Stat big label="Risultato netto complessivo (equity − capitale − costi AI)" value={sgn(overall)} color={tone(overall)}
        sub={overall === null ? 'non calcolabile: manca un dato registrato' : `${pct(overall / eq.initial * 100)} sul capitale · include l’aperto all’ultimo giro`} />
    </div>
  </Card>;
}

function Positions({ run, live, onRefresh, nowMs }) {
  const open = live ? live.open_positions || [] : run.open_positions || [];
  const haveLive = !!live;
  return <Section title={`Posizioni aperte (${open.length})`}
    hint={haveLive ? 'Prezzo e P&L aggiornati dal ticker a ogni lettura (P&L lordo, commissioni escluse). Stop = stop iniziale.'
      : 'Prezzo e P&L per posizione non disponibili in questo momento: il P&L aperto complessivo è nella card sopra.'}>
    {open.length === 0 && <Card style={{ textAlign: 'center', color: C.muted, fontSize: 14 }}>Nessuna posizione aperta</Card>}
    <BrainCloseControls positions={open} allowCloseAll={false} readOnly={run.manual_close_allowed !== true}
      serverPending={run.close_pending === true} onRefresh={onRefresh}
      closeUrl={`/api/v3/compare/${run.name}/close`} resultUrl={`/api/v3/compare/${run.name}/close-result`}
      itemStyle={{ background: C.card, borderRadius: 18, padding: 14, border: `1px solid ${C.line}`, marginBottom: 10 }}
      closeLabel={p => `Chiudi ${p.symbol} (PAPER)`}
      renderPosition={p => <div data-testid={`bot-position-${run.name}`}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <SideTag side={p.side} />
          <strong style={{ fontSize: 17 }}>{String(p.symbol || '?').replace('USDT', '')}</strong>
          <span style={{ color: C.soft, fontSize: 14 }}>{p.leverage ?? '—'}×</span>
          {own(LEG, legOf(run, p)) && <span style={{ fontSize: 12, color: C.accent }}>{own(LEG, legOf(run, p))}</span>}
          <span style={{ marginLeft: 'auto', fontSize: 18, fontWeight: 800, color: tone(p.unrealized_pnl) }}>
            {haveLive ? sgn(p.unrealized_pnl) : ''}</span>
        </div>
        <Grid cols={3} gap={8}>
          <div style={{ marginTop: 10 }}><Stat compact label="Entrata" value={price(p.entry)} /></div>
          <div style={{ marginTop: 10 }}><Stat compact label="Prezzo ora" value={haveLive ? price(p.price) : '—'} /></div>
          <div style={{ marginTop: 10 }}><Stat compact label="Margine" value={usd(p.margin)} /></div>
          <Stat compact label={stopBrain(run, p) ? 'Stop (Brain)' : 'Stop'} value={price(stopBrain(run, p) || p.stop)} color={C.down} />
          <Stat compact label="Take profit" value={haveLive ? price(p.take_profit) : '—'} color={C.up} />
          <Stat compact label="Aperta da" value={Number.isSafeInteger(p.opened_at_ms) ? duration(nowMs - p.opened_at_ms) : '—'} />
        </Grid>
      </div>} />
    {run.manual_close_allowed !== true && open.length > 0 && <Note>Chiusura manuale non disponibile finché il servizio
      uscite di questo bot non è sano. Stop e take profit restano attivi.</Note>}
  </Section>;
}

// quota e stop stretto: dal dato live (ticker) o, in mancanza, dalla lettura del giro (stessa posizione)
const fromRun = (run, p) => (run.open_positions || []).find(o => o.position_id === p.position_id) || {};
const legOf = (run, p) => p.leg || fromRun(run, p).leg || null;
const stopBrain = (run, p) => p.stop_brain || fromRun(run, p).stop_brain || null;

function ReviewsFold({ run, nowMs }) {
  const reviews = run.reviews || [];
  if (!run.config?.unico?.position_review) return null;
  return <Fold title={`🤖 Revisioni AI delle posizioni (${reviews.length})`} label={`Revisioni ${run.label}`}>
    {reviews.length === 0 && <Note>Nessuna revisione finora: avviene a ogni giro per ogni posizione aperta.</Note>}
    {reviews.map((r, i) => <div key={`${r.ts_ms}-${i}`} style={{ padding: '8px 0', borderBottom: i < reviews.length - 1 ? `1px solid ${C.line}` : 'none' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 14 }}>
        <strong>{String(r.symbol || '—').replace('USDT', '')}</strong>
        <span style={{ color: C.muted, fontSize: 13 }}>{ago(r.ts_ms, nowMs) || when(r.ts_ms)}</span>
      </div>
      <div style={{ fontSize: 14, color: r.executed && r.executed !== 'HOLD' ? C.up : C.soft, marginTop: 2 }}>
        {own(REVIEW_ACTION, r.executed) || '—'}{r.proposed && r.proposed !== r.executed ? ` (DeepSeek: ${own(REVIEW_ACTION, r.proposed) || '—'})` : ''}
        {own(REVIEW_CODE, r.code) ? <span style={{ color: C.warn }}> · {own(REVIEW_CODE, r.code)}</span> : null}</div>
      {r.claude && <div style={{ fontSize: 13, color: C.muted, marginTop: 2 }}>Claude: {own(REVIEW_ACTION, r.claude) || (r.claude === 'CONFIRM' ? 'conferma' : r.claude)} · decisione: {own(SOURCE, r.source) || '—'}</div>}
    </div>)}
    <Note>DeepSeek propone; nei casi importanti Claude dà un parere indipendente e un arbitro deterministico decide; il codice
      valida: lo stop si sposta solo verso il profitto. Stop, take profit e protezioni restano sempre attivi, anche se le AI
      non rispondono. Nessuna chiusura per solo tempo.</Note>
  </Fold>;
}

// DeepSeek + Claude: quanto collaborano e con quale risultato (dal journal)
function CollaborationFold({ run }) {
  const c = run.collaboration;
  if (!run.config?.unico?.claude) return null;
  const sp = run.ai_spend?.by_provider || {};
  return <Fold title="🤝 DeepSeek + Claude" label={`Collaborazione AI ${run.label}`}>
    {!c ? <Note>Nessun consulto finora: Claude viene chiamato solo nelle situazioni importanti.</Note> : <>
      <Grid cols={2} gap={10}>
        <Stat compact label="Aperture valutate da Claude" value={String(c.entry.consults)} sub={`d’accordo ${c.entry.agreed} · scelta di Claude ${c.entry.claude_adopted}`} />
        <Stat compact label="Aperture fermate" value={String(c.entry.blocked)} sub={`Claude non disponibile: ${c.entry.unavailable}`} />
        <Stat compact label="Posizioni con consulto" value={String(c.review.consults)} sub={`d’accordo ${c.review.agreed} · Claude ${c.review.claude_adopted} · DeepSeek ${c.review.deepseek_kept}`} />
        <Stat compact label="Costi Claude" value={usd(sp.claude?.total, 3)} sub={`DeepSeek ${usd(sp.deepseek?.total, 3)}`} />
      </Grid>
      <div style={{ marginTop: 10, fontSize: 13, color: C.soft }}>Risultato netto dei trade per decisione: {['deepseek', 'agreed', 'claude']
        .map(k => `${own(SOURCE, k)} ${c.results[k].trades} trade ${sgn(c.results[k].net_pnl)}`).join(' · ')}</div>
    </>}
    <Note>Serve a capire se e quando Claude aggiunge valore, senza presumere che abbia sempre ragione. Limite di spesa di
      Claude: {usd(run.config.unico.claude.daily_cap_usd, 2)} al giorno.</Note>
  </Fold>;
}

function GuardianFold({ run, nowMs }) {
  const g = guardianView(run);
  return <Fold title={`🛡️ Guardian${g ? ` · ${g.label}` : ''}`} label={`Guardian ${run.label}`}>
    {!g ? <Note>Nessuna valutazione registrata finora: compare dopo il primo giro.</Note> : <>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <Pill color={g.color}>{g.label}</Pill><Fresh live={false} atMs={g.asOfMs} nowMs={nowMs} />
      </div>
      <p style={{ fontSize: 14, color: C.soft, margin: '10px 0' }}>{g.detail}{g.reasons.length ? ` (${g.reasons.join(', ')})` : ''}</p>
      <Grid cols={2} gap={10}>
        <Stat label="Picco di sessione" value={usd(g.peak)} />
        <Stat label="Profitto restituito" value={usd(g.giveback)} />
        <Stat label="Floor" value={usd(g.floor)} />
        <Stat label="Rischio ancora disponibile" value={usd(g.budget)} />
        <Stat label="Tetto per nuova apertura" value={g.state === 'NORMAL' ? 'ordinario' : usd(g.riskCap)} />
      </Grid>
      <Note>Il floor limita le nuove aperture: non garantisce il risultato finale. La sessione parte {g.unico ? 'a mezzanotte (ora italiana)' : 'alle 08:00'}.</Note>
    </>}
  </Fold>;
}

function DecisionsFold({ run, nowMs }) {
  const decisions = run.decisions || [];
  return <Fold title={`🧾 Ultime decisioni (${decisions.length})`} label={`Decisioni ${run.label}`}>
    {decisions.length === 0 && <Note>Nessuna decisione registrata.</Note>}
    {decisions.map((d, i) => <div key={`${d.ts_ms}-${i}`} style={{ padding: '8px 0', borderBottom: i < decisions.length - 1 ? `1px solid ${C.line}` : 'none' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, fontSize: 14 }}>
        <strong>{String(d.symbol || '—').replace('USDT', '')}</strong>
        <span style={{ color: C.muted, fontSize: 13 }}>{ago(d.ts_ms, nowMs) || when(d.ts_ms)}</span>
      </div>
      <div style={{ fontSize: 14, color: d.kind === 'OPEN' ? C.up : C.soft, marginTop: 2 }}>{reasonText(d.rationale)}
        {d.risk_reason ? <span style={{ color: C.warn }}> · {riskText(d.risk_reason)}</span> : null}</div>
    </div>)}
    <Note><Link to="/performance" style={{ color: '#c4b5fd' }}>Tutti i motivi (anche NO_TRADE) in Performance →</Link></Note>
  </Fold>;
}

export function BotCard({ run, live, nowMs, onRefresh }) {
  if (run.available !== true) {
    const st = botStatus(run, nowMs);
    return <Card aria-label={`Bot ${run.label}`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <strong style={{ fontSize: 18 }}>{run.label}</strong><Badge status={st} /></div>
      <Note>{st.detail} Nessun dato viene mostrato finché non esiste il suo journal.</Note>
    </Card>;
  }
  return <section aria-label={`Bot ${run.label}`}>
    <StatusCard run={run} nowMs={nowMs} />
    <EquityCard run={run} nowMs={nowMs} />
    <PnlCard run={run} nowMs={nowMs} />
    <PiggyCard run={run} nowMs={nowMs} />
    <Positions run={run} live={live} onRefresh={onRefresh} nowMs={nowMs} />
    <div style={{ marginTop: 18 }}>
      <ReviewsFold run={run} nowMs={nowMs} />
      <CollaborationFold run={run} />
      <GuardianFold run={run} nowMs={nowMs} />
      <DecisionsFold run={run} nowMs={nowMs} />
    </div>
  </section>;
}

export function PaperBotsContent({ data, live = null, error = false, nowMs = Date.now(), onRefresh = () => {},
  initialSelected = null, onSelectedChange = () => {} }) {
  const runs = data?.available ? (data.runs || []) : [];
  const [choice, setChoice] = useState(initialSelected);
  // scelta valida o, in mancanza, il primo bot: mai un pannello vuoto se i dati cambiano
  const current = runs.find(r => r.name === choice) || runs[0] || null;
  const currentName = current ? current.name : null;
  const notify = useRef(onSelectedChange);
  notify.current = onSelectedChange;
  useEffect(() => { notify.current(currentName); }, [currentName]);
  return <Page>
    <PageHeader title="Brain" subtitle={`${runs.length === 1 ? 'Brain unico PAPER' : runs.map(r => r.label).join(' e ') || 'Bot PAPER'} · dati letti ${data?.generated_at_ms ? ago(data.generated_at_ms, nowMs) : '—'}`} />
    <LoadState error={error && !data} loading={!error && data === null} what="Dati dei bot" />
    {error && data && <p role="status" style={{ color: C.warn, fontSize: 14, margin: '6px 2px' }}>Ultimo aggiornamento non
      riuscito: i valori mostrati sono quelli dell’ultima lettura.</p>}
    {!error && data && !data.available && <Card><strong>Bot non ancora attivi</strong>
      <Note>La run PAPER non è ancora stata preparata: nessun dato viene mostrato finché non esiste il suo journal.</Note></Card>}
    {runs.length > 0 && <>
      {runs.length > 1 && <BotSwitch runs={runs} selected={current.name} onSelect={setChoice} render={(r, on) => SummaryTile(r, on, nowMs)}
        controls={r => panelId(r.name)}
        label={(r, on) => { const st = botStatus(r, nowMs); const eq = equityView(r);
          return `${r.label}: ${st.label}${r.available ? `, equity ${usd(eq.value)}` : ''}${on ? ', dettagli mostrati sotto' : ', mostra i dettagli'}`; }} />}
      <div id={panelId(current.name)} role="region" aria-label={`Dettagli ${current.label}`}>
        <BotCard key={current.name} run={current} live={live && live.name === current.name ? live : null}
          nowMs={nowMs} onRefresh={onRefresh} />
      </div>
      <Note>Soldi simulati: nessun ordine reale. {runs.length > 1 ? 'Ogni bot ha la sua run, il suo journal e il suo servizio uscite.' : 'Una sola run, con il suo journal e il suo servizio uscite.'} Ciò che non
        è registrato resta “—”. Qui sono consentite solo chiusure manuali singole, con conferma; avvio, pausa e mandato
        restano un intervento del proprietario sul server. Le run precedenti e gli altri portafogli sono
        nell’<Link to="/archivio" style={{ color: '#c4b5fd' }}>Archivio</Link>.</Note>
    </>}
  </Page>;
}

export default function PaperBots() {
  const [selected, setSelected] = useState(null);
  const cmp = usePoll(['/api/v3/compare']);
  const data = cmp.data ? cmp.data[0] : null;
  const runs = data?.available ? data.runs || [] : [];
  const current = runs.find(r => r.name === selected && r.available) || null;
  // prezzo e P&L per posizione (ticker) solo per il bot mostrato; se la rotta manca o fallisce restano i dati del giro
  const tr = usePoll(current ? [`/api/v3/compare/${current.name}/trades?limit=1`] : []);
  const live = !tr.error && tr.data && tr.data[0] && tr.data[0].name === current?.name ? tr.data[0] : null;
  const refresh = () => { cmp.refresh(); tr.refresh(); };
  return <PaperBotsContent data={data} live={live} error={cmp.error} onRefresh={refresh} onSelectedChange={setSelected} />;
}
