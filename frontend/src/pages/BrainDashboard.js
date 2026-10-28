import React, { useEffect, useState } from 'react';
import { brainAPI } from '../api';
import BrainFreePanel from '../components/BrainFreePanel';

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
const leverage = value => Number.isFinite(value) && value > 0 ? `${fmt(value, 2).replace(/\.?0+$/, '')}×` : '—';
const percent = value => Number.isFinite(value) ? `${fmt(value)}%` : '—';
const date = ms => Number.isFinite(ms) ? new Date(ms).toLocaleString('it-IT') : 'Non disponibile';
const color = value => Number.isFinite(value) ? (value < 0 ? '#f87171' : '#4ade80') : '#94a3b8';
const lookup = (mapping, value) => typeof value === 'string' && Object.prototype.hasOwnProperty.call(mapping, value) ? mapping[value] : 'Non disponibile';
const source = value => lookup({ 'brain-deepseek': 'DeepSeek', adaptive_ai: 'AI adattiva', classical_rules: 'Regole classiche', rules: 'Regole classiche', 'classical-rules': 'Regole classiche', local_adaptive_profit: 'Protezione locale del profitto', classical_engine_1m: 'Stop / target del motore' }, value);
const provider = value => lookup({ adaptive_ai: 'Risposta AI ricevuta', model_pending: 'AI in elaborazione · regole e protezioni attive', missing_model_key: 'AI non configurata · regole attive', paced_profile_allowance: 'Attesa quota AI del profilo', paced_monthly_allowance: 'Attesa quota AI mensile', hard_budget_cap: 'Limite di spesa AI raggiunto', stale_model_result: 'Risposta AI scaduta o esposizione cambiata', invalid_or_failed_model_result: 'Risposta AI non applicabile', already_reserved: 'Richiesta già prenotata' }, value);
const noteStyle = { color: '#94a3b8', fontSize: '12px', lineHeight: 1.5 };
const Row = ({ label, children }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', padding: '5px 0', fontSize: '13px' }}>
    <span style={{ color: '#94a3b8' }}>{label}</span><span>{children}</span>
  </div>
);

// Exported for offline server-render tests; React escapes all model text.
export function BrainCards({ data }) {
  const paired = data?.runtime === 'classical-adaptive-v1';
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
        <Row label="Margine totale impegnato">{money(portfolio.margin_in_use)}</Row>
        <Row label="P&L da $1000 PAPER"><span style={{ color: color(portfolio.pnl) }}>{money(portfolio.pnl)} · {fmt(portfolio.pnl_pct)}%</span></Row>
        <Row label="Cicli completati">{portfolio.cycles ?? '—'}</Row>
        <p style={noteStyle}>Valutazione alle {date(portfolio.valued_ms)}. {portfolio.stale ? 'Dati non aggiornati.' : paired ? 'Prezzi osservati dal profilo; controllare data e stato feed.' : 'Prezzi dell’ultimo ciclo, aggiornati ogni 15 minuti.'}</p>
      </Card>
      <Card title="Posizioni aperte">
        {positions.map(position => (
          <div key={position.symbol} style={{ borderBottom: '1px solid #334155', padding: '8px 0' }}>
            <Row label={position.symbol}><strong style={{ color: position.side === 'LONG' ? '#4ade80' : '#f87171' }}>{position.side}</strong></Row>
            <Row label="Margine impegnato">{money(position.margin)}</Row>
            <Row label="Leva effettiva">{leverage(position.leverage)}</Row>
            <Row label="Valore posizione (entry)">{money(position.notional_entry)}</Row>
            <Row label="Entry">{fmt(position.entry, 6)}</Row>
            <Row label="P&L floating lordo"><span style={{ color: color(position.floating_pnl) }}>{money(position.floating_pnl)}</span></Row>
            <Row label="Rendimento lordo sul margine"><span style={{ color: color(position.floating_margin_roi_pct) }}>{percent(position.floating_margin_roi_pct)}</span></Row>
            {paired && <>
              <Row label="Netto stimato alla chiusura"><span style={{ color: color(position.net_close_estimate) }}>{money(position.net_close_estimate)}</span></Row>
              <Row label="ROI netto stimato">{percent(position.net_margin_roi_pct)}</Row>
              <Row label="Aperta da">{fmt(position.age_minutes, 1)} min</Row>
              <Row label="Stop / target">{fmt(position.stop, 6)} / {fmt(position.target, 6)}</Row>
              <Row label="Ingresso deciso da">{source(position.decision_source)}</Row>
              <p style={noteStyle}>{position.entry_reason || 'Motivo ingresso non disponibile'}</p>
            </>}
            {position.stale && <div style={noteStyle}>Prezzo non aggiornato · {date(position.valued_ms)}</div>}
          </div>
        ))}
        {!positions.length && <p style={noteStyle}>{available ? 'Nessuna posizione aperta' : 'Posizioni non disponibili'}</p>}
        <p style={noteStyle}>Il margine è il capitale PAPER impegnato, inclusi eventuali DCA; il valore posizione è quantità × entry media. La leva è quella salvata dal pilot, non il massimo consentito. Floating e rendimento sul margine sono lordi: commissioni e funding non detratti.</p>
        {paired && <p style={noteStyle}>Il netto stimato include i costi del motore PAPER, anche quelli d’ingresso già pagati. È una stima di chiusura, non un rendimento garantito.</p>}
      </Card>
      <Card title="Ultimi trade chiusi">
        {trades.map((trade, index) => (
          <div key={`${trade.symbol}-${trade.closed_ms}-${index}`} style={{ borderBottom: '1px solid #334155', padding: '8px 0' }}>
            <Row label={`${trade.symbol} · ${trade.side}`}><span style={{ color: color(trade.pnl) }}>{money(trade.pnl)}</span></Row>
            <div style={noteStyle}>{trade.reason || 'Motivo non disponibile'}{trade.partial ? ' · Chiusura parziale' : ''} · {date(trade.closed_ms)}</div>
            {paired && <div style={noteStyle}>Margine {money(trade.margin)} · {leverage(trade.leverage)} · {source(trade.decision_source)}</div>}
          </div>
        ))}
        {!trades.length && <p style={noteStyle}>{available ? 'Nessun trade chiuso disponibile' : 'Storico non disponibile'}</p>}
        <p style={noteStyle}>{paired ? 'Ultimi 20 realizzi dal registro SQLite' : 'Ultimi 20 realizzi esportati'}, incluse le chiusure parziali.</p>
      </Card>
      <Card title="Statistiche">
        <Row label="Trade interamente chiusi">{stats.closed_trades ?? '—'}</Row>
        <Row label="Win rate">{fmt(stats.win_rate_pct)}%</Row>
        <Row label="P&L medio per trade">{money(stats.average_pnl)}</Row>
        <Row label={`Daily stop · limite ${Number.isFinite(daily.limit_pct) ? fmt(daily.limit_pct, 0) : paired ? '—' : '20'}%`}>{daily.stopped === true ? 'Raggiunto · protezioni attive' : daily.stopped === false ? 'Non raggiunto' : 'Non disponibile'}</Row>
        <Row label="Perdita equity oggi">{fmt(daily.drawdown_pct)}%</Row>
        <Row label="Quota del limite usata">{fmt(daily.used_limit_pct)}%</Row>
        <p style={noteStyle}>Giorno UTC: {daily.day || '—'}. {daily.state === 'awaiting_utc_rollover' ? 'In attesa del rollover del pilot.' : ''} Le statistiche aggregano i parziali per posizione e includono l’intero storico SQLite.</p>
      </Card>
      <Card title={paired ? 'Decisioni e supervisione' : 'Ultimo reasoning DeepSeek'}>
        <Row label="Ultima chiamata tentata">{date(reasoning.last_call_ms)}</Row>
        {paired ? <>
          <Row label="Fonte ultimo ciclo">{source(data?.execution?.decision_source)}</Row>
          <Row label="Nuovi ingressi">{data?.execution?.operator_paused === true ? 'In pausa · protezioni attive' : available ? 'Consentiti dai controlli del profilo' : 'Non disponibile'}</Row>
          <Row label="Ultimo stato AI">{provider(data?.execution?.provider_status)}</Row>
          <Row label="Feed rapido">{data?.execution?.fresh_fast_data === true ? 'Disponibile' : available ? 'Non aggiornato · nuovi ingressi sospesi' : 'Non disponibile'}</Row>
          {data?.execution?.coverage_unresolved && <p style={{ ...noteStyle, color: '#fbbf24' }}>Intervallo dati incompleto: nuovi ingressi sospesi, verifica necessaria.</p>}
          <p style={noteStyle}>{data?.execution?.note}</p>
          <strong style={{ fontSize: '13px' }}>Ultima proposta AI · {date(reasoning.advice?.ts_ms)}</strong>
          {(reasoning.advice?.decisions || []).map((d, i) => <p key={i} style={{ ...noteStyle, overflowWrap: 'anywhere' }}>{d.symbol} · {d.action}: {d.reason || 'Motivo non disponibile'}</p>)}
          {!reasoning.advice?.decisions?.length && <p style={noteStyle}>Nessuna proposta disponibile.</p>}
          <Row label="Spesa AI prenotata oggi (condivisa)">{money(data?.api_budget?.daily_reserved)}</Row>
          <Row label="Tetto AI giornaliero condiviso">{money(data?.api_budget?.shared_daily_cap)}</Row>
          <p style={noteStyle}>H24 comprende regole e protezione locale. Le chiamate AI rispettano il budget; le prenotazioni non sono la fattura del fornitore.</p>
        </> : <>
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
        </>}
        <p style={noteStyle}>{reasoning.note}</p>
      </Card>
      <Card title="Stato sistema">
        <Row label="Container">{system.container || (paired ? 'Non attestato dal reader' : 'superbot-brain-pilot')}</Row>
        <Row label="Salute Docker">{system.health || 'unknown'}</Row>
        <Row label="SHA in esecuzione">{system.sha || 'Non disponibile'}</Row>
        <Row label="Uptime">{system.uptime_seconds == null ? 'Non disponibile' : `${fmt(system.uptime_seconds / 3600, 1)} h`}</Row>
        <Row label="Heartbeat">{system.heartbeat || 'unknown'}</Row>
        <Row label="Ultimo heartbeat">{date(system.heartbeat_ms)}</Row>
        {!paired && typeof system.operator_paused === 'boolean' && <Row label="Nuovi ingressi">{system.operator_paused ? 'In pausa · protezioni attive' : 'Nessuna pausa operatore'}</Row>}
        {paired && <Row label="Versione metodo">{system.method_version ? `${system.method_version.slice(0, 12)}…` : 'Non disponibile'}</Row>}
        <p style={noteStyle}>{system.note}</p>
      </Card>
    </div>
  );
}

function LegacyBrainDashboard() {
  const [data, setData] = useState(null);
  const [selection, setSelection] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    const poll = async () => {
      try {
        let response;
        if (typeof brainAPI.getProfiles === 'function') {
          try { response = await brainAPI.getProfiles(controller.signal); }
          catch (e) {
            if (e?.response?.status !== 404) throw e;
            response = await brainAPI.getStatus(controller.signal);
          }
        } else response = await brainAPI.getStatus(controller.signal);
        if (!controller.signal.aborted) setData(response.data?.profiles ? response.data : { status: 'ok', profiles: {}, legacy: response.data });
      } catch (_) {
        if (!controller.signal.aborted) setData({ status: 'unavailable', profiles: {}, legacy: { status: 'unavailable' } });
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
  const selected = selection || (data?.profiles?.hawk?.status === 'ok' ? 'hawk' : data?.profiles?.bull?.status === 'ok' ? 'bull' : 'legacy');
  const current = selected === 'legacy' ? data?.legacy : data?.profiles?.[selected] || { runtime: 'classical-adaptive-v1', profile: selected, status: data?.status === 'unavailable' ? 'unavailable' : 'not_started' };
  const title = selected === 'legacy' ? 'conto precedente' : selected === 'hawk' ? 'Hawk' : 'Bull';
  return (
    <main style={{ padding: '16px', maxWidth: '600px', margin: '0 auto', color: '#f1f5f9' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '4px' }}>🧠 Brain · {title} · PAPER</h1>
      <p style={noteStyle}>Conti virtuali distinti · sola osservazione · capitale e risultati non sommati</p>
      <nav aria-label="Portafoglio Brain" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', margin: '12px 0' }}>
        {[['hawk', 'Hawk + Brain'], ['bull', 'Bull + Brain'], ['legacy', 'Brain precedente']].map(([id, label]) => (
          <button key={id} data-profile={id} type="button" aria-pressed={selected === id} onClick={() => setSelection(id)} style={{ background: selected === id ? '#075985' : '#1e293b', color: '#f1f5f9', border: '1px solid #475569', borderRadius: '10px', padding: '10px' }}>{label}</button>
        ))}
      </nav>
      <div role="status" aria-live="polite" style={{ ...noteStyle, marginBottom: '12px' }}>
        {loading ? 'Caricamento…' : current?.status === 'not_started' ? 'Profilo non ancora avviato: comparirà dopo il rilascio del nuovo motore.' : current?.status !== 'ok' ? 'Brain non disponibile. Nuovo controllo automatico tra 30 secondi.' : 'Dati PAPER · nessun controllo operativo'}
      </div>
      <BrainCards data={current} />
    </main>
  );
}


export default function BrainDashboard() {
  const [free, setFree] = useState(null);
  const [error, setError] = useState(false);
  const [archive, setArchive] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); let timer;
    const poll = async () => {
      try {
        const r = await brainAPI.getFreeStatus(controller.signal);
        if (!controller.signal.aborted) {
          if (r.data.status === 'retired') setFree(null);
          else if (r.data.available || r.data.status === 'unavailable') setFree(r.data);
          setError(!r.data.available && !['not_started', 'retired'].includes(r.data.status));
        }
      } catch (_) { if (!controller.signal.aborted) setError(true); }
      if (!controller.signal.aborted) timer = setTimeout(poll, 15000);
    };
    poll(); return () => { controller.abort(); clearTimeout(timer); };
  }, []);
  if (!free) return <><div style={{ padding: 12, textAlign: 'center' }}><a href="/brain/scalp" style={{color:'#38bdf8'}}>Brain Hawk / Brain Bull · nuovi portafogli PAPER</a></div><LegacyBrainDashboard /></>;
  return <><div style={{ padding: 12, textAlign: 'center' }}><a href="/brain/scalp" style={{color:'#38bdf8'}}>Brain Hawk / Brain Bull · nuovi portafogli PAPER</a><p />
    <button type="button" onClick={() => setArchive(!archive)}>{archive ? 'Torna al Brain AI libero' : 'Consulta archivio dei tre Brain precedenti'}</button>
    {archive && <p>Archivio separato: questi risultati non fanno parte della nuova run da 2.000$.</p>}
  </div>{archive ? <LegacyBrainDashboard /> : <BrainFreePanel data={free} error={error} />}</>;
}
