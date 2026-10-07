import React, { useState, useEffect } from 'react';
import { botAPI } from '../api';
import { isPlatformAuthenticatorAvailable, createCredential, getCredential } from '../webauthnClient';

export default function Login({ onLogin }) {
  const [pwd, setPwd] = useState('');
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [loading, setLoading] = useState(false);
  const [bioAvailable, setBioAvailable] = useState(false);
  const [offerBioSetup, setOfferBioSetup] = useState(false);

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

  const finishLogin = (token) => {
    localStorage.setItem('sb_token', token);
    onLogin();
  };

  const handleLogin = async () => {
    setLoading(true); setError(''); setInfo('');
    try {
      const { data } = await botAPI.login(pwd);
      // Dopo il primo login a password, se il dispositivo supporta il
      // biometrico e non ci sono già credenziali salvate, lo propone.
      try {
        const { data: status } = await botAPI.webauthnStatus();
        const platformOk = await isPlatformAuthenticatorAvailable();
        if (status.available && platformOk && !status.has_credentials) {
          setOfferBioSetup(true);
        }
      } catch { /* non blocca il login */ }
      finishLogin(data.token);
    } catch {
      setError('Password errata');
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
      finishLogin(data.token);
    } catch {
      setError('Accesso biometrico non riuscito, usa la password');
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterBio = async () => {
    setLoading(true); setError(''); setInfo('');
    try {
      const { data: options } = await botAPI.webauthnRegisterOptions();
      const { state_id, credentialJSON } = await createCredential(options);
      await botAPI.webauthnRegisterVerify(state_id, credentialJSON, 'Questo dispositivo');
      setOfferBioSetup(false);
      setInfo('Impronta digitale attivata per i prossimi accessi.');
    } catch {
      setError('Non è stato possibile attivare l\'impronta digitale su questo dispositivo');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', padding: '24px',
      background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)'
    }}>
      <div style={{ fontSize: '60px', marginBottom: '16px' }}>🤖</div>
      <h1 style={{ fontSize: '28px', fontWeight: 'bold', marginBottom: '8px', color: '#f1f5f9' }}>SuperBot</h1>
      <p style={{ color: '#94a3b8', marginBottom: '32px' }}>Trading Bot Dashboard</p>
      <div style={{ width: '100%', maxWidth: '360px' }}>
        {offerBioSetup ? (
          <div style={{
            background: '#1e293b', border: '1px solid #334155', borderRadius: '12px',
            padding: '16px', marginBottom: '16px', color: '#f1f5f9'
          }}>
            <p style={{ marginBottom: '12px', fontSize: '14px' }}>
              Vuoi attivare l'accesso con impronta digitale su questo dispositivo, così non devi sempre digitare la password?
            </p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button onClick={handleRegisterBio} disabled={loading} style={{
                flex: 1, padding: '10px', borderRadius: '10px', background: '#0ea5e9',
                color: 'white', border: 'none', fontWeight: 'bold', cursor: 'pointer'
              }}>Attiva impronta</button>
              <button onClick={() => setOfferBioSetup(false)} style={{
                flex: 1, padding: '10px', borderRadius: '10px', background: 'none',
                color: '#94a3b8', border: '1px solid #334155', cursor: 'pointer'
              }}>Più tardi</button>
            </div>
          </div>
        ) : null}

        {bioAvailable && !offerBioSetup && (
          <button onClick={handleBioLogin} disabled={loading} style={{
            width: '100%', padding: '14px', borderRadius: '12px', marginBottom: '16px',
            background: '#1e293b', border: '1px solid #38bdf8', color: '#38bdf8',
            fontSize: '15px', fontWeight: 'bold', cursor: loading ? 'not-allowed' : 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px'
          }}>
            👆 Sblocca con impronta digitale
          </button>
        )}

        <input
          type="password"
          placeholder="Password"
          value={pwd}
          onChange={e => setPwd(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleLogin()}
          style={{
            width: '100%', padding: '14px 16px', borderRadius: '12px',
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
      </div>
    </div>
  );
}
