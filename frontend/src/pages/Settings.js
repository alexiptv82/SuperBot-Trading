import React, { useState, useEffect, useRef } from 'react';
import { botAPI, deskAPI, bullAPI, errMsg } from '../api';
import { botState, signed, fmtClock, fmtDateTime, PARAM_ROWS, DAY_LABELS, DAY_NAMES } from '../deskUi';
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

const apiFor = (pf) => (pf === 'bull' ? bullAPI : deskAPI);

const Row = ({ label, value, color }) => (
  <div style={{
    display: 'flex', justifyContent: 'space-between', gap: '12px',
    padding: '7px 0', borderBottom: `1px solid ${BORDER}`, fontSize: '13px'
  }}>
    <span style={{ color: MUTED }}>{label}</span>
    <span style={{ fontWeight: 'bold', color: color || '#f1f5f9', textAlign: 'right' }}>{value}</span>
  </div>
);

const bigBtn = (enabled, color, bg) => ({
  width: '100%', padding: '11px', borderRadius: '10px', marginTop: '8px', fontSize: '13px', fontWeight: 'bold',
  border: `1px solid ${enabled ? color : BORDER}`, background: enabled ? bg : 'rgba(51,65,85,0.2)',
  color: enabled ? color : '#475569', cursor: enabled ? 'pointer' : 'not-allowed',
});

// Stato + comandi di un portafoglio (Hawk o Bull)
function PortfolioControl({ portfolio }) {
  const isBull = portfolio === 'bull';
  const name = isBull ? 'Toro' : 'Falco';
  const icon = isBull ? '🐂' : '🦅';
  const [status, setStatus] = useState(null);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState(null);

  const refresh = React.useCallback(async () => {
    try { const { data } = await apiFor(portfolio).getStatus(); setStatus(data); return data; }
    catch { return null; }
  }, [portfolio]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 6000);
    return () => clearInterval(t);
  }, [refresh]);

  const resetBudget = async () => {
    if (!window.confirm(`Azzerare il budget giornaliero di Claude per ${name}?\nIl conto e le posizioni non vengono toccati.`)) return;
    setBusy('budget'); setMsg(null);
    try {
      const { data } = await apiFor(portfolio).resetBudget();
      setMsg({ ok: true, text: data.message });
    } catch (e) { setMsg({ ok: false, text: `Errore: ${errMsg(e)}` }); }
    finally { setBusy(null); setTimeout(refresh, 2500); }
  };

  const resetPortfolio = async () => {
    const n = status?.total_closed ?? 0;
    const text = `Azzerare il portafoglio ${name}?\n\n` +
      `• La run attuale (${n} trade chiusi, ${signed(status?.pnl_total)}$) viene archiviata: la ritrovi in Performance → Run.\n` +
      `• Il conto riparte da ${status?.start_equity ?? 1000}$ con i parametri del codice (quelli mostrati qui sotto).\n` +
      `• Il cervello del bot (storico dei trade, appunti di Claude, registro di apprendimento) NON viene toccato: continua a imparare.\n` +
      `• Il bot resta in pausa finché non premi Avvia nella Dashboard.`;
    const vaultActive = status?.salvadanaio?.available === true;
    const warning = vaultActive ? "\n\n⚠️ ATTENZIONE: anche il Salvadanaio sarà AZZERATO (saldo e somme in attesa). I movimenti precedenti restano archiviati. Il cervello non sarà cancellato." : "";
    if (!window.confirm(text + warning)) return;
    if (vaultActive && !window.confirm(`SECONDA CONFERMA: azzerare conto e Salvadanaio di ${name}? Operazione non annullabile.`)) return;
    setBusy('portfolio'); setMsg(null);
    const runBefore = status?.run_no;
    try {
      const { data } = await apiFor(portfolio).resetPortfolio(vaultActive);
      setMsg({ ok: true, text: data.message });
      // il bot esegue il comando entro pochi secondi: aspetto che il numero di run cambi
      for (let i = 0; i < 12; i += 1) {
        await new Promise(r => setTimeout(r, 2500));
        const st = await refresh();
        if (st && st.run_no !== runBefore) {
          setMsg({ ok: true, text: `✅ Fatto: nuova run #${st.run_no}, conto a $${Number(st.equity).toFixed(0)}. Il bot è in pausa: premi Avvia dalla Dashboard quando vuoi ripartire.` });
          break;
        }
        if (st && st.last_action?.type === 'reset_portfolio' && st.last_action.ok === false) {
          setMsg({ ok: false, text: `Il bot ha rifiutato: ${st.last_action.detail}` });
          break;
        }
      }
    } catch (e) { setMsg({ ok: false, text: errMsg(e) }); }
    finally { setBusy(null); }
  };

  const st = botState(status);
  const canReset = status?.available && status.can_reset && !status.reset_pending && !busy;

  return (
    <>
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        {icon} {name} — Stato e comandi
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        {!status ? (
          <div style={{ color: '#64748b', fontSize: '13px' }}>Caricamento...</div>
        ) : !status.available ? (
          <div style={{ color: MUTED, fontSize: '13px' }}>{status.message || `${name} non raggiungibile`}</div>
        ) : (
          <>
            <Row label="Stato del bot" value={st.text} color={st.color} />
            <Row label="Equity" value={`$${Number(status.equity ?? 0).toFixed(2)}  (${signed(status.pnl_total)}$)`} />
            <Row label="Cassa libera" value={`$${Number(status.cash ?? 0).toFixed(2)}`} />
            <Row label="Margine in uso" value={`$${Number(status.margin_used ?? 0).toFixed(0)}`} />
            <Row label="Posizioni aperte" value={`${status.open_positions ?? 0} / ${status.max_open ?? '-'}`} />
            <Row label="Trade chiusi (run attuale)" value={String(status.total_closed ?? 0)} />
            <Row label="Run" value={`#${status.run_no ?? 1}`} />
            <Row label="Budget AI oggi" value={`$${Number(status.budget_spent_usd ?? 0).toFixed(3)} / $${Number(status.budget_daily_cap_usd ?? 0.7).toFixed(2)}`} />
            {status.cycle?.next_cycle_ms && st.key === 'running' && (
              <Row label="Prossimo controllo mercato" value={fmtClock(status.cycle.next_cycle_ms)} />
            )}
            {status.halt && (
              <div style={{ marginTop: '10px', padding: '8px 10px', borderRadius: '8px', background: 'rgba(220,38,38,0.1)', color: '#fca5a5', fontSize: '12px' }}>
                ⚠️ Nuovi trade bloccati: {status.halt}
              </div>
            )}

            <button onClick={resetBudget} disabled={!!busy} style={bigBtn(!busy, '#fbbf24', 'rgba(251,191,36,0.08)')}>
              🔁 Azzera budget AI di oggi
            </button>

            <div style={{ height: '1px', background: BORDER, margin: '16px 0 4px' }} />
            <div style={{ fontSize: '12px', color: MUTED, margin: '8px 0' }}>
              <strong style={{ color: '#cbd5e1' }}>Azzera portafoglio</strong> — riparte da {status.start_equity ?? 1000}$ per provare
              nuovi parametri. Si può fare solo con il bot <em>in pausa</em> e <em>senza posizioni aperte</em>;
              la run attuale viene archiviata per il confronto. Se il Salvadanaio è attivo, vengono azzerati anche saldo e somme in attesa, dopo doppia conferma. Il cervello del bot (storico, appunti, registro) non si cancella mai.
            </div>
            <button onClick={resetPortfolio} disabled={!canReset} style={bigBtn(canReset, '#fca5a5', 'rgba(239,68,68,0.1)')}>
              {busy === 'portfolio' ? '⏳ Azzeramento…' : status.reset_pending ? '⏳ Azzeramento in corso…' : `🗑️ Azzera ${name} a ${status.start_equity ?? 1000}$`}
            </button>
            {!status.can_reset && (
              <div style={{ marginTop: '8px', fontSize: '12px', color: '#fbbf24' }}>{status.reset_blocked_reason}</div>
            )}
          </>
        )}
        {msg && (
          <div style={{ marginTop: '10px', fontSize: '12px', color: msg.ok ? GOOD : '#fca5a5' }}>{msg.text}</div>
        )}
      </Card>
    </>
  );
}

// Orari di trading: spenti di default. Fuori dalle fasce il bot non apre nulla di nuovo e lascia chiudere da sole le
// posizioni aperte (come la Pausa, ma da solo). Il tasto Pausa vince sempre. Lo accende solo l'utente, da qui.
const newWindow = () => ({ days: [0, 1, 2, 3, 4, 5, 6], start: '08:00', end: '22:00' });

const draftFrom = (cfg) => ({
  enabled: !!cfg?.enabled,
  tz: cfg?.tz || 'Europe/Rome',
  windows: cfg?.windows?.length
    ? cfg.windows.map(w => ({ days: w.days || [0, 1, 2, 3, 4, 5, 6], start: w.start, end: w.end }))
    : [newWindow()],
});

function HoursControl({ portfolio }) {
  const isBull = portfolio === 'bull';
  const name = isBull ? 'Toro' : 'Falco';
  const icon = isBull ? '🐂' : '🦅';
  const [info, setInfo] = useState(null);       // {config, state, supported} come lo vede il server
  const [draft, setDraft] = useState(null);     // cio' che stai modificando
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const dirtyRef = useRef(false);
  dirtyRef.current = dirty;

  const load = React.useCallback(async () => {
    try {
      const { data } = await apiFor(portfolio).getHours();
      setInfo(data);
      if (!dirtyRef.current) setDraft(draftFrom(data.config));   // non butto via cio' che stai scrivendo
    } catch { /* riprovo al prossimo giro */ }
  }, [portfolio]);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const change = (fn) => { setDraft(d => fn(d)); setDirty(true); setMsg(null); };
  const setWindow = (i, patch) => change(d => ({ ...d, windows: d.windows.map((w, k) => (k === i ? { ...w, ...patch } : w)) }));
  const toggleDay = (i, day) => change(d => ({
    ...d,
    windows: d.windows.map((w, k) => {
      if (k !== i) return w;
      const has = w.days.includes(day);
      return { ...w, days: has ? w.days.filter(x => x !== day) : [...w.days, day].sort() };
    }),
  }));

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      const { data } = await apiFor(portfolio).setHours(draft);
      setInfo(data); setDraft(draftFrom(data.config)); setDirty(false);
      setMsg({ ok: true, text: data.message });
    } catch (e) { setMsg({ ok: false, text: errMsg(e) }); }
    finally { setBusy(false); }
  };

  const state = info?.state;
  const supported = info?.supported;
  const color = isBull ? '#a78bfa' : '#38bdf8';
  const inp = { background: '#0f172a', color: '#f1f5f9', border: `1px solid ${BORDER}`, borderRadius: '8px', padding: '6px 8px', fontSize: '13px' };

  return (
    <>
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        🕒 {icon} {name} — Orari di trading
      </h2>
      <Card style={{ marginBottom: '16px' }}>
        {!draft ? (
          <div style={{ color: '#64748b', fontSize: '13px' }}>Caricamento...</div>
        ) : (
          <>
            <div style={{ fontSize: '12px', color: MUTED, marginBottom: '10px' }}>
              Spenti di default. Se li attivi, {name} apre nuovi trade <strong style={{ color: '#cbd5e1' }}>solo nelle fasce</strong> qui sotto.
              Fuori fascia si comporta come in pausa: non apre niente di nuovo e lascia chiudere da sole le posizioni già aperte
              (nessuna chiusura forzata). Il tasto Pausa vince sempre. Gli orari sono nel fuso scelto qui sotto.
            </div>
            {!supported && (
              <div style={{ marginBottom: '10px', padding: '8px 10px', borderRadius: '8px', background: 'rgba(251,191,36,0.08)', color: WARN, fontSize: '12px' }}>
                Il bot gira ancora con la versione precedente e non conosce gli orari: potrai attivarli dopo la ridistribuzione dei bot.
              </div>
            )}
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', fontSize: '14px', fontWeight: 'bold', color: draft.enabled ? GOOD : MUTED, cursor: 'pointer' }}>
              <input type="checkbox" checked={draft.enabled} disabled={busy || (!supported && !draft.enabled)}
                     onChange={e => change(d => ({ ...d, enabled: e.target.checked }))} />
              {draft.enabled ? 'Orari attivi' : 'Orari spenti'}
            </label>

            {state?.mode === 'on' && (
              <div style={{ marginTop: '8px', fontSize: '12px', color: state.blocked ? WARN : GOOD }}>
                {state.blocked ? '⏸ Adesso: fuori orario (nessuna nuova apertura)' : '▶ Adesso: dentro orario'}
                {state.next_change_ms ? ` · ${state.blocked ? 'riparte' : 'finisce'} ${fmtDateTime(state.next_change_ms)}` : ''}
              </div>
            )}
            {state?.mode === 'invalid' && (
              <div style={{ marginTop: '8px', fontSize: '12px', color: '#fca5a5' }}>
                ⚠️ Il bot non riesce a leggere il file degli orari ({state.error || 'errore'}): per prudenza non apre nuovi trade. Salva di nuovo gli orari.
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '12px', fontSize: '12px', color: MUTED }}>
              Fuso
              <select value={draft.tz} onChange={e => change(d => ({ ...d, tz: e.target.value }))} style={inp}>
                <option value="Europe/Rome">Italia / Svizzera (ora legale automatica)</option>
                <option value="UTC">UTC</option>
              </select>
            </div>

            {draft.windows.map((w, i) => (
              <div key={i} style={{ marginTop: '10px', padding: '10px', borderRadius: '10px', border: `1px solid ${BORDER}`, background: 'rgba(15,23,42,0.5)' }}>
                <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginBottom: '8px' }}>
                  {DAY_LABELS.map((lab, day) => {
                    const on = w.days.includes(day);
                    return (
                      <button key={day} type="button" title={DAY_NAMES[day]} onClick={() => toggleDay(i, day)} style={{
                        width: '32px', height: '32px', borderRadius: '8px', fontWeight: 'bold', fontSize: '12px', cursor: 'pointer',
                        border: `1px solid ${on ? color : BORDER}`, background: on ? color + '22' : 'none', color: on ? color : '#64748b',
                      }}>{lab}</button>
                    );
                  })}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', fontSize: '12px', color: MUTED }}>
                  dalle <input type="time" value={w.start} onChange={e => setWindow(i, { start: e.target.value })} style={inp} />
                  alle <input type="time" value={w.end} onChange={e => setWindow(i, { end: e.target.value })} style={inp} />
                  <button type="button" onClick={() => change(d => ({ ...d, windows: d.windows.filter((_, k) => k !== i) }))}
                          style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#f87171', cursor: 'pointer', fontSize: '12px' }}>
                    Togli
                  </button>
                </div>
                {w.end <= w.start && (
                  <div style={{ fontSize: '11px', color: '#64748b', marginTop: '6px' }}>
                    {w.end === w.start ? '⚠️ Inizio e fine uguali: non vale.' : 'Finisce il giorno dopo (i giorni indicano quando la fascia INIZIA).'}
                  </div>
                )}
              </div>
            ))}
            <button type="button" onClick={() => change(d => ({ ...d, windows: [...d.windows, newWindow()] }))}
                    style={{ ...bigBtn(!busy, color, 'none'), marginTop: '10px' }}>
              + Aggiungi una fascia
            </button>

            <button onClick={save} disabled={!dirty || busy} style={bigBtn(dirty && !busy, GOOD, 'rgba(74,222,128,0.08)')}>
              {busy ? '⏳ Salvataggio…' : dirty ? '💾 Salva orari' : 'Nessuna modifica da salvare'}
            </button>
          </>
        )}
        {msg && <div style={{ marginTop: '10px', fontSize: '12px', color: msg.ok ? GOOD : '#fca5a5' }}>{msg.text}</div>}
      </Card>
    </>
  );
}

// Parametri veri, letti dal bot (non piu' scritti a mano nell'app)
function ParamsCard() {
  const [params, setParams] = useState({ hawk: null, bull: null });
  useEffect(() => {
    deskAPI.getStatus().then(({ data }) => setParams(p => ({ ...p, hawk: data?.params || null }))).catch(() => {});
    bullAPI.getStatus().then(({ data }) => setParams(p => ({ ...p, bull: data?.params || null }))).catch(() => {});
  }, []);
  const block = (label, color, p) => (
    <>
      <div style={{ fontSize: '12px', color, fontWeight: 'bold', margin: '10px 0 6px' }}>{label}</div>
      {!p ? <div style={{ color: '#64748b', fontSize: '12px' }}>Disponibili appena il bot ha il primo battito.</div>
        : PARAM_ROWS.map(([l, get, show]) => (get(p) == null ? null : <Row key={l} label={l} value={show(get(p))} color={color} />))}
    </>
  );
  return (
    <Card style={{ marginBottom: '16px' }}>
      <div style={{ fontSize: '11px', color: '#64748b', marginBottom: '4px' }}>
        Sono i valori con cui il bot sta davvero girando. Per cambiarli chiedi a Claude: la modifica passa dal codice e
        vale dal riavvio del bot. Poi azzera il portafoglio qui sopra, così la nuova run parte pulita e puoi confrontarla con la precedente in Performance → Run.
      </div>
      {block('🦅 FALCO', '#38bdf8', params.hawk)}
      {block('🐂 TORO', '#a78bfa', params.bull)}
      <div style={{
        marginTop: '12px', padding: '8px 10px', borderRadius: '8px',
        background: 'rgba(56,189,248,0.07)', border: '1px solid rgba(56,189,248,0.2)',
        fontSize: '11px', color: '#38bdf8'
      }}>
        💡 Se Claude propone margine o leva sotto i minimi del portafoglio, il codice li porta ai minimi indicati sopra.
      </div>
    </Card>
  );
}

export default function Settings() {
  const [showLogs, setShowLogs] = useState(false);
  const [showPwdForm, setShowPwdForm] = useState(false);
  const [pwdMsg, setPwdMsg] = useState('');
  const [pwdStatus, setPwdStatus] = useState(null);

  useEffect(() => {
    botAPI.passwordStatus().then(({ data }) => setPwdStatus(data)).catch(() => {});
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

      {/* ── Stato e comandi dei due portafogli ── */}
      <PortfolioControl portfolio="hawk" />
      <PortfolioControl portfolio="bull" />

      {/* ── Orari di trading (spenti di default) ── */}
      <HoursControl portfolio="hawk" />
      <HoursControl portfolio="bull" />

      {/* ── Parametri con cui gira il bot ── */}
      <h2 style={{ fontSize: '15px', fontWeight: 'bold', marginBottom: '8px', color: '#cbd5e1' }}>
        📐 Parametri del bot
      </h2>
      <ParamsCard />

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
