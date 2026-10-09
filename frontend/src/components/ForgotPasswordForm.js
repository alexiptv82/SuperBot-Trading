import React, { useState } from 'react';
import { botAPI } from '../api';
import PasswordInput from './PasswordInput';

const MIN_LEN = 10;
const CODE_LEN = 8;

const inputStyle = {
  width: '100%', padding: '12px 14px', borderRadius: '10px', boxSizing: 'border-box',
  border: '1px solid #334155', background: '#0f172a', color: '#f1f5f9',
  fontSize: '16px', marginBottom: '10px', outline: 'none',
};

const primaryBtn = (busy) => ({
  flex: 1, padding: '12px', borderRadius: '10px', border: 'none',
  background: busy ? '#334155' : '#0ea5e9', color: 'white', fontWeight: 'bold',
  cursor: busy ? 'not-allowed' : 'pointer',
});

const ghostBtn = {
  padding: '12px 16px', borderRadius: '10px', background: 'none',
  color: '#94a3b8', border: '1px solid #334155', cursor: 'pointer',
};

const errorText = (e, fallback) => {
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (!e?.response) return 'Impossibile contattare il server. Controlla la connessione e riprova.';
  return fallback;
};

/**
 * Password dimenticata, in due passi:
 *  1. "Invia codice": il server manda un codice a 8 cifre sul Telegram del
 *     proprietario (il codice non passa mai da qui).
 *  2. Si inserisce il codice e si sceglie la nuova password; il server
 *     risponde con una sessione completa (onSuccess riceve il token).
 */
export default function ForgotPasswordForm({ onSuccess, onCancel }) {
  const [step, setStep] = useState('request');
  const [code, setCode] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [busy, setBusy] = useState(false);

  const sendCode = async () => {
    setBusy(true); setError(''); setInfo('');
    try {
      await botAPI.forgotPassword();
      setStep('confirm');
      setInfo('Codice inviato su Telegram. Vale 10 minuti.');
    } catch (e) {
      setError(errorText(e, 'Non sono riuscito a inviare il codice, riprova.'));
    } finally {
      setBusy(false);
    }
  };

  const localError = () => {
    if (code.length !== CODE_LEN) return `Il codice ha ${CODE_LEN} cifre`;
    if (newPwd.length < MIN_LEN) return `La nuova password deve avere almeno ${MIN_LEN} caratteri`;
    if (newPwd !== confirm) return 'Le due password non coincidono';
    return '';
  };

  const submit = async () => {
    const problem = localError();
    if (problem) { setError(problem); return; }
    setBusy(true); setError(''); setInfo('');
    try {
      const { data } = await botAPI.forgotPasswordConfirm(code, newPwd);
      onSuccess(data.token);
    } catch (e) {
      setError(errorText(e, 'Recupero non riuscito, riprova.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      {step === 'request' && (
        <>
          <p style={{ marginBottom: '14px', fontSize: '14px', lineHeight: 1.4 }}>
            Ti mando un codice a {CODE_LEN} cifre sul tuo Telegram. Con quel codice scegli una nuova password.
          </p>
          {error && <p style={{ color: '#f87171', fontSize: '13px', margin: '0 0 10px' }}>{error}</p>}
          <div style={{ display: 'flex', gap: '8px' }}>
            <button onClick={sendCode} disabled={busy} style={primaryBtn(busy)}>
              {busy ? '...' : 'Invia codice su Telegram'}
            </button>
            <button onClick={onCancel} disabled={busy} style={ghostBtn}>Indietro</button>
          </div>
        </>
      )}

      {step === 'confirm' && (
        <>
          {info && <p style={{ color: '#4ade80', fontSize: '13px', margin: '0 0 10px' }}>{info}</p>}
          <input
            type="text" inputMode="numeric" autoComplete="one-time-code" maxLength={CODE_LEN}
            placeholder={`Codice (${CODE_LEN} cifre)`} value={code}
            onChange={e => setCode(e.target.value.replace(/\D/g, ''))}
            style={inputStyle}
          />
          <PasswordInput autoComplete="new-password" placeholder={`Nuova password (min. ${MIN_LEN} caratteri)`}
            value={newPwd} onChange={e => setNewPwd(e.target.value)} style={inputStyle} />
          <PasswordInput autoComplete="new-password" placeholder="Ripeti la nuova password"
            value={confirm} onChange={e => setConfirm(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()} style={inputStyle} />
          {error && <p style={{ color: '#f87171', fontSize: '13px', margin: '0 0 10px' }}>{error}</p>}
          <div style={{ display: 'flex', gap: '8px', marginBottom: '10px' }}>
            <button onClick={submit} disabled={busy} style={primaryBtn(busy)}>
              {busy ? '...' : 'Imposta nuova password'}
            </button>
            <button onClick={onCancel} disabled={busy} style={ghostBtn}>Annulla</button>
          </div>
          <button onClick={sendCode} disabled={busy} style={{
            background: 'none', border: 'none', color: '#38bdf8', fontSize: '13px',
            cursor: 'pointer', padding: 0,
          }}>Non è arrivato? Rimanda il codice</button>
        </>
      )}
    </div>
  );
}
