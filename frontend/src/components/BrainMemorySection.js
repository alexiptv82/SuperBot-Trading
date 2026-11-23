import React from 'react';

// Memoria e apprendimento del Brain (sola lettura, /api/v3/brain/memory). Stesso stile delle sezioni Overview.
// Nessun controllo operativo: niente pulsanti, niente soglie modificabili. Solo codici fissi tradotti qui.
const BLOCK = { background: '#172338', border: '1px solid #2f425b', borderRadius: 16, padding: 16, marginBottom: 12 };
const MUTED = { color: '#a8bacd', fontSize: 12 };
const ROW = { display: 'flex', justifyContent: 'space-between', gap: 12, padding: '5px 0', fontSize: 13 };

const LINK_TEXT = {
  valid: 'tracciata', missing: 'snapshot mancante', chain_broken: 'catena non integra',
  decision_written_late: 'scritta in ritardo', snapshot_written_late: 'snapshot in ritardo',
  snapshot_after_open: 'snapshot dopo l’apertura', snapshot_hash_mismatch: 'hash non coincidente',
  snapshot_conflict: 'snapshot doppio',
};
const KIND_TEXT = { OPEN: 'Apertura', NO_TRADE: 'Nessun trade', HOLD: 'Attesa' };
const STATUS_TEXT = { APPROVED: 'approvata', REJECTED: 'rifiutata', RISK_REJECTED: 'rifiutata dal rischio', DRAFT: 'bozza' };
const RULE_TEXT = { reentry_limit: 'oltre il 2° reingresso', loss_cooldown: 'attesa dopo perdita' };

// Solo chiavi PROPRIE delle tabelle: un codice come "__proto__" o "toString" non deve mai diventare testo o oggetto.
const own = (table, code) => (typeof code === 'string' && Object.prototype.hasOwnProperty.call(table, code)
  ? table[code] : undefined);
const n = value => (Number.isFinite(value) ? value : '—');
const when = ms => (Number.isFinite(ms) ? new Date(ms).toLocaleString('it-IT') : '—');
const linkText = code => own(LINK_TEXT, code) || (typeof code === 'string' && code ? 'non valida' : '—');
const Row = ({ label, children }) => <div style={ROW}><span style={MUTED}>{label}</span><span>{children}</span></div>;

function Progress({ label, value, target }) {
  const pct = Number.isFinite(value) && Number.isFinite(target) && target > 0 ? Math.min(100, (value / target) * 100) : 0;
  return <div style={{ margin: '8px 0' }}>
    <div style={{ ...ROW, padding: 0 }}><span style={MUTED}>{label}</span><span>{n(value)} / {n(target)}</span></div>
    <div role="progressbar" aria-label={label} aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}
      style={{ height: 6, background: '#263750', borderRadius: 4, overflow: 'hidden', marginTop: 4 }}>
      <div style={{ width: `${pct}%`, height: '100%', background: '#38bdf8' }} />
    </div>
  </div>;
}

// collapsible: ogni blocco diventa una sezione espandibile (chiusa), con lo stesso contenuto. Default: invariato.
function Sect({ label, title, collapsible, children }) {
  if (!collapsible) return <section style={BLOCK} aria-label={label}>
    <h2 style={{ fontSize: 17, marginTop: 0 }}>{title}</h2>{children}</section>;
  return <details style={BLOCK} aria-label={label}>
    <summary style={{ fontSize: 15, fontWeight: 700, cursor: 'pointer', color: '#cbd5e1' }}>{title}</summary>
    <div style={{ marginTop: 10 }}>{children}</div></details>;
}

export default function BrainMemorySection({ memory, collapsible = false }) {
  if (!memory || memory.state === 'unavailable') {
    return <Sect label="Memoria Brain" title="🗂️ Memoria e apprendimento" collapsible={collapsible}>
      <p style={MUTED}>Memoria non disponibile in questo momento. Le altre sezioni restano valide.</p>
    </Sect>;
  }
  if (memory.state === 'not_started') {
    return <Sect label="Memoria Brain" title="🗂️ Memoria e apprendimento" collapsible={collapsible}>
      <p style={MUTED}>Brain non ancora avviato: nessuna decisione registrata.</p>
    </Sect>;
  }
  const m = memory.memory || {};
  const t = memory.theses || {};
  const l = memory.learning || {};
  const recent = memory.recent || [];
  const chainBroken = m.chain_ok === false;
  return <>
    <Sect label="Memoria Brain" title="🗂️ Memoria decisionale" collapsible={collapsible}>
      {chainBroken && <p role="alert" style={{ ...MUTED, color: '#fb7185' }}>
        Catena del registro non integra: nessuna decisione è considerata tracciata finché non viene verificata.</p>}
      <Row label="Decisioni registrate">{n(m.decisions)}</Row>
      <Row label="Tracciate correttamente">{n(m.valid_links)} {m.coverage_pct != null ? `(${m.coverage_pct}%)` : ''}</Row>
      <Row label="Senza snapshot">{n(m.missing)}</Row>
      <Row label="Snapshot non validi">{n(m.invalid)}</Row>
      <Row label="Decisioni “nessun trade” conservate">{n(m.no_trade)}</Row>
      <Row label="Aperture senza traccia valida">
        <span style={{ color: m.untraced_opens > 0 ? '#fbbf24' : undefined }}>{n(m.untraced_opens)}</span></Row>
      <Row label="Decisioni duplicate nello stesso slot">
        {m.duplicate_slot_decisions == null ? <span style={MUTED}>non verificabile</span>
          : <span style={{ color: m.duplicate_slot_decisions > 0 ? '#fbbf24' : undefined }}>{n(m.duplicate_slot_decisions)}</span>}</Row>
      <p style={MUTED}>Conta solo i collegamenti verificati (hash, ordine, coerenza), non le semplici associazioni.</p>
      <h3 style={{ fontSize: 14, margin: '14px 0 6px' }}>Ultime decisioni</h3>
      {recent.map((d, i) => <div key={`${d.ts_ms}-${d.symbol}-${i}`} style={{ borderTop: '1px solid #314357', padding: '7px 0', fontSize: 13 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
          <strong>{d.symbol || '—'} · {own(KIND_TEXT, d.kind) || '—'}</strong>
          <span style={{ ...MUTED, color: d.link === 'valid' ? '#34d399' : '#fbbf24' }}>{linkText(d.link)}</span>
        </div>
        <div style={MUTED}>{own(STATUS_TEXT, d.status) || '—'} · {when(d.ts_ms)}
          {d.reentry_index ? ` · tesi: ingresso n. ${d.reentry_index}` : ''}
          {d.would_block ? ' · in osservazione: verrebbe bloccato' : ''}</div>
      </div>)}
      {!recent.length && <p style={MUTED}>Nessuna decisione ancora registrata.</p>}
    </Sect>
    <Sect label="Tesi e reingressi" title="🔁 Tesi e reingressi" collapsible={collapsible}>
      <Row label="Modalità anti-reingresso">{t.enforce_active ? 'Blocco attivo' : t.mode === 'observe' ? 'Solo osservazione' : 'Non attiva'}</Row>
      <Row label="Aperture con tesi">{n(t.opens_with_thesis)}</Row>
      <Row label="Tesi distinte">{n(t.distinct_theses)}</Row>
      <Row label="Reingressi">{n(t.reentries)}</Row>
      <Row label="Che sarebbero stati bloccati">{n(t.would_block)}</Row>
      {Object.entries(t.rules || {}).map(([rule, count]) => <Row key={rule} label={`· ${own(RULE_TEXT, rule) || 'altra regola'}`}>{n(count)}</Row>)}
      <p style={MUTED}>In osservazione nulla viene bloccato: il blocco richiede i risultati E0 e l’approvazione del proprietario.</p>
    </Sect>
    <Sect label="Raccolta per l’apprendimento" title="🎓 Apprendimento" collapsible={collapsible}>
      <Progress label="Esempi tracciati (soglia shadow)" value={l.valid_examples_collected} target={l.shadow_threshold?.examples} />
      <Progress label="Giorni distinti (soglia shadow)" value={l.distinct_days} target={l.shadow_threshold?.days} />
      <Row label="Soglia per valutare una promozione">{n(l.promotion_review_threshold?.examples)} esempi · {n(l.promotion_review_threshold?.days)} giorni</Row>
      <Row label="Addestramento autorizzato">{l.training_authorized === true ? 'Sì' : 'No'}</Row>
      <Row label="Modello appreso attivo">{l.model_active === true ? 'Sì' : 'No'}</Row>
      <p style={MUTED}>È l’avanzamento della raccolta: i dati diventano utilizzabili solo dopo la verifica indipendente
        nel Dataset Builder (candele attestate, registro attestato). Le perdite restano nello storico e non entrano
        automaticamente nell’addestramento.</p>
    </Sect>
  </>;
}
