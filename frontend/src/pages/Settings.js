import React, { useState, useEffect } from 'react';
import { botAPI } from '../api';
import { isPlatformAuthenticatorAvailable, createCredential } from '../webauthnClient';
import Logs from './Logs';
import ChangePasswordForm from '../components/ChangePasswordForm';

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
  const [riskForm, setRiskForm] = useState(null);
  const [riskMsg, setRiskMsg] = useState(null); // { ok: bool, text: string }
  const [riskBusy, setRiskBusy] = useState(false);
  const [showPwdForm, setShowPwdForm] = useState(false);
  const [pwdMsg, setPwdMsg] = useState('');
  const [pwdStatus, setPwdStatus] = useState(null);

  const refreshStatus = async () => {
    try {
      const [{ data: cfg }, { data: webauthn }, platformOk, { data: st }, { data: pf }] = await Promise.all([
        botAPI.getConfig(), botAPI.webauthnStatus(), isPlatformAuthenticatorAvailable(),
        botAPI.getStatus(), botAPI.getPerformance(),
      ]);
      setConfig(cfg);
      setRiskForm(prev => prev || {
        max_leverage: String(cfg.max_leverage),
        max_daily_loss_percent: String(cfg.max_daily_loss_percent),
        max_open_positions: String(cfg.max_open_positions),
      });
      setHasCredentials(!!webauthn.has_credentials);
      setBioAvailable(platformOk);
      setStatus(st);
      setPerf(pf);
    } catch (e) { console.error(e); }
  };

  useEffect(() => { refreshStatus(); }, []);
  useEffect(() => { botAPI.passwordStatus().then(({ data }) => setPwdStatus(data)).catch(() => {}); }, []);

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

  const RISK_FIELDS = [
    { key: 'max_leverage', label: 'Leva massima', unit: 'x', step: 1 },
    { key: 'max_daily_loss_percent', label: 'Perdita massima giornaliera', unit: '%', step: 0.5 },
    { key: 'max_open_positions', label: 'Posizioni aperte massime', unit: '', step: 1 },
  ];

  const riskError = (key) => {
    if (!riskForm || !config?.risk_bounds) return null;
    const b = config.risk_bounds[key];
    const raw = riskForm[key];
    const n = Number(raw);
    if (raw === '' || Number.isNaN(n)) return 'Inserisci un numero';
    if (key !== 'max_daily_loss_percent' && !Number.isInteger(n)) return 'Deve essere un numero intero';
    if (n < b.min || n > b.max) return `Tra ${b.min} e ${b.max}`;
    return null;
  };

  const riskDirty = !!(config && riskForm) && RISK_FIELDS.some(f => Number(riskForm[f.key]) !== Number(config[f.key]));
  const riskValid = !!riskForm && RISK_FIELDS.every(f => !riskError(f.key));

  const handleSaveRisk = async () => {
    setRiskBusy(true); setRiskMsg(null);
    try {
      const payload = {};
      RISK_FIELDS.forEach(f => { payload[f.key] = Number(riskForm[f.key]); });
      const { data } = await botAPI.updateRiskConfig(payload);
      const a = data.applied;
      setConfig(c => ({ ...c, ...a }));
      setRiskForm({
        max_leverage: String(a.max_leverage),
        max_daily_loss_percent: String(a.max_daily_loss_percent),
        max_open_positions: String(a.max_open_positions),
      });
      setRiskMsg({ ok: true, text: 'Salvato. Il bot usa i nuovi valori dal prossimo ciclo.' });
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setRiskMsg({ ok: false, text: typeof detail === 'string' ? detail : 'Salvataggio non riuscito, riprova.' });
    } finally {
      setRiskBusy(false);
    }
  };

  const rows = config ? [
    ['Modalità', config.trading_mode],
    ['Capitale iniziale', `$${config.initial_capital}`],
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
        {pwdStatus?.set && (
          <div style={{ fontSize: '13px', color: pwdStatus.warn ? WARN : '#94a3b8', marginTop: '16px', marginBottom: '10px' }}>
            Password valida ancora {pwdStatus.days_left} {pwdStatus.days_left === 1 ? 'giorno' : 'giorni'} (si cambia ogni 60 giorni).
          </div>
        )}
        {showPwdForm ? (
          <div style={{ marginTop: '10px' }}>
            <ChangePasswordForm
              askOld
              onCancel={() => setShowPwdForm(false)}
              onSuccess={(newToken) => {
                // Il cambio password chiude tutte le sessioni precedenti: questa
                // continua col nuovo token.
                localStorage.setItem('sb_token', newToken);
                setShowPwdForm(false);
                setPwdMsg('Password cambiata. Gli altri dispositivi dovranno accedere di nuovo.');
                botAPI.passwordStatus().then(({ data }) => setPwdStatus(data)).catch(() => {});
              }}
            />
          </div>
        ) : (
          <button onClick={() => { setPwdMsg(''); setShowPwdForm(true); }} style={{
            width: '100%', marginTop: pwdStatus?.set ? 0 : '16px', padding: '12px', borderRadius: '10px',
            border: '1px solid #334155', background: 'none', color: '#cbd5e1',
            fontWeight: 'bold', cursor: 'pointer'
          }}>
            🔑 Cambia password
          </button>
        )}
        {pwdMsg && <div style={{ fontSize: '12px', color: '#4ade80', marginTop: '10px' }}>{pwdMsg}</div>}
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

      {config && riskForm && (
        <>
          <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
            ✏️ Limiti di Rischio
          </h2>
          <Card style={{ marginBottom: '16px' }}>
            {RISK_FIELDS.map(f => {
              const err = riskError(f.key);
              return (
                <div key={f.key} style={{ padding: '8px 0', borderBottom: `1px solid ${BORDER}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '13px' }}>
                    <label htmlFor={f.key} style={{ color: MUTED }}>{f.label}</label>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <input
                        id={f.key} type="number" inputMode="decimal" step={f.step}
                        value={riskForm[f.key]}
                        onChange={e => { setRiskMsg(null); setRiskForm(r => ({ ...r, [f.key]: e.target.value })); }}
                        style={{
                          width: '80px', padding: '6px 8px', borderRadius: '8px', textAlign: 'right',
                          background: '#0f172a', color: 'white', fontWeight: 'bold',
                          border: `1px solid ${err ? BAD : BORDER}`
                        }}
                      />
                      <span style={{ color: MUTED, width: '12px' }}>{f.unit}</span>
                    </span>
                  </div>
                  {err && <div style={{ fontSize: '11px', color: BAD, marginTop: '4px', textAlign: 'right' }}>{err}</div>}
                </div>
              );
            })}
            <button
              onClick={handleSaveRisk}
              disabled={!riskDirty || !riskValid || riskBusy}
              style={{
                width: '100%', marginTop: '14px', padding: '12px', borderRadius: '10px', border: 'none',
                background: (!riskDirty || !riskValid || riskBusy) ? '#334155' : '#0ea5e9',
                color: 'white', fontWeight: 'bold',
                cursor: (!riskDirty || !riskValid || riskBusy) ? 'not-allowed' : 'pointer'
              }}>
              {riskBusy ? '...' : 'Salva limiti di rischio'}
            </button>
            {riskMsg && (
              <div style={{ fontSize: '12px', color: riskMsg.ok ? GOOD : BAD, marginTop: '10px' }}>{riskMsg.text}</div>
            )}
            <div style={{ fontSize: '11px', color: '#64748b', marginTop: '10px' }}>
              I valori salvati restano anche dopo un riavvio o un nuovo deploy. Limiti accettati: leva 1–20x, perdita giornaliera 0,5–20%, posizioni 1–10.
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
          Modalità, capitale e coppie sono definiti sul server (non modificabili da qui).
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
