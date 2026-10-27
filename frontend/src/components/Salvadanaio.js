import React from 'react';

const money = value => Number(value).toLocaleString('it-IT', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export default function Salvadanaio({ data }) {
  return (
    <section aria-label="Salvadanaio" style={{ background: '#172b2a', border: '1px solid #2d6653', borderRadius: 16, padding: 16, marginBottom: 12 }}>
      <h3 style={{ margin: '0 0 8px', color: '#86efac' }}>Salvadanaio</h3>
      {!data?.available ? <p style={{ margin: 0, color: '#94a3b8' }}>{data?.message || 'Salvadanaio non ancora attivo sul bot PAPER.'}</p> : <>
        <div style={{ fontSize: 28, fontWeight: 'bold', color: '#86efac' }}>${money(data.balance)}</div>
        <p style={{ color: '#cbd5e1', fontSize: 13 }}>Accantonato oggi (UTC): <strong>${money(data.deposited_today)}</strong> · PAPER</p>
        {!data.bot_online && <p style={{ color: '#fbbf24' }}>Bot offline: ultimo saldo salvato.</p>}
        {!data.ready && <p style={{ color: '#fbbf24' }}>Accantonamento in attesa di verifica. Le somme in attesa non sono ancora nel Salvadanaio.</p>}
        {Number(data.pending) > 0 && <p style={{ color: '#94a3b8', fontSize: 12 }}>In attesa di liquidità o realizzo: ${money(data.pending)}. Non incluso nel saldo.</p>}
        <p style={{ color: '#94a3b8', fontSize: 12 }}>{data.message} Chiusura giornata alle 00:00 UTC; nessuna chiusura forzata delle posizioni.</p>
        {data.days?.length ? <details><summary style={{ cursor: 'pointer', color: '#cbd5e1' }}>Storico giornaliero degli accantonamenti</summary>
          <table style={{ width: '100%', marginTop: 8, fontSize: 12, color: '#cbd5e1' }}><thead><tr><th align="left">Data accredito (UTC)</th><th align="right">Accantonato netto</th></tr></thead>
            <tbody>{data.days.map(day => <tr key={day.utc_day}><td>{day.utc_day}</td><td align="right">${money(day.amount)}</td></tr>)}</tbody>
          </table>{data.day_count > data.days.length && <p style={{ color: '#94a3b8', fontSize: 12 }}>Ultimi {data.days.length} giorni di accredito; storico completo conservato dal bot.</p>}
        </details> : <p style={{ color: '#94a3b8', fontSize: 12 }}>Nessun accantonamento registrato dall’attivazione.</p>}
      </>}
    </section>
  );
}
