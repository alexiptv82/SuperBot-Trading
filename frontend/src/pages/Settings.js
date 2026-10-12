import React, { useState, useEffect } from 'react';
import { botAPI, deskAPI, bullAPI } from '../api';
import Logs from './Logs';
import ChangePasswordForm from '../components/ChangePasswordForm';
import BiometricManager from '../components/BiometricManager';

const MUTED = '#94a3b8';
const BORDER = '#334155';
const GOOD = '#4ade80';
const WARN = '#fbbf24';

const Card = ({ children, style }) => (
  <div style={{
    background: '#1e293b', borderRadius: '16px', padding: '16px',
    border: `1px solid ${BORDER}`, ...style
  }}>{children}</div>
);

// Parametri V2 — Portafoglio HAWK
const HAWK_PARAMS = [
  { label: 'Portafoglio', value: '🦅 HAWK' },
  { label: 'Margine max per trade', value: '$100' },
  { label: 'Posizioni contemporanee', value: 'max 10' },
  { label: 'Budget totale', value: '$1000' },
  { label: 'TIER A (BTC, XAU, XAG)', value: 'max 45x' },
  { label: 'TIER B (ETH)', value: 'max 30x' },
  { label: 'TIER C (altri)', value: 'max 25x' },
  { label: 'Soglia TIER A/B (BTC/ETH/XAU/XAG)', value: 'conf ≥ 60/100' },
  { label: 'Soglia TIER C (altcoin)', value: 'conf ≥ 70/100' },
  { label: 'TP parziale scalp', value: '35% al TP1, 65% con TP2' },
  { label: 'DCA aggiuntivi', value: 'max 2 (solo tipo "medio")' },
  { label: 'DCA su scalp', value: 'max 1' },
  { label: 'Stop giornaliero', value: '12% del capitale' },
  { label: 'Kill equity', value: '450$' },
];

// Parametri V2 — Portafoglio BULL
const BULL_PARAMS = [
  { label: 'Portafoglio', value: '🐂 BULL' },
  { label: 'Margine max per trade', value: '$350' },
  { label: 'Posizioni contemporanee', value: 'max 3' },
  { label: 'Budget totale', value: '$1000' },
  { label: 'TIER A (BTC, XAU, XAG)', value: 'max 45x' },
  { label: 'TIER B (ETH)', value: 'max 30x' },
  { label: 'TIER C (altri)', value: 'max 25x' },
  { label: 'Soglia TIER A/B', value: 'conf ≥ 65/100' },
  { label: 'Soglia TIER C (altcoin)', value: 'conf ≥ 75/100' },
  { label: 'TP minimo accettabile', value: '5% (bot può tenere se trend continua)' },
  { label: 'TP parziale', value: '35-40% al TP1, residuo con TP2' },
  { label: 'DCA aggiuntivi', value: 'max 2 (solo tipo "medio")' },
  { label: 'Stop giornaliero', value: '12% del capitale' },
  { label: 'Kill equity', value: '450$' },
];

export default function Settings() {
  const [deskStatus, setDeskStatus] = useState(null);
  const [bullStatus, setBullStatus] = useState(null);
  const [showLogs, setShowLogs] = useState(false);
  const [showPwdForm, setShowPwdForm] = useState(false);
  const [pwdMsg, setPwdMsg] = useState('');
  const [pwdStatus, setPwdStatus] = useState(null);
  // Reset Hawk
  const [resetMsg, setResetMsg] = useState('');
  const [resetLoading, setResetLoading] = useState(false);
  // Reset Bull
  const [bullResetMsg, setBullResetMsg] = useState('');
  const [bullResetLoading, setBullResetLoading] = useState(false);

  useEffect(() => {
    botAPI.passwordStatus().then(({ data }) => setPwdStatus(data)).catch(() => {});
    deskAPI.getStatus().then(({ data }) => setDeskStatus(data)).catch(() => {});
    bullAPI.getStatus().then(({ data }) => setBullStatus(data)).catch(() => {});
  }, []);

  const handleResetBudget = async (equityReset) => {
    const label = equityReset ? 'equity a 1000$ + budget AI HAWK' : 'solo budget AI HAWK';
    if (!window.confirm(`Confermi reset ${label}?`)) return;
    setResetLoading(true);
    setResetMsg('');
    try {
      const { data } = await deskAPI.resetBudget(equityReset);
      setResetMsg(`✅ ${data.message} — attivo al prossimo ciclo`);
      setTimeout(() => {
        deskAPI.getStatus().then(({ data }) => setDeskStatus(data)).catch(() => {});
      }, 3000);
    } catch (e) {
      setResetMsg('❌ Errore reset Hawk: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setResetLoading(false);
    }
  };

  const handleBullResetBudget = async (equityReset) => {
    const label = equityReset ? 'equity a 1000$ + budget AI BULL' : 'solo budget AI BULL';
    if (!window.confirm(`Confermi reset ${label}?`)) return;
    setBullResetLoading(true);
    setBullResetMsg('');
    try {
      const { data } = await bullAPI.resetBudget(equityReset);
      setBullResetMsg(`✅ ${data.message} — attivo al prossimo ciclo`);
      setTimeout(() => {
        bullAPI.getStatus().then(({ data }) => setBullStatus(data)).catch(() => {});
      }, 3000);
    } catch (e) {
      setBullResetMsg('❌ Errore reset Bull: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setBullResetLoading(false);
    }
  };

  return (
    <div style={{ padding: '16px', maxWidth: '600px', margin: '0 auto' }}>
      <h1 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '16px' }}>⚙️ Impostazioni</h1>

      {/* ── Accesso ── */}
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        🔐 Accesso
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        <BiometricManager />
        <div style={{ height: '1px', background: BORDER, margin: '16px 0' }} />
        {pwdStatus?.set && (
          <div style={{ fontSize: '13px', color: pwdStatus.warn ? WARN : MUTED, marginBottom: '10px' }}>
            Password valida ancora {pwdStatus.days_left} {pwdStatus.days_left === 1 ? 'giorno' : 'giorni'} (si cambia ogni 60 giorni).
          </div>
        )}
        {showPwdForm ? (
          <div style={{ marginTop: '10px' }}>
            <ChangePasswordForm
              askOld
              onCancel={() => setShowPwdForm(false)}
              onSuccess={(newToken) => {
                sessionStorage.setItem('sb_token', newToken);
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
        {pwdMsg && <div style={{ fontSize: '12px', color: GOOD, marginTop: '10px' }}>{pwdMsg}</div>}
      </Card>

      {/* ── Bot V2 — Stato HAWK ── */}
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        🦅 Hawk — Stato
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        {!deskStatus ? (
          <div style={{ color: '#64748b', fontSize: '13px' }}>Caricamento...</div>
        ) : !deskStatus.available ? (
          <div style={{ color: MUTED, fontSize: '13px' }}>{deskStatus.message || 'Hawk non raggiungibile'}</div>
        ) : (
          <>
            {[
              ['Equity', `$${Number(deskStatus.equity ?? 0).toFixed(2)}`],
              ['Cassa libera', `$${Number(deskStatus.cash ?? 0).toFixed(2)}`],
              ['Margine in uso', `$${Number(deskStatus.margin_used ?? 0).toFixed(0)}`],
              ['Posizioni aperte', String(Array.isArray(deskStatus.positions) ? deskStatus.positions.length : (deskStatus.open_positions ?? 0))],
              ['Trade chiusi totali', String(deskStatus.total_closed ?? '--')],
              ['Budget AI oggi', `$${Number(deskStatus.budget_spent_usd ?? 0).toFixed(3)} / $${Number(deskStatus.budget_daily_cap_usd ?? 0.70).toFixed(2)}`],
              ['Ciclo corrente', String(deskStatus.cycle ?? '--')],
            ].map(([label, value]) => (
              <div key={label} style={{
                display: 'flex', justifyContent: 'space-between',
                padding: '8px 0', borderBottom: `1px solid ${BORDER}`, fontSize: '13px'
              }}>
                <span style={{ color: MUTED }}>{label}</span>
                <span style={{ fontWeight: 'bold' }}>{value}</span>
              </div>
            ))}
            {deskStatus.halt && (
              <div style={{ marginTop: '10px', padding: '8px 10px', borderRadius: '8px', background: 'rgba(220,38,38,0.1)', color: '#fca5a5', fontSize: '12px' }}>
                ⚠️ HALT: {deskStatus.halt}
              </div>
            )}
          </>
        )}
      </Card>

      {/* ── Bot V2 — Stato BULL ── */}
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        🐂 Bull — Stato
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        {!bullStatus ? (
          <div style={{ color: '#64748b', fontSize: '13px' }}>Caricamento...</div>
        ) : !bullStatus.available ? (
          <div style={{ color: MUTED, fontSize: '13px' }}>{bullStatus.message || 'Bull non ancora attivo'}</div>
        ) : (
          <>
            {[
              ['Equity', `$${Number(bullStatus.equity ?? 0).toFixed(2)}`],
              ['Cassa libera', `$${Number(bullStatus.cash ?? 0).toFixed(2)}`],
              ['Margine in uso', `$${Number(bullStatus.margin_used ?? 0).toFixed(0)}`],
              ['Posizioni aperte', String(Array.isArray(bullStatus.positions) ? bullStatus.positions.length : (bullStatus.open_positions ?? 0))],
              ['Trade chiusi totali', String(bullStatus.total_closed ?? '--')],
              ['Budget AI oggi', `$${Number(bullStatus.budget_spent_usd ?? 0).toFixed(3)} / $${Number(bullStatus.budget_daily_cap_usd ?? 0.70).toFixed(2)}`],
              ['Ciclo corrente', String(bullStatus.cycle ?? '--')],
            ].map(([label, value]) => (
              <div key={label} style={{
                display: 'flex', justifyContent: 'space-between',
                padding: '8px 0', borderBottom: `1px solid ${BORDER}`, fontSize: '13px'
              }}>
                <span style={{ color: MUTED }}>{label}</span>
                <span style={{ fontWeight: 'bold' }}>{value}</span>
              </div>
            ))}
            {bullStatus.halt && (
              <div style={{ marginTop: '10px', padding: '8px 10px', borderRadius: '8px', background: 'rgba(220,38,38,0.1)', color: '#fca5a5', fontSize: '12px' }}>
                ⚠️ HALT: {bullStatus.halt}
              </div>
            )}
          </>
        )}
      </Card>

      {/* ── Reset HAWK ── */}
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        🔄 Reset 🦅 Hawk
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '12px' }}>
          Attivo al ciclo successivo (max 15-30 min).
        </div>
        <button onClick={() => handleResetBudget(false)} disabled={resetLoading}
          style={{ width: '100%', padding: '11px', borderRadius: '10px', marginBottom: '8px',
            border: '1px solid #334155', background: 'none', color: '#fbbf24',
            fontWeight: 'bold', cursor: resetLoading ? 'not-allowed' : 'pointer', fontSize: '13px' }}>
          🔁 Azzera solo budget AI Hawk
        </button>
        <button onClick={() => handleResetBudget(true)} disabled={resetLoading}
          style={{ width: '100%', padding: '11px', borderRadius: '10px',
            border: '1px solid #ef4444', background: 'rgba(239,68,68,0.08)', color: '#fca5a5',
            fontWeight: 'bold', cursor: resetLoading ? 'not-allowed' : 'pointer', fontSize: '13px' }}>
          ⚠️ Reset Hawk: equity 1000$ + chiudi posizioni + azzera budget
        </button>
        {resetMsg && (
          <div style={{ marginTop: '10px', fontSize: '12px', color: resetMsg.startsWith('✅') ? GOOD : '#fca5a5' }}>
            {resetMsg}
          </div>
        )}
      </Card>

      {/* ── Reset BULL ── */}
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        🔄 Reset 🐂 Bull
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '12px' }}>
          Attivo al ciclo successivo (max 15-30 min).
        </div>
        <button onClick={() => handleBullResetBudget(false)} disabled={bullResetLoading}
          style={{ width: '100%', padding: '11px', borderRadius: '10px', marginBottom: '8px',
            border: '1px solid #334155', background: 'none', color: '#fbbf24',
            fontWeight: 'bold', cursor: bullResetLoading ? 'not-allowed' : 'pointer', fontSize: '13px' }}>
          🔁 Azzera solo budget AI Bull
        </button>
        <button onClick={() => handleBullResetBudget(true)} disabled={bullResetLoading}
          style={{ width: '100%', padding: '11px', borderRadius: '10px',
            border: '1px solid #ef4444', background: 'rgba(239,68,68,0.08)', color: '#fca5a5',
            fontWeight: 'bold', cursor: bullResetLoading ? 'not-allowed' : 'pointer', fontSize: '13px' }}>
          ⚠️ Reset Bull: equity 1000$ + chiudi posizioni + azzera budget
        </button>
        {bullResetMsg && (
          <div style={{ marginTop: '10px', fontSize: '12px', color: bullResetMsg.startsWith('✅') ? GOOD : '#fca5a5' }}>
            {bullResetMsg}
          </div>
        )}
      </Card>

      {/* ── Parametri V2 (read-only) ── */}
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        📐 Parametri Bot V2
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        <div style={{ fontSize: '11px', color: '#475569', marginBottom: '12px' }}>
          Leva, margini e regole sono configurati nel codice del motore — non modificabili da qui.
          Chiedi a Claude di cambiarli se necessario.
        </div>
        {/* HAWK */}
        <div style={{ fontSize: '12px', color: '#fbbf24', fontWeight: 'bold', margin: '8px 0 6px' }}>🦅 HAWK</div>
        {HAWK_PARAMS.filter(p => p.label !== 'Portafoglio').map(({ label, value }) => (
          <div key={label} style={{
            display: 'flex', justifyContent: 'space-between',
            padding: '5px 0', borderBottom: `1px solid ${BORDER}`, fontSize: '13px'
          }}>
            <span style={{ color: MUTED, flex: 1 }}>{label}</span>
            <span style={{ fontWeight: 'bold', color: '#38bdf8', textAlign: 'right' }}>{value}</span>
          </div>
        ))}
        {/* BULL */}
        <div style={{ fontSize: '12px', color: '#a78bfa', fontWeight: 'bold', margin: '14px 0 6px' }}>🐂 BULL</div>
        {BULL_PARAMS.filter(p => p.label !== 'Portafoglio').map(({ label, value }) => (
          <div key={label} style={{
            display: 'flex', justifyContent: 'space-between',
            padding: '5px 0', borderBottom: `1px solid ${BORDER}`, fontSize: '13px'
          }}>
            <span style={{ color: MUTED, flex: 1 }}>{label}</span>
            <span style={{ fontWeight: 'bold', color: '#a78bfa', textAlign: 'right' }}>{value}</span>
          </div>
        ))}
        <div style={{
          marginTop: '12px', padding: '8px 10px', borderRadius: '8px',
          background: 'rgba(56,189,248,0.07)', border: '1px solid rgba(56,189,248,0.2)',
          fontSize: '11px', color: '#38bdf8'
        }}>
          💡 <strong>GUARDRAIL attivo:</strong> il codice corregge margini e leva proposti da Claude se sotto i minimi del portafoglio.
        </div>
      </Card>

      {/* ── Log di sistema ── */}
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
