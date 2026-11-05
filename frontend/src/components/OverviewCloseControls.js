/** Controls for closing PAPER positions from Overview; no live order execution. */
import React, { useEffect, useRef, useState } from 'react';
import API, { deskAPI, bullAPI } from '../api';
import { closePositionRequest } from './LiveParts';

const BTN = { border: '1px solid #fda4af', color: '#fecdd3', borderRadius: 8, padding: '7px 10px', background: '#462230', cursor: 'pointer', fontSize: 12 };
const MUTED = { color: '#a8bacd', fontSize: 12 };

export function closeResultMessages(result) {
  if (!result) return [];
  if (result.status === 'expired') return ['La richiesta è scaduta: riprova.'];
  if (result.status === 'invalid_request') return ['Richiesta non valida: riprova.'];
  const notes = (result.closed || []).map(id => `${id}: posizione chiusa.`);
  for (const [id, code] of result.failed || []) {
    if (code === 'position_already_closed' || code === 'position_not_open') {
      notes.push(`${id}: posizione già chiusa.`);
    } else if (code === 'price_unavailable' || code === 'invalid_exit_price') {
      notes.push(`${id}: prezzo non disponibile, riprova.`);
    } else {
      notes.push('Impossibile completare una chiusura. Verifica lo stato del Brain e riprova.');
    }
  }
  return notes.length ? notes : ['Nessuna posizione chiusa. Verifica il Brain e riprova.'];
}

const brainErrorText = err => {
  const code = err?.response?.data?.detail?.code;
  return ({ brain_non_risponde: 'Il Brain non risponde. Riprova più tardi.',
    posizione_non_aperta: 'Questa posizione non è più aperta.',
    nessuna_posizione: 'Non ci sono posizioni aperte.',
    richiesta_in_corso: 'Una richiesta di chiusura è già in corso.',
    richiesta_non_valida: 'Richiesta non valida. Aggiorna la pagina.' })[code] || 'Invio non riuscito. Riprova.';
};

export function BrainCloseControls({ positions = [], serverPending = false, onRefresh = () => {} }) {
  const [confirm, setConfirm] = useState(null);
  const [pending, setPending] = useState(null);
  const [sending, setSending] = useState(false);
  const [notes, setNotes] = useState([]);
  const [problem, setProblem] = useState('');
  const active = useRef(false);
  const positionsRef = useRef(positions);
  positionsRef.current = positions;
  const refreshRef = useRef(onRefresh);
  refreshRef.current = onRefresh;

  const submit = async () => {
    if (active.current || !confirm) return;
    active.current = true;
    setSending(true);
    setProblem('');
    setNotes([]);
    const payload = confirm.all ? { all: true } : { position_id: confirm.position_id };
    try {
      const { data } = await API.post('/api/v3/brain/close', payload);
      setPending({ ts_ms: data.ts_ms, at_ms: Date.now() });
      setConfirm(null);
    } catch (err) {
      setProblem(brainErrorText(err));
      active.current = false;
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    if (!pending) return undefined;
    let alive = true;
    let polling = false;
    const tick = async () => {
      if (!alive) return;
      if (Date.now() - pending.at_ms >= 60000) {
        setProblem('Il Brain non risponde: controlla la connessione o riprova.');
        setPending(null);
        active.current = false;
        return;
      }
      if (polling) return;
      polling = true;
      try {
        const { data } = await API.get('/api/v3/brain/close-result');
        const result = data?.result;
        if (alive && !data?.pending && result?.request_ts_ms === pending.ts_ms) {
          setNotes(closeResultMessages(result));
          setPending(null);
          active.current = false;
          refreshRef.current();
        }
      } catch (_) {
        // Transient network errors are retried until the 60-second deadline.
      } finally {
        polling = false;
      }
    };
    const timer = setInterval(tick, 3000);
    return () => { alive = false; clearInterval(timer); };
  }, [pending]);

  const ask = target => {
    if (!active.current && !sending && !serverPending) { setNotes([]); setProblem(''); setConfirm(target); }
  };
  const disabled = active.current || sending || serverPending;
  return <div>
    {positions.length > 0 && <div style={{ marginBottom: 10, display: 'flex', justifyContent: 'flex-end' }}>
      <button type="button" style={BTN} disabled={disabled} onClick={() => ask({ all: true })}>Chiudi tutte ({positions.length})</button>
    </div>}
    {positions.map(p => <div key={p.position_id} style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 10 }}>
      <button type="button" style={BTN} disabled={disabled} onClick={() => ask({ position_id: p.position_id, symbol: p.symbol })}>Chiudi {p.symbol}</button>
    </div>)}
    {confirm && <div role="dialog" aria-label="Conferma chiusura Brain" style={{ border: '1px solid #fda4af', padding: 12, borderRadius: 10, marginTop: 8 }}>
      <p style={{ margin: '0 0 10px' }}>{confirm.all
        ? `Chiudere tutte le ${positions.length} posizioni aperte del Brain a prezzo di mercato?`
        : `Chiudere ${confirm.symbol} adesso a prezzo di mercato?`}</p>
      <p style={MUTED}>Operazione PAPER, nessun ordine reale su Bitget.</p>
      <button type="button" style={BTN} onClick={submit} disabled={sending}>Chiudi</button>{' '}
      <button type="button" style={{ ...BTN, background: 'transparent' }} onClick={() => setConfirm(null)} disabled={sending}>Annulla</button>
    </div>}
    {pending && <div role="status" style={MUTED}>Richiesta inviata… controllo la risposta del Brain.</div>}
    {!pending && serverPending && <div role="status" style={MUTED}>Una richiesta di chiusura è già in corso.</div>}
    {problem && <p role="alert" style={{ color: '#fda4af', fontSize: 12 }}>{problem}</p>}
    {notes.map((note, i) => <p key={`${i}-${note}`} role="status" style={MUTED}>{note}</p>)}
  </div>;
}

export function ClassicCloseControls({ portfolio, positions = [], canClose = false, pending = [], onRefresh = () => {} }) {
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const locked = useRef(false);
  if (!positions.length) return null;
  if (!canClose) return <p style={MUTED}>Chiusura manuale non ancora disponibile su questo bot.</p>;
  const send = async () => {
    if (locked.current || !confirm) return;
    locked.current = true;
    setBusy(true);
    setMessage('');
    try {
      let r;
      if (confirm.all) {
        const api = portfolio === 'toro' ? bullAPI : deskAPI;
        await api.closeAll();
        r = { ok: true, message: 'Richiesta di chiusura totale inviata.' };
      } else {
        r = await closePositionRequest(portfolio === 'toro' ? 'bull' : 'hawk', confirm.symbol);
      }
      setMessage(r.ok ? 'Richiesta inviata. Il bot sta elaborando la chiusura.' : (r.message || 'Chiusura non riuscita.'));
      if (r.ok) onRefresh();
    } catch (_) {
      setMessage('Chiusura non riuscita. Verifica il bot e riprova.');
    } finally {
      locked.current = false;
      setBusy(false);
      setConfirm(null);
    }
  };
  return <div style={{ marginTop: 8 }}>
    <button type="button" style={BTN} disabled={busy || !!pending.length} onClick={() => setConfirm({ all: true })}>Chiudi tutte ({positions.length})</button>
    {positions.map(p => <div key={p.symbol} style={{ padding: '8px 0', borderBottom: '1px solid #30405b' }}>
      <span>{p.symbol} · {p.side === 1 ? 'LONG' : 'SHORT'} · {p.leverage || '—'}×</span>
      <span style={{ display: 'block', ...MUTED }}>Ingresso {p.entry} · Stop {p.stop ?? '—'} · P&L {p.unrealized_pnl}</span>
      <button type="button" style={{ ...BTN, marginTop: 6 }} disabled={busy || !!pending.length}
        onClick={() => setConfirm({ symbol: p.symbol })}>Chiudi {p.symbol}</button>
    </div>)}
    {confirm && <div role="dialog" aria-label={`Conferma chiusura ${portfolio}`} style={{ padding: 10, border: '1px solid #fda4af', borderRadius: 8 }}>
      <p>{confirm.all ? `Chiudere tutte le ${positions.length} posizioni di ${portfolio}?` : `Chiudere ${confirm.symbol} adesso a prezzo di mercato?`}</p>
      <button type="button" style={BTN} onClick={send} disabled={busy}>Chiudi</button>{' '}
      <button type="button" style={{ ...BTN, background: 'transparent' }} disabled={busy} onClick={() => setConfirm(null)}>Annulla</button>
    </div>}
    {!!pending.length && <p style={MUTED}>Chiusura in corso: elaborazione dal bot.</p>}
    {message && <p role="status" style={MUTED}>{message}</p>}
  </div>;
}
