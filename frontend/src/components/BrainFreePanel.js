import React from 'react';
const money = v => Number.isFinite(v) ? `$${v.toFixed(2)}` : 'Non disponibile';
const card = { background: '#1e293b', border: '1px solid #334155', borderRadius: 16, padding: 16, marginBottom: 12 };
const date = v => v ? new Date(v).toLocaleString('it-IT') : 'Non avviato';
export default function BrainFreePanel({ data, error }) {
  const d = data || {}, spend = d.spend || {};
  return <main style={{ maxWidth: 640, margin: 'auto', padding: 16, color: '#f1f5f9' }}>
    <h1>🧠 Brain AI libero · PAPER</h1>
    <p>Unico conto PAPER · {d.max_slots ?? 10} slot · decisioni DeepSeek</p>
    {(error || !d.online) && <p role="status" style={{ color: '#fbbf24' }}>Connessione o Brain non aggiornato. Visualizzati gli ultimi dati disponibili.</p>}
    <section style={card}><h2>Portafoglio</h2>
      <p>Equity {money(d.equity)} · P&amp;L run attuale {money(d.pnl)}</p>
      {Number.isFinite(d.pnl_since_original_start) && d.run_start_equity !== 2000 && <p>P&amp;L cumulato dalla V1 {money(d.pnl_since_original_start)} · base V2 {money(d.run_start_equity)}</p>}
      <p>Cash {money(d.cash)} · margine {money(d.margin)} / {money(d.margin_limit)}</p>
      <p>Slot {d.positions?.length ?? '—'} / {d.max_slots ?? 10} · {d.paused ? 'Nuove esposizioni in pausa' : d.available ? 'H24' : 'Stato non disponibile'}</p>
      <small>Prezzi non aggiornati: il floating non viene inventato. Liquidazione e costi sono simulazioni PAPER.</small>
    </section>
    <section style={card}><h2>Spesa DeepSeek</h2>
      <p>Oggi ({spend.today_utc}, UTC): {Number.isFinite(spend.today_usd) ? `$${spend.today_usd.toFixed(4)}` : '—'}</p>
      <p>Spesa AI run attuale: {Number.isFinite(spend.current_run_usd) ? `${spend.current_run_usd.toFixed(4)}` : '—'}</p>
      <p>Spesa AI storica: {Number.isFinite(spend.total_usd) ? `${spend.total_usd.toFixed(4)}` : '—'}</p>
      <p>Richieste dal costo incerto: {spend.uncertain_requests ?? '—'}</p>
      <small>Nessun tetto software. Consumo calcolato dai token a tariffa registrata; non è la fattura del provider.</small>
    </section>
    <section style={card}><h2>Posizioni aperte</h2>
      {!d.positions?.length && <p>Nessuna posizione aperta.</p>}
      {d.positions?.map(p => <article key={p.symbol} style={{ borderBottom: '1px solid #475569', paddingBottom: 12 }}>
        <h3>{p.symbol} · {p.side}</h3>
        <p>Margine {money(p.margin)} · leva {p.leverage.toFixed(2)}× · esposizione {money(p.notional)}</p>
        <p>Quantità {p.qty} · floating lordo {money(p.floating_gross)} · età {p.age_minutes.toFixed(1)} min</p>
        <p>Netto stimato alla chiusura: {money(p.net_close_estimate)} (costi registrati)</p>
        <p>Stop {p.stop} · target {p.target ?? 'Gestione AI'} · liquidazione stimata {p.liquidation_estimate}</p>
        <p><strong>Perché ha aperto:</strong> {p.reason}</p><p>Invalidazione: {p.invalidation}</p>
      </article>)}
    </section>
    <section style={card}><h2>Decisione AI</h2><p>{d.decision?.summary || 'Nessuna risposta AI completata.'}</p>
      <p>Stato provider: {d.provider_status || 'In attesa'}</p>
      <details><summary>Proposte AI ed eventuali rifiuti fisici</summary>
        {d.decision?.decisions?.map((a, i) => <p key={i}>{a.symbol} · {a.action} · {a.reason}</p>)}
        {d.execution_rejections?.map((a, i) => <p key={`reject-${i}`} style={{color:'#fbbf24'}}>{a.symbol}: non eseguito · {a.code}</p>)}
      </details>
      <details><summary>Scenari e motivazioni per simbolo</summary>{d.decision?.assessments?.map((a, i) => <p key={i}><strong>{a.symbol}</strong> · LONG: {a.long_case} · SHORT: {a.short_case} · {a.decision}</p>)}</details>
    </section>
    <section style={card}><h2>Contesto di mercato · non vincolante</h2>
      {Object.entries(d.market_context || {}).map(([key, c]) => <div key={key}><strong>{key}</strong> · {c.status} · {c.source}
        <p>{date(c.updated_ms)} · {JSON.stringify(c.data ?? 'Non disponibile')}</p></div>)}
      <small>Fear &amp; Greed: Alternative.me, ultimo valore pubblicato. Notizie, sentiment e dominanza sono dati per l’AI, senza filtri automatici.</small>
    </section>
    <section style={card}><h2>Ultimi trade completati (memoria V1 e V2)</h2>{d.trades?.map(t => <p key={t.position_id}>{t.symbol} · {t.side === 1 ? 'LONG' : 'SHORT'} · netto {money(t.net)} · fee {money(t.fees)}<br />{t.reason}</p>)}</section>
    <section style={card}><h2>Ultimo report serale</h2>
      {!d.latest_report ? <p>Il primo report verrà prodotto alle 22:00 italiane.</p> : <>
        <p>Giorno dati: {d.latest_report.today_utc} UTC · aperture {d.latest_report.opens_today}</p>
        <p>Netto realizzato {money(d.latest_report.realized_net)} · fee pagate {money(d.latest_report.fees)}</p>
        <p>WR {Number.isFinite(d.latest_report.win_rate) ? `${(d.latest_report.win_rate * 100).toFixed(1)}%` : 'Non disponibile'} · PF {Number.isFinite(d.latest_report.profit_factor) ? d.latest_report.profit_factor.toFixed(2) : 'Non definito'}</p>
        <p>Durata media {Number.isFinite(d.latest_report.mean_duration_minutes) ? d.latest_report.mean_duration_minutes.toFixed(1) : '—'} min · senza posizioni {d.latest_report.empty_minutes?.toFixed(1)} min</p>
        <p>Slot medi {Number.isFinite(d.latest_report.slot_occupancy) ? `${(d.latest_report.slot_occupancy * 100).toFixed(1)}%` : '—'} · non osservato {d.latest_report.unobserved_minutes?.toFixed(1)} min</p>
        <details><summary>Aperture per ora UTC e confronto descrittivo con i classici</summary>
          <p>{JSON.stringify(d.latest_report.opens_per_hour_utc)}</p><p>{JSON.stringify(d.latest_report.comparators)}</p>
          <p>Conti e capitali differenti: il confronto non dimostra una causa o una strategia migliore.</p>
        </details>
      </>}
    </section>
    <section style={card}><h2>Test di 168 ore</h2><p>Avvio verificato: {date(d.experiment_start_ms)}</p>
      <p>{Number.isFinite(d.elapsed_hours) ? d.elapsed_hours.toFixed(1) : '—'} / 168 ore · prompt e guardrail congelati salvo bug</p>
      <small style={{wordBreak: 'break-all'}}>Report alle 22:00 italiane. Hash configurazione: {d.config_hash}</small>
    </section>
  </main>;
}
