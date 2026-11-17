/** Chiusura manuale PAPER di UNA posizione di UNA AI dell'Arena, con conferma e motivazione facoltativa. */
import React, { useEffect, useRef, useState } from 'react';
import API from '../api';
import { CLOSE_REASONS, NOTE_MAX, arenaErrorText, newRequestId, statusText, validNote } from '../arenaCloseModel';

const BTN = { border: '1px solid #fda4af', color: '#fecdd3', borderRadius: 8, padding: '7px 10px', background: '#462230', cursor: 'pointer', fontSize: 12 };
const SOFT = { ...BTN, borderColor: '#456079', color: '#e2e8f0', background: '#172338' };
const MUTED = { color: '#a8bacd', fontSize: 12 };
const POLL_MS = 3000;
const MAX_POLLS = 260;              // ~13 minuti: oltre, il backend risponde "unconfirmed"

function ReasonForm({ provider, requestId, onSaved }) {
  const [reason, setReason] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const save = async () => {
    if (!reason || !validNote(note)) return;
    setBusy(true); setError(null);
    try {
      const body = note.trim() ? { reason, note } : { reason };
      const r = await API.post(`/api/v3/arena/${provider}/close/${requestId}/annotation`, body);
      onSaved(r.data.annotation);
    } catch (err) { setError(arenaErrorText(err)); } finally { setBusy(false); }
  };
  return <fieldset style={{ border: '1px solid #30465e', borderRadius: 10, padding: 10, marginTop: 8 }}>
    <legend style={MUTED}>Perché hai chiuso? (facoltativo, una sola volta)</legend>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
      {CLOSE_REASONS.map(r => <label key={r.id} style={{ ...MUTED, display: 'flex', gap: 4, alignItems: 'center' }}>
        <input type="radio" name={`reason-${requestId}`} value={r.id} checked={reason === r.id}
          onChange={() => setReason(r.id)}/>{r.label}
      </label>)}
    </div>
    <input aria-label="Nota facoltativa" value={note} maxLength={NOTE_MAX} placeholder="Nota (facoltativa)"
      onChange={e => setNote(e.target.value)}
      style={{ width: '100%', boxSizing: 'border-box', marginTop: 8, padding: 7, borderRadius: 8, border: '1px solid #456079', background: '#0e1a2d', color: '#eef5ff' }}/>
    <button style={{ ...SOFT, marginTop: 8 }} disabled={busy || !reason || !validNote(note)} onClick={save}>
      Registra motivazione
    </button>
    {error && <div role="alert" style={{ color: '#fda4af', fontSize: 12, marginTop: 6 }}>{error}</div>}
  </fieldset>;
}

function PositionClose({ provider, position, ready, renderPosition, onDone, annotated, onSent }) {
  const [confirming, setConfirming] = useState(false);
  const [requestId, setRequestId] = useState(null);
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(null);
  const polls = useRef(0);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;
  useEffect(() => {
    if (!requestId || state?.terminal) return undefined;
    let alive = true;
    const timer = setTimeout(async () => {
      polls.current += 1;
      try {
        const r = await API.get(`/api/v3/arena/${provider}/close/${requestId}`);
        if (alive) {
          setState(r.data);
          if (r.data.terminal && doneRef.current) doneRef.current();
        }
      } catch (err) {
        if (alive) setError(arenaErrorText(err));
      }
      if (alive && polls.current >= MAX_POLLS) setError('Nessuna conferma ricevuta: verifica lo stato prima di riprovare.');
    }, POLL_MS);
    return () => { alive = false; clearTimeout(timer); };
  }, [provider, requestId, state]);

  const send = async () => {
    const id = requestId || newRequestId();        // stesso id se si ripete: il backend non duplica
    setRequestId(id); setError(null);
    try {
      const r = await API.post(`/api/v3/arena/${provider}/close`, { position_id: position.position_id, request_id: id });
      setState(r.data); setConfirming(false); onSent(position);
    } catch (err) { setError(arenaErrorText(err)); }
  };
  const label = `${position.symbol || 'posizione'}`;
  const text = statusText(state);
  return <div>
    {renderPosition(position)}
    {!requestId && !confirming && <button style={BTN} disabled={!ready} onClick={() => setConfirming(true)}>
      Chiudi {label}
    </button>}
    {confirming && <div role="dialog" aria-label={`Conferma chiusura ${label}`} style={{ ...MUTED, marginTop: 6 }}>
      Chiudere in PAPER {label} al prossimo prezzo disponibile? Nessun ordine reale.
      <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
        <button style={BTN} onClick={send}>Conferma chiusura</button>
        <button style={SOFT} onClick={() => setConfirming(false)}>Annulla</button>
      </div>
    </div>}
    {text && <div role="status" style={{ ...MUTED, marginTop: 6 }}>{text}</div>}
    {error && <div role="alert" style={{ color: '#fda4af', fontSize: 12, marginTop: 6 }}>{error}</div>}
    {state?.status === 'closed' && !saved && !annotated &&
      <ReasonForm provider={provider} requestId={requestId} onSaved={setSaved}/>}
    {(saved || annotated) && <div role="status" style={{ ...MUTED, marginTop: 6 }}>Motivazione registrata.</div>}
  </div>;
}

export default function ArenaCloseControls({ provider, positions, ready, annotations = [], onRefresh, renderPosition }) {
  // Una posizione con richiesta inviata resta visibile anche dopo la chiusura, per mostrare l'esito e chiedere il motivo.
  const [tracked, setTracked] = useState({});
  const done = new Set(annotations.map(a => a.position_id));
  const openIds = new Set(positions.map(p => p.position_id));
  const shownList = positions.concat(Object.values(tracked).filter(p => !openIds.has(p.position_id)));
  return <section>
    {!ready && <div role="status" style={{ ...MUTED, padding: 9 }}>
      Chiusura manuale non disponibile: il servizio di uscita PAPER di questa AI non è attivo.
    </div>}
    {shownList.map((p, i) => <PositionClose key={p.position_id || i} provider={provider} position={p}
      ready={ready === true && typeof p.position_id === 'string'} renderPosition={renderPosition}
      onDone={onRefresh} annotated={done.has(p.position_id)}
      onSent={pos => setTracked(t => ({ ...t, [pos.position_id]: pos }))}/>)}
  </section>;
}
