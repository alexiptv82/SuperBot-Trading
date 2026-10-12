import React, { useState, useEffect } from 'react';
import { botAPI, deskAPI } from '../api';
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

// Parametri V2 hardcoded nel motore — mostrati in read-only
const V2_PARAMS = [
  { label: 'TIER A (BTC, XAU, XAG)', value: 'max 45x' },
  { label: 'TIER B (ETH)', value: 'max 30x' },
  { label: 'TIER C (altri)', value: 'max 25x' },
  { label: 'Margine minimo per trade', value: '150$ (GUARDRAIL)' },
  { label: 'Posizioni contemporanee', value: 'max 10' },
  { label: 'Soglia segnale TIER A/B (BTC/ETH/XAU/XAG)', value: 'conf ≥ 60/100' },
  { label: 'Soglia segnale TIER C (altcoin)', value: 'conf ≥ 70/100' },
  { label: 'TP parziale scalp', value: '35% al TP1, 65% con TP2' },
  { label: 'DCA aggiuntivi', value: 'max 2 (solo tipo "medio")' },
  { label: 'DCA su scalp', value: 'max 1' },
  { label: 'Stop giornaliero', value: '12% del capitale' },
  { label: 'Kill equity', value: '450$' },
];

export default function Settings() {
  const [deskStatus, setDeskStatus] = useState(null);
  const [showLogs, setShowLogs] = useState(false);
  const [showPwdForm, setShowPwdForm] = useState(false);
  const [pwdMsg, setPwdMsg] = useState('');
  const [pwdStatus, setPwdStatus] = useState(null);

  useEffect(() => {
    botAPI.passwordStatus().then(({ data }) => setPwdStatus(data)).catch(() => {});
    deskAPI.getStatus().then(({ data }) => setDeskStatus(data)).catch(() => {});
  }, []);

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

      {/* ── Bot V2 — Stato ── */}
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        🧠 Bot V2 — Stato
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        {!deskStatus ? (
          <div style={{ color: '#64748b', fontSize: '13px' }}>Caricamento...</div>
        ) : !deskStatus.available ? (
          <div style={{ color: MUTED, fontSize: '13px' }}>{deskStatus.message || 'Bot V2 non raggiungibile'}</div>
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
              ['Giorno', String(deskStatus.day || '--')],
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

      {/* ── Parametri V2 (read-only) ── */}
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        📐 Parametri Bot V2
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        <div style={{ fontSize: '11px', color: '#475569', marginBottom: '12px' }}>
          Leva, margini e regole sono configurati nel codice del motore — non modificabili da qui.
          Chiedi a Claude di cambiarli se necessario.
        </div>
        {V2_PARAMS.map(({ label, value }) => (
          <div key={label} style={{
            display: 'flex', justifyContent: 'space-between',
            padding: '7px 0', borderBottom: `1px solid ${BORDER}`, fontSize: '13px'
          }}>
            <span style={{ color: MUTED, flex: 1 }}>{label}</span>
            <span style={{ fontWeight: 'bold', color: '#38bdf8', textAlign: 'right' }}>{value}</span>
          </div>
        ))}
        <div style={{
          marginTop: '12px', padding: '8px 10px', borderRadius: '8px',
          background: 'rgba(56,189,248,0.07)', border: '1px solid rgba(56,189,248,0.2)',
          fontSize: '11px', color: '#38bdf8'
        }}>
          💡 <strong>GUARDRAIL attivo:</strong> anche se Claude propone un margine inferiore a 150$ o una leva sotto 15x, il codice lo corregge automaticamente prima di aprire il trade.
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
