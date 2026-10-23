import React, { useCallback, useEffect, useState } from 'react';
import { deskAPI } from '../api';

// Capital V1 component is deliberately invisible until the PAPER bot confirms
// capital_v1 capability and a reconciled state. Never infer balances from legacy.
export default function CapitalPanel({ portfolio }) {
  const api = portfolio === 'bull'
    ? {getCapital: deskAPI.getBullCapital,
       withdrawFromVault: deskAPI.withdrawFromBullVault,
       getCapitalTransfer: deskAPI.getBullCapitalTransfer}
    : deskAPI;
  const [capital, setCapital] = useState(null);
  const [pending, setPending] = useState(null);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const { data } = await api.getCapital();
      setCapital(data?.available === true ? data : null);
    } catch (_) {
      setCapital(null);
    }
  }, [portfolio]); // api is selected deterministically by portfolio

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10000);
    return () => clearInterval(timer);
  }, [refresh]);

  useEffect(() => {
    if (!pending) return undefined;
    let cancelled = false;
    const poll = async () => {
      try {
        const { data } = await api.getCapitalTransfer(pending);
        if (cancelled) return;
        if (data.status === 'completed') {
          setNotice('✅ Trasferimento completato dal bot.');
          setPending(null);
          refresh();
        } else if (data.status === 'rejected') {
          setNotice('❌ Trasferimento rifiutato: ' + (data.reason || 'verifica i saldi'));
          setPending(null);
          refresh();
        }
      } catch (_) {
        if (!cancelled) setNotice('Trasferimento in verifica: nessun nuovo invio automatico.');
      }
    };
    poll();
    const timer = setInterval(poll, 3500);
    return () => { cancelled = true; clearInterval(timer); };
  }, [pending, portfolio, refresh]);

  const transfer = async () => {
    if (!capital?.can_withdraw || busy || pending) return;
    const raw = window.prompt('Quanto vuoi trasferire dal salvadanaio al portafoglio PAPER? (USD)');
    if (raw == null) return;
    const amount = raw.trim();
    if (!/^\d+(?:\.\d{1,2})?$/.test(amount) || Number(amount) <= 0 ||
        Number(amount) > Number(capital.vault_balance)) {
      setNotice('Importo non valido o superiore al saldo del salvadanaio.');
      return;
    }
    if (!window.confirm('Confermi il trasferimento manuale di $' + amount +
        ' dal salvadanaio ' + portfolio.toUpperCase() +
        '? Non modifica i limiti giornalieri.')) return;
    const id = crypto.randomUUID();
    setBusy(true);
    setNotice('');
    try {
      const { data } = await api.withdrawFromVault({
        idempotency_key: id, amount, expected_revision: capital.revision,
      });
      // "queued" is NOT a completed transfer.
      if (data.status === 'completed') {
        setNotice('✅ Trasferimento confermato dal bot.');
        refresh();
      } else {
        setPending(id);
        setNotice('Richiesta ricevuta. Attendo la conferma contabile del bot.');
      }
    } catch (e) {
      setNotice('Errore: ' + (e?.response?.data?.detail || e?.message || 'richiesta non riuscita'));
    } finally {
      setBusy(false);
    }
  };

  if (!capital) return null;
  const fmt = (n) => n == null ? 'non verificato' : '$' + Number(n).toFixed(2);
  const rows = [
    ['Capitale operativo', fmt(capital.operating_equity)],
    ['Budget per nuovi ingressi', fmt(capital.day_budget)],
    ['Salvadanaio protetto', fmt(capital.vault_balance)],
    ['Accantonamento in attesa (non garantito)', fmt(capital.pending)],
    ['Patrimonio totale', fmt(capital.total_equity)],
    ['Margine massimo per posizione', capital.position_cap_pct + '% del budget'],
    ['Stop giornaliero', capital.daily_stop_pct + '% · ' +
      (capital.stop_latched ? 'BLOCCO ATTIVO' : 'non attivo')],
    ['Protezione assoluta', fmt(capital.kill_equity)],
  ];

  return (
    <section style={{ border: '1px solid #334155', borderRadius: 14,
                      padding: 14, marginBottom: 12, background: '#172333',
                      color: '#e2e8f0', fontSize: 13 }}>
      <strong>🏦 Gestione capitale · {portfolio.toUpperCase()} · PAPER</strong>
      <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 5 }}>
        Giorno UTC {capital.utc_day} · dati {capital.valuation_fresh ? 'verificati' : 'non aggiornati'}
        {' · '}versione {capital.version || 'non disponibile'}
      </div>
      {rows.map(([label, value]) => (
        <div key={label} style={{ display: 'flex', justifyContent: 'space-between',
                                  gap: 8, marginTop: 8 }}>
          <span style={{ color: '#94a3b8' }}>{label}</span><strong>{value}</strong>
        </div>
      ))}
      <button type="button" disabled={!capital.can_withdraw || busy || !!pending}
              onClick={transfer}
              style={{ marginTop: 12, width: '100%', padding: 10, borderRadius: 9,
                       background: '#334155', border: '1px solid #64748b',
                       color: '#e2e8f0', opacity: !capital.can_withdraw || pending ? 0.5 : 1 }}>
        {busy ? 'Invio richiesta…' : pending ? 'Verifica trasferimento in corso…' :
          'Trasferisci dal salvadanaio al portafoglio'}
      </button>
      {notice && <div role="status" style={{ marginTop: 8, color: '#cbd5e1' }}>{notice}</div>}
    </section>
  );
}
