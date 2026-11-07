/** Controls for closing PAPER positions from Overview; no live order execution. */
import React, { useEffect, useRef, useState } from 'react';
import API, { deskAPI, bullAPI } from '../api';
import { closePositionRequest } from './LiveParts';

const BTN = { border: '1px solid #fda4af', color: '#fecdd3', borderRadius: 8, padding: '7px 10px', background: '#462230', cursor: 'pointer', fontSize: 12 };
const MUTED = { color: '#a8bacd', fontSize: 12 };

// nameOf traduce l'identificativo tecnico di una posizione in un nome leggibile (il simbolo).
export function closeResultMessages(result, nameOf = id => id) {
  if (!result) return [];
  if (result.status === 'expired') return ['La richiesta è scaduta: riprova.'];
  if (result.status === 'invalid_request') return ['Richiesta non valida: riprova.'];
  const notes = (result.closed || []).map(id => `${nameOf(id)}: posizione chiusa.`);
  for (const [id, code] of result.failed || []) {
    if (code === 'position_already_closed' || code === 'position_not_open') {
      notes.push(`${nameOf(id)}: posizione già chiusa.`);
    } else if (code === 'price_unavailable' || code === 'invalid_exit_price') {
      notes.push(`${nameOf(id)}: prezzo non disponibile, riprova.`);
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

/** Shared position facts for Falco, Toro and Brain. No invented mark, PnL or target. */
export function PortfolioTradeFields({ p, brain = false }) {
  const pxLabel = brain ? 'Prezzo attuale'
    : p.price_source === 'bot' ? 'Ultimo prezzo bot'
    : p.price_source === 'live' ? 'Prezzo live' : 'Prezzo';
  const pnl = p.price == null || p.unrealized_pnl == null ? null : p.unrealized_pnl;
  const roi = pnl == null || p.roi_pct == null ? '—' : `${p.roi_pct}%`;
  const qty = p.quantity ?? p.qty ?? null;
  const positive = pnl != null && !String(pnl).startsWith('-');
  return <div data-testid={`portfolio-trade-${brain ? 'brain' : 'classic'}`}>
    <strong>{p.symbol} · <span style={{ color: p.side === 1 ? '#4ade80' : '#fda4af' }}>
      {p.side === 1 ? 'LONG' : p.side === -1 ? 'SHORT' : '—'}</span> · {p.leverage ?? '—'}×</strong>
    {(p.trade_type || p.strategy_id) && <span style={{ display:'block', ...MUTED }}>
      {brain ? 'Strategia' : 'Tipo'}: {brain ? p.strategy_id || 'Non dichiarata' : p.trade_type || '—'}</span>}
    <div style={{ ...MUTED, marginTop: 6 }}>Ingresso {p.entry ?? '—'} · {pxLabel} {p.price ?? '—'}</div>
    {p.price == null && <div style={MUTED}>Prezzo aggiornato non disponibile.</div>}
    <div style={MUTED}>Margine {p.margin ?? '—'} USDT · Stop {p.stop ?? '—'}</div>
    <div style={MUTED}>Obiettivo {p.take_profit ?? '—'} · Liquidazione {p.liquidation ?? '—'}</div>
    {qty != null && <div style={MUTED}>Quantità {qty}</div>}
    <div style={{ fontSize: 13, fontWeight: 700, color: pnl == null ? '#a8bacd' : positive ? '#4ade80' : '#fda4af' }}>
      {brain ? 'P&L non realizzato:' : 'P&L'} {pnl == null ? '—' : `${pnl} USDT`} · ROI {roi}
    </div>
  </div>;
}

export function BrainCloseControls({ positions = [], serverPending = false, onRefresh = () => {}, renderPosition = null }) {
  const [confirm, setConfirm] = useState(null);
  const [pending, setPending] = useState(null);
  const [sending, setSending] = useState(false);
  const [notes, setNotes] = useState([]);
  const [problem, setProblem] = useState('');
  const active = useRef(false);
  const positionsRef = useRef(positions);
  positionsRef.current = positions;
  // Simboli delle posizioni al momento del clic: la pagina si aggiorna ogni 30 s e la posizione chiusa sparisce dall'elenco.
  const namesRef = useRef({});
  const refreshRef = useRef(onRefresh);
  refreshRef.current = onRefresh;

  const submit = async () => {
    if (active.current || !confirm) return;
    active.current = true;
    setSending(true);
    setProblem('');
    setNotes([]);
    const payload = confirm.all ? { all: true } : { position_id: confirm.position_id };
    namesRef.current = Object.fromEntries(positionsRef.current.map(p => [p.position_id, p.symbol]));
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
          setNotes(closeResultMessages(result, id => namesRef.current[id] || 'Posizione'));
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
    {positions.map(p => <div key={p.position_id} style={{ display: 'flex', gap: 10, alignItems: 'center', borderTop: '1px solid #314357', padding: '12px 0', minWidth: 0 }}>
      <div style={{ minWidth: 0, flex: 1 }}>{renderPosition ? renderPosition(p) : <PortfolioTradeFields p={p} brain />}</div>
      <button type="button" style={{ ...BTN, flexShrink: 0 }} disabled={disabled} onClick={() => ask({ position_id: p.position_id, symbol: p.symbol })}>Chiudi {p.symbol}</button>
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

export function ClassicCloseControls({ portfolio, positions = [], canClose = false, pending = [],
  allPending = false, lastAction = null, onRefresh = () => {} }) {
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [awaiting, setAwaiting] = useState(null);
  const locked = useRef(false);
  const refreshRef = useRef(onRefresh);
  refreshRef.current = onRefresh;

  useEffect(() => {
    if (!awaiting) return undefined;
    let active = true;
    let polling = false;
    const poll = async () => {
      if (!active || polling) return;
      if (Date.now() - awaiting.at_ms >= 60000) {
        setMessage('Nessuna conferma di chiusura ricevuta: aggiorna lo stato del portafoglio.');
        setAwaiting(null);
        return;
      }
      polling = true;
      try {
        const { data } = await API.get('/api/v3/overview');
        const portfolioData = (data?.portfolios || []).find(p => p.id === portfolio);
        const action = portfolioData?.last_action;
        if (active && action?.type === awaiting.type &&
            Number.isFinite(Number(action.ts)) && Number(action.ts) >= awaiting.at_ms) {
          setMessage(action.ok
            ? ('Chiusura PAPER confermata: ' + (action.detail || 'operazione registrata.'))
            : ('Chiusura NON eseguita: ' + (action.detail || 'controlla il bot.')));
          setAwaiting(null);
          refreshRef.current();
        }
      } catch (_) {
        // Network errors are retried for up to one minute: never invent success.
      } finally {
        polling = false;
      }
    };
    const timer = setInterval(poll, 3000);
    return () => { active = false; clearInterval(timer); };
  }, [awaiting, portfolio]);

  const blocked = busy || !!pending.length || allPending || !!awaiting;
  const result = (lastAction && ['close_all', 'close_position'].includes(lastAction.type))
    ? lastAction : null;
  if (!positions.length) return <div>
    <p style={MUTED}>Nessuna posizione aperta.</p>
    {result && <p role="status" style={{ ...MUTED, color: result.ok ? '#4ade80' : '#fda4af' }}>
      Ultima chiusura: {result.detail || (result.ok ? 'eseguita' : 'non eseguita')}</p>}
  </div>;
  const send = async () => {
    if (locked.current || !confirm) return;
    locked.current = true;
    setBusy(true);
    setMessage('');
    const initiatedAt = Date.now(); // before POST: a fast worker can finish before HTTP returns
    try {
      let r;
      if (confirm.all) {
        const api = portfolio === 'toro' ? bullAPI : deskAPI;
        const { data } = await api.closeAll();
        r = { ok: data?.ok === true && data?.queued === true,
          message: data?.message || 'Il bot non ha confermato la presa in carico.' };
      } else {
        r = await closePositionRequest(portfolio === 'toro' ? 'bull' : 'hawk', confirm.symbol);
      }
      setMessage(r.ok ? 'Richiesta inviata, attendo conferma della chiusura PAPER.'
        : (r.message || 'Chiusura non riuscita.'));
      if (r.ok) {
        setAwaiting({ type: confirm.all ? 'close_all' : 'close_position', at_ms: initiatedAt });
        onRefresh();
      }
    } catch (error) {
      setMessage(error?.response?.status === 409
        ? 'Il bot non risponde: nessuna chiusura inviata. Serve il processo PAPER di chiusura attivo.'
        : 'Chiusura non riuscita. Verifica il bot e riprova.');
    } finally {
      locked.current = false;
      setBusy(false);
      setConfirm(null);
    }
  };
  return <div style={{ marginTop: 8 }}>
    {!canClose && <p style={MUTED}>Chiusura manuale non ancora disponibile su questo bot (processo spento oppure versione precedente). Le posizioni restano visibili: nessun comando viene accodato.</p>}
    {canClose && <button type="button" style={BTN} disabled={blocked} onClick={() => setConfirm({ all: true })}>Chiudi tutte ({positions.length})</button>}
    {positions.map(p => <div key={p.symbol} style={{ background:'#0e1a2d', padding:'12px', border:'1px solid #30465e', borderRadius:11, marginTop:9 }}>
      <PortfolioTradeFields p={p} />
      {canClose && <button type="button" style={{ ...BTN, marginTop:8 }} disabled={blocked}
        onClick={() => setConfirm({ symbol: p.symbol })}>Chiudi {p.symbol}</button>}
    </div>)}
    {canClose && confirm && <div role="dialog" aria-label={`Conferma chiusura ${portfolio}`} style={{ padding: 10, border: '1px solid #fda4af', borderRadius: 8 }}>
      <p>{confirm.all ? `Chiudere tutte le ${positions.length} posizioni di ${portfolio}?` : `Chiudere ${confirm.symbol} adesso a prezzo di mercato?`}</p>
      <button type="button" style={BTN} onClick={send} disabled={busy}>Chiudi</button>{' '}
      <button type="button" style={{ ...BTN, background: 'transparent' }} disabled={busy} onClick={() => setConfirm(null)}>Annulla</button>
    </div>}
    {(!!pending.length || allPending || !!awaiting) &&
      <p style={MUTED}>Chiusura in corso: aspetto la registrazione del risultato.</p>}
    {message && <p role="status" style={MUTED}>{message}</p>}
    {result && <p role="status" style={{ ...MUTED, color: result.ok ? '#4ade80' : '#fda4af' }}>
      Ultima chiusura: {result.detail || (result.ok ? 'eseguita' : 'non eseguita')}</p>}
  </div>;
}
