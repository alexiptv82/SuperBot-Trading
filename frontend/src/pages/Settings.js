import React, { useState, useEffect } from 'react';
import { botAPI } from '../api';
import { isPlatformAuthenticatorAvailable, createCredential } from '../webauthnClient';
import Logs from './Logs';

const MUTED = '#94a3b8';
const BORDER = '#334155';
const GOOD = '#4ade80';
const WARN = '#fbbf24';
const BAD = '#f87171';

const Card = ({ children, style }) => (
  <div style={{
    background: '#1e293b', borderRadius: '16px', padding: '16px',
    border: `1px solid ${BORDER}`, ...style
  }}>{children}</div>
);

const RiskBar = ({ label, current, max, unit = '', tone }) => {
  const pct = max > 0 ? Math.min(100, Math.max(0, (current / max) * 100)) : 0;
  const color = tone || (pct >= 100 ? BAD : pct >= 70 ? WARN : GOOD);
  return (
    <div style={{ marginBottom: '14px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '6px' }}>
        <span style={{ color: MUTED }}>{label}</span>
        <span style={{ fontWeight: 'bold' }}>{current}{unit} / {max}{unit}</span>
      </div>
      <div style={{ height: '6px', borderRadius: '4px', background: '#0f172a', overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: '4px', transition: 'width 0.3s' }} />
      </div>
    </div>
  );
};

export default function Settings() {
  const [config, setConfig] = useState(null);
  const [status, setStatus] = useState(null);
  const [perf, setPerf] = useState(null);
  const [bioAvailable, setBioAvailable] = useState(false);
  const [hasCredentials, setHasCredentials] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [showLogs, setShowLogs] = useState(false);

  const refreshStatus = async () => {
    try {
      const [{ data: cfg }, { data: webauthn }, platformOk, { data: st }, { data: pf }] = await Promise.all([
        botAPI.getConfig(), botAPI.webauthnStatus(), isPlatformAuthenticatorAvailable(),
        botAPI.getStatus(), botAPI.getPerformance(),
      ]);
      setConfig(cfg);
      setHasCredentials(!!webauthn.has_credentials);
      setBioAvailable(platformOk);
      setStatus(st);
      setPerf(pf);
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

      {config && status && (
        <>
          <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
            🛡️ Rischio in Tempo Reale
          </h2>
          <Card style={{ marginBottom: '16px' }}>
            <RiskBar
              label="Perdita giornaliera"
              current={Math.round(Math.max(0, -(status.daily_pnl || 0)) / (config.initial_capital || 1) * 1000) / 10}
              max={config.max_daily_loss_percent}
              unit="%"
            />
            <RiskBar
              label="Posizioni aperte"
              current={status.open_positions || 0}
              max={config.max_open_positions}
            />
            {perf && perf.equity_curve && perf.equity_curve.length > 0 && (() => {
              const initial = config.initial_capital || 0;
              let peak = initial, current = initial;
              for (const p of perf.equity_curve) {
                const eq = initial + p.equity;
                if (eq > peak) peak = eq;
                current = eq;
              }
              const ddPct = peak > 0 ? Math.round(Math.max(0, (peak - current) / peak) * 1000) / 10 : 0;
              return (
                <RiskBar label="Drawdown attuale" current={ddPct} max={8} unit="%"
                  tone={ddPct >= 8 ? BAD : ddPct >= 5 ? WARN : GOOD} />
              );
            })()}
            <div style={{ fontSize: '11px', color: '#64748b', marginTop: '4px' }}>
              Calcolato sui dati reali del bot. Il drawdown usa una soglia di riferimento dell'8%, non ancora configurabile.
            </div>
          </Card>
        </>
      )}

      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        🎛️ Parametri Configurati
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
