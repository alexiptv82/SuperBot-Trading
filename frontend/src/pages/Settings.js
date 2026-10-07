import React, { useState, useEffect } from 'react';
import { botAPI } from '../api';
import { isPlatformAuthenticatorAvailable, createCredential } from '../webauthnClient';
import Logs from './Logs';

const Card = ({ children, style }) => (
  <div style={{
    background: '#1e293b', borderRadius: '16px', padding: '16px',
    border: '1px solid #334155', ...style
  }}>{children}</div>
);

export default function Settings() {
  const [config, setConfig] = useState(null);
  const [bioAvailable, setBioAvailable] = useState(false);
  const [hasCredentials, setHasCredentials] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [showLogs, setShowLogs] = useState(false);

  const refreshStatus = async () => {
    try {
      const [{ data: cfg }, { data: webauthn }, platformOk] = await Promise.all([
        botAPI.getConfig(), botAPI.webauthnStatus(), isPlatformAuthenticatorAvailable(),
      ]);
      setConfig(cfg);
      setHasCredentials(!!webauthn.has_credentials);
      setBioAvailable(platformOk);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { refreshStatus(); }, []);

  const handleAddBio = async () => {
    setBusy(true); setMsg('');
    try {
      const { data: options } = await botAPI.webauthnRegisterOptions();
      const { state_id, credentialJSON } = await createCredential(options);
      await botAPI.webauthnRegisterVerify(state_id, credentialJSON, 'Dispositivo aggiunto da Impostazioni');
      setMsg('Impronta digitale attivata su questo dispositivo.');
      refreshStatus();
    } catch {
      setMsg("Non è stato possibile attivare l'impronta su questo dispositivo.");
    } finally {
      setBusy(false);
    }
  };

  const rows = config ? [
    ['Modalità', config.trading_mode],
    ['Capitale iniziale', `$${config.initial_capital}`],
    ['Leva massima', `x${config.max_leverage}`],
    ['Perdita massima giornaliera', `${config.max_daily_loss_percent}%`],
    ['Posizioni aperte massime', config.max_open_positions],
    ['Coppie', (config.trading_pairs || []).join(', ')],
  ] : [];

  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '16px' }}>⚙️ Impostazioni</h1>

      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        🔐 Accesso
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        <div style={{ fontSize: '13px', color: '#94a3b8', marginBottom: '10px' }}>
          {hasCredentials
            ? 'Impronta digitale attiva su almeno un dispositivo.'
            : 'Nessuna impronta digitale registrata ancora.'}
        </div>
        {bioAvailable ? (
          <button onClick={handleAddBio} disabled={busy} style={{
            width: '100%', padding: '12px', borderRadius: '10px', border: 'none',
            background: busy ? '#334155' : '#0ea5e9', color: 'white',
            fontWeight: 'bold', cursor: busy ? 'not-allowed' : 'pointer'
          }}>
            {busy ? '...' : '👆 Attiva impronta su questo dispositivo'}
          </button>
        ) : (
          <div style={{ fontSize: '12px', color: '#64748b' }}>
            Il biometrico richiede HTTPS con un dominio reale: non ancora disponibile su questo indirizzo.
          </div>
        )}
        {msg && <div style={{ fontSize: '12px', color: '#4ade80', marginTop: '10px' }}>{msg}</div>}
      </Card>

      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        🎛️ Parametri di Rischio
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        {!config ? (
          <div style={{ color: '#64748b', fontSize: '13px' }}>Caricamento...</div>
        ) : rows.map(([label, value]) => (
          <div key={label} style={{
            display: 'flex', justifyContent: 'space-between',
            padding: '8px 0', borderBottom: '1px solid #334155', fontSize: '13px'
          }}>
            <span style={{ color: '#94a3b8' }}>{label}</span>
            <span style={{ fontWeight: 'bold' }}>{value}</span>
          </div>
        ))}
        <div style={{ fontSize: '11px', color: '#64748b', marginTop: '10px' }}>
          Questi parametri sono definiti sul server; modificarli richiede per ora un aggiornamento della configurazione lato bot.
        </div>
      </Card>

      <button onClick={() => setShowLogs(s => !s)} style={{
        width: '100%', padding: '12px', borderRadius: '10px', border: '1px solid #334155',
        background: 'none', color: '#cbd5e1', fontWeight: 'bold', cursor: 'pointer', marginBottom: '16px'
      }}>
        {showLogs ? '▲ Nascondi log di sistema' : '▼ Mostra log di sistema'}
      </button>
      {showLogs && <div style={{ margin: '-16px' }}><Logs /></div>}
    </div>
  );
}
