import React, { useState, useEffect } from 'react';
import { botAPI } from '../api';
import { isPlatformAuthenticatorAvailable, createCredential, getCredential } from '../webauthnClient';
import ChangePasswordForm from '../components/ChangePasswordForm';
import PasswordInput from '../components/PasswordInput';

const panel = {
  background: '#1e293b', border: '1px solid #334155', borderRadius: '12px',
  padding: '16px', marginBottom: '16px', color: '#f1f5f9',
};

// "Password errata" solo se il server risponde davvero 401: prima qualunque
// errore (server irraggiungibile, richiesta bloccata dal browser, 5xx) veniva
// mostrato come password sbagliata, nascondendo il problema vero.
const loginErrorMessage = (e) => {
  const status = e?.response?.status;
  const detail = e?.response?.data?.detail;
  if (status === 401) return 'Password errata';
  if ((status === 429 || status === 503) && typeof detail === 'string') return detail;
  if (!e?.response) return 'Impossibile contattare il server. Controlla la connessione e riprova.';
  return `Errore del server (${status}). Riprova tra poco.`;
};

// Fasi: 'login' -> (eventuale) 'change' -> (eventuale) 'bio' -> app
export default function Login({ onLogin }) {
  const [stage, setStage] = useState('login');
  const [pwd, setPwd] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [bioAvailable, setBioAvailable] = useState(false);
  // { token, reason: 'first_login'|'expired', knownOld, askOld }
  const [change, setChange] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const [{ data: status }, platformOk] = await Promise.all([
          botAPI.webauthnStatus(),
          isPlatformAuthenticatorAvailable(),
        ]);
        setBioAvailable(!!status.available && platformOk);
      } catch {
        setBioAvailable(false);
      }
    })();
  }, []);

  // Sessione completa ottenuta: salva il token e, se ha senso, propone
  // l'impronta prima di entrare nell'app.
  const finishLogin = async (token, { offerBio } = {}) => {
    localStorage.setItem('sb_token', token);
    if (offerBio) {
      try {
        const [{ data: status }, platformOk] = await Promise.all([
          botAPI.webauthnStatus(), isPlatformAuthenticatorAvailable(),
        ]);
        if (platformOk && !status.has_credentials) {
          setStage('bio');
          return;
        }
      } catch { /* non blocca l'accesso */ }
    }
    onLogin();
  };

  // Risposta di login/biometrico: token completo oppure token limitato +
  // must_change ('first_login' | 'expired').
  const handleLoginResponse = (data, typedPassword) => {
    if (data.must_change) {
      setChange({
        token: data.token,
        reason: data.must_change,
        knownOld: typedPassword || '',
        askOld: !typedPassword,
      });
      setStage('change');
      return Promise.resolve();
    }
    return finishLogin(data.token, { offerBio: true });
  };

  const handleLogin = async () => {
    if (!pwd) return;
    setLoading(true); setError(''); setInfo('');
    try {
      const { data } = await botAPI.login(pwd);
      await handleLoginResponse(data, pwd);
    } catch (e) {
      setError(loginErrorMessage(e));
    } finally {
      setLoading(false);
    }
  };

  const handleBioLogin = async () => {
    setLoading(true); setError(''); setInfo('');
    try {
      const { data: options } = await botAPI.webauthnLoginOptions();
      const { state_id, credentialJSON } = await getCredential(options);
      const { data } = await botAPI.webauthnLoginVerify(state_id, credentialJSON);
      await handleLoginResponse(data, '');
    } catch {
      setError('Accesso biometrico non riuscito, usa la password');
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterBio = async () => {
    setLoading(true); setError('');
    try {
      const { data: options } = await botAPI.webauthnRegisterOptions();
      const { state_id, credentialJSON } = await createCredential(options);
      await botAPI.webauthnRegisterVerify(state_id, credentialJSON, 'Questo dispositivo');
      onLogin();
    } catch {
      setError('Non è stato possibile attivare l\'impronta digitale su questo dispositivo');
      setLoading(false);
    }
  };

  const reasonText = change?.reason === 'expired'
    ? 'La password è scaduta (dura 60 giorni). Scegline una nuova per continuare.'
    : 'Primo accesso: scegli la tua password personale. Quella iniziale non servirà più.';

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', padding: '24px',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)'
    }}>
      <div style={{ fontSize: '60px', marginBottom: '16px' }}>🤖</div>
      <h1 style={{
        fontSize: '28px', fontWeight: 'bold', marginBottom: '8px',
        background: 'linear-gradient(90deg, #f1f5f9, #38bdf8)',
        WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent'
      }}>SuperBot</h1>
      <p style={{ color: '#94a3b8', marginBottom: '32px' }}>Trading Bot Dashboard</p>
      <div style={{ width: '100%', maxWidth: '360px' }}>

        {stage === 'change' && change && (
          <div style={panel}>
            <p style={{ marginBottom: '14px', fontSize: '14px', lineHeight: 1.4 }}>{reasonText}</p>
            <ChangePasswordForm
              askOld={change.askOld}
              knownOld={change.knownOld}
              token={change.token}
              onSuccess={(newToken) => finishLogin(newToken, { offerBio: true })}
            />
          </div>
        )}

        {stage === 'bio' && (
          <div style={panel}>
            <p style={{ marginBottom: '12px', fontSize: '14px' }}>
              Vuoi attivare l'accesso con impronta digitale su questo dispositivo, così non devi sempre digitare la password?
            </p>
            {error && <p style={{ color: '#f87171', fontSize: '13px', marginBottom: '10px' }}>{error}</p>}
            <div style={{ display: 'flex', gap: '8px' }}>
              <button onClick={handleRegisterBio} disabled={loading} style={{
                flex: 1, padding: '10px', borderRadius: '10px', background: '#0ea5e9',
                color: 'white', border: 'none', fontWeight: 'bold', cursor: 'pointer'
              }}>{loading ? '...' : 'Attiva impronta'}</button>
              <button onClick={onLogin} disabled={loading} style={{
                flex: 1, padding: '10px', borderRadius: '10px', background: 'none',
                color: '#94a3b8', border: '1px solid #334155', cursor: 'pointer'
              }}>Più tardi</button>
            </div>
          </div>
        )}

        {stage === 'login' && (
          <>
            {bioAvailable && (
              <button onClick={handleBioLogin} disabled={loading} style={{
                width: '100%', padding: '14px', borderRadius: '12px', marginBottom: '16px',
                background: '#1e293b', border: '1px solid #38bdf8', color: '#38bdf8',
                fontSize: '15px', fontWeight: 'bold', cursor: loading ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
              }}>
                👆 Sblocca con impronta digitale
              </button>
            )}

            <PasswordInput
              placeholder="Password"
              autoComplete="current-password"
              value={pwd}
              onChange={e => setPwd(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleLogin()}
              style={{
                width: '100%', padding: '14px 16px', borderRadius: '12px', boxSizing: 'border-box',
                border: '1px solid #334155', background: '#1e293b',
                color: '#f1f5f9', fontSize: '16px', marginBottom: '12px', outline: 'none'
              }}
            />
            {error && <p style={{ color: '#f87171', marginBottom: '12px', textAlign: 'center' }}>{error}</p>}
            {info && <p style={{ color: '#4ade80', marginBottom: '12px', textAlign: 'center' }}>{info}</p>}
            <button onClick={handleLogin} disabled={loading} style={{
              width: '100%', padding: '14px', borderRadius: '12px',
              background: loading ? '#334155' : '#0ea5e9',
              color: 'white', fontSize: '16px', fontWeight: 'bold',
              border: 'none', cursor: loading ? 'not-allowed' : 'pointer'
            }}>
              {loading ? 'Accesso...' : 'Accedi'}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
