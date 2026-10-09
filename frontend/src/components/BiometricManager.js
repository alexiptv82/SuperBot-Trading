import React, { useState, useEffect, useCallback } from 'react';
import { botAPI } from '../api';
import {
  isPlatformAuthenticatorAvailable, createCredential, deviceLabel, describeWebAuthnError,
} from '../webauthnClient';

const MUTED = '#94a3b8';
const GOOD = '#4ade80';
const BAD = '#f87171';

const formatDate = (iso) => {
  if (!iso) return '';
  try { return new Date(iso).toLocaleDateString('it-IT', { day: 'numeric', month: 'short', year: 'numeric' }); }
  catch { return ''; }
};

/**
 * Gestione dell'impronta digitale in Impostazioni: elenco dei dispositivi
 * registrati, attivazione su questo dispositivo (anche piu' tardi) e rimozione
 * (telefono cambiato, impronta cambiata, o non la si vuole piu').
 */
export default function BiometricManager({ onChange }) {
  const [creds, setCreds] = useState(null);
  const [platformOk, setPlatformOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null); // { ok, text }

  const load = useCallback(async () => {
    try {
      const [{ data }, ok] = await Promise.all([botAPI.webauthnCredentials(), isPlatformAuthenticatorAvailable()]);
      setCreds(data.credentials || []);
      setPlatformOk(ok);
    } catch {
      setCreds([]);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const add = async () => {
    setBusy(true); setNote(null);
    try {
      const { data: options } = await botAPI.webauthnRegisterOptions();
      const { state_id, credentialJSON } = await createCredential(options);
      await botAPI.webauthnRegisterVerify(state_id, credentialJSON, deviceLabel());
      setNote({ ok: true, text: 'Impronta digitale attivata su questo dispositivo.' });
      await load();
      if (onChange) onChange();
    } catch (e) {
      console.warn('Attivazione impronta fallita:', e);
      setNote({ ok: false, text: describeWebAuthnError(e) });
    } finally {
      setBusy(false);
    }
  };

  const remove = async (c) => {
    if (!window.confirm(`Rimuovere l'impronta di "${c.device_label}"? Su quel dispositivo dovrai usare la password.`)) return;
    setBusy(true); setNote(null);
    try {
      await botAPI.webauthnRemove(c.id);
      setNote({ ok: true, text: 'Impronta rimossa.' });
      await load();
      if (onChange) onChange();
    } catch (e) {
      setNote({ ok: false, text: describeWebAuthnError(e) });
    } finally {
      setBusy(false);
    }
  };

  const list = creds || [];

  return (
    <div>
      <div style={{ fontSize: '13px', color: MUTED, marginBottom: '10px' }}>
        {creds === null ? 'Controllo…'
          : list.length === 0 ? 'Nessuna impronta digitale registrata.'
          : `Impronta attiva su ${list.length} ${list.length === 1 ? 'dispositivo' : 'dispositivi'}:`}
      </div>

      {list.map((c) => (
        <div key={c.id} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px',
          background: '#0f172a', border: '1px solid #334155', borderRadius: '10px',
          padding: '10px 12px', marginBottom: '8px',
        }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: '14px', fontWeight: 'bold', overflow: 'hidden', textOverflow: 'ellipsis' }}>👆 {c.device_label}</div>
            {c.created_at && <div style={{ fontSize: '11px', color: MUTED }}>Attivata il {formatDate(c.created_at)}</div>}
          </div>
          <button onClick={() => remove(c)} disabled={busy} style={{
            background: 'none', border: '1px solid #334155', color: BAD, borderRadius: '8px',
            padding: '6px 10px', fontSize: '12px', cursor: busy ? 'not-allowed' : 'pointer', flexShrink: 0,
          }}>Rimuovi</button>
        </div>
      ))}

      {platformOk ? (
        <button onClick={add} disabled={busy} style={{
          width: '100%', padding: '12px', borderRadius: '10px', border: 'none', marginTop: '4px',
          background: busy ? '#334155' : '#0ea5e9', color: 'white',
          fontWeight: 'bold', cursor: busy ? 'not-allowed' : 'pointer',
        }}>
          {busy ? '...' : '👆 Attiva impronta su questo dispositivo'}
        </button>
      ) : (
        <div style={{ fontSize: '12px', color: '#64748b' }}>
          Questo dispositivo o browser non offre l'impronta digitale (serve un blocco schermo con impronta o volto attivo).
        </div>
      )}
      <div style={{ fontSize: '11px', color: '#64748b', marginTop: '8px' }}>
        Se cambi telefono o impronta: rimuovi la vecchia qui sopra e attivala di nuovo.
      </div>
      {note && <div style={{ fontSize: '12px', color: note.ok ? GOOD : BAD, marginTop: '10px' }}>{note.text}</div>}
    </div>
  );
}
