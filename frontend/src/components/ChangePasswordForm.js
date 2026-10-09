import React, { useState } from 'react';
import { botAPI } from '../api';

const MIN_LEN = 10;

const inputStyle = {
  width: '100%', padding: '12px 14px', borderRadius: '10px', boxSizing: 'border-box',
  border: '1px solid #334155', background: '#0f172a', color: '#f1f5f9',
  fontSize: '16px', marginBottom: '10px', outline: 'none',
};

/**
 * Form di cambio password, usato in tre casi:
 *  - primo accesso / password scaduta, subito dopo il login (askOld=false:
 *    la password attuale e' quella appena digitata, passata in `knownOld`)
 *  - password scaduta con login biometrico (askOld=true: non l'abbiamo digitata)
 *  - cambio volontario da Impostazioni (askOld=true)
 * `token` e' il token limitato del login (solo per i primi due casi);
 * onSuccess riceve il nuovo token completo.
 */
export default function ChangePasswordForm({ askOld, knownOld = '', token, onSuccess, onCancel }) {
  const [oldPwd, setOldPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const current = askOld ? oldPwd : knownOld;

  const localError = () => {
    if (askOld && !oldPwd) return 'Inserisci la password attuale';
    if (newPwd.length < MIN_LEN) return `La nuova password deve avere almeno ${MIN_LEN} caratteri`;
    if (newPwd === current) return 'La nuova password deve essere diversa dall\'attuale';
    if (newPwd !== confirm) return 'Le due password non coincidono';
    return '';
  };

  const submit = async () => {
    const problem = localError();
    if (problem) { setError(problem); return; }
    setBusy(true); setError('');
    try {
      const { data } = await botAPI.changePassword(current, newPwd, token);
      onSuccess(data.token);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Cambio password non riuscito, riprova.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      {askOld && (
        <input type="password" autoComplete="current-password" placeholder="Password attuale"
          value={oldPwd} onChange={e => setOldPwd(e.target.value)} style={inputStyle} />
      )}
      <input type="password" autoComplete="new-password" placeholder={`Nuova password (min. ${MIN_LEN} caratteri)`}
        value={newPwd} onChange={e => setNewPwd(e.target.value)} style={inputStyle} />
      <input type="password" autoComplete="new-password" placeholder="Ripeti la nuova password"
        value={confirm} onChange={e => setConfirm(e.target.value)}
        onKeyDown={e => e.key === 'Enter' && submit()} style={inputStyle} />
      {error && <p style={{ color: '#f87171', fontSize: '13px', margin: '0 0 10px' }}>{error}</p>}
      <div style={{ display: 'flex', gap: '8px' }}>
        <button onClick={submit} disabled={busy} style={{
          flex: 1, padding: '12px', borderRadius: '10px', border: 'none',
          background: busy ? '#334155' : '#0ea5e9', color: 'white', fontWeight: 'bold',
          cursor: busy ? 'not-allowed' : 'pointer',
        }}>{busy ? '...' : 'Salva nuova password'}</button>
        {onCancel && (
          <button onClick={onCancel} disabled={busy} style={{
            padding: '12px 16px', borderRadius: '10px', background: 'none',
            color: '#94a3b8', border: '1px solid #334155', cursor: 'pointer',
          }}>Annulla</button>
        )}
      </div>
    </div>
  );
}
